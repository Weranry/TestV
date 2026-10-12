"""接口清单：管理面板里的「接口文档」，替代 prod 下打不开的 `/docs`。

`/docs` 与 `/openapi.json` 是 FastAPI 自动生成的，但它们挂在需要鉴权的链路上
（prod 下浏览器直接打开只会拿到 401），而放行它们等于向匿名暴露全量路由结构。
这里改为由登录后的面板**现算**一份精简清单：方法、完整路径、所属插件、视图种类 /
JSON 名、是否需要 evkey、插件描述——够屏端固件开发者查接口，不额外暴露任何东西。
"""
import config
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.utils.route_walk import iter_routes

router = APIRouter()

# 后台自身与框架端点：对「接口清单」的读者（屏端固件 / 调用方）没有意义，
# 列进去只会把真正要看的业务接口淹没
_SKIP_PREFIXES = ('/admin', '/docs', '/redoc', '/openapi.json', '/public')

# 一个路径下要展示的请求方法；HEAD / OPTIONS 是框架与浏览器自动发的，不列
_IGNORED_METHODS = ('HEAD', 'OPTIONS')


def _needs_evkey(path):
    """与鉴权中间件同一套白名单判定：'/' 只精确匹配，其余按前缀匹配"""
    for prefix in config.AUTH_WHITELIST:
        if path == prefix or (prefix != '/' and path.startswith(prefix)):
            return False
    return True


def _describe_path(path, plugin_names):
    """路径 → (插件名, 类型, 名称)

    只按「第一段是已知插件名」判定，不靠 `/x/y/z` 的段数猜：插件可以注册自定义
    路由（不挂在 /插件名/ 下），按段数猜会把无关路径误认成插件接口。
    """
    parts = [seg for seg in path.strip('/').split('/') if seg]
    if not parts:
        return '', '', ''
    name = parts[0]
    if name not in plugin_names:
        return '', '', ''
    if len(parts) >= 2 and parts[1] in ('view', 'json', 'page'):
        return name, parts[1], (parts[2] if len(parts) > 2 else '')
    return name, '', ''


@router.get('/api/api-docs')
async def admin_api_docs(request: Request):
    """现算接口清单；路由变化（插件热重载、开关路由）后重新拉一次即可"""
    app = request.app
    result = getattr(app.state, 'plugin_result', {}) or {}
    descriptions = {p.get('name'): p.get('description', '') for p in result.get('plugins', [])}
    plugin_names = set(getattr(app.state, 'plugin_states', {}) or {})

    rows = []
    # 必须走 iter_routes 展开惰性 include：新版 FastAPI 的 router.routes 里装的是空壳，
    # 直接遍历会得到一份空清单（且不报错）
    for route in iter_routes(app.router.routes):
        path = getattr(route, 'path', '') or ''
        if not path or path.startswith(_SKIP_PREFIXES):
            continue
        methods = [m for m in (getattr(route, 'methods', None) or ())
                   if m not in _IGNORED_METHODS]
        if not methods:
            continue
        plugin, kind, name = _describe_path(path, plugin_names)
        for method in sorted(methods):
            rows.append({
                'method': method,
                'path': path,
                # 路径里带 {param} 的是管理/框架类参数路由，业务插件接口都是字面路径
                'param_path': '{' in path,
                'plugin': plugin,
                'kind': kind,
                'name': name,
                'description': descriptions.get(plugin, '') if plugin else '',
                'need_evkey': _needs_evkey(path),
            })
    rows.sort(key=lambda r: (not bool(r['plugin']), r['path'], r['method']))
    return JSONResponse({'routes': rows, 'total': len(rows)})