from modules.database.core import _exec
from modules.database.access import _set_cached_rule, _drop_cached_rule
# preload_access_cache 会用 global 重新绑定缓存字典，所以这里必须用模块属性在调用时取值，
# 不能 `from ... import _plugin_access_cache`，否则拿到的是重新绑定前的旧字典。
import modules.database.access as _access

# 自助注册的默认落组名（替代旧版本的 'user' 组；组被删除时注册流程会按这个名字重建）
REGISTER_GROUP_NAME = 'Free'

# 内置兜底管理组：建库时固定为 id=1，category='admin' + builtin=1，禁止删除。
# 组名只是显示名，真实类别看 user_groups.category —— 管理员可以把某个组叫 'admin'，
# 也可以把内置管理组改名，判定一律以 category 为准。
ADMIN_GROUP_ID = 1
ADMIN_GROUP_NAME = 'admin'

# 内置兜底用户组（id=2，Free）：删除「默认注册组」且选择连带删除账号时，默认注册组落到这里。
FALLBACK_USER_GROUP_ID = 2

# 管理组可勾选的后台分页（不含恒可用的「我的」）。顺序即面板展示顺序。
ALL_ADMIN_TABS = ('overview', 'plugins', 'users', 'test', 'logs', 'cache',
                  'prerender', 'stats', 'config', 'backup')
# 任何身份都进得去的分页：用户组的唯一分页、管理组的个人信息页
ACCOUNT_TAB = 'account'

CATEGORY_ADMIN = 'admin'
CATEGORY_USER = 'user'


def normalize_category(value):
    """类别收敛到合法取值：只认 admin，其余一律按 user（缺省 = 普通用户组）"""
    return CATEGORY_ADMIN if str(value or '').strip().lower() == CATEGORY_ADMIN else CATEGORY_USER


def normalize_admin_tabs(value):
    """把分页多选收敛成合法 CSV：只保留已知分页、去重、按固定顺序排列。

    传列表或逗号分隔字符串都接受；非法值不会写进库，避免面板漏掉一个 typo
    就让整个管理组进不去后台。
    """
    if isinstance(value, (list, tuple, set)):
        picked = {str(v).strip() for v in value}
    else:
        picked = {s.strip() for s in str(value or '').split(',')}
    return ','.join(t for t in ALL_ADMIN_TABS if t in picked)


def is_admin_category(category):
    return (category or '') == CATEGORY_ADMIN


def is_admin_user(user):
    """账号/用户字典（需含 group_category）是否为管理组身份。

    类别字段缺失时（老测试、临时拼的字典）退回内置管理组 id 判定，不再看组名：
    组名可以随便起，靠名字判断等于把权限交给一个可编辑的显示字段。
    """
    if not isinstance(user, dict):
        return False
    category = user.get('group_category')
    if category is None:
        return user.get('group_id') == ADMIN_GROUP_ID
    return is_admin_category(category)


def group_is_admin_category(group_id):
    """该用户组是否属于管理组类别（组不存在时 False）"""
    row = _exec('SELECT category FROM user_groups WHERE id = ?', (group_id,), fetch_one=True)
    return bool(row) and is_admin_category(row.get('category'))


def builtin_user_group_id():
    """内置兜底用户组的 id。找不到返回 0（此时调用方必须自己兜住，不能写死 id）"""
    row = _exec(
        "SELECT id FROM user_groups WHERE builtin = 1 AND category = 'user' ORDER BY id LIMIT 1",
        fetch_one=True,
    )
    if row:
        return row['id']
    row = _exec('SELECT id FROM user_groups WHERE name = ?', (REGISTER_GROUP_NAME,), fetch_one=True)
    return row['id'] if row else 0


def allowed_admin_tabs(group):
    """该管理组可访问的后台分页集合。

    内置兜底管理组恒为全部：它是整个后台的兜底入口，把它的分页清空等于所有人都进不去，
    连改回来的地方都没有。「我的」任何身份都可用，不在 admin_tabs 里存。
    """
    if not isinstance(group, dict):
        return set(ALL_ADMIN_TABS) | {ACCOUNT_TAB}
    if group.get('builtin') and is_admin_category(group.get('category')):
        return set(ALL_ADMIN_TABS) | {ACCOUNT_TAB}
    stored = {s.strip() for s in str(group.get('admin_tabs') or '').split(',') if s.strip()}
    return (stored & set(ALL_ADMIN_TABS)) | {ACCOUNT_TAB}


