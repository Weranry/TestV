"""current 视图专用排版辅助：页眉、温度区间、指标数据组装。"""
from ..common import text_size, draw_at, draw_right


def date_line(data):
    """'11月13日 周四'，取预报首日（当地日期）"""
    days = data.get('daily') or []
    if not days:
        return ''
    d = str(days[0].get('date', ''))
    try:
        _, m, day = d.split('-')
        return f'{int(m)}月{int(day)}日 {days[0].get("weekday", "")}'
    except ValueError:
        return d


def draw_header(draw, data, margin, width, title_font, date_font, y=8):
    """页眉：左侧城市，右侧日期，同一基线视觉高度对齐"""
    name = str(data['location']['name'])
    draw_at(draw, (margin, y), name, title_font, fill=1)
    title_h = text_size(draw, name, title_font)[1]
    date = date_line(data)
    date_h = text_size(draw, date, date_font)[1]
    draw_right(draw, width - margin, y + (title_h - date_h), date, date_font, fill=1)


def draw_range(draw, x, y, tmax, tmin, font, max_fill=2, min_fill=1, gap=8, align='right'):
    """'↑12° ↓2°'：最高温红、最低温黑。align='right' 时 x 为右缘，'left' 时为左缘"""
    lo = f'↓{int(round(tmin))}°'
    hi = f'↑{int(round(tmax))}°'
    lo_w = text_size(draw, lo, font)[0]
    hi_w = text_size(draw, hi, font)[0]
    if align == 'left':
        draw_at(draw, (x, y), hi, font, fill=max_fill)
        draw_at(draw, (x + hi_w + gap, y), lo, font, fill=min_fill)
    else:
        draw_at(draw, (x - lo_w, y), lo, font, fill=min_fill)
        draw_at(draw, (x - lo_w - gap - hi_w, y), hi, font, fill=max_fill)


def metric_items(current):
    """底部指标行数据：(label, value) 列表，视图只管排布。

    风向放进标签（风力·西北），数值只留速度——两行都短，窄列下不截断。
    """
    wind_dir = current.get('wind_dir') or ''
    wind_label = f'风力·{wind_dir}' if wind_dir else '风力'
    return [
        ('湿度', f"{current['humidity']}%"),
        (wind_label, f"{int(round(current['wind_speed']))}km/h"),
        ('气压', f"{current['pressure']}hPa"),
        ('降水', f"{current['precip']:.1f}mm"),
    ]
