"""赛道轮廓与资料：优先读插件内打包的 GeoJSON，网络仅作兜底，并能为新增赛道自动发现。

轮廓数据来自公开仓库 `bacinger/f1-circuits`（LineString，坐标为 [经度, 纬度]，
`properties` 里带赛道长度 `length`、所在城市 `Location`、赛道名 `Name`、启用年份 `opened`）。
这些文件**已随插件打包**在 `plugins/formula1/assets/tracks/<文件名>.geojson`：一个赛道轮廓
约 3~5 KB，23 条合计不到 100 KB，本地读取零延迟，也不再受 GitHub 连通性影响。

文件名是「国家码-首次办赛年份」（如 `it-1922` = 蒙扎），与 Ergast 的 `circuitId` 没有直接
对应关系，因此这里维护一张 `circuitId → 文件名` 的映射表。

**遇到映射表里没有的新赛道**（赛历新增分站）时，自动按以下顺序兜底：

1. **按年份探测**：新赛道在仓库里的文件名是 `国家码-首办年份`，而首次办赛年份就是它进入
   F1 的年份，因此先试 `es-2027`、`es-2026`… 这类文件名，命中即用（直接取文件，不用目录索引）；
2. **目录索引兜底**：按国家码筛出仓库全部候选文件（jsDelivr 数据接口，进程内缓存 7 天），
   用于找回「不是首次加入 F1、只是没进本地映射表」的老赛道；
3. 无论哪条路径，都要用「城市名 + 赛道名」与 Ergast 数据打分，分数够高才认，防止把同国的
   其它赛道错认成新赛道；
4. 命中的 `circuitId → 文件名` 记在进程内，后续请求不再重复探测。

仍然失败（网络不可达、国家码未知、仓库里确实还没有这条赛道）就返回 None：地图区留空、
长度圈数省略，其余信息照常显示——不臆造形状，也不让装饰性内容把整张图连坐成 400。
失败结果也会短暂记住（1 小时），避免每张图都为一个取不到的赛道等超时。
"""
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from modules.utils import plog

_TRACK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'tracks'))
_USER_AGENT = 'eInkViews-formula1-plugin'
_TIMEOUT_SECONDS = 15.0
# 自动发现是「锦上添花」，超时给短一些：取不到就先空着，别把一张图拖十几秒
_DISCOVERY_TIMEOUT_SECONDS = 5.0
# 新赛道进入 F1 的年份不会早于当前赛季太多，往前探 6 年足够覆盖首办情形
_YEAR_PROBE_SPAN = 6
# 打分门槛：低于这个分数说明城市与赛道名都对不上，宁可不用
_MIN_MATCH_SCORE = 2

# 网络兜底的两个镜像：jsDelivr 在国内通常可达，GitHub 原始地址作为最后手段
_REMOTE_SOURCES = (
    'https://cdn.jsdelivr.net/gh/bacinger/f1-circuits@master/circuits/{}.geojson',
    'https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/{}.geojson',
)
# 自动发现只走第一个镜像：探测要试好几年，多个源叠在一起会把一次出图拖成几十秒
_DISCOVERY_SOURCES = _REMOTE_SOURCES[:1]
# 目录索引，用于新赛道的自动发现
_INDEX_URL = 'https://data.jsdelivr.com/v1/packages/gh/bacinger/f1-circuits@master?structure=flat'

# 轮廓数据几乎不变，TTL 给足一天；目录索引更稳定，缓存一周
_CACHE_TTL_SECONDS = 24 * 3600
_INDEX_TTL_SECONDS = 7 * 24 * 3600
_NEGATIVE_TTL_SECONDS = 3600
_CACHE_MAX_ENTRIES = 64

