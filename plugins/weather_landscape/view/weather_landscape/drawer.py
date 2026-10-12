"""天气横向视图的绘制引擎（HXL / H2XL 共用）。

只负责把 `lib/weather_landscape_fetcher.py` 给出的天气序列画到画布上；几何参数由
各尺寸的视图自己传进来，因此两套尺寸是各写各的坐标，不存在缩放关系。

配色：框架 `bwr` 画布是 0=白 1=黑 2=红，而自带精灵图素材是 0=黑 1=白 2=红 3=透明，
索引恰好相反。载入精灵图时统一重映射一次、并生成 1 bit 掩膜，贴图走
`Image.paste()`（C 层实现），不再逐像素走 Python 循环。
"""
import datetime
import math
import os
import random

from PIL import Image, ImageOps

from modules.utils.timezone import now_in_timezone

from ...lib.weather_landscape_fetcher import SunCalculator, WeatherData

# 框架 bwr 画布索引
WHITE = 0
BLACK = 1
RED = 2

# 温度曲线数组里「这一段不要放东西」的哨兵值
DISABLED = -999999

SPRITE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'assets', 'sprite'))

# 精灵图索引 → 画布索引：黑 0→1、白 1→0、红 2→2、其余（3 透明）丢弃
_INDEX_MAP = [3] * 256
_INDEX_MAP[0], _INDEX_MAP[1], _INDEX_MAP[2] = BLACK, WHITE, RED

# 精灵图只读且只有几十张小图，(名字, 序号, 是否镜像) → (重映射图, 1 bit 掩膜)。
# 热重载会重建本模块，缓存跟着天然失效。
_SPRITE_CACHE = {}


def load_sprite(name, index, mirror=False):
    """取 `(已重映射的精灵图, 掩膜)`；素材缺失返回 None（调用方按宽度 0 处理）"""
    key = (name, index, mirror)
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]

    sprite = None
    path = os.path.join(SPRITE_DIR, '%s_%02i.png' % (name, index))
    if os.path.exists(path):
        src = Image.open(path)
        if mirror:
            src = ImageOps.mirror(src)
        img = src.point(_INDEX_MAP)
        mask = Image.new('1', src.size)
        mask.putdata([0 if v == 3 else 1 for v in src.get_flattened_data()])
        # 显式 load，避免多线程同时贴同一张图时在惰性解码上撞车
        img.load()
        mask.load()
        sprite = (img, mask)

    _SPRITE_CACHE[key] = sprite
    return sprite


