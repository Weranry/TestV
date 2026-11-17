"""维基百科每日摘要 · 400×300 小屏横屏。

版面结构：紧凑日期头 + 快讯条（正在发生 / 最近逝世）+ 新闻动态。
新闻优先占用剩余高度；新闻较短时，剩余空间自动补一个「你知道吗？」分区。
小屏空间有限，不做特色内容长段落，避免正文被压缩成两三行。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from .utils import (
    BODY_LINE_H,
    SECTION_GAP,
    draw_bullet_items,
    draw_section_header,
    draw_ticker,
    load_fonts,
)

W, H = 400, 300
MARGIN = 16
RIGHT = W - MARGIN
TOP_BAR_H = 6
HEADER_RULE_Y = 78
FOOTER_RULE_Y = H - 30
BODY_BOTTOM = FOOTER_RULE_Y - 6

HOT_LABEL_WIDTH = 72
HOT_ROW_H = 22
HEAD_H = 26

WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')


def _draw_header(draw, now, fonts):
    draw.rectangle([0, 0, W - 1, TOP_BAR_H - 1], fill=2)
    draw.text((MARGIN, 10), '维基百科 · 每日摘要', font=fonts['body'], fill=2)
    draw.text((RIGHT, 10), str(now.year), font=fonts['body'], fill=2, anchor='ra')
    draw.text((MARGIN, 32), f'{now.month}月{now.day}日', font=fonts['head'], fill=1)
    draw.text((RIGHT, 32), WEEKDAYS[now.weekday()], font=fonts['head'], fill=1, anchor='ra')
    draw.line([(MARGIN, HEADER_RULE_Y), (RIGHT, HEADER_RULE_Y)], fill=1, width=2)
    draw.rectangle([MARGIN, HEADER_RULE_Y - 5, MARGIN + 48, HEADER_RULE_Y - 1], fill=1)


def _draw_footer(draw, now, fonts):
    draw.line([(MARGIN, FOOTER_RULE_Y), (RIGHT, FOOTER_RULE_Y)], fill=1, width=1)
    draw.text((MARGIN, FOOTER_RULE_Y + 6), '维基百科 · zh.wikipedia.org',
              font=fonts['body'], fill=1)
    draw.text((RIGHT, FOOTER_RULE_Y + 6), now.strftime('%m-%d %H:%M'),
              font=fonts['body'], fill=1, anchor='ra')


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

    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    _draw_header(draw, now, fonts)

    y = _draw_hot_rows(draw, data, HEADER_RULE_Y + 8, fonts['body'])
    if data['news']:
        y = draw_section_header(draw, '新闻动态', MARGIN, y, RIGHT, fonts['body'], HEAD_H)
        y = draw_bullet_items(draw, data['news'], MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                              fonts['body'], BODY_LINE_H)
        y += SECTION_GAP

    if data['dyk'] and BODY_BOTTOM - y >= HEAD_H + BODY_LINE_H:
        y = draw_section_header(draw, '你知道吗？', MARGIN, y, RIGHT, fonts['body'], HEAD_H)
        draw_bullet_items(draw, data['dyk'], MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                          fonts['body'], BODY_LINE_H)

    _draw_footer(draw, now, fonts)
    return finalize_image_common(img, rotate=rotate, invert=invert)
