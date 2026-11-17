"""forecast 视图专用排版辅助：标题、日期跨度、单列温度的组合绘制。"""
from ..common import text_size, draw_at, draw_right, draw_centered


def forecast_title(n):
    if n == 2:
        return '两日预报'
    if n == 3:
        return '三日预报'
    return f'未来{n}日预报'


def date_span(daily):
    """'11-13 ~ 11-15'，取预报首尾日期"""
    if not daily:
        return ''
    first, last = daily[0]['date'], daily[-1]['date']
    if first == last:
        return first[5:]
    return f'{first[5:]} ~ {last[5:]}'


def draw_header(draw, data, n, margin, width, title_font, meta_font, y=8):
    """页眉：左「N日预报」，右「城市 · 日期跨度」"""
    draw_at(draw, (margin, y), forecast_title(n), title_font, fill=1)
    title_h = text_size(draw, forecast_title(n), title_font)[1]
    meta = f'{data["location"]["name"]} · {date_span(data["daily"])}'
    meta_h = text_size(draw, meta, meta_font)[1]
    draw_right(draw, width - margin, y + (title_h - meta_h), meta, meta_font, fill=1,
               max_width=width - margin * 3)


def draw_day_range_inline(draw, cx, y, day, hi_font, lo_font, gap=5):
    """'12°/2°' 单行居中：高值红、低值黑，字号相同靠颜色分层"""
    hi, lo = f"{int(round(day['tmax']))}°", f"{int(round(day['tmin']))}°"
    hi_w = text_size(draw, hi, hi_font)[0]
    sep_w = text_size(draw, '/', hi_font)[0]
    lo_w = text_size(draw, lo, lo_font)[0]
    total = hi_w + sep_w + lo_w + gap * 2
    x = cx - total // 2
    x += draw_at(draw, (x, y), hi, hi_font, fill=2)[0]
    x += draw_at(draw, (x, y), '/', hi_font, fill=1)[0]
    draw_at(draw, (x + gap, y), lo, lo_font, fill=1)


def draw_day_range_stacked(draw, cx, y_hi, y_lo, day, hi_font, lo_font):
    """高低温上下两行居中：红高黑低，大尺寸屏用"""
    draw_centered(draw, cx, y_hi, f"{int(round(day['tmax']))}°", hi_font, fill=2)
    draw_centered(draw, cx, y_lo, f"{int(round(day['tmin']))}°", lo_font, fill=1)
