from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_calendar_data


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('m', palette_type='bwr', cmode=cmode)
    title_font = get_font_global(18, font_path=FONT_PATH)
    content_font = get_font_global(15, font_path=FONT_PATH)
    large_font = get_font_global(54, font_path=FONT_PATH)
    small_font = get_font_global(12, font_path=FONT_PATH)

    solar, lunar, ganzhi, *_ = get_calendar_data(tz)
    # 顶部公历日期（年/月/日）
    solar_text = f"{solar['solar_year']}/{solar['solar_month']}/{solar['solar_day']}"
    draw.text((10, 10), solar_text, font=title_font, fill=1)

    # 星期
    draw.text((10, 36), solar['weekday'], font=content_font, fill=1)

    # 农历日期
    lunar_text = f"农历{lunar['lunar_month']}{lunar['lunar_day']}"
    draw.text((10, 58), lunar_text, font=content_font, fill=1)

    # 放大阳历日（居中）
    solar_day = str(solar['solar_day'])
    solar_day_bbox = draw.textbbox((0, 0), solar_day, font=large_font)
    text_w = solar_day_bbox[2] - solar_day_bbox[0]
    x_center = (img.width - text_w) / 2
    draw.text((x_center, 90), solar_day, font=large_font, fill=1)

    # 干支纪年（底部）
    ganzhi_text = f"{ganzhi['ganzhi_year']}[{ganzhi.get('shengxiao','')}]"
    draw.text((10, img.height - 32), ganzhi_text, font=small_font, fill=1)

    # 边框
    draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=1, width=1)

    return finalize_image_common(img, rotate=rotate, invert=invert)
