import secrets

from modules.database.core import _exec, _hash_password, _verify_password

# ---- Account CRUD ----

_ACCOUNT_FIELDS = (
    'a.id, a.uid, a.name, a.group_id, a.description, a.enabled, a.created_at, '
    'a.must_change_password, a.expires_on, a.fallback_group_id, a.email, '
    'g.name as group_name, g.max_evkeys, g.category as group_category, '
    'g.builtin as group_builtin'
)
_ACCOUNT_FROM = 'FROM accounts a JOIN user_groups g ON a.group_id = g.id'

# 分配 uid 的唯一实现：单条语句内取「现有最大 uid + 1」，起点 10000。
# 放在 INSERT 里而不是先 SELECT 再写，是为了让并发建号也只可能撞到 idx_accounts_uid 唯一索引，
# 不会出现两个账号拿到同一个号。
_NEXT_UID_SQL = '(SELECT COALESCE(MAX(uid), 9999) + 1 FROM accounts)'


def is_numeric_identifier(value):
    """纯数字串（仅 ASCII 数字）= 保留给 uid 登录。

    账号名不允许是纯数字，否则「10000」既可能是名字也可能是编号，登录入口无法消歧。
    校验入口：注册、管理员建号、改名。
    """
    return bool(value) and value.isascii() and value.isdigit()


def _select_account(where, params):
    return _exec(f'SELECT {_ACCOUNT_FIELDS} {_ACCOUNT_FROM} WHERE {where}', params, fetch_one=True)


def get_account_by_id(account_id):
    return _select_account('a.id = ? AND a.enabled = 1', (account_id,))


def get_account_row(account_id):
    """含禁用账号的行 + 所属组的配额设定与类别（额度调整 / 会员调整等管理操作要用）。

    get_account_by_id 会过滤 enabled=1，被禁用的账号改额度时会查不到；
    这里一并带出 quota_limit / quota_period，省掉再一次查组。
    """
    return _exec(
        'SELECT a.id, a.name, a.group_id, a.enabled, a.expires_on, a.fallback_group_id, '
        'g.name AS group_name, g.quota_limit, g.quota_period, g.category AS group_category, '
        'g.builtin AS group_builtin FROM accounts a '
        'JOIN user_groups g ON a.group_id = g.id WHERE a.id = ?',
        (account_id,), fetch_one=True,
    )


def get_account_by_name(name):
    """按账号名查（不区分大小写）。`Admin` 与 `admin` 视为同一个名字。

    库里另有 lower(name) 的唯一索引兜底，这里的 NOCASE 是为了让查重与登录
    在应用层就走同一条口径（唯一索引只防新增，查不到时仍要能按任意大小写命中）。
    """
    return _select_account('a.name = ? COLLATE NOCASE AND a.enabled = 1', ((name or '').strip(),))


def get_account_for_reset(name, email):
    """「忘记密码」用的匹配：账号名与注册邮箱都对上才返回该行（两者都不区分大小写）。

    邮箱是唯一凭据，因此必须与账号名一起校验；只比邮箱会让任意人用一个邮箱
    把别人账号的密码改掉（邮箱在多账号间并不保证唯一）。
    """
    return _select_account(
        'a.name = ? COLLATE NOCASE AND a.email <> \'\' AND a.email = ? COLLATE NOCASE '
        'AND a.enabled = 1',
        ((name or '').strip(), (email or '').strip()),
    )


def get_all_accounts():
    return _exec(
        f'SELECT {_ACCOUNT_FIELDS}, '
        '(SELECT COUNT(*) FROM evkeys e WHERE e.account_id = a.id) as evkey_count '
        f'{_ACCOUNT_FROM} ORDER BY a.id',
        fetch_all=True,
    )


