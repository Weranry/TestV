"""`/openmeteo/json/weatherjson`：实况 + 逐日预报的结构化输出。"""
from ..lib.fetcher import fetch_weather_sync


def to_json(**kwargs):
    return fetch_weather_sync(**kwargs)
