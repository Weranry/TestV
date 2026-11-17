from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_calendar_data


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    # 字体全部为16或其整数倍
    title_font = get_font_global(32, font_path=FONT_PATH)      # 标题用32
    content_font = get_font_global(16, font_path=FONT_PATH)    # 内容用16
    large_font = get_font_global(128, font_path=FONT_PATH)     # 放大日用128

    solar, lunar, ganzhi, season, festival = get_calendar_data(tz)
    # 绘制公历日期和星期
    solar_text = f"{solar['solar_year']}/{solar['solar_month']}/{solar['solar_day']} {solar['weekday']}"
    draw.text((10, 10), solar_text, font=title_font, fill=1)

    # 绘制农历日期
    lunar_text = f"农历{lunar['lunar_month']}{lunar['lunar_day']}"
    draw.text((10, 10 + 32 + 4), lunar_text, font=title_font, fill=1)

    # 绘制干支纪年与属相
    ganzhi_text = f"{ganzhi['ganzhi_year']}[{ganzhi.get('shengxiao','')}]"
    draw.text((10, 10 + 32*2 + 8), ganzhi_text, font=content_font, fill=1)
    ganzhi_text2 = f"{ganzhi['ganzhi_month']} {ganzhi['ganzhi_day']}"
    draw.text((10, 10 + 32*2 + 8 + 16 + 4), ganzhi_text2, font=content_font, fill=1)

    # 绘制放大版阳历日（居中）
    solar_day = str(solar['solar_day'])
    solar_day_bbox = draw.textbbox((0, 0), solar_day, font=large_font)
    text_w = solar_day_bbox[2] - solar_day_bbox[0]
    x_center = (img.width - text_w) / 2
    draw.text((x_center, 10 + 32*2 + 8 + 16*2 + 8), solar_day, font=large_font, fill=1)

    # 数九或伏（若有）
    fujiu = season.get('fujiu', '')
    if fujiu:
        draw.text((img.width - 10, 10), fujiu, font=title_font, fill=1, anchor="ra")

    # 物候和节气
    season_text = f"{season.get('wu_hou','')} {season.get('hou','')}".strip()
    if season_text:
        season_bbox = draw.textbbox((0, 0), season_text, font=content_font)
        season_w = season_bbox[2] - season_bbox[0]
        x_pos = (img.width - season_w) / 2
        draw.text((x_pos, img.height - 64), season_text, font=content_font, fill=1)

    # 节日信息（公历/农历）
    festival_text = f"{festival.get('solar_festival','')} {festival.get('lunar_festival','')}".strip()
    if festival_text:
        festival_bbox = draw.textbbox((0, 0), festival_text, font=content_font)
        fest_w = festival_bbox[2] - festival_bbox[0]
        x_pos = (img.width - fest_w) / 2
        draw.text((x_pos, img.height - 32), festival_text, font=content_font, fill=2)

    return finalize_image_common(img, rotate=rotate, invert=invert)
