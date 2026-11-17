"""内存共享后端：单实例（未配置 REDIS_URL）下的默认实现，也是 Redis 故障时的回落目标。

限流窗口直接复用 `modules.utils.rate_limiter.SlidingWindow`（单调时钟 + deque），
登录防撞库是原 `modules.utils.login_guard` 的状态机原样搬来：改造前这两处本就是
进程内内存实现，「未启用共享后端」时多实例各自独立计数是既定行为。
"""
import math
import threading
import time

from modules.shared.backend import SharedBackend
from modules.utils.rate_limiter import SlidingWindow


class _Guard:
    """登录防撞库状态机。

    计时一律用 `time.monotonic()`：锁定与窗口都是「相对时长」，墙钟被 NTP 回拨后
    `locked_until - now` 会突然变大（锁定被无限延长），前拨则提前解锁。
    """

    def __init__(self):
        # key -> 窗口内的失败时间戳列表；key -> 解锁时间戳
        self.fails = {}
        self.locked_until = {}
        self._lock = threading.Lock()

    def _purge(self, now, window, maxsize):
        """表超过上限时清掉已过期项，避免长期运行内存无界（调用方需持锁）"""
        if len(self.fails) + len(self.locked_until) <= maxsize:
            return
        cutoff = now - window
        for k in [k for k, v in self.fails.items() if not v or v[-1] <= cutoff]:
            self.fails.pop(k, None)
        for k in [k for k, t in self.locked_until.items() if t <= now]:
            self.locked_until.pop(k, None)

    def check(self, keys):
        now = time.monotonic()
        with self._lock:
            remaining = [self.locked_until[k] - now for k in keys if self.locked_until.get(k, 0) > now]
        if not remaining:
            return 0
        return max(1, int(math.ceil(max(remaining))))

    def failure(self, keys, max_fails, window, lock_seconds, maxsize):
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            self._purge(now, window, maxsize)
            for k in keys:
                stamps = [t for t in self.fails.get(k, []) if t > cutoff]
                stamps.append(now)
                if len(stamps) >= max_fails:
                    self.locked_until[k] = now + lock_seconds
                    self.fails.pop(k, None)
                else:
                    self.fails[k] = stamps

    def success(self, keys):
        with self._lock:
            for k in keys:
                self.fails.pop(k, None)
                self.locked_until.pop(k, None)


class _Leases:
    """单例租约（内存版）。

    计时用 `time.monotonic()`（同 _Guard）：租约是相对时长，墙钟回拨会让
    「锁已过期」判定失真。未配置 REDIS_URL 时单实例必然拿到锁，行为与
    「没有 leader 概念」等价；Redis 不可用时的回落也走这里（见 redis_backend）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._leases = {}

    def maintain(self, name, token, ttl_seconds):
        now = time.monotonic()
        with self._lock:
            holder, deadline = self._leases.get(name, (None, 0))
            if holder is not None and holder != token and deadline > now:
                return False
            self._leases[name] = (token, now + ttl_seconds)
            return True

    def release(self, name, token):
        with self._lock:
            if self._leases.get(name, (None, 0))[0] == token:
                self._leases.pop(name, None)


class MemoryBackend(SharedBackend):
    """进程内实现：限流窗口按 window 秒数各自一份 SlidingWindow"""

    name = 'memory'

    def __init__(self):
        self._windows = {}
        self._windows_lock = threading.Lock()
        self._guard = _Guard()
        self._leases = _Leases()
        self._versions = {}
        self._versions_lock = threading.Lock()

    def _window(self, window_seconds):
        with self._windows_lock:
            w = self._windows.get(window_seconds)
            if w is None:
                w = SlidingWindow(window_seconds)
                self._windows[window_seconds] = w
            return w

    def local_size(self):
        with self._windows_lock:
            windows = list(self._windows.values())
        return sum(w.size() for w in windows)

    async def sliding_check(self, specs):
        results = []
        for key, limit, window in specs:
            allowed, remaining = self._window(window).check(key, limit)
            results.append((allowed, remaining))
            if not allowed:
                break
        while len(results) < len(specs):
            results.append((False, -1))
        return results

    async def sliding_peek(self, key, window):
        return self._window(window).count(key)

    async def guard_check(self, keys, lock_seconds):
        return self._guard.check(keys)

    async def guard_failure(self, keys, max_fails, window, lock_seconds, maxsize):
        self._guard.failure(keys, max_fails, window, lock_seconds, maxsize)

    async def guard_success(self, keys):
        self._guard.success(keys)

    async def lock_maintain(self, name, token, ttl_seconds):
        return self._leases.maintain(name, token, ttl_seconds)

    async def lock_release(self, name, token):
        self._leases.release(name, token)

    async def version_get(self, kinds):
        with self._versions_lock:
            return {kind: int(self._versions.get(kind, 0)) for kind in kinds}

    async def version_bump(self, kinds):
        with self._versions_lock:
            result = {}
            for kind in kinds:
                value = int(self._versions.get(kind, 0)) + 1
                self._versions[kind] = value
                result[kind] = value
            return result