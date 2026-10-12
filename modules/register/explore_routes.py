"""访客导航页 `/explore`：公开页面，展示实例里正在运行的插件。

它挂在站点根下（不是 `/admin/...`）——这是给**未登录访客**看的介绍页，藏进后台路径
等于要求先登录才看得到「这站能出什么图」，与页面本身的目的相反。经 `AUTH_WHITELIST`
放行后，任何人都能打开，因此这里有一条硬规则：

    页面上出现的每一条信息都必须是「对外可见」的。

据此做了三层过滤（改动本文件时请一并守住）：
  1. 只列**加载成功且当前启用**的插件；加载失败的插件在 `/admin` 里有原因，不对外暴露。
  2. 路由只取插件自己注册的那些（`app.state.plugin_routes`），并剔除 `/admin`、`/docs`
     等框架与后台前缀；插件若自定义了 `/admin/xxx` 也照样被剔掉。
  3. 「可用用户」只显示**用户组名**，绝不列出账号、evkey、UID。

数据一次渲染完（模板里的 `{{EXPLORE_CARDS}}`），前端不拉任何接口：访客页多一个接口就多
一处「忘了鉴权 / 忘了过滤」的风险点。

渲染结果按 `plugin_generation()` 在服务端缓存（见 `_cached_html`），插件有装卸/开关/配置
变动才重算，其余请求直接命中。
"""
import html
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from modules.admin_ui.explore_page import EXPLORE_HTML
from modules.admin_ui.panel_render import panel_html, req_lang
from modules.utils.route_walk import iter_routes

router = APIRouter(tags=['explore'])

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PLUGINS_ROOT = os.path.join(PROJECT_ROOT, 'plugins')

# 对访客无意义、且属于「内部结构」的前缀：后台自身、自动文档、静态资源
_SKIP_PREFIXES = ('/admin', '/docs', '/redoc', '/openapi.json', '/public')
_IGNORED_METHODS = ('HEAD', 'OPTIONS')


def _route_rows(route_objects):
    """插件注册的路由对象 → `[{path, methods, disabled}]`，已剔除后台/文档路径"""
    rows = []
    for route in iter_routes(route_objects):
        path = getattr(route, 'path', '') or ''
        if not path or path.startswith(_SKIP_PREFIXES):
            continue
        methods = sorted(m for m in (getattr(route, 'methods', None) or ())
                         if m not in _IGNORED_METHODS)
        if not methods:
            continue
        rows.append({'path': path, 'methods': methods})
    rows.sort(key=lambda r: r['path'])
    return rows


def _view_sizes(plugin_name, kind):
    """视图种类下的可选尺寸（与插件面板同一套口径，见 available_view_sizes）"""
    from modules.register.auto_view_routes import available_view_sizes
    return available_view_sizes(
        plugin_name, os.path.join(PLUGINS_ROOT, plugin_name, 'view'), kind)


def _plugin_params(plugin_name):
    """插件在 plugin_config.py 里声明的 DEFAULT_ARGS **参数名**

    只取名字、不取默认值：默认值是插件自带的、装完就不会变，列出来只会盖过参数名本身。
    """
    from modules.plugins.plugin_loader import get_plugin_default_args
    try:
        defaults = get_plugin_default_args(plugin_name, os.path.join(PLUGINS_ROOT, plugin_name))
    except Exception:
        # 插件配置读不出来不该把整页带崩：访客页少一段参数，好过整个 500
        return []
    return [str(key) for key in sorted(defaults)]


def _available_groups():
    """全部用户组（含内置管理组），读不出来时返回空列表（页面上就不显示这一行）"""
    try:
        from modules.database.groups import get_all_groups
        return get_all_groups() or []
    except Exception:
        return []


def _group_names_for(plugin_name, all_groups):
    """该插件当前对哪些用户组可用；返回 `(names, all_allowed)`

    判定走的是运行时同一套 `check_user_plugin_access`，而不是自己去翻 group_plugins 表：
    内置管理组在权限缓存里被整体跳过（恒为允许），自己查表会漏掉它。
    """
    from modules.database.access import check_user_plugin_access
    names = [g.get('name') or '' for g in all_groups
             if check_user_plugin_access(g.get('id'), plugin_name)]
    return names, bool(all_groups) and len(names) == len(all_groups)


def _esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def _route_html(row, plugin_name, lang):
    from modules.i18n.registry import t
    path = row['path']
    parts = [s for s in path.strip('/').split('/') if s]
    # `/插件/view/<种类>`：可选尺寸挂在 `view/<种类>/` 下，所以取的是第三段而不是第二段
    sizes = []
    if len(parts) >= 3 and parts[0] == plugin_name and parts[1] == 'view':
        sizes = _view_sizes(plugin_name, parts[2])
    method = ' · '.join(row['methods'])
    # 尺寸是「这条路由的可选项」，属于下一层：缩进挂在路由下面，而不是并排挤在同一行
    sub_html = ''
    if sizes:
        sub_html = '<div class="rtsub"><span class="rtsub-k">%s</span>%s</div>' % (
            _esc(t('explore.sizes', lang)),
            ''.join('<span class="rtsub-v">%s</span>' % _esc(s) for s in sizes))
    return ('<div class="rt"><span class="m">%s</span><div class="rtb">'
            '<span class="p">%s</span>%s</div></div>'
            % (_esc(method), _esc(path), sub_html))