def _activation_member_sql(group_expr):
    """「经激活码开通、且会员还没到期」的账号判定（针对 accounts 别名 a）。

    删组守卫与面板的 unexpired_count 必须共用这一段，否则会出现「面板显示可删、点下去被
    后端拒」这种前后不一致。判定分两步：
      1) 会员还没到期（'' = 永久有效也算，激活码 duration_days=0 出的就是这种）；
      2) 该账号**最近一条**会员变动日志是 activate，且落点就是本组。
    用「最近一条」而不是「有没有 activate 记录」：手动改过组/到期日/回落组的账号最近一条
    会变成 set，按更新后的口径就不再受保护；管理员直接建号到本组则压根没有日志，也不计。
    """
    return (
        f' a.group_id = {group_expr}'
        " AND (a.expires_on = '' OR a.expires_on >= ?)"
        ' AND (SELECT l.action FROM account_membership_logs l'
        ' WHERE l.account_id = a.id ORDER BY l.id DESC LIMIT 1) = \'activate\''
        ' AND (SELECT l.new_group_id FROM account_membership_logs l'
        f' WHERE l.account_id = a.id ORDER BY l.id DESC LIMIT 1) = {group_expr}'
    )


def count_unexpired_accounts_in_group(group_id):
    """组内「激活码开通、且会员还没到期」的账号数。

    只有这类账号才拦删组：它们是花激活码换来的限期权限，组一删要么被连带删除、要么被塞进
    别的组，两种情况都等于单方面撕毁已售出的时长。管理员手动提级进来的账号不算——那本就是
    他自己的操作，随时可以再改回去；这类账号在面板上仍然会显示在组里，只是不再阻止删除。
    """
    from modules.database.activations import today_iso
    row = _exec(
        'SELECT COUNT(*) AS cnt FROM accounts a WHERE' + _activation_member_sql('?'),
        (group_id, today_iso(), group_id), fetch_one=True,
    )
    return row['cnt'] if row else 0

# ---- Group CRUD ----

def get_all_groups():
    # account_count：删除用户组前要在面板上告知会连带影响多少个账号
    # unexpired_count：其中「激活码开通且还没到期」的账号数——有这类账号的组禁止删除，
    #   面板据此直接禁用删除按钮；判定与 count_unexpired_accounts_in_group 共用同一段 SQL
    from modules.database.activations import today_iso
    return _exec(
        'SELECT g.*, (SELECT COUNT(*) FROM accounts a WHERE a.group_id = g.id) as account_count, '
        '(SELECT COUNT(*) FROM accounts a WHERE' + _activation_member_sql('g.id') +
        ') as unexpired_count '
        'FROM user_groups g ORDER BY g.id',
        (today_iso(),), fetch_all=True,
    )


def get_group(group_id):
    return _exec('SELECT * FROM user_groups WHERE id = ?', (group_id,), fetch_one=True)


