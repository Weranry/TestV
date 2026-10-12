import asyncio
import os
import time
import platform

from cachetools import TTLCache
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _app_state, _body, _fmt_bytes
from modules.errors.errors import error_response
from modules.i18n.registry import lang_of, t_req
from modules.utils.metrics import PROCESS_START_TIME
from modules.utils.timezone import fmt_duration

router = APIRouter()

# 概览页自检的短缓存：面板每 10 秒轮询一次，但这几项各自都是真开销
# （shutil.disk_usage、os.path.getsize、多项自检、若干聚合查询），窗口内复用上次结果。
# 运行时长 / 请求计数 / 今日指标变化快且几乎零成本，放在缓存外重算。
_status_cache = TTLCache(maxsize=1, ttl=3)

# 后台延迟任务的强引用：`asyncio.create_task` 的返回值不持有的话，任务可能在执行前
# 被 GC 掉（重启这类「响应下发后再做」的动作就静默不执行了）。
_bg_tasks = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _status_expensive(s, project_root):
    """概览页里昂贵的部分：查库 + 磁盘 + 各项健康自检（3 秒结果缓存）

    每项都单独兜底：概览轮询不能因为某个子系统（如数据库停用）整个 500。
    """
    cached = _status_cache.get('snap')
    if cached is not None:
        return dict(cached)

    try:
        from modules.database.core import is_db_available
        db_available = is_db_available()
    except Exception:
        db_available = False

    user_count = evkey_count = db_size = 0
    session_count = total_uptime = 0
    first_startup = last_startup = None
    if db_available:
        try:
            from modules.database.accounts import get_account_count, get_evkey_count
            from modules.database.core import db_file_size
            from modules.database.stats import get_server_info, get_session_count, get_total_uptime_seconds
            user_count = get_account_count()
            evkey_count = get_evkey_count()
            db_size = db_file_size()
            first_startup = get_server_info('first_startup')
            last_startup = get_server_info('last_startup')
            session_count = get_session_count()
            total_uptime = get_total_uptime_seconds()
        except Exception:
            pass

    try:
        from config import REQUEST_LOG_RETENTION_DAYS
        retention_days = REQUEST_LOG_RETENTION_DAYS
    except Exception:
        retention_days = None

    try:
        from modules.cache.cache import stats as cache_stats_fn, is_enabled as cache_enabled
        cs = cache_stats_fn(with_items=False)
        cache_info = {
            'enabled': cache_enabled(), 'size': cs['size'], 'maxsize': cs['maxsize'],
            'hits': cs['hits'], 'misses': cs['misses'], 'hit_rate': cs['hit_rate'],
        }
    except Exception:
        cache_info = {'enabled': False, 'size': 0, 'maxsize': 0, 'hits': 0, 'misses': 0, 'hit_rate': 0.0}

    try:
        import shutil
        du = shutil.disk_usage(project_root)
        disk = {'total': du.total, 'used': du.used, 'free': du.free}
    except Exception:
        disk = {'total': 0, 'used': 0, 'free': 0}

    flush_thread = getattr(s, '_flush_thread', None)
    flush_alive = bool(flush_thread is not None and flush_thread.is_alive())

    log_queue = {'size': 0, 'maxsize': 0, 'dropped': 0}
    try:
        from modules.database.logs import log_queue_size, dropped_log_count
        qs, qm = log_queue_size()
        log_queue = {'size': qs, 'maxsize': qm, 'dropped': dropped_log_count()}
    except Exception:
        pass

    rl_entries = 0
    try:
        from modules.utils.rate_limiter import store_size
        rl_entries = store_size()
    except Exception:
        pass

    checks = []
    def _check(name, status, detail):
        checks.append({'name': name, 'status': status, 'detail': detail})

    if db_available:
        _check('overview.check_db', 'ok', f'正常 · {_fmt_bytes(db_size)}')
    else:
        _check('overview.check_db', 'off', '当前模式已停用（无持久化存储）')

    if db_available:
        # 结构迁移收敛到 schema_migrations 之后，这里把版本摆出来：库是不是最新结构
        # 一眼可见，不必再去翻启动日志
        try:
            from modules.database.migrations import schema_status
            st = schema_status()
            if st['up_to_date']:
                _check('overview.check_schema', 'ok',
                       f"v{st['version']}（最新 v{st['latest']}，已登记 {st['applied']} 条迁移）")
            else:
                _check('overview.check_schema', 'warn',
                       f"v{st['version']} 落后于最新 v{st['latest']}，重启服务以完成迁移")
        except Exception:
            pass

    if cache_info['enabled']:
        _check('overview.check_cache', 'ok', f"启用 · {cache_info['size']}/{cache_info['maxsize']} 条目 · 命中率 {cache_info['hit_rate']}%")
    else:
        _check('overview.check_cache', 'warn', '已停用，每次请求实时加载字体')

    if flush_alive:
        _check('overview.check_flush', 'ok', '运行中')
    elif db_available:
        _check('overview.check_flush', 'error', '未运行，统计数据可能不落库')
    else:
        _check('overview.check_flush', 'off', '当前模式不启用')

    if log_queue['maxsize']:
        ratio = log_queue['size'] / log_queue['maxsize']
        st = 'error' if ratio >= 0.95 else ('warn' if ratio >= 0.8 else 'ok')
        detail = f"{log_queue['size']}/{log_queue['maxsize']} 条待写入"
        # 队列写满后日志会被丢弃，丢掉多少必须显式可见，否则"刷爆当天"是静默的
        if log_queue['dropped']:
            detail += f" · 已丢弃 {log_queue['dropped']} 条"
        _check('overview.check_log_queue', st, detail)
    else:
        _check('overview.check_log_queue', 'off', '未启用')

    if disk['total']:
        free_ratio = disk['free'] / disk['total'] * 100
        st = 'error' if disk['free'] < 200 * 1024 * 1024 else ('warn' if free_ratio < 10 else 'ok')
        _check('overview.check_disk', st, f"剩余 {_fmt_bytes(disk['free'])} / 共 {_fmt_bytes(disk['total'])}（{free_ratio:.0f}%）")
    else:
        _check('overview.check_disk', 'off', '无法读取')

    _check('overview.check_ratelimit', 'ok', f'追踪 {rl_entries} 个额度 key')

    # 渲染维度：前 6 项都是基础设施，渲染本身的状态（是否打满、单次多慢）原来无处可见
    try:
        from modules.generate_views import render_metrics
        rm = render_metrics.snapshot()
    except Exception:
        rm = {'active': 0, 'total': 0, 'hits': 0, 'last_ms': None, 'avg_ms': None, 'slowest_ms': None}

    try:
        from config import MAX_CONCURRENT_RENDERS, RENDER_SLOW_MS
        max_renders = int(MAX_CONCURRENT_RENDERS or 0)
        slow_ms = float(RENDER_SLOW_MS or 0)
    except (TypeError, ValueError):
        max_renders, slow_ms = 0, 0

    limit_txt = f'/{max_renders}' if max_renders > 0 else '（不限）'
    busy = max_renders > 0 and rm['active'] >= max_renders
    _check('overview.check_render', 'warn' if busy else 'ok',
           f"进行中 {rm['active']}{limit_txt} · 累计 {rm['total']} 次 · 缓存命中 {rm['hits']} 次")

    if rm['last_ms'] is None:
        _check('overview.check_last_render', 'off', '本次启动还没有渲染记录')
    else:
        st = 'warn' if (slow_ms > 0 and rm['last_ms'] >= slow_ms) else 'ok'
        _check('overview.check_last_render', st,
               f"{rm['last_ms']}ms · 平均 {rm['avg_ms']}ms · 最慢 {rm['slowest_ms']}ms")

    severity = {'error': 2, 'warn': 1, 'ok': 0, 'off': 0}
    worst = max([severity.get(c['status'], 0) for c in checks], default=0)
    health = 'error' if worst >= 2 else ('warn' if worst == 1 else 'ok')

    snap = {
        'db_available': db_available,
        'user_count': user_count, 'evkey_count': evkey_count, 'db_size': db_size,
        'cache': cache_info,
        'runtime': {
            'first_startup': first_startup, 'last_startup': last_startup,
            'session_count': session_count, 'total_uptime_seconds': total_uptime,
            'retention_days': retention_days,
        },
        'disk': disk,
        'flush_alive': flush_alive,
        'log_queue': log_queue,
        'rl_entries': rl_entries,
        'health': {'status': health, 'checks': checks},
    }
    _status_cache['snap'] = snap
    return dict(snap)

