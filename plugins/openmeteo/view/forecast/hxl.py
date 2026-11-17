"""HXL（384×184）横屏多日预报：等宽分栏 + 栏间细线。

字号只用 16 的倍数。每列自上而下：星期 → 日期 → 图标 → 天气名 → 高低温 → 降水概率。
列数自适应：≤5 列时高低温同行（16），≥6 列窄栏改上下两行，避免压线重叠。
"""
import importlib

canvas_factory = importlib.import_module("modules.generate_views.canvas_factory")
create_canvas = canvas_factory.create_canvas
finalize_image_common = canvas_factory.finalize_image_common

from ...lib.fetcher import fetch_weather
from ..common import (load_font, load_icon_font, draw_centered, draw_icon,
                      divider, vdivider)
from .utils import draw_header, draw_day_range_inline, draw_day_range_stacked

MARGIN = 16


async def generate_image(city=None, lat=None, lon=None, days=3,
                         rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_weather(city=city, lat=lat, lon=lon, days=days, host=kwargs.get('host'))
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    w, h = img.width, img.height
    daily = data['daily']
    n = max(1, len(daily))

    text_font = load_font(16)
    stacked = n >= 6  # 窄列：高低温上下两行
    # 图标不受 16 倍数限制：宽列取满栏高，窄列收一点避让栏线
    icon_font = load_icon_font(28 if stacked else 36)

    draw_header(draw, data, n, MARGIN, w, text_font, text_font, y=8)
    divider(draw, 30, MARGIN, w - MARGIN)

    x0, x1 = MARGIN, w - MARGIN
    col_w = (x1 - x0) // n
    for i, day in enumerate(daily):
        cx = x0 + col_w * i + col_w // 2
        draw_centered(draw, cx, 36, day['weekday'], text_font, fill=1, max_width=col_w - 8)
        draw_centered(draw, cx, 56, str(day['date'])[5:], text_font, fill=1)
        draw_icon(draw, cx, 88, day['icon'], icon_font, fill=1)
        if stacked:
            draw_centered(draw, cx, 106, day['condition'], text_font, fill=1, max_width=col_w - 4)
            draw_day_range_stacked(draw, cx, 124, 142, day, text_font, text_font)
            # 窄列省掉「雨」前缀，概率数字本身已表意
            draw_centered(draw, cx, 162, f'{day["precip_prob"]}%', text_font, fill=1)
        else:
            draw_centered(draw, cx, 108, day['condition'], text_font, fill=1, max_width=col_w - 6)
            draw_day_range_inline(draw, cx, 128, day, text_font, text_font)
            draw_centered(draw, cx, 150, f'雨 {day["precip_prob"]}%', text_font, fill=1)

        if i:
            vdivider(draw, x0 + col_w * i, 34, h - 14)

    return finalize_image_common(img, rotate=rotate, invert=invert)
