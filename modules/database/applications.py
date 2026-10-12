from modules.database.core import _exec
from modules.database.accounts import new_evkey, count_evkeys_for_account


class EvkeyLimitExceeded(Exception):
    """账号已持有的 evkey 数达到目标用户组上限，不能再发放"""


# ---- EVKEY Applications ----

def group_max_evkeys(group_id):
    """用户组的 evkey 持有上限：-1 = 不限，0 = 禁止创建，N = 最多 N 个；组不存在按 0 处理。

    管理组一律返回 -1（不限）：这个上限是给外部使用者设的护栏，拿它卡住后台操作者
    只会让管理员在紧急情况下发不出新密钥。判定放在这一处，三条发放路径
    （管理端代发、管理端批量生成、用户自助申请/审批）读的都是同一份口径。
    注意是「折算成 -1」而不是「把库里的值改成 -1/0」：0 在 evkey 语义里是禁止创建，
    改配置既歧义，又会被后来的人当成可调项再改回去。
    """
    row = _exec('SELECT max_evkeys, category FROM user_groups WHERE id = ?',
                (group_id,), fetch_one=True)
    if not row:
        return 0
    from modules.database.groups import is_admin_category
    if is_admin_category(row.get('category')):
        return -1
    return int(row['max_evkeys'] or 0)


def evkey_quota(max_evkeys, held, pending=0):
    """还能再发几个 evkey。上限为负（不限）时返回 -1，其余返回 max(0, 上限 - 已持有 - 审批中)。

    审批中的申请也要占名额：只看已持有的话，用户能把申请堆到上限之外，管理员挨个
    批准后就超了。上限判定统一走这里，避免「0 = 不限」的旧假设在各处残留。
    """
    try:
        limit = int(max_evkeys)
    except (TypeError, ValueError):
        return 0
    if limit < 0:
        return -1
    return max(0, limit - int(held or 0) - int(pending or 0))


def count_pending_applications(account_id):
    return _exec("SELECT COUNT(*) AS cnt FROM evkey_applications WHERE account_id = ? AND status = 'pending'",
                 (account_id,), fetch_one=True)['cnt']


def list_applications_for_account(account_id, status='pending', limit=20):
    """本账号的申请明细：用户端列表要能看到「审批中」那几行。

    只回计数的话，提交完申请的用户在列表里看不到任何东西，会以为申请丢了而反复提交，
    每提交一次就多占一个名额（evkey_quota 把 pending 也算在内）。
    """
    return _exec('SELECT id, status, applicant_note, created_at FROM evkey_applications'
                 ' WHERE account_id = ? AND status = ?'
                 ' ORDER BY created_at DESC, id DESC LIMIT ?',
                 (account_id, status, limit), fetch_all=True)


def create_evkey_application(account_id, account_name, applicant_note='', group_id=1):
    return _exec(
        'INSERT INTO evkey_applications (account_id, account_name, applicant_note, group_id) VALUES (?, ?, ?, ?)',
        (account_id, account_name, applicant_note, group_id), commit=True,
    )


def get_application_groups(status=None, limit=50, offset=0):
    """按账号折叠申请：一个账号一行，附带该账号在当前筛选下的全部申请明细。

    分页必须落在「账号」这一层：若按申请行分页，同一账号的申请会被切到两页，
    折叠后就会出现两条同名行，每页的行数也对不上。
    """
    where, params = '', []
    if status:
        where = ' WHERE status = ?'
        params.append(status)
    groups = _exec(
        'SELECT account_id, account_name, COUNT(*) AS total,'
        " SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,"
        " SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,"
        " SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,"
        ' MAX(created_at) AS latest_at'
        ' FROM evkey_applications' + where +
        # created_at 只精确到秒，同秒的账号必须有稳定次序，否则翻页会漏行/重行
        ' GROUP BY account_id, account_name'
        ' ORDER BY latest_at DESC, account_name DESC LIMIT ? OFFSET ?',
        params + [limit, offset], fetch_all=True,
    )
    if not groups:
        return groups
    # 明细一次取回：按 (account_id, account_name) 匹配，避免逐组各查一次库。
    # 老库的 account_id 可能为空，用 -1 兜住以保证 NULL 也能等值匹配。
    keys = []
    for g in groups:
        keys.extend([-1 if g['account_id'] is None else g['account_id'], g['account_name']])
    clause = ' OR '.join(['(IFNULL(account_id, -1) = ? AND account_name = ?)'] * len(groups))
    sql = 'SELECT * FROM evkey_applications WHERE (' + clause + ')'
    if status:
        sql += ' AND status = ?'
        keys.append(status)
    bucket = {}
    for row in _exec(sql + ' ORDER BY created_at DESC, id DESC', keys, fetch_all=True):
        bucket.setdefault((row['account_id'] or -1, row['account_name']), []).append(row)
    for g in groups:
        g['applications'] = bucket.get((g['account_id'] or -1, g['account_name']), [])
    return groups


