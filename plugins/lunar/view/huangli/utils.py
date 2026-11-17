from ...lib.today_huangli import todayhuangli
from modules.generate_views.font_loader import get_root_font_path

# 本插件不带字体资源，统一使用框架内置字体（assets/fonts/font.ttf）
FONT_PATH = get_root_font_path('font.ttf')


def get_huangli_data(tz=None):
    hl = todayhuangli(tz=tz)
    jishen = hl.get_jishen()
    taishen = hl.get_taishen()
    taisui = hl.get_taisui()
    pengzubaiji = hl.get_pengzubaiji()
    ershibaxingxiu = hl.get_ershibaxingxiu()
    chongsha = hl.get_chongsha()
    return jishen, taishen, taisui, pengzubaiji, ershibaxingxiu, chongsha
