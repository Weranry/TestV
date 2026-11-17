"""HXL（384×184）横屏 F1 下场比赛图：左侧赛道轮廓，右侧时间地点与周末赛程。

所有字号只用 16 或 32（框架字体规范要求 16 的整数倍），版面按这个字号重新排过。
"""
from modules.generate_views.canvas_factory import create_canvas, finalize_image_common

from ...lib.f1_client import fetch_race
from ...lib.track_map import fetch_track
from .utils import (
    P_BLACK,
    P_RED,
    draw_progress,
    draw_right,
    draw_text,
    draw_track,
    fit_font,
    fit_text,
    fmt_circuit_stats,
    fmt_countdown,
    fmt_datetime,
    fmt_round,
    fmt_short_time,
    load_font,
    text_width,
)

WIDTH, HEIGHT = 384, 184
MARGIN = 8
COL_RIGHT = WIDTH - MARGIN

# 赛道轮廓画框
MAP_X, MAP_Y, MAP_W, MAP_H = 8, 50, 140, 126
# 右侧信息列起点
COL_X = 156

ROW_Y = 102
ROW_STEP = 18


async def generate_image(rotate=0, invert=False, tz=None, cmode=None,
                         round='next', season=None, **kwargs):
    race = await fetch_race(round_ref=round, season=season, tz=tz)
    track = await fetch_track(race['circuit_id'], race['country'],
                              race['circuit_name'], race['locality'])

    img, draw = create_canvas('hxl', palette_type='bwr', cmode=cmode)

    info_font = load_font(16)

    # 站次标题：赛事名（红）+ 赛季进度；两段都按各自预算截断，谁长都不会挤掉对方
    race_name = race['race_name'] or 'F1 Grand Prix'
    round_budget = (WIDTH - 2 * MARGIN) / 2
    round_text = fit_text(draw, fmt_round(race['round'], race['total_rounds']),
                          info_font, round_budget)
    title_budget = WIDTH - 2 * MARGIN - text_width(draw, round_text, info_font) - 8

    draw_text(draw, (MARGIN, 6), fit_text(draw, race_name, info_font, title_budget),
              info_font, P_RED)
    draw_right(draw, COL_RIGHT, 6, round_text, info_font, P_BLACK)

    draw_progress(draw, MARGIN, 40, WIDTH - 2 * MARGIN, 5,
                  race['round'], race['total_rounds'])

    # 赛道图是装饰性内容：取不到就留空，不影响其余信息
    if track:
        draw_track(draw, track['points'], MAP_X, MAP_Y, MAP_W, MAP_H)

    col_budget = COL_RIGHT - COL_X
    draw_text(draw, (COL_X, 48), fmt_datetime(race['race_time']), info_font, P_BLACK)
    countdown = fmt_countdown(race['days_until'])
    if countdown:
        draw_right(draw, COL_RIGHT, 48, countdown, info_font, P_RED)

    circuit_font = fit_font(draw, race['circuit_name'], info_font, col_budget, 16)
    draw_text(draw, (COL_X, 66), fit_text(draw, race['circuit_name'], circuit_font, col_budget),
              circuit_font, P_BLACK)

    # 地点与赛道资料合成一行：384 宽的窄屏要留出赛程的纵向空间
    place = race['locality'] or race['country']
    stats = fmt_circuit_stats(race['circuit_id'], (track or {}).get('length_m'))
    subtitle = ' · '.join(item for item in (place, stats) if item)
    draw_text(draw, (COL_X, 84), fit_text(draw, subtitle, info_font, col_budget),
              info_font, P_BLACK)

    row_y = ROW_Y
    for session in race['sessions']:
        if row_y + 17 > HEIGHT - MARGIN:
            break
        # 时间固定右对齐，节次名只拿剩下的宽度，超长截断，两段不会压在一起
        time_text = fmt_short_time(session['time'])
        label_budget = COL_RIGHT - COL_X - text_width(draw, time_text, info_font) - 8
        draw_text(draw, (COL_X, row_y),
                  fit_text(draw, session['label'], info_font, label_budget), info_font, P_BLACK)
        draw_right(draw, COL_RIGHT, row_y, time_text, info_font, P_BLACK)
        row_y += ROW_STEP

    return finalize_image_common(img, rotate=rotate, invert=invert)
