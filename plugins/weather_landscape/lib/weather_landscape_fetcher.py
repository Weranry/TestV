"""OpenWeatherMap 取数：请求参数 → 可展示的天气序列。

只做数据（含网络与日出日落计算），不碰画布；视图层拿 `weather_data` 直接画。
传给视图的一切时间都是**插件的时区下的 naive 本地时间**，跨时区比较不做转换。
"""
import asyncio
import datetime
from math import acos, asin, cos
from math import degrees as deg
from math import radians as rad, sin, tan

import httpx

from modules.errors.errors import ParamError
from modules.utils.timezone import convert_utc_to_local, get_timezone_offset, now_in_timezone


class WeatherData:
    """实况 + 预报的合并序列，天气项按时间升序排列"""

    TEMP_UNITS_CELSIUS = 0
    TEMP_UNITS_FAHRENHEIT = 1
    KTOC = 273.15
    Thunderstorm = 2
    Drizzle = 3
    Rain = 5
    Snow = 6
    Atmosphere = 7
    Clouds = 8
    FORECAST_PERIOD_HOURS = 3
    OWMURL = "https://api.openweathermap.org/data/2.5/"

    def __init__(self, api_key, lat, lon, units_mode=0, pressure_min=980, pressure_max=1030, tz=None):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.units_mode = units_mode
        self.pressure_min = pressure_min
        self.pressure_max = pressure_max
        self.weather_data = []
        self.tz = tz
        self.reqstr = f"lat={self.lat}&lon={self.lon}&mode=json&APPID={self.api_key}"
        self.url_forecast = f"{self.OWMURL}forecast?{self.reqstr}"
        self.url_current = f"{self.OWMURL}weather?{self.reqstr}"

    @staticmethod
    async def _fetch_json(client, url):
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def get_weather_data(self):
        """拉取实况与预报，返回按时间升序的序列。

        两个端点互不依赖，并发发出——串行发等于把两次网络等待叠在一起，
        而视图中转的每一毫秒都占着渲染槽位。
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                current, forecast = await asyncio.gather(
                    self._fetch_json(client, self.url_current),
                    self._fetch_json(client, self.url_forecast),
                )
        except httpx.HTTPError as exc:
            raise ParamError(f"天气数据获取失败: {exc}")

        self.weather_data = [self._process_weather_info(current)]
        for item in forecast.get('list') or []:
            if self._check_weather_data(item):
                self.weather_data.append(self._process_weather_info(item))
        return self.weather_data

    def _process_weather_info(self, data):
        """处理从API获取的天气数据，存储为naive datetime"""
        is_celsius = self.units_mode != self.TEMP_UNITS_FAHRENHEIT
        utc_dt = datetime.datetime.fromtimestamp(int(data['dt']), tz=datetime.timezone.utc)
        local_dt_naive = convert_utc_to_local(utc_dt, self.tz).replace(tzinfo=None)

        weather_info = {
            'time': local_dt_naive,
            'id': int(data['weather'][0]['id']),
            'clouds': int(data['clouds'].get('all', 0)) if 'clouds' in data else 0,
            'rain': 0.0,
            'snow': 0.0,
            'windspeed': float(data['wind'].get('speed', 0.0)) if 'wind' in data else 0.0,
            'winddeg': float(data['wind'].get('deg', 0.0)) if 'wind' in data else 0.0,
            'pressure': float(data['main']['pressure']),
            'is_celsius': is_celsius
        }
        if 'rain' in data:
             if '3h' in data['rain']: weather_info['rain'] = float(data['rain']['3h'])
             elif '1h' in data['rain']: weather_info['rain'] = float(data['rain']['1h'])
        if 'snow' in data:
             if '3h' in data['snow']: weather_info['snow'] = float(data['snow']['3h'])
             elif '1h' in data['snow']: weather_info['snow'] = float(data['snow']['1h'])

        temp_kelvin = float(data['main']['temp'])
        weather_info['temp'] = self._to_celsius(temp_kelvin)
        weather_info['temp_fahrenheit'] = self._to_fahrenheit(temp_kelvin)

        return weather_info

    def _to_celsius(self, kelvin):
        return kelvin - self.KTOC

    def _to_fahrenheit(self, kelvin):
        return (kelvin - self.KTOC) * 1.8 + 32

    @staticmethod
    def _check_weather_data(data):
        if not ('dt' in data and 'weather' in data and 'main' in data):
            return False
        return True

    def _get_naive_datetime_in_timezone(self, dt_input):
        """Converts aware or naive datetime to naive datetime in instance's timezone."""
        if dt_input.tzinfo is not None:
            return convert_utc_to_local(dt_input, self.tz).replace(tzinfo=None)
        else:
            return dt_input

    def get_temp_range(self, max_time):
        """获取指定时间内的温度范围 (使用 naive 时间比较)"""
        if not self.weather_data: return None

        naive_max_time = self._get_naive_datetime_in_timezone(max_time)

        tmax = -999
        tmin = 999
        found_data = False

        for i, weather in enumerate(self.weather_data):
            if weather['time'] <= naive_max_time:
                if weather['temp'] > tmax: tmax = weather['temp']
                if weather['temp'] < tmin: tmin = weather['temp']
                found_data = True
            elif weather['time'] > naive_max_time and i > 0:
                 break

        return (tmin, tmax) if found_data else None

    def get_current(self):
        if not self.weather_data: return None
        return self.weather_data[0]

    def get_forecast_at_time(self, time):
        """获取指定时间的天气预报 (使用 naive 时间比较)"""
        if not self.weather_data: return None

        naive_target_time = self._get_naive_datetime_in_timezone(time)

        for weather in self.weather_data[1:]:
            if weather['time'] > naive_target_time:
                return weather
        return None


