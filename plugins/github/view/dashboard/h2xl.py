from modules.generate_views import canvas_factory
from modules.generate_views.canvas_factory import finalize_image_common
from modules.generate_views import font_loader
from ...lib.fetcher import fetch_github_data


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, username='atc1441', **kwargs):
    user_info = await fetch_github_data(username)
    matches = user_info.get('contributions', [])

    size_key = 'h2xl'
    palette_type = 'bwr'
    image, draw = canvas_factory.create_canvas(size_key, palette_type, cmode=cmode)
    width, height = image.size

    P_WHITE = 0
    P_BLACK = 1
    P_RED = 2

    font_path = font_loader.get_root_font_path('font.ttf')
    icon_font_path = font_loader.get_plugin_font_path('icons.ttf', __file__)

    font_48 = font_loader.get_font(48, font_path)
    font_32 = font_loader.get_font(32, font_path)
    font_16 = font_loader.get_font(16, font_path)
    font_icon = font_loader.get_font(16, icon_font_path)

    margin_x = 10
    layer1_y = 5

    # 纵向锚点按画布高度推导（h2xl 为 400×300），不再写死像素：
    # 原布局的 line1_y = 85 与 stats_y = 85 - 20 - 5 在此保持不变。
    line1_y = height * 17 // 60          # 85
    stats_y = line1_y - 20 - 5           # 60

    def get_text_width(text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    name = user_info.get('name', '') or ''
    login = user_info.get('login', '') or ''
    login_text = f"@{login}"

    # 名字和登录名要同排放下：先降一档字号，仍放不下才截断名字。
    # 48px 下 "Linus Torvalds" 刚好容不下 @login，降字号比把名字截成 "Linus Torv.." 好看，
    # 而完全不处理的话 @login 会被顶出画布右边缘、只剩半截残字。
    login_w = get_text_width(login_text, font_16)
    budget = width - 2 * margin_x - login_w - 5
    name_font = font_48
    if get_text_width(name, name_font) > budget:
        name_font = font_32
        if get_text_width(name, name_font) > budget:
            while name and get_text_width(name + '..', name_font) > budget:
                name = name[:-1]
            name += '..'

    # Header Name in RED to highlight
    draw.text((margin_x, layer1_y - 5 + font_48.size - name_font.size), f"{name}",
              fill=P_RED, font=name_font)

    name_w = get_text_width(name, name_font)

    login_x = margin_x + name_w + 5
    login_y = layer1_y
    draw.text((login_x, login_y), login_text, fill=P_BLACK, font=font_16)

    followers = user_info.get('followers', 0)
    following = user_info.get('following', 0)
    total_stars = user_info.get('total_stars', 0)
    repos_count = user_info.get('public_repos', 0)

    stat_item_gap = 20

    stats_data = [
        ('\ue600', followers),
        ('\ue60f', following),
        ('\ue621', total_stars),
        ('\ue616', repos_count)
    ]

    current_stat_x = margin_x

    for stat_icon_char, value in stats_data:
        draw.text((current_stat_x, stats_y), stat_icon_char, fill=P_BLACK, font=font_icon)
        icon_w = draw.textlength(stat_icon_char, font=font_icon)
        text_x = current_stat_x + icon_w + 5
        draw.text((text_x, stats_y), str(value), fill=P_BLACK, font=font_16)
        current_stat_x += icon_w + 5 + get_text_width(str(value), font_16) + stat_item_gap

    bio = user_info.get('bio', '')
    if bio:
        # 右侧资料块起点（400 宽时为 250）
        bio_x = width - width * 3 // 8
        if len(bio) > 15: bio = bio[:12] + "..."
        draw.text((bio_x, layer1_y + 10), bio, fill=P_BLACK, font=font_16)

    draw.line((margin_x, line1_y, width - margin_x, line1_y), fill=P_BLACK, width=1)

    layer2_y = line1_y + 5
    repo_name = user_info.get('top_repo_name')
    if repo_name:
        stars = user_info.get('top_repo_stars', 0)
        lang = user_info.get('top_repo_lang', 'Unknown')
        desc = user_info.get('top_repo_desc', '') or ''

        draw.text((margin_x, layer2_y), repo_name, fill=P_BLACK, font=font_16)

        stats_y_repo = layer2_y + 40
        lang_text = f"• {lang}"
        draw.text((margin_x, stats_y_repo), lang_text, fill=P_BLACK, font=font_16)

        star_icon_char = "\ue621"
        star_icon_w = draw.textlength(star_icon_char, font=font_icon)
        star_value_text = f" {stars}"
        star_value_w = get_text_width(star_value_text, font_16)
        total_star_w = star_icon_w + star_value_w

        star_start_x = width - total_star_w - margin_x
        draw.text((star_start_x, stats_y_repo), star_icon_char, fill=P_BLACK, font=font_icon)
        draw.text((star_start_x + star_icon_w, stats_y_repo), star_value_text, fill=P_BLACK, font=font_16)

        name_repo_w = get_text_width(repo_name, font_32)
        if desc:
            desc_x = margin_x + name_repo_w + 15
            available_w = width - margin_x - desc_x
            if available_w > 50:
                max_chars = int(available_w / 8)
                if len(desc) > max_chars: desc = desc[:max_chars-2] + ".."
                draw.text((desc_x, layer2_y + 12), desc, fill=P_BLACK, font=font_16)

    line2_y = layer2_y + 65
    draw.line((margin_x, line2_y, width - margin_x, line2_y), fill=P_BLACK, width=1)

    BOX_SIZE = 11
    BOX_OUTER_SIZE = 11
    GAP = 2
    CHART_MARGIN_LEFT = margin_x + 35
    CHART_MARGIN_TOP = line2_y + 25

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
            draw_obj.rectangle([x+3, y+3, x + size - 4, y + size - 4], fill=P_BLACK)
        elif lvl == 2:
            draw_obj.rectangle([x, y, x + size - 1, y + size - 1], outline=P_BLACK, fill=P_WHITE)
            draw_obj.rectangle([x+2, y+2, x + size - 3, y + size - 3], fill=P_BLACK)
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