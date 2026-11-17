"""Open-Meteo 取数：城市解析 + 实况/逐日预报，产出视图可直接消费的结构。

只做数据（网络与格式化），不碰画布。Open-Meteo 免密钥；`timezone=auto`
让返回的时间字符串就是**当地时区**的本地时间，视图直接展示、无需换算。

视图走 `fetch_weather`（异步），JSON 路由走 `fetch_weather_sync`（同步），
两者共用同一份 URL 构造与解析函数，保证两条链路的字段完全一致。
"""
import datetime
from urllib.parse import urlencode

import httpx

from modules.errors.errors import ParamError

from .wmo_codes import describe, wind_direction

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
DEFAULT_FORECAST_HOST = 'api.open-meteo.com'
TIMEOUT = 10


def forecast_url_base(host=None):
    """预报端点基址。个别网络只放行镜像实例域名，用 host 参数切换。"""
    return f'https://{(host or DEFAULT_FORECAST_HOST).strip()}/v1/forecast'

_CURRENT_FIELDS = ('temperature_2m,relative_humidity_2m,apparent_temperature,is_day,'
                   'precipitation,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure')
_DAILY_FIELDS = ('weather_code,temperature_2m_max,temperature_2m_min,'
                 'sunrise,sunset,precipitation_probability_max')

_WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _weekday_cn(date_str):
    try:
        return _WEEKDAYS[datetime.date.fromisoformat(date_str).weekday()]
    except (TypeError, ValueError):
        return ''


def _clock(iso_str):
    """'2026-11-13T06:48' → '06:48'"""
    try:
        return str(iso_str).split('T', 1)[1][:5]
    except IndexError:
        return ''


def resolve_location(city, lat, lon):
    """坐标参数优先；否则用城市名走地理编码。返回 (name, lat, lon)。"""
    if lat is not None and lon is not None and str(lat).strip() and str(lon).strip():
        return (city or '').strip() or f'{_as_float(lat, 0):.2f},{_as_float(lon, 0):.2f}', \
            _as_float(lat, 0.0), _as_float(lon, 0.0)
    name = (city or '').strip()
    if not name:
        raise ParamError('缺少参数: 请提供 city 或 lat/lon')
    url = f'{GEOCODE_URL}?{urlencode({"name": name, "count": 1, "language": "zh", "format": "json"})}'
    with httpx.Client(timeout=TIMEOUT) as client:
        payload = _get_json(client, url)
    results = payload.get('results') or []
    if not results:
        raise ParamError(f'无法找到城市: {name}')
    hit = results[0]
    label = hit.get('name') or name
    admin = hit.get('admin1') or ''
    if admin and admin not in label:
        label = f'{label}·{admin}'
    return label, _as_float(hit.get('latitude'), 0.0), _as_float(hit.get('longitude'), 0.0)


def build_forecast_url(lat, lon, days, host=None):
    query = {
        'latitude': lat,
        'longitude': lon,
        'current': _CURRENT_FIELDS,
        'daily': _DAILY_FIELDS,
        'timezone': 'auto',
        'forecast_days': max(1, min(_as_int(days, 3), 7)),
    }
    return f'{forecast_url_base(host)}?{urlencode(query)}'


def _get_json(client, url):
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise ParamError(f'天气数据获取失败: {exc}')


def parse_forecast(payload, name, lat, lon):
    """把 Open-Meteo 响应整理成视图直接消费的结构"""
    current_raw = payload.get('current') or {}
    code = _as_int(current_raw.get('weather_code'), 999)
    is_day = bool(current_raw.get('is_day', 1))
    condition, icon = describe(code, is_day)

    current = {
        'time': current_raw.get('time', ''),
        'temp': _as_float(current_raw.get('temperature_2m'), 0.0),
        'feels': _as_float(current_raw.get('apparent_temperature'), 0.0),
        'humidity': _as_int(current_raw.get('relative_humidity_2m'), 0),
        'wind_speed': _as_float(current_raw.get('wind_speed_10m'), 0.0),
        'wind_dir': wind_direction(current_raw.get('wind_direction_10m')),
        'pressure': _as_int(current_raw.get('surface_pressure'), 0),
        'precip': _as_float(current_raw.get('precipitation'), 0.0),
        'is_day': is_day,
        'code': code,
        'condition': condition,
        'icon': icon,
    }

    daily_raw = payload.get('daily') or {}
    dates = daily_raw.get('time') or []
    codes = daily_raw.get('weather_code') or []
    tmaxs = daily_raw.get('temperature_2m_max') or []
    tmins = daily_raw.get('temperature_2m_min') or []
    sunrises = daily_raw.get('sunrise') or []
    sunsets = daily_raw.get('sunset') or []
    probs = daily_raw.get('precipitation_probability_max') or []

    daily = []
    for i, date_str in enumerate(dates):
        d_code = _as_int(codes[i] if i < len(codes) else 999, 999)
        d_cond, d_icon = describe(d_code)
        daily.append({
            'date': date_str,
            'weekday': _weekday_cn(date_str),
            'code': d_code,
            'condition': d_cond,
            'icon': d_icon,
            'tmax': _as_float(tmaxs[i] if i < len(tmaxs) else None, 0.0),
            'tmin': _as_float(tmins[i] if i < len(tmins) else None, 0.0),
            'sunrise': _clock(sunrises[i]) if i < len(sunrises) else '',
            'sunset': _clock(sunsets[i]) if i < len(sunsets) else '',
            'precip_prob': _as_int(probs[i], 0) if i < len(probs) and probs[i] is not None else 0,
        })

    return {
        'location': {'name': name, 'lat': lat, 'lon': lon,
                     'timezone': payload.get('timezone', '')},
        'current': current,
        'daily': daily,
    }


async def fetch_weather(city=None, lat=None, lon=None, days=3, host=None, **_ignored):
    name, lat_v, lon_v = resolve_location(city, lat, lon)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.get(build_forecast_url(lat_v, lon_v, days, host))
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ParamError(f'天气数据获取失败: {exc}')
    return parse_forecast(payload, name, lat_v, lon_v)


def fetch_weather_sync(city=None, lat=None, lon=None, days=3, host=None, **_ignored):
    name, lat_v, lon_v = resolve_location(city, lat, lon)
    with httpx.Client(timeout=TIMEOUT) as client:
        payload = _get_json(client, build_forecast_url(lat_v, lon_v, days, host))
    return parse_forecast(payload, name, lat_v, lon_v)
