"""openmeteo 视图共用排版原语。

墨水屏排版的美观度几乎全部来自**视觉对齐**：PIL 默认按字身框（advance）
定位，而 CJK、数字、图标字体的字身框与墨迹框差异很大——直接 `draw.text`
会出现「看起来没对齐」的一两个像素偏差。这里的 `draw_at` 系列一律按
**墨迹包围盒**落位，所有视图共用同一套口径。

调色板约定（bwr）：fill=1 黑、fill=2 红。红色只做点缀（温度、分隔强调），
大面积文字保持黑色，保证黑白屏（cmode=bw）下信息层级不塌。
"""
import importlib

font_loader = importlib.import_module("modules.generate_views.font_loader")
get_root_font_path = font_loader.get_root_font_path
get_font = font_loader.get_font


def load_font(size):
    try:
        return get_font(size, get_root_font_path("font.ttf"))
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def load_icon_font(size):
    return get_font(size, get_root_font_path("weather-icon.ttf"))


def text_size(draw, text, font):
    """墨迹视觉尺寸（宽, 高）"""
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_at(draw, xy, text, font, fill):
    """按墨迹左上角落位绘制文字，返回 (w, h)。超出画布右缘时自动截断加省略号。"""
    text = str(text)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = xy[0] - bbox[0], xy[1] - bbox[1]
    draw.text((x, y), text, fill=fill, font=font)
    return w, h


def fit_text(draw, text, font, max_width):
    """超宽时逐字截断并补省略号"""
    text = str(text)
    if text_size(draw, text, font)[0] <= max_width:
        return text
    while text and text_size(draw, text + '…', font)[0] > max_width:
        text = text[:-1]
    return (text + '…') if text else '…'


def draw_right(draw, right_x, y, text, font, fill, max_width=None):
    """右对齐：墨迹右缘贴 right_x"""
    text = str(text)
    if max_width:
        text = fit_text(draw, text, font, max_width)
    w, h = text_size(draw, text, font)
    draw_at(draw, (right_x - w, y), text, font, fill)
    return w, h


def draw_centered(draw, cx, y, text, font, fill, max_width=None):
    """水平居中于 cx"""
    text = str(text)
    if max_width:
        text = fit_text(draw, text, font, max_width)
    w, h = text_size(draw, text, font)
    draw_at(draw, (cx - w // 2, y), text, font, fill)
    return w, h


def draw_icon(draw, cx, cy, glyph, font, fill=1):
    """图标按墨迹框居中于 (cx, cy)——天气图标字形上下留白差异大，必须实测居中"""
    bbox = draw.textbbox((0, 0), str(glyph), font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - w // 2 - bbox[0], cy - h // 2 - bbox[1]), str(glyph), fill=fill, font=font)
    return w, h


def divider(draw, y, x0, x1, fill=1):
    draw.line((x0, y, x1, y), fill=fill, width=1)


def vdivider(draw, x, y0, y1, fill=1):
    draw.line((x, y0, x, y1), fill=fill, width=1)


def fmt_temp(value):
    return f"{int(round(value))}°"


def draw_temp_block(draw, x, y, value, unit, num_font, unit_font,
                    num_fill=1, unit_fill=2, gap=2):
    """大数字 + 小单位（°C）：单位顶缘贴数字顶缘，形成一体感。

    数字本身不带度数——度数完全交给单位，避免出现 '8° °C' 的重复。
    """
    text = str(int(round(value)))
    num_w, num_h = draw_at(draw, (x, y), text, num_font, num_fill)
    unit_w, _ = draw_at(draw, (x + num_w + gap, y + 2), unit, unit_font, unit_fill)
    return num_w + gap + unit_w


def draw_metric_columns(draw, x0, x1, y, items, label_font, value_font,
                        label_fill=1, value_fill=1, gap_ratio=0.45):
    """等宽指标列：每列 (label, value) 居中排布，列间均分 x0..x1。

    label 在上、value 在下，垂直间距按两字号高度比例分配，
    保证不同字号组合下视觉节奏一致。
    """
    n = len(items)
    if n == 0:
        return
    col_w = (x1 - x0) // n
    label_h = text_size(draw, '国', label_font)[1]
    value_h = text_size(draw, '国', value_font)[1]
    value_y = y + label_h + max(2, int(label_h * gap_ratio))
    for i, (label, value) in enumerate(items):
        cx = x0 + col_w * i + col_w // 2
        draw_centered(draw, cx, y, label, label_font, label_fill, max_width=col_w - 6)
        draw_centered(draw, cx, value_y, value, value_font, value_fill, max_width=col_w - 6)
