"""设备的「下次什么时候回来」计算——**纯函数**，不落库、不起 worker、不主动推送。

这是整套设备功能里最容易走偏的一处，所以把边界写死：

- **计时器跑在设备上**。后端只回答「你现在该等多少秒」「到点该请求哪个 URL」，
  设备自己睡、自己醒、自己来请求。服务端**没有**排期任务表、没有到期扫描、没有 leader 锁，
  也没有任何「到点主动推给设备」的通道。
- 因此这里的函数都是**给当前时间 + 设备配置，算出相对秒数**，两次调用之间不保存任何状态。
  想增加「多视图按时段切换」时也走同一条路：换一个纯函数，而不是加一张任务表。
- 返回值**永不**是 None 或负数：固件拿到空值会把深睡时长算成 0，变成忙轮询把后端打爆。
"""
import datetime
import random

import config
from modules.prerender.scheduler import _next_cron_time, parse_cron, parse_daily_times
from modules.utils.timezone import convert_utc_to_local, now_in_timezone

# 排期配置读不出来 / 非法时的兜底间隔（秒）。给一个明确的中等值，而不是 0 或 None：
# 设备宁可十分钟后再问一次，也不能因为配置写坏就卡死或狂刷。
FALLBACK_INTERVAL_SECONDS = 600


def _clamp(seconds):
    """钳制到下发的允许区间。下限防「配置成 0 秒」变成忙轮询，上限强制设备定期回连
    ——daily / cron 这类墙上时间排期靠设备本地计时必然漂移，回连越勤，漂移越封得住。
    """
    try:
        low = int(getattr(config, 'DEVICE_MIN_SLEEP_SECONDS', 60))
        high = int(getattr(config, 'DEVICE_MAX_SLEEP_SECONDS', 21600))
    except (TypeError, ValueError):
        return FALLBACK_INTERVAL_SECONDS
    if high < low:
        high = low
    try:
        return max(low, min(int(seconds), high))
    except (TypeError, ValueError):
        return low


def _tz_of(device_row):
    """设备自己的时区（空 = 站点默认）。允许写偏移小时数，也允许写 'Asia/Shanghai'"""
    return (device_row or {}).get('timezone') or None


def _interval_seconds(device_row):
    try:
        value = int((device_row or {}).get('interval_seconds') or 0)
    except (TypeError, ValueError):
        return FALLBACK_INTERVAL_SECONDS
    return value if value > 0 else FALLBACK_INTERVAL_SECONDS


def _number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _adaptive_seconds(device_row, seconds):
    """按设备最近一次上报的电量 / 信号延长间隔。

    - 电量 <= 0 表示设备没上报，不能当成「0 mV 快没电了」；
    - RSSI 合法值是负数，0 同样表示没上报；
    - 两个条件同时命中取较大系数，结果仍走 _clamp，不会突破上下限。
    """
    if seconds <= 0:
        return seconds
    factor = 1.0
    battery = _number((device_row or {}).get('battery_mv'))
    if battery > 0:
        threshold = _number(getattr(config, 'DEVICE_LOW_BATTERY_MV', 0))
        if threshold > 0 and battery <= threshold:
            try:
                factor = max(factor, float(getattr(config, 'DEVICE_LOW_BATTERY_SLEEP_FACTOR', 1.0)))
            except (TypeError, ValueError):
                pass
    rssi = _number((device_row or {}).get('rssi'))
    if rssi < 0:
        threshold = _number(getattr(config, 'DEVICE_WEAK_RSSI_DBM', 0))
        if threshold < 0 and rssi <= threshold:
            try:
                factor = max(factor, float(getattr(config, 'DEVICE_WEAK_RSSI_SLEEP_FACTOR', 1.0)))
            except (TypeError, ValueError):
                pass
    if factor <= 1.0:
        return _clamp(seconds)
    return _clamp(int(round(seconds * factor)))


def jitter_sleep_seconds(seconds):
    """在服务端算出的间隔上加 ±N% 抖动，打散整点唤醒的尖峰。

    只用于真正「睡多久」的下发值；`0`（立即取图）和配错时的兜底值不抖动。
    抖动后仍按上下限钳制，避免把 60 秒抖到 57 秒。
    """
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return FALLBACK_INTERVAL_SECONDS
    if value <= 0:
        return 0
    try:
        pct = float(getattr(config, 'DEVICE_SLEEP_JITTER_PCT', 0) or 0)
    except (TypeError, ValueError):
        pct = 0.0
    if pct <= 0:
        return _clamp(value)
    pct = min(pct, 50.0)
    factor = random.uniform(1 - pct / 100.0, 1 + pct / 100.0)
    return _clamp(int(round(value * factor)))


