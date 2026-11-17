"""本地模式（dev/prod）的持久化生命周期：启动初始化、统计刷盘、退出收尾。

原先这些逻辑直接铺在 app_core.create_app 里，和 FastAPI 应用组装混在一起；
run_core 的 console `exit` 命令又各自复制了一份收尾逻辑。统一收敛到这里。
"""
import threading
import time

from modules.utils.timezone import utc_now_iso

# 会话心跳的最小间隔（秒）。心跳只用来在进程被强杀时兜一个收尾时间点，
# 与刷盘周期（STATS_FLUSH_INTERVAL，默认 30 秒）解耦，避免空闲站点上无谓的写库。
_SESSION_HEARTBEAT_SECONDS = 300


def setup_persistence(app):
    """建库、加载权限缓存、登记本次启动会话、恢复插件请求计数"""
    from modules.database.core import init_db
    from modules.database.access import preload_access_cache
    from modules.database.stats import (
        get_server_info, set_server_info,
        create_session, close_stale_sessions, load_plugin_request_counts,
        load_account_usage,
    )

    init_db()
    preload_access_cache()

    now_iso = utc_now_iso()
    if get_server_info('first_startup') is None:
        set_server_info('first_startup', now_iso)
    set_server_info('last_startup', now_iso)

    # 上次进程被强杀会留下 end_time 为空的会话，先按心跳闭合掉
    close_stale_sessions()

    version = getattr(app, 'version', '')
    app.state._session_id = create_session(now_iso, app.state.mode, version)
    app.state.request_counts = load_plugin_request_counts()
    # 落库前先记住「上次成功落库的基线」：flush 只写 当前 − 基线 的增量，成功后推进基线。
    # 刚启动时基线就是库里已有的值（这部分已经在库里了，不能再写一遍）。
    app.state.counts_flushed = dict(app.state.request_counts)
    # 账号用量按天累计：把当天已落库的部分载回内存做基线，避免重启后从头计数
    from modules.utils.timezone import now_in_timezone
    app.state.account_usage = load_account_usage(now_in_timezone().date().isoformat())
    app.state.account_usage_flushed = {
        key: list(value) for key, value in app.state.account_usage.items()
    }
    # 停机期间到期的激活码账号也要归位，所以启动先扫一次（缓存此时还没建，不用失效）
    sweep_expirations(app)


def reload_after_restore(app):
    """数据库文件被整体替换后重建全部内存态（恢复备份后调用）。

    恢复备份 = 换了一个库：连接绑定到具体文件、权限缓存 / 插件与路由开关 / 配置覆盖 /
    统计基线 / 组限额 / 鉴权缓存 / 限流与防撞库计数 / 内存成品缓存全是按**旧库**算出来的。
    不逐项重来的后果是「面板显示旧库的设置、写入落到新库」——静默错配，比直接报错难查。

    调用前必须已完成文件替换与建库（换文件在 backup_routes 里持 core._db_lock 完成）。
    """
    from modules.database.core import init_db, reset_initialized
    from modules.database.access import preload_access_cache
    from modules.database.stats import (
        create_session, load_plugin_request_counts, load_account_usage,
    )
    from modules.utils.timezone import now_in_timezone

    # 换进来的是别人的库，迁移标记要清掉，让 init_db 按新库的结构补齐缺列/缺表
    reset_initialized()
    init_db()
    preload_access_cache()

    # 插件/路由开关与配置覆盖：先回到「全部启用、无禁用路由」的初始态再套库里存的，
    # 否则旧库禁用过、而新库里没有这条记录的插件会一直保持禁用
    app.state.plugin_states = {name: True for name in getattr(app.state, 'plugin_states', {})}
    app.state.disabled_routes = set()
    try:
        from modules.app_core import _load_persisted_states
        _load_persisted_states(app)
    except Exception:
        from modules.utils import plog
        plog.exception('恢复数据库后重载内存态失败')
    from modules import config_store
    config_store.enforce_mode_constraints()

    # 统计基线按新库重新取，否则增量刷盘会把旧库的累计值当成"已落库"而漏记
    app.state.request_counts = load_plugin_request_counts()
    app.state.counts_flushed = dict(app.state.request_counts)
    app.state.account_usage = load_account_usage(now_in_timezone().date().isoformat())
    app.state.account_usage_flushed = {
        key: list(value) for key, value in app.state.account_usage.items()
    }
    # 本次进程的会话记录原来挂在旧库里，重新登记一条，否则心跳与启动历史都对不上
    app.state._session_id = create_session(
        utc_now_iso(), app.state.mode, getattr(app, 'version', ''))

    # --- 内存态清空 ---
    from modules.auth.auth import invalidate_auth_cache
    invalidate_auth_cache()
    from modules.utils.rate_limiter import invalidate_group_limits
    invalidate_group_limits()
    semaphores = getattr(app.state, 'render_semaphores', None)
    if semaphores is not None:
        semaphores.clear()
    from modules.prerender import memcache
    memcache.clear()
    # 限流窗口与登录防撞库计数：重建共享后端即丢掉本实例内存里的计数（Redis 侧不受影响）
    from modules.shared.backend import set_backend
    set_backend(None)

    # 恢复出来的库可能带着已到期的会员，按启动时同一套逻辑归位一次
    sweep_expirations(app)


