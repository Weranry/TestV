"""预渲染任务的持久化与成品图缓存读写。

每个入口先判 `is_db_available()`：Vercel 模式没有持久存储，这里必须整体降级成
「没有预渲染」，而不是抛错。渲染热路径上的命中查询也只在这一层做判断。
"""
import asyncio
import threading

from modules.database.core import _exec, _exec_many, _delete_batched, is_db_available
from modules.errors.errors import AccessDeniedError, ParamError
from modules.prerender import memcache
from modules.prerender.keying import build_identity
from modules.utils import plog

# 命中计数先在内存累计，由后台刷盘线程落库：命中路径是热路径，
# 每次命中都写一次库等于把「省下来的渲染」又花在 IO 上。
_pending_hits = {}
_hits_lock = threading.Lock()

TASK_COLUMNS = (
    'id, name, plugin_name, route_path, route_kind, size, params_json, cache_key, enabled, '
    'schedule_type, interval_seconds, daily_time, cron_expr, cache_ttl_hours, next_run_at, '
    'last_run_at, last_status, last_error, last_ms, run_count, hit_count, created_at'
)


# ======================== 任务 ========================

def list_tasks():
    if not is_db_available():
        return []
    return _exec(f'SELECT {TASK_COLUMNS} FROM prerender_tasks ORDER BY id DESC', fetch_all=True)


def get_task(task_id):
    if not is_db_available():
        return None
    return _exec(f'SELECT {TASK_COLUMNS} FROM prerender_tasks WHERE id = ?',
                 (task_id,), fetch_one=True)


def get_task_by_cache_key(cache_key):
    if not is_db_available():
        return None
    return _exec(f'SELECT {TASK_COLUMNS} FROM prerender_tasks WHERE cache_key = ?',
                 (cache_key,), fetch_one=True)


def create_task(name, plugin_name, route_path, route_kind, size, params_json, cache_key,
                enabled, schedule_type, interval_seconds, daily_time, cache_ttl_hours,
                next_run_at, cron_expr=''):
    if not is_db_available():
        raise RuntimeError('当前模式不支持定时预渲染')
    return _exec(
        'INSERT INTO prerender_tasks (name, plugin_name, route_path, route_kind, size, '
        'params_json, cache_key, enabled, schedule_type, interval_seconds, daily_time, '
        'cache_ttl_hours, next_run_at, cron_expr) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (name, plugin_name, route_path, route_kind, size, params_json, cache_key,
         1 if enabled else 0, schedule_type, interval_seconds, daily_time, cache_ttl_hours,
         next_run_at, cron_expr),
        commit=True,
    )


def update_task(task_id, **fields):
    """按字段更新任务；函数内部拼 SQL，key 只可能是代码里写死的列名"""
    if not is_db_available() or not fields:
        return
    cols = ', '.join(f'{k} = ?' for k in fields)
    _exec(f'UPDATE prerender_tasks SET {cols} WHERE id = ?',
          tuple(fields.values()) + (task_id,), commit=True)


def delete_task(task_id):
    if not is_db_available():
        return
    _exec('DELETE FROM prerender_tasks WHERE id = ?', (task_id,), commit=True)
    delete_cache_by_task(task_id)


def mark_run(task_id, status, error, elapsed_ms, next_run_at):
    """写回一次执行结果：run_count 自增交给 SQL，避免读-改-写丢计数"""
    if not is_db_available():
        return
    _exec(
        "UPDATE prerender_tasks SET last_run_at = datetime('now'), last_status = ?, "
        'last_error = ?, last_ms = ?, next_run_at = ?, run_count = run_count + 1 WHERE id = ?',
        (status, error or '', elapsed_ms, next_run_at, task_id), commit=True,
    )


# 每轮调度最多取的任务数：到期任务积压时若一轮全取，调度循环会被这批任务长时间占住，
# 后面的 tick 只能排队，实时性反而更差
DUE_BATCH_LIMIT = 20


