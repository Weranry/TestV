from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from ...lib.fetcher import fetch_steam_data
from .utils import render_steam_stats
from modules.errors.errors import ParamError


async def generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs):
    api_key = kwargs.get('api_key')
    steam_id = kwargs.get('steam_id')

    if not api_key or not steam_id:
        raise ParamError("Missing mandatory parameters: api_key, steam_id")

    data = await fetch_steam_data(api_key, steam_id)

    # 画布尺寸由本文件所在的模块名决定：框架在调用 generate_image 前已经把 size
    # 从业务参数里摘掉了，因此这里不能再从 kwargs 取 size。
    canvas, draw = create_canvas('v2xl', palette_type='bwr', cmode=cmode)

    # 渲染动态 Grid 网格视图
    render_steam_stats(canvas, draw, data)

    return finalize_image_common(canvas, rotate=rotate, invert=invert)
