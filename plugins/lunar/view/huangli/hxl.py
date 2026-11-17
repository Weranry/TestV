from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font as get_font_global
from .utils import FONT_PATH, get_huangli_data

W = 384
H = 184


def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)
    jishen, taishen, taisui, pengzubaiji, ershibaxingxiu, chongsha = get_huangli_data(tz=tz)

    title_font = get_font_global(16, font_path=FONT_PATH)
    label_font = get_font_global(11, font_path=FONT_PATH)
    font = get_font_global(10, font_path=FONT_PATH)

    cx = W // 2
    draw.text((cx, 14), "黄历", fill=1, font=title_font, anchor='mm')

    # 吉神（铺满整幅宽度）
    jishen_keys = list(jishen.keys())
    jishen_values = list(jishen.values())
    jishen_count = len(jishen_keys)
    if jishen_count > 1:
        step = (W - 64) // (jishen_count - 1)
        start_x = cx - (step * (jishen_count - 1)) // 2
    else:
        step = 0
        start_x = cx
    for i, (key, value) in enumerate(zip(jishen_keys, jishen_values)):
        x = start_x + i * step
        draw.text((x, 30), key, fill=1, font=font, anchor='mm')
        draw.text((x, 44), value, fill=1, font=font, anchor='mm')

    draw.line([(12, 56), (W - 12, 56)], fill=1, width=1)
    draw.line([(cx, 56), (cx, 108)], fill=1, width=1)

    left_x = cx // 2
    right_x = cx + cx // 2
    for x, label1, val1, label2, val2 in (
        (left_x, "太岁", taisui, "胎神", taishen),
        (right_x, "冲煞", chongsha, "二十八宿", ershibaxingxiu),
    ):
        draw.text((x, 68), label1, fill=1, font=label_font, anchor='mm')
        draw.text((x, 80), val1, fill=1, font=font, anchor='mm')
        draw.text((x, 94), label2, fill=1, font=label_font, anchor='mm')
        draw.text((x, 106), val2, fill=1, font=font, anchor='mm')

    draw.line([(12, 118), (W - 12, 118)], fill=1, width=1)

    bz_font = get_font_global(12, font_path=FONT_PATH)
    draw.text((cx, 126), "彭祖百忌", fill=1, font=bz_font, anchor='mm')
    draw.text((cx, 144), pengzubaiji, fill=1, font=font, anchor='mm')
    return finalize_image_common(img, rotate=rotate, invert=invert)
