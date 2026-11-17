from modules.generate_views.canvas_factory import create_canvas, finalize_image_common
from ...lib.fetcher import ScheduleFetcher
from .utils import render_schedule


def generate_image(rotate=0, invert=False, tz=None, cmode=None, json_name='course_schedule', **kwargs):
    # 画布尺寸由本文件所在的模块名决定：框架在调用 generate_image 前已经把 size
    # 从业务参数里摘掉了，因此这里不能再从 kwargs 取 size。
    canvas, draw = create_canvas('v2xl', palette_type='bwr', cmode=cmode)

    schedule_data = ScheduleFetcher(json_name=json_name).fetch(tz=tz)
    render_schedule(canvas, draw, schedule_data)

    return finalize_image_common(canvas, rotate=rotate, invert=invert)
