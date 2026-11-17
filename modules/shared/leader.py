"""跨实例单例租约。

有些任务必须**全集群只有一个实例**在做：预渲染调度、到期扫描、日志/审计/成品图裁剪。
多实例同时做不会写坏数据（写入都是可重入的），但会把算力与库写入放大成 N 倍。

租约用「SET NX PX + token 比对续租」而不是「抢到就一直持有」：进程被强杀时锁必须
能自动过期，否则整个集群再没有人做这些清理。

未配置 REDIS_URL（MemoryBackend）时锁必然拿到，行为与「没有 leader 概念」等价。
"""
import uuid

LEADER_NAME = 'leader'


class LeaderLock:
    """一个具名租约。`maintain()` 兼做抢占与续租，调用方按固定周期驱动即可。"""

    def __init__(self, name=LEADER_NAME, ttl_seconds=None, token=None):
        self.name = name
        # token 每次进程启动都不同：旧进程被杀后遗留的锁不能被新进程误认成自己的
        self.token = token or uuid.uuid4().hex
        self._ttl = ttl_seconds
        self._held = False

    def ttl_seconds(self):
        """租约时长；未显式指定时现取配置（面板改了不必重启）"""
        if self._ttl:
            return max(1, int(self._ttl))
        import config
        try:
            return max(1, int(config.SHARED_LEADER_TTL_SECONDS or 30))
        except (TypeError, ValueError):
            return 30

    def held(self):
        return self._held

    async def maintain(self):
        """一次抢占/续租；返回当前是否持有租约"""
        from modules.shared.backend import get_backend
        try:
            ok = await get_backend().lock_maintain(self.name, self.token, self.ttl_seconds())
        except Exception:
            ok = False
        self._held = bool(ok)
        return self._held

    async def release(self):
        """主动释放（优雅停机用：让下一个实例立刻接管，不必等租约过期）"""
        from modules.shared.backend import get_backend
        try:
            await get_backend().lock_release(self.name, self.token)
        except Exception:
            pass
        self._held = False