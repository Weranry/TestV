import importlib
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from modules.errors.errors import ParamError
from modules.utils import plog


def register_json_routes(router, plugin_name, json_module_dir):
    if not os.path.exists(json_module_dir):
        return
    plugin_dir = os.path.dirname(json_module_dir)

    for fname in os.listdir(json_module_dir):
        if not fname.endswith('.py') or fname.startswith('_'):
            continue
        json_name = fname[:-3]

        async def make_json_endpoint(request: Request, _json_name=json_name):
            from modules.prerender.params import resolve_json_params
            # 参数解析与预渲染任务创建共用一份实现，否则缓存键与运行时参数会悄悄对不上
            params = resolve_json_params(plugin_name, plugin_dir, request.query_params)
            route_path = f'/{plugin_name}/json/{_json_name}'

            # 定时预渲染命中：参数完全一致才命中，命中路径不再调用 to_json
            from modules.prerender import store as prerender_store
            cached = await prerender_store.try_serve(
                request, plugin_name, route_path, params, 'json',
                getattr(request.state, 'user_group_id', None))
            if cached is not None:
                return cached

            mod_path = f'plugins.{plugin_name}.json_module.{_json_name}'
            try:
                mod = importlib.import_module(mod_path)
            except ModuleNotFoundError as e:
                # 模块真的不存在：与视图路径 auto_view_routes 保持一致的文案
                plog.exception(f'JSON模块 {mod_path} 不存在')
                raise ParamError(f'JSON模块 {mod_path} 不存在: {str(e)}')
            except Exception as e:
                # 语法错误 / 缺依赖 / 模块级异常：不能再吞成「不存在」，要带原始异常信息
                plog.exception(f'JSON模块 {mod_path} 加载失败')
                raise ParamError(f'JSON模块 {mod_path} 加载失败: {str(e)}')
            if not hasattr(mod, 'to_json'):
                raise ParamError(f'JSON模块 {mod_path} 未实现 to_json')

            try:
                result = mod.to_json(**params)
            except Exception as e:
                raise ParamError(f'JSON数据生成失败: {str(e)}')
            return JSONResponse(content=result)

        endpoint_name = f'json_{plugin_name}_{json_name}'
        make_json_endpoint.__name__ = endpoint_name

        router.add_api_route(
            f'/{plugin_name}/json/{json_name}',
            endpoint=make_json_endpoint,
            methods=['GET'],
            name=endpoint_name,
        )