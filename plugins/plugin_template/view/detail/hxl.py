import importlib

canvas_factory = importlib.import_module("modules.generate_views.canvas_factory")
create_canvas = canvas_factory.create_canvas
finalize_image_common = canvas_factory.finalize_image_common

from ...lib.demo_data import build_demo_data
from .utils import load_font, draw_safe_text, draw_panel, text_size


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    data = build_demo_data(
        a=kwargs.get('a'),
        b=kwargs.get('b'),
        tz=tz,
        title=kwargs.get('title'),
        subtitle=kwargs.get('subtitle'),
        left=kwargs.get('left'),
        right=kwargs.get('right'),
        note=kwargs.get('note'),
    )
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)

    title_font = load_font(32)
    body_font = load_font(16)
    small_font = load_font(16)

    draw_safe_text(draw, (16, 12), str(data['meta']['title']), fill=2, font=title_font, img_width=img.width, img_height=img.height)
    left_y = 56
    right_y = 56
    draw_panel(draw, 16, left_y, 160, 'Left', data['detail']['left'], body_font, body_font, img.width, img.height)
    draw_panel(draw, 200, right_y, 160, 'Right', data['detail']['right'], body_font, body_font, img.width, img.height)

    note = str(data['detail']['note'])
    note_w, note_h = text_size(draw, note, small_font)
    draw_safe_text(draw, (img.width - 16 - note_w, img.height - 16 - note_h), note, fill=1, font=small_font, img_width=img.width, img_height=img.height)

    return finalize_image_common(img, rotate=rotate, invert=invert)