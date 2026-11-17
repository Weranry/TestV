"""维基百科每日摘要 · 800×480 横屏。

版面结构：
1. 红色顶条 + 紧凑日期头（32px 日期、年份、星期）
2. 全宽快讯条：正在发生 / 最近逝世，各一行
3. 下方左右双栏：左栏「新闻动态 + 你知道吗？」，右栏「特色内容」

横屏宽度足够，双栏避免长行带来的阅读疲劳；栏目高度按剩余空间分配，
内容不足时自然上移，放不下时补省略号。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from .utils import (
    BODY_LINE_H,
    SECTION_GAP,
    draw_bullet_items,
    draw_paragraph,
    draw_section_header,
    draw_ticker,
    draw_wrapped_title,
    load_fonts,
)

W, H = 800, 480
MARGIN = 28
RIGHT = W - MARGIN
TOP_BAR_H = 6
HEADER_RULE_Y = 84
FOOTER_RULE_Y = H - 34
BODY_BOTTOM = FOOTER_RULE_Y - 8

COL_GAP = 28
COL_W = (RIGHT - MARGIN - COL_GAP) // 2
LEFT_RIGHT = MARGIN + COL_W
RIGHT_X = LEFT_RIGHT + COL_GAP

HOT_LABEL_WIDTH = 72
HOT_ROW_H = 22
HEAD_H = 28
SECTION_TITLE_LINE_H = 40
NEWS_SHARE = 0.55

WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')


def _draw_header(draw, now, fonts):
    draw.rectangle([0, 0, W - 1, TOP_BAR_H - 1], fill=2)
    draw.text((MARGIN, 12), '维基百科 · 每日摘要', font=fonts['body'], fill=2)
    draw.text((RIGHT, 12), str(now.year), font=fonts['body'], fill=2, anchor='ra')
    draw.text((MARGIN, 30), f'{now.month}月{now.day}日', font=fonts['head'], fill=1)
    draw.text((RIGHT, 30), WEEKDAYS[now.weekday()], font=fonts['head'], fill=1, anchor='ra')
    draw.line([(MARGIN, HEADER_RULE_Y), (RIGHT, HEADER_RULE_Y)], fill=1, width=2)
    draw.rectangle([MARGIN, HEADER_RULE_Y - 6, MARGIN + 64, HEADER_RULE_Y - 2], fill=1)


def _draw_footer(draw, now, fonts):
    draw.line([(MARGIN, FOOTER_RULE_Y), (RIGHT, FOOTER_RULE_Y)], fill=1, width=1)
    draw.text((MARGIN, FOOTER_RULE_Y + 8), '维基百科 · zh.wikipedia.org',
              font=fonts['body'], fill=1)
    draw.text((RIGHT, FOOTER_RULE_Y + 8), now.strftime('%m-%d %H:%M'),
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
        y += 4
        draw.line([(MARGIN, y), (RIGHT, y)], fill=1, width=1)
        y += 12
    else:
        y += 10
    return y


def _draw_left_column(draw, data, y, fonts):
    font = fonts['body']
    sections = [key for key in ('news', 'dyk') if data[key]]
    if not sections:
        return
    content_h = BODY_BOTTOM - y - len(sections) * HEAD_H - (len(sections) - 1) * SECTION_GAP
    content_h = max(0, content_h)
    news_h = int(content_h * NEWS_SHARE) // BODY_LINE_H * BODY_LINE_H if data['news'] else 0

    if data['news']:
        y = draw_section_header(draw, '新闻动态', MARGIN, y, LEFT_RIGHT, font, HEAD_H)
        bottom = BODY_BOTTOM if not data['dyk'] else y + max(news_h, BODY_LINE_H)
        y = draw_bullet_items(draw, data['news'], MARGIN, y, COL_W, bottom, font, BODY_LINE_H)
        if data['dyk']:
            y += SECTION_GAP

    if data['dyk']:
        y = draw_section_header(draw, '你知道吗？', MARGIN, y, LEFT_RIGHT, font, HEAD_H)
        draw_bullet_items(draw, data['dyk'], MARGIN, y, COL_W, BODY_BOTTOM, font, BODY_LINE_H)


def _draw_right_column(draw, data, y, fonts):
    featured = data['featured']
    if not featured:
        return
    y = draw_section_header(draw, featured['label'], RIGHT_X, y, RIGHT, fonts['body'], HEAD_H)
    if featured['title']:
        y = draw_wrapped_title(draw, featured['title'], RIGHT_X, y, COL_W,
                               fonts['head'], SECTION_TITLE_LINE_H, max_lines=2)
        y += 4
    if featured['text']:
        draw_paragraph(draw, featured['text'], RIGHT_X, y, COL_W, BODY_BOTTOM,
                       fonts['body'], BODY_LINE_H)


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_wikipedia_daily(page_url=kwargs.get('page_url'))
    now = now_in_timezone(tz)
    fonts = load_fonts()

    img, draw = create_canvas('h4xl', palette_type='bwr', cmode=cmode)
    _draw_header(draw, now, fonts)

    y = _draw_hot_rows(draw, data, HEADER_RULE_Y + 14, fonts['body'])
    _draw_left_column(draw, data, y, fonts)
    _draw_right_column(draw, data, y, fonts)

    _draw_footer(draw, now, fonts)
    return finalize_image_common(img, rotate=rotate, invert=invert)
