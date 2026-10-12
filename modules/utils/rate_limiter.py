import asyncio
import time
import threading
from collections import deque
from cachetools import TTLCache
from fastapi import Request
from modules.errors.errors import error_response
from modules.utils import metrics as _metrics


class SlidingWindow:
    """滑动窗口计数器。

    限额在 check() 时才传入，因此管理员改用户组限额后立即生效，不必重建计数器。
    每个 key 存一个按时间递增的 deque，check() 只从左侧增量剔除过期时间戳，
    复杂度降到 O(过期数)；限额 1000 时不必每请求重建整份列表、比较 1000 次。

    计时一律用 time.monotonic()：墙钟被 NTP 回拨或前拨时，窗口内的时间戳会凭空
    变"旧"或被推到未来，限流随之失真（回拨后旧时间戳永不出窗口 = 误封，前拨后
    整个窗口被清空 = 绕过限流）。单调时钟只保证前进，窗口语义才成立。
    """

    def __init__(self, window_seconds):
        from config import RATE_LIMITER_STORE_MAXSIZE
        self.window = window_seconds
        self._store = TTLCache(maxsize=RATE_LIMITER_STORE_MAXSIZE, ttl=window_seconds)
        self._lock = threading.Lock()

    def _prune(self, stamps, now):
        """剔除窗口外的旧时间戳（deque 头部即最旧）"""
        cutoff = now - self.window
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()

    def size(self):
        """当前追踪的 key 数量（管理面板健康检查用，只读）"""
        with self._lock:
            return len(self._store)

    def check(self, key, limit):
        """记一次请求，返回 (是否放行, 剩余次数)。limit <= 0 表示不限制，此时不记录、不占内存。"""
        if limit <= 0:
            return True, -1
        with self._lock:
            now = time.monotonic()
            stamps = self._store.get(key)
            if stamps is None:
                stamps = deque()
            else:
                self._prune(stamps, now)
            if len(stamps) >= limit:
                self._store[key] = stamps
                return False, 0
            stamps.append(now)
            # 回写以刷新条目 TTL，否则窗口内仍在计数的条目会被整条过期丢掉
            self._store[key] = stamps
            return True, limit - len(stamps)

    def count(self, key):
        """窗口内已记录次数（只读，不改状态）"""
        with self._lock:
            stamps = self._store.get(key)
            if not stamps:
                return 0
            cutoff = time.monotonic() - self.window
            used = 0
            for t in reversed(stamps):
                if t <= cutoff:
                    break
                used += 1
            return used

    def peek(self, key, limit):
        """只读查看当前窗口内已用次数，不记请求、不改状态。limit <= 0 表示不限，返回 -1。"""
        if limit <= 0:
            return -1
        return self.count(key)


def store_size():
    """当前后端在本实例内存中追踪的 key 数（管理面板健康检查用）

    共享后端为 Redis 时它只是本实例的回落计数条目数——跨实例的 key 总数要查 Redis，
    不适合放在按秒轮询的健康检查里。
    """
    from modules.shared.backend import get_backend
    return get_backend().local_size()


def _account_id(request):
    """当前请求的账号 id；无用户身份（如环境变量 EVKEY 鉴权）返回 None"""
    user = getattr(request.state, 'user', None)
    return user.get('id') if isinstance(user, dict) else None


def _quota_scope(request):
    """额度归属：按用户（账号）聚合，同一账号下所有 evkey 共用一份计数。

    用户组只提供限额数值与权限，不参与计数。无用户身份时退回到 evkey 本身，
    再退到来源 IP。这里只用于内存滑动窗口的 key，配额计数按账号落库。
    """
    user_id = _account_id(request)
    if user_id is not None:
        return f'user:{user_id}'
    evkey = request.headers.get('evkey') or request.query_params.get('evkey')
    if evkey:
        return f'evkey:{evkey}'
    # 取法与登录防撞库共用一份（modules/utils/client_ip.py）：
    # 代理后的部署要么开 TRUST_PROXY_HEADERS，要么所有人共用这一份额度
    from modules.utils.client_ip import client_ip
    return client_ip(request)


_group_limits_cache = {}
_group_limits_lock = threading.Lock()


def _group_limits_cached(group_id):
    """只读缓存查询：命中返回 (True, 限额)，未命中返回 (False, None)。

    命中路径是纯 dict 查找（微秒级），不值得付一次线程调度开销；因此把它单独拆出来，
    让调用方只在真正要查库时才走 worker 线程。
    """
    with _group_limits_lock:
        if group_id in _group_limits_cache:
            return True, _group_limits_cache[group_id]
    return False, None


