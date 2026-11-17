from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_huangliA_data

W = 384
H = 184


def wrap_text(text, font, max_width, max_lines=4):
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
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    font_large = get_font_global(14, font_path=FONT_PATH)
    font_small = get_font_global(12, font_path=FONT_PATH)

    lunar_date, ganzhi_date, solar_date, yiji = get_huangliA_data(tz=tz)

    lunar_text = f"农历{lunar_date['lunar_month']}{lunar_date['lunar_day']}"
    draw.text((8, 6), lunar_text, font=font_large, fill=1)

    ganzhi_text = f"{ganzhi_date['ganzhi_year']} {ganzhi_date['ganzhi_month']}{ganzhi_date['ganzhi_day']} [{ganzhi_date['shengxiao']}]"
    draw.text((8, 24), ganzhi_text, font=font_small, fill=1)

    solar_text = f"{solar_date['solar_year']}年{solar_date['solar_month']}月{solar_date['solar_day']}日 {solar_date['weekday']} {solar_date['xingzuo']}"
    draw.text((8, 40), solar_text, font=font_small, fill=1)

    draw.line((8, 54, W - 8, 54), fill=1)

    cx = W // 2
    draw.line((cx, 54, cx, H - 8), fill=1)

    # 宜（左栏）
    draw.text((10, 58), "宜", font=font_large, fill=1)
    yi_lines = wrap_text(' '.join(yiji['Yi']), font_small, 148)
    for i, line in enumerate(yi_lines):
        draw.text((34, 58 + i * 18), line, font=font_small, fill=1)

    # 忌（右栏）
    draw.text((cx + 8, 58), "忌", font=font_large, fill=1)
    ji_lines = wrap_text(' '.join(yiji['Ji']), font_small, 148)
    for i, line in enumerate(ji_lines):
        draw.text((cx + 32, 58 + i * 18), line, font=font_small, fill=1)

    return finalize_image_common(img, rotate=rotate, invert=invert)
