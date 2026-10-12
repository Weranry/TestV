from modules.database.core import _exec

# ---- Access Control Helpers ---- Check access ----

_plugin_access_cache = {}
_route_access_cache = {}
_params_cache = {}
_access_cache_loaded = False


def _notify_changed():
    """多实例：本进程重算了权限缓存，别的实例也得重算一次"""
    from modules.shared import events
    events.notify(events.ACCESS)


def _set_cached_rule(cache, group_id, key, enabled):
    """权限变更后同步内存缓存，避免必须重启才生效"""
    cache.setdefault(group_id, {})[key] = bool(enabled)
    _notify_changed()


def _drop_cached_rule(cache, group_id, key):
    rules = cache.get(group_id)
    if rules is not None:
        rules.pop(key, None)
    _notify_changed()


def _builtin_admin_group_ids():
    """内置兜底管理组的 id 集合（正常只有一个 id=1）。

    它恒为「无条件最高权限」：库里即使留着它的规则也不参与判定，否则管理员给自己
    配一条禁用规则就能把整个后台锁死，而且没有任何界面还能改回来。
    """
    return {r['id'] for r in _exec(
        "SELECT id FROM user_groups WHERE builtin = 1 AND category = 'admin'", fetch_all=True)}


def _build_group_cache(rows, key_field, skip_group_ids=()):
    result = {}
    for r in rows:
        if r['group_id'] in skip_group_ids:
            continue
        result.setdefault(r['group_id'], {})[r[key_field]] = bool(r['enabled'])
    return result


def preload_access_cache():
    global _plugin_access_cache, _route_access_cache, _params_cache, _access_cache_loaded
    skip = _builtin_admin_group_ids()
    _plugin_access_cache = _build_group_cache(
        _exec('SELECT group_id, plugin_name, enabled FROM group_plugins', fetch_all=True),
        'plugin_name', skip)
    _route_access_cache = _build_group_cache(
        _exec('SELECT group_id, route_path, enabled FROM group_routes', fetch_all=True),
        'route_path', skip)
    _params_cache = _build_group_cache(
        _exec('SELECT group_id, param_key, enabled FROM group_params', fetch_all=True),
        'param_key', skip)
    _access_cache_loaded = True
    _notify_changed()


def invalidate_access_cache():
    """清空权限规则内存缓存（强制下次从库里重读）。

    仅供测试重置权限缓存使用，生产路径不要调用：生产改权限一律走 set_group_* /
    delete_group_*，它们内部会同步刷新缓存，直接清空反而会让所有组短暂回到「默认允许」。
    """
    global _plugin_access_cache, _route_access_cache, _params_cache, _access_cache_loaded
    _plugin_access_cache = {}
    _route_access_cache = {}
    _params_cache = {}
    _access_cache_loaded = False


def check_user_plugin_access(group_id, plugin_name):
    group_rules = _plugin_access_cache.get(group_id)
    if group_rules is None:
        return True
    enabled = group_rules.get(plugin_name)
    return True if enabled is None else enabled


def check_user_route_access(group_id, route_path):
    group_rules = _route_access_cache.get(group_id)
    if group_rules is None:
        return True
    enabled = group_rules.get(route_path)
    if enabled is not None:
        return enabled
    for stored_path, stored_enabled in group_rules.items():
        base = stored_path.split('{', 1)[0]
        if base and route_path.startswith(base):
            return stored_enabled
    return True


def get_group_params(group_id):
    if _access_cache_loaded:
        return _params_cache.get(group_id, {})
    rows = _exec(
        'SELECT param_key, enabled FROM group_params WHERE group_id = ?',
        (group_id,), fetch_all=True,
    )
    return {r['param_key']: bool(r['enabled']) for r in rows}


def set_group_param(group_id, param_key, enabled):
    _exec(
        'INSERT OR REPLACE INTO group_params (group_id, param_key, enabled) VALUES (?, ?, ?)',
        (group_id, param_key, int(enabled)), commit=True,
    )
    _set_cached_rule(_params_cache, group_id, param_key, enabled)


def delete_group_param(group_id, param_key):
    _exec(
        'DELETE FROM group_params WHERE group_id = ? AND param_key = ?',
        (group_id, param_key), commit=True,
    )
    _drop_cached_rule(_params_cache, group_id, param_key)


def check_group_param_access(group_id, param_key):
    """参数访问校验。preload_access_cache 之后走内存缓存，请求热路径不再查库"""
    if _access_cache_loaded:
        rules = _params_cache.get(group_id)
        if rules is None:
            return True
        enabled = rules.get(param_key)
        return True if enabled is None else enabled
    row = _exec(
        'SELECT enabled FROM group_params WHERE group_id = ? AND param_key = ?',
        (group_id, param_key), fetch_one=True,
    )
    if row is None:
        return True
    return bool(row['enabled'])