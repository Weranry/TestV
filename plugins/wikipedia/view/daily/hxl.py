"""维基百科每日摘要 · 384×184 小屏横屏。

极简版面：日期行 + 快讯条（正在发生 / 最近逝世）+ 两三条新闻动态。
小屏不做分区标题和页脚，把高度全部留给内容；快讯条至少保留一行，
没有快讯时才退化为纯新闻列表。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from .utils import (
    BODY_LINE_H,
    draw_headline_items,
    draw_ticker,
    load_fonts,
)

W, H = 384, 184
MARGIN = 16
RIGHT = W - MARGIN
TOP_BAR_H = 4
HEADER_RULE_Y = 52
BODY_BOTTOM = H - 4

HOT_LABEL_WIDTH = 72
HOT_ROW_H = 22

WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')


def _draw_header(draw, now, fonts):
    draw.rectangle([0, 0, W - 1, TOP_BAR_H - 1], fill=2)
    draw.text((MARGIN, 8), f'{now.month}月{now.day}日', font=fonts['head'], fill=1)
    draw.text((RIGHT, 12), WEEKDAYS[now.weekday()], font=fonts['body'], fill=1, anchor='ra')
    draw.line([(MARGIN, HEADER_RULE_Y), (RIGHT, HEADER_RULE_Y)], fill=1, width=2)
    draw.rectangle([MARGIN, HEADER_RULE_Y - 5, MARGIN + 40, HEADER_RULE_Y - 1], fill=1)


def _draw_hot_rows(draw, data, y, font):
    drew = False
    if data['ongoing']:
        draw_ticker(draw, '正在发生', data['ongoing'], MARGIN, y, RIGHT, font, HOT_LABEL_WIDTH)
        y += HOT_ROW_H
        drew = True
    if data['deaths']:
        draw_ticker(draw, '最近逝世', data['deaths'], MARGIN, y, RIGHT, font, HOT_LABEL_WIDTH)
        y += HOT_ROW_H
        drew = True
    if drew:
        y += 3
        draw.line([(MARGIN, y), (RIGHT, y)], fill=1, width=1)
        y += 9
    return y


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_wikipedia_daily(page_url=kwargs.get('page_url'))
    now = now_in_timezone(tz)
    fonts = load_fonts()

    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    _draw_header(draw, now, fonts)

    y = _draw_hot_rows(draw, data, HEADER_RULE_Y + 6, fonts['body'])
    items = data['news'] or data['dyk']
    if items:
        draw_headline_items(draw, items, MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                            fonts['body'], BODY_LINE_H, gap=0)

    return finalize_image_common(img, rotate=rotate, invert=invert)
