import importlib
import importlib.util
import os
import sys
from functools import lru_cache
from fastapi import FastAPI
from modules.database.core import is_db_available
from modules.plugins.manifest import (
    DEFAULT_DEPENDENCIES,
    ManifestError,
    load_manifest,
    resolve_load_order,
)
from modules.utils import plog


# plugin_config.py 里只有「配置项」进配置面。元信息（名称、描述…）的唯一来源是
# plugin.json，这几个名字在 plugin_config.py 里只是声明，面板不得把它们列成可编辑项。
# VIEW_ARGS_SCHEMA 同理：它是参数 schema 的**声明**（值本身是个 dict，会被当成合法配置值），
# 走 get_view_args_schema() 单独读取，不进面板的配置项列表、也不允许被覆盖。
CONFIG_RESERVED_KEYS = ('PLUGIN_NAME', 'PLUGIN_DESCRIPTION', 'CONFIG_LABELS', 'VIEW_ARGS_SCHEMA')
# 允许出现在配置里的取值类型，与面板的渲染分支同口径：只有这几种能被编辑
CONFIG_VALUE_TYPES = (bool, int, float, str, dict, list, type(None))


def _config_items(module):
    """挑出 plugin_config.py 里的配置项，丢掉元信息声明、私有名与非值类型（模块/函数/类）"""
    items = {}
    for key in dir(module):
        if key.startswith('_') or key in CONFIG_RESERVED_KEYS:
            continue
        value = getattr(module, key)
        if isinstance(value, CONFIG_VALUE_TYPES):
            items[key] = value
    return items


def _config_labels(module):
    """插件自报的配置项标签 `{键: {label, desc}}`；写法的容错在读取侧收敛，非法一律忽略"""
    raw = getattr(module, 'CONFIG_LABELS', None)
    labels = {}
    if not isinstance(raw, dict):
        return labels
    for key, meta in raw.items():
        if isinstance(meta, dict):
            labels[key] = meta
        elif isinstance(meta, str):
            labels[key] = {'label': meta}
    return labels