def _group_limits(group_id):
    """读取用户组限额，返回 (每分钟速率, 配额上限, 配额周期)，0 = 不限；查不到返回 None。

    带内存缓存：不带的话每个带组身份的请求都要跑一次 `SELECT * FROM user_groups`，
    还走全局数据库锁。限额本身是「改完立即生效」的语义，因此不做 TTL，只靠
    admin_update_group / admin_delete_group 显式失效——否则就要等过期才生效。

    本函数是**同步**的，只能从同步上下文调用；异步中间件里请走
    `_group_limits_cached` + asyncio.to_thread，否则查库会阻塞事件循环。
    """
    hit, limits = _group_limits_cached(group_id)
    if hit:
        return limits
    from modules.database.groups import get_group
    from modules.database.quotas import normalize_period
    group = get_group(group_id)
    if not group:
        limits = None
    else:
        limits = (
            int(group.get('rate_limit_per_minute') or 0),
            int(group.get('quota_limit') or 0),
            normalize_period(group.get('quota_period')),
        )
    with _group_limits_lock:
        _group_limits_cache[group_id] = limits
    return limits


def invalidate_group_limits(group_id=None):
    """用户组限额变更后立即失效缓存（group_id 为 None 时全清）"""
    with _group_limits_lock:
        if group_id is None:
            _group_limits_cache.clear()
        else:
            _group_limits_cache.pop(group_id, None)
    # 多实例：别的实例的限额缓存也要失效（事件不带 group_id，接收侧整体清空）
    from modules.shared import events
    events.notify(events.GROUP)


async def _resolve_group_limits(group_id):
    """异步解析用户组限额：命中缓存是纯 dict 查找，不付线程调度开销；
    未命中才查库，且必须下放 worker 线程——同步 SQLite + 全局数据库锁，
    直接在事件循环里跑会把并发的所有请求一起卡住。解析失败返回 None（回落全局配置）"""
    hit, limits = _group_limits_cached(group_id)
    if hit:
        return limits
    try:
        return await asyncio.to_thread(_group_limits, group_id)
    except Exception:
        return None


async def _sliding_check(specs):
    """把两段窗口检查交给共享后端，合并成一次调用（Redis 下即一次往返）"""
    from modules.shared.backend import get_backend
    return await get_backend().sliding_check(specs)


async def check_scoped(key, limit, window_seconds=60):
    """给「非账号维度」的限流用：按任意作用域 key 记一次，返回 `(是否放行, 剩余)`。

    全站限流中间件按账号 / evkey / IP 计数，而设备面走 `X-Device-Token` 鉴权、
    既没有 evkey 也不该共用同 NAT 下其它设备的额度，因此需要按 `device:<id>` 这样的
    作用域单独计数。key 是任意可哈希值（见 `SlidingWindow.check`）。
    """
    if limit <= 0:
        return True, -1
    # 后端按「一次调用可带多段窗口」设计，返回的是逐段结果的列表；这里只要第一段
    return (await _sliding_check([(key, limit, window_seconds)]))[0]


async def _sliding_peek(key, window):
    from modules.shared.backend import get_backend
    return await get_backend().sliding_peek(key, window)


async def quota_usage(request):
    """当前请求所属额度范围的实时用量（只读，不计数），供个人控制台展示。

    与 rate_limit_middleware 共用同一套限额解析，避免两处各写一份后对不上：
    有用户组身份时用组配额（落库、按账号计数），无组身份时回落全局小时窗口。
    """
    from config import (
        RATE_LIMIT_ENABLE, RATE_LIMIT_PER_MINUTE, RATE_LIMIT_PER_HOUR,
    )
    group_id = getattr(request.state, 'user_group_id', None)
    limits = await _resolve_group_limits(group_id) if group_id is not None else None
    scope = _quota_scope(request)
    if limits is not None:
        per_minute, quota_limit, quota_period = limits
        # get_status 返回的是「组配额 + 该账号发放额」，展示与限流文案都用它
        long_limit, used, period, _ = await _quota_status(request, quota_limit, quota_period)
        return {
            'enabled': bool(RATE_LIMIT_ENABLE),
            'per_minute': per_minute,
            'minute_used': await _sliding_peek(scope, 60) if per_minute > 0 else -1,
            'long_label': _quota_used_label(request, period),
            'long_limit': long_limit,
            'long_used': used,
        }
    return {
        'enabled': bool(RATE_LIMIT_ENABLE),
        'per_minute': RATE_LIMIT_PER_MINUTE,
        'minute_used': await _sliding_peek(scope, 60) if RATE_LIMIT_PER_MINUTE > 0 else -1,
        'long_label': _quota_used_label(request, None),
        'long_limit': RATE_LIMIT_PER_HOUR,
        'long_used': await _sliding_peek(scope, 3600) if RATE_LIMIT_PER_HOUR > 0 else -1,
    }


_QUOTA_EXHAUSTED = {
    # trial 是「按次总量」模式，不止内置 Try 组在用，文案保持中性
    'trial': '总量额度已用完（共 {limit} 次），如需继续请联系管理员',
    'day': '今日请求已达上限（{limit} 次），请明天再试',
    'week': '本周请求已达上限（{limit} 次），请下周再试',
    'month': '本月请求已达上限（{limit} 次），请下月再试',
    'year': '本年请求已达上限（{limit} 次），请明年再试',
}

