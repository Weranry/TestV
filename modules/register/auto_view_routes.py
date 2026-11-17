import asyncio
import importlib
import os
import inspect
import time
from fastapi import Request
from modules.errors.errors import AccessDeniedError, ParamError, RenderError
from modules.generate_views.image_output import save_image
from modules.utils import plog


def available_view_sizes(plugin_name, view_dir, kind):
    """`view/<kind>/` 下**真正可用**的尺寸：能导入且实现了 `generate_image` 的模块。

    目录里除了 hxl / h2xl，还住着 utils.py、drawer.py 这类被视图 import 的辅助模块，
    它们不是尺寸——请求 `/插件/view/<种类>?size=utils` 必然 400。插件面板与访客导航页
    展示「可选尺寸」时按同一口径过滤，否则会把辅助模块的名字当成尺寸列给用户。
    """
    kind_path = os.path.join(view_dir, kind)
    if not os.path.isdir(kind_path):
        return []
    sizes = []
    for entry in sorted(os.listdir(kind_path)):
        if entry.startswith('_') or entry.startswith('.') or not entry.endswith('.py'):
            continue
        size = entry[:-3]
        try:
            mod = importlib.import_module(f'plugins.{plugin_name}.view.{kind}.{size}')
        except Exception:
            # 导入就失败的模块本就不可能出图（缺依赖 / 语法错），不列为可选尺寸
            continue
        if hasattr(mod, 'generate_image'):
            sizes.append(size)
    return sizes


def register_view_routes(router, plugin_name, view_dir):
    # 只有视图目录时才注册：插件可以只提供 json_module/ 而不写任何视图，
    # 缺了这个判断 os.listdir 会抛 FileNotFoundError，把整个插件的注册流程带崩。
    if not os.path.exists(view_dir):
        return
    plugin_dir = os.path.dirname(view_dir)

    for kind in sorted(os.listdir(view_dir)):
        # 跳过 __pycache__ 这类下划线开头的目录，否则会被当成视图种类注册出
        # /插件/view/__pycache__ 这种幽灵路由（调用时必然 400）
        if kind.startswith('_') or kind.startswith('.'):
            continue
        kind_path = os.path.join(view_dir, kind)
        if not os.path.isdir(kind_path):
            continue

        async def make_view_endpoint(request: Request, _kind=kind):
            from modules.prerender.params import resolve_view_params
            # 参数解析与预渲染任务创建共用一份实现，否则缓存键与运行时参数会悄悄对不上
            params = resolve_view_params(
                plugin_name, plugin_dir, request.query_params.get('size'), request.query_params)
            size = params['size']
            img_format = params['fmt']
            route_path = f'/{plugin_name}/view/{_kind}'

            try:
                group_id = getattr(request.state, 'user_group_id', None)
                if group_id is not None:
                    from modules.database.access import check_group_param_access
                    for pk in ('rotate', 'invert', 'cmode'):
                        if request.query_params.get(pk) is not None \
                                and not check_group_param_access(group_id, pk):
                            raise ParamError(f'用户组禁止使用{pk}参数')

                # 定时预渲染命中：业务参数一致即命中，旋转/反色/cmode/格式按本次请求现算
                from modules.prerender import store as prerender_store
                cached = await prerender_store.try_serve(
                    request, plugin_name, route_path, params, 'view', group_id)
                if cached is not None:
                    return cached

                try:
                    mod = importlib.import_module(f'plugins.{plugin_name}.view.{_kind}.{size}')
                except ModuleNotFoundError as e:
                    plog.exception(f'视图 {plugin_name}.view.{_kind}.{size} 不存在')
                    raise ParamError(f'视图 {plugin_name}.view.{_kind}.{size} 不存在: {str(e)}')
                if not hasattr(mod, 'generate_image'):
                    raise ParamError(f'视图 {plugin_name}.view.{_kind}.{size} 未实现 generate_image')

                rotate = params.pop('rotate')
                invert = params.pop('invert')
                cmode = params.pop('cmode')
                params.pop('size')
                params.pop('fmt')

                from modules.app_core import get_render_semaphore
                from modules.generate_views import render_metrics
                user = getattr(request.state, 'user', None) or {}
                sem = await get_render_semaphore(request.app, group_id, user.get('id'))
                async with sem:
                    render_metrics.mark_start()
                    started = time.perf_counter()
                    try:
                        if inspect.iscoroutinefunction(mod.generate_image):
                            img = await mod.generate_image(rotate=rotate, invert=invert, cmode=cmode, **params)
                        else:
                            # 同步 generate_image 是纯 CPU 的 Pillow 绘制，直接调用会独占
                            # 事件循环，把这个请求期间的所有其它请求全部卡住
                            img = await asyncio.to_thread(
                                mod.generate_image, rotate=rotate, invert=invert, cmode=cmode, **params)
                    finally:
                        # 失败也必须收尾，否则 active 只增不减，健康检查会一直显示"渲染进行中"
                        render_metrics.mark_end((time.perf_counter() - started) * 1000)
            except (ParamError, AccessDeniedError):
                # 框架自己的参数/权限错误必须原样上抛：AccessDeniedError 的本意是 403，
                # 被下面的兜底包成 ParamError 会变成 400，调用方拿不到"权限不足"的语义，
                # 个人控制台也无法据此提示该找管理员开通。
                raise
            except Exception as e:
                plog.exception(f'图片生成失败: {e}')
                # 渲染失败是服务端的问题：包成 ParamError 会变成 400，调用方会以为
                # 是自己参数写错了，日志统计里也会把它当成「正常流量」漏掉
                raise RenderError(f'图片生成失败: {str(e)}')

            # 编码同样是 CPU 密集（1-bit 大图 PNG/JPEG 要几十毫秒），下放线程避免卡事件循环
            return await asyncio.to_thread(
                save_image, img, img_format, [plugin_name, _kind, size], group_id=group_id)

        endpoint_name = f'view_{plugin_name}_{kind}'
        make_view_endpoint.__name__ = endpoint_name

        router.add_api_route(
            f'/{plugin_name}/view/{kind}',
            endpoint=make_view_endpoint,
            methods=['GET'],
            name=endpoint_name,
        )