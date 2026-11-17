"""维基百科「你知道吗？」 · 400×300 横屏。

栏目名写在页头（「维基百科 · 你知道吗」），不再重复画分区标题；
不显示快讯条，正文占满剩余高度。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_wikipedia_daily
from ..daily.utils import (
    BODY_LINE_H,
    draw_bullet_items,
    draw_paragraph,
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


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = await fetch_wikipedia_daily(page_url=kwargs.get('page_url'))
    now = now_in_timezone(tz)
    fonts = load_fonts()

    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    draw_header(draw, now, fonts, title='维基百科 · 你知道吗')
    y = HEADER_RULE_Y + 8

    if data['dyk']:
        draw_bullet_items(draw, data['dyk'], MARGIN, y, RIGHT - MARGIN, BODY_BOTTOM,
                          fonts['body'], BODY_LINE_H)
    else:
        draw_paragraph(draw, '今日暂无「你知道吗」内容', MARGIN, y, RIGHT - MARGIN,
                       BODY_BOTTOM, fonts['body'], BODY_LINE_H)

    draw_footer(draw, now, fonts)
    return finalize_image_common(img, rotate=rotate, invert=invert)