@router.get('/api/status')
async def admin_status(request: Request):
    """概览页数据源：运行状态 + 今日指标 + 各项健康检查"""
    s = _app_state(request)
    up = time.time() - PROCESS_START_TIME
    # 这段是真开销（磁盘 + 多项自检 + 聚合查询），面板每 10 秒轮询一次，必须下放线程：
    # 同步执行会把事件循环按在这个端点上
    snap = await asyncio.to_thread(_status_expensive, s, _project_root())
    # 检查项名字进快照的是键：快照按语言无关缓存，取词放到每次请求里做，避免先到者
    # 的语言被缓存 3 秒、另一语言的界面读到中文名
    snap_health = snap['health']
    health = {
        'status': snap_health['status'],
        'checks': [{'name': t_req(request, c['name']), 'status': c['status'], 'detail': c['detail']}
                   for c in snap_health['checks']],
    }

    today = {'total': 0, 'errors': 0, 'avg_ms': None}
    if snap['db_available']:
        try:
            from modules.database.logs import get_today_summary
            from modules.utils.timezone import get_timezone_offset
            try:
                tz_offset = get_timezone_offset()
            except Exception:
                tz_offset = None
            today = await asyncio.to_thread(get_today_summary, tz_offset)
        except Exception:
            pass

    return JSONResponse({
        'mode': getattr(s, 'mode', 'unknown'),
        'version': getattr(request.app, 'version', ''),
        'uptime_seconds': round(up, 1),
        'uptime_display': fmt_duration(up, lang_of(request)),
        'python': platform.python_version(),
        'user_count': snap['user_count'], 'evkey_count': snap['evkey_count'],
        'request_counts': getattr(s, 'request_counts', {}),
        'plugin_count': len(getattr(s, 'plugin_result', {}).get('plugins', [])),
        'today': today,
        'cache': snap['cache'],
        'db': {'available': snap['db_available'], 'size_bytes': snap['db_size']},
        'runtime': snap['runtime'],
        'disk': snap['disk'],
        'flush_thread': snap['flush_alive'],
        'log_queue': snap['log_queue'],
        'rate_limiter': {'entries': snap['rl_entries']},
        'health': health,
    })


