from ...lib.date_calculator import DateCalculator
from modules.generate_views.font_loader import get_root_font_path

# 本插件不带字体资源，统一使用框架内置字体（assets/fonts/font.ttf）
FONT_PATH = get_root_font_path('font.ttf')


def get_calendar_data(tz=None):
    dc = DateCalculator(tz)
    solar = dc.get_solar_date()
    lunar = dc.get_lunar_date()
    ganzhi = dc.get_ganzhi_date()
    season = dc.get_season_info()
    festival = dc.get_festival_info()
    return solar, lunar, ganzhi, season, festival