class Sprites:
    """精灵图与曲线数组上的绘制原语"""

    DIGITPLAS = 10
    DIGITMINUS = 11
    DIGITSEMICOLON = 12

    HEAVYRAIN = 5.0
    RAINFACTOR = 20

    HEAVYSNOW = 5.0
    SNOWFACTOR = 10

    SMOKE_R_PX = 30
    SMOKE_SIZE = 60

    def __init__(self, canvas):
        self.img = canvas
        self.pix = canvas.load()
        self.w, self.h = canvas.size

    def Dot(self, x, y, color=BLACK):
        if (y >= self.h) or (x >= self.w) or (y < 0) or (x < 0):
            return
        self.pix[x, y] = color

    def Draw(self, name, index, xpos, ypos, ismirror=False):
        """在 `(xpos, ypos)` 贴一张精灵图（ypos 是底边），返回精灵图宽度"""
        # 坐标可能来自时间差换算（日出日落那个位置就是带小数的），统一取整
        xpos = int(xpos)
        ypos = int(ypos)
        if (xpos < 0) or (ypos < 0):
            return 0
        sprite = load_sprite(name, index, ismirror)
        if sprite is None:
            # 找不到该 sprite 直接返回宽度 0，不影响主流程（调用方会继续绘制）
            return 0
        img, mask = sprite
        w, h = img.size
        self.img.paste(img, (xpos, ypos - h), mask)
        return w

    def DrawInt(self, n, xpos, ypos, issign=True, mindigits=1):
        n = round(n)
        if n < 0:
            sign = self.DIGITMINUS
        else:
            sign = self.DIGITPLAS
        n = abs(n)
        n0 = int(n / 100)
        n1 = int((n % 100) / 10)
        n2 = n % 10
        dx = 0
        if (issign) or (sign == self.DIGITMINUS):
            w = self.Draw("digit", sign, xpos + dx, ypos)
            dx += w + 1
        if (n0 != 0) or (mindigits >= 3):
            w = self.Draw("digit", n0, xpos + dx, ypos)
            dx += w
            if (n0 != 1):
                dx += 1
        if (n1 != 0) or (n0 != 0) or (mindigits >= 2):
            if (n1 == 1):
                dx -= 1
            w = self.Draw("digit", n1, xpos + dx, ypos)
            dx += w
            if (n1 != 1):
                dx += 1
        if (n2 == 1):
            dx -= 1
        w = self.Draw("digit", n2, xpos + dx, ypos)
        dx += w
        if (n2 != 1):
            dx += 1
        return dx

    def DrawClock(self, xpos, ypos, h, m):
        dx = 0
        w = self.DrawInt(h, xpos + dx, ypos, False, 2)
        dx += w
        w = self.Draw("digit", self.DIGITSEMICOLON, xpos + dx, ypos)
        dx += w
        dx = self.DrawInt(m, xpos + dx, ypos, False, 2)
        dx += w + 1
        return dx

    def DrawCloud(self, persent, xpos, ypos, width, height):
        if persent < 2:
            return
        elif persent < 5:
            cloudset = [2]
        elif persent < 10:
            cloudset = [3, 2]
        elif persent < 20:
            cloudset = [5, 3, 2]
        elif persent < 30:
            cloudset = [10, 5]
        elif persent < 40:
            cloudset = [10, 10]
        elif persent < 50:
            cloudset = [10, 10, 5]
        elif persent < 60:
            cloudset = [30, 5]
        elif persent < 70:
            cloudset = [30, 10]
        elif persent < 80:
            cloudset = [30, 10, 5, 5]
        elif persent < 90:
            cloudset = [30, 10, 10]
        else:
            cloudset = [50, 30, 10, 10, 5]
        dx = width
        for c in cloudset:
            self.Draw("cloud", c, xpos + random.randrange(dx), ypos)

    def DrawRain(self, value, xpos, ypos, width, tline):
        if value <= 0:
            # 无降水时 r == 1.0，random.random() 永远不大于它，一个点都画不出来
            return
        ypos += 1
        r = 1.0 - (value / self.HEAVYRAIN) / self.RAINFACTOR
        for x in range(xpos, xpos + width):
            for y in range(ypos, tline[x], 2):
                if (x >= self.w):
                    continue
                if (y >= self.h):
                    continue
                if (random.random() > r):
                    self.pix[x, y] = BLACK
                    self.pix[x, y - 1] = BLACK

    def DrawSnow(self, value, xpos, ypos, width, tline):
        if value <= 0:
            # 同 DrawRain：无降水时整段循环都是空转
            return
        ypos += 1
        r = 1.0 - (value / self.HEAVYSNOW) / self.SNOWFACTOR
        for x in range(xpos, xpos + width):
            for y in range(ypos, tline[x], 2):
                if (x >= self.w):
                    continue
                if (y >= self.h):
                    continue
                if (random.random() > r):
                    self.pix[x, y] = BLACK

    def DrawWind_degdist(self, deg1, deg2):
        h = max(deg1, deg2)
        l = min(deg1, deg2)
        d = h - l
        if d > 180:
            d = 360 - d
        return d

    def DrawWind_dirsprite(self, dir, dir0, name, out):
        count = [4, 3, 3, 2, 2, 1, 1]
        step = 11.25
        dist = self.DrawWind_degdist(dir, dir0)
        n = int(dist / step)
        if n < len(count):
            for i in range(0, count[n]):
                out.append(name)

    def DrawWind(self, speed, direction, xpos, tline):
        names = []
        self.DrawWind_dirsprite(direction, 0, "pine", names)
        self.DrawWind_dirsprite(direction, 90, "east", names)
        self.DrawWind_dirsprite(direction, 180, "palm", names)
        self.DrawWind_dirsprite(direction, 270, "tree", names)
        random.shuffle(names)
        if speed <= 0.4:
            windindex = []
        elif speed <= 0.7:
            windindex = [0]
        elif speed <= 1.7:
            windindex = [1, 0, 0]
        elif speed <= 3.3:
            windindex = [1, 1, 0, 0]
        elif speed <= 5.2:
            windindex = [1, 2, 0, 0]
        elif speed <= 7.4:
            windindex = [1, 2, 2, 0]
        elif speed <= 9.8:
            windindex = [1, 2, 3, 0]
        elif speed <= 12.4:
            windindex = [2, 2, 3, 0]
        else:
            windindex = [3, 3, 3, 3]
        ix = int(xpos)
        random.shuffle(windindex)
        j = 0
        for i in windindex:
            if j >= len(names):
                break
            xx = ix + random.randint(-1, 1)
            ismirror = random.random() < 0.5
            offset = xx + 5
            if offset >= len(tline):
                break
            if ismirror:
                xx -= 16
            self.Draw(names[j], i, xx, tline[offset] + 1, ismirror)
            ix += 9
            j += 1

    def DrawSmoke_makeline(self, angle_deg):
        a = (math.pi * angle_deg) / 180
        r = self.SMOKE_R_PX
        k = r * math.sin(a) / (math.sqrt((r * math.cos(a))))
        yp = 0
        dots = []
        for x in range(0, self.w):
            y = int(k * math.sqrt(x))
            if y > self.h:
                y = self.h
            yi = yp
            while True:
                rr = math.sqrt(x * x + yi * yi)
                dots.append((x, yi, rr))
                if rr > self.SMOKE_SIZE:
                    return dots
                yi += 1
                if yi >= y:
                    yp = y
                    break

    def DrawSmoke(self, x0, y0, percent):
        dots = self.DrawSmoke_makeline(percent)
        for x, y, r in dots:
            if random.random() * 1.3 > (r / self.SMOKE_SIZE):
                if random.random() * 1.2 < (r / self.SMOKE_SIZE):
                    dx = random.randint(-1, 1)
                    dy = random.randint(-1, 1)
                else:
                    dx = 0
                    dy = 0
                self.Dot(x0 + x + dx, self.h - (y0 + y) + dy, BLACK)


