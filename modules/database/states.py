from modules.database.core import _exec

# ---- Plugin/Route States (persistent toggle) ----

def get_plugin_states():
    rows = _exec('SELECT * FROM plugin_states', fetch_all=True)
    return {r['plugin_name']: bool(r['enabled']) for r in rows}


def save_plugin_state(plugin_name, enabled):
    _exec(
        'INSERT OR REPLACE INTO plugin_states (plugin_name, enabled) VALUES (?, ?)',
        (plugin_name, int(enabled)), commit=True,
    )


def get_route_states():
    rows = _exec('SELECT * FROM route_states', fetch_all=True)
    return {r['route_path']: bool(r['enabled']) for r in rows}


def save_route_state(route_path, enabled):
    _exec(
        'INSERT OR REPLACE INTO route_states (route_path, enabled) VALUES (?, ?)',
        (route_path, int(enabled)), commit=True,
    )


# ---- Config Overrides ----

def get_config_overrides():
    rows = _exec('SELECT * FROM config_overrides', fetch_all=True)
    return {r['key']: r['value'] for r in rows}


def save_config_override(key, value):
    _exec(
        'INSERT OR REPLACE INTO config_overrides (key, value) VALUES (?, ?)',
        (key, str(value)), commit=True,
    )


def delete_config_override(key):
    _exec('DELETE FROM config_overrides WHERE key = ?', (key,), commit=True)


# ---- Plugin Config Overrides ----

def get_plugin_config_overrides(plugin_name):
    rows = _exec(
        'SELECT key, value FROM plugin_config_overrides WHERE plugin_name = ?',
        (plugin_name,), fetch_all=True,
    )
    return {r['key']: r['value'] for r in rows}


def get_all_plugin_config_overrides():
    """全部插件的配置覆盖（配置导出用）。

    导出必须一次拿全：按插件名逐个查会在导出时刻产生不一致的切片，
    而且插件清单本身也要现取。
    """
    rows = _exec('SELECT plugin_name, key, value FROM plugin_config_overrides', fetch_all=True)
    out = {}
    for r in rows:
        out.setdefault(r['plugin_name'], {})[r['key']] = r['value']
    return out


def save_plugin_config_override(plugin_name, key, value):
    _exec(
        'INSERT OR REPLACE INTO plugin_config_overrides (plugin_name, key, value) VALUES (?, ?, ?)',
        (plugin_name, key, str(value)), commit=True,
    )


def delete_plugin_config_override(plugin_name, key):
    _exec(
        'DELETE FROM plugin_config_overrides WHERE plugin_name = ? AND key = ?',
        (plugin_name, key), commit=True,
    )