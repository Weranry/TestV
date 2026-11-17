"""F1 站次信息的 JSON 输出，供接口调试与二次开发。

JSON 路由把全部查询参数原样透传给 `to_json`，因此这里用显式参数收下要用的两个键，
其余（size / rotate 等）由 `**kwargs` 吞掉。
"""
import asyncio
import concurrent.futures
import datetime

from ..lib.f1_client import fetch_race

# JSON 端点是在事件循环里**同步**调用 to_json 的（框架没有 async to_json 分支），
# 此时本线程已经在跑事件循环，直接 asyncio.run 会抛 RuntimeError。
# 因此把协程丢到独立线程用自己的循环跑（线程是复用的，不是每请求新建）。
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _run(coro):
    return _pool.submit(asyncio.run, coro).result()


def _jsonable(value):
    """datetime → 本地时间字符串，便于被 JSON 序列化"""
    if isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def to_json(round='next', season=None, tz=None, **kwargs):
    """`round`：next（默认）/ last / 站号整数；`season` 留空为当前赛季"""
    data = _run(fetch_race(round_ref=round, season=season, tz=tz))
    return _jsonable(data)