def bezier_func(t, d0, d1, d2, d3):
    return (1 - t) * ((1 - t) * ((1 - t) * d0 + t * d1) + t * ((1 - t) * d1 + t * d2)) + \
        t * ((1 - t) * ((1 - t) * d1 + t * d2) + t * ((1 - t) * d2 + t * d3))


def bezier_y(x, xa, ya, xb, yb):
    d = xb - xa
    t = float(x - xa) / float(d)
    return int(bezier_func(t, ya, ya, yb, yb))


class WeatherDrawer:
    """天气横轴图：左侧房子与时钟，右侧温度曲线贯穿全宽。

    几何参数没有默认值，由各尺寸视图显式给出——同一引擎配不同坐标就是两套布局，
    改了某一套不会牵动另一套。
    """

    def __init__(self, canvas, xstart, xstep, xflat, ystep, drawoffset,
                 degree_per_pixel=0.5, flower_left_px=10, flower_right_px=15):
        self.img = canvas
        self.sprite = Sprites(canvas)
        self.pic_width, self.pic_height = canvas.size
        self.xstart = int(xstart)
        self.xstep = int(xstep)
        self.xflat = int(xflat)
        self.ystep = int(ystep)
        self.ypos = int(drawoffset)
        self.default_degree_per_pixel = degree_per_pixel
        self.flower_left_px = int(flower_left_px)
        self.flower_right_px = int(flower_right_px)
        # 下面几项在 draw() 里按当次数据算出，供 deg_to_pix 使用
        self.tmin = 0.0
        self.tmax = 0.0
        self.temp_range = 0.0
        self.degree_per_pixel = degree_per_pixel

    def time_diff_to_pixels(self, dt):
        ds = dt.total_seconds()
        seconds_per_pixel = (WeatherData.FORECAST_PERIOD_HOURS * 60 * 60) / self.xstep
        return int(ds / seconds_per_pixel)

    def deg_to_pix(self, t):
        n = (t - self.tmin) / self.degree_per_pixel
        return self.ypos + self.ystep - int(n)

    def block_range(self, tline, x0, x1):
        for x in range(x0, x1):
            if x < len(tline):
                tline[x] = DISABLED

    def draw_temperature(self, f, x, y, sprite):
        temp = f['temp'] if f['is_celsius'] else f['temp_fahrenheit']
        if f['is_celsius']:
            sprite.DrawInt(temp, x, y + 10, True, 2)
        else:
            sprite.DrawInt(temp, x, y + 10, False, 1)

    def draw(self, weather_data):
        """把天气序列画到构造时给的画布上，返回该画布"""
        sprite = self.sprite
        pic_width = self.pic_width
        pic_height = self.pic_height

        n_forecast = (pic_width - self.xstart) / self.xstep
        max_time = now_in_timezone(weather_data.tz) + datetime.timedelta(
            hours=WeatherData.FORECAST_PERIOD_HOURS * n_forecast)

        (self.tmin, self.tmax) = weather_data.get_temp_range(max_time)
        self.temp_range = self.tmax - self.tmin

        if self.temp_range < self.ystep:
            self.degree_per_pixel = self.default_degree_per_pixel
        else:
            self.degree_per_pixel = self.temp_range / float(self.ystep)

        xpos = 0
        tline = [0] * (pic_width + self.xstep * 2)

        f = weather_data.get_current()
        old_temp = f['temp']
        old_y = self.deg_to_pix(old_temp)

        for i in range(self.xstart):
            tline[i] = old_y

        y_clouds = int(self.ypos - self.ystep / 2)
        house_width = sprite.Draw("house", 0, xpos, old_y)

        t_now = now_in_timezone(weather_data.tz)
        sprite.DrawClock(xpos + house_width, old_y - 10, t_now.hour, t_now.minute)
        self.draw_temperature(f, xpos + 8, old_y, sprite)

        curr_hpa = f['pressure']
        smoke_angle_deg = ((curr_hpa - weather_data.pressure_min) /
                           (weather_data.pressure_max - weather_data.pressure_min)) * 85 + 5
        if smoke_angle_deg < 0:
            smoke_angle_deg = 0
        if smoke_angle_deg > 90:
            smoke_angle_deg = 90

        sprite.DrawSmoke(xpos + 21, pic_height - old_y + 23, smoke_angle_deg)
        sprite.DrawCloud(f['clouds'], xpos, y_clouds, self.xstart, self.ystep / 2)
        sprite.DrawRain(f['rain'], xpos, y_clouds, self.xstart, tline)
        sprite.DrawSnow(f['snow'], xpos, y_clouds, self.xstart, tline)

        t = now_in_timezone(weather_data.tz)
        dt = datetime.timedelta(hours=WeatherData.FORECAST_PERIOD_HOURS)
        tf = t

        x0 = self.xstart
        xpos = x0
        n_forecast = int(n_forecast)

        n = int((self.xstep - self.xflat) / 2)
        for i in range(n_forecast + 1):
            f = weather_data.get_forecast_at_time(tf)
            if f is None:
                continue
            new_temp = f['temp']
            new_y = self.deg_to_pix(new_temp)
            for i in range(n):
                if xpos + i < len(tline):
                    tline[xpos + i] = bezier_y(xpos + i, xpos, old_y, xpos + n, new_y)
            for i in range(self.xflat):
                if int(xpos + i + n) < len(tline):
                    tline[int(xpos + i + n)] = new_y
            xpos += n + self.xflat
            n = (self.xstep - self.xflat)
            old_temp = new_temp
            old_y = new_y
            tf += dt

        # 预报数据用尽后右侧还剩一段：用最后一个点铺平，否则曲线会在末端断掉
        for x in range(xpos, pic_width):
            if x < len(tline):
                tline[x] = old_y

        tline0 = tline.copy()
        self.block_range(tline, 0, x0)

        sun_calc = SunCalculator(weather_data.lat, weather_data.lon, tz=weather_data.tz)
        tf = t
        xpos = self.xstart
        obj_counter = 0

        for i in range(n_forecast + 1):
            f = weather_data.get_forecast_at_time(tf)
            if f is None:
                continue
            t_sunrise, t_sunset, _ = sun_calc.sun_times(tf)
            t_noon = datetime.datetime(tf.year, tf.month, tf.day, 12, 0, 0, 0)
            t_midn = datetime.datetime(tf.year, tf.month, tf.day, 0, 0, 0, 0) + datetime.timedelta(days=1)
            y_moon = self.ypos - self.ystep * 5 / 8

            if (tf <= t_sunrise) and (tf + dt > t_sunrise):
                dx = self.time_diff_to_pixels(t_sunrise - tf) - self.xstep / 2
                sprite.Draw("sun", 0, xpos + dx, y_moon)
                obj_counter += 1
                if obj_counter == 2:
                    break

            if (tf <= t_sunset) and (tf + dt > t_sunset):
                dx = self.time_diff_to_pixels(t_sunset - tf) - self.xstep / 2
                sprite.Draw("moon", 0, xpos + dx, y_moon)
                obj_counter += 1
                if obj_counter == 2:
                    break

            if (tf <= t_noon) and (tf + dt > t_noon):
                dx = self.time_diff_to_pixels(t_noon - tf) - self.xstep / 2
                ix = int(xpos + dx)
                if ix < len(tline):
                    sprite.Draw("flower", 1, ix, tline[ix] + 1)
                    self.block_range(tline, ix - self.flower_left_px, ix + self.flower_right_px)

            if (tf <= t_midn) and (tf + dt > t_midn):
                dx = self.time_diff_to_pixels(t_midn - tf) - self.xstep / 2
                ix = int(xpos + dx)
                if ix < len(tline):
                    sprite.Draw("flower", 0, ix, tline[ix] + 1)
                    self.block_range(tline, ix - self.flower_left_px, ix + self.flower_right_px)

            xpos += self.xstep
            tf += dt

        is_tmin_printed = False
        is_tmax_printed = False
        tf = t
        xpos = self.xstart
        n = int((self.xstep - self.xflat) / 2)
        drawn = set()

        for i in range(n_forecast + 1):
            f = weather_data.get_forecast_at_time(tf)
            if f is None:
                continue
            dx = self.time_diff_to_pixels(f['time'] - tf) - self.xstep / 2
            ix = int(xpos + dx)
            y_clouds = int(self.ypos - self.ystep / 2)
            if (f['temp'] == self.tmin) and (not is_tmin_printed):
                if xpos + n < len(tline0):
                    self.draw_temperature(f, xpos + n, tline0[xpos + n], sprite)
                    is_tmin_printed = True
            if (f['temp'] == self.tmax) and (not is_tmax_printed):
                if xpos + n < len(tline0):
                    self.draw_temperature(f, xpos + n, tline0[xpos + n], sprite)
                    is_tmax_printed = True
            # 同一个预报项会被相邻几个时间点取到，只画一次
            if id(f) not in drawn:
                drawn.add(id(f))
                sprite.DrawWind(f['windspeed'], f['winddeg'], ix, tline)
                sprite.DrawCloud(f['clouds'], ix, y_clouds, self.xstep, self.ystep / 2)
                sprite.DrawRain(f['rain'], ix, y_clouds, self.xstep, tline0)
                sprite.DrawSnow(f['snow'], ix, y_clouds, self.xstep, tline0)
            xpos += self.xstep
            tf += dt

        for x in range(pic_width):
            if x < len(tline0) and tline0[x] < pic_height:
                sprite.Dot(x, tline0[x], BLACK)

        return self.img