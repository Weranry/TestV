"""预渲染成品缓存的产物编解码：一份与「请求格式 / 后处理参数」无关的图。

存「索引数组 + 调色板」（`P` 模式，PNG 作容器）而不是按请求编码好的成品图，于是
`rotate` / `invert` / `cmode` / `format` 全部退出缓存键，命中时按当次请求现场套用。

为什么 `cmode` 能事后精确重映射：视图在 `P` 画布上按**索引**绘制，`cmode` 经
`map_palette()` 只改**调色板表**、不动索引。只要调色板还在，事后重映射与当时渲染等价。

超过 256 色时（视图自己在 RGB 空间做过混合/抖动）回退存 RGB PNG：调色板已丢，
`cmode` 只能退化成「按颜色替换」（近似）。这是回退路径，正常视图不会走到。
"""
import io

from PIL import Image, ImageChops

from modules.generate_views.palette_mapper import map_palette

ART_INDEXED = 'p'
ART_RGB = 'rgb'

# map_palette 的规则只认这四个颜色（见 palette_mapper.py）
_SPECIAL_COLORS = ((255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0))

# 超过这个颜色数就没法用调色板表达，必须回退 RGB
_MAX_COLORS = 256


def encode_canonical(img):
    """渲染结果 → (payload, art_kind, width, height)"""
    rgb = img.convert('RGB')
    width, height = rgb.size
    # maxcolors 多给 1：正好 257 色时 getcolors 会返回 257 条而不是 None，得靠长度判断
    colors = rgb.getcolors(maxcolors=_MAX_COLORS + 1)
    if colors and len(colors) <= _MAX_COLORS:
        # 按颜色排序建调色板：顺序必须稳定，否则同图两次编码出来字节不同
        palette_colors = sorted(color for _count, color in colors)
        flat = [v for color in palette_colors for v in color]
        # quantize(palette=...) 是 C 实现的最邻近匹配，颜色全在表内 → 距离 0 → 逐像素精确
        palette_img = Image.new('P', (1, 1))
        palette_img.putpalette(flat)
        indexed = rgb.quantize(palette=palette_img, dither=Image.Dither.NONE)
        return _to_png(indexed), ART_INDEXED, width, height
    return _to_png(rgb), ART_RGB, width, height


def decode_canonical(payload, art_kind, cmode=None):
    """产物 → RGB 图（`cmode` 按 map_palette 的规则现算）"""
    img = Image.open(io.BytesIO(payload or b''))
    img.load()  # 必须 load：BytesIO 出了作用域就被回收，惰性读取会失败
    if art_kind == ART_INDEXED and img.mode == 'P':
        img.putpalette(map_palette(img.getpalette() or [], cmode))
        return img.convert('RGB')
    return _remap_rgb(img.convert('RGB'), cmode)


def _to_png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _color_map(cmode):
    """cmode → {原色: 新色}，只保留真正发生变化的颜色"""
    out = {}
    for color in _SPECIAL_COLORS:
        mapped = tuple(map_palette(list(color), cmode))
        if mapped != color:
            out[color] = mapped
    return out


def _remap_rgb(img, cmode):
    """RGB 回退路径：按颜色替换实现 cmode（调色板已丢失，只能是近似）

    与原「逐像素 Python 循环 + mapping.get(三元组)」完全等价，只在整三元组
    精确相等时替换（不因逐通道近似而误替换），但改走 Pillow 的 C 层：
    先用 difference 取每通道的绝对差，再把「三通道都为 0（= 整像素相等）」合成掩码，
    最后只在该掩码上 composite 出新色。输出与原实现逐字节一致。
    """
    mapping = _color_map(cmode)
    if not mapping:
        return img
    out = img
    for src, dst in mapping.items():
        bands = ImageChops.difference(img, Image.new('RGB', img.size, src)).split()
        # 单通道相等 → 255，否则 0；三通道相与才是整像素相等
        mask = None
        for band in bands:
            equal = band.point(lambda v: 255 if v == 0 else 0)
            mask = equal if mask is None else ImageChops.multiply(mask, equal)
        out = Image.composite(Image.new('RGB', img.size, dst), out, mask)
    return out