from PIL import ImageFont
import importlib

font_loader = importlib.import_module("modules.generate_views.font_loader")
get_root_font_path = font_loader.get_root_font_path
get_font = font_loader.get_font


def load_font(size):
    try:
        return get_font(size, get_root_font_path("font.ttf"))
    except Exception:
        return ImageFont.load_default()


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_safe_text(draw, xy, text, fill, font, img_width, img_height):
    x, y = xy
    text = str(text)
    tw, th = text_size(draw, text, font)
    if x + tw > img_width:
        x = max(0, img_width - tw - 2)
    if y + th > img_height:
        y = max(0, img_height - th - 2)
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    draw.text((x, y), text, fill=fill, font=font)
    return tw, th


def draw_label_value(draw, x, y, label, value, label_font, value_font, img_width, img_height, label_fill=2, value_fill=1, gap=6):
    draw_safe_text(draw, (x, y), label, fill=label_fill, font=label_font, img_width=img_width, img_height=img_height)
    label_w, label_h = text_size(draw, label, label_font)
    draw_safe_text(draw, (x + label_w + gap, y), value, fill=value_fill, font=value_font, img_width=img_width, img_height=img_height)
    value_h = text_size(draw, value, value_font)[1]
    return max(label_h, value_h)


def draw_rows(draw, x, y, rows, label_font, value_font, img_width, img_height, row_gap=8):
    current_y = y
    for label, value in rows:
        row_h = draw_label_value(draw, x, current_y, label, value, label_font, value_font, img_width, img_height)
        current_y += row_h + row_gap
    return current_y