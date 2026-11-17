"""400×300 聚焦视图的共用版面：紧凑日期头与页脚。

聚焦视图（特色 / 你知道吗 / 新闻）只放一类内容，头部压成一行，
栏目名写在日期旁边，不加快讯条，把高度全部留给正文。
"""
from .daily.utils import measure_width

W, H = 400, 300
MARGIN = 16
RIGHT = W - MARGIN
TOP_BAR_H = 6
HEADER_RULE_Y = 52
FOOTER_RULE_Y = H - 30
BODY_BOTTOM = FOOTER_RULE_Y - 6

WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')


def draw_header(draw, now, fonts, title='维基百科'):
    """日期 + 栏目名（如「维基百科 · 特色条目」）+ 星期，压成一行。"""
    draw.rectangle([0, 0, W - 1, TOP_BAR_H - 1], fill=2)
    date_text = f'{now.month}月{now.day}日'
    draw.text((MARGIN, 8), date_text, font=fonts['head'], fill=1)
    label_x = MARGIN + measure_width(draw, date_text, fonts['head']) + 10
    draw.text((label_x, 18), title, font=fonts['body'], fill=2)
    draw.text((RIGHT, 20), WEEKDAYS[now.weekday()], font=fonts['body'], fill=1, anchor='ra')
    draw.line([(MARGIN, HEADER_RULE_Y), (RIGHT, HEADER_RULE_Y)], fill=1, width=2)
    draw.rectangle([MARGIN, HEADER_RULE_Y - 5, MARGIN + 40, HEADER_RULE_Y - 1], fill=1)


def draw_footer(draw, now, fonts):
    draw.line([(MARGIN, FOOTER_RULE_Y), (RIGHT, FOOTER_RULE_Y)], fill=1, width=1)
    draw.text((MARGIN, FOOTER_RULE_Y + 6), '维基百科 · zh.wikipedia.org',
              font=fonts['body'], fill=1)
    draw.text((RIGHT, FOOTER_RULE_Y + 6), now.strftime('%m-%d %H:%M'),
              font=fonts['body'], fill=1, anchor='ra')