_QUOTA_USED_KEY = {
    'trial': 'account.used_trial', 'day': 'account.used_day', 'week': 'account.used_week',
    'month': 'account.used_month', 'year': 'account.used_year',
}


def _quota_exhausted_label(period):
    return _QUOTA_EXHAUSTED.get(period, '请求已达上限（{limit} 次）')


def _quota_used_label(request, period):
    """实时用量卡片的标签文案：按请求语言取词。

    `period=None` 表示无用户组身份，回落全局小时窗口（`account.used_hour`）。
    """
    from modules.i18n.registry import t_req
    if not period:
        return t_req(request, 'account.used_hour')
    return t_req(request, _QUOTA_USED_KEY.get(period, 'account.used_period'))


async def _quota_status(request, limit, period):
    """只读查询配额用量；无账号身份或未配置配额时直接给出「不限」"""
    account_id = _account_id(request)
    if account_id is None:
        return limit, 0, period, ''
    from modules.database.quotas import get_status
    return await asyncio.to_thread(get_status, account_id, limit, period)


async def _consume_quota(request, limit, period):
    """消耗一次配额，返回 (是否放行, 剩余次数, 实际额度)。

    配额落库（account_quotas）并按账号计数、惰性重置：年 / 总量这类长周期额度重启
    不清零，周期到了由下一次请求当场归零，不需要定时任务。查库写库一律下放
    worker 线程——同步 SQLite 走全局数据库锁，直接在事件循环里跑会卡住所有并发请求。

    实际额度含管理员发放的部分（limit + granted），剩余量必须按实际额度算，
    否则发过额度的账号会提前被拒。
    """
    account_id = _account_id(request)
    if account_id is None:
        return True, -1, limit
    from modules.database.quotas import consume
    allowed, used, _, effective = await asyncio.to_thread(consume, account_id, limit, period)
    return allowed, max(0, effective - used) if allowed else 0, effective


async def rate_limit_middleware(request: Request, call_next):
    from config import (
        RATE_LIMIT_ENABLE, RATE_LIMIT_WHITELIST,
        RATE_LIMIT_PER_MINUTE, RATE_LIMIT_PER_HOUR,
    )

    if not RATE_LIMIT_ENABLE:
        return await call_next(request)

    path = request.url.path
    for prefix in RATE_LIMIT_WHITELIST:
        if path.startswith(prefix):
            return await call_next(request)

    group_id = getattr(request.state, 'user_group_id', None)
    group_limits = None
    if group_id is not None:
        group_limits = await _resolve_group_limits(group_id)

    scope = _quota_scope(request)
    if group_limits is not None:
        # 用户组提供限额数值，计数范围是账号：同一账号下所有 evkey 共用一份额度
        per_minute, quota_limit, quota_period = group_limits
        minute_label = '请求过于频繁，每分钟限制 {limit} 次，请稍后再试'
        long_label = _quota_exhausted_label(quota_period)
        specs = [(scope, per_minute, 60)]
        hour_label = None
    else:
        # 无组身份（如 EVKEY 环境变量鉴权）时回落到全局配置
        per_minute = RATE_LIMIT_PER_MINUTE
        quota_limit = None
        quota_period = None
        minute_label = '请求过于频繁，每分钟限制 {limit} 次，请稍后再试'
        hour_label = '请求过于频繁，每小时限制 {limit} 次，请稍后再试'
        # 两个窗口一次交给后端（Redis 下即一次往返）；后端按顺序检查、被拒即短路，
        # 因此被分钟额度拒掉的请求不会顺带占掉小时的计数
        specs = [(scope, per_minute, 60), (scope, RATE_LIMIT_PER_HOUR, 3600)]

    results = await _sliding_check(specs)
    allowed, minute_remaining = results[0]
    if not allowed:
        _metrics.incr('rate_limit_rejected')
        return error_response(minute_label.format(limit=per_minute), 429)

    if quota_period is not None:
        long_limit = quota_limit
        long_remaining = -1
        # 0 = 不限：不落库、不查库，无配额的组在热路径上不为配额付任何开销
        if long_limit > 0:
            allowed, long_remaining, long_limit = await _consume_quota(request, long_limit, quota_period)
            if not allowed:
                _metrics.incr('rate_limit_rejected')
                return error_response(long_label.format(limit=long_limit), 429)
    else:
        long_limit = RATE_LIMIT_PER_HOUR
        allowed, long_remaining = results[1]
        if not allowed:
            _metrics.incr('rate_limit_rejected')
            return error_response(hour_label.format(limit=long_limit), 429)

    response = await call_next(request)

    if per_minute > 0:
        response.headers['X-RateLimit-Limit'] = str(per_minute)
        response.headers['X-RateLimit-Remaining'] = str(minute_remaining)
    if long_limit > 0:
        response.headers['X-RateLimit-Long-Limit'] = str(long_limit)
        response.headers['X-RateLimit-Long-Remaining'] = str(long_remaining)

    return response