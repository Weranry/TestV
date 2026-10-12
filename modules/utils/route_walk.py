"""展开 `app.router.routes` 里的惰性包含，得到真正生效的路由对象。

FastAPI 0.141 起 `include_router()` 不再把子路由摊平进 `router.routes`，而是塞一个
`_IncludedRouter` 占位（它没有 `.path`），真正展开发生在匹配请求时。于是任何
「遍历全部路由」的代码（接口清单、管理接口的全量路由覆盖断言）都必须显式展开，
否则拿到的是一堆空壳：结果是空列表、且不报错，属于静默失效。
"""


def iter_routes(routes):
    """逐个产出可用的路由对象（带 `path` / `methods` 的 APIRoute 或其上下文包装）

    展开用 `_IncludedRouter.effective_route_contexts()`（内部已递归处理多层 include）；
    普通路由与 Starlette Route 直接产出。
    """
    for route in routes:
        expand = getattr(route, 'effective_route_contexts', None)
        if callable(expand):
            for ctx in expand():
                if getattr(ctx, 'path', None):
                    yield ctx
            continue
        if getattr(route, 'path', None):
            yield route