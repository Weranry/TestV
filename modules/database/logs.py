import queue
import threading
from cachetools import TTLCache

from modules.database.core import _exec, _get_conn, _db_lock, _ensure_log_queue, _delete_batched

# 队列写满时日志会被静默丢弃：原来既不计数也不上报，刷爆当天只看得到"队列满"，
# 丢掉多少条完全无感。这里只做进程内累计计数，不进热路径的写库。
_dropped = 0
_dropped_lock = threading.Lock()

def log_request(timestamp, path, method, plugin_name, status_code, duration_ms, error,
                account_id=None, cache_hit=0, request_id=None):
    try:
        _ensure_log_queue().put_nowait(
            (timestamp, path, method, plugin_name, status_code, duration_ms, error,
             account_id, 1 if cache_hit else 0, request_id)
        )
    except queue.Full:
        global _dropped
        with _dropped_lock:
            _dropped += 1

def dropped_log_count():
    """本次启动以来因队列写满而丢弃的日志条数（健康检查/日志页展示）"""
    with _dropped_lock:
        return _dropped


# 一次提交的最大条数。与 core._delete_batched 同一取向：单个事务越大，写锁与 WAL
# 增长的持续时间越长。批次之间主动放开 _db_lock，排队的写请求才有机会插进来，
# 而不是在"重启后积压满 5000 条"时被一把锁挡到最后。
_LOG_FLUSH_BATCH = 500


