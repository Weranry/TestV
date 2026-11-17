from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_huangli_data


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    # 获取数据
    jishen, taishen, taisui, pengzubaiji, ershibaxingxiu, chongsha = get_huangli_data(tz=tz)

    # 标题
    title_font = get_font_global(24, font_path=FONT_PATH)
    font = get_font_global(16, font_path=FONT_PATH)
    draw.text((200, 28), "黄历", fill=1, font=title_font, anchor='mm')

    # 吉神（居中横排）
    jishen_keys = list(jishen.keys())
    jishen_values = list(jishen.values())
    jishen_count = len(jishen_keys)
    start_x = 200 - (jishen_count - 1) * 60 // 2
    for i, (key, value) in enumerate(zip(jishen_keys, jishen_values)):
        x = start_x + i * 60
        draw.text((x, 60), key, fill=1, font=font, anchor='mm')
        draw.text((x, 85), value, fill=1, font=font, anchor='mm')

    # 分割线
    draw.line([(30, 110), (370, 110)], fill=1, width=1)
    draw.line([(200, 110), (200, 210)], fill=1, width=1)

    # 左栏
    left_x = 115
    draw.text((left_x, 130), "太岁", fill=1, font=font, anchor='mm')
    draw.text((left_x, 155), taisui, fill=1, font=font, anchor='mm')
    draw.text((left_x, 185), "胎神", fill=1, font=font, anchor='mm')
    draw.text((left_x, 210), taishen, fill=1, font=font, anchor='mm')

    # 右栏
    right_x = 285
    draw.text((right_x, 130), "冲煞", fill=1, font=font, anchor='mm')
    draw.text((right_x, 155), chongsha, fill=1, font=font, anchor='mm')
    draw.text((right_x, 185), "二十八宿", fill=1, font=font, anchor='mm')
    draw.text((right_x, 210), ershibaxingxiu, fill=1, font=font, anchor='mm')

    # 底部分割线
    draw.line([(30, 235), (370, 235)], fill=1, width=1)

    # 彭祖百忌
    bz_font = get_font_global(18, font_path=FONT_PATH)
    draw.text((200, 255), "彭祖百忌", fill=1, font=bz_font, anchor='mm')
    draw.text((200, 285), pengzubaiji, fill=1, font=font, anchor='mm')
    return finalize_image_common(img, rotate=rotate, invert=invert)
