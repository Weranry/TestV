"""HXL（384×184）横屏天气图：左侧房子与时钟，右侧一整条温度曲线贯穿全宽。"""

from ...lib.weather_landscape_fetcher import WeatherData
from .drawer import WeatherDrawer
from .utils import create_weather_canvas, finalize_image

# 几何参数只属于本尺寸，改这里不会牵动 h2xl
XSTART = 32
XSTEP = 44
XFLAT = 10
YSTEP = 50
DRAWOFFSET = 100


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

    img, _ = create_weather_canvas('hxl', cmode=cmode)
    WeatherDrawer(img, xstart=XSTART, xstep=XSTEP, xflat=XFLAT, ystep=YSTEP,
                  drawoffset=DRAWOFFSET).draw(weather)
    return finalize_image(img, rotate=rotate, invert=invert)
