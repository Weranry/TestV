"""H2XL（400×300）横屏实况天气卡：与 hxl 同一套画面语言，独立坐标。

字号仍只用 16 的倍数，多出的高度给更大的图标（80）与温度（96）、
更松的行距，以及独立的页脚温度区间（32）——层级靠尺寸差，不靠小字。
"""
import importlib

canvas_factory = importlib.import_module("modules.generate_views.canvas_factory")
create_canvas = canvas_factory.create_canvas
finalize_image_common = canvas_factory.finalize_image_common

from ...lib.fetcher import fetch_weather
from ..common import (load_font, load_icon_font, draw_at, draw_right, draw_centered,
                      draw_icon, divider, fmt_temp, draw_temp_block, draw_metric_columns)
from .utils import draw_header, draw_range, metric_items

MARGIN = 20


async def generate_image(city=None, lat=None, lon=None, days=3,
                         rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_weather(city=city, lat=lat, lon=lon, days=days, host=kwargs.get('host'))
    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    w, h = img.width, img.height
    cur = data['current']
    today = (data['daily'] or [{}])[0]

    title_font = load_font(32)
    text_font = load_font(16)
    num_font = load_font(96)
    unit_font = load_font(32)
    icon_font = load_icon_font(88)  # 图标不受 16 倍数限制，按主区高度取满

    # 页眉：城市 32 + 日期 16（底缘对齐）
    draw_header(draw, data, MARGIN, w, title_font, text_font, y=12)
    divider(draw, 56, MARGIN, w - MARGIN)

    # 主区左：图标 + 天气名
    draw_icon(draw, 68, 112, cur['icon'], icon_font, fill=1)
    draw_centered(draw, 68, 160, cur['condition'], text_font, fill=1, max_width=120)

    # 主区中：大温度 + 体感
    draw_temp_block(draw, 140, 52, cur['temp'], '°C', num_font, unit_font,
                    num_fill=1, unit_fill=2)
    draw_at(draw, (140, 120), f'体感 {fmt_temp(cur["feels"])}', text_font, fill=1)

    # 指标带
    divider(draw, 184, MARGIN, w - MARGIN)
    draw_metric_columns(draw, MARGIN, w - MARGIN, 194, metric_items(cur),
                        text_font, text_font)

    # 页脚：今日温度区间（32，红高黑低）+ 日出日落（16）
    divider(draw, 244, MARGIN, w - MARGIN)
    if today:
        draw_range(draw, MARGIN, 254, today.get('tmax', cur['temp']),
                   today.get('tmin', cur['temp']), unit_font, gap=16, align='left')
    draw_right(draw, w - MARGIN, 262,
               f'日出 {today.get("sunrise", "")}  日落 {today.get("sunset", "")}',
               text_font, fill=1)

    return finalize_image_common(img, rotate=rotate, invert=invert)
