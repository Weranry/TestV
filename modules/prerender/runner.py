"""预渲染任务的执行：把任务参数渲染成成品图 / JSON 字节。

每次执行都从磁盘现取模块、现查插件状态，禁止捕获路由对象或模块实例：
插件热重载会清掉 sys.modules 里的 plugins.*，捕获下来的旧对象指向的是已删除的代码。
"""
import asyncio
import importlib
import inspect
import json
import time

from modules.prerender import store
from modules.prerender.keying import load_params
from modules.utils import plog

# 视图路由里由路由层单独解析、不传给 generate_image 的保留参数
_RESERVED = ('size', 'rotate', 'invert', 'cmode', 'fmt')

STATUS_RENDERED = 'rendered'
STATUS_SKIPPED = 'skipped'
STATUS_INVALID = 'invalid'
STATUS_ERROR = 'error'


def _route_name(route_path):
    """/{插件}/view/{种类} 或 /{插件}/json/{名称} 的最后一段"""
    return (route_path or '').rstrip('/').split('/')[-1]


def _availability(app, task):
    """任务当前是否可执行。返回 (状态, 原因)，None 表示可执行。

    插件/路由被禁用记 skipped —— 这是"暂时不做"，缓存要留着，重新启用即可继续命中；
    插件目录已被删记 invalid —— 任务不可能再成功，但也不自动删，交给管理员处置。
    """
    plugin_name = task['plugin_name']
    states = getattr(app.state, 'plugin_states', {}) or {}
    if plugin_name not in states:
        return STATUS_INVALID, f'插件 {plugin_name} 不存在'
    if states.get(plugin_name) is False:
        return STATUS_SKIPPED, f'插件 {plugin_name} 已禁用'
    disabled = getattr(app.state, 'disabled_routes', None) or set()
    if task['route_path'] in disabled:
        return STATUS_SKIPPED, f'路由 {task["route_path"]} 已禁用'
    return None, ''


async def _call_render(func, kwargs):
    """同步渲染是 CPU 密集的（Pillow / 数据拼装），必须挪到线程，否则会卡住事件循环"""
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    return await asyncio.to_thread(func, **kwargs)


async def _render_view(task, params):
    """视图任务 → (产物字节, 产物种类, 宽, 高)

    固定以 rotate=0 / invert=False / cmode=None 出图：产物要「与后处理无关」，
    命中时再按当次请求套用，否则旋转、反色、cmode 会被烘进图里无法还原。
    """
    from modules.prerender import artifact

    plugin_name = task['plugin_name']
    kind = _route_name(task['route_path'])
    size = params.get('size') or task['size']
    if not size:
        raise RuntimeError('视图任务缺少 size 参数')

    mod_path = f'plugins.{plugin_name}.view.{kind}.{size}'
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f'视图 {mod_path} 不存在: {exc}')
    if not hasattr(mod, 'generate_image'):
        raise RuntimeError(f'视图 {mod_path} 未实现 generate_image')

    kwargs = {k: v for k, v in params.items() if k not in _RESERVED}
    img = await _call_render(mod.generate_image, {
        'rotate': 0,
        'invert': False,
        'cmode': None,
        **kwargs,
    })
    # 编码（convert/getcolors/quantize/PNG）是纯 CPU，必须和渲染一样下放线程，
    # 否则刚让出的渲染又用编码占住事件循环
    return await asyncio.to_thread(artifact.encode_canonical, img)


async def _render_json(task, params):
    """JSON 任务 → (产物字节, 产物种类, 宽, 高)"""
    plugin_name = task['plugin_name']
    name = _route_name(task['route_path'])
    mod_path = f'plugins.{plugin_name}.json_module.{name}'
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f'JSON模块 {mod_path} 不存在: {exc}')
    if not hasattr(mod, 'to_json'):
        raise RuntimeError(f'JSON模块 {mod_path} 未实现 to_json')

    result = await _call_render(mod.to_json, params)
    # 与 starlette.JSONResponse.render 完全一致：命中与实时返回的字节必须相同
    content = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=None,
                         separators=(',', ':')).encode('utf-8')
    return content, 'json', 0, 0


async def run_task(app, task):
    """渲染一个任务并存缓存，返回 {status, error, elapsed_ms}（不写任务行）"""
    import config

    started = time.perf_counter()
    status, error = STATUS_ERROR, ''
    try:
        status, error = _availability(app, task)
        if status is None:
            params = load_params(task['params_json'])
            coro = _render_json(task, params) if task['route_kind'] == 'json' \
                else _render_view(task, params)
            try:
                timeout = max(1, int(config.PRERENDER_TIMEOUT_SECONDS or 30))
            except (TypeError, ValueError):
                timeout = 30
            payload, art_kind, width, height = await asyncio.wait_for(coro, timeout)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            store.put_cache(task['cache_key'], task['id'], art_kind, width, height,
                            payload, elapsed_ms)
            status, error = STATUS_RENDERED, ''
    except asyncio.TimeoutError:
        error = f'渲染超时（>{config.PRERENDER_TIMEOUT_SECONDS}s）'
    except Exception as exc:
        error = str(exc)
        plog.exception(f'预渲染任务 {task["id"]} 渲染失败')
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {'status': status, 'error': error, 'elapsed_ms': elapsed_ms}