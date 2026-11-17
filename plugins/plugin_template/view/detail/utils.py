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


def draw_panel(draw, x, y, width, title, body, title_font, body_font, img_width, img_height):
    draw_safe_text(draw, (x, y), title, fill=2, font=title_font, img_width=img_width, img_height=img_height)
    title_h = text_size(draw, title, title_font)[1]
    draw_safe_text(draw, (x, y + title_h + 6), body, fill=1, font=body_font, img_width=img_width, img_height=img_height)
    body_h = text_size(draw, body, body_font)[1]
    return title_h + 6 + body_h