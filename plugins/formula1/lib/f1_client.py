"""Jolpica F1 取数：赛季赛历、站次选取与进程内 TTL 缓存。

数据源是公开的 Jolpica F1 API（`https://api.jolpi.ca/ergast/f1/`，Ergast 兼容接口，
无需 API key）。取一次整个赛季的赛历即可：一个响应里就带着全部分站的日期、地点与各节
练习/排位/冲刺时间，再在本地选出目标站次，比多打一次 `/next` 端点更省配额。

网络失败按「拿不到数据」抛 ParamError，让请求明确报 400 而不是静默出一张空图；
缓存是模块级字典，热重载清掉 `sys.modules` 后本模块重新导入、缓存自然重建。
"""
import datetime
import threading
import time

import httpx

from modules.errors.errors import NotFoundError, ParamError
from modules.utils.timezone import convert_utc_to_local, now_in_timezone

_BASE_URL = 'https://api.jolpi.ca/ergast/f1'
_USER_AGENT = 'eInkViews-formula1-plugin'
_TIMEOUT_SECONDS = 15.0

_CACHE_TTL_SECONDS = 600
_CACHE_MAX_ENTRIES = 16

# 赛程各节的展示顺序与中文标签
SESSIONS = (
    ('FirstPractice', '练习赛 1'),
    ('SecondPractice', '练习赛 2'),
    ('ThirdPractice', '练习赛 3'),
    ('SprintQualifying', '冲刺排位'),
    ('Sprint', '冲刺赛'),
    ('Qualifying', '排位赛'),
)
_SPRINT_KEYS = ('Sprint', 'SprintQualifying')

# 按插入顺序淘汰最旧的条目（FIFO，命中时不重排）
_cache = {}
_cache_lock = threading.Lock()


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.monotonic():
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key, value):
    with _cache_lock:
        _cache[key] = (value, time.monotonic() + _CACHE_TTL_SECONDS)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(node):
    """赛程节点（`{'date': '2026-10-25', 'time': '20:00:00Z'}`）→ aware UTC datetime"""
    if not isinstance(node, dict):
        return None
    date_text = node.get('date')
    if not date_text:
        return None
    text = f"{date_text}T{node.get('time') or '00:00:00Z'}"
    if text[-1] in ('Z', 'z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_local(moment, tz):
    """UTC 时刻 → 插件时区下的 naive 本地时间（tz 为空时按 UTC 墙钟，与框架口径一致）"""
    if moment is None:
        return None
    return convert_utc_to_local(moment, tz).replace(tzinfo=None)


def _local_now(tz):
    """当前本地时间，统一成 naive（`now_in_timezone` 在 ZoneInfo 下返回 aware）"""
    now = now_in_timezone(tz)
    if isinstance(now, datetime.datetime) and now.tzinfo is not None:
        return now.replace(tzinfo=None)
    return now


async def _season_races(season):
    """整个赛季的原始赛程列表。`season` 为空或 'current' 时取当前赛季。"""
    key = season or 'current'
    cached = _cache_get(key)
    if cached is not None:
        return cached

    url = f'{_BASE_URL}/{key}.json'
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params={'limit': 100})
    except httpx.HTTPError as exc:
        # httpx 超时异常的 str() 可能是空串，带上类型名才看得出是超时还是连不上
        raise ParamError(f"F1 赛历获取失败: {type(exc).__name__}: {str(exc)}")

    if resp.status_code == 404:
        raise NotFoundError(f"F1 赛季 {key} 不存在")
    if resp.status_code != 200:
        raise ParamError(f"F1 赛历获取失败: HTTP {resp.status_code}")

    try:
        races = (((resp.json().get('MRData') or {}).get('RaceTable') or {}).get('Races')) or []
    except ValueError as exc:
        raise ParamError(f"F1 赛历解析失败: {exc}")
    if not isinstance(races, list):
        races = []

    _cache_put(key, races)
    return races


def _select_race(races, round_ref):
    """按 `next` / `last` / 站号从赛程里选出目标站次"""
    ref = str(round_ref or 'next').strip().lower()
    if ref in ('', 'next'):
        now = datetime.datetime.now(datetime.timezone.utc)
        for race in races:
            moment = _parse_utc(race)
            if moment is not None and moment >= now:
                return race
        # 赛季已结束：退化为最后一站，至少还能看到一场比赛的完整信息
        return races[-1]
    if ref == 'last':
        # 已结束的最后一站，而不是赛历上的最后一站（赛季进行中时后者还是未来）
        now = datetime.datetime.now(datetime.timezone.utc)
        past = [race for race in races
                if (_parse_utc(race) or datetime.datetime.max.replace(
                    tzinfo=datetime.timezone.utc)) <= now]
        return past[-1] if past else races[0]
    try:
        index = int(ref)
    except (TypeError, ValueError):
        raise ParamError('round 只能是 next / last / 站号（整数）')
    if index < 1 or index > len(races):
        raise ParamError(f'站号 {index} 超出范围（1-{len(races)}）')
    return races[index - 1]


def _normalize(race, total_rounds, tz):
    circuit = race.get('Circuit') or {}
    location = circuit.get('Location') or {}
    sessions = []
    for key, label in SESSIONS:
        moment = _to_local(_parse_utc(race.get(key)), tz)
        if moment is not None:
            sessions.append({'key': key, 'label': label, 'time': moment})
    race_time = _to_local(_parse_utc(race), tz)
    days_until = None
    if race_time is not None:
        days_until = (race_time.date() - _local_now(tz).date()).days
    try:
        round_no = int(race.get('round') or 0)
    except (TypeError, ValueError):
        round_no = 0
    return {
        'season': str(race.get('season') or ''),
        'round': round_no,
        'total_rounds': total_rounds,
        'race_name': race.get('raceName') or '',
        'circuit_id': circuit.get('circuitId') or '',
        'circuit_name': circuit.get('circuitName') or '',
        'locality': location.get('locality') or '',
        'country': location.get('country') or '',
        'lat': _as_float(location.get('lat')),
        'lon': _as_float(location.get('long')),
        'race_time': race_time,
        'sessions': sessions,
        'is_sprint': any(item['key'] in _SPRINT_KEYS for item in sessions),
        'days_until': days_until,
    }


async def fetch_race(round_ref='next', season=None, tz=None):
    """取目标站次的规范化信息（`round_ref` 见 plugin_config.DEFAULT_ARGS 注释）"""
    races = await _season_races(season)
    if not races:
        raise NotFoundError('F1 赛历为空')
    return _normalize(_select_race(races, round_ref), len(races), tz)