def sweep_expirations(app):
    """到期清理：激活码账号转入各自的回落组 + 销毁已过有效日期的激活码。

    没有定时任务：这里由启动和后台刷盘线程按周期驱动，到期的账号才会真的换组。
    换组后必须清鉴权缓存并丢弃相关用户组的并发信号量，否则旧组信息会继续沿用。
    """
    from modules.database.activations import expire_accounts, purge_dead_codes
    # 用完 / 过期即销毁：废码不留在面板列表里越堆越多
    purge_dead_codes()
    moved = expire_accounts()
    if not moved:
        return
    from modules.auth.auth import invalidate_auth_cache
    from modules.admin.common import _drop_group_semaphores
    groups = set()
    for _account_id, from_group, to_group in moved:
        groups.add(from_group)
        groups.add(to_group)
    _drop_group_semaphores(app.state, *groups)
    invalidate_auth_cache()


def persist_counters(app):
    """把内存中**新增**的插件请求计数增量刷入数据库。

    整值覆盖在多实例部署下会互相抹掉计数（后写的实例把别的实例的计数覆盖掉），
    因此只写 当前 − 已落库基线 的增量；落库失败不推进基线，下一轮自然重试。
    """
    from modules.database.stats import flush_plugin_request_counts
    counts = dict(getattr(app.state, 'request_counts', {}) or {})
    if not counts:
        return
    flushed = getattr(app.state, 'counts_flushed', None)
    if flushed is None:
        flushed = app.state.counts_flushed = {}
    deltas = {}
    for name, total in counts.items():
        delta = total - flushed.get(name, 0)
        if delta > 0:
            deltas[name] = delta
    if not deltas:
        return
    flush_plugin_request_counts(deltas)
    for name, delta in deltas.items():
        flushed[name] = flushed.get(name, 0) + delta


def persist_account_usage(app):
    """把内存里按天累计的账号用量增量刷入 account_stats。

    与 persist_counters 同一套基线机制；已落库的历史日期条目落库后即可丢弃，
    只留当天的继续在内存里累计。
    """
    usage = getattr(app.state, 'account_usage', None)
    if not usage:
        return
    from modules.database.stats import flush_account_usage
    from modules.utils.timezone import now_in_timezone

    flushed = getattr(app.state, 'account_usage_flushed', None)
    if flushed is None:
        flushed = app.state.account_usage_flushed = {}
    rows = []
    applied = []
    for key, value in dict(usage).items():
        base = flushed.get(key) or [0, 0, 0]
        delta = [max(0, value[0] - base[0]), max(0, value[1] - base[1]), max(0, value[2] - base[2])]
        if not any(delta):
            continue
        rows.append((key[0], key[1], key[2], delta[0], delta[1], delta[2]))
        applied.append((key, list(value)))
    if rows:
        flush_account_usage(rows)
        # 只在落库成功后推进基线，否则失败的那批会被当成已写而永久丢失
        for key, value in applied:
            flushed[key] = value
    today = now_in_timezone().date().isoformat()
    for key, _v in list(usage.items()):
        if key[0] != today:
            usage.pop(key, None)
            flushed.pop(key, None)


