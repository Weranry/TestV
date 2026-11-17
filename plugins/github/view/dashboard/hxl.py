from modules.generate_views import canvas_factory
from modules.generate_views.canvas_factory import finalize_image_common
from modules.generate_views import font_loader
from ...lib.fetcher import fetch_github_data


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, username='atc1441', **kwargs):
    user_info = await fetch_github_data(username)
    matches = user_info.get('contributions', [])

    size_key = 'hxl'
    palette_type = 'bwr'
    image, draw = canvas_factory.create_canvas(size_key, palette_type, cmode=cmode)
    width, height = image.size

    P_WHITE = 0
    P_BLACK = 1
    P_RED = 2

    font_path = font_loader.get_root_font_path('font.ttf')
    icon_font_path = font_loader.get_plugin_font_path('icons.ttf', __file__)

    font_32 = font_loader.get_font(32, font_path)
    font_16 = font_loader.get_font(16, font_path)
    font_icon = font_loader.get_font(16, icon_font_path)

    margin_x = 10
    layer1_y = 5

    def get_text_width(text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    name = user_info.get('name', '') or ''
    login = user_info.get('login', '') or ''
    login_text = f"@{login}"

    # 名字和登录名要同排放下：先降一档字号，仍放不下才截断名字，
    # 否则长名字会把 @login 顶出画布右边缘、只剩半截残字
    login_w = get_text_width(login_text, font_16)
    budget = width - 2 * margin_x - login_w - 5
    name_font = font_32
    if get_text_width(name, name_font) > budget:
        name_font = font_16
        if get_text_width(name, name_font) > budget:
            while name and get_text_width(name + '..', name_font) > budget:
                name = name[:-1]
            name += '..'

    # Header Name in RED
    draw.text((margin_x, layer1_y + font_32.size - name_font.size), f"{name}",
              fill=P_RED, font=name_font)

    name_w = get_text_width(name, name_font)

    login_x = margin_x + name_w + 5
    login_y = layer1_y + 12
    draw.text((login_x, login_y), login_text, fill=P_BLACK, font=font_16)

    followers = user_info.get('followers', 0)
    following = user_info.get('following', 0)
    total_stars = user_info.get('total_stars', 0)
    repos_count = user_info.get('public_repos', 0)

    stat_item_gap = 15
    stats_data = [
        ('\ue600', followers),
        ('\ue60f', following),
        ('\ue621', total_stars),
        ('\ue616', repos_count)
    ]

    stats_y = layer1_y + 40
    current_stat_x = margin_x

    for stat_icon_char, value in stats_data:
        draw.text((current_stat_x, stats_y), stat_icon_char, fill=P_BLACK, font=font_icon)
        icon_w = draw.textlength(stat_icon_char, font=font_icon)
        text_x = current_stat_x + icon_w + 2
        draw.text((text_x, stats_y), str(value), fill=P_BLACK, font=font_16)
        current_stat_x += icon_w + 2 + get_text_width(str(value), font_16) + stat_item_gap

    line1_y = stats_y + 25
    draw.line((margin_x, line1_y, width - margin_x, line1_y), fill=P_BLACK, width=1)

    # Layer 2: top repo is omitted or minimal to save space for hxl (384x184)
    # We directly draw the contribution graph

    BOX_SIZE = 9
    BOX_OUTER_SIZE = 9
    GAP = 2
    CHART_MARGIN_LEFT = margin_x + 30
    CHART_MARGIN_TOP = line1_y + 20

    days_per_col = 7
    cols_available = (width - CHART_MARGIN_LEFT - 10) // (BOX_SIZE + GAP)
    total_days_visible = cols_available * days_per_col
    visible_levels = matches[-total_days_visible:] if matches else []

    week_days = {1: "Mon", 3: "Wed", 5: "Fri"}
    for day_idx, day_name in week_days.items():
        label_y = CHART_MARGIN_TOP + day_idx * (BOX_SIZE + GAP)
        draw.text((margin_x, label_y - 2), day_name, fill=P_BLACK, font=font_16)

    def draw_level_box(draw_obj, x, y, size, lvl):
        if lvl == 0:
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], outline=P_BLACK, fill=P_WHITE)
        elif lvl == 1:
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], outline=P_BLACK, fill=P_WHITE)
            draw_obj.rectangle([x+2, y+2, x + size - 3, y + size - 3], fill=P_BLACK)
        elif lvl == 2:
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], outline=P_BLACK, fill=P_WHITE)
            draw_obj.rectangle([x+1, y+1, x + size - 2, y + size - 2], fill=P_BLACK)
        elif lvl == 3:
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], fill=P_BLACK)
        else: # lvl == 4
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], fill=P_RED)

    if visible_levels:
        for i, (date_str, level_str) in enumerate(visible_levels):
            col = i // days_per_col
            row = i % days_per_col
            lvl = int(level_str)
            x = CHART_MARGIN_LEFT + col * (BOX_OUTER_SIZE + GAP)
            y = CHART_MARGIN_TOP + row * (BOX_OUTER_SIZE + GAP)
            draw_level_box(draw, x, y, BOX_OUTER_SIZE, lvl)

    return finalize_image_common(image, rotate=rotate, invert=invert)