def due_tasks(now_iso):
    """到期且已启用的任务（按到期时间升序），调度循环每轮取一批"""
    if not is_db_available():
        return []
    return _exec(
        f'SELECT {TASK_COLUMNS} FROM prerender_tasks '
        'WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ? '
        'ORDER BY next_run_at ASC LIMIT ?',
        (now_iso, DUE_BATCH_LIMIT), fetch_all=True,
    )


# ======================== 成品缓存 ========================

# 「库里到底有没有成品」的内存标志：一个成品都没有时，每个取图请求都不必再进 worker
# 线程查一次 prerender_cache。
#
# 只朝"有成品"的方向翻转：put_cache 置 True；clear_cache 是唯一把它翻回 False 的地方
# （那条路径保证表已空）。其余删除路径（单键删除 / 裁剪 / 寿命回收）不动它——标志偏高
# 的代价只是"多查一次库"（等于改造前的行为），而偏低会变成"有成品却不去命中"。
_artifacts_probed = False
_has_artifacts = False


def _probe_artifacts():
    """首次调用时探一次库；之后只读内存标志。探测失败按"有成品"处理，宁可多查一次"""
    global _artifacts_probed, _has_artifacts
    if _artifacts_probed:
        return _has_artifacts
    try:
        _has_artifacts = _exec(
            'SELECT 1 FROM prerender_cache LIMIT 1', fetch_one=True) is not None
    except Exception:
        _has_artifacts = True
    _artifacts_probed = True
    return _has_artifacts


def put_cache(cache_key, task_id, art_kind, width, height, payload, render_ms):
    """写一份与后处理无关的产物。

    覆盖时不动 last_hit_at：寿命看的是"最后一次被请求"，重渲一次不该给没人读的条目续命。
    """
    global _has_artifacts, _artifacts_probed
    if not is_db_available():
        return
    _exec(
        'INSERT INTO prerender_cache (cache_key, task_id, art_kind, width, height, payload, '
        "size_bytes, rendered_at, render_ms) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?) "
        'ON CONFLICT(cache_key) DO UPDATE SET task_id = excluded.task_id, '
        'art_kind = excluded.art_kind, width = excluded.width, height = excluded.height, '
        'payload = excluded.payload, size_bytes = excluded.size_bytes, '
        'rendered_at = excluded.rendered_at, render_ms = excluded.render_ms',
        (cache_key, task_id, art_kind, width, height, payload, len(payload), render_ms),
        commit=True,
    )
    # 现在库里至少有这一份了：命中路径不必再走首次探测
    _has_artifacts = True
    _artifacts_probed = True
    # 覆盖后内存里这份键的编码结果就过期了（同键新图）：只摘这一个键派生出的条目，
    # 整体清空会把其它任务的热点产物一起打掉，下一轮全部重新编码
    memcache.delete_identity(cache_key)


def get_cache(cache_key):
    if not is_db_available():
        return None
    return _exec('SELECT * FROM prerender_cache WHERE cache_key = ?', (cache_key,), fetch_one=True)


def delete_cache(cache_key):
    if not is_db_available():
        return
    _exec('DELETE FROM prerender_cache WHERE cache_key = ?', (cache_key,), commit=True)
    memcache.delete_identity(cache_key)


def delete_cache_by_task(task_id):
    if not is_db_available():
        return
    _exec('DELETE FROM prerender_cache WHERE task_id = ?', (task_id,), commit=True)
    memcache.clear()


def clear_cache():
    """清空全部成品缓存（任务保留，下个周期会重新生成）"""
    global _has_artifacts, _artifacts_probed
    if not is_db_available():
        return
    # 与 request_logs 的清理同一处理：整表单条 DELETE 会长时间占住全局写锁，切成小批
    _delete_batched(
        'DELETE FROM prerender_cache WHERE rowid IN ('
        'SELECT rowid FROM prerender_cache LIMIT ?)',
        (),
    )
    # 这条路径保证表已经空了，是唯一可以把标志翻回 False 的地方
    _has_artifacts = False
    _artifacts_probed = True
    memcache.clear()


