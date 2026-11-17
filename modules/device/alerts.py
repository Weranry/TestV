"""设备离线告警：设备超过配置时长没有回连时 POST 一份 JSON 到 webhook。

与预渲染失败告警（`modules/prerender/alerts.py`）同一套取向：通用 JSON 出口、
没配地址就不发、发送失败只打印堆栈、绝不影响别的后台任务。

去重不靠内存节流，而是落在 `devices.offline_alerted` 上：
- 扫描前用条件 UPDATE 抢占标记，抢到才发（多实例下也只有一个发得出去）；
- 设备任何一次回连（`touch_device`）都会把标记清零，所以「掉线 → 恢复 → 再掉线」
  会重新告警，而同一次连续离线只告一次。

扫描由 `lifecycle.start_flush_thread` 的 leader 分支周期调用（同步函数，跑在后台线程里，
不占事件循环）。
"""
import datetime

import config
from modules.utils import plog
from modules.utils.timezone import utc_now_iso


def _minutes():
    """离线判定阈值（分钟）；非法值按 0（关闭）处理"""
    try:
        return max(0, int(getattr(config, 'DEVICE_OFFLINE_ALERT_MINUTES', 0) or 0))
    except (TypeError, ValueError):
        return 0


def _threshold_iso(minutes):
    """当前时间往前推 minutes 分钟的 UTC ISO 字符串（与 `last_seen_at` 同格式）"""
    now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return now.isoformat().replace('+00:00', 'Z')


def build_payload(device, minutes):
    """告警 JSON 体；抽成独立函数便于测试与复用"""
    return {
        'source': 'einkviews',
        'event': 'device_offline',
        'device_id': device['id'],
        'device_name': device.get('name') or device.get('model') or '',
        'model': device.get('model') or '',
        'hw_uid': device.get('hw_uid') or '',
        'account_id': device.get('account_id'),
        'account_name': device.get('account_name') or '',
        'last_seen_at': device.get('last_seen_at') or '',
        'offline_minutes': minutes,
        'battery_mv': int(device.get('battery_mv') or 0),
        'rssi': int(device.get('rssi') or 0),
        'occurred_at': utc_now_iso(),
    }


def scan_offline_devices():
    """扫一遍离线设备并告警，返回本次发出的条数（测试与日志用）。

    `DEVICE_OFFLINE_ALERT_MINUTES <= 0` 或 `DEVICE_ALERT_WEBHOOK` 为空时直接返回：
    不查库、不发请求。
    """
    minutes = _minutes()
    url = str(getattr(config, 'DEVICE_ALERT_WEBHOOK', '') or '').strip()
    if minutes <= 0 or not url:
        return 0

    from modules.device import store
    try:
        rows = store.list_offline_devices(_threshold_iso(minutes))
    except Exception:
        plog.exception('离线设备扫描失败')
        return 0

    sent = 0
    for device in rows:
        if not store.mark_device_offline_alerted(device['id']):
            continue
        try:
            import httpx
            httpx.post(url, json=build_payload(device, minutes), timeout=5)
            sent += 1
        except Exception:
            # 发送失败保留标记：宁可丢一条告警，也不要 webhook 坏掉时每轮重试刷屏
            plog.exception(f'设备离线告警发送失败: device={device["id"]}')
    return sent
