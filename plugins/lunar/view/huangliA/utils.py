from ...lib.today_huangli_A import todayhuangliA
from modules.generate_views.font_loader import get_root_font_path

# 本插件不带字体资源，统一使用框架内置字体（assets/fonts/font.ttf）
FONT_PATH = get_root_font_path('font.ttf')


def get_huangliA_data(tz=None):
    today = todayhuangliA(tz=tz)
    lunar_date = today.get_lunar_date()
    ganzhi_date = today.get_ganzhi_date()
    solar_date = today.get_solar_date()
    yiji = today.get_Day_Yiji()
    return lunar_date, ganzhi_date, solar_date, yiji
