"""插件业务参数的**声明式**描述（`VIEW_ARGS_SCHEMA`）与校验。

插件在 `plugin_config.py` 里写一份 `VIEW_ARGS_SCHEMA`，就能把「某个业务参数是什么类型、
取值范围、有哪些可选值」讲清楚。框架据此在**请求入口**把 URL 传进来的字符串强转并校验，
而不是拖到 `generate_image` 内部才因为类型不对炸掉（那种 500 排查起来要翻插件代码）。

两个刻意的约定：

- **没声明就完全不过问**：插件没写 `VIEW_ARGS_SCHEMA` 时 `normalize_schema` 返回 `{}`，
  下游 `validate_view_args` 直接返回空字典。既有插件的行为与引入本模块之前完全一致。
- **只校验 URL 显式传了的键**：补默认值是 `DEFAULT_ARGS` 那条链路的事，这里不掺和，
  避免「最终值由谁决定」出现两处口径。
"""
from modules.errors.errors import ParamError

# 支持的类型。`enum` 是「取值必须落在 options 里」的特例，其余按 Python 内建类型强转。
_TYPES = ('bool', 'int', 'float', 'str', 'enum')
_NUMERIC_TYPES = ('int', 'float')
_BOOL_TRUE = ('t', 'true', '1', 'yes', 'on')
_BOOL_FALSE = ('f', 'false', '0', 'no', 'off')


def _is_number(value):
    # bool 是 int 的子类，必须排掉，否则 `min=True` 会被当成 1 收下
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_options(raw):
    """`[值]` / `[{"value","label"}]` 两种写法统一成 `[{"value","label"}]`"""
    if not isinstance(raw, (list, tuple)):
        return []
    options = []
    for opt in raw:
        if isinstance(opt, dict):
            if 'value' not in opt:
                continue
            label = opt.get('label')
            options.append({
                'value': opt['value'],
                'label': label if isinstance(label, str) and label else str(opt['value']),
            })
        elif isinstance(opt, (str, int, float, bool)):
            options.append({'value': opt, 'label': str(opt)})
    return options


def normalize_schema(raw, known_keys):
    """把插件自报的 `VIEW_ARGS_SCHEMA` 收敛成框架认得的形状。

    容错口径与 `CONFIG_LABELS` 一致：**非法项静默丢弃**，不抛异常——插件把 schema
    写错，不该让它的路由整体不可用。`known_keys` 是可声明的键名集合（即 `DEFAULT_ARGS`
    的键）：声明里多写的、写错名字的一律丢掉，规范化结果因此天然与 `DEFAULT_ARGS` 同域。
    """
    if not isinstance(raw, dict) or not known_keys:
        return {}
    known = set(known_keys)
    schema = {}
    for key, spec in raw.items():
        if not isinstance(key, str) or key not in known or not isinstance(spec, dict):
            continue
        value_type = spec.get('type')
        if value_type not in _TYPES:
            continue
        item = {'type': value_type, 'label': key}
        label = spec.get('label')
        if isinstance(label, str) and label:
            item['label'] = label
        if 'default' in spec:
            item['default'] = spec['default']
        if value_type in _NUMERIC_TYPES:
            for bound in ('min', 'max'):
                if _is_number(spec.get(bound)):
                    item[bound] = spec[bound]
            if 'min' in item and 'max' in item and item['min'] > item['max']:
                # 声明自相矛盾，留着会让这个参数的任何取值都被判非法，按坏声明丢掉
                continue
            step = spec.get('step')
            if _is_number(step) and step > 0:
                item['step'] = step
        if value_type == 'enum':
            options = _normalize_options(spec.get('options'))
            if not options:
                # enum 没有可选项等于没有约束，留着只会让参数「永远不合法」
                continue
            item['options'] = options
        description = spec.get('description')
        if isinstance(description, str) and description:
            item['description'] = description
        if spec.get('required') is True:
            item['required'] = True
        schema[key] = item
    return schema


def validate_view_args(schema, query_params, reserved):
    """校验并强转 URL 里**显式传了**的业务参数，返回 `{键: 强转后的值}`。

    - `schema` 为空（插件没声明）→ 返回 `{}`，调用方 merge 进去等于什么都没做；
    - `reserved` 里的键（size/rotate/invert/cmode/format）由路由层单独解析，此处跳过；
    - 没传的键不在这里补默认值，默认值合并只由 `DEFAULT_ARGS` 负责；
    - `required` 不在这里拦，它连同 `label` / `description` / `step` 一起供以后后台
      自动生成参数表单用——真在请求上强制，会打挂所有依赖 `DEFAULT_ARGS` 兜底的 URL。

    非法取值抛 `ParamError`（→ 400），不静默吞掉：设备固件把参数拼错时，一个明确的
    400 比一张「看起来正常」的图好排查得多。
    """
    if not schema:
        return {}
    skip = set(reserved or ())
    coerced = {}
    for key, spec in schema.items():
        if key in skip:
            continue
        raw = query_params.get(key)
        if raw is None or raw == '':
            continue
        coerced[key] = _coerce(key, spec, raw)
    return coerced


def _coerce(key, spec, raw):
    value_type = spec['type']
    text = _as_text(raw)
    if value_type == 'bool':
        value = _parse_bool(key, text)
    elif value_type == 'int':
        value = _parse_number(key, text, int, '整数')
    elif value_type == 'float':
        value = _parse_number(key, text, float, '数字')
    elif value_type == 'str':
        value = text
    else:
        value = _parse_enum(key, spec, text)
    if value_type in _NUMERIC_TYPES:
        if 'min' in spec and value < spec['min']:
            raise ParamError(f'参数 {key} 不能小于 {spec["min"]}')
        if 'max' in spec and value > spec['max']:
            raise ParamError(f'参数 {key} 不能大于 {spec["max"]}')
    return value


def _as_text(raw):
    """多值参数取最后一个，与 Starlette `QueryParams.get` 的口径保持一致"""
    if isinstance(raw, (list, tuple)):
        raw = raw[-1] if raw else ''
    return raw if isinstance(raw, str) else str(raw)


def _parse_bool(key, text):
    lowered = text.strip().lower()
    if lowered in _BOOL_TRUE:
        return True
    if lowered in _BOOL_FALSE:
        return False
    raise ParamError(f'参数 {key} 必须为 t / f 或 true / false')


def _parse_number(key, text, caster, name):
    try:
        return caster(text.strip())
    except (TypeError, ValueError):
        raise ParamError(f'参数 {key} 必须为{name}')


def _parse_enum(key, spec, text):
    for option in spec['options']:
        if text == str(option['value']):
            return option['value']
    choices = ' / '.join(str(option['value']) for option in spec['options'])
    raise ParamError(f'参数 {key} 必须为 {choices}')
