"""激活码：注册时填写即进入指定用户组，并带上账号有效期与到期回落组。

语义（沿用项目「0 = 不限 / 不过期」约定）：
- max_uses = 0 → 不限激活次数；N → 最多激活 N 个账号，用完即作废（记录当场销毁）
- expires_on = '' → 激活码永不过期；'YYYY-MM-DD' → 过了当天（本地日期）即失效（同样销毁）
- duration_days = 0 → 激活出的账号永久有效；N → 自激活当日起 N 天后到期
- fallback_group_id = 0 → 到期后不转移；否则到期后自动转入该用户组

同一账号对同一张码只能生效一次（code_redemptions 表），否则不限次数的码会被反复核销。
"""
import secrets

from modules.database.core import _exec
from modules.utils.timezone import now_in_timezone


def today_iso():
    """本地日期。激活码有效日期与账号到期日都按本地自然日算，避免零点前后差一天"""
    return now_in_timezone().date().isoformat()


def expiry_after(days):
    """自今天起 N 天后的日期（激活码的 duration_days → 账号到期日）"""
    import datetime
    return (now_in_timezone().date() + datetime.timedelta(days=int(days))).isoformat()


def extend_expiry(current, days, today=None):
    """反复激活时的续期：在现有到期日上叠加 N 天，未用完的天数不丢。

    基准取 max(现有到期日, 今天)：已过期的账号从今天重新起算，没过期的接着往后加。
    账号当前没有到期日（'' = 永久）时基准取今天——注册进来的新账号本就没有到期日，
    首次激活一张限期码就必须得到一个真实到期日，否则「到期回落组」永远不会触发。
    days <= 0 表示码是永久有效，直接给永久。
    """
    import datetime
    if int(days or 0) <= 0:
        return ''
    today = today or today_iso()
    current = (current or '').strip()
    base = max(current, today) if current else today
    try:
        start = datetime.date.fromisoformat(base)
    except ValueError:
        # 到期日不是合法日期（老库脏数据）：退回「今天 + N 天」，不让它把激活流程带崩
        start = now_in_timezone().date()
    return (start + datetime.timedelta(days=int(days))).isoformat()


def new_code():
    """生成一个激活码（16 位十六进制）"""
    return secrets.token_hex(8)


def create_code(group_id, max_uses=0, expires_on='', duration_days=0,
                fallback_group_id=0, note='', allow_repeat=0):
    """新建激活码，返回 (id, code)。

    allow_repeat=1 时同一账号可以反复核销这张码（每次照常占一个可激活账号名额），
    默认 0 表示同一账号只能生效一次。
    """
    code = new_code()
    cid = _exec(
        'INSERT INTO activation_codes (code, group_id, max_uses, expires_on, duration_days,'
        ' fallback_group_id, note, allow_repeat) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (code, int(group_id), int(max_uses or 0), expires_on or '',
         int(duration_days or 0), int(fallback_group_id or 0), note or '',
         1 if allow_repeat else 0),
        commit=True,
    )
    return cid, code


def list_codes(group_id=None):
    """激活码列表。group_id 为 0/None 时返回全部用户组的码（跨组管理用）。

    带 group_name：目标用户组可被改名，面板要显示当前名字而不是让前端自己拼。
    """
    sql = ('SELECT c.*, g.name AS group_name FROM activation_codes c'
           ' LEFT JOIN user_groups g ON g.id = c.group_id')
    if group_id:
        return _exec(sql + ' WHERE c.group_id = ? ORDER BY c.id DESC',
                     (int(group_id),), fetch_all=True)
    return _exec(sql + ' ORDER BY c.id DESC', fetch_all=True)


def get_code(code_id):
    return _exec('SELECT * FROM activation_codes WHERE id = ?', (code_id,), fetch_one=True)


def get_code_by_code(code):
    return _exec('SELECT * FROM activation_codes WHERE code = ?', (code,), fetch_one=True)


def set_code_enabled(code_id, enabled):
    _exec('UPDATE activation_codes SET enabled = ? WHERE id = ?',
          (int(bool(enabled)), code_id), commit=True)