def _card_html(card, lang, include_groups=True):
    from modules.i18n.registry import t
    e = _esc
    name = card['name']
    # 作者一行：没有作者也照常渲染空元素（高度由 CSS 定死），否则两张卡片会差出一行
    by = '<span class="xby">%s</span>' % e(card['author'])
    # 可用用户组直接铺标签、不写标签名；全部可用时只留一枚蓝色标签，不逐个铺开
    if card['all_groups'] and card['groups']:
        tags = '<span class="chip chip-all">%s</span>' % e(t('explore.all_users', lang))
    else:
        tags = ''.join('<span class="chip">%s</span>' % e(g) for g in card['groups'])
        if not tags:
            tags = '<span class="xnone">%s</span>' % e(t('explore.no_users', lang))
    # 静态版（Vercel 边缘直出）整行不留：那边的数据源是「这只实例的库」，而静态页是在
    # 构建机上生成的，写死一份用户组名单只会是一份对不上任何人库的快照
    tags_html = ('<div class="xtags">%s</div>' % tags) if include_groups else ''

    route_html = ''.join(_route_html(r, name, lang) for r in card['routes'])
    if not route_html:
        route_html = '<div class="none">%s</div>' % e(t('explore.no_routes', lang))

    # 参数只列名字：默认值不展示（见 _plugin_params）
    param_html = ''.join('<span class="pmk">%s</span>' % e(k) for k in card['params'])
    if not param_html:
        param_html = '<div class="none">%s</div>' % e(t('explore.no_params', lang))

    # 弹窗标题下的一行：版本 / 作者 / 路由数，都是卡片上放不下或不必放的信息
    meta_parts = [p for p in (card['version'],
                              card['author'],
                              t('explore.routes_n', lang, n=len(card['routes']))) if p]

    # 明细内联在卡片里（<template> 不渲染、不占布局），点开时由脚本搬进弹窗：
    # 访客页因此不需要任何前端接口。卡片上只留四段固定行数的身份信息，版本号这类
    # 明细收进弹窗（见 meta_parts）
    return (
        '<article class="xcard" tabindex="0" role="button" data-meta="%s" aria-label="%s">'
        '<span class="xname">%s</span>'
        '%s'
        '<p class="xdesc">%s</p>'
        '%s'
        '<template class="xdetail">'
        '<div class="sec">%s</div>%s'
        '<div class="sec">%s</div><div class="pmrow">%s</div>'
        '</template>'
        '</article>'
    ) % (
        e(' · '.join(meta_parts)), e(name),
        e(name),
        by,
        e(card['description']),
        tags_html,
        e(t('explore.routes', lang)), route_html,
        e(t('explore.plugin_params', lang)), param_html,
    )


def build_explore_html(request, include_groups=True):
    """聚合「插件 → 路由 / 参数 / 可用用户组」并渲染整页 HTML

    `include_groups=False` 供静态生成用（见 `explore_static`）：静态页在构建机上生成、
    部署到没有数据库的环境，用户组名单没有可信来源，索性整行不渲染。
    """
    from modules.i18n.registry import t
    lang = req_lang(request)
    state = request.app.state
    result = getattr(state, 'plugin_result', {}) or {}
    states = getattr(state, 'plugin_states', {}) or {}
    plugin_routes = getattr(state, 'plugin_routes', {}) or {}
    disabled_routes = getattr(state, 'disabled_routes', set()) or set()
    all_groups = _available_groups()

    cards = []
    for plugin in result.get('plugins', []):
        name = plugin.get('name', '')
        # 停用的插件整条不出现：它的路由压根不通，列出来等于给访客一个必错的地址
        if not name or states.get(name) is not True:
            continue
        routes = _route_rows(plugin_routes.get(name, []))
        # 被停用的路由整条不出现：它一定返回错误，列出来等于给访客一个必错的地址
        routes = [r for r in routes if r['path'] not in disabled_routes]
        groups, all_allowed = _group_names_for(name, all_groups)
        cards.append({
            'name': name,
            'description': plugin.get('description') or '',
            'version': plugin.get('version') or '',
            'author': plugin.get('author') or '',
            'routes': routes,
            'params': _plugin_params(name),
            'groups': groups,
            'all_groups': all_allowed,
        })
    cards.sort(key=lambda c: c['name'])

    cards_html = ''.join(_card_html(c, lang, include_groups) for c in cards)
    if not cards_html:
        cards_html = '<p class="empty">%s</p>' % _esc(t('explore.empty', lang))

    out = EXPLORE_HTML
    # 版本号取 app_core 的唯一来源（与 /healthz、app.version 同一份）；函数内局部 import
    # 是为了避开 app_core → 注册链路 → 本模块的循环导入
    from modules.app_core import FRAMEWORK_VERSION
    out = out.replace('{{FRAMEWORK_VERSION}}', _esc(FRAMEWORK_VERSION))
    out = out.replace('{{EXPLORE_CARDS}}', cards_html)
    out = out.replace('{{EXPLORE_COUNT}}', _esc(t('explore.count', lang, n=len(cards))))
    return out


@router.get('/explore', response_class=HTMLResponse)
async def explore_page(request: Request):
    return panel_html(_cached_html(request), req_lang(request))


# 渲染结果缓存：键 =（插件世代号, 语言）。这一页每次请求都要查库算「可用用户组」、逐个视图
# 目录 listdir 取尺寸，而它的输出在两次插件变动之间是完全确定的。
# 用 `plugin_generation()` 而不是自己记「有没有清缓存」：装卸 / 开关 / 路由开关 / 配置改动
# 都会推进世代号（见 plugin_loader），漏掉任何一个入口都会长期显示过期页面。
_page_cache = {}


def _cached_html(request):
    from modules.plugins.plugin_loader import plugin_generation
    key = (plugin_generation(), req_lang(request))
    html = _page_cache.get(key)
    if html is None:
        html = build_explore_html(request)
        # 世代号单调递增，旧世代的键不会再被命中，顺手清掉免得随插件变动次数无限堆积
        for stale in [k for k in _page_cache if k[0] != key[0]]:
            _page_cache.pop(stale, None)
        _page_cache[key] = html
    return html
