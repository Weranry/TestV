"""schedule 视图渲染引擎（黑白时间轴版式）。

版式参考手机端「今日课程」小组件：只列出当天真正要上的课，左侧一条黑色竖条做视觉
锚点，课名在上、教室与教师在下，右侧上下两行显示开始 / 结束时间。

- 只画有课的节次：空节次留白，不出现一排空行，节次数量再多也不会挤爆版面。
- 三档行高自适应：宽裕时课名 32px，一般时课名 16px + 两行，紧张时单行压缩。
- 没配置时间时，右侧改显示节次名（M1 / A1 ...），旧课程表照常可用。
- 纯黑白：不画任何彩色，分隔靠留白与竖条，不用满屏横线。
所有字号只用 16 的整数倍。
"""

from modules.generate_views.font_loader import get_font, get_root_font_path

FONT_PATH = get_root_font_path('font.ttf')

BLACK = 1
WHITE = 0

TITLE_SIZE = 16
INFO_SIZE = 16
NAME_SIZES = (32, 16)
ACCENT_WIDTH = 4
MAX_ROW_HEIGHT = 88


def load_font(size):
    """按字号加载字体；字号须为 16 的整数倍。"""
    return get_font(size, FONT_PATH)


def fit_text(draw, text, font, max_width, ellipsis='..'):
    """单行文本兜底：放不下就二分找最长可放前缀并补 `..`，绝不越界。"""
    text = str(text)
    if max_width <= 0:
        return ''
    if draw.textlength(text, font=font) <= max_width:
        return text
    if draw.textlength(ellipsis, font=font) > max_width:
        return ''
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if draw.textlength(text[:mid] + ellipsis, font=font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low] + ellipsis


def wrap_text(draw, text, font, max_width, max_lines):
    """按字符折行，最多 max_lines 行；额度用完后把剩余内容压进最后一行并截断。"""
    if not text or max_width <= 0:
        return []
    lines, current = [], ''
    for index, char in enumerate(text):
        if draw.textlength(current + char, font=font) <= max_width:
            current += char
        elif len(lines) + 1 >= max_lines:
            current += text[index:]
            break
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return [fit_text(draw, line, font, max_width) for line in lines]


def _distribute(total, count):
    """把 total 像素均分给 count 行，余数从前往后各加 1，总和正好等于 total。"""
    base, extra = divmod(max(total, 0), count)
    return [base + (1 if index < extra else 0) for index in range(count)]


def _entry_text(entry, separator=' · '):
    """课程 → (课名, 教室 · 教师)；窄屏用空格分隔，省下的宽度足够放下完整教师名。"""
    name = str(entry.get('name') or '')
    details = [str(entry[key]) for key in ('room', 'teacher') if entry.get(key)]
    return name, separator.join(details)


def _side_texts(entry):
    """右侧时间列的文字：有时间就上下两行开始 / 结束，否则退回节次名。"""
    start, end = entry.get('start'), entry.get('end')
    if start and end:
        return [start, end]
    if start or end:
        return [start or end]
    label = str(entry.get('label') or '')
    return [label] if label else []


def _range_text(entry):
    """单行版式用的时间串：08:00-08:45 / 08:00 / M1。"""
    start, end = entry.get('start'), entry.get('end')
    if start and end:
        return f'{start}-{end}'
    if start or end:
        return start or end
    return str(entry.get('label') or '')


def _start_text(entry):
    """窄屏单行版式只留开始时间，把省下的宽度让给课名。"""
    return str(entry.get('start') or entry.get('end') or entry.get('label') or '')


