"""共享后端：多实例（配置 REDIS_URL）下跨进程共享的短生命周期状态。

改造前限流计数与登录防撞库状态都在进程内存里，多实例部署时每个实例各记一份：
限流随之变成 N 倍宽松（每个 worker 各有一份额度），撞库计数也各自为政。

- `REDIS_URL` 为空 → MemoryBackend，行为与改造前逐字节一致（monotonic + 进程内字典）；
- 配了 `REDIS_URL` → RedisBackend，用 Redis 服务端 TIME 做跨进程可比较的滑动窗口。

Redis 导入或连接失败一律自动回落内存并置 `degraded`（/metrics 可见）：既不 fail-open
（等于没限流），也不 fail-closed（把 Redis 抖动放大成全站 503——fail-closed 惯例针对的是
权限越权，限流只是可用性保护）。
"""
import threading

from modules.utils import plog

_backend = None
_injected = False
_signature = None
_lock = threading.Lock()


class SharedBackend:
    """共享后端接口。

    所有方法都可能被并发调用，实现方各自保证线程/连接安全。方法一律异步：Redis
    实现要走网络，同步签名会逼调用方在事件循环里阻塞。
    """

    name = 'memory'
    degraded = False

    def status(self):
        """当前后端状态（/metrics 与面板用，只读）"""
        return {'backend': self.name, 'degraded': bool(self.degraded), 'keys': self.local_size()}

    def local_size(self):
        """本实例内存中追踪的限流条目数（多实例下不含其它实例）"""
        return 0

    async def sliding_check(self, specs):
        """滑动窗口限流。

        `specs = [(key, limit, window_seconds)]`，按顺序检查并**短路**：前一个窗口被拒时
        后面的窗口不再计数（被拒的请求不占位，否则用量会被自己的拒绝请求越推越满）。
        返回与 specs 等长的 `[(是否放行, 剩余次数)]`，未执行的条目回填 `(False, -1)`。
        `limit <= 0` 表示不限：不计数、不占内存。
        """
        raise NotImplementedError

    async def sliding_peek(self, key, window):
        """窗口内的已用次数（只读，不计数）"""
        raise NotImplementedError

    async def guard_check(self, keys, lock_seconds):
        """任一 key 处于锁定中时返回还需等待的整秒数（向上取整），0 表示未锁定"""
        raise NotImplementedError

    async def guard_failure(self, keys, max_fails, window, lock_seconds, maxsize):
        """记一次失败；任一 key 在窗口内累计到阈值即锁定该 key"""
        raise NotImplementedError

    async def guard_success(self, keys):
        """登录成功：清掉这些 key 的失败记录与锁定"""
        raise NotImplementedError

    # ---- 单例租约（H3：调度与清理类任务只允许一个实例做）----

    async def lock_maintain(self, name, token, ttl_seconds):
        """续租单例锁；锁空闲或持有者就是本 token 时返回 True。

        把「抢占」和「续租」合成一条命令（一次往返）：分成 SET NX + 比对续租两条时，
        网络抖动会让续租失败而锁其实还在自己手上，下一轮 SET NX 又必然失败，
        白白丢掉一个租约周期。
        """
        raise NotImplementedError

    async def lock_release(self, name, token):
        """释放单例锁（只释放自己持有的那把）"""
        raise NotImplementedError

    # ---- 缓存失效版本号（H4：跨实例广播内存态失效）----

    async def version_get(self, kinds):
        """各 kind 的当前版本号（不存在的按 0）"""
        raise NotImplementedError

    async def version_bump(self, kinds):
        """自增各 kind 的版本号，返回自增后的值"""
        raise NotImplementedError


def get_backend():
    """当前共享后端（进程内单例）。REDIS_URL 变化时按新配置重建。"""
    global _backend, _signature
    if _injected:
        return _backend
    from config import REDIS_URL, SHARED_KEY_PREFIX
    signature = (REDIS_URL or '', SHARED_KEY_PREFIX or '')
    if _backend is not None and _signature == signature:
        return _backend
    with _lock:
        if _backend is not None and _signature == signature:
            return _backend
        _backend = _build(signature[0], signature[1])
        _signature = signature
    return _backend


def _build(url, prefix):
    if not url:
        from modules.shared.memory import MemoryBackend
        return MemoryBackend()
    try:
        from modules.shared.redis_backend import RedisBackend
        return RedisBackend(url, prefix)
    except Exception:
        # 没装 redis 客户端或 URL 非法：回落内存并留痕（启动摘要与面板都能看到）
        plog.exception('Redis 共享后端不可用，已回落内存后端')
        from modules.shared.memory import MemoryBackend
        return MemoryBackend()


def set_backend(backend):
    """测试注入共享后端（传 None 恢复「按配置构建」）"""
    global _backend, _injected
    with _lock:
        _backend = backend
        _injected = backend is not None