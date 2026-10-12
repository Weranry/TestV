"""「请求参数 → 最终渲染参数」的解析规则，集中一处。

视图路由与预渲染任务创建共用这一份：两处各写一份的话，缓存键与运行时参数很容易
对不上，表现为「建了任务、请求也发了，却永远不命中」，且不报任何错。
"""
import config
from modules.errors.errors import ParamError

# 这些参数不是透传给 generate_image 的业务参数，而是由路由层单独解析
_RESERVED = ('size', 'rotate', 'invert', 'cmode', 'format')

# rotate / invert 的 URL 取值表。/random/views 也走这里的 parse_* 解析，
# 两处各写一份的话，同一个错参数在一个端点上报 400、在另一个端点上静默忽略
ROTATE_MAP = {'c': 270, 'cc': 90, 'h': 180}
INVERT_MAP = {'t': True, 'f': False}


def explicit_value(query_params, key):
    """取「请求里确实写了的」参数值：没写与写空串都算没写。

    只校验显式传的值是刻意的——插件的 DEFAULT_ROTATE / DEFAULT_CMODE 属配置错误，
    该在配置层发现，不该在每次请求上让设备收到 400。
    """
    value = query_params.get(key)
    return value or None


def parse_rotate_arg(value):
    """URL 的 rotate 取值 → 角度；未传返回 None，非法值抛 400。

    原先用 `{'c':270,'cc':90,'h':180}.get(v, 0)`，`rotate=90` 和 `rotate=xyz` 都会被
    当成「不旋转」照常出图：设备固件把参数拼错时拿到的是一张正常的图，只能靠比对
    画面才发现，比直接报错难排查得多。
    """
    if value is None:
        return None
    rotate = ROTATE_MAP.get(value)
    if rotate is None:
        raise ParamError('rotate 参数必须为 c / cc / h')
    return rotate


def parse_invert_arg(value):
    """URL 的 invert 取值 → 布尔；未传返回 None，非法值抛 400"""
    if value is None:
        return None
    invert = INVERT_MAP.get(value)
    if invert is None:
        raise ParamError('invert 参数必须为 t 或 f')
    return invert


def parse_cmode_arg(value):
    """URL 的 cmode 取值 → 字符串；未传返回 None，非法值抛 400"""
    if value is None:
        return None
    from modules.generate_views.palette_mapper import CMODE_ARG_VALUES
    if value not in CMODE_ARG_VALUES:
        raise ParamError('cmode 参数必须为 ' + ' / '.join(CMODE_ARG_VALUES))
    return value


def resolve_view_params(plugin_name, plugin_dir, size, query_params):
    """解析 /{plugin}/view/{kind} 的最终参数（含 size/rotate/invert/cmode/fmt）

    返回的字典既是要传给 generate_image 的业务参数（除上述保留项外），
    也是预渲染缓存键的输入，因此必须在 merge 之后取。
    """
    if not size:
        raise ParamError('缺少 size 参数')
    # size 会当成模块名拼成 plugins.<plugin>.view.<kind>.<size>：形状不对时先给一句
    # 明确的 400，而不是让 importlib 抛 ModuleNotFoundError 再被包成一句含堆栈的报错
    if not size.isidentifier() or size.startswith('_'):
        raise ParamError('size 参数不合法')
    from modules.plugins.plugin_loader import load_plugin_config, get_plugin_default_args
    # 插件配置每次请求现取（load_plugin_config 自带缓存，面板保存时会清缓存）
    plugin_config = load_plugin_config(plugin_name, plugin_dir)
    merged = dict(get_plugin_default_args(plugin_name, plugin_dir))
    merged.update({k: v for k, v in query_params.items() if k not in _RESERVED})

    # 插件声明的参数 schema（VIEW_ARGS_SCHEMA）在这里生效：URL 传进来的都是字符串，
    # 按声明强转成 int/float/bool 并做范围与枚举校验，非法直接 400。插件没声明时
    # validate_view_args 返回空字典，merge 等于什么都没做——老插件行为零变化。
    # 校验与 merge 放在同一处，是为了不留"参数在路由层是一套口径、在渲染层又是另一套"的缝。
    from modules.plugins.plugin_loader import get_view_args_schema
    from modules.plugins.view_args import validate_view_args
    merged.update(validate_view_args(get_view_args_schema(plugin_name, plugin_dir),
                                     query_params, _RESERVED))

    # 与 rotate/invert 同一优先级链，也与 /random/views 一致：
    # URL 显式 > 插件 DEFAULT_ARGS 的 cmode > 全局 config.DEFAULT_CMODE。
    # cmode 是保留项（不进缓存键），此处只影响调色板映射，不改变键。
    cmode = parse_cmode_arg(explicit_value(query_params, 'cmode'))
    if cmode is None:
        cmode = merged.get('cmode')
        if cmode is None:
            cmode = getattr(config, 'DEFAULT_CMODE', None)

    rotate = parse_rotate_arg(explicit_value(query_params, 'rotate'))
    if rotate is None:
        default_rotate = plugin_config.get('DEFAULT_ROTATE', None)
        rotate = default_rotate if default_rotate is not None else config.DEFAULT_ROTATE

    invert = parse_invert_arg(explicit_value(query_params, 'invert'))
    if invert is None:
        default_invert = plugin_config.get('DEFAULT_INVERT', None)
        invert = default_invert if default_invert is not None else config.DEFAULT_INVERT

    merged.update({
        'size': size,
        'rotate': rotate,
        'invert': invert,
        'cmode': cmode,
        'fmt': (query_params.get('format') or config.DEFAULT_IMAGE_FORMAT).lower(),
    })
    return merged


def resolve_json_params(plugin_name, plugin_dir, query_params):
    """解析 /{plugin}/json/{name} 的最终参数。

    JSON 路由把全部查询参数原样透传给 to_json（与改造前一致），不做保留项过滤，
    避免改变既有插件的行为；它和视图路由靠 route_path 区分，不需要额外的类型标记。
    """
    from modules.plugins.plugin_loader import get_plugin_default_args
    merged = dict(get_plugin_default_args(plugin_name, plugin_dir))
    merged.update({k: v for k, v in query_params.items()})
    return merged