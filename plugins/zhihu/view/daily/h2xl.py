"""H2XL（400×300）知乎日报图：日期标头 + 标题折行 + 右下角原文二维码。

画布尺寸由本文件所在的模块名（h2xl）决定：框架在调用 generate_image 前已经把 size
从业务参数里摘掉了，因此这里必须硬编码 create_canvas('h2xl', ...)，不能再从 kwargs 取。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from modules.generate_views.font_loader import get_font, get_root_font_path
from modules.generate_views.qrcode_util import generate_qrcode
from modules.utils.timezone import now_in_timezone

from ...lib.fetcher import fetch_zhihu_daily

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    # 1. 先取数据（失败时直接抛错，不浪费画布）
    data = await fetch_zhihu_daily(rsshub_base=kwargs.get('rsshub_base'))

    # 2. 初始化画布（尺寸硬编码为 h2xl 400×300；框架已把 size 从参数里摘掉）
    canvas, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)
    width, height = canvas.size

    # 3. 准备字体
    font_path = get_root_font_path('font.ttf')
    font_32 = get_font(32, font_path)
    font_16 = get_font(16, font_path)

    # 4. 绘制顶部信息
    now = now_in_timezone(tz)
    margin = 16

    # 居左标头：知乎日报 ZHIHU DAILY（红字）
    draw.text((margin, margin), "知乎日报 ZHIHU DAILY", font=font_16, fill=2)

    # 居右：日期信息（黑字）
    date_text = f"{now.strftime('%m月%d日')} | {WEEKDAYS[now.weekday()]}"
    date_w = draw.textlength(date_text, font=font_16)
    draw.text((width - margin - date_w, margin), date_text, font=font_16, fill=1)

    # 分隔线
    line_y = margin + 28
    draw.line([(margin, line_y), (width - margin, line_y)], fill=1, width=2)

    # 5. 二维码固定在右下角
    qr_size = 96
    qr_x = width - margin - qr_size
    qr_y = height - margin - qr_size

    if data.get('link'):
        # 生成标准 0=黑 / 255=白 的 L 模式二维码
        qr_img = generate_qrcode(data['link'], box_size=3, border=1,
                                 fill_color="black", back_color="white")
        qr_img = qr_img.resize((qr_size, qr_size), resample=0)  # 0 = NEAREST，杜绝杂色
        # bwr 调色板里 1 是黑、0 是白：把 L 模式的 0(黑) 映射成 1、255(白) 映射成 0
        qr_img = qr_img.point(lambda x: 1 if x < 128 else 0)
        canvas.paste(qr_img, (qr_x, qr_y))

    # 6. 标题动态折行：一旦进入二维码所在高度，就把行宽收窄到二维码左侧，避免压字
    title_text = data.get('title', '')
    title_start_y = line_y + 16
    line_height = 48
    max_width = width - margin * 2

    def wrap_title(text):
        lines = []
        line = ''
        y = title_start_y
        for char in text:
            current_max_width = max_width
            if y + line_height > qr_y - 8:
                # 为避免压到二维码，进入二维码高度的行需收缩到二维码左侧
                current_max_width = qr_x - margin * 2
            if draw.textlength(line + char, font=font_32) > current_max_width:
                if line:
                    lines.append((line, y))
                    y += line_height
                line = char
            else:
                line += char
        if line:
            lines.append((line, y))
        return lines

    # 最多显示 5 行，并确保字不越界
    for line_str, y_pos in wrap_title(title_text)[:5]:
        if y_pos + line_height <= height:
            draw.text((margin, y_pos), line_str, font=font_32, fill=1)

    return finalize_image_common(canvas, rotate=rotate, invert=invert)
