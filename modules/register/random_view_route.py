import asyncio
import os
import importlib
import inspect
import random
import time
from fastapi import APIRouter, Request
from modules.errors.errors import AccessDeniedError, ParamError, RenderError
import config
from modules.plugins.plugin_loader import load_plugin_config, get_plugin_default_args
from modules.generate_views.image_output import save_image
from modules.utils import plog

router = APIRouter()


def parse_routes_param(param):
    if not param:
        raise ParamError('routes参数不能为空')
    items = []
    parts = param.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        segs = part.split(':')
        if len(segs) < 2:
            continue
        view_path = segs[0]
        size = segs[1]
        # view_path 必须是「插件.种类」两段式、size 必须非空且是合法模块名：否则后面
        # split('.', 1) 会直接抛 ValueError 变成 500，拼出来的模块路径也不可能是插件视图
        if view_path.count('.') != 1 or not size \
                or not size.isidentifier() or size.startswith('_'):
            continue
        weight = 1.0
        param_dict = {}
        param_start = 2
        if len(segs) > 2 and '=' not in segs[2]:
            try:
                weight = float(segs[2])
                param_start = 3
            except ValueError:
                pass
        for s in segs[param_start:]:
            if '=' in s:
                k, v = s.split('=', 1)
                param_dict[k] = v
        items.append(((view_path, size), weight, param_dict))
    filtered = [i for i in items if i[1] > 0]
    if not filtered:
        raise ParamError('所有权重均为0或未设置，无法选择视图')
    return filtered


def _allowed_choices(request, choices, group_id):
    """剔除不可用的候选视图，返回还能参与随机的候选列表。

    本端点挂在 /random 下，中间件是按 URL 首段判插件与路由权限的，看不到真正被
    随机到的目标视图；不在这里自己过滤，被禁用的插件/路由、以及用户组无权访问的
    视图都能靠 `routes=weather.summary:hxl` 绕过。
    """
    state = request.app.state
    states = getattr(state, 'plugin_states', {}) or {}
    disabled_routes = getattr(state, 'disabled_routes', set()) or set()
    allowed = []
    for (view_path, size), weight, param_dict in choices:
        plugin, kind = view_path.split('.', 1)
        route_path = f'/{plugin}/view/{kind}'
        # 未注册的插件（目录被删 / 加载失败）与显式禁用的路由一律不给
        if states.get(plugin) is not True or route_path in disabled_routes:
            continue
        if group_id is not None:
            from modules.database.access import (
                check_user_plugin_access, check_user_route_access,
            )
            if not check_user_plugin_access(group_id, plugin) \
                    or not check_user_route_access(group_id, route_path):
                continue
        allowed.append(((view_path, size), weight, param_dict))
    if not allowed:
        raise ParamError('没有可用的视图：候选插件/路由已被禁用，或当前用户组无权访问')
    return allowed