def flush_log_queue():
    entries = []
    while True:
        try:
            entries.append(_ensure_log_queue().get_nowait())
        except queue.Empty:
            break
    if not entries:
        return
    conn = _get_conn()
    # evkey 列保留但不再写入：request_logs 是纯追加表，SQLite 删列要整表重建，
    # 为了几个字节不值得。新行的 evkey 为 NULL，查询侧也不再把这一列带出来。
    sql = ('INSERT INTO request_logs (timestamp, path, method, plugin_name, status_code, '
           'duration_ms, error, account_id, cache_hit, request_id) '
           'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
    for start in range(0, len(entries), _LOG_FLUSH_BATCH):
        chunk = entries[start:start + _LOG_FLUSH_BATCH]
        with _db_lock:
            conn.executemany(sql, chunk)
            conn.commit()


def _log_filters(plugin_name=None, min_status=None, account_id=None):
    """request_logs 的公共过滤条件，列表查询与计数共用，避免两处 SQL 各自维护"""
    clauses, params = [], []
    if plugin_name:
        clauses.append('plugin_name = ?')
        params.append(plugin_name)
    if min_status is not None:
        clauses.append('status_code >= ?')
        params.append(min_status)
    if account_id:
        clauses.append('account_id = ?')
        params.append(account_id)
    return (' AND ' + ' AND '.join(clauses)) if clauses else '', params


def _tz_modifier(offset_hours):
    """时区偏移 → SQLite modifier（如 '+8 hours'）；None/0 表示按 UTC 分组"""
    if offset_hours is None:
        return None
    try:
        off = float(offset_hours)
    except (TypeError, ValueError):
        return None
    if not off:
        return None
    return f'{"+" if off > 0 else "-"}{abs(off)} hours'


# 日志列表/导出统一走这份投影：evkey 已不再记录（老行里残留的值也不再对外返回）
_LOG_FIELDS = ('id, timestamp, path, method, plugin_name, status_code, duration_ms, '
               'error, account_id, cache_hit, request_id')


def get_request_logs(limit=100, offset=0, plugin_name=None, min_status=None, account_id=None):
    where, params = _log_filters(plugin_name, min_status, account_id)
    return _exec(
        f'SELECT {_LOG_FIELDS} FROM request_logs WHERE 1=1{where} ORDER BY id DESC LIMIT ? OFFSET ?',
        params + [limit, offset], fetch_all=True,
    )


def get_request_log_count(plugin_name=None, min_status=None, account_id=None):
    where, params = _log_filters(plugin_name, min_status, account_id)
    row = _exec(f'SELECT COUNT(*) as cnt FROM request_logs WHERE 1=1{where}', params, fetch_one=True)
    return row['cnt'] if row else 0


def clear_request_logs():
    row = _exec('SELECT COUNT(*) as cnt FROM request_logs', fetch_one=True)
    deleted = row['cnt'] if row else 0
    # 整表单条 DELETE 会长时间占住全局写锁，与保留期清理同一处理：切成小批
    _delete_batched('DELETE FROM request_logs WHERE id IN ('
                    'SELECT id FROM request_logs LIMIT ?)', ())
    _stats_cache.clear()
    return deleted


# 统计页的聚合结果短缓存：面板是轮询展示、允许秒级延迟，不值得每次全量重算。
# 容量必须留够：键里有 route_pct 的 (插件, 天数, 样本上限) 组合，插件数 × 天数档位
# 很容易超过几十条；容量不够时各键互相挤出，缓存等于没做，每次都退化成跑 5 条窗口
# 聚合 + 拉 5000 行回 Python 算分位。
_stats_cache = TTLCache(maxsize=128, ttl=5)

# 「错误」的口径：下面的聚合一律用 `status_code >= 500`。4xx 是调用方自己的问题
# （参数写错 / 没鉴权 / 路径不存在），属于正常流量——把它们算进错误数与错误率，只会让
# 面板长期被扫描器和配错参数的设备带偏。渲染失败（RenderError）与插件异常都走 5xx，
# 所以这一条口径同时覆盖了这三类。改动时请一并保持 stats.py 与 app_core.py 的同一口径。


def get_request_statistics(days=7, offset_hours=None):
    """统计页聚合：每日趋势、按插件、状态码分布、总计（时间窗口内）

    offset_hours 只影响「每日趋势」的分日边界——库里的 timestamp 是 UTC，
    不换算的话北京时间凌晨的请求会被算进前一天。

    4 条聚合各自扫一遍窗口，叠加起来不便宜；(timestamp, plugin_name) 组合索引
    让窗口裁剪与按插件分组都能走索引，再配一个 5 秒的短缓存兜住面板轮询。
    """
    window = f'-{days} days'
    tzmod = _tz_modifier(offset_hours)
    cache_key = (days, tzmod)
    cached = _stats_cache.get(cache_key)
    if cached is not None:
        return cached
    daily = _exec(
        f"SELECT date(timestamp{', ?' if tzmod else ''}) as dt, COUNT(*) as total, "
        "SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) as errors "
        "FROM request_logs WHERE timestamp >= datetime('now', ?) GROUP BY dt ORDER BY dt ASC",
        ([tzmod] if tzmod else []) + [window], fetch_all=True,
    )
    by_plugin = _exec(
        'SELECT plugin_name, COUNT(*) as total, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) as errors, '
        'ROUND(AVG(duration_ms), 1) as avg_ms FROM request_logs '
        "WHERE plugin_name IS NOT NULL AND plugin_name != '' AND timestamp >= datetime('now', ?) "
        'GROUP BY plugin_name ORDER BY total DESC', (window,), fetch_all=True,
    )
    status_dist = _exec(
        "SELECT CASE WHEN status_code < 300 THEN '2xx' WHEN status_code < 400 THEN '3xx' "
        "WHEN status_code < 500 THEN '4xx' ELSE '5xx' END AS cls, COUNT(*) AS cnt "
        "FROM request_logs WHERE timestamp >= datetime('now', ?) AND status_code IS NOT NULL "
        'GROUP BY cls', (window,), fetch_all=True,
    )
    grand_total = _exec(
        'SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END), 0) as errors, '
        'ROUND(AVG(duration_ms), 1) as avg_ms '
        "FROM request_logs WHERE timestamp >= datetime('now', ?)", (window,), fetch_one=True,
    )
    by_account = _exec(
        'SELECT r.account_id, COALESCE(a.name, "(未知)") as account_name, COUNT(*) as total, '
        'COALESCE(SUM(CASE WHEN r.status_code >= 500 THEN 1 ELSE 0 END), 0) as errors, '
        'ROUND(AVG(r.duration_ms), 1) as avg_ms '
        'FROM request_logs r LEFT JOIN accounts a ON r.account_id = a.id '
        "WHERE r.timestamp >= datetime('now', ?) "
        'GROUP BY r.account_id ORDER BY total DESC',
        (window,), fetch_all=True,
    )
    result = {
        'grand_total': dict(grand_total) if grand_total else {'total': 0, 'errors': 0, 'avg_ms': None},
        'daily': [dict(r) for r in daily],
        'status_dist': [dict(r) for r in status_dist],
        'by_plugin': [dict(r) for r in by_plugin],
        'by_account': [dict(r) for r in by_account],
    }
    _stats_cache[cache_key] = result
    return result


def get_today_summary(offset_hours=None):
    """今日（按配置时区的自然日）请求总量、错误数与平均耗时，供概览页展示。

    与统计页共用 5 秒短缓存：概览是轮询展示，且 /api/status 每 10 秒拉一次。
    """
    tzmod = _tz_modifier(offset_hours)
    cache_key = ('today', tzmod)
    cached = _stats_cache.get(cache_key)
    if cached is not None:
        return cached
    body = (
        'SELECT COUNT(*) as total, '
        'COALESCE(SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END), 0) as errors, '
        'ROUND(AVG(duration_ms), 1) as avg_ms FROM request_logs WHERE '
    )
    if tzmod:
        row = _exec(body + "date(timestamp, ?) = date('now', ?)", (tzmod, tzmod), fetch_one=True)
    else:
        row = _exec(body + 'date(timestamp) = date(\'now\')', fetch_one=True)
    result = dict(row) if row else {'total': 0, 'errors': 0, 'avg_ms': None}
    _stats_cache[cache_key] = result
    return result


def log_queue_size():
    """日志队列当前积压条数（健康检查用）。只读，不触发刷盘"""
    q = _ensure_log_queue()
    return q.qsize(), q.maxsize


def get_plugin_route_stats(plugin_name, days=7):
    """某插件在时间窗口内的按路由统计（统计页按插件展开明细）

    顺带带上 p50/p95：同一次展开里既看请求量也看耗时，避免前端再打一次接口。
    """
    rows = _exec(
        'SELECT path, COUNT(*) as total, COALESCE(SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END), 0) as errors, '
        'ROUND(AVG(duration_ms), 1) as avg_ms FROM request_logs '
        "WHERE plugin_name = ? AND timestamp >= datetime('now', ?) "
        'GROUP BY path ORDER BY total DESC LIMIT 100',
        (plugin_name, f'-{days} days'), fetch_all=True,
    )
    pct = {r['path']: r for r in get_route_percentiles(plugin_name, days)}
    result = []
    for row in rows:
        item = dict(row)
        item['p50_ms'] = None
        item['p95_ms'] = None
        p = pct.get(row['path'])
        if p:
            item['p50_ms'] = p['p50_ms']
            item['p95_ms'] = p['p95_ms']
        result.append(item)
    return result


# 样本太少时分位没有意义（一条记录既是最快也是最慢），低于这个数不给分位
_MIN_PERCENTILE_SAMPLE = 5


def _percentile(sorted_vals, q):
    """已排序列表的分位数（线性插值），q ∈ [0,1]"""
    n = len(sorted_vals)
    if not n:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def get_route_percentiles(plugin_name=None, days=7, sample_max=5000):
    """按路由的渲染耗时分位（p50/p95），也可当「最慢路由榜」用（按 p95 降序）。

    SQLite 没有 percentile 函数，窗口函数同样要全量排序，所以直接取窗口内最近的
    sample_max 条 duration_ms 回 Python 算；配 _stats_cache 的 5 秒短缓存，
    面板轮询不会反复扫表。

    命中成品图缓存的请求只有 ~1ms，混进来会把分位整体拉低，因此用 cache_hit 排除。
    """
    cache_key = ('route_pct', plugin_name, days, sample_max)
    cached = _stats_cache.get(cache_key)
    if cached is not None:
        return cached

    where = ("timestamp >= datetime('now', ?) AND COALESCE(cache_hit, 0) = 0 "
             'AND duration_ms IS NOT NULL')
    params = [f'-{days} days']
    if plugin_name:
        where = 'plugin_name = ? AND ' + where
        params.insert(0, plugin_name)
    rows = _exec(
        f'SELECT path, plugin_name, duration_ms FROM request_logs WHERE {where} '
        'ORDER BY id DESC LIMIT ?',
        params + [sample_max], fetch_all=True,
    )

    buckets = {}
    for r in rows:
        buckets.setdefault((r['plugin_name'] or '', r['path'] or ''), []).append(float(r['duration_ms'] or 0))

    result = []
    for (pname, path), vals in buckets.items():
        n = len(vals)
        if n < _MIN_PERCENTILE_SAMPLE:
            continue
        vals.sort()
        result.append({
            'plugin_name': pname, 'path': path, 'samples': n,
            'p50_ms': round(_percentile(vals, 0.5), 1),
            'p95_ms': round(_percentile(vals, 0.95), 1),
            'avg_ms': round(sum(vals) / n, 1),
            'max_ms': round(vals[-1], 1),
        })
    result.sort(key=lambda x: x['p95_ms'], reverse=True)
    _stats_cache[cache_key] = result
    return result


def prune_request_logs(days):
    """删除超过保留期的日志。分批执行，避免单条大 DELETE 长时间占住全局锁"""
    _delete_batched(
        "DELETE FROM request_logs WHERE id IN ("
        "SELECT id FROM request_logs WHERE timestamp < datetime('now', ?) LIMIT ?)",
        (f'-{days} days',),
    )


def trim_request_logs(max_rows):
    """超出上限时淘汰最旧的记录。用 OFFSET 直接定位阈值 id，不跑全表 COUNT(*)"""
    if max_rows <= 0:
        return
    row = _exec(
        'SELECT id FROM request_logs ORDER BY id DESC LIMIT 1 OFFSET ?',
        (max_rows,), fetch_one=True,
    )
    if not row:
        return
    _delete_batched(
        'DELETE FROM request_logs WHERE id IN ('
        'SELECT id FROM request_logs WHERE id <= ? LIMIT ?)',
        (row['id'],),
    )