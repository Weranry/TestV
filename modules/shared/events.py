"""跨实例内存态失效广播。

多实例下每个进程都有一份内存态：鉴权缓存、用户组权限缓存、组限额缓存、并发信号量。
管理端在实例 A 上改了权限，实例 B 不知道，会继续按旧规则放行——**静默**的越权或误拒，
所以必须让改动传播出去。

机制是「版本号 + 轮询」而不是 Pub/Sub 订阅：
- 本地失效的漏斗函数（`invalidate_auth_cache` / `invalidate_group_limits` /
  `preload_access_cache` / 权限规则写入）改完本实例内存态后调 `notify(kind)`；
- `notify` 立刻（在事件循环里）把该 kind 的共享版本号 +1，其它实例下一轮轮询发现
  版本号变了就重跑对应的本地失效；
- 轮询本身就是兜底机制，再挂一条 Pub/Sub 长连接要额外处理重连与任务生命周期，
  收益只是把上限从 SHARED_POLL_SECONDS 压到亚秒级——文档给出的保证本来就是
  「最长 SHARED_POLL_SECONDS 生效」，轮询独立地满足这个保证。

未配置 REDIS_URL 时版本号活在本进程的 MemoryBackend 里，只服务「两个假实例共用同一个
MemoryBackend」这种场景；单实例部署下 `notify` 等价于空操作（本地失效已经做完了）。
"""
import asyncio
import threading

AUTH = 'auth'
ACCESS = 'access'
GROUP = 'group'
KINDS = (AUTH, ACCESS, GROUP)

_pending = set()
_applied = {}
_primed = False
_was_degraded = False
_loop = None
_app = None
_lock = threading.Lock()
_local = threading.local()


def register_app(app):
    """注册当前应用（`group` 事件要清它的并发信号量；其余事件不用 app）"""
    global _app
    _app = app


def bind_loop(loop):
    """注册事件循环句柄：notify 要从同步上下文发一条异步命令，必须知道往哪发"""
    global _loop
    _loop = loop


def reset():
    """清空全部状态（测试用：避免用例之间互相污染）"""
    global _loop, _app, _primed, _was_degraded
    with _lock:
        _pending.clear()
        _applied.clear()
    _loop = None
    _app = None
    _primed = False
    _was_degraded = False
    _local.applying = False


def notify(kind):
    """声明某个 kind 的本地内存态变了，需要让其它实例也失效一次。

    - 重入抑制：`apply_local` 内部会再调一遍漏斗函数，若不放行就会
      「失效 → 广播 → 收到 → 失效 → …」无限回环；
    - 事件循环还没绑定（启动期）时只留待发集合，由轮询兜底发出。
    """
    if kind not in KINDS or getattr(_local, 'applying', False):
        return
    with _lock:
        _pending.add(kind)
    _schedule()


def _schedule():
    loop = _loop
    if loop is None or loop.is_closed():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(publish_pending(), loop)
        future.add_done_callback(_swallow)
    except Exception:
        # 循环正在关闭：待发集合留着，下一轮轮询（若还有）再来
        pass


def _swallow(future):
    """取一次异常，避免 asyncio 打「exception was never retrieved」"""
    try:
        future.exception()
    except Exception:
        pass


async def publish_pending():
    """把待发集合里的 kind 各 +1 次版本号（多个 kind 合并成一次往返）"""
    with _lock:
        if not _pending:
            return
        kinds = sorted(_pending)
        _pending.clear()
    from modules.shared.backend import get_backend
    try:
        versions = await get_backend().version_bump(kinds)
    except Exception:
        with _lock:
            _pending.update(kinds)
        return
    # 自己发出去的版本号记成「已应用」：本地失效在 notify 之前就做完了，
    # 不记的话下一轮轮询会把自己的事件再应用一遍
    with _lock:
        for kind, version in versions.items():
            _applied[kind] = version


async def poll_once():
    """轮询一次版本号并按需重放本地失效（由后台共享线程按 SHARED_POLL_SECONDS 驱动）"""
    global _primed, _was_degraded
    await publish_pending()
    from modules.shared.backend import get_backend
    backend = get_backend()
    try:
        versions = await backend.version_get(KINDS)
    except Exception:
        return
    degraded = bool(getattr(backend, 'degraded', False))
    with _lock:
        primed = _primed
        applied = dict(_applied)
    if not primed:
        # 启动首次轮询只对齐基线：本实例的内存态刚从库里建好，没有"待失效"的东西。
        # 不对齐的话会把库里累积的历史版本号当成新事件，白跑一遍全量失效。
        with _lock:
            _applied.update(versions)
            _primed = True
        _was_degraded = degraded
        return
    for kind, version in versions.items():
        if applied.get(kind, 0) == version:
            continue
        apply_local(kind)
        with _lock:
            _applied[kind] = version
    if _was_degraded and not degraded:
        # Redis 不可用期间别人发的版本号无从得知（连版本号本身都可能读不到），
        # 恢复后整体重放一次，把这段窗口里丢掉的事件补回来
        for kind in KINDS:
            apply_local(kind)
    _was_degraded = degraded


def apply_local(kind):
    """重放一次本地失效。**不广播**（否则与 notify 回环），由重入标志保证。"""
    if getattr(_local, 'applying', False):
        return
    _local.applying = True
    try:
        if kind == AUTH:
            # 鉴权缓存：evkey → 账号、账号 id → 账号、有无用户身份
            from modules.auth.auth import invalidate_auth_cache
            invalidate_auth_cache()
        elif kind == ACCESS:
            # 用户组权限（插件 / 路由 / 参数）整表重建
            from modules.database.access import preload_access_cache
            preload_access_cache()
        elif kind == GROUP:
            # 用户组限额改了：限额缓存全清
            from modules.utils.rate_limiter import invalidate_group_limits
            invalidate_group_limits()
            # 并发信号量按账号缓存、进程本地，且缓存的 key 里带 group_id（semaphores 的
            # 值为 (group_id, semaphore)），改组后旧上限必须整体丢弃。事件不带 group_id，
            # 与其在这里维护一份组 → 账号的映射，不如整体清空——这是管理端的低频操作
            semaphores = getattr(getattr(_app, 'state', None), 'render_semaphores', None)
            if semaphores is not None:
                semaphores.clear()
    finally:
        _local.applying = False