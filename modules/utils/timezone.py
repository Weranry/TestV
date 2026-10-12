import datetime

import config


def _default_offset():
    """DEFAULT_TIMEZONE_OFFSET 必须每次现取：管理面板改完会 importlib.reload(config)，
    导入期用 `from config import ...` 拿到的会是旧值。"""
    return getattr(config, 'DEFAULT_TIMEZONE_OFFSET', None)


def _resolve_timezone(param_offset=None):
    if param_offset is not None:
        try:
            return float(param_offset)
        except (ValueError, TypeError):
            pass
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(str(param_offset))
        except Exception:
            pass
    offset = _default_offset()
    if offset is not None:
        return float(offset)
    return None


def utc_now_iso():
    """当前 UTC 时间的 ISO 字符串（形如 2026-09-19T12:00:00Z），用于会话/日志时间戳"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


def get_timezone_offset(param_offset=None):
    tz = _resolve_timezone(param_offset)
    if tz is None:
        return None
    if isinstance(tz, datetime.tzinfo):
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        return tz.utcoffset(utc_now).total_seconds() / 3600
    return tz


def now_in_timezone(param_offset=None):
    tz = _resolve_timezone(param_offset)
    if tz is None:
        # 未配置时区时回落 naive UTC（去掉 tzinfo），与 get_timezone_offset() 的 None→0
        # 偏移一致：否则会退回服务器本地墙钟，让「按天统计的今天」与「UTC 排期」错位
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    if isinstance(tz, datetime.tzinfo):
        return datetime.datetime.now(tz)
    utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return utc_now + datetime.timedelta(hours=tz)


def convert_utc_to_local(dt_utc, param_offset=None):
    tz = _resolve_timezone(param_offset)
    if tz is None:
        return dt_utc
    if isinstance(tz, datetime.tzinfo):
        if hasattr(dt_utc, 'tzinfo') and dt_utc.tzinfo is not None:
            dt_utc = dt_utc.astimezone(datetime.timezone.utc)
        else:
            dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
        return dt_utc.astimezone(tz).replace(tzinfo=None)
    if hasattr(dt_utc, 'tzinfo') and dt_utc.tzinfo is not None:
        dt_utc = dt_utc.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt_utc + datetime.timedelta(hours=tz)


def utc_string_to_local(value, fmt='%Y-%m-%d %H:%M:%S', param_offset=None):
    """库里存的 UTC 时间字符串 → 本地时间字符串。

    兼容两种存量格式：`utc_now_iso()` 的 `...T...+00:00`，以及 SQLite 默认值
    `datetime('now')` 的 `YYYY-MM-DD HH:MM:SS`（无时区标记，按 UTC 解释）。
    解析失败时原样返回，不抛错。
    """
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    normalized = text.replace(' ', 'T')
    if normalized[-1] in ('Z', 'z'):
        normalized = normalized[:-1] + '+00:00'
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return convert_utc_to_local(dt, param_offset).strftime(fmt)


def fmt_duration(seconds, lang=None):
    """秒数 → 时长文案（启动信息、控制台概览与面板共用一份口径，避免三处各写一遍）

    文案走文案表，`lang=None` 时缺键回落中文——控制台打印用默认值即可，
    面板接口按请求语言传入（`lang_of(request)`），英文界面才不会露出中文「分钟」。
    """
    from modules.i18n.registry import t
    sec = max(int(seconds or 0), 0)
    if sec < 60:
        return t('duration.lt_minute', lang)
    m, h, d = sec // 60, sec // 3600, sec // 86400
    if d:
        return t('duration.dhm', lang, d=d, h=h % 24, m=m % 60)
    if h:
        return t('duration.hm', lang, h=h, m=m % 60)
    return t('duration.m', lang, m=m)