def set_code_allow_repeat(code_id, allow_repeat):
    """改「同一账号能否反复激活」开关。关掉只是以后不能再重复核销，已激活的账号不受影响"""
    _exec('UPDATE activation_codes SET allow_repeat = ? WHERE id = ?',
          (1 if allow_repeat else 0, code_id), commit=True)


def delete_code(code_id):
    """删除激活码，连带清掉它的核销记录。码 id 自增不复用，留着只是垃圾"""
    _exec('DELETE FROM code_redemptions WHERE code_id = ?', (code_id,), commit=True)
    _exec('DELETE FROM activation_codes WHERE id = ?', (code_id,), commit=True)


def code_status(row, today=None):
    """激活码状态：active / disabled / expired / exhausted / invalid。

    面板展示与核销条件必须是同一套判定，否则会出现「面板显示可用、注册却被拒」。
    """
    if not row:
        return 'invalid'
    if not int(row.get('enabled') or 0):
        return 'disabled'
    expires_on = (row.get('expires_on') or '').strip()
    if expires_on and (today or today_iso()) > expires_on:
        return 'expired'
    limit = int(row.get('max_uses') or 0)
    if limit > 0 and int(row.get('used_count') or 0) >= limit:
        return 'exhausted'
    return 'active'


def has_redeemed(code_id, account_id):
    """该账号是否已经用过这张码。用于自助激活去重（同账号同码只能生效一次）"""
    row = _exec(
        'SELECT 1 FROM code_redemptions WHERE code_id = ? AND account_id = ?',
        (int(code_id), int(account_id)), fetch_one=True,
    )
    return row is not None


def record_redemption(code_id, account_id, code):
    """记录一次核销。UNIQUE(code_id, account_id) 兜底，重复插入直接抛异常"""
    _exec(
        'INSERT INTO code_redemptions (code_id, account_id, code) VALUES (?, ?, ?)',
        (int(code_id), int(account_id), code), commit=True,
    )


def redeem(code, today=None):
    """核销一次激活码。成功返回该码的行，无效/过期/用完返回 None。

    自增与全部判定合成同一条 UPDATE（上限写进 WHERE）：拆成「先查再写」的话，
    并发注册会双双通过检查，把可激活账号数用超。
    """
    n = _exec(
        'UPDATE activation_codes SET used_count = used_count + 1'
        " WHERE code = ? AND enabled = 1"
        " AND (expires_on = '' OR expires_on >= ?)"
        ' AND (max_uses <= 0 OR used_count < max_uses)',
        (code, today or today_iso()), commit=True, rowcount=True,
    )
    if not n:
        return None
    return get_code_by_code(code)


def redeem_for_account(code, account_id, today=None):
    """自助激活核销：同一账号同一张码只能生效一次。

    返回 (行, None) 或 (None, 原因)，原因取值 invalid / disabled / expired / exhausted / used。
    原因必须能分开——「这个码你已经用过了」和「这个码无效/过期」要能分别提示，
    否则 max_uses = 0（不限次数）的码会被同一账号反复核销、每次都报「激活成功」。
    """
    row = get_code_by_code(code)
    if row is None:
        return None, 'invalid'
    repeat = int(row.get('allow_repeat') or 0)
    # 先看这张码本账号是否已经用过：有限次的码用满后 status 会变成 exhausted，
    # 但对重试的本人来说「你已经用过了」才是准确提示（别人再试才叫已用尽）。
    # 开了 allow_repeat 的码跳过这一步——反复激活是它要的效果。
    if not repeat and has_redeemed(row['id'], account_id):
        return None, 'used'
    status = code_status(row, today)
    if status != 'active':
        return None, status
    if redeem(code, today) is None:
        # 判定与自增之间被并发抢先（停用/删掉/用尽）
        return None, 'invalid'
    row = get_code_by_code(code)
    if repeat:
        # 不写核销记录：code_redemptions 的 UNIQUE(code_id, account_id) 只容得下一次，
        # 这类码按定义就是要同一账号能用多次，审计让位给简单
        return row, None
    try:
        record_redemption(row['id'], account_id, code)
    except Exception:
        # 同账号双开同时提交：唯一约束兜住，把刚扣的名额还回去
        refund(code)
        return None, 'used'
    return row, None