def flush_and_close(app):
    """退出收尾：落盘待写日志、刷统计、关闭本次会话"""
    try:
        from modules.database.logs import flush_log_queue
        flush_log_queue()
        persist_counters(app)
        persist_account_usage(app)
        session_id = getattr(app.state, '_session_id', None)
        if session_id:
            from modules.database.stats import close_session
            close_session(session_id, utc_now_iso())
    except Exception:
        pass


def start_prerender_scheduler(app):
    """启动定时预渲染调度循环（只能在 asyncio 事件循环内调用，故挂在 startup 事件上）"""
    import asyncio
    from modules.prerender.scheduler import scheduler_loop

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    # 先按「单实例」置为开：多实例下由共享线程在首个 tick 按租约结果改写成本实例是否为
    # leader（调度循环有启动宽限，改写一定发生在第一次取到期任务之前）。这里保留 True
    # 是为了在共享线程意外缺席时退回改造前的行为，而不是静默地不做任何预渲染。
    app.state.prerender_enabled = True
    task = loop.create_task(scheduler_loop(app))
    app.state._prerender_task = task
    return task


def stop_prerender_scheduler(app):
    task = getattr(app.state, '_prerender_task', None)
    if task is not None:
        task.cancel()


def start_shared_loop(app):
    """启动共享存储后台线程：单例租约维护 + 跨实例失效事件轮询。

    只能在 asyncio 事件循环内调用（需要循环句柄把异步的后端命令丢回主循环执行），
    因此与预渲染调度一样挂在 lifespan 上。未配置 REDIS_URL 时它同样要跑：
    MemoryBackend 下租约必然拿到、版本号也没有别的实例在改，每轮只付两次内存操作。

    线程内不做任何网络等待：所有后端调用经 `run_coroutine_threadsafe` 回到事件循环，
    超时兜底 5 秒（单条 Redis 命令自身还有 SHARED_TIMEOUT_MS 的超时）。
    """
    import asyncio
    import config
    from modules.shared import events
    from modules.shared.leader import LeaderLock

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    events.register_app(app)
    events.bind_loop(loop)
    lock = LeaderLock()
    app.state._leader_lock = lock
    app.state.is_leader = False

    def _run(coro):
        try:
            return asyncio.run_coroutine_threadsafe(coro, loop).result(5.0)
        except Exception:
            return None

    def tick_seconds():
        """维护周期：续租必须在租约到期前完成（不超过 ttl/3），同时不超过轮询周期"""
        try:
            ttl = max(1, int(config.SHARED_LEADER_TTL_SECONDS or 30))
        except (TypeError, ValueError):
            ttl = 30
        try:
            poll = max(1, int(config.SHARED_POLL_SECONDS or 5))
        except (TypeError, ValueError):
            poll = 5
        return max(1, min(poll, max(1, ttl // 3)))

    def _worker():
        while not app.state._shutdown:
            held = bool(_run(lock.maintain()))
            app.state.is_leader = held
            # 只有 leader 负责预渲染调度：多实例下每个实例各排一份会把渲染算力放大 N 倍
            app.state.prerender_enabled = held
            _run(events.poll_once())
            time.sleep(tick_seconds())

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    app.state._shared_thread = thread
    return thread


async def stop_shared_loop(app):
    """停机收尾：主动释放租约，下一个实例立刻接管，不必干等租约过期"""
    lock = getattr(app.state, '_leader_lock', None)
    if lock is not None:
        await lock.release()


def is_leader(app):
    """本实例是否持有共享租约（= 是否负责调度与清理类任务）。

    共享线程还没起来（未调用 start_shared_loop，如单元测试直接调刷盘函数）时按单实例
    处理恒为 True：否则清理与到期扫描会被静默地永远跳过。
    """
    if getattr(app.state, '_leader_lock', None) is None:
        return True
    return bool(getattr(app.state, 'is_leader', False))


def start_flush_thread(app):
    """后台线程：周期刷统计与日志队列，并按周期清理过期日志"""
    import config

    def _loop():
        from modules.database.stats import touch_session
        from modules.database.logs import (
            flush_log_queue, prune_request_logs, trim_request_logs,
        )
        iteration = 0
        last_beat = 0.0
        while not app.state._shutdown:
            # 这些配置必须在循环内现取：面板改完要立刻生效，
            # 若在线程启动时闭包捕获，就非得重启进程才生效（且 importlib.reload 也救不回来）
            try:
                interval = max(1, int(config.STATS_FLUSH_INTERVAL or 60))
            except (TypeError, ValueError):
                interval = 60
            time.sleep(interval)
            if app.state._shutdown:
                break
            try:
                # 增量刷盘必须走 persist_counters：flush_plugin_request_counts 收的是
                # 「增量」，直接塞 request_counts（累计值）会被反复累加，计数随时间虚高
                persist_counters(app)
                persist_account_usage(app)
                flush_log_queue()
                # 心跳：进程若被强杀，下次启动就按这个时间收尾，不会把停机时长算进去。
                # 按更低的频率单独计时——空闲站点上它是唯一"每轮必写"的语句，
                # 跟着 30 秒的刷盘周期走等于每天近三千次写库，在 SD 卡部署上是白付的磨损。
                # 它只用于兜一个停机时间点，分钟级粒度足够。
                if time.time() - last_beat >= _SESSION_HEARTBEAT_SECONDS:
                    session_id = getattr(app.state, '_session_id', None)
                    if session_id:
                        touch_session(session_id, utc_now_iso())
                    last_beat = time.time()
                # 预渲染命中计数在内存累计，同样交给这个线程落库（命中是热路径，不宜写库）
                from modules.prerender import store as prerender_store
                prerender_store.flush_hits()
                # 以上都是"各实例各有一份数据"，必须每个实例都做；下面这些是集群级任务，
                # 只让 leader 做——否则 N 个实例同时扫描/裁剪会把库写入放大 N 倍
                if is_leader(app):
                    # 激活码账号到期回落 + 过期码销毁：每轮都扫，查询只走一次过滤，开销可忽略
                    sweep_expirations(app)
            except Exception:
                pass
            iteration += 1
            try:
                cleanup_cycles = max(1, int(config.LOG_CLEANUP_CYCLES or 1))
            except (TypeError, ValueError):
                cleanup_cycles = 1
            if iteration % cleanup_cycles == 0 and is_leader(app):
                try:
                    prune_request_logs(config.REQUEST_LOG_RETENTION_DAYS)
                    trim_request_logs(config.REQUEST_LOG_MAX_ROWS)
                except Exception:
                    pass
                try:
                    from modules.database.audit import trim_audit_logs
                    trim_audit_logs(config.AUDIT_LOG_MAX_ROWS)
                except Exception:
                    pass
                try:
                    from modules.prerender import store as prerender_store
                    prerender_store.trim_cache(
                        config.PRERENDER_CACHE_MAX_ROWS, config.PRERENDER_CACHE_MAX_MB)
                    # 寿命回收：超过任务 cache_ttl_hours 且期间没被请求过的产物释放掉
                    prerender_store.purge_expired()
                except Exception:
                    pass
                try:
                    # 备份快照按保留策略回收：这个目录只进不出（每次恢复前写一份），
                    # 没有这轮兜底就会被它慢慢吃满磁盘。策略见 config.BACKUP_KEEP_COUNT
                    from modules.database.core import db_path, is_db_available
                    from modules.admin.backup_routes import cleanup_backups
                    if is_db_available():
                        backup_db = db_path()
                        if backup_db:
                            cleanup_backups(backup_db)
                except Exception:
                    pass

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    app.state._flush_thread = thread
    return thread