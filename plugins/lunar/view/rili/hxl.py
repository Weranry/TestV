from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_calendar_data


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    title_font = get_font_global(22, font_path=FONT_PATH)
    content_font = get_font_global(18, font_path=FONT_PATH)
    large_font = get_font_global(72, font_path=FONT_PATH)
    small_font = get_font_global(14, font_path=FONT_PATH)

    solar, lunar, ganzhi, season, festival = get_calendar_data(tz)
    # 公历日期和星期
    solar_text = f"{solar['solar_year']}/{solar['solar_month']}/{solar['solar_day']} {solar['weekday']}"
    draw.text((12, 12), solar_text, font=title_font, fill=1)

    # 农历日期
    lunar_text = f"农历{lunar['lunar_month']}{lunar['lunar_day']}"
    draw.text((12, 42), lunar_text, font=content_font, fill=1)

    # 干支纪年与属相
    ganzhi_text = f"{ganzhi['ganzhi_year']}[{ganzhi.get('shengxiao','')}]"
    draw.text((12, 66), ganzhi_text, font=content_font, fill=1)
    ganzhi_text2 = f"{ganzhi['ganzhi_month']} {ganzhi['ganzhi_day']}"
    draw.text((12, 88), ganzhi_text2, font=content_font, fill=1)

    # 放大阳历日（右侧居中）
    solar_day = str(solar['solar_day'])
    solar_day_bbox = draw.textbbox((0, 0), solar_day, font=large_font)
    text_w = solar_day_bbox[2] - solar_day_bbox[0]
    text_h = solar_day_bbox[3] - solar_day_bbox[1]
    x_center = img.width - text_w - 22
    y_center = (img.height - text_h) // 2
    draw.text((x_center, y_center), solar_day, font=large_font, fill=1)

    # 数九或伏（右上角）
    fujiu = season.get('fujiu', '')
    if fujiu:
        draw.text((img.width - 12, 12), fujiu, font=content_font, fill=1, anchor="ra")

    # 物候和节气（底部左侧）
    season_text = f"{season.get('wu_hou','')} {season.get('hou','')}".strip()
    if season_text:
        draw.text((12, img.height - 44), season_text, font=small_font, fill=1)

    # 节日信息（底部右侧）
    festival_text = f"{festival.get('solar_festival','')} {festival.get('lunar_festival','')}".strip()
    if festival_text:
        draw.text((img.width - 12, img.height - 44), festival_text, font=small_font, fill=2, anchor="ra")

    # 边框
    draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=1, width=1)

    return finalize_image_common(img, rotate=rotate, invert=invert)