def cache_summary():
    """缓存条目数与总字节数（面板展示 + 裁剪依据）"""
    if not is_db_available():
        return {'rows': 0, 'bytes': 0}
    row = _exec('SELECT COUNT(*) as rows, COALESCE(SUM(size_bytes), 0) as bytes FROM prerender_cache',
                fetch_one=True)
    return dict(row) if row else {'rows': 0, 'bytes': 0}


# 「最近一次使用时间」：被请求过就看命中时间，从没被请求过退化为生成时间。
# 淘汰与寿命判定必须共用这一个口径，否则天天被屏端命中的热条目会因为 rendered_at
# 旧而被先淘汰。寿命用的是 COALESCE(c.last_hit_at, c.rendered_at)，与此同源。
_RECENT = 'COALESCE(last_hit_at, rendered_at)'


def _as_limit(value):
    """上限统一规整成非负整数：非数字、负数一律当 0（= 不启用该上限）"""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def trim_cache(max_rows, max_mb):
    """按条数与总字节双上限淘汰，保留「最近使用」的前缀（LRU），返回删除条数。

    两段各用一条 SQL 删「不在保留集里」的行，而不是「取第 N+1 条的时间当水位再 < 比较」：
    批量渲染常让多条 rendered_at 落在同一秒，水位比较会一条都删不掉，条数上限静默失效。
    排序并列时用 cache_key 兜底，保证顺序稳定。
    """
    if not is_db_available():
        return 0
    max_rows = _as_limit(max_rows)
    max_mb = _as_limit(max_mb)
    if max_rows <= 0 and max_mb <= 0:
        return 0
    # 删除条数直接取 rowcount：原先在前后各跑一次 cache_summary()（全表 COUNT+SUM）
    # 再相减，等于每次裁剪多扫两遍全表。两段 NOT IN 删的是同一快照下的不相交集合，
    # 条数相加即总数。
    deleted = 0
    if max_rows > 0:
        deleted += _exec(
            'DELETE FROM prerender_cache WHERE cache_key NOT IN ('
            f'SELECT cache_key FROM prerender_cache ORDER BY {_RECENT} DESC, cache_key DESC LIMIT ?)',
            (max_rows,), commit=True, rowcount=True,
        ) or 0
    if max_mb > 0:
        # 窗口函数按同一顺序累加字节，只保留累计不超过上限的最新前缀；
        # 连最新一条都超上限时整个前缀为空，等于全清——否则会永远超限
        deleted += _exec(
            'DELETE FROM prerender_cache WHERE cache_key NOT IN ('
            'SELECT cache_key FROM (SELECT cache_key, SUM(size_bytes) OVER ('
            f'ORDER BY {_RECENT} DESC, cache_key DESC) AS cum FROM prerender_cache) WHERE cum <= ?)',
            (max_mb * 1024 * 1024,), commit=True, rowcount=True,
        ) or 0
    # 只在确实删了行时清内存缓存：这条清理由后台线程按周期驱动，无条件清空会把
    # 「本实例内存里有、库里也有」的热门产物每轮清一次，缓存等于白做
    if deleted:
        memcache.clear()
    return deleted


# 寿命判定：任务设了 cache_ttl_hours 且「最后一次被请求」早于 now-ttl 即视为可回收。
# 用 COALESCE 是因为从没被请求过也算到了寿命，否则一个没人读的新条目永远不会被回收。
_EXPIRED_WHERE = (
    'FROM prerender_cache c JOIN prerender_tasks t ON t.id = c.task_id '
    'WHERE t.cache_ttl_hours > 0 '
    "AND COALESCE(c.last_hit_at, c.rendered_at) < datetime('now', '-' || t.cache_ttl_hours || ' hours')"
)


