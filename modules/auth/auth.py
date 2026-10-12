import asyncio
import hmac
import os
import threading
import time
import secrets
from fastapi import Request, Response
import config
from modules.errors.errors import AuthError
from modules.database.core import is_db_available
from modules.utils import metrics as _metrics

_JWT_SECRET_ENV = os.environ.get('JWT_SECRET') or ''
# 没配 JWT_SECRET 时只能退回进程内随机值：能跑，但会话密钥随进程消亡，
# 每次重启都让全部登录态失效（多实例部署还会互相不认）。启动摘要会就此告警。
JWT_SECRET = _JWT_SECRET_ENV or secrets.token_hex(32)
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = int(os.environ.get('JWT_EXPIRY_HOURS', '24'))
SESSION_COOKIE_NAME = 'ink_session'


def uses_ephemeral_jwt_secret():
    """会话密钥是否为进程内随机兜底值（未配置 JWT_SECRET 环境变量）"""
    return not _JWT_SECRET_ENV


_auth_cache = None
_has_users_cache = None
_has_users_cache_ts = 0

# 下面几个缓存会被 worker 线程读写：查库那一步经 asyncio.to_thread 下放，
# 同一时刻可能有多个线程在补缓存，而 cachetools 的 Cache 本身不是线程安全的。
# RLock 是因为 _cached_get_* 会先取锁、内部再调同样取锁的 _get_auth_cache()。
_cache_lock = threading.RLock()


def _get_auth_cache():
    """鉴权缓存。AUTH_CACHE_TTL / AUTH_CACHE_MAXSIZE 是面板可改项，
    导入期烙进 TTLCache 会导致面板改完不生效，所以每次比对一次、变了就重建。"""
    global _auth_cache
    # TTLCache 延迟导入：鉴权缓存只在数据库可用时才用得上（Vercel 无库、走 EVKEY
    # 环境变量比对，从不建缓存），所以 Vercel 侧不装 cachetools 也跑得起来。
    from cachetools import TTLCache
    try:
        ttl = int(getattr(config, 'AUTH_CACHE_TTL', 60))
    except (TypeError, ValueError):
        ttl = 60
    try:
        maxsize = int(getattr(config, 'AUTH_CACHE_MAXSIZE', 100))
    except (TypeError, ValueError):
        maxsize = 100
    with _cache_lock:
        if _auth_cache is None or _auth_cache.ttl != ttl or _auth_cache.maxsize != maxsize:
            _auth_cache = TTLCache(maxsize=maxsize, ttl=ttl)
        return _auth_cache