def create_account(name, password, group_id=1, description='', expires_on='',
                   fallback_group_id=0, email=''):
    """建账号。expires_on / fallback_group_id 只有激活码开通用得上（'' / 0 = 永久、不回落）。

    email 是「忘记密码」的唯一凭据（注册时必填，校验在路由层）。
    uid 由库自己按注册顺序发放（见 _NEXT_UID_SQL），调用方不传也不用管。
    """
    pw_hash = _hash_password(password) if password else ''
    return _exec(
        'INSERT INTO accounts (name, password, email, group_id, description, expires_on,'
        f' fallback_group_id, uid) VALUES (?, ?, ?, ?, ?, ?, ?, {_NEXT_UID_SQL})',
        (name, pw_hash, (email or '').strip(), group_id, description,
         expires_on or '', int(fallback_group_id or 0)),
        commit=True,
    )


def update_account(account_id, **kwargs):
    # expires_on / fallback_group_id 也在白名单里：面板的「权限记录」弹窗
    # 就是通过这个接口改组、改到期日、改回落组的（校验与记录在路由层）
    allowed = {'name', 'group_id', 'description', 'enabled',
               'expires_on', 'fallback_group_id', 'email'}
    sets = {k: v for k, v in kwargs.items() if k in allowed}
    if not sets:
        return
    clauses = ', '.join(f'{k} = ?' for k in sets)
    values = list(sets.values()) + [account_id]
    _exec(f'UPDATE accounts SET {clauses} WHERE id = ?', values, commit=True)


def set_account_membership(account_id, group_id, expires_on='', fallback_group_id=0):
    """改账号的会员属性：落组 + 到期日 + 到期回落组（注册后自助激活用）。

    expires_on = '' 表示永久有效，fallback_group_id = 0 表示到期不转移。
    """
    _exec(
        'UPDATE accounts SET group_id = ?, expires_on = ?, fallback_group_id = ? WHERE id = ?',
        (int(group_id), expires_on or '', int(fallback_group_id or 0), account_id),
        commit=True,
    )


def set_account_password(account_id, password):
    pw_hash = _hash_password(password)
    _exec('UPDATE accounts SET password = ?, must_change_password = 0 WHERE id = ?', (pw_hash, account_id), commit=True)


def verify_account_login(identifier, password):
    """identifier 可以是账号名或 uid。

    纯数字一律按 uid 解释（账号名已禁止纯数字，见 is_numeric_identifier），
    所以这里不需要「先查名字再查编号」的回落——那种回落会让一个数字账号名把对应 uid 的登录抢走。
    """
    ident = (identifier or '').strip()
    if is_numeric_identifier(ident):
        where, params = 'a.uid = ? AND a.enabled = 1', (int(ident),)
    else:
        # 账号名不区分大小写：登录入口与 get_account_by_name 走同一口径
        where, params = 'a.name = ? COLLATE NOCASE AND a.enabled = 1', (ident,)
    acct = _exec(
        f'SELECT {_ACCOUNT_FIELDS}, a.password {_ACCOUNT_FROM} WHERE {where}',
        params, fetch_one=True,
    )
    if not acct or not _verify_password(password, acct['password']):
        return None
    del acct['password']
    return acct


def delete_account(account_id):
    _exec('DELETE FROM accounts WHERE id = ?', (account_id,), commit=True)


def default_admin_account_id():
    """建库时自动生成的那个管理账号（内置管理组里最早创建的一个）。

    账号名可以随便改，所以不能按名字认；id 自增不复用，取内置管理组的最小 id
    就是它。删掉它等于把后台的兜底入口一并删掉，删除接口据此拦截。
    """
    row = _exec(
        'SELECT MIN(a.id) AS id FROM accounts a JOIN user_groups g ON a.group_id = g.id '
        "WHERE g.builtin = 1 AND g.category = 'admin'",
        fetch_one=True,
    )
    return row['id'] if row and row['id'] is not None else None


def default_admin_needs_password_change():
    """内置管理账号是否还在用建库时的初始口令（must_change_password=1）。

    只给启动摘要用：这条口令是公开写在代码里的，机器部署完一直没人登录面板改，它就一直有效。
    账号名可改，所以仍按 id 认（见 default_admin_account_id）；查不到账号返回 False。
    """
    account_id = default_admin_account_id()
    if account_id is None:
        return False
    row = _exec('SELECT must_change_password FROM accounts WHERE id = ?',
                (account_id,), fetch_one=True)
    return bool(row and row['must_change_password'])


