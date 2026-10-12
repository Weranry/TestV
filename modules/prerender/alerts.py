"""预渲染失败告警：通用 JSON webhook。

任务失败以前只落在任务行的 `last_status` 上，没有告警出口——坏任务会一直安静地
按周期重试失败。这里补一条最通用的出口：POST 一份 JSON 到配置的地址，具体怎么
转发（钉钉 / 飞书 / 自研网关）由接收端决定，框架不做适配。

三条硬约束：
- 没配 webhook 时不生成任何请求；
- 发送失败只打印堆栈，绝不影响调度（告警是附加能力，不能反过来把调度搞挂）；
- 同一任务在 PRERENDER_ALERT_MIN_INTERVAL 秒内只发一次，避免一个坏任务每周期刷屏。
"""
import datetime
import os
import socket
import threading
import time

import config
from modules.utils import plog

# 节流状态：task_id -> 上次发送的单调时钟。只在配置了最小间隔时才写入，
# 所以把间隔调成 0（每次都发）不会让这个字典无限增长。
_last_sent = {}
_throttle_lock = threading.Lock()


def _min_interval():
    """最小发送间隔（秒）；配置非法或为负按 600 处理"""
    try:
        return max(0, int(config.PRERENDER_ALERT_MIN_INTERVAL or 0))
    except (TypeError, ValueError):
        return 600


def _throttled(task_id):
    """True = 本任务处于节流窗口内，应当跳过

    在发送**之前**记账：否则 webhook 本身不可用时每次都发，节流形同虚设。
    """
    interval = _min_interval()
    if interval <= 0:
        return False
    now = time.monotonic()
    with _throttle_lock:
        # 顺手摘掉早已出窗的条目：任务被删掉后 key 不会自己消失，长期运行只会越攒越多
        for stale in [k for k, t in _last_sent.items() if now - t >= interval]:
            _last_sent.pop(stale, None)
        last = _last_sent.get(task_id)
        if last is not None and now - last < interval:
            return True
        _last_sent[task_id] = now
    return False


def _instance_id():
    """实例标识：多实例部署下要能看出是哪台机器发出的告警"""
    try:
        return f'{socket.gethostname()}:{os.getpid()}'
    except Exception:
        return 'unknown'


def _occurred_at():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
        '+00:00', 'Z')


def build_payload(task, result):
    """告警 JSON 体；抽成独立函数便于测试与复用"""
    return {
        'source': 'einkviews',
        'event': 'prerender_failure',
        'task_id': task['id'],
        'task_name': task['name'],
        'plugin': task['plugin_name'],
        'route': task['route_path'],
        'status': result.get('status'),
        'error': result.get('error') or '',
        'elapsed_ms': result.get('elapsed_ms'),
        'occurred_at': _occurred_at(),
        'instance': _instance_id(),
    }


async def notify_failure(task, result):
    """任务失败 / 路由失效时 POST 一条告警；未配置或处于节流窗口则直接返回"""
    url = str(getattr(config, 'PRERENDER_ALERT_WEBHOOK', '') or '').strip()
    if not url:
        return
    try:
        task_id = task['id']
    except (KeyError, IndexError, TypeError):
        return
    if _throttled(task_id):
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=build_payload(task, result))
    except Exception:
        plog.exception('预渲染失败告警发送失败')