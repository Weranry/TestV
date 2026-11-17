"""维基百科特色内容 · 400×300 横屏。

栏目名写在页头（「维基百科 · 特色条目」），正文直接以 32px 标题开场，
不再重复画分区标题；特色内容是整屏主角，不显示快讯条。
首页特色区块缺失时显示占位文字，避免整屏只剩页眉页脚。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from ..daily.utils import (
    BODY_LINE_H,
    draw_paragraph,
    draw_wrapped_title,
    load_fonts,
)
from ..focus_h2xl import (
    BODY_BOTTOM,
    HEADER_RULE_Y,
    MARGIN,
    RIGHT,
    draw_footer,
    draw_header,
)

TITLE_LINE_H = 40
TITLE_MAX_LINES = 2


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_wikipedia_daily(page_url=kwargs.get('page_url'))
    now = now_in_timezone(tz)
    fonts = load_fonts()

    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    draw_header(draw, now, fonts, title='维基百科 · 特色条目')
    y = HEADER_RULE_Y + 8

    featured = data['featured']
    if featured:
        if featured['title']:
            y = draw_wrapped_title(draw, featured['title'], MARGIN, y, RIGHT - MARGIN,
                                   fonts['head'], TITLE_LINE_H, max_lines=TITLE_MAX_LINES)
            y += 4
        if featured['text']:
            draw_paragraph(draw, featured['text'], MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                           fonts['body'], BODY_LINE_H)
    else:
        draw_paragraph(draw, '今日暂无特色内容', MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                       fonts['body'], BODY_LINE_H)

    draw_footer(draw, now, fonts)
    return finalize_image_common(img, rotate=rotate, invert=invert)