def count_expired():
    """按寿命已可回收的条目数（面板提示"下次清理会释放多少"）"""
    if not is_db_available():
        return 0
    row = _exec(f'SELECT COUNT(*) as n {_EXPIRED_WHERE}', fetch_one=True)
    return int(row['n']) if row else 0


def purge_expired():
    """回收超过任务寿命且期间没被请求过的产物，返回删除条数

    条数直接取 DELETE 的 rowcount：再调一次 count_expired() 等于把同一条件扫两遍
    （面板要"预计释放多少"时自己调 count_expired()，不在这里重复）。
    """
    if not is_db_available():
        return 0
    deleted = _exec(
        f'DELETE FROM prerender_cache WHERE cache_key IN (SELECT c.cache_key {_EXPIRED_WHERE})',
        commit=True, rowcount=True,
    ) or 0
    # 同 trim_cache：这条由后台线程按周期驱动，只在真删了行时才清内存缓存
    if deleted:
        memcache.clear()
    return deleted


# ======================== 命中统计 ========================

def flush_hits():
    """把内存累计的命中次数落库（由后台刷盘线程调用）

    一并刷新 last_hit_at：寿命回收只认"最后一次被请求"，而命中是热路径不能每次写库。
    所有 key 的写入合并进一个事务：原先每个 key 两条独立的 commit，命中多的批次
    会连着做几十次 fsync。
    """
    if not is_db_available() or not _pending_hits:
        return
    with _hits_lock:
        pending = dict(_pending_hits)
        _pending_hits.clear()
    statements = []
    for cache_key, cnt in pending.items():
        statements.append(
            ('UPDATE prerender_tasks SET hit_count = hit_count + ? WHERE cache_key = ?',
             (cnt, cache_key)))
        statements.append(
            ("UPDATE prerender_cache SET last_hit_at = datetime('now') WHERE cache_key = ?",
             (cache_key,)))
    try:
        _exec_many(statements)
    except Exception:
        pass


# ======================== 命中路径 ========================

def _mark_hit(request, cache_key):
    try:
        from modules.generate_views import render_metrics
        render_metrics.mark_hit()
    except Exception:
        pass
    try:
        request.state.prerender_hit = True
    except Exception:
        pass
    with _hits_lock:
        _pending_hits[cache_key] = _pending_hits.get(cache_key, 0) + 1


def _mem_key(cache_key, fmt, params):
    """内存成品缓存的键：同一份产物按「本次请求的输出格式 + 后处理」各存一份。

    预渲染缓存键刻意剔除了 rotate/invert/cmode/format（产物与后处理无关），
    所以这里必须补回来——编码结果是后处理的函数，不补就会把 90° 的图当 0° 返回。
    """
    return (cache_key, fmt, params.get('rotate') or 0,
            bool(params.get('invert')), params.get('cmode'))


def _encode_indexed(row, params, plugin_name, route_path, fmt):
    """索引图产物行 → 编码好的响应体四元组 (content, mime, filename, raw_len)

    「解码 → 后处理 → 编码」全是 CPU 密集的同步操作，调用方负责放在 worker 线程里。
    """
    from modules.prerender.artifact import decode_canonical
    from modules.generate_views.image_output import build_image_bytes
    from modules.generate_views.image_transform import invert_image, rotate_image

    img = decode_canonical(row['payload'], row['art_kind'], params.get('cmode'))
    img = rotate_image(img, params.get('rotate') or 0)
    if params.get('invert'):
        img = invert_image(img)

    kind = (route_path or '').rstrip('/').split('/')[-1]
    name_parts = [plugin_name, kind, str(params.get('size') or '')]
    return build_image_bytes(img, fmt, name_parts)


