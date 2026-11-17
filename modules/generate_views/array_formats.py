"""数组格式族：把渲染结果按面板调色板的色数打包成紧凑位流。

码表就是调色板索引（白=0、黑=1、红=2、黄=3、绿=4、蓝=5、橙=6），颜色序从
`canvas_factory.PALETTES` 现取，不在本模块另抄一份字面量。位序 MSB 在前，
每行末尾补 0 bit 到整字节（与 PIL 模式 `1` 的 `tobytes()` 同一约定）。

`cmode` 不在这里参与运算：它已在渲染链路（`create_canvas`）或预渲染命中链路
（`decode_canonical`）改过调色板，本模块只做「颜色 → 码」的搭桥。

规格与决策见 .trae/documents/数组格式族扩展方案.md。
"""
from PIL import Image

from modules.generate_views.palette_mapper import CMODE_MODES, map_palette

# format → canvas_factory.PALETTES 的键。色数决定位数：2 色 1bpp、3~4 色 2bpp、5~8 色 3bpp
ARRAY_FORMATS = {
    'array': 'bw',
    'bwarray': 'bw',
    'bwrarray': 'bwr',
    'bwyarray': 'bwy',
    'bwryarray': 'bwry',
    '7carray': '7color',
}

# 别名 → 正式名。黑名单与用户组权限键都按正式名查，否则「禁了 format_array
# 却能改用 bwarray 绕开」
_ALIASES = {'bwarray': 'array'}

# 降级规则链：2bw 会把任何颜色压成白/黑，必须放最后，前面的 r2y / y2r 才有机会
# 把红黄落进目标调色板。模式名仍以 palette_mapper.CMODE_MODES 为唯一来源。
_DOWNGRADE_MODES = tuple(m for m in CMODE_MODES if m != '2bw') + ('2bw',)

_MAX_COLORS = 256

# 逐位取值表：码 → 255/0，供 translate 在 C 层展开成位平面
_BIT_TABLES = {k: bytes(255 if (v >> k) & 1 else 0 for v in range(256)) for k in range(8)}
# 1bpp 位流取反（PIL 的 `1` 图里位=1 表示白，本模块位=1 表示黑）
_NOT_BITS = bytes(255 - i for i in range(256))
# 'L' 的 0/255 → 码 0/1
_TO_01 = bytes([0] * 255 + [1])


def canonical_format(fmt):
    """别名归一：`bwarray` → `array`"""
    return _ALIASES.get(fmt, fmt)


def is_array_format(fmt):
    return fmt in ARRAY_FORMATS


def array_formats():
    """数组格式族的全部名字（面板候选用）"""
    return sorted(ARRAY_FORMATS)


# 调色板 → 该调色板唯一对应的数组格式（正式名）。设备只上报「支持颜色」（palette），
# 输出格式由它推导、不再让用户手选。`bwarray` 是 `array` 的别名，建表时跳过，保证
# 'bw' 落到正式名 `array` —— 与 `canonical_format` 同一口径。
PALETTE_FORMATS = {key: name for name, key in ARRAY_FORMATS.items() if name not in _ALIASES}


def format_for_palette(palette_key):
    """调色板键 → 唯一对应的数组格式；未知调色板返回 None。"""
    return PALETTE_FORMATS.get(palette_key)


def _palette_colors(palette_key):
    from modules.generate_views.canvas_factory import PALETTES
    palette = PALETTES[palette_key]
    return [tuple(palette[i:i + 3]) for i in range(0, len(palette), 3)]


def _bits_of(color_count):
    return max(1, (color_count - 1).bit_length())


def _is_light(color):
    """PIL 的亮度阈值判定，与旧 `array`（`convert('1')`）完全同一口径"""
    probe = Image.new('RGB', (1, 1), tuple(color))
    return probe.convert('1', dither=Image.Dither.NONE).getpixel((0, 0)) != 0


def _code_of(color, palette):
    """颜色 → 码：精确命中 → cmode 降级规则链 → 亮度兜底"""
    if color in palette:
        return palette.index(color)
    for mode in _DOWNGRADE_MODES:
        mapped = tuple(map_palette(list(color), mode))
        if mapped in palette:
            return palette.index(mapped)
    # 现有调色板都含白与黑，2bw 必然命中，这一行只是兜底
    return 0 if _is_light(color) else 1


def _codes_by_index(rgb, present, palette):
    """≤256 色：先精确取回索引（距离 0，不是最近色），再把「出现色 → 码」翻译过去。

    翻译表必须按**目标调色板**取码：`present` 只是 quantize 用的排序色表，
    它的下标不等于码（本就不含未出现的色，白/黑也未必排在前面）。
    """
    flat = [v for color in present for v in color]
    flat += [0] * (768 - len(flat))
    palette_img = Image.new('P', (1, 1))
    palette_img.putpalette(flat)
    indexed = rgb.quantize(palette=palette_img, dither=Image.Dither.NONE)
    table = bytearray(_MAX_COLORS)
    for i, color in enumerate(present):
        table[i] = _code_of(color, palette)
    return indexed.tobytes().translate(bytes(table))


def _codes_by_luma(rgb):
    """>256 色（照片类）取不到索引：退回亮度阈值，白→码 0、黑→码 1"""
    bw = rgb.convert('1', dither=Image.Dither.NONE)  # 位=1 表示白
    flipped = Image.frombytes('1', bw.size, bw.tobytes().translate(_NOT_BITS))
    return flipped.convert('L').tobytes().translate(_TO_01)


def _pack(codes, width, height, bits):
    """逐像素码 → MSB 在前、行末补 0 bit 到整字节的位流。

    每像素摊成 `bits` 个子像素（高位在前）后交给 PIL 转 1bpp：行末自然补 0，
    长度即 `ceil(w*bits/8)*h`。全链路都在 C 层（translate / 步长切片 / convert），
    没有逐像素 Python 循环。
    """
    expanded = bytearray(len(codes) * bits)
    for j in range(bits):
        expanded[j::bits] = codes.translate(_BIT_TABLES[bits - 1 - j])
    wide = Image.frombytes('L', (width * bits, height), bytes(expanded))
    return wide.convert('1', dither=Image.Dither.NONE).tobytes()


def pack_array(img, fmt):
    """渲染结果 → 该数组格式的位流字节（长度 `ceil(w*bits/8)*h`）"""
    palette_key = ARRAY_FORMATS.get((fmt or '').lower())
    if palette_key is None:
        raise ValueError(f'不是数组格式: {fmt}')
    palette = _palette_colors(palette_key)
    rgb = img if img.mode == 'RGB' else img.convert('RGB')
    # maxcolors 多给 1：正好 257 色时 getcolors 返回 257 条而不是 None，得靠长度判断
    found = rgb.getcolors(maxcolors=_MAX_COLORS + 1)
    if found and len(found) <= _MAX_COLORS:
        present = sorted(color for _count, color in found)
        codes = _codes_by_index(rgb, present, palette)
    else:
        codes = _codes_by_luma(rgb)
    return _pack(codes, rgb.width, rgb.height, _bits_of(len(palette)))
