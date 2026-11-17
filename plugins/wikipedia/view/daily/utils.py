"""v4xl 版面工具：中文折行、省略号、分区标题、快讯条与列表绘制。

折行按「词元」推进：英文/数字串保持完整（Gen.G、2026），中文逐字断行；
同时避免标点出现在行首、开引号/开括号出现在行尾。
"""
import re

from modules.generate_views.font_loader import get_font, get_root_font_path

FONT_PATH = get_root_font_path('font.ttf')

# 正文字号 16 是框架要求的 16 的整数倍；行高 22 在 480 宽的竖屏上密度合适
BODY_LINE_H = 22
ITEM_GAP = 6
HEAD_H = 30
SECTION_GAP = 14

# 不能出现在行首 / 行尾的标点
_NO_LINE_START = set('，。、；：？！…—·）》」』】”’%,.;:?!)]}')
_NO_LINE_END = set('（《「『【“‘([{')

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-'’][A-Za-z0-9]+)*|[ \t]+|[\s\S]")


def load_fonts():
    return {
        'body': get_font(16, FONT_PATH),
        'head': get_font(32, FONT_PATH),
        'date': get_font(48, FONT_PATH),
    }


def measure_width(draw, text, font):
    """统一用 textbbox 量文本宽度（框架要求，禁止 textlength）。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text(draw, text, font, max_width):
    """把一段文本折成若干行，宽度不超过 max_width。"""
    if not text:
        return []
    lines, line = [], ''
    for token in _TOKEN_RE.findall(text):
        if token.isspace():
            if line and not line.endswith(' '):
                line += ' '
            continue
        candidate = line + token
        if measure_width(draw, candidate, font) <= max_width:
            line = candidate
            continue
        if not line:
            # 单个词元比整行还宽（超长英文/数字串）：退化成逐字符切
            for char in token:
                if line and measure_width(draw, line + char, font) > max_width:
                    lines.append(line)
                    line = char
                else:
                    line += char
            continue
        if token in _NO_LINE_START:
            # 标点不能出现在行首：把上一行最后一个字符一起带下来
            carry = line[-1]
            head = line[:-1].rstrip()
            if head:
                lines.append(head)
            line = carry + token
            if measure_width(draw, line, font) > max_width:
                lines.append(carry)
                line = token
        elif line[-1] in _NO_LINE_END:
            # 开引号/开括号不能留在行尾
            carry = line[-1]
            head = line[:-1].rstrip()
            if head:
                lines.append(head)
            line = carry + token
        else:
            lines.append(line.rstrip())
            line = token
    if line.strip():
        lines.append(line.rstrip())
    return lines


def ellipsize(draw, text, font, max_width):
    """把 text 裁到 max_width 内并补省略号（调用方只在需要截断时使用）。"""
    text = (text or '').rstrip()
    while text and measure_width(draw, text + '…', font) > max_width:
        text = text[:-1].rstrip()
    return f'{text}…' if text else '…'


def draw_section_header(draw, label, x, y, right, font, head_h=HEAD_H):
    """红色小号分区标签 + 一条延伸到右边的细线；head_h 供不同尺寸压缩间距。"""
    max_label_w = right - x - 12
    label = ellipsize(draw, label, font, max_label_w) \
        if measure_width(draw, label, font) > max_label_w else label
    draw.text((x, y + 2), label, font=font, fill=2)
    label_w = measure_width(draw, label, font)
    line_x = x + label_w + 12
    if line_x < right:
        draw.line([(line_x, y + 12), (right, y + 12)], fill=1, width=1)
    return y + head_h


def draw_ticker(draw, label, items, x, y, right, font, label_width=72):
    """快讯条一行：红色标签（正在发生 / 最近逝世）+ 单行内容，超出部分省略。"""
    draw.text((x, y), label, font=font, fill=2)
    if not items:
        return
    text = ' · '.join(items)
    available = right - (x + label_width)
    if available <= 0:
        return
    line = text if measure_width(draw, text, font) <= available \
        else ellipsize(draw, text, font, available)
    draw.text((x + label_width, y), line, font=font, fill=1)


def draw_headline_items(draw, items, x, y, width, bottom, font, line_h, gap=2,
                        bullet='·', fill=1):
    """单行标题列表：每条压成一行，超宽补省略号；放不下就停。"""
    bullet_width = 14
    text_width = width - bullet_width
    for item in items:
        if y + line_h > bottom:
            break
        text = item if measure_width(draw, item, font) <= text_width \
            else ellipsize(draw, item, font, text_width)
        draw.text((x, y), bullet, font=font, fill=fill)
        draw.text((x + bullet_width, y), text, font=font, fill=fill)
        y += line_h + gap
    return y


def draw_bullet_items(draw, items, x, y, width, bottom, font, line_h, gap=ITEM_GAP,
                      bullet='·', fill=1):
    """画带「·」前缀的列表；放不下时在最后一行补省略号，绝不越界。"""
    bullet_width = 14
    text_x = x + bullet_width
    text_width = width - bullet_width
    for index, item in enumerate(items):
        if y + line_h > bottom:
            break
        lines = wrap_text(draw, item, font, text_width)
        if not lines:
            continue
        allowed = int((bottom - y) // line_h)
        truncated = len(lines) > allowed
        if truncated:
            lines = lines[:allowed]
            if not lines:
                break
            lines[-1] = ellipsize(draw, lines[-1], font, text_width)
        draw.text((x, y), bullet, font=font, fill=fill)
        for line in lines:
            draw.text((text_x, y), line, font=font, fill=fill)
            y += line_h
        if truncated:
            break
        if index < len(items) - 1 and y + gap + line_h <= bottom:
            y += gap
    return y


def draw_paragraph(draw, text, x, y, width, bottom, font, line_h, fill=1):
    """画一段折行正文；放不下时在最后一行补省略号，绝不越界。"""
    lines = wrap_text(draw, text, font, width)
    if not lines:
        return y
    allowed = int((bottom - y) // line_h)
    if allowed <= 0:
        return y
    truncated = len(lines) > allowed
    if truncated:
        lines = lines[:allowed]
        lines[-1] = ellipsize(draw, lines[-1], font, width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def draw_wrapped_title(draw, text, x, y, width, font, line_h, max_lines, fill=1):
    lines = wrap_text(draw, text, font, width)
    if not lines:
        return y
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(draw, lines[-1], font, width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y
