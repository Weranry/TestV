"""登录防撞库：同一账号 / 同一来源 IP 连续失败到阈值后锁定一段时间。

状态存放在共享后端（modules/shared）：未配置 REDIS_URL 时是进程内内存（与改造前一致），
配置后落在 Redis —— 多实例部署下同一账号的失败计数才能跨实例累计，否则攻击者只需
在实例之间轮换就能把「5 次失败锁定」摊薄成「每个实例各 5 次」。

账号与 IP 两个维度分别计数、任一超阈值即拒绝：只按账号锁，攻击者换 IP 就能绕过；
只按 IP 锁，分布式撞库（同一账号、多来源）又能绕过。锁定时长由锁 key 的 TTL 承担。

计时一律用 time.monotonic()（内存后端）：锁定与窗口都是「相对时长」，墙钟被 NTP 回拨后
`locked_until - now` 会突然变大（锁定被无限延长），前拨则会提前解锁。
"""


def _cfg():
    """每次现取配置：面板改完要立即生效，禁止在导入期捕获"""
    from config import (
        LOGIN_GUARD_ENABLE, LOGIN_MAX_FAILS, LOGIN_WINDOW_SECONDS,
        LOGIN_LOCK_SECONDS, LOGIN_GUARD_MAXSIZE,
    )
    return (LOGIN_GUARD_ENABLE, int(LOGIN_MAX_FAILS or 0),
            LOGIN_WINDOW_SECONDS, LOGIN_LOCK_SECONDS, LOGIN_GUARD_MAXSIZE)


def _backend():
    from modules.shared.backend import get_backend
    return get_backend()


async def check(keys):
    """这些 key 是否有任一处于锁定中，返回还需等待的整秒数（向上取整），0 表示未锁定"""
    enable, max_fails, _window, lock_seconds, _maxsize = _cfg()
    if not enable or max_fails <= 0 or lock_seconds <= 0:
        return 0
    return await _backend().guard_check(list(keys), lock_seconds)


async def record_failure(keys):
    """记一次失败；任一 key 在窗口内累计到阈值即锁定该 key"""
    enable, max_fails, window, lock_seconds, maxsize = _cfg()
    if not enable or max_fails <= 0 or lock_seconds <= 0:
        return
    await _backend().guard_failure(list(keys), max_fails, window, lock_seconds, maxsize)


async def record_success(keys):
    """登录成功：清掉这些 key 的失败记录与锁定"""
    await _backend().guard_success(list(keys))