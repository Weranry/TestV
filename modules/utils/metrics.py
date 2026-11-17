"""进程内指标：Prometheus 文本出口 `/metrics`。

手写 Prometheus 文本格式，不引入 prometheus_client（依赖清单只有 requirements.txt / requirements-local.txt 两个文件，不为一个指标出口新增依赖）。

数据源全部是**已在内存里**的计数与快照，不额外查库；只有「库文件大小」与「预渲染成品
缓存条数」两处需要读库，都是 O(1) / O(小表)，被监控轮询的代价可忽略。每段各自兜底：
某个子系统（如数据库停用、resource 在 Windows 上不存在）不可用时只少几行指标，不整个 500。

进程内单例：项目强制单进程单 worker，多 worker 会让指标各记一份（与限流同因）。
"""
import platform
import sys
import threading
import time

# 本模块在进程启动期（app_core 导入 template_routes 时）即被加载，用导入时刻近似进程起点。
# 公开出去：面板概览的「运行时长」与这里的 uptime 指标必须同一个起点，否则两处各记一份会各报一个数
PROCESS_START_TIME = time.time()

_lock = threading.Lock()
_counters = {}


def incr(name, value=1):
    """累加一个具名计数器（线程安全）。

    只存进程内、重启归零：这些计数的作用是「让抖动可见」（如鉴权缓存命中率骤降、
    限流频繁拒绝），落库反而给热路径每次多一次写。
    """
    with _lock:
        _counters[name] = _counters.get(name, 0) + value


def counter(name):
    with _lock:
        return _counters.get(name, 0)


def reset():
    """清空全部进程内计数器（测试用）"""
    with _lock:
        _counters.clear()


def _esc(value):
    """Prometheus 标签值转义：反斜杠、双引号、换行都要转，否则一个含引号的插件名会破坏整段文本"""
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _num(value):
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float):
        return repr(round(value, 3))
    return str(value)


def _labels(labels):
    if not labels:
        return ''
    parts = ','.join(f'{k}="{_esc(v)}"' for k, v in labels.items())
    return '{' + parts + '}'


def _emit(lines, name, help_text, mtype, value, labels=None):
    """按 Prometheus 文本格式输出一条指标；value 为 None 表示该项当前不可用，直接跳过"""
    if value is None:
        return
    lines.append(f'# HELP {name} {help_text}')
    lines.append(f'# TYPE {name} {mtype}')
    lines.append(f'{name}{_labels(labels)} {_num(value)}')


def _collect_process(app, lines):
    mode = getattr(app.state, 'mode', 'unknown')
    _emit(lines, 'einkviews_info', 'eInkViews 构建与运行模式信息', 'gauge', 1,
          {'mode': mode, 'version': getattr(app, 'version', ''),
           'python': platform.python_version()})
    _emit(lines, 'einkviews_uptime_seconds', '进程运行时长（秒）', 'gauge',
          time.time() - PROCESS_START_TIME, {'mode': mode})

    try:
        # resource 是 Unix-only 模块，Windows 上导入即失败（部署目标是 Linux，仅本地开发受影响）
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux 的单位是 KB，macOS 是字节
        rss_bytes = rss if sys.platform == 'darwin' else rss * 1024
        _emit(lines, 'einkviews_process_rss_bytes', '进程常驻内存（字节，峰值）', 'gauge', rss_bytes)
    except Exception:
        pass

    try:
        from modules.database.core import db_file_size, is_db_available
        if is_db_available():
            _emit(lines, 'einkviews_db_size_bytes', 'SQLite 库文件大小（字节）', 'gauge', db_file_size())
    except Exception:
        pass


def _collect_render(app, lines):
    try:
        from modules.generate_views import render_metrics
        rm = render_metrics.snapshot()
    except Exception:
        return
    _emit(lines, 'einkviews_render_active', '当前正在渲染的请求数', 'gauge', rm['active'])
    _emit(lines, 'einkviews_render_total', '本次进程累计渲染次数', 'counter', rm['total'])
    _emit(lines, 'einkviews_render_cache_hits_total', '本次进程成品图缓存命中次数', 'counter', rm['hits'])
    _emit(lines, 'einkviews_render_last_ms', '最近一次渲染耗时（毫秒）', 'gauge', rm['last_ms'])
    _emit(lines, 'einkviews_render_avg_ms', '本次进程渲染平均耗时（毫秒）', 'gauge', rm['avg_ms'])
    _emit(lines, 'einkviews_render_slowest_ms', '本次进程最慢一次渲染耗时（毫秒）', 'gauge', rm['slowest_ms'])

    # 信号量条目数：按账号缓存、只增不减曾是不可观测的内存增长，这里让它一眼可见
    sems = getattr(app.state, 'render_semaphores', None)
    if sems is not None:
        _emit(lines, 'einkviews_render_semaphores', '缓存的渲染并发信号量条目数', 'gauge', len(sems))