def create_session_token(user_id):
    # PyJWT 只在会话 Cookie 上用（本地/单实例才有面板登录），所以延迟到函数内导入：
    # Vercel 侧走 evkey 鉴权、从不发会话，把 import 放模块级会让它白装一个包
    # （app.py 的导入链会经过本模块，模块级导入即 ImportError）。
    import jwt
    payload = {
        'user_id': user_id,
        'iat': int(time.time()),
        'exp': int(time.time()) + JWT_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_session_token(token):
    import jwt
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('user_id')
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def is_https_request(request):
    """请求是否经由 HTTPS（直连或反向代理转发）。

    会话 Cookie 只在 HTTPS 下加 Secure：自托管 prod 常以 http://ip:5000 直连，
    带 Secure 的 Cookie 浏览器根本不会回传，登录后立刻又是未登录状态。
    """
    proto = request.headers.get('x-forwarded-proto')
    if proto:
        return proto.split(',')[0].strip().lower() == 'https'
    return request.url.scheme == 'https'


def set_session_cookie(response: Response, token: str, secure=False):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite='lax',
        max_age=JWT_EXPIRY_HOURS * 3600,
        path='/',
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')


def _dev_user():
    """dev 模式下使用的默认用户对象"""
    return {
        'id': 1,
        'name': 'dev',
        'group_id': 1,
        'group_name': 'admin',
        'enabled': 1,
    }


async def check_auth(request: Request):
    """
    鉴权流程:
    1. 尝试验证 Session Cookie (admin 登录态)
    2. dev 模式: 注入默认 dev 用户, 跳过鉴权
    3. 白名单路径免鉴权
    4. evkey 校验 (数据库用户 > 环境变量)
    """
    path = request.url.path

    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token and is_db_available():
        try:
            user_id = decode_session_token(session_token)
            if user_id is not None:
                user = await asyncio.to_thread(_cached_get_account, user_id)
                if user is not None:
                    request.state.user = user
                    request.state.user_group_id = user['group_id']
                    request.state.user_group_name = user['group_name']
                    return
        except Exception:
            pass

    if not config.AUTH_ENABLE:
        if not hasattr(request.state, 'user') or request.state.user is None:
            request.state.user = _dev_user()
        request.state.user_group_id = request.state.user.get('group_id', 1)
        request.state.user_group_name = request.state.user.get('group_name', 'admin')
        return

    for prefix in config.AUTH_WHITELIST:
        # '/' 只做精确匹配，否则会放行所有路径
        if path == prefix or (prefix != '/' and path.startswith(prefix)):
            return

    evkey = request.headers.get('evkey') or request.query_params.get('evkey')
    if not evkey:
        raise AuthError('缺少鉴权密钥 evkey')

    try:
        # Vercel 模式无数据库，直接跳过用户表查询，回落到 EVKEY 环境变量比对。
        # 查库是同步 SQLite（单连接 + 全局锁），一律下放到 worker 线程：鉴权中间件在
        # 事件循环里跑，直接调用会把所有并发请求一起卡住。
        if is_db_available() and await asyncio.to_thread(_cached_has_users):
            user = await asyncio.to_thread(_cached_get_user, evkey)
            if user is None:
                raise AuthError('无效的 evkey，用户不存在或已禁用')
            request.state.user = user
            request.state.user_group_id = user['group_id']
            request.state.user_group_name = user['group_name']
            return
    except AuthError:
        raise
    except Exception:
        pass

    env_key = os.environ.get('EVKEY')
    if not env_key:
        raise AuthError('未配置鉴权密钥 (EVKEY 环境变量或数据库用户)')
    # 定长比较：`!=` 会在第一个不同字符处短路，逐字节泄露密钥前缀信息。
    # 先编成 bytes：compare_digest 对含非 ASCII 的 str 会抛 TypeError，而请求头/查询
    # 参数的值是调用方可控的，直接比会把一次非法输入变成 500。
    if not hmac.compare_digest(evkey.encode('utf-8'), env_key.encode('utf-8')):
        raise AuthError('鉴权失败，evkey无效')


def _cached_has_users():
    global _has_users_cache, _has_users_cache_ts
    with _cache_lock:
        now = time.time()
        if _has_users_cache is not None and now - _has_users_cache_ts < 60:
            return _has_users_cache
    from modules.database.accounts import has_accounts
    result = has_accounts()
    with _cache_lock:
        _has_users_cache = result
        _has_users_cache_ts = now
    return result


def _cached_get_user(evkey):
    # 计数器在锁外累加：_cache_lock 与 metrics 自身的锁若互相嵌套，会多出一组
    # 需要维护的加锁顺序（缓存里存 None 表示「查过、不存在」，因此不能用 get 的默认值）
    cache = _get_auth_cache()
    with _cache_lock:
        found = evkey in cache
        user = cache[evkey] if found else None
    if found:
        _metrics.incr('auth_cache_hits')
        return user
    _metrics.incr('auth_cache_misses')
    from modules.database.accounts import get_account_by_evkey
    user = get_account_by_evkey(evkey)
    with _cache_lock:
        cache[evkey] = user
    return user


def _cached_get_account(user_id):
    """按账号 id 取用户（面板 Session 鉴权用），与 evkey 分支共用同一个缓存。

    key 加 `user:` 前缀与 evkey（32 位十六进制）区分开，避免命名空间相撞。
    账号被禁用/改密时由 invalidate_auth_cache() 清掉，旧会话立即失效。
    """
    cache = _get_auth_cache()
    key = f'user:{user_id}'
    with _cache_lock:
        found = key in cache
        user = cache[key] if found else None
    if found:
        _metrics.incr('auth_cache_hits')
        return user
    _metrics.incr('auth_cache_misses')
    from modules.database.accounts import get_account_by_id
    user = get_account_by_id(user_id)
    with _cache_lock:
        cache[key] = user
    return user


def auth_cache_stats():
    """鉴权缓存的条目 / 上限 / 命中情况（/metrics 用）。

    命中率骤降即「容量小于在线设备数」的信号：每个请求都在回落到查库（过全局数据库锁），
    面板上把 AUTH_CACHE_MAXSIZE 调大即可。
    """
    cache = _get_auth_cache()
    with _cache_lock:
        entries, maxsize, ttl = len(cache), cache.maxsize, cache.ttl
    return {
        'entries': entries,
        'maxsize': maxsize,
        'ttl': ttl,
        'hits': _metrics.counter('auth_cache_hits'),
        'misses': _metrics.counter('auth_cache_misses'),
    }


def invalidate_auth_cache(evkey=None):
    cache = _get_auth_cache()
    global _has_users_cache, _has_users_cache_ts
    with _cache_lock:
        if evkey:
            cache.pop(evkey, None)
        else:
            cache.clear()
        _has_users_cache = None
        _has_users_cache_ts = 0
    # 多实例：只清本进程的话，别的实例会继续按旧结果放行（改密/禁用账号后仍能用）
    from modules.shared import events
    events.notify(events.AUTH)