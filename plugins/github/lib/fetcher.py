"""GitHub 取数：并发请求 + 进程内 TTL 缓存。

三个请求（用户资料 / 仓库列表 / 贡献图）互不依赖，用 `asyncio.gather` 并发发出。
未认证的 GitHub API 限 60 次/小时，而一次出图就要 3 次请求；预渲染会反复渲染同一批
URL，因此按 username 做一层 TTL 缓存，否则配额很快被打满。

仓库列表与贡献图只影响星标数和一小片方格：这两个请求失败时按「没有数据」处理，
只有用户资料拿不到才算失败——否则一个装饰性端点的抖动就能把整张仪表盘连坐成 400。

缓存是模块级字典：热重载清掉 `sys.modules` 后本模块会被重新导入，缓存自然重建，
不需要框架层再提供失效入口。
"""
import asyncio
import re
import threading
import time

import httpx

from modules.errors.errors import NotFoundError, ParamError
from modules.utils import plog

_USER_AGENT = 'eInkViews-github-plugin'
_TIMEOUT_SECONDS = 15.0

_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 32

# 按插入顺序淘汰最旧的条目（FIFO，命中时不重排）
_cache = {}
_cache_lock = threading.Lock()


def _cache_get(username):
    with _cache_lock:
        entry = _cache.get(username)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.monotonic():
            _cache.pop(username, None)
            return None
        return value


def _cache_put(username, value):
    with _cache_lock:
        _cache[username] = (value, time.monotonic() + _CACHE_TTL_SECONDS)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))


def _usable(resp):
    """拿到了响应且是 200。请求本身失败（超时 / 连不上）时传进来的是异常对象"""
    return isinstance(resp, httpx.Response) and resp.status_code == 200


def _parse_repos(repos_resp):
    """仓库列表 → (总 star 数, star 最多的仓库)"""
    total_stars = 0
    top_repo = None
    if not _usable(repos_resp):
        return total_stars, top_repo

    max_stars = -1
    for repo in repos_resp.json():
        stars = repo.get('stargazers_count', 0)
        total_stars += stars
        if stars > max_stars:
            max_stars = stars
            top_repo = repo
    return total_stars, top_repo


def _parse_contributions(contrib_resp):
    """贡献图 HTML → [(date, level), ...]，按日期升序"""
    if not _usable(contrib_resp):
        return []
    pattern = r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?data-level="(\d+)"'
    matches = re.findall(pattern, contrib_resp.text)
    matches.sort(key=lambda x: x[0])
    return matches


async def fetch_github_data(username):
    if not username:
        raise ParamError("username is required")

    cached = _cache_get(username)
    if cached is not None:
        return cached

    user_url = f"https://api.github.com/users/{username}"
    repos_url = f"https://api.github.com/users/{username}/repos"
    contributions_url = f"https://github.com/users/{username}/contributions"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT, 'Accept': 'application/vnd.github+json'},
            follow_redirects=True,
        ) as client:
            # 三个请求互不依赖，必须并发：串行会把出图耗时累加成三次网络往返。
            # return_exceptions 收下单个请求的异常，交给下面按「有没有数据」分别处理
            user_resp, repos_resp, contrib_resp = await asyncio.gather(
                client.get(user_url),
                client.get(repos_url, params={'per_page': 100, 'sort': 'pushed'}),
                client.get(contributions_url),
                return_exceptions=True,
            )
    except httpx.HTTPError as e:
        raise ParamError(f"GitHub fetch failed: {type(e).__name__}: {str(e)}")

    if isinstance(user_resp, Exception):
        # 用户资料是这张图的骨架，拿不到就只能算失败。httpx 超时异常的 str() 可能是空串，
        # 带上类型名才知道是超时还是解析错误，否则错误提示会只剩个「fetch failed: 」
        raise ParamError(f"GitHub fetch failed: {type(user_resp).__name__}: {str(user_resp)}")
    if user_resp.status_code == 404:
        raise NotFoundError(f"GitHub user {username} not found")
    if user_resp.status_code != 200:
        raise ParamError(f"GitHub fetch failed: HTTP {user_resp.status_code}")

    for label, resp in (('repos', repos_resp), ('contributions', contrib_resp)):
        if isinstance(resp, Exception):
            plog.info(f'GitHub {label} 取数失败，按空处理: {type(resp).__name__}: {str(resp)}')

    data = user_resp.json()
    total_stars, top_repo = _parse_repos(repos_resp)

    user_info = {
        'name': data.get('name') or username,
        'login': data.get('login'),
        'bio': data.get('bio'),
        'public_repos': data.get('public_repos'),
        'followers': data.get('followers'),
        'following': data.get('following'),
        'total_stars': total_stars,
        'contributions': _parse_contributions(contrib_resp),
    }
    if top_repo:
        user_info['top_repo_name'] = top_repo.get('name')
        user_info['top_repo_stars'] = top_repo.get('stargazers_count')
        user_info['top_repo_desc'] = top_repo.get('description')
        user_info['top_repo_lang'] = top_repo.get('language')

    _cache_put(username, user_info)
    return user_info