def count_application_groups(status=None):
    """折叠后的账号数：分页总数必须与列表口径一致，否则末页会空"""
    sql = 'SELECT COUNT(*) AS cnt FROM (SELECT 1 FROM evkey_applications'
    params = []
    if status:
        sql += ' WHERE status = ?'
        params.append(status)
    return _exec(sql + ' GROUP BY account_id, account_name)', params, fetch_one=True)['cnt']


def count_evkey_applications(status=None):
    sql = 'SELECT COUNT(*) as cnt FROM evkey_applications WHERE 1=1'
    params = []
    if status:
        sql += ' AND status = ?'
        params.append(status)
    return _exec(sql, params, fetch_one=True)['cnt']


def _application_group_id(app):
    """申请单自带的用户组；老库里没写（NULL/0）时回落到账号当前所在组。

    批准不再让管理员选组：申请时就把申请人所在组写进了这一行，选组只会把
    「这个人属于哪个组」重新问一遍，答错了还会拿另一个组的上限去卡他。
    """
    group_id = app.get('group_id') or 0
    if group_id:
        return int(group_id)
    from modules.database.accounts import get_account_row
    row = get_account_row(app['account_id']) if app.get('account_id') else None
    return int((row or {}).get('group_id') or 0)


def approve_evkey_application(app_id, admin_note=''):
    app = _exec('SELECT * FROM evkey_applications WHERE id = ? AND status = ?',
                (app_id, 'pending'), fetch_one=True)
    if not app:
        return None
    account_id = app['account_id']
    limit = group_max_evkeys(_application_group_id(app))
    # 批准前再卡一次上限：申请时校验过，但排队期间管理员可能已批准过同账号的其他申请
    held = count_evkeys_for_account(account_id)
    if evkey_quota(limit, held) == 0:
        reason = '该用户组不允许创建 evkey' if limit == 0 \
            else '已持有 %d 个 evkey，达到用户组上限 %d 个' % (held, limit)
        raise EvkeyLimitExceeded('账号「%s」%s，无法再批准' % (app['account_name'], reason))
    evkey = new_evkey()
    # 抢占式改状态：把「仍为 pending」写进 WHERE，用 rowcount 判成败。
    # 原先的「先 SELECT 判 pending、再无条件 UPDATE」在双击或两个管理员同时审批时，
    # 两次 SELECT 都会读到 pending，于是各插一把 evkey——一次申请发两个密钥。
    # 与 reject_evkey_application 同一套原子写法。
    changed = _exec("UPDATE evkey_applications SET status = 'approved', admin_note = ?, "
                    "updated_at = datetime('now') "
                    "WHERE id = ? AND status = 'pending'",
                    (admin_note, app_id), commit=True, rowcount=True)
    if not changed:
        return None
    _exec('INSERT INTO evkeys (account_id, evkey, description) VALUES (?, ?, ?)',
          (account_id, evkey, 'auto-generated'), commit=True)
    return {'account_id': account_id, 'account_name': app['account_name'], 'evkey': evkey}


def reject_evkey_application(app_id, admin_note=''):
    """拒绝单条申请，返回真正改动的行数（已处理过的申请是 0，不计入批量结果）"""
    return _exec("UPDATE evkey_applications SET status = 'rejected', admin_note = ?, "
                 "updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
                 (admin_note, app_id), commit=True, rowcount=True)


def batch_approve_evkey_applications(app_ids, admin_note=''):
    """批量批准：逐条只处理仍为 pending 的申请。

    返回 (生成的 evkey 列表, 被跳过原因列表)：某个账号已到上限不该中断整批，
    但要把它为什么没批准告诉管理员，否则会被当成"已处理"而静默消失。
    """
    result, skipped = [], []
    for app_id in app_ids:
        try:
            one = approve_evkey_application(app_id, admin_note)
        except EvkeyLimitExceeded as e:
            skipped.append(str(e))
            continue
        if one:
            result.append({'id': app_id, 'account_id': one['account_id'],
                           'account_name': one['account_name'], 'evkey': one['evkey']})
    return result, skipped


def batch_reject_evkey_applications(app_ids, admin_note=''):
    """批量拒绝，返回真正被拒绝的条数"""
    return sum(1 for app_id in app_ids if reject_evkey_application(app_id, admin_note))