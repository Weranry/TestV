from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_huangliA_data


def wrap_text(text, font, max_width, max_lines=2):
    lines = []
    if font.getlength(text) <= max_width:
        lines.append(text)
    else:
        words = text.split(' ')
        current_line = words[0]
        for word in words[1:]:
            if font.getlength(current_line + ' ' + word) <= max_width and len(lines) < max_lines:
                current_line += ' ' + word
            else:
                if len(lines) < max_lines:
                    lines.append(current_line)
                    current_line = word
                else:
                    break
        if len(lines) < max_lines:
            lines.append(current_line)
    return lines


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    font_large = get_font_global(32, font_path=FONT_PATH)
    font_small = get_font_global(16, font_path=FONT_PATH)

    # 获取数据
    lunar_date, ganzhi_date, solar_date, yiji = get_huangliA_data(tz=tz)

    # 绘制农历日期，大字体
    lunar_text = f"农历{lunar_date['lunar_month']}{lunar_date['lunar_day']}"
    draw.text((10, 10), lunar_text, font=font_large, fill=1)

    # 绘制干支日期和属相，小字体
    ganzhi_text = f"{ganzhi_date['ganzhi_year']} {ganzhi_date['ganzhi_month']}{ganzhi_date['ganzhi_day']} [{ganzhi_date['shengxiao']}]"
    draw.text((10, 45), ganzhi_text, font=font_small, fill=1)

    # 绘制阳历日期和星期几，小字体
    solar_text = f"{solar_date['solar_year']}年{solar_date['solar_month']}月{solar_date['solar_day']}日 {solar_date['weekday']} {solar_date['xingzuo']}"
    draw.text((10, 75), solar_text, font=font_small, fill=1)

    # 绘制分割线
    draw.line((10, 105, 390, 105), fill=1)

    # 绘制宜，大字体
    draw.text((10, 115), "宜", font=font_large, fill=1)
    yi_text = ' '.join(yiji['Yi'])
    yi_lines = wrap_text(yi_text, font_small, 380)
    for i, line in enumerate(yi_lines):
        draw.text((10, 150 + i * 20), line, font=font_small, fill=1)

    # 绘制忌，大字体
    draw.text((10, 195), "忌", font=font_large, fill=1)
    ji_text = ' '.join(yiji['Ji'])
    ji_lines = wrap_text(ji_text, font_small, 380)
    for i, line in enumerate(ji_lines):
        draw.text((10, 230 + i * 20), line, font=font_small, fill=1)

    return finalize_image_common(img, rotate=rotate, invert=invert)
