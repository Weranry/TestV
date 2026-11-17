"""Redis 共享后端：跨实例限流与登录防撞库。

计时用 Redis 服务端 `TIME`：滑动窗口要跨进程比较，必须用同一个时钟源，
`time.monotonic()` 只在单个进程内可比较（两个进程的 monotonic 起点无关）。

窗口用 ZSET 而不是 `INCR + PEXPIRE`：固定窗口在边界会放出两倍突发，
属于静默的语义损失。热路径上「分钟 + 小时」两个窗口合成 **一次** Lua 调用：

- 服务端取一次 `TIME`；
- 逐窗口按顺序检查，前一个被拒即短路（被拒的请求不占位后续窗口）；
- 成员名带随机后缀，同一毫秒的并发请求不会互相覆盖彼此的计数。

任何 Redis 异常都回落 MemoryBackend 计数并置 `degraded`（见 backend.py 的说明）。
"""
import math

from modules.shared.backend import SharedBackend
from modules.shared.memory import MemoryBackend
from modules.utils import plog

# 滑动窗口检查：ARGV 是 [limit, window_ms] 交替；KEYS 是完整 key 名。
# 返回扁平数组 [allowed, remaining, ...]，被短路时数组更短，调用方按位置回填。
_WINDOW_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local out = {}
for i = 1, #KEYS do
  local limit = tonumber(ARGV[(i - 1) * 2 + 1])
  local win = tonumber(ARGV[(i - 1) * 2 + 2])
  local key = KEYS[i]
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - win)
  local used = redis.call('ZCARD', key)
  if used >= limit then
    break
  end
  redis.call('ZADD', key, now, now .. ':' .. tostring(math.random(1000000)))
  redis.call('PEXPIRE', key, win)
  out[#out + 1] = 1
  out[#out + 1] = limit - used - 1
end
return out
"""

# 登录失败计数：ARGV = [max_fails, window_ms, lock_ms, lock_key_1, ..., lock_key_N]
# KEYS 是各 key 的失败计数 ZSET；锁定时长由锁 key 的 TTL 承担。
_GUARD_LUA = """
local maxf = tonumber(ARGV[1])
local win = tonumber(ARGV[2])
local lock_ms = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
for i = 1, #KEYS do
  local key = KEYS[i]
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - win)
  redis.call('ZADD', key, now, now .. ':' .. tostring(math.random(1000000)))
  redis.call('PEXPIRE', key, win)
  if redis.call('ZCARD', key) >= maxf then
    redis.call('SET', ARGV[3 + i], '1', 'PX', lock_ms)
    redis.call('DEL', key)
  end
end
return 1
"""

# 单例租约：ARGV = [token, ttl_ms]。持有者是本 token（续租）或锁空闲（抢占）都返回 1。
# 用一条脚本同时承担两件事，避免「续租失败但锁还在自己手上」被误判成丢掉租约。
_LEADER_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
  return 1
end
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
  return 1
end
return 0
"""

# 释放租约：比对 token 后才删，避免删掉已经换了持有者的锁
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""


class RedisBackend(SharedBackend):
    """Redis 实现。客户端懒连接：构造时不握手，第一条命令才真的连，

    这样 `REDIS_URL` 写错也不会在启动期炸掉，而是走降级路径（回落内存 + degraded 标志）。
    """

    name = 'redis'

    def __init__(self, url, prefix='einkviews', client=None):
        from config import SHARED_TIMEOUT_MS

        try:
            timeout = max(0.05, int(SHARED_TIMEOUT_MS or 200) / 1000.0)
        except (TypeError, ValueError):
            timeout = 0.2
        if client is None:
            # 懒连接：from_url 不握手，第一条命令才真的连，所以 URL 写错也不会在启动期炸掉
            from redis import asyncio as redis_async
            client = redis_async.from_url(
                url, decode_responses=True,
                socket_timeout=timeout, socket_connect_timeout=timeout,
            )
        self._client = client
        self._prefix = (prefix or 'einkviews').rstrip(':')
        self._fallback = MemoryBackend()
        self._sha = {}
        self.degraded = False

    # ---- 内部 ----

    def _key(self, kind, name):
        return f'{self._prefix}:{kind}:{name}'

    def _mark_alive(self):
        """Redis 可用：清掉降级标志（降级期间的失效事件由 shared.events 的轮询补全量重放）"""
        self.degraded = False

    def _degrade(self):
        """只在首次降级时留痕：Redis 抖动期间每请求打一次栈会把日志冲垮"""
        if not self.degraded:
            plog.exception('Redis 共享后端异常，已降级为内存计数')
            self.degraded = True

    async def _eval(self, name, script, keys, args):
        """EVALSHA 优先（脚本体只传一次），NOSCRIPT 时补一次 SCRIPT LOAD 重试"""
        sha = self._sha.get(name)
        if sha:
            try:
                return await self._client.evalsha(sha, len(keys), *keys, *args)
            except Exception as exc:
                if 'NOSCRIPT' not in str(exc):
                    raise
        sha = await self._client.script_load(script)
        self._sha[name] = sha
        return await self._client.evalsha(sha, len(keys), *keys, *args)

    async def _fallback_or_open(self, specs):
        """降级：默认回落本地内存计数；显式关掉回落后直接放行（不再本地计数）"""
        from config import SHARED_FALLBACK_LOCAL
        if not SHARED_FALLBACK_LOCAL:
            return [(True, -1) for _ in specs]
        return await self._fallback.sliding_check(specs)

    # ---- 限流 ----

    def local_size(self):
        return self._fallback.local_size()

    async def sliding_check(self, specs):
        results = [(True, -1)] * len(specs)
        active = [i for i, spec in enumerate(specs) if int(spec[1]) > 0]
        if not active:
            return results
        keys = [self._key('rl', specs[i][0]) for i in active]
        args = []
        for i in active:
            args.append(int(specs[i][1]))
            args.append(int(specs[i][2]) * 1000)
        try:
            out = await self._eval('window', _WINDOW_LUA, keys, args)
        except Exception:
            self._degrade()
            return await self._fallback_or_open(specs)
        self._mark_alive()
        values = [int(v) for v in (out or [])]
        for n, idx in enumerate(active):
            if 2 * n + 2 > len(values):
                results[idx] = (False, -1)  # 服务端短路，该窗口未计数
            else:
                results[idx] = (bool(values[2 * n]), values[2 * n + 1])
        return results

    async def sliding_peek(self, key, window):
        try:
            t = await self._client.time()
            now_ms = int(t[0]) * 1000 + int(t[1]) // 1000
            used = await self._client.zcount(
                self._key('rl', key), f'({now_ms - int(window) * 1000}', '+inf')
            self._mark_alive()
            return int(used or 0)
        except Exception:
            self._degrade()
            return await self._fallback.sliding_peek(key, window)

    # ---- 登录防撞库 ----

    async def guard_check(self, keys, lock_seconds):
        if not keys:
            return 0
        try:
            pipe = self._client.pipeline(transaction=False)
            for k in keys:
                pipe.pttl(self._key('lock', k))
            outs = await pipe.execute()
            self._mark_alive()
        except Exception:
            self._degrade()
            return await self._fallback.guard_check(keys, lock_seconds)
        best = max([int(o or 0) for o in outs] or [0])
        if best <= 0:
            return 0
        return max(1, int(math.ceil(best / 1000.0)))

    async def guard_failure(self, keys, max_fails, window, lock_seconds, maxsize):
        if not keys:
            return
        args = [int(max_fails), int(window) * 1000, int(lock_seconds) * 1000]
        args += [self._key('lock', k) for k in keys]
        try:
            await self._eval('guard', _GUARD_LUA, [self._key('fail', k) for k in keys], args)
            self._mark_alive()
        except Exception:
            self._degrade()
            await self._fallback.guard_failure(keys, max_fails, window, lock_seconds, maxsize)

    async def guard_success(self, keys):
        if not keys:
            return
        try:
            pipe = self._client.pipeline(transaction=False)
            for k in keys:
                pipe.delete(self._key('fail', k))
                pipe.delete(self._key('lock', k))
            await pipe.execute()
            self._mark_alive()
        except Exception:
            self._degrade()
            await self._fallback.guard_success(keys)

    # ---- 单例租约 ----

    async def lock_maintain(self, name, token, ttl_seconds):
        key = self._key('leader', name)
        try:
            out = await self._eval('leader', _LEADER_LUA, [key], [token, int(ttl_seconds) * 1000])
            self._mark_alive()
            return bool(int(out or 0))
        except Exception:
            self._degrade()
            # 回落本地租约：单实例部署下 Redis 抖动不该顺带停掉到期扫描；多实例下
            # 降级期可能短暂出现两个 leader，重复执行的只是可重入的调度与裁剪，无正确性问题
            return await self._fallback.lock_maintain(name, token, ttl_seconds)

    async def lock_release(self, name, token):
        try:
            await self._eval('release', _RELEASE_LUA, [self._key('leader', name)], [token])
            self._mark_alive()
        except Exception:
            self._degrade()
            await self._fallback.lock_release(name, token)

    # ---- 缓存失效版本号 ----

    async def version_get(self, kinds):
        if not kinds:
            return {}
        try:
            pipe = self._client.pipeline(transaction=False)
            for kind in kinds:
                pipe.get(self._key('ver', kind))
            outs = await pipe.execute()
            self._mark_alive()
        except Exception:
            self._degrade()
            return await self._fallback.version_get(kinds)
        return {kind: int(value or 0) for kind, value in zip(kinds, outs)}

    async def version_bump(self, kinds):
        if not kinds:
            return {}
        try:
            pipe = self._client.pipeline(transaction=False)
            for kind in kinds:
                pipe.incr(self._key('ver', kind))
            outs = await pipe.execute()
            self._mark_alive()
        except Exception:
            self._degrade()
            return await self._fallback.version_bump(kinds)
        return {kind: int(value or 0) for kind, value in zip(kinds, outs)}