def _collect_plugins(app, lines):
    counts = getattr(app.state, 'request_counts', None) or {}
    states = getattr(app.state, 'plugin_states', None) or {}
    _emit(lines, 'einkviews_plugins_loaded', '已加载的插件数', 'gauge', len(states))
    if not counts:
        return
    lines.append('# HELP einkviews_plugin_requests_total 插件累计请求数')
    lines.append('# TYPE einkviews_plugin_requests_total counter')
    for name in sorted(counts):
        lines.append(f'einkviews_plugin_requests_total{{plugin="{_esc(name)}"}} {_num(counts[name])}')


def _collect_rate_limit(lines):
    _emit(lines, 'einkviews_rate_limit_rejected_total', '因限流被拒绝的请求数', 'counter',
          counter('rate_limit_rejected'))
    try:
        from modules.utils.rate_limiter import store_size
        _emit(lines, 'einkviews_rate_limiter_keys', '限流器当前追踪的额度 key 数', 'gauge', store_size())
    except Exception:
        pass


def _collect_shared(lines, app):
    """共享后端状态：backend=memory 单实例 / redis 多实例，degraded=1 表示已回落本地计数"""
    try:
        from modules.shared.backend import get_backend
        st = get_backend().status()
    except Exception:
        return
    _emit(lines, 'einkviews_shared_backend', '共享后端类型（memory=单实例 / redis=多实例）', 'gauge', 1,
          {'backend': st['backend'], 'degraded': '1' if st['degraded'] else '0'})
    _emit(lines, 'einkviews_shared_backend_keys', '本实例内存中追踪的共享状态条目数', 'gauge', st['keys'])
    # 多实例下只有一个实例为 1：它负责预渲染调度与到期扫描/日志裁剪。全是 0 说明租约没抢到
    # （Redis 抖动或 ttl 配置过小），全是 1 说明共享存储实际没生效——两种情况都该有告警
    _emit(lines, 'einkviews_shared_leader', '本实例是否持有共享租约（1=负责调度与集群级清理）',
          'gauge', 1 if getattr(app.state, 'is_leader', False) else 0)


def _collect_logs(lines):
    try:
        from modules.database.logs import log_queue_size, dropped_log_count
        size, maxsize = log_queue_size()
        _emit(lines, 'einkviews_log_queue_size', '待写入的请求日志条数', 'gauge', size)
        _emit(lines, 'einkviews_log_queue_maxsize', '请求日志队列上限', 'gauge', maxsize)
        _emit(lines, 'einkviews_log_dropped_total', '因队列写满而丢弃的日志条数', 'counter',
              dropped_log_count())
    except Exception:
        pass


def _collect_cache(lines):
    try:
        from modules.cache.cache import stats as cache_stats
        cs = cache_stats(with_items=False)
    except Exception:
        return
    _emit(lines, 'einkviews_font_cache_entries', '字体缓存当前条目数', 'gauge', cs['size'])
    _emit(lines, 'einkviews_font_cache_maxsize', '字体缓存条目上限', 'gauge', cs['maxsize'])
    _emit(lines, 'einkviews_font_cache_hits_total', '字体缓存命中次数', 'counter', cs['hits'])
    _emit(lines, 'einkviews_font_cache_misses_total', '字体缓存未命中次数', 'counter', cs['misses'])


def _collect_auth(lines):
    try:
        from modules.auth.auth import auth_cache_stats
        st = auth_cache_stats()
    except Exception:
        return
    # 命中率骤降就说明容量小于在线设备数：每个请求都在回落到查库（过全局数据库锁）
    _emit(lines, 'einkviews_auth_cache_entries', '鉴权缓存当前条目数', 'gauge', st['entries'])
    _emit(lines, 'einkviews_auth_cache_maxsize', '鉴权缓存条目上限', 'gauge', st['maxsize'])
    _emit(lines, 'einkviews_auth_cache_hits_total', '鉴权缓存命中次数', 'counter', st['hits'])
    _emit(lines, 'einkviews_auth_cache_misses_total', '鉴权缓存未命中次数', 'counter', st['misses'])


def _collect_prerender(lines):
    try:
        from modules.prerender.store import cache_summary
        cs = cache_summary()
        _emit(lines, 'einkviews_prerender_cache_rows', '预渲染成品缓存条目数', 'gauge', cs['rows'])
        _emit(lines, 'einkviews_prerender_cache_bytes', '预渲染成品缓存占用字节数', 'gauge', cs['bytes'])
    except Exception:
        pass
    try:
        from modules.prerender import memcache
        ms = memcache.stats()
        _emit(lines, 'einkviews_prerender_mem_entries', '内存成品缓存条目数', 'gauge', ms['entries'])
        _emit(lines, 'einkviews_prerender_mem_bytes', '内存成品缓存占用字节数', 'gauge', ms['bytes'])
        _emit(lines, 'einkviews_prerender_mem_max_bytes', '内存成品缓存预算字节数（0=关闭）', 'gauge',
              ms['max_bytes'])
    except Exception:
        pass


def render(app):
    """渲染整份 Prometheus 文本（每段独立兜底，任一段失败只是少几行）"""
    lines = []
    _collect_process(app, lines)
    _collect_render(app, lines)
    _collect_plugins(app, lines)
    _collect_rate_limit(lines)
    _collect_shared(lines, app)
    _collect_logs(lines)
    _collect_cache(lines)
    _collect_auth(lines)
    _collect_prerender(lines)
    return '\n'.join(lines) + '\n'