"""HXL / H2XL 共用的画布辅助。

画布固定 `bwr` 三色（0=白 1=黑 2=红），图上一切内容都由 `drawer.py` 画。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common


def create_weather_canvas(size_key, cmode=None):
    return create_canvas(size_key, palette_type='bwr', cmode=cmode)


def finalize_image(img, rotate=0, invert=False):
    return finalize_image_common(img, rotate=rotate, invert=invert)