def _draw_header(draw, width, margin, date_info):
    """标题行：左侧「10.23」+ 反白星期标签，右侧周次。"""
    date_text = str(date_info.get('todayDate', ''))
    if len(date_text) >= 10:
        date_text = date_text[5:].replace('-', '.')
    weekday = f"周{date_info.get('dayOfWeek', '?')}"
    week = f"第 {date_info.get('weekNumber', '?')} 周"

    font = load_font(TITLE_SIZE)
    draw.text((margin, margin), date_text, font=font, fill=BLACK, anchor='lt')

    chip_x = margin + draw.textlength(date_text, font=font) + 8
    chip_w = draw.textlength(weekday, font=font) + 12
    chip_h = TITLE_SIZE + 8
    draw.rounded_rectangle([chip_x, margin, chip_x + chip_w, margin + chip_h],
                           radius=4, fill=BLACK)
    draw.text((chip_x + 6, margin + 4), weekday, font=font, fill=WHITE, anchor='lt')

    # 窄屏放不下「第 11 周」时退成「11周」，避免贴边截断
    right_budget = width - margin * 2 - (chip_x + chip_w - margin) - 12
    if draw.textlength(week, font=font) > right_budget:
        week = f"{date_info.get('weekNumber', '?')}周"
    draw.text((width - margin, margin + chip_h / 2),
              fit_text(draw, week, font, right_budget), font=font, fill=BLACK, anchor='rm')

    return margin + chip_h


def _draw_empty(draw, width, top, bottom):
    """整天没课时居中给一句说明。"""
    font = load_font(INFO_SIZE)
    draw.text((width / 2, (top + bottom) / 2), '今天没有课', font=font, fill=BLACK, anchor='mm')


def _draw_note(draw, width, height, margin, note):
    """课多到一屏放不下时，在右下角标出被省略的节次数。"""
    if not note:
        return
    font = load_font(INFO_SIZE)
    draw.text((width - margin, height - margin), note, font=font, fill=BLACK, anchor='rb')


def _draw_accent(draw, x, top, height):
    """课程左侧的黑色竖条，替代彩色块，成本最低的视觉锚点。"""
    height = int(height)
    if height <= 0:
        return
    draw.rectangle([x, top, x + ACCENT_WIDTH - 1, top + height - 1], fill=BLACK)


def _side_column_width(draw, entries, font):
    texts = [text for entry in entries for text in _side_texts(entry)]
    return max((draw.textlength(text, font=font) for text in texts), default=0)


def _pick_name_font(draw, names, budget, row_height):
    """课名字号：行高与列宽都够就用 32，否则退回 16（只在这两档之间选）。"""
    if row_height >= NAME_SIZES[0] + INFO_SIZE + 12 and budget > 0:
        large = load_font(NAME_SIZES[0])
        if names and max(draw.textlength(name, font=large) for name in names) <= budget:
            return large
    return load_font(NAME_SIZES[1])


def _draw_stacked_row(draw, width, margin, row_y, row_height, entry, details,
                      name_font, time_width):
    """两行版式：课名 + 教室教师，右侧时间上下对齐。"""
    name, info = details
    info_font = load_font(INFO_SIZE)
    text_x = margin + ACCENT_WIDTH + 10
    gap = 12 if width >= 300 else 8
    name_width = width - margin - time_width - (gap if time_width else 0) - text_x

    max_lines = 2 if row_height >= name_font.size * 2 + INFO_SIZE + 16 else 1
    lines = [fit_text(draw, name, name_font, name_width)]
    if max_lines > 1 and lines[0] != name:
        lines = wrap_text(draw, name, name_font, name_width, 2)

    # 教室与教师放不下时，行高允许就折成两行，而不是直接截断
    info_lines = []
    if info:
        info_lines = [info]
        allowed = row_height >= len(lines) * name_font.size + INFO_SIZE * 2 + 12
        if allowed and draw.textlength(info, font=info_font) > name_width:
            # 优先在教室与教师之间的空格处断开，避免把「老师」拆成「老」+「师」
            head, _, tail = info.partition(' ')
            if (tail and draw.textlength(head, font=info_font) <= name_width
                    and draw.textlength(tail, font=info_font) <= name_width):
                info_lines = [head, tail]
            else:
                info_lines = wrap_text(draw, info, info_font, name_width, 2)

    content_height = (len(lines) * name_font.size
                      + (4 + len(info_lines) * INFO_SIZE if info_lines else 0))
    content_top = row_y + max((row_height - content_height) / 2, 6)

    _draw_accent(draw, margin, content_top + 2, content_height - 4)

    line_y = content_top
    for line in lines:
        draw.text((text_x, line_y), line, font=name_font, fill=BLACK, anchor='lt')
        line_y += name_font.size
    for info_line in info_lines:
        draw.text((text_x, line_y + 4), info_line, font=info_font, fill=BLACK, anchor='lt')
        line_y += INFO_SIZE

    side = _side_texts(entry)
    right = width - margin
    if len(side) == 1:
        draw.text((right, content_top + content_height / 2), side[0],
                  font=info_font, fill=BLACK, anchor='rm')
    elif len(side) >= 2:
        if info:
            centers = [content_top + name_font.size / 2,
                       content_top + content_height - INFO_SIZE / 2]
        else:
            centers = [content_top + content_height / 2 - INFO_SIZE / 2,
                       content_top + content_height / 2 + INFO_SIZE / 2]
        for text, center_y in zip(side[:2], centers):
            draw.text((right, center_y), text, font=info_font, fill=BLACK, anchor='rm')


