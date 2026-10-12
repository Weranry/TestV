# cmode 支持的映射模式。参数校验从这里取，不要再抄一份字面量：
# 抄一份的话，这里加了新模式、那边还会照旧拒绝，表现为「支持了但一传就 400」
CMODE_MODES = ('2bw', 'r2y', 'y2r', 'yr2r', 'yr2y')
# URL 上显式传 cmode 时允许的取值：上述模式 + 'None'（显式表示不映射）
CMODE_ARG_VALUES = ('None',) + CMODE_MODES


def map_palette(palette, mode):
    """
    调色板映射函数
    palette: [r,g,b, r,g,b, ...]
    mode: None, 'None', 或 CMODE_MODES 中的任意一项
    """
    if not mode or mode == 'None':
        return palette
    colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
    WHITE = (255,255,255)
    BLACK = (0,0,0)
    RED = (255,0,0)
    YELLOW = (255,255,0)
    if mode == '2bw':
        mapped = [WHITE if c == WHITE else BLACK for c in colors]
    elif mode == 'r2y':
        mapped = [YELLOW if c == RED else c for c in colors]
    elif mode == 'y2r':
        mapped = [RED if c == YELLOW else c for c in colors]
    elif mode == 'yr2r':
        mapped = [RED if c == RED or c == YELLOW else c for c in colors]
    elif mode == 'yr2y':
        mapped = [YELLOW if c == RED or c == YELLOW else c for c in colors]
    else:
        mapped = colors
    return [v for c in mapped for v in c]
