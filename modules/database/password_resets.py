"""找回密码申请单：用户提交申请，管理员批准后拿到一次性临时密码。

申请单只记录「谁在什么时候申请」，不保存任何凭据。批准时由这里生成随机临时密码，
把哈希写进 accounts（见 accounts.set_account_temp_password），明文只在批准响应里
出现一次、由管理员转交；用户登录后 must_change_password 会强制其改密。
"""

import datetime
import secrets

from modules.database.accounts import set_account_temp_password
from modules.database.core import _exec

# 临时密码有效期：超过这个时间没被使用就作废，用户需要重新申请
TEMP_PASSWORD_TTL_HOURS = 24

# 已处理申请单的保留天数：只用于追溯，过期后由生命周期清理回收
RETENTION_DAYS = 30


def new_temp_password():
    """12 位十六进制临时密码：满足最小长度，字符无歧义，方便管理员口述或抄写。"""
    return secrets.token_hex(6)


def _expiry(hours):
    deadline = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)
    return deadline.strftime('%Y-%m-%d %H:%M:%S')


def create_request(account_id):
    """登记一条待处理申请；同一账号已有待处理申请时沿用原单，不重复堆积。"""
    row = _exec(
        "SELECT id FROM password_reset_requests WHERE account_id = ? AND status = 'pending' "
        'ORDER BY id LIMIT 1',
        (account_id,), fetch_one=True)
    if row:
        return row['id']
    return _exec(
        'INSERT INTO password_reset_requests (account_id) VALUES (?)',
        (account_id,), commit=True)


def list_pending():
    """待处理申请（含账号名/UID/邮箱/所在组类别，管理员据此核实身份）。

    组类别一并带出：面板要据此把「管理组账号」的批准按钮置灰（接口侧另有一道 403）。
    """
    return _exec(
        'SELECT r.id, r.account_id, r.created_at, a.uid, a.name AS account_name, a.email, '
        'g.category AS group_category '
        'FROM password_reset_requests r JOIN accounts a ON r.account_id = a.id '
        'JOIN user_groups g ON a.group_id = g.id '
        "WHERE r.status = 'pending' ORDER BY r.id",
        fetch_all=True)


def get_pending(request_id):
    """一条待处理申请的目标账号（含所在组类别）。批准前据此判定有没有越权。"""
    return _exec(
        'SELECT r.id, r.account_id, a.group_id, g.category AS group_category '
        'FROM password_reset_requests r JOIN accounts a ON r.account_id = a.id '
        'JOIN user_groups g ON a.group_id = g.id '
        "WHERE r.id = ? AND r.status = 'pending'",
        (request_id,), fetch_one=True)


def approve(request_id, admin_name, ttl_hours=TEMP_PASSWORD_TTL_HOURS):
    """批准申请：生成临时密码并写入账号，返回明文；申请不存在或已处理返回 None。

    先用带 `status = 'pending'` 条件的 UPDATE 抢占申请单，避免两个管理员同时点
    批准时生成两套互相覆盖的临时密码——只有一个能把状态从 pending 改走。
    """
    claimed = _exec(
        "UPDATE password_reset_requests SET status = 'approved', handled_by = ?, "
        "handled_at = datetime('now') WHERE id = ? AND status = 'pending'",
        (admin_name, request_id), commit=True, rowcount=True)
    if not claimed:
        return None
    row = _exec('SELECT account_id FROM password_reset_requests WHERE id = ?',
                (request_id,), fetch_one=True)
    if not row:
        return None
    temp_password = new_temp_password()
    set_account_temp_password(row['account_id'], temp_password, _expiry(ttl_hours))
    return temp_password


def purge_handled(days=RETENTION_DAYS):
    """清理保留期外的已处理申请（批准/拒绝），返回删除行数。

    待处理申请绝不在这里删：它们还没被任何人处理，删掉等于用户的申请凭空消失。
    表只会随申请增长，没有这轮兜底会一直累积。
    """
    return _exec(
        "DELETE FROM password_reset_requests WHERE status <> 'pending' "
        "AND handled_at <> '' AND handled_at < datetime('now', ?)",
        (f'-{int(days)} days',), commit=True, rowcount=True)


def reject(request_id, admin_name):
    """拒绝申请：只改状态，绝不触碰账号口令。返回是否成功占到这条待处理申请。"""
    return bool(_exec(
        "UPDATE password_reset_requests SET status = 'rejected', handled_by = ?, "
        "handled_at = datetime('now') WHERE id = ? AND status = 'pending'",
        (admin_name, request_id), commit=True, rowcount=True))