def _draw_compact_row(draw, width, margin, row_y, row_height, entry, details):
    """单行版式：课名与教室教师合并成一行，右侧时间区间。"""
    name, info = details
    font = load_font(INFO_SIZE)
    text_x = margin + ACCENT_WIDTH + 10
    right_text = _start_text(entry) if width < 300 else _range_text(entry)
    right_width = draw.textlength(right_text, font=font) if right_text else 0
    budget = width - margin - right_width - (12 if right_width else 0) - text_x

    # 窄屏单行版式挤不下教室教师，也不留「· ..」这种半截残渣，只保留课名与开始时间
    combined = name if width < 300 else (f'{name} · {info}' if info else name)
    center_y = row_y + row_height / 2
    draw.text((text_x, center_y), fit_text(draw, combined, font, budget),
              font=font, fill=BLACK, anchor='lm')
    if right_text:
        draw.text((width - margin, center_y), right_text, font=font, fill=BLACK, anchor='rm')

    _draw_accent(draw, margin, center_y - INFO_SIZE / 2 + 2, INFO_SIZE - 4)


def _render_list(draw, width, height, schedule_data):
    margin = 16 if width >= 400 else 8
    entries = schedule_data.get('entries') or []

    header_bottom = _draw_header(draw, width, margin, schedule_data.get('dateInfo', {}))
    rows_top = header_bottom + 10
    rows_bottom = height - margin

    if not entries:
        _draw_empty(draw, width, rows_top, rows_bottom)
        return

    info_font = load_font(INFO_SIZE)
    # 节次再多也不能把文字压成一团：每行至少留出 16px 字高 + 4px 间隙
    min_row = INFO_SIZE + 4
    max_rows = max(1, (rows_bottom - rows_top) // min_row)
    hidden = max(len(entries) - max_rows, 0)
    if hidden:
        rows_bottom -= INFO_SIZE + 4
        max_rows = max(1, (rows_bottom - rows_top) // min_row)
        hidden = max(len(entries) - max_rows, 0)
        entries = entries[:max_rows]

    row_heights = [min(value, MAX_ROW_HEIGHT)
                   for value in _distribute(rows_bottom - rows_top, len(entries))]
    row_height = min(row_heights)

    separator = ' ' if width < 300 else ' · '
    details = [_entry_text(entry, separator) for entry in entries]
    names = [name for name, _ in details]

    note = f'还有 {hidden} 节' if hidden else ''

    if row_height < INFO_SIZE * 2 + 8:
        # 行高不给两行文字留余地时压缩成单行
        row_y = rows_top
        for entry, entry_details in zip(entries, details):
            _draw_compact_row(draw, width, margin, row_y, row_height, entry, entry_details)
            row_y += row_height
        _draw_note(draw, width, height, margin, note)
        return

    time_width = _side_column_width(draw, entries, info_font)
    text_x = margin + ACCENT_WIDTH + 10
    gap = 12 if width >= 300 else 8
    name_budget = width - margin - time_width - (gap if time_width else 0) - text_x
    name_font = _pick_name_font(draw, names, name_budget, row_height)

    row_y = rows_top
    for entry, entry_details in zip(entries, details):
        _draw_stacked_row(draw, width, margin, row_y, row_height, entry, entry_details,
                          name_font, time_width)
        row_y += row_height
    _draw_note(draw, width, height, margin, note)


def render_schedule(canvas, draw, schedule_data):
    """渲染当天课程列表；横竖屏同一套版式，靠宽度自动收缩字号与时间列。"""
    width, height = canvas.size
    _render_list(draw, width, height, schedule_data)
