from PIL import Image, ImageDraw
from modules.generate_views.image_transform import rotate_image, invert_image
from modules.generate_views.palette_mapper import map_palette

# 预定义常用尺寸的墨水屏，h表示横屏，v表示竖屏
SIZES = {
    'm':    (200, 200), # 对应1.54inch墨水屏，无需区分
    'hl':   (250, 122), # 对应2.13inch墨水屏，横屏
    'hxl':  (384, 184), # 对应3.50inch墨水屏，横屏
    'h2xl': (400, 300), # 对应4.20inch墨水屏，横屏
    'h3xl': (600, 480), # 对应5.83inch墨水屏，横屏
    'h4xl': (800, 480), # 对应7.50inch墨水屏，横屏
    'vl':   (122, 250), # 对应2.13inch墨水屏，竖屏
    'vxl':  (184, 384), # 对应3.50inch墨水屏，竖屏
    'v2xl': (300, 400), # 对应4.20inch墨水屏，竖屏
    'v3xl': (480, 600), # 对应5.83inch墨水屏，竖屏
    'v4xl': (480, 800)  # 对应7.50inch墨水屏，竖屏
}

# 多种调色板定义
PALETTES = {
    'bw': [255, 255, 255, 0, 0, 0], # 白黑 双色
    'bwr': [255, 255, 255, 0, 0, 0, 255, 0, 0], # 白黑红 三色
    'bwy': [255, 255, 255, 0, 0, 0, 255, 255, 0],  # 白黑黄 三色
    'bwry': [255, 255, 255, 0, 0, 0, 255, 0, 0, 255, 255, 0],  # 白黑红黄 四色
    '7color': [255, 255, 255, 0, 0, 0, 255, 0, 0, 255, 255, 0, 0, 255, 0, 0, 0, 255, 255, 128, 0]# 白黑红黄绿蓝橙 七色
}
# 创建预定义尺寸的墨水屏画布，必须指定调色板
def create_canvas(size_key, palette_type, cmode=None):
    size = SIZES.get(size_key)
    if not size:
        raise ValueError(f'未知尺寸: {size_key}')
    palette = PALETTES.get(palette_type)
    if not palette:
        raise ValueError(f'未知调色板类型: {palette_type}')
    palette = map_palette(palette, cmode)
    img = Image.new('P', size)
    img.putpalette(palette)
    draw = ImageDraw.Draw(img)
    return img, draw

# 创建自定义尺寸的墨水屏画布，必须指定调色板
def create_custom_canvas(width, height, palette_type, cmode=None):
    palette = PALETTES.get(palette_type)
    if not palette:
        raise ValueError(f'未知调色板类型: {palette_type}')
    palette = map_palette(palette, cmode)
    img = Image.new('P', (width, height))
    img.putpalette(palette)
    draw = ImageDraw.Draw(img)
    return img, draw

# 对图像进行最终处理转换格式，旋转和反转
def finalize_image_common(img, rotate=0, invert=False):
    rgb_img = img.convert('RGB')
    rgb_img = rotate_image(rgb_img, rotate)
    if invert:
        rgb_img = invert_image(rgb_img)
    return rgb_img