def _next_wall_time(device_row, kind, now):
    """下一个 **本地墙上时刻**（naive datetime）；配置非法返回 None"""
    if kind == 'daily':
        times = parse_daily_times((device_row or {}).get('daily_times'))
        if not times:
            return None
        candidates = []
        for hh, mm in times:
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            # 今天的这个点已经过了就顺延到明天；多个时刻取最早的那个。
            # 跨零点天然正确：cand + 1 天 落在明天，差值为正数。
            candidates.append(cand if cand > now else cand + datetime.timedelta(days=1))
        return min(candidates)
    cron = parse_cron((device_row or {}).get('cron_expr') or '')
    if cron is None:
        return None
    return _next_cron_time(cron, now)


def compute_sleep_seconds(device_row, now_local=None):
    """设备这次该睡多少秒（相对秒数）。

    - `last_seen_at` 为空 = 首次回连（刚配对完 / 刚重置令牌）→ 返回 `0`：立刻取第一张图。
      这是唯一可能小于下限的返回值，它是个「现在就取」的信号而不是睡眠时长，
      因此**不参与钳制**；设备侧看到 0 就是马上请求。
    - `interval` → 直接用设备配的间隔秒数；
    - `daily` / `cron` → 下一个墙上时刻 − 现在；
    - 配置非法 → 回退 `FALLBACK_INTERVAL_SECONDS`；
    - 其余一律钳制到 `DEVICE_MIN_SLEEP_SECONDS .. DEVICE_MAX_SLEEP_SECONDS`。

    `now_local` 只在测试里传（本地墙上时间，naive），不传就按设备时区现取。
    """
    if not device_row:
        return FALLBACK_INTERVAL_SECONDS
    if not str(device_row.get('last_seen_at') or '').strip():
        return 0

    kind = str(device_row.get('schedule_type') or 'interval').lower()
    if kind == 'interval':
        return _adaptive_seconds(device_row, _interval_seconds(device_row))
    if kind in ('daily', 'cron'):
        now = now_local or now_in_timezone(_tz_of(device_row))
        target = _next_wall_time(device_row, kind, now)
        if target is None:
            return _adaptive_seconds(device_row, FALLBACK_INTERVAL_SECONDS)
        delta = int((target - now).total_seconds())
        # 算出来的时刻不该已过去；真出现了（时钟被回拨等）就退到兜底间隔，绝不返回负数
        return _adaptive_seconds(device_row, delta if delta > 0 else FALLBACK_INTERVAL_SECONDS)
    return _adaptive_seconds(device_row, FALLBACK_INTERVAL_SECONDS)


def compute_next_refresh_at(device_row):
    """下次回连时刻的估算（UTC ISO 字符串）；从未上线返回 `''`。

    设备是「取完图 → 按当次下发的秒数睡下去」，所以下一次 ≈ 上次回连时刻 + 当次会下发的
    睡眠秒数。daily / cron 用**上次回连那一刻**去算，才对得上设备当时真正睡下的时长；
    用「现在」算会把已经睡过去的那一段重复计进去，得到的时刻总是偏晚。
    """
    last_text = str((device_row or {}).get('last_seen_at') or '').strip()
    if not last_text:
        return ''
    normalized = last_text.replace(' ', 'T')
    if normalized[-1:] in ('Z', 'z'):
        normalized = normalized[:-1] + '+00:00'
    try:
        last_utc = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return ''
    if last_utc.tzinfo is None:
        last_utc = last_utc.replace(tzinfo=datetime.timezone.utc)
    last_local = convert_utc_to_local(last_utc, _tz_of(device_row))
    if getattr(last_local, 'tzinfo', None) is not None:
        last_local = last_local.replace(tzinfo=None)
    seconds = compute_sleep_seconds(device_row, now_local=last_local)
    if seconds <= 0:
        seconds = _interval_seconds(device_row)
    nxt = last_utc.astimezone(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    return nxt.isoformat().replace('+00:00', 'Z')


def build_next_url(request, device_row=None):
    """设备下次该请求的**绝对地址**。

    默认指向 `/device/image`：设备只要「到点 GET 这个地址」就够，不必自己拼参数、也不必
    知道渲染项有几条。以后要按设备切到别的取图入口（例如锁定某个渲染项），改的也只是这里。
    """
    base = str(getattr(request, 'base_url', '') or '').rstrip('/')
    return base + '/device/image'