# Ergast circuitId → f1-circuits 文件名（当前赛历在用的赛道）
CIRCUIT_FILES = {
    'albert_park': 'au-1953',
    'shanghai': 'cn-2004',
    'suzuka': 'jp-1962',
    'miami': 'us-2022',
    'villeneuve': 'ca-1978',
    'monaco': 'mc-1929',
    'catalunya': 'es-1991',
    'red_bull_ring': 'at-1969',
    'silverstone': 'gb-1948',
    'spa': 'be-1925',
    'hungaroring': 'hu-1986',
    'zandvoort': 'nl-1948',
    'monza': 'it-1922',
    'madring': 'es-2026',
    'baku': 'az-2016',
    'sepang': 'my-1999',
    'marina_bay': 'sg-2008',
    'americas': 'us-2012',
    'rodriguez': 'mx-1962',
    'interlagos': 'br-1940',
    'vegas': 'us-2023',
    'losail': 'qa-2004',
    'yas_marina': 'ae-2009',
}

# Ergast 的 `Location.country` → 仓库文件名里的国家码（自动发现时用来筛候选）
COUNTRY_CODES = {
    'Argentina': 'ar',
    'Australia': 'au',
    'Austria': 'at',
    'Azerbaijan': 'az',
    'Bahrain': 'bh',
    'Belgium': 'be',
    'Brazil': 'br',
    'Canada': 'ca',
    'China': 'cn',
    'France': 'fr',
    'Germany': 'de',
    'Hungary': 'hu',
    'India': 'in',
    'Italy': 'it',
    'Japan': 'jp',
    'Korea': 'kr',
    'Malaysia': 'my',
    'Mexico': 'mx',
    'Monaco': 'mc',
    'Netherlands': 'nl',
    'Portugal': 'pt',
    'Qatar': 'qa',
    'Russia': 'ru',
    'Saudi Arabia': 'sa',
    'Singapore': 'sg',
    'South Africa': 'za',
    'Spain': 'es',
    'Sweden': 'se',
    'Switzerland': 'ch',
    'Turkey': 'tr',
    'UAE': 'ae',
    'UK': 'gb',
    'USA': 'us',
    'Vietnam': 'vn',
}

# 正赛里程的官方口径：常规 305 km，摩纳哥特例 260 km
_DEFAULT_RACE_DISTANCE_KM = 305.0
_MONACO_RACE_DISTANCE_KM = 260.0

_cache = {}
_resolved_files = {}
_misses = {}
_cache_lock = threading.Lock()

_index_files = None
_index_expires_at = 0.0
_index_lock = threading.Lock()


def _cache_get(circuit_id):
    with _cache_lock:
        entry = _cache.get(circuit_id)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.monotonic():
            _cache.pop(circuit_id, None)
            return None
        return value


def _cache_put(circuit_id, value):
    with _cache_lock:
        _cache[circuit_id] = (value, time.monotonic() + _CACHE_TTL_SECONDS)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))


def _miss_get(circuit_id):
    """刚失败过的赛道短时间内不再重试，避免每张图都卡在同一个超时上"""
    with _cache_lock:
        expires_at = _misses.get(circuit_id)
        if expires_at is None or expires_at <= time.monotonic():
            _misses.pop(circuit_id, None)
            return False
        return True


def _miss_put(circuit_id):
    with _cache_lock:
        _misses[circuit_id] = time.monotonic() + _NEGATIVE_TTL_SECONDS


def _parse_length_m(value):
    try:
        length = int(float(value))
    except (TypeError, ValueError):
        return None
    return length if length > 0 else None


