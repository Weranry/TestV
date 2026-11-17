"""WMO 天气码 → 中文天气名 + weather-icon.ttf 码点。

重要：这份字体的 cmap 字形名（墨迹编号）与**实际形状不符**——逐个渲染核对后
确认：名为 150「阵雨」的字形其实是月亮（夜晴）、315-318「雪」是雨、真正的雪在
400/401/499、雾在 509/510。因此本表完全按字形实际形状映射，忽略 cmap 名。

月亮系（150-153 号位）是夜间变体，只在实况视图 is_day=0 时启用；
逐日预报没有昼夜标志，统一用白天字形。
"""

_SUN = 0xF101           # 太阳
_SUN_CLOUD = 0xF102     # 日+大云
_SUN_SMALL = 0xF103     # 日+小云
_CLOUD = 0xF105         # 阴云
_MOON = 0xF106          # 月
_MOON_CLOUD = 0xF107    # 月+云
_MOON_RAIN = 0xF108     # 月+云+雨
_MOON_BOLT = 0xF109     # 月+云+雷
_BOLT_RAIN = 0xF10A     # 云+雷+雨
_SHOWER = 0xF10B        # 日+云+雨（阵雨）
_SHOWER2 = 0xF10C       # 日+云+雨（强阵雨）
_RAIN = 0xF10D          # 云+疏雨
_STORM = 0xF10E         # 云+密雨+雷
_DRIZZLE = 0xF10F       # 云+毛毛雨
_RAIN_HEAVY = 0xF110    # 云+大雨
_RAIN_TORRENT = 0xF112  # 云+暴雨
_FREEZE = 0xF113        # 云+冻雨滴
_SNOW_L = 0xF120        # 云+疏雪晶
_SNOW_M = 0xF121        # 云+密雪晶
_SNOW_FLAKE = 0xF12D    # 单片大雪花
_FOG = 0xF135           # 云+雾线
_UNKNOWN = 0xF146       # N/A

# WMO 码 → (中文名, 白天字形, 夜间字形；None 表示无夜间变体)
_WMO = {
    0:  ('晴', _SUN, _MOON),
    1:  ('晴间多云', _SUN_SMALL, _MOON_CLOUD),
    2:  ('多云', _SUN_CLOUD, _MOON_CLOUD),
    3:  ('阴', _CLOUD, None),
    45: ('雾', _FOG, None),
    48: ('雾凇', _FOG, None),
    51: ('毛毛雨', _DRIZZLE, None),
    53: ('细雨', _DRIZZLE, None),
    55: ('毛毛雨', _DRIZZLE, None),
    56: ('冻雨', _FREEZE, None),
    57: ('冻雨', _FREEZE, None),
    61: ('小雨', _RAIN, None),
    63: ('中雨', _RAIN_HEAVY, None),
    65: ('大雨', _RAIN_TORRENT, None),
    66: ('冻雨', _FREEZE, None),
    67: ('冻雨', _FREEZE, None),
    71: ('小雪', _SNOW_L, None),
    73: ('中雪', _SNOW_M, None),
    75: ('大雪', _SNOW_FLAKE, None),
    77: ('雪', _SNOW_FLAKE, None),
    80: ('阵雨', _SHOWER, _MOON_RAIN),
    81: ('阵雨', _SHOWER, _MOON_RAIN),
    82: ('强阵雨', _SHOWER2, _MOON_RAIN),
    85: ('阵雪', _SNOW_L, None),
    86: ('强阵雪', _SNOW_M, None),
    95: ('雷阵雨', _BOLT_RAIN, _MOON_BOLT),
    96: ('强雷阵雨', _STORM, _MOON_BOLT),
    99: ('雷阵雨伴有冰雹', _STORM, _MOON_BOLT),
}


def describe(code, is_day=True):
    """WMO 码 → (中文名, 图标字符)。未知码回落到 N/A 字形。"""
    try:
        name, day_glyph, night_glyph = _WMO[int(code)]
    except (KeyError, TypeError, ValueError):
        return '未知', chr(_UNKNOWN)
    if not is_day and night_glyph is not None:
        return name, chr(night_glyph)
    return name, chr(day_glyph)


_WIND_SECTORS = ('北', '东北', '东', '东南', '南', '西南', '西', '西北')


def wind_direction(deg):
    """风向角度（来向，0=北）→ 八方位中文"""
    try:
        deg = float(deg)
    except (TypeError, ValueError):
        return ''
    return _WIND_SECTORS[round(deg / 45) % 8]