# ---- 关于页：运行时信息 ----

@router.get('/api/runtime')
async def admin_runtime(request: Request):
    """「关于」页数据源：版本、平台、运行时长、存储与更新状态（一次性读取，无轮询）"""
    s = _app_state(request)
    up = time.time() - PROCESS_START_TIME
    lang = lang_of(request)
    info = {
        'version': getattr(request.app, 'version', ''),
        'mode': getattr(s, 'mode', 'unknown'),
        'python': platform.python_version(),
        'uptime_display': fmt_duration(up, lang),
        'uptime_seconds': round(up, 1),
        'plugin_count': len(getattr(s, 'plugin_result', {}).get('plugins', [])),
    }
    # 运行时长/进程的几项是进程内内存态，零成本；库大小 / schema 版本要查库，放线程
    def _db_bits():
        try:
            from modules.database.core import is_db_available, db_file_size
            from modules.database.migrations import schema_status
            if not is_db_available():
                return {'available': False, 'size_bytes': 0, 'schema': None}
            st = schema_status()
            return {'available': True, 'size_bytes': db_file_size(),
                    'schema': {'version': st.get('version'), 'latest': st.get('latest'),
                               'up_to_date': st.get('up_to_date', True)}}
        except Exception:
            return {'available': False, 'size_bytes': 0, 'schema': None}
    info['db'] = await asyncio.to_thread(_db_bits)

    # 更新：git 检查会走网络（fetch），只在打开关于页时做一次，不做轮询
    from modules.updater import project_root, check_update, update_settings
    root = project_root()
    settings = update_settings()
    info['update'] = {'settings': settings}
    try:
        info['update']['check'] = await asyncio.to_thread(
            check_update, root, remote=settings['remote'], branch=settings['branch'])
    except Exception as exc:
        info['update']['check'] = {'reason': 'error', 'detail': str(exc)}
    return JSONResponse(info)


# ---- 更新 / 重启 ----

async def _update_settings_from_body(request):
    """远端 / 分支：请求体里的优先，缺省回落面板配置（前端一般不带，直接走配置）"""
    from modules.updater import update_settings
    settings = update_settings()
    body = await _body(request) or {}
    return (str(body.get('remote') or settings['remote']),
            str(body.get('branch') or settings['branch']))


@router.get('/api/update/check')
async def admin_update_check(request: Request):
    """检查远端是否有更新（不改变工作区）。结果带 reason 码，前端按码取词"""
    from modules.updater import project_root, check_update
    remote, branch = await _update_settings_from_body(request)
    result = await asyncio.to_thread(
        check_update, project_root(), remote=remote, branch=branch)
    return JSONResponse(result)


@router.post('/api/update/download')
async def admin_update_download(request: Request):
    """只把远端对象拉回本地备用（fetch），工作区一行不改"""
    from modules.updater import project_root, apply_update
    remote, branch = await _update_settings_from_body(request)
    result = await asyncio.to_thread(
        apply_update, project_root(), remote=remote, branch=branch, download_only=True)
    return JSONResponse(result)


@router.post('/api/update/apply')
async def admin_update_apply(request: Request):
    """覆盖框架文件并安装依赖（如有变更）。**不自动重启**：由前端在拿到结果后决定"""
    from modules.updater import project_root, apply_update
    remote, branch = await _update_settings_from_body(request)
    result = await asyncio.to_thread(
        apply_update, project_root(), remote=remote, branch=branch, download_only=False)
    return JSONResponse(result)


@router.post('/api/system/restart')
async def admin_system_restart(request: Request):
    """延迟约 1 秒自重启。响应先行返回，重启动作放后台执行。

    不在请求处理里直接 execv：execv 会立刻替换进程镜像，正在写回响应的那段代码
    可能执行到一半就没了，客户端收不到成功提示。延迟一秒给响应留出写回的时间窗。
    """
    from modules.utils.restart import can_restart, restart_process
    if not can_restart():
        return error_response(t_req(request, 'about.restart_unsupported'), 400)

    app = request.app

    async def _later():
        await asyncio.sleep(1.0)
        restart_process(app)

    _spawn(_later())
    return JSONResponse({'success': True, 'message': t_req(request, 'about.restart_scheduled')})