def _parse_geojson(payload):
    """GeoJSON → `{'points', 'length_m', 'location', 'name', 'opened'}`；结构不对返回 None"""
    try:
        feature = (payload.get('features') or [{}])[0]
        geometry = feature.get('geometry') or {}
        coords = geometry.get('coordinates') or []
        # MultiLineString 只取最长的一段，避免把互不相连的路段接成乱线
        if geometry.get('type') == 'MultiLineString' and coords:
            coords = max(coords, key=len)
        points = [
            (float(point[0]), float(point[1]))
            for point in coords
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        props = feature.get('properties') or {}
        length_m = _parse_length_m(props.get('length'))
        opened = props.get('opened')
        opened = int(opened) if isinstance(opened, (int, float)) else None
        location = str(props.get('Location') or '')
        name = str(props.get('Name') or '')
    except (ValueError, TypeError, AttributeError):
        return None
    if len(points) < 3:
        return None
    return {
        'points': points,
        'length_m': length_m,
        'location': location,
        'name': name,
        'opened': opened,
    }


def _load_local(filename):
    """读插件内打包的轮廓文件；不存在或损坏返回 None"""
    path = os.path.join(_TRACK_DIR, filename + '.geojson')
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return _parse_geojson(json.load(handle))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        plog.warn(f'F1 本地赛道轮廓读取失败: {path} {exc}')
        return None


async def _fetch_remote_status(filename, timeout=_TIMEOUT_SECONDS, sources=_REMOTE_SOURCES):
    """取一条轮廓，返回 `(track, status)`；status 为 'ok' / 'notfound' / 'error'

    区分 404 与网络错误：探测新赛道时，404 说明「这个年份没有」，可以继续试下一年；
    网络错误说明外网不通，继续试只会白等一串超时。
    """
    had_error = False
    for template in sources:
        url = template.format(filename)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                headers={'User-Agent': _USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            had_error = True
            plog.info(f'F1 赛道轮廓取数失败({type(exc).__name__})，换下一个源: {url}')
            continue
        if resp.status_code == 404:
            continue
        if resp.status_code != 200:
            had_error = True
            plog.info(f'F1 赛道轮廓取数失败(HTTP {resp.status_code}): {url}')
            continue
        try:
            track = _parse_geojson(resp.json())
        except ValueError as exc:
            plog.info(f'F1 赛道轮廓解析失败: {url} {exc}')
            continue
        if track:
            return track, 'ok'
    return None, 'error' if had_error else 'notfound'


async def _fetch_remote(filename, timeout=_TIMEOUT_SECONDS, sources=_REMOTE_SOURCES):
    return (await _fetch_remote_status(filename, timeout, sources))[0]


async def _remote_file_list():
    """仓库里的轮廓文件清单（不含扩展名）；失败返回 None"""
    global _index_files, _index_expires_at
    with _index_lock:
        if _index_files is not None and _index_expires_at > time.monotonic():
            return _index_files
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_DISCOVERY_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(_INDEX_URL)
        if resp.status_code != 200:
            return None
        files = [
            entry['name'].rsplit('/', 1)[-1][:-len('.geojson')]
            for entry in resp.json().get('files', [])
            if entry.get('name', '').startswith('/circuits/')
            and entry['name'].endswith('.geojson')
        ]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        plog.info(f'F1 赛道索引取数失败({type(exc).__name__}): {exc}')
        return None
    if not files:
        return None
    with _index_lock:
        _index_files = files
        _index_expires_at = time.monotonic() + _INDEX_TTL_SECONDS
    return files


_GENERIC_WORDS = {
    'circuit', 'circuito', 'autodromo', 'autodrome', 'international', 'grand', 'prix',
    'race', 'track', 'street', 'park', 'de', 'del', 'di', 'the', 'of',
}


def _words(text):
    """切成小写词集合，去掉 circuit / international 这类哪个赛道都有的通用词"""
    return {
        word for word in re.split(r'[^0-9a-z\u00c0-\u024f]+', str(text).lower())
        if word and word not in _GENERIC_WORDS
    }


def _match_score(track, locality, circuit_name):
    """候选轮廓与 Ergast 数据的相似度：城市命中优先，其次赛道名重合度"""
    score = 0
    if locality and track['location'] and track['location'].lower() == locality.lower():
        score += 4
    score += 2 * len(_words(locality) & _words(track['location']))
    score += len(_words(circuit_name) & _words(track['name']))
    return score


async def _probe_years(code, circuit_id, circuit_name, locality):
    """按「国家码-首办年份」探测新赛道；文件名里的年份就是它首次办 F1 的年份"""
    start = datetime.now(timezone.utc).year + 1
    for year in range(start, start - _YEAR_PROBE_SPAN - 1, -1):
        filename = f'{code}-{year}'
        track = _load_local(filename)
        if track is None:
            track, status = await _fetch_remote_status(
                filename, timeout=_DISCOVERY_TIMEOUT_SECONDS, sources=_DISCOVERY_SOURCES)
            if status == 'error':
                # 外网不通，再试下一年只是重复等超时
                return None, None
        if track is None:
            continue
        if _match_score(track, locality, circuit_name) >= _MIN_MATCH_SCORE:
            return filename, track
        # 年份文件存在但对不上（比如同国的旧赛道），继续往前探
    return None, None


async def _discover(circuit_id, country, circuit_name, locality):
    """映射表里没有的新赛道：先按年份探测，再靠目录索引找老赛道

    两条路径都要过相似度门槛，返回 `(filename, track)`；探测不到返回 `(None, None)`。
    """
    code = COUNTRY_CODES.get(country or '')
    if not code:
        return None, None

    filename, track = await _probe_years(code, circuit_id, circuit_name, locality)
    if filename:
        plog.info(f'F1 新赛道按年份匹配: {circuit_id} → {filename}')
        return filename, track

    files = await _remote_file_list()
    if not files:
        return None, None

    # 已被静态表占用的文件跳过，免得把新赛道错认成同国的旧赛道
    used = set(CIRCUIT_FILES.values())
    candidates = [name for name in files if name.startswith(code + '-')]
    fresh = [name for name in candidates if name not in used]
    candidates = (fresh or candidates)[:4]

    best = (None, None, -1)
    for filename in candidates:
        track, status = await _fetch_remote_status(
            filename, timeout=_DISCOVERY_TIMEOUT_SECONDS, sources=_DISCOVERY_SOURCES)
        if status == 'error':
            break
        if track is None:
            continue
        score = _match_score(track, locality, circuit_name)
        if score > best[2]:
            best = (filename, track, score)
    if best[0] is None or best[2] < _MIN_MATCH_SCORE:
        return None, None

    plog.info(f'F1 新赛道按索引匹配: {circuit_id} → {best[0]}（相似度 {best[2]}）')
    return best[0], best[1]


async def fetch_track(circuit_id, country=None, circuit_name=None, locality=None):
    """→ `{'points': [(lon, lat), ...], 'length_m': int|None, ...}`；拿不到返回 None

    `country` / `circuit_name` / `locality` 来自 Ergast，只有新赛道自动发现时才会用到。
    """
    if not circuit_id:
        return None

    cached = _cache_get(circuit_id)
    if cached is not None:
        return cached
    if _miss_get(circuit_id):
        return None

    with _cache_lock:
        filename = CIRCUIT_FILES.get(circuit_id) or _resolved_files.get(circuit_id)

    track = None
    if filename:
        track = _load_local(filename)
        if track is None:
            track = await _fetch_remote(filename)
    else:
        filename, track = await _discover(circuit_id, country, circuit_name, locality)
        if filename:
            with _cache_lock:
                _resolved_files[circuit_id] = filename

    if track is None:
        _miss_put(circuit_id)
        return None

    _cache_put(circuit_id, track)
    return track


def project(points, box_width, box_height):
    """经纬度 → 画框内的像素坐标（等距圆柱投影，等比缩放后居中）。

    赛道尺度很小，用等距圆柱投影（经度乘 cos(平均纬度)）就足够，不需要墨卡托。
    纬度向北、像素 y 向下，所以 y 取反向。
    """
    lats = [point[1] for point in points]
    lons = [point[0] for point in points]
    lon_min, lat_max = min(lons), max(lats)
    cos_lat = math.cos(math.radians((min(lats) + lat_max) / 2))

    xs = [(lon - lon_min) * cos_lat for lon in lons]
    ys = [lat_max - lat for lat in lats]

    span_x = max(xs) or 1.0
    span_y = max(ys) or 1.0
    scale = min(box_width / span_x, box_height / span_y)
    offset_x = (box_width - span_x * scale) / 2
    offset_y = (box_height - span_y * scale) / 2

    return [
        (int(offset_x + x * scale), int(offset_y + y * scale))
        for x, y in zip(xs, ys)
    ]


def laps_for(circuit_id, length_m):
    """由赛道长度推正赛圈数（里程达标的最小圈数）；长度缺失返回 None"""
    if not length_m:
        return None
    target = _MONACO_RACE_DISTANCE_KM if circuit_id == 'monaco' else _DEFAULT_RACE_DISTANCE_KM
    return int(math.ceil(target / (length_m / 1000.0)))
