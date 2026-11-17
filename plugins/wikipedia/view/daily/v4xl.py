"""维基百科每日摘要 · 480×800 竖屏。

版面结构（自上而下）：
1. 红色顶条 + 日期区（大号日期、年份、星期）
2. 快讯条：正在发生 / 最近逝世，各一行
3. 新闻动态、你知道吗、典范条目（或特色列表）三个分区

正文统一 16px / 22px 行高，分区标签 16px（红色），日期 48px，特色条目名称 32px，
均为 16 的整数倍。每个分区的行数由剩余高度动态分配，内容不足时自然上移，
内容过长时补省略号。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from .utils import (
    BODY_LINE_H,
    HEAD_H,
    SECTION_GAP,
    draw_bullet_items,
    draw_paragraph,
    draw_section_header,
    draw_ticker,
    draw_wrapped_title,
    load_fonts,
    wrap_text,
)

W, H = 480, 800
MARGIN = 24
RIGHT = W - MARGIN
TOP_BAR_H = 6
HEADER_RULE_Y = 112
FOOTER_RULE_Y = H - 38
BODY_BOTTOM = FOOTER_RULE_Y - 6
HOT_LABEL_WIDTH = 72
HOT_ROW_H = 22
SECTION_TITLE_LINE_H = 40
FEATURED_TEXT_LINES = 5
MIN_NEWS_LINES = 4
MIN_DYK_LINES = 3

WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')


def _draw_header(draw, now, fonts):
    draw.rectangle([0, 0, W - 1, TOP_BAR_H - 1], fill=2)
    draw.text((MARGIN, 18), '维基百科 · 每日摘要', font=fonts['body'], fill=2)
    draw.text((RIGHT, 18), str(now.year), font=fonts['body'], fill=2, anchor='ra')
    draw.text((MARGIN, 42), f'{now.month}月{now.day}日', font=fonts['date'], fill=1)
    draw.text((RIGHT, 56), WEEKDAYS[now.weekday()], font=fonts['head'], fill=1, anchor='ra')
    draw.line([(MARGIN, HEADER_RULE_Y), (RIGHT, HEADER_RULE_Y)], fill=1, width=2)
    draw.rectangle([MARGIN, HEADER_RULE_Y - 6, MARGIN + 56, HEADER_RULE_Y - 2], fill=1)


def _draw_footer(draw, now, fonts):
    draw.line([(MARGIN, FOOTER_RULE_Y), (RIGHT, FOOTER_RULE_Y)], fill=1, width=1)
    draw.text((MARGIN, FOOTER_RULE_Y + 8), '维基百科 · zh.wikipedia.org',
              font=fonts['body'], fill=1)
    draw.text((RIGHT, FOOTER_RULE_Y + 8), now.strftime('%m-%d %H:%M'),
              font=fonts['body'], fill=1, anchor='ra')


def _draw_ticker(draw, data, y, font):
    has_ongoing = bool(data['ongoing'])
    has_deaths = bool(data['deaths'])
    if has_ongoing:
        draw_ticker(draw, '正在发生', data['ongoing'], MARGIN, y, RIGHT, font, HOT_LABEL_WIDTH)
        y += HOT_ROW_H
    if has_deaths:
        draw_ticker(draw, '最近逝世', data['deaths'], MARGIN, y, RIGHT, font, HOT_LABEL_WIDTH)
        y += HOT_ROW_H
    if has_ongoing or has_deaths:
        y += 4
        draw.line([(MARGIN, y), (RIGHT, y)], fill=1, width=1)
        y += 16
    else:
        y += 12
    return y


def _featured_title_lines(draw, featured, font):
    if not featured or not featured.get('title'):
        return 0
    lines = wrap_text(draw, featured['title'], font, W - 2 * MARGIN)
    return min(2, len(lines))


def _allocate(draw, data, top, fonts):
    """按剩余高度给三个分区分配正文行高（像素）。

    特色条目固定保留标题 + 5 行正文；余下空间按 55/45 分给新闻动态和你知道吗。
    """
    section_count = sum(bool(data[key]) for key in ('news', 'dyk', 'featured'))
    gaps = max(0, section_count - 1)
    available = BODY_BOTTOM - top - section_count * HEAD_H - gaps * SECTION_GAP
    if data['featured']:
        title_lines = _featured_title_lines(draw, data['featured'], fonts['head'])
        featured_h = title_lines * SECTION_TITLE_LINE_H + 4 + FEATURED_TEXT_LINES * BODY_LINE_H
    else:
        featured_h = 0
    remaining = max(0, available - featured_h)
    news_lines = max(MIN_NEWS_LINES, int(remaining * 0.55) // BODY_LINE_H)
    dyk_lines = max(MIN_DYK_LINES, remaining // BODY_LINE_H - news_lines)
    return news_lines * BODY_LINE_H, dyk_lines * BODY_LINE_H


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_wikipedia_daily(page_url=kwargs.get('page_url'))
    now = now_in_timezone(tz)
    fonts = load_fonts()

    img, draw = create_canvas('v4xl', palette_type='bwr', cmode=cmode)
    _draw_header(draw, now, fonts)

    y = _draw_ticker(draw, data, HEADER_RULE_Y + 12, fonts['body'])
    news_h, dyk_h = _allocate(draw, data, y, fonts)

    if data['news']:
        y = draw_section_header(draw, '新闻动态', MARGIN, y, RIGHT, fonts['body'])
        y = draw_bullet_items(draw, data['news'], MARGIN, y, RIGHT - MARGIN, y + news_h,
                              fonts['body'], BODY_LINE_H)
        y += SECTION_GAP

    if data['dyk']:
        y = draw_section_header(draw, '你知道吗？', MARGIN, y, RIGHT, fonts['body'])
        y = draw_bullet_items(draw, data['dyk'], MARGIN, y, RIGHT - MARGIN, y + dyk_h,
                              fonts['body'], BODY_LINE_H)
        y += SECTION_GAP

    featured = data['featured']
    if featured:
        y = draw_section_header(draw, featured['label'], MARGIN, y, RIGHT, fonts['body'])
        if featured['title']:
            y = draw_wrapped_title(draw, featured['title'], MARGIN, y, RIGHT - MARGIN,
                                   fonts['head'], SECTION_TITLE_LINE_H, max_lines=2)
            y += 4
        if featured['text']:
            draw_paragraph(draw, featured['text'], MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                           fonts['body'], BODY_LINE_H)

    _draw_footer(draw, now, fonts)
    return finalize_image_common(img, rotate=rotate, invert=invert)
