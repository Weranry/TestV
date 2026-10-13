"""H2XL（400×300）横屏天气图：与 hxl 同一套画面语言，温度带更宽更高。

与 hxl 是两套独立坐标，不是把 hxl 的图放大。
"""

from ...lib.weather_landscape_fetcher import WeatherData
from .drawer import WeatherDrawer
from .utils import create_weather_canvas, finalize_image

# 几何参数只属于本尺寸，改这里不会牵动 hxl
XSTART = 36
XSTEP = 50
XFLAT = 12
YSTEP = 78
DRAWOFFSET = 156


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


async def generate_image(key='', lat=0.0, lon=0.0, units=0, pressure_min=980.0,
                         pressure_max=1030.0, rotate=0, invert=False, tz=None,
                         cmode=None, **kwargs):
    weather = WeatherData(
        key or '',
        _as_float(lat, 0.0),
        _as_float(lon, 0.0),
        units_mode=_as_int(units, 0),
        pressure_min=_as_float(pressure_min, 980.0),
        pressure_max=_as_float(pressure_max, 1030.0),
        tz=tz,
    )
    await weather.get_weather_data()

    img, _ = create_weather_canvas('h2xl', cmode=cmode)
    WeatherDrawer(img, xstart=XSTART, xstep=XSTEP, xflat=XFLAT, ystep=YSTEP,
                  drawoffset=DRAWOFFSET, flower_left_px=10, flower_right_px=12).draw(weather)
    return finalize_image(img, rotate=rotate, invert=invert)
