"""HXL / H2XL 共用的绘制辅助：字体、文本测量、赛道折线与格式化。

配色沿用框架 `bwr` 画布：0=白 1=黑 2=红。
"""
from modules.generate_views import font_loader
from ...lib.track_map import laps_for, project

P_WHITE = 0
P_BLACK = 1
P_RED = 2

_WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def load_font(size):
    return font_loader.get_font(size, font_loader.get_root_font_path('font.ttf'))


def text_width(draw, text, font):
    return draw.textlength(str(text), font=font)


def fit_font(draw, text, font, max_width, min_size):
    """先按给定字号，放不下就按 16 的整数倍逐级降到 min_size"""
    size = font.size
    while size > min_size and text_width(draw, text, font) > max_width:
        size = max(size - 16, min_size)
        font = load_font(size)
    return font


def fit_text(draw, text, font, max_width, ellipsis='..'):
    """单行文本的兜底：先整串放，超宽就按字符截断并以 `..` 结尾。

    二分找到「能放下的最长前缀 + 省略号」，比逐字回退少测一轮屏；任何赛事名 / 赛道名 /
    地点都不会顶出画布。连省略号都放不下时返回空串，宁可留白也不越界。
    """
    text = str(text)
    if text_width(draw, text, font) <= max_width:
        return text
    if text_width(draw, ellipsis, font) > max_width:
        return ''
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if text_width(draw, text[:mid] + ellipsis, font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low] + ellipsis


def draw_text(draw, xy, text, font, fill=P_BLACK):
    draw.text(xy, str(text), font=font, fill=fill)


def draw_right(draw, x_right, y, text, font, fill=P_BLACK):
    text = str(text)
    draw.text((x_right - text_width(draw, text, font), y), text, font=font, fill=fill)


def fmt_datetime(moment):
    if moment is None:
        return '--'
    return f"{moment.strftime('%m-%d')} {_WEEKDAYS[moment.weekday()]} {moment.strftime('%H:%M')}"


def fmt_short_time(moment):
    """列表用，不重复日期时也能看清是哪天"""
    if moment is None:
        return '--'
    return f"{moment.strftime('%m-%d')} {moment.strftime('%H:%M')}"


def fmt_countdown(days):
    if days is None:
        return ''
    if days < 0:
        return '已结束'
    if days == 0:
        return '今天'
    if days == 1:
        return '明天'
    return f'还有 {days} 天'


def fmt_round(round_no, total_rounds):
    if not round_no:
        return ''
    return f'第 {round_no} 站 / 共 {total_rounds} 站'


def fmt_circuit_stats(circuit_id, length_m):
    """赛道基本资料：长度（km）+ 由长度推出的正赛圈数"""
    if not length_m:
        return ''
    length_text = f'{length_m / 1000.0:.3f} km'
    laps = laps_for(circuit_id, length_m)
    return f'{length_text} · {laps} 圈' if laps else length_text


def draw_progress(draw, x, y, width, height, value, total):
    """赛季进度条：底框 + 红色已赛场次"""
    draw.rectangle([x, y, x + width, y + height], outline=P_BLACK, width=1)
    if not total:
        return
    filled = int(round((width - 2) * min(max(value, 0), total) / total))
    if filled > 0:
        draw.rectangle([x + 1, y + 1, x + filled, y + height - 1], fill=P_RED)


def draw_track(draw, points, x, y, width, height, fill=P_BLACK, line_width=2):
    """把赛道轮廓投影进 (x, y, width, height) 画框并闭合描边"""
    pts = project(points, width, height)
    if len(pts) < 2:
        return
    shifted = [(x + px, y + py) for px, py in pts]
    shifted.append(shifted[0])
    draw.line(shifted, fill=fill, width=line_width)