@lru_cache(maxsize=64)
def _plugin_config_bundle(plugin_name, plugin_dir):
    """→ `(items, labels)`。**唯一带缓存的入口**：配置项与标签一起读、一起失效，
    面板保存后只清这里一处，就不会出现「值刷新了、标签还是旧的」这种半新半旧状态。"""
    normalized_dir = os.path.realpath(plugin_dir)
    config_path = os.path.join(normalized_dir, 'plugin_config.py')
    if not os.path.isfile(config_path):
        return {}, {}
    spec = importlib.util.spec_from_file_location(f'{plugin_name}_plugin_config', config_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        plog.warn(f'插件 {plugin_name} 的 plugin_config.py 加载失败，改用默认配置: {exc}')
        return {}, {}
    items, labels = _config_items(mod), _config_labels(mod)
    # 标签只对「真的成了配置项」的键有意义：CONFIG_LABELS 里多写的、给私有名写的一律丢掉，
    # 调用方拿到的 labels 与 items 因此天然同键，不必各自再过滤一遍
    labels = {k: v for k, v in labels.items() if k in items}
    if not is_db_available():
        return items, labels
    try:
        from modules.database.states import get_plugin_config_overrides
        from modules.utils.config_value import parse_config_value
        for k, v in get_plugin_config_overrides(plugin_name).items():
            # 覆盖只落在 plugin_config.py 声明过的配置项上：否则历史脏数据（例如曾把元信息
            # 常量存成过覆盖）会凭这张表重新变回可编辑项
            if k in items:
                items[k] = parse_config_value(v)
        return items, labels
    except Exception:
        return items, labels


def load_plugin_config(plugin_name, plugin_dir):
    """插件配置项（已合并面板覆盖），不含任何元信息"""
    return _plugin_config_bundle(plugin_name, plugin_dir)[0]


def get_plugin_config_labels(plugin_name, plugin_dir):
    """配置项的可读标签与说明，来自 plugin_config.py 的 CONFIG_LABELS（未登记的键不在此）"""
    return _plugin_config_bundle(plugin_name, plugin_dir)[1]


@lru_cache(maxsize=64)
def _view_args_schema_bundle(plugin_name, plugin_dir):
    """→ 归一化后的 `VIEW_ARGS_SCHEMA`；插件没声明（或声明非法）返回 `{}`。

    独立于 `_plugin_config_bundle` 单独缓存，而不是塞进那份 `(items, labels)`：
    后者是所有配置读取方的公共入口，改它的返回形状会波及面板、导入导出、预渲染等
    全部调用点。schema 的消费方（请求参数校验、以后的后台表单与设备侧校验）只关心
    这一块，各读各的、各清各的缓存，互不影响。
    """
    normalized_dir = os.path.realpath(plugin_dir)
    config_path = os.path.join(normalized_dir, 'plugin_config.py')
    if not os.path.isfile(config_path):
        return {}
    spec = importlib.util.spec_from_file_location(f'{plugin_name}_plugin_config', config_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        plog.warn(f'插件 {plugin_name} 的 plugin_config.py 加载失败，参数 schema 视为未声明: {exc}')
        return {}
    defaults = getattr(mod, 'DEFAULT_ARGS', None)
    known_keys = set(defaults) if isinstance(defaults, dict) else set()
    from modules.plugins.view_args import normalize_schema
    return normalize_schema(getattr(mod, 'VIEW_ARGS_SCHEMA', None), known_keys)


def get_view_args_schema(plugin_name, plugin_dir):
    """插件对业务参数的声明式描述；未声明插件返回 `{}`（下游据此不改变任何行为）"""
    return _view_args_schema_bundle(plugin_name, plugin_dir)


# 「插件可变状态」的世代号：装卸 / 开关 / 路由开关 / 配置改动都会 +1。
# 对外页面（如访客导航页 /explore）把渲染结果按它做缓存键——这些页面每次请求都要扫目录、
# 查库算可用用户组，代价不低，而它们的输出在两次插件变动之间是完全确定的。
# 用世代号而不是给每个改状态的入口写一句「清缓存」：漏掉一个入口就会长期显示旧页面。
_generation = 0


def bump_generation():
    """插件相关的可变状态变了，让按世代号缓存的结果在下次请求时重算"""
    global _generation
    _generation += 1


def plugin_generation():
    return _generation


def clear_plugin_config_cache():
    """插件配置的失效入口：面板保存、配置导入与热重载都走这里，配置项、标签与参数 schema 一起清"""
    _plugin_config_bundle.cache_clear()
    _view_args_schema_bundle.cache_clear()
    # 配置变了 = DEFAULT_ARGS 可能变了，对外页面展示的参数也随之过期
    bump_generation()


def get_plugin_default_args(plugin_name, plugin_dir):
    """取插件的 DEFAULT_ARGS，非字典一律当空处理，避免下游 dict() 直接炸掉"""
    args = load_plugin_config(plugin_name, plugin_dir).get('DEFAULT_ARGS')
    return args if isinstance(args, dict) else {}


def _collect_manifests(abs_plugins_dir, plugin_names):
    """扫描阶段先把全部 plugin.json 读成索引，再交给 resolve_load_order 排序。

    返回 `(manifests, errors)`：`manifests[name]` 为 None 表示该插件没写清单（照旧加载），
    `errors[name]` 为清单存在但非法的原因（该插件不加载）。
    """
    manifests, errors = {}, {}
    for name in plugin_names:
        try:
            manifests[name] = load_manifest(os.path.join(abs_plugins_dir, name), expected_name=name)
        except ManifestError as exc:
            manifests[name] = None
            errors[name] = f'插件清单不合法: {exc}'
    return manifests, errors


def register_plugins(app: FastAPI, plugins_dir='plugins'):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    abs_plugins_dir = os.path.join(project_root, plugins_dir)
    result = {'total': 0, 'success': 0, 'failed': 0, 'plugins': [], 'failures': [],
              'manifest_missing': 0}
    try:
        entries = os.listdir(abs_plugins_dir)
    except FileNotFoundError:
        plog.warn(f'插件目录不存在: {abs_plugins_dir}')
        return result
    plugin_names = [
        name for name in entries
        if os.path.isdir(os.path.join(abs_plugins_dir, name))
        and os.path.exists(os.path.join(abs_plugins_dir, name, 'routes.py'))
    ]
    result['total'] = len(plugin_names)
    if not hasattr(app.state, 'plugin_states'):
        app.state.plugin_states = {}
    if not hasattr(app.state, 'disabled_routes'):
        app.state.disabled_routes = set()
    if not hasattr(app.state, 'request_counts'):
        app.state.request_counts = {}
    if not hasattr(app.state, 'plugin_routes'):
        app.state.plugin_routes = {}
    if not plugin_names:
        return result

    # 清单先建索引再排序：被依赖的插件必须先加载，否则后者的 routes.py 在 import 期
    # 拿不到前者的代码。框架版本与 /healthz 同源（FastAPI app.version）。
    manifests, manifest_errors = _collect_manifests(abs_plugins_dir, plugin_names)
    order, skipped = resolve_load_order(plugin_names, manifests, getattr(app, 'version', '') or '')
    result['manifest_missing'] = sum(1 for name in plugin_names if manifests.get(name) is None)
    for name, reason in list(manifest_errors.items()) + list(skipped.items()):
        result['failed'] += 1
        result['failures'].append({'name': name, 'error': reason})

    for plugin_name in order:
        routes_module_path = f'{plugins_dir}.{plugin_name}.routes'
        manifest = manifests.get(plugin_name)
        try:
            # include_router 会把每个 APIRoute 新建对象后 append 进 app.router.routes，
            # 这里用「前后快照按对象身份做差集」精确记下本插件新增的路由对象。
            # 不能用路径前缀猜：插件自定义的路由不保证挂在 /插件名/ 前缀下。
            # 记录下来的对象供 reload_plugins 按身份摘除。
            before_ids = {id(r) for r in app.router.routes}
            module = importlib.import_module(routes_module_path)
            if hasattr(module, 'router'):
                app.include_router(module.router)
            app.state.plugin_routes[plugin_name] = [
                r for r in app.router.routes if id(r) not in before_ids
            ]
            app.state.plugin_states[plugin_name] = True
            # 清单是元信息的唯一来源，描述以清单为准；只有没写清单（或清单没写描述）的
            # 插件才回落到代码常量，否则第三方插件在面板上会连一句话都看不到
            description = (manifest or {}).get('description', '') \
                or getattr(module, 'PLUGIN_DESCRIPTION', '') or '无描述'
            result['plugins'].append({
                'name': plugin_name,
                'description': description,
                'version': (manifest or {}).get('version', ''),
                'author': (manifest or {}).get('author', ''),
                'min_framework_version': (manifest or {}).get('min_framework_version', ''),
                'dependencies': (manifest or {}).get('dependencies', dict(DEFAULT_DEPENDENCIES)),
                'manifest_missing': manifest is None,
            })
            result['success'] += 1
        except Exception as e:
            plog.exception(f'插件 {plugin_name} 加载失败')
            result['failed'] += 1
            # 失败原因带回给管理面板，否则面板只能看到一个"少了的插件"
            result['failures'].append({'name': plugin_name, 'error': str(e)})
            continue
    return result


def _purge_plugin_modules(plugins_dir):
    """清掉插件自身的模块缓存。

    视图 / JSON 端点是在**请求时**才 importlib.import_module('plugins.名.view.种类.尺寸')，
    所以清掉后下一次请求就会重新执行磁盘上的新代码；routes.py 靠 reload_plugins 重建路由生效。
    """
    prefix = f'{plugins_dir}.'
    for name in list(sys.modules):
        if name.startswith(prefix):
            sys.modules.pop(name, None)


def reload_plugins(app: FastAPI, plugins_dir='plugins'):
    """热重载全部插件：摘旧路由 → 清模块缓存 → 重新扫描注册。

    - 新增的插件目录会被发现（与启动期同一套扫描逻辑）
    - 目录已被删除的插件，路由与开关状态一并移除，不留幽灵条目
    - 已注册插件的开关状态保留，不会冲掉面板里设过的禁用
    - 导入失败的插件保持未注册，失败原因随返回值交给调用方
    """
    old_routes = getattr(app.state, 'plugin_routes', {}) or {}
    stale = {id(r) for routes in old_routes.values() for r in routes}
    if stale:
        app.router.routes = [r for r in app.router.routes if id(r) not in stale]
    app.state.plugin_routes = {}

    _purge_plugin_modules(plugins_dir)
    clear_plugin_config_cache()

    # 先清空开关状态：register_plugins 只给「当前目录里成功加载的插件」写回，
    # 被删掉的插件因此不会留下残留条目；已禁用状态在注册完成后按名字恢复。
    prev_states = dict(getattr(app.state, 'plugin_states', {}) or {})
    app.state.plugin_states = {}

    result = register_plugins(app, plugins_dir=plugins_dir)
    for name, enabled in prev_states.items():
        if name in app.state.plugin_states:
            app.state.plugin_states[name] = enabled

    # 路由表变了，必须清 OpenAPI 缓存，否则 /docs 与 /openapi.json 还是旧的
    app.openapi_schema = None
    return result