"""月相图案绘制：把相位角渲染成可直接贴到墨水屏画布上的 1-bit 精灵。

与插件框架、天文计算完全解耦，只依赖 Pillow，任何插件都能直接复用。

为什么不用「先降采样、再最近邻旋转」这种写法：精灵是二值图（纯黑/透明），在低分辨率上
做最近邻旋转会把边缘拧成锯齿，并在轮廓上留下断点与孤立散点——墨水屏上就是肉眼可见的
「空白像素瑕疵」。这里的做法是：

1. 在 `size * supersample` 的高分辨率下，用**一条闭合多边形**画出整轮月面（受光区），
   而不是拼接「半圆 + 椭圆」——拼接法在多边形接缝与上下极点处会留下细缝；
2. 在高分辨率上旋转（BICUBIC），避开低分辨率旋转的锯齿；
3. 降采样回目标尺寸（LANCZOS），此时边缘是平滑的灰度过渡；
4. 最后**统一二值化一次**，收敛成干净的 0/255 边界。

渲染结果按（相位角, 尺寸, 旋转角, 是否画轮廓, 超采样倍数）缓存住二值蒙版：相位角变化极慢，
同一台设备反复轮询时命中率很高，省掉重复的高分辨率绘制与旋转。蒙版是只读的，每次调用
另建一张 RGBA 精灵返回，调用方拿到的是独立副本。
"""

import math
from functools import lru_cache

from PIL import Image, ImageDraw

# 超采样倍数：4 倍足以把 1px 的轮廓与边缘平滑掉，再高收益递减、开销翻倍
DEFAULT_SUPERSAMPLE = 4
# 相位角量化步长（度）：0.1° 远小于墨水屏可分辨的差异，却能让缓存有效命中
_ANGLE_STEPS = 10
# 蒙版缓存条目上限：常规尺寸的蒙版约几十 KB，32 条足以覆盖数天内用到的相位
_MASK_CACHE_SIZE = 32


def draw_moon_sprite(phase_angle_degrees, size, rotation=0.0, outline=True,
                     supersample=DEFAULT_SUPERSAMPLE):
    """绘制月相精灵。

    phase_angle_degrees: 相位角，0=新月、90=上弦、180=满月、270=下弦（北半球视角）
    size:               精灵边长（像素）
    rotation:           整体旋转角度（度，PIL 口径：正数逆时针），用于按观测纬度摆正
    outline:            是否画出整轮月面的 1px 圆轮廓

    返回 `size x size` 的 RGBA 精灵：不透明处为黑色墨点，其余透明。
    """
    mask = _moon_mask(
        round((phase_angle_degrees % 360) * _ANGLE_STEPS) / _ANGLE_STEPS,
        int(size),
        round((rotation % 360) * _ANGLE_STEPS) / _ANGLE_STEPS,
        bool(outline),
        int(supersample),
    )
    sprite = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    sprite.paste((0, 0, 0, 255), (0, 0, size, size), mask=mask)
    return sprite


@lru_cache(maxsize=_MASK_CACHE_SIZE)
def _moon_mask(phase_angle_degrees, size, rotation, outline, supersample):
    """→ 只读二值蒙版（255 表示墨点）。参数需可哈希，故由 draw_moon_sprite 量化后传入。"""
    hi = size * supersample
    mask = _draw_lit_mask(phase_angle_degrees, hi, supersample, outline)
    if rotation:
        # 在高分辨率上旋转：低分辨率的二值旋转正是锯齿与断点的来源
        mask = mask.rotate(rotation, resample=Image.BICUBIC, expand=False)
    mask = mask.resize((size, size), Image.LANCZOS)
    # 只在这一处做二值化：抗锯齿的灰度在这里收敛成干净的 0/255
    return mask.point(lambda value: 255 if value >= 128 else 0, mode='L')


def _draw_lit_mask(phase_angle_degrees, hi, supersample, outline):
    """在 `hi x hi` 的高分辨率上画出「受光区 ∪ 月面轮廓」，白=墨。"""
    angle = phase_angle_degrees % 360
    center = hi / 2.0
    # 留 1 个最终像素的边距，保证轮廓不被画布边缘裁掉
    radius = center - supersample
    box = [center - radius, center - radius, center + radius, center + radius]
    mask = Image.new('L', (hi, hi), 0)
    draw = ImageDraw.Draw(mask)

    draw.polygon(_lit_polygon(angle, center, radius), fill=255)

    # 轮廓最后画：放在受光区之后，月牙在上下两极的收口才不会把圆咬断
    if outline:
        draw.ellipse(box, outline=255, width=supersample)
    return mask


def _lit_polygon(angle, center, radius):
    """受光区域的闭合多边形顶点。

    轮廓分两段描边，合成一条不自交的封闭路径：
    - 外缘：受光一侧的半个圆周，由上极点经该侧走到下极点；
    - 明暗界线：由下极点沿半月牙状的椭圆界线回到上极点。

    界线在高度 y 处的位置为 `x = ±R·cosθ·sin(t)`：θ=0/360° 时与受光侧外缘重合（无受光），
    θ=90°/270° 时退化成竖直线（恰好半个月面），θ=180° 时与另一侧外缘重合（整轮受光）。
    """
    k = math.cos(math.radians(angle))
    steps = max(360, int(radius))
    limb, terminator = [], []
    for i in range(steps + 1):
        t = math.pi * i / steps
        y = center - radius * math.cos(t)
        sin_t = math.sin(t)
        if angle < 180:
            limb.append((center + radius * sin_t, y))
            terminator.append((center + radius * k * sin_t, y))
        else:
            limb.append((center - radius * sin_t, y))
            terminator.append((center - radius * k * sin_t, y))
    # 界线倒序拼接，使路径在上下极点处闭合且不自交
    return limb + terminator[::-1]