def refund(code, account_id=None):
    """把刚核销的一次还回去。仅用于核销成功后建号/落组失败的情况，否则用户白扣一个名额。

    自助激活传 account_id：连核销记录一起撤掉，否则这次失败的尝试会把该账号
    永久标记成「已用过这张码」，等码恢复正常后也再激活不了。
    """
    if account_id is not None:
        row = get_code_by_code(code)
        if row:
            _exec('DELETE FROM code_redemptions WHERE code_id = ? AND account_id = ?',
                  (row['id'], int(account_id)), commit=True)
    _exec(
        'UPDATE activation_codes SET used_count = used_count - 1 WHERE code = ? AND used_count > 0',
        (code,), commit=True,
    )


def purge_if_exhausted(code_id):
    """激活码「用完即销毁」：有限次码用尽后立即从面板消失。

    无限次（max_uses = 0）的码永远用不尽，保留；只有显式设了上限且已用满的才删。
    """
    row = get_code(code_id)
    if row is None:
        return False
    limit = int(row.get('max_uses') or 0)
    if limit > 0 and int(row.get('used_count') or 0) >= limit:
        delete_code(code_id)
        return True
    return False


def purge_dead_codes(today=None):
    """把所有废码当场销毁：过了有效日期的 + 有限次已用满的。返回销毁条数。

    核销与后台扫描都会当场销毁，这里再兜一次底——老库里在本次改动之前就已经
    用满/过期的码不会再有任何机会被清理，面板一刷新就不该再看到它们。
    """
    today = today or today_iso()
    dead = ("(expires_on <> '' AND expires_on < ?)"
            ' OR (max_uses > 0 AND used_count >= max_uses)')
    # 先只读探一次：没有废码就直接返回，省掉两条 DELETE + 两次 commit。
    # 本函数由后台刷盘线程每轮调用（见 lifecycle.start_flush_thread），空闲站点上
    # 这两条写语句是纯开销——不删任何行也要开一次写事务、占一次全局写锁、磨一次 SD 卡。
    if _exec(f'SELECT 1 FROM activation_codes WHERE {dead} LIMIT 1',
             (today,), fetch_one=True) is None:
        return 0
    _exec('DELETE FROM code_redemptions WHERE code_id IN'
          f' (SELECT id FROM activation_codes WHERE {dead})', (today,), commit=True)
    return _exec(f'DELETE FROM activation_codes WHERE {dead}', (today,),
                 commit=True, rowcount=True)


def expire_accounts(today=None):
    """到期账号转入各自回落组，返回 [(account_id, 原组 id, 新组 id)]。

    fallback_group_id = 0 的账号不参与（到期后留在原组，面板仍按已过期展示），
    因此只捞有回落组的。转移后清空 expires_on / fallback_group_id：账号已永久
    归属新组，下一次扫描不必再看到它。

    每次归位写一条 account_membership_logs（action='expire'）：这是一次真实的
    权限下降，面板的「权限记录」里必须能解释「我的组怎么自己变了」。
    """
    rows = _exec(
        "SELECT id, group_id, fallback_group_id FROM accounts"
        " WHERE expires_on <> '' AND expires_on <= ? AND fallback_group_id > 0",
        (today or today_iso(),), fetch_all=True,
    )
    if not rows:
        return []
    from modules.database.membership import get_membership, log_change
    # 变动前的快照要在 UPDATE 之前取，否则前后一样、看不出是被归位了
    before = {r['id']: get_membership(r['id']) for r in rows}
    ids = [r['id'] for r in rows]
    _exec(
        'UPDATE accounts SET group_id = fallback_group_id, fallback_group_id = 0, expires_on = \'\''
        f" WHERE id IN ({','.join('?' for _ in ids)})",
        ids, commit=True,
    )
    for r in rows:
        after = get_membership(r['id'])
        if before.get(r['id']) and after:
            log_change(r['id'], 'expire', before[r['id']], after, '会员到期自动归位', '')
    return [(r['id'], r['group_id'], r['fallback_group_id']) for r in rows]