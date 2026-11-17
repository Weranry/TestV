from modules.generate_views.font_loader import get_font, get_root_font_path


def render_steam_stats(canvas, draw, data):
    width, height = canvas.size

    font_path = get_root_font_path('font.ttf')

    # 动态字号判定(16px倍数)
    if width >= 600:
        header_font = get_font(48, font_path)
        sub_font = get_font(32, font_path)
        val_font = get_font(64, font_path)
        lbl_font = get_font(32, font_path)
        list_font = get_font(32, font_path)
        margin = 32
    elif width >= 400:  # h2xl (400x300)
        header_font = get_font(32, font_path)
        sub_font = get_font(16, font_path)
        val_font = get_font(48, font_path)
        lbl_font = get_font(16, font_path)
        list_font = get_font(16, font_path)
        margin = 16
    elif width >= 300:  # hxl (384x184), v2xl (300x400)
        header_font = get_font(32, font_path)
        sub_font = get_font(16, font_path)
        val_font = get_font(48, font_path) if height > 200 else get_font(32, font_path)
        lbl_font = get_font(16, font_path)
        list_font = get_font(16, font_path)
        margin = 16
    else:  # m(200x200), vl(122x250)
        header_font = get_font(16, font_path)
        sub_font = get_font(16, font_path)
        val_font = get_font(32, font_path)
        lbl_font = get_font(16, font_path)
        list_font = get_font(16, font_path)
        margin = 8

    # ====== 行布局协调 ======
    curr_y = margin

    # === 1. 顶部 Header (红标题 + 黑昵称) ===
    title = "STEAM"
    draw.text((margin, curr_y), title, font=header_font, fill=2)  # 红
    title_w = draw.textlength(title, font=header_font)

    nickname = f"| {data.get('nickname', 'Unk')}"

    # 若一行太挤，则换行显示
    nick_w = draw.textlength(nickname, font=header_font)
    if margin + title_w + 16 + nick_w > width - margin:
        # 太长截断
        max_nick_w = width - margin - title_w - 32
        while draw.textlength(nickname, font=header_font) > max_nick_w and len(nickname) > 4:
            nickname = nickname[:-4] + "..."

    draw.text((margin + title_w + 16, curr_y), nickname, font=header_font, fill=1)  # 黑
    header_h = max(header_font.getbbox(title)[3], header_font.getbbox(nickname)[3])
    curr_y += header_h + 8

    # === 2. 最后在线时间 ===
    last_logoff = f"最后在线: {data.get('last_logoff', '')}"
    if draw.textlength(last_logoff, font=sub_font) > width - margin * 2:
        last_logoff = last_logoff.replace('最后在线: ', '在线: ')

    # 尽可能靠右，如果挤不下了就靠左
    logoff_w = draw.textlength(last_logoff, font=sub_font)
    if width - margin - logoff_w > margin:
        draw.text((width - margin - logoff_w, curr_y), last_logoff, font=sub_font, fill=1)
    else:
        draw.text((margin, curr_y), last_logoff, font=sub_font, fill=1)

    curr_y += sub_font.getbbox(last_logoff)[3] + 8

    # 分割线 1
    draw.line([(margin, curr_y), (width - margin, curr_y)], fill=1, width=2)
    curr_y += 16

    # === 3. 数据网格 (Grid布局) ===
    # 判断要几列：如果宽度极小(<150)，可以分两行
    if width < 150:
        cols = 1
    elif width < 250:
        cols = 2
    else:
        cols = 3

    stats = [
        {"val": str(data.get('steam_level', 0)), "lbl": "LEVEL"},
        {"val": f"{int(data.get('total_playtime_hours', 0))}h", "lbl": "HOURS"},
        {"val": str(data.get('game_count', 0)), "lbl": "GAMES"}
    ]

    col_w = (width - margin * 2) / cols
    row_h = val_font.getbbox("0")[3] + lbl_font.getbbox("L")[3] + 16  # padding
    if width < 300:
        row_h += 8

    grid_h = ((3 + cols - 1) // cols) * row_h

    # 画Grid内容
    for idx, stat in enumerate(stats):
        c = idx % cols
        r = idx // cols

        cell_x = margin + c * col_w
        cell_y = curr_y + r * row_h

        # 居中渲染
        val_w = draw.textlength(stat["val"], font=val_font)
        lbl_w = draw.textlength(stat["lbl"], font=lbl_font)

        # 避免越界
        v_size = val_font
        while val_w > col_w - 4 and v_size.size >= 16:
            v_size = get_font(v_size.size - 16 if v_size.size > 16 else 16, font_path)
            val_w = draw.textlength(stat["val"], font=v_size)
            if v_size.size == 16:
                break

        draw.text((cell_x + (col_w - val_w) / 2, cell_y), stat["val"], font=v_size, fill=1)
        draw.text((cell_x + (col_w - lbl_w) / 2, cell_y + v_size.getbbox(stat["val"])[3] + 8),
                  stat["lbl"], font=lbl_font, fill=1)

    # 画Grid的分界线
    if cols > 1:
        for c in range(1, cols):
            line_x = margin + c * col_w
            draw.line([(line_x, curr_y + margin), (line_x, curr_y + grid_h - margin)], fill=1, width=1)

    if cols < 3:  # 有多行的话画横线
        for r in range(1, (3 + cols - 1) // cols):
            line_y = curr_y + r * row_h
            draw.line([(margin + col_w, line_y), (width - margin, line_y)], fill=1, width=1)

    curr_y += grid_h + 16

    if curr_y + 16 < height:
        draw.line([(margin, curr_y), (width - margin, curr_y)], fill=1, width=2)
        curr_y += 16

        # === 4. 最近游玩列表 ===
        draw.text((margin, curr_y), "最近常玩 (2周):", font=sub_font, fill=2)  # 红字
        curr_y += sub_font.getbbox("最")[3] + 16

        games = data.get('recent_game_names', [])
        if not games:
            draw.text((margin, curr_y), "无记录/隐藏资料", font=list_font, fill=1)
        else:
            for game_name in games:
                if curr_y + list_font.getbbox("A")[3] + 8 > height - margin:
                    break  # 放不下了
                item = f"• {game_name}"
                while draw.textlength(item, font=list_font) > width - margin * 2 and len(item) > 5:
                    item = item[:-4] + "..."
                draw.text((margin, curr_y), item, font=list_font, fill=1)
                curr_y += list_font.getbbox("A")[3] + 8
