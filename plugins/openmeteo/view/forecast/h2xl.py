"""H2XL（400×300）横屏多日预报：与 hxl 同一套分栏语言，纵向节奏更松。

字号只用 16 的倍数：≤5 列用 32/64 的大字号层级（星期 32、图标 64、高低温 32
上下两行红高黑低），≥6 列窄栏整体降一档（16/48）保证不压线。
"""
import importlib

canvas_factory = importlib.import_module("modules.generate_views.canvas_factory")
create_canvas = canvas_factory.create_canvas
finalize_image_common = canvas_factory.finalize_image_common

from ...lib.fetcher import fetch_weather
from ..common import (load_font, load_icon_font, draw_centered, draw_icon,
                      divider, vdivider)
from .utils import draw_header, draw_day_range_stacked

MARGIN = 20


async def generate_image(city=None, lat=None, lon=None, days=3,
                         rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_weather(city=city, lat=lat, lon=lon, days=days, host=kwargs.get('host'))
    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    w, h = img.width, img.height
    daily = data['daily']
    n = max(1, len(daily))

    wide = n <= 5
    title_font = load_font(32)
    text_font = load_font(16)
    weekday_font = load_font(32 if wide else 16)
    temp_font = load_font(32 if wide else 16)
    # 图标不受 16 倍数限制，按列宽与行距取最优
    icon_font = load_icon_font(68 if wide else 44)

    draw_header(draw, data, n, MARGIN, w, title_font, text_font, y=12)
    divider(draw, 52, MARGIN, w - MARGIN)

    x0, x1 = MARGIN, w - MARGIN
    col_w = (x1 - x0) // n
    for i, day in enumerate(daily):
        cx = x0 + col_w * i + col_w // 2
        # 星期 32px 时「周五」占 64px，5 列（col_w=72）下限制必须放到 col_w-4
        draw_centered(draw, cx, 60, day['weekday'], weekday_font, fill=1, max_width=col_w - 4)
        draw_centered(draw, cx, 100 if wide else 88, str(day['date'])[5:], text_font, fill=1)
        draw_icon(draw, cx, 142 if wide else 128, day['icon'], icon_font, fill=1)
        draw_centered(draw, cx, 178 if wide else 160, day['condition'], text_font,
                      fill=1, max_width=col_w - 8)
        draw_day_range_stacked(draw, cx, 200 if wide else 182,
                               236 if wide else 204, day, temp_font, temp_font)
        # 窄列省掉「雨」前缀，避免与栏间细线挤压
        draw_centered(draw, cx, 270,
                      f'雨 {day["precip_prob"]}%' if wide else f'{day["precip_prob"]}%',
                      text_font, fill=1)

        if i:
            vdivider(draw, x0 + col_w * i, 58, h - 20)

    return finalize_image_common(img, rotate=rotate, invert=invert)
