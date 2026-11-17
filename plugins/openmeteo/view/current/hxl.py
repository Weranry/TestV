"""HXL（384×184）横屏实况天气卡。

版面：页眉（城市/日期）→ 主区（左图标+天气名，中温度+体感，右温度区间与日出日落）
→ 细线 → 底部四列指标。字号全部为 16 的倍数（项目约定），层级靠字号差与留白拉开：
温度 64 是唯一主角，图标 48 次之，其余统一 16。红色只给 °C 单位与最高温。
"""
import importlib

canvas_factory = importlib.import_module("modules.generate_views.canvas_factory")
create_canvas = canvas_factory.create_canvas
finalize_image_common = canvas_factory.finalize_image_common

from ...lib.fetcher import fetch_weather
from ..common import (load_font, load_icon_font, draw_at, draw_right, draw_centered,
                      draw_icon, divider, fmt_temp, draw_temp_block, draw_metric_columns)
from .utils import draw_header, draw_range, metric_items

MARGIN = 16


async def generate_image(city=None, lat=None, lon=None, days=3,
                         rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_weather(city=city, lat=lat, lon=lon, days=days, host=kwargs.get('host'))
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    w, h = img.width, img.height
    cur = data['current']
    today = (data['daily'] or [{}])[0]

    text_font = load_font(16)
    num_font = load_font(64)
    icon_font = load_icon_font(56)  # 图标不受 16 倍数限制，按主区高度取满

    # 页眉：城市 + 日期，同为 16 直接同一 y
    draw_header(draw, data, MARGIN, w, text_font, text_font, y=8)
    divider(draw, 30, MARGIN, w - MARGIN)

    # 主区左：图标 + 天气名
    draw_icon(draw, 48, 74, cur['icon'], icon_font, fill=1)
    draw_centered(draw, 48, 104, cur['condition'], text_font, fill=1, max_width=100)

    # 主区中：大温度 + 体感
    draw_temp_block(draw, 104, 38, cur['temp'], '°C', num_font, text_font,
                    num_fill=1, unit_fill=2)
    draw_at(draw, (104, 86), f'体感 {fmt_temp(cur["feels"])}', text_font, fill=1)

    # 主区右：今日温度区间 + 日出日落
    if today:
        draw_range(draw, w - MARGIN, 38, today.get('tmax', cur['temp']),
                   today.get('tmin', cur['temp']), text_font)
    draw_right(draw, w - MARGIN, 60, f'日出 {today.get("sunrise", "")}', text_font, fill=1)
    draw_right(draw, w - MARGIN, 82, f'日落 {today.get("sunset", "")}', text_font, fill=1)

    # 底部指标
    divider(draw, 124, MARGIN, w - MARGIN)
    draw_metric_columns(draw, MARGIN, w - MARGIN, 132, metric_items(cur),
                        text_font, text_font)

    return finalize_image_common(img, rotate=rotate, invert=invert)