def is_setup_required():
    """系统是否尚未完成初始化 = 内置管理账号还在用建库时的公开初始口令。

    只有本地模式（dev/prod）用得上：Vercel 侧数据库被停用，这里直接返回 False，
    不与 app.py 的精简链路发生关系。库还没建好/被占用时按「已初始化」放行——
    门禁是为了提示，不该因为一次读库异常把整个站挡在门外。
    """
    from modules.database.core import is_db_available
    if not is_db_available():
        return False
    try:
        return default_admin_needs_password_change()
    except Exception:
        return False


def get_account_count():
    row = _exec('SELECT COUNT(*) as cnt FROM accounts WHERE enabled = 1', fetch_one=True)
    return row['cnt'] if row else 0


def count_accounts_in_group(group_id):
    row = _exec('SELECT COUNT(*) as cnt FROM accounts WHERE group_id = ?', (group_id,), fetch_one=True)
    return row['cnt'] if row else 0


def get_evkey_count():
    row = _exec('SELECT COUNT(*) as cnt FROM evkeys', fetch_one=True)
    return row['cnt'] if row else 0


# ---- 批量操作（面板多选后一次提交，避免逐条发请求） ----

def _id_placeholders(ids):
    return ','.join('?' for _ in ids)


def update_accounts_group(account_ids, group_id):
    if not account_ids:
        return
    _exec(
        f'UPDATE accounts SET group_id = ? WHERE id IN ({_id_placeholders(account_ids)})',
        [group_id] + list(account_ids), commit=True,
    )


def set_accounts_enabled(account_ids, enabled):
    if not account_ids:
        return
    _exec(
        f'UPDATE accounts SET enabled = ? WHERE id IN ({_id_placeholders(account_ids)})',
        [int(bool(enabled))] + list(account_ids), commit=True,
    )


def delete_accounts(account_ids):
    if not account_ids:
        return
    _exec(
        f'DELETE FROM accounts WHERE id IN ({_id_placeholders(account_ids)})',
        list(account_ids), commit=True,
    )


def has_accounts():
    row = _exec('SELECT COUNT(*) as cnt FROM accounts', fetch_one=True)
    return (row['cnt'] if row else 0) > 0


# ---- Evkey CRUD ----

def get_account_by_evkey(evkey):
    return _exec(
        "SELECT a.id, a.name, a.group_id, a.description, a.enabled, a.created_at, "
        "g.name as group_name, g.max_evkeys, g.category as group_category, "
        "g.builtin as group_builtin, e.id as evkey_id "
        "FROM evkeys e JOIN accounts a ON e.account_id = a.id "
        "JOIN user_groups g ON a.group_id = g.id "
        "WHERE e.evkey = ? AND a.enabled = 1 AND e.enabled = 1",
        (evkey,), fetch_one=True,
    )


def get_evkeys_for_account(account_id):
    return _exec(
        'SELECT * FROM evkeys WHERE account_id = ? ORDER BY id',
        (account_id,), fetch_all=True,
    )


def count_evkeys_for_account(account_id):
    """账号已持有的 evkey 数（含被禁用的）。

    持有上限看的是"占用名额"，禁用只是停用、名额仍占着——否则禁用一下就能
    再申请一个，上限形同虚设。只有删除才释放名额。
    """
    row = _exec('SELECT COUNT(*) as cnt FROM evkeys WHERE account_id = ?', (account_id,), fetch_one=True)
    return row['cnt'] if row else 0


def new_evkey():
    """生成一个 evkey（32 位十六进制），全局唯一生成方式集中在这里"""
    return secrets.token_hex(16)


def create_evkey(account_id, evkey, description=''):
    return _exec(
        'INSERT INTO evkeys (account_id, evkey, description) VALUES (?, ?, ?)',
        (account_id, evkey, description), commit=True,
    )


def delete_evkey(evkey_id):
    _exec('DELETE FROM evkeys WHERE id = ?', (evkey_id,), commit=True)


def toggle_evkey(evkey_id, enabled):
    _exec('UPDATE evkeys SET enabled = ? WHERE id = ?', (int(enabled), evkey_id), commit=True)