class SunCalculator:
    """计算日出日落时间 (返回 naive 本地时间)"""

    def __init__(self, lat, lon, tz=None):
        self.lat = lat
        self.lon = lon
        self.tz = tz

    def _get_naive_datetime_in_timezone(self, dt_input=None):
        """Gets current or specified time as naive datetime in instance's timezone."""
        if dt_input is None:
            return now_in_timezone(self.tz).replace(tzinfo=None)
        elif hasattr(dt_input, 'tzinfo') and dt_input.tzinfo is not None:
            return convert_utc_to_local(dt_input, self.tz).replace(tzinfo=None)
        else:
            return dt_input

    def sun_times(self, when=None):
        """一次算出 (日出, 日落, 太阳正午)。

        原先 sunrise() / sunset() 各自跑一遍 `__preptime` + `__calc`，而调用方在每
        个预测点上两样各取一次——同一时刻的同一套三角函数被算了两遍。合成一次
        调用后结果逐位相同，运算量减半。
        """
        naive_when = self._get_naive_datetime_in_timezone(when)
        self._preptime(naive_when)
        self._calc()
        return (self._timefromdecimalday(self.sunrise_t, naive_when),
                self._timefromdecimalday(self.sunset_t, naive_when),
                self._timefromdecimalday(self.solarnoon_t, naive_when))

    def _timefromdecimalday(self, day_fraction, base_naive_when):
        hours = 24.0 * day_fraction
        h = int(hours)
        minutes = (hours - h) * 60
        m = int(minutes)
        seconds = (minutes - m) * 60
        s = int(round(seconds))

        if s >= 60:
            s -= 60
            m += 1
        if m >= 60:
            m -= 60
            h += 1

        day_offset = 0
        while h < 0:
            h += 24
            day_offset -= 1
        while h >= 24:
            h -= 24
            day_offset += 1

        base_date = base_naive_when.date()

        try:
            adjusted_date = base_date + datetime.timedelta(days=day_offset)
            return datetime.datetime(adjusted_date.year, adjusted_date.month, adjusted_date.day, h, m, s)
        except OverflowError:
             raise ValueError(f"Date calculation resulted in overflow for base_date={base_date}, day_offset={day_offset}")
        except ValueError as e:
             raise ValueError(f"Could not construct valid naive datetime. adjusted_date={adjusted_date}, h={h}, m={m}, s={s}. Original error: {e}") from e

    def _preptime(self, naive_when):
        self.timezone_offset_hours = get_timezone_offset(self.tz) or 0.0

        when_utc = naive_when - datetime.timedelta(hours=self.timezone_offset_hours)

        self.day = when_utc.toordinal() - (734124 - 40529)
        t = when_utc.time()
        self.time = (t.hour + t.minute/60.0 + t.second/3600.0) / 24.0

    def _calc(self):
        timezone = self.timezone_offset_hours
        longitude = self.lon
        latitude = self.lat
        time = self.time
        day = self.day

        Jday = day + 2415018.5 + time
        Jcent = (Jday - 2451545) / 36525

        Manom = 357.52911 + Jcent * (35999.05029 - 0.0001537 * Jcent)
        Mlong = (280.46646 + Jcent * (36000.76983 + Jcent * 0.0003032)) % 360
        Eccent = 0.016708634 - Jcent * (0.000042037 + 0.0001537 * Jcent)

        Mobliq = 23 + (26 + ((21.448 - Jcent * (46.815 + Jcent * (0.00059 - Jcent * 0.001813)))) / 60) / 60
        obliq = Mobliq + 0.00256 * cos(rad(125.04 - 1934.136 * Jcent))
        vary = tan(rad(obliq / 2)) * tan(rad(obliq / 2))
        Seqcent = sin(rad(Manom)) * (1.914602 - Jcent * (0.004817 + 0.000014 * Jcent)) + \
                  sin(rad(2 * Manom)) * (0.019993 - 0.000101 * Jcent) + \
                  sin(rad(3 * Manom)) * 0.000289
        Struelong = (Mlong + Seqcent) % 360
        Sapplong = Struelong - 0.00569 - 0.00478 * sin(rad(125.04 - 1934.136 * Jcent))
        declination = deg(asin(sin(rad(obliq)) * sin(rad(Sapplong))))

        eqtime = 4 * deg(vary * sin(2 * rad(Mlong)) - 2 * Eccent * sin(rad(Manom)) + \
                         4 * Eccent * vary * sin(rad(Manom)) * cos(2 * rad(Mlong)) - \
                         0.5 * vary * vary * sin(4 * rad(Mlong)) - \
                         1.25 * Eccent * Eccent * sin(2 * rad(Manom)))

        ha_arg = (cos(rad(90.833)) / (cos(rad(latitude)) * cos(rad(declination))) - \
                  tan(rad(latitude)) * tan(rad(declination)))
        ha_arg = max(-1.0, min(1.0, ha_arg))
        hourangle = deg(acos(ha_arg))

        self.solarnoon_t = (720 - 4 * longitude - eqtime + timezone * 60) / 1440
        self.sunrise_t = self.solarnoon_t - hourangle * 4 / 1440
        self.sunset_t = self.solarnoon_t + hourangle * 4 / 1440