def _register_default_config_id():
    """面板配置的默认注册组 id（config.REGISTER_DEFAULT_GROUP_ID）。0 = 未配置"""
    import config
    try:
        return int(getattr(config, 'REGISTER_DEFAULT_GROUP_ID', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _valid_register_group(group_id):
    """该 id 能否作为自助注册的默认落组。管理组（category='admin'）一律不行。

    默认注册组指向管理组时，任何人在注册页不带激活码注册一次就当场拿到后台权限，
    而这正是激活码那三条路径（生成入口、注册核销、自助激活）都显式堵死的组合。
    第四条路径「默认落组」必须一起堵：这道校验刻意放在数据库层，面板配置入口
    （config_routes）与直接改库都绕不过去。
    """
    try:
        gid = int(group_id or 0)
    except (TypeError, ValueError):
        return False
    return bool(gid) and not group_is_admin_category(gid)


def set_register_default_group(group_id):
    """把默认注册组改写成 group_id（0 = 交回内置 Free 回落逻辑）"""
    from modules import config_store
    from modules.database.states import save_config_override
    value = str(int(group_id or 0))
    save_config_override('REGISTER_DEFAULT_GROUP_ID', value)
    config_store.apply_one('REGISTER_DEFAULT_GROUP_ID', value)


def current_register_group_id():
    """当前默认注册组 id（只读，不建组）。

    面板展示用：配置的组已被删除时返回实际会回落的 Free 组 id，
    两者都不存在则返回 0（此时注册会现场建出 Free）。
    """
    configured = _register_default_config_id()
    if _valid_register_group(configured) and _exec(
            'SELECT id FROM user_groups WHERE id = ?', (configured,), fetch_one=True):
        return configured
    # 回落的锚点是 builtin 标记而不是组名：组名可改，认名字会让改名后的组不再是默认注册组
    return builtin_user_group_id()


def ensure_register_group():
    """返回自助注册的落组 id。

    优先用面板配置的默认注册组，未配置（或该组已被删除）时回落到内置兜底用户组、
    不存在则现场创建。用户组是可删除的，而 accounts.group_id 上有外键约束：
    注册落组必须现取现建，写死组名或 id 都会在该组被删掉后让注册撞 FOREIGN KEY。
    """
    configured = _register_default_config_id()
    if _valid_register_group(configured):
        row = _exec('SELECT id FROM user_groups WHERE id = ?', (configured,), fetch_one=True)
        if row:
            return row['id']
    # 内置兜底用户组优先于按名回落：组名是管理员可改的显示字段，若这里按名找 'Free'，
    # 一旦那个组被改名就会当场另建一个同名组，账号悄悄落进没人配置过的新组。
    builtin_id = builtin_user_group_id()
    if builtin_id:
        return builtin_id
    row = _exec('SELECT id FROM user_groups WHERE name = ?', (REGISTER_GROUP_NAME,), fetch_one=True)
    if row:
        return row['id']
    # INSERT OR IGNORE + 回查：并发注册同时建组时只有一个插入成功，另一个直接复用
    _exec(
        'INSERT OR IGNORE INTO user_groups (name, description, max_evkeys) VALUES (?, ?, ?)',
        (REGISTER_GROUP_NAME, 'Default group for self-registered accounts', 5),
        commit=True,
    )
    row = _exec('SELECT id FROM user_groups WHERE name = ?', (REGISTER_GROUP_NAME,), fetch_one=True)
    return row['id'] if row else None


def create_group(name, description='', max_concurrent_renders=5,
                 rate_limit_per_minute=0, max_evkeys=3, quota_limit=0, quota_period='day',
                 category=CATEGORY_USER, admin_tabs='', show_announcement=1):
    # max_evkeys / quota_* / category / admin_tabs 放在末尾：它们是后加的字段，
    # 插进中间会悄悄改掉既有位置参数的语义
    # max_evkeys：-1 = 不限，0 = 禁止创建，N = N 个
    # show_announcement：管理组是否在概览页看到站内信卡片，1 = 显示
    return _exec(
        'INSERT INTO user_groups (name, description, max_evkeys, max_concurrent_renders,'
        ' rate_limit_per_minute, quota_limit, quota_period, category, admin_tabs,'
        ' show_announcement)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (name, description, max_evkeys, max_concurrent_renders, rate_limit_per_minute,
         quota_limit, quota_period, normalize_category(category),
         normalize_admin_tabs(admin_tabs), 1 if show_announcement else 0),
        commit=True,
    )


def update_group(group_id, **kwargs):
    allowed = {
        'name', 'description', 'max_evkeys', 'max_devices', 'max_concurrent_renders',
        'rate_limit_per_minute', 'quota_limit', 'quota_period',
        'category', 'admin_tabs', 'show_announcement',
    }
    sets = {k: v for k, v in kwargs.items() if k in allowed}
    if not sets:
        return
    # 类别与分页都要收敛到合法取值：面板多选拼出来的 CSV 带个 typo 就会让整个
    # 管理组进不去后台，而库层是最后一道关口
    if 'category' in sets:
        sets['category'] = normalize_category(sets['category'])
    if 'admin_tabs' in sets:
        sets['admin_tabs'] = normalize_admin_tabs(sets['admin_tabs'])
    if 'show_announcement' in sets:
        sets['show_announcement'] = 1 if sets['show_announcement'] else 0
    # 内置组不变量：类别与 builtin 标记不可被改写（改掉内置管理组的类别会让所有人
    # 同时失去后台入口，且没有任何界面能改回来）
    row = _exec('SELECT builtin, category FROM user_groups WHERE id = ?', (group_id,), fetch_one=True)
    if row and row.get('builtin'):
        sets.pop('category', None)
        if is_admin_category(row.get('category')):
            sets.pop('admin_tabs', None)
    # 内置兜底管理组整组不可编辑：它拥有全部权限（access 会跳过它的规则），改坏它等于
    # 把自己锁在后台外面。这道校验放在库层，面板与直接改库都绕不过去。
    if row and row.get('builtin') and is_admin_category(row.get('category')):
        return
    if not sets:
        return
    clauses = ', '.join(f'{k} = ?' for k in sets)
    values = list(sets.values()) + [group_id]
    _exec(f'UPDATE user_groups SET {clauses} WHERE id = ?', values, commit=True)


def delete_group(group_id):
    """删除用户组，并清掉指向它的遗留引用。

    activation_codes.group_id 与 accounts.fallback_group_id 都没有外键约束，
    留着会让注册（激活码指向已删除的组）和到期扫描（回落组已不存在）撞
    FOREIGN KEY constraint failed，所以在这里一并收口。
    """
    _exec('DELETE FROM code_redemptions WHERE code_id IN'
          ' (SELECT id FROM activation_codes WHERE group_id = ?)', (group_id,), commit=True)
    _exec('DELETE FROM activation_codes WHERE group_id = ?', (group_id,), commit=True)
    _exec('UPDATE accounts SET fallback_group_id = 0 WHERE fallback_group_id = ?',
          (group_id,), commit=True)
    _exec('DELETE FROM user_groups WHERE id = ?', (group_id,), commit=True)


def transfer_group_accounts(from_group_id, to_group_id):
    """把某用户组下的账号整体转移到另一个用户组。

    accounts.group_id 是 ON DELETE CASCADE：删组前不先转移会连带删掉账号与 evkey。
    """
    _exec(
        'UPDATE accounts SET group_id = ? WHERE group_id = ?',
        (to_group_id, from_group_id), commit=True,
    )


# ---- Group Permissions ----

def get_group_permissions(group_id):
    plugins = _exec(
        'SELECT plugin_name, enabled FROM group_plugins WHERE group_id = ?',
        (group_id,), fetch_all=True,
    )
    routes = _exec(
        'SELECT route_path, enabled FROM group_routes WHERE group_id = ?',
        (group_id,), fetch_all=True,
    )
    return {
        'plugins': {p['plugin_name']: bool(p['enabled']) for p in plugins},
        'routes': {r['route_path']: bool(r['enabled']) for r in routes},
    }


def set_group_plugin(group_id, plugin_name, enabled):
    _exec(
        'INSERT OR REPLACE INTO group_plugins (group_id, plugin_name, enabled) VALUES (?, ?, ?)',
        (group_id, plugin_name, int(enabled)), commit=True,
    )
    _set_cached_rule(_access._plugin_access_cache, group_id, plugin_name, enabled)


def set_group_route(group_id, route_path, enabled):
    _exec(
        'INSERT OR REPLACE INTO group_routes (group_id, route_path, enabled) VALUES (?, ?, ?)',
        (group_id, route_path, int(enabled)), commit=True,
    )
    _set_cached_rule(_access._route_access_cache, group_id, route_path, enabled)


def delete_group_plugin(group_id, plugin_name):
    _exec('DELETE FROM group_plugins WHERE group_id = ? AND plugin_name = ?', (group_id, plugin_name), commit=True)
    _drop_cached_rule(_access._plugin_access_cache, group_id, plugin_name)


def delete_group_route(group_id, route_path):
    _exec('DELETE FROM group_routes WHERE group_id = ? AND route_path = ?', (group_id, route_path), commit=True)
    _drop_cached_rule(_access._route_access_cache, group_id, route_path)