def _serve_cached(cache_key, params, plugin_name, route_path, group_id, route_kind):
    """命中路径里所有同步阻塞的部分：读产物行（含整块 BLOB）+ 后处理 + 构造响应。

    整体丢给 worker 线程执行，故这里不碰 request / request.state。
    """
    from modules.generate_views.image_output import (
        build_response_from_bytes, check_format_allowed, ensure_format_supported)

    fmt = str(params.get('fmt') or '').lower()
    if route_kind != 'json':
        # 格式黑名单与用户组权限校验必须每请求重跑：图是之前生成的，组权限可能在那之后被改掉。
        # 它俩只读配置与内存权限缓存、不碰库，放在内存缓存之前是廉价的。
        check_format_allowed(fmt, group_id)
        ensure_format_supported(fmt)

        # 内存成品缓存必须**先于**读库：产物 BLOB 正是这条路径的主要开销之一，
        # 命中内存却仍去读一遍 BLOB，等于只省了编码、没省 IO。
        # 这里能跳过读行是安全的——build_identity 已把 route_kind 折进 cache_key，
        # 视图键与 JSON 键不可能指向同一行；而所有删除 / 覆盖产物行的入口都会 clear()。
        key = _mem_key(cache_key, fmt, params)
        payload = memcache.get(key)
        if payload is not None:
            return build_response_from_bytes(*payload)
        row = get_cache(cache_key)
        if not row:
            return None
        payload = _encode_indexed(row, params, plugin_name, route_path, fmt)
        memcache.put(key, payload)
        return build_response_from_bytes(*payload)

    row = get_cache(cache_key)
    if not row:
        return None
    if row['art_kind'] == 'json':
        from fastapi.responses import Response
        return Response(content=row['payload'] or b'', media_type='application/json')
    # 键里 kind 对不上却拿到图片产物：按坏产物处理，回落实时渲染
    return None


async def try_serve(request, plugin_name, route_path, params, route_kind='view', group_id=None):
    """命中成品缓存则返回响应，否则 None（未启用预渲染 / 无库 / 未命中 / 格式被拒）

    命中会在 request.state 上打标记，供请求日志把这条记为 cache_hit —— 命中只有
    约 1ms，与真实渲染混在一起算分位，会把 p50/p95 整体拉低。

    这里只看总开关 PRERENDER_ENABLE，**不看 app.state.prerender_enabled**：后者是
    「本实例是否负责调度」，多实例下只有 leader 为真，而产物是全集群共用的，非 leader
    一样要直接返回它——否则预渲染只在 leader 上省事，其余实例全在实时渲染。

    读库与 Pillow 解码都是同步阻塞操作，必须走 worker 线程：这条路径在事件循环里
    被每个带缓存的请求走到，直接调用会把并发的 /healthz 等请求一起卡住。
    """
    import config
    if not config.PRERENDER_ENABLE or not is_db_available():
        return None
    # 一个成品都没有（常见于没配任何预渲染任务的部署）时，这条路径整段跳过：
    # 省下一次 worker 线程调度 + 一次索引查询。首次探测要走库，故同样下放线程；
    # 之后是纯内存标志，不再付线程开销。
    if not _artifacts_probed:
        await asyncio.to_thread(_probe_artifacts)
    if not _has_artifacts:
        return None
    cache_key = build_identity(plugin_name, route_path, params, route_kind)
    try:
        response = await asyncio.to_thread(
            _serve_cached, cache_key, params, plugin_name, route_path, group_id, route_kind)
    except (ParamError, AccessDeniedError):
        # 格式被禁 / 用户组无权：是本次请求的问题，产物本身没问题，原样上抛，
        # 让路由层的 403 / 400 语义保留（不能当成坏产物删掉缓存行）
        raise
    except Exception:
        # 产物 BLOB 损坏 / 非图片字节：删掉这行坏产物并回落实时渲染，否则该路由会被
        # 这一行永久打断（视图路径 400、JSON 路径 500）。留痕但不静默。
        plog.exception(f'预渲染产物不可用，已删除缓存并回落实时渲染: {cache_key}')
        delete_cache(cache_key)
        return None
    if response is None:
        return None
    _mark_hit(request, cache_key)
    return response