@router.get('/random/views')
async def random_views(request: Request):
    routes_param = request.query_params.get('routes')
    if not routes_param:
        raise ParamError('缺少 routes 参数')

    from modules.prerender.params import (
        explicit_value, parse_cmode_arg, parse_invert_arg, parse_rotate_arg,
    )
    # 保留参数与 /{plugin}/view/{kind} 走同一份解析：非法值一律 400，
    # 不再「在视图路由上报错、在随机视图上静默按默认值出图」
    rotate_arg = explicit_value(request.query_params, 'rotate')
    invert_arg = explicit_value(request.query_params, 'invert')
    global_rotate = parse_rotate_arg(rotate_arg)
    global_invert = parse_invert_arg(invert_arg)
    cmode_global = parse_cmode_arg(explicit_value(request.query_params, 'cmode'))

    group_id = getattr(request.state, 'user_group_id', None)
    choices = _allowed_choices(request, parse_routes_param(routes_param), group_id)
    view_size_pairs = [vc for vc, _, _ in choices]
    weights = [weight for _, weight, _ in choices]
    params_list = [param_dict for _, _, param_dict in choices]

    idx = random.choices(range(len(view_size_pairs)), weights=weights, k=1)[0]
    (view_path, size) = view_size_pairs[idx]
    params = params_list[idx]
    plugin, kind = view_path.split('.', 1)

    mod_path = f'plugins.{plugin}.view.{kind}.{size}'
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as e:
        plog.exception(f'视图 {mod_path} 不存在')
        raise ParamError(f'视图 {mod_path} 不存在: {str(e)}')

    plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f'../../plugins/{plugin}'))
    plugin_config = load_plugin_config(plugin, plugin_dir)
    plugin_default_args = get_plugin_default_args(plugin, plugin_dir)
    plugin_default_rotate = plugin_config.get('DEFAULT_ROTATE', None)
    plugin_default_invert = plugin_config.get('DEFAULT_INVERT', None)

    extra_params = dict(plugin_default_args)
    extra_params.update(params)
    extra_params.pop('rotate', None)
    extra_params.pop('invert', None)
    extra_params.pop('cmode', None)

    cmode = parse_cmode_arg(explicit_value(params, 'cmode')) or cmode_global \
        or plugin_default_args.get('cmode')

    rotate_val = parse_rotate_arg(explicit_value(params, 'rotate'))
    rotate = rotate_val if rotate_val is not None \
        else (global_rotate if global_rotate is not None \
        else (plugin_default_rotate if plugin_default_rotate is not None else config.DEFAULT_ROTATE))

    invert_val = parse_invert_arg(explicit_value(params, 'invert'))
    invert = invert_val if invert_val is not None \
        else (global_invert if global_invert is not None \
        else (plugin_default_invert if plugin_default_invert is not None else config.DEFAULT_INVERT))

    if not hasattr(mod, 'generate_image'):
        raise ParamError(f'视图 {mod_path} 未实现 generate_image')

    try:
        if group_id is not None:
            from modules.database.access import check_group_param_access
            for pk, pv in (('rotate', rotate_arg or params.get('rotate')),
                           ('invert', invert_arg or params.get('invert')),
                           ('cmode', cmode)):
                if pv is not None and not check_group_param_access(group_id, pk):
                    raise ParamError(f'用户组禁止使用{pk}参数')
        from modules.app_core import get_render_semaphore
        from modules.generate_views import render_metrics
        user = getattr(request.state, 'user', None) or {}
        sem = await get_render_semaphore(request.app, group_id, user.get('id'))
        async with sem:
            # 与 auto_view_routes 同一套渲染指标：随机路由漏统计会让健康检查里的
            # 「进行中 / 最近耗时」看不到这一半流量
            render_metrics.mark_start()
            started = time.perf_counter()
            try:
                if inspect.iscoroutinefunction(mod.generate_image):
                    img = await mod.generate_image(rotate=rotate, invert=invert, cmode=cmode, **extra_params)
                else:
                    # 同 auto_view_routes：同步视图是纯 CPU 的 Pillow 绘制，直接调用会卡住事件循环
                    img = await asyncio.to_thread(
                        mod.generate_image, rotate=rotate, invert=invert, cmode=cmode, **extra_params)
            finally:
                # 失败也必须收尾，否则 active 只增不减，健康检查会一直显示「渲染进行中」
                render_metrics.mark_end((time.perf_counter() - started) * 1000)
    except (ParamError, AccessDeniedError):
        # 框架自己的参数 / 权限错误必须原样上抛：被下面的兜底包成 ParamError 会把权限不足
        # 的 403 语义压成 400，调用方拿不到「该找管理员开通」的提示
        raise
    except Exception as e:
        plog.exception(f'随机图片生成失败: {e}')
        # 同 auto_view_routes：渲染失败是服务端的问题，必须是 500 而不是 400
        raise RenderError(f'随机图片生成失败: {str(e)}')

    img_format = request.query_params.get('format', config.DEFAULT_IMAGE_FORMAT)
    # 编码也是 CPU 密集，下放线程
    return await asyncio.to_thread(
        save_image, img, img_format, [plugin, kind, size], group_id=group_id)