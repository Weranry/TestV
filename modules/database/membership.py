"""账号会员属性的变动记录（用户组升降 + 有效期增减）。

一张表同时承载三类变动：管理员手动调整（set）、激活码开通/续期（activate）、
到期自动归位（expire）。记录里冗余存下组名与到期日，用户组事后被删除也不影响回看。
"""
from modules.database.core import _exec

# 变动类型 → 面板徽章文案与配色（badge-on / badge-off / badge-warn）
ACTION_LABELS = {
    'set': '管理员调整',
    'activate': '激活码开通',
    'expire': '到期归位',
}


def get_membership(account_id):
    """账号当前的会员属性（含所属用户组名与回落组名），用于改动前后快照"""
    return _exec(
        'SELECT a.id AS account_id, a.group_id, g.name AS group_name, a.expires_on,'
        ' a.fallback_group_id, '
        "COALESCE((SELECT f.name FROM user_groups f WHERE f.id = a.fallback_group_id), '') "
        'AS fallback_group_name '
        'FROM accounts a JOIN user_groups g ON a.group_id = g.id WHERE a.id = ?',
        (account_id,), fetch_one=True,
    )


def _empty_snapshot():
    return {
        'group_id': 0, 'group_name': '', 'expires_on': '',
        'fallback_group_id': 0, 'fallback_group_name': '',
    }


def _pick(snapshot, key):
    return (snapshot or _empty_snapshot()).get(key) or ''


def log_change(account_id, action, old, new, reason='', admin_name=''):
    """记一条会员变动。

    old / new 是 get_membership() 的结果或同结构字典（None 视为空快照）。
    调用方负责保证确实是变动后再调用——无变化也写一行只是噪音。
    """
    _exec(
        'INSERT INTO account_membership_logs (account_id, action, old_group_id, new_group_id,'
        ' old_group_name, new_group_name, old_expires_on, new_expires_on,'
        ' old_fallback_group_id, new_fallback_group_id, old_fallback_name, new_fallback_name,'
        ' reason, admin_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            int(account_id), action or '',
            int(_pick(old, 'group_id') or 0), int(_pick(new, 'group_id') or 0),
            _pick(old, 'group_name'), _pick(new, 'group_name'),
            _pick(old, 'expires_on'), _pick(new, 'expires_on'),
            int(_pick(old, 'fallback_group_id') or 0), int(_pick(new, 'fallback_group_id') or 0),
            _pick(old, 'fallback_group_name'), _pick(new, 'fallback_group_name'),
            reason or '', admin_name or '',
        ),
        commit=True,
    )


def list_logs(account_id, limit=50, offset=0):
    return _exec(
        'SELECT * FROM account_membership_logs WHERE account_id = ? ORDER BY id DESC'
        ' LIMIT ? OFFSET ?',
        (account_id, max(1, int(limit)), max(0, int(offset))), fetch_all=True,
    )


def count_logs(account_id):
    row = _exec(
        'SELECT COUNT(*) AS cnt FROM account_membership_logs WHERE account_id = ?',
        (account_id,), fetch_one=True,
    )
    return row['cnt'] if row else 0


def purge_account_logs(account_id):
    _exec('DELETE FROM account_membership_logs WHERE account_id = ?', (account_id,), commit=True)
