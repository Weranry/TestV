"""H2XL（400×300）横屏 F1 下场比赛图：与 hxl 同一套信息，画面更宽裕。

赛程放到底部通栏，能完整列出含冲刺周末在内的全部节次。
所有字号只用 16 或 32（框架字体规范要求 16 的整数倍）。
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

WIDTH, HEIGHT = 400, 300
MARGIN = 10
COL_RIGHT = WIDTH - MARGIN

# 赛道轮廓画框
MAP_X, MAP_Y, MAP_W, MAP_H = 10, 76, 170, 132
# 右侧信息列起点
COL_X = 192

# 底部通栏赛程：两个字列，逐行下移
BAND_Y = 224
BAND_STEP = 22
COLUMN_STARTS = (10, 204)


async def generate_image(rotate=0, invert=False, tz=None, cmode=None,
                         round='next', season=None, **kwargs):
    race = await fetch_race(round_ref=round, season=season, tz=tz)
    track = await fetch_track(race['circuit_id'], race['country'],
                              race['circuit_name'], race['locality'])

    img, draw = create_canvas('h2xl', palette_type='bwr', cmode=cmode)

    info_font = load_font(16)

    countdown = fmt_countdown(race['days_until'])
    header = f'下场比赛 · {countdown}' if countdown else '下场比赛'
    round_text = fit_text(draw, fmt_round(race['round'], race['total_rounds']),
                          info_font, (WIDTH - 2 * MARGIN) / 2)
    draw_text(draw, (MARGIN, 0),
              fit_text(draw, header, info_font,
                       WIDTH - 2 * MARGIN - text_width(draw, round_text, info_font) - 8),
              info_font, P_BLACK)
    draw_right(draw, COL_RIGHT, 0, round_text, info_font, P_BLACK)

    race_name = race['race_name'] or 'F1 Grand Prix'
    budget = WIDTH - 2 * MARGIN
    title_font = fit_font(draw, race_name, load_font(32), budget, 16)
    draw_text(draw, (MARGIN, 24), fit_text(draw, race_name, title_font, budget),
              title_font, P_RED)

    draw_progress(draw, MARGIN, 64, WIDTH - 2 * MARGIN, 6,
                  race['round'], race['total_rounds'])

    # 赛道图是装饰性内容：取不到就留空，不影响其余信息
    if track:
        draw_track(draw, track['points'], MAP_X, MAP_Y, MAP_W, MAP_H)

    col_budget = COL_RIGHT - COL_X
    draw_text(draw, (COL_X, 76), fmt_datetime(race['race_time']), info_font, P_BLACK)

    circuit_font = fit_font(draw, race['circuit_name'], info_font, col_budget, 16)
    draw_text(draw, (COL_X, 98), fit_text(draw, race['circuit_name'], circuit_font, col_budget),
              circuit_font, P_BLACK)

    location = ' · '.join(item for item in (race['locality'], race['country']) if item)
    draw_text(draw, (COL_X, 118), fit_text(draw, location, info_font, col_budget),
              info_font, P_BLACK)

    stats = fmt_circuit_stats(race['circuit_id'], (track or {}).get('length_m'))
    if stats:
        draw_text(draw, (COL_X, 138), stats, info_font, P_BLACK)

    # 底部通栏赛程
    draw.line((MARGIN, 212, COL_RIGHT, 212), fill=P_BLACK, width=1)

    row_font = load_font(16)
    for index, session in enumerate(race['sessions']):
        column_x = COLUMN_STARTS[index % len(COLUMN_STARTS)]
        row_y = BAND_Y + (index // len(COLUMN_STARTS)) * BAND_STEP
        if row_y + 17 > HEIGHT - MARGIN:
            break
        # 列宽 182：时间固定右对齐，节次名只拿剩下的宽度，超长截断
        time_text = fmt_short_time(session['time'])
        label_budget = 182 - text_width(draw, time_text, row_font) - 8
        draw_text(draw, (column_x, row_y),
                  fit_text(draw, session['label'], row_font, label_budget), row_font, P_BLACK)
        draw_right(draw, column_x + 182, row_y, time_text, row_font, P_BLACK)

    return finalize_image_common(img, rotate=rotate, invert=invert)
