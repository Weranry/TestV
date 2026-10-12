"""账号级配额：限额 + 周期（day / week / month / year / trial）。

计数落库、惰性重置：周期到期不靠定时任务归零，而是下一次请求发现 period_start
变了之后当场重置。服务停机再久，重启后的第一次请求也会自动进入新周期，不会把
停机期间的时间算进额度里。trial（按次总量）的 period_start 恒为空串，永不重置，
等于「这个账号一生就这么多」；到期自动补齐指的是其余周期——到点 used 归零，
未用部分不结转（额度不累加，每期固定就是 quota_limit）。

实际可用额度 = 用户组配额 + 账号级发放额度（account_quotas.granted）。发放额跨周期
持久保留，不随惰性重置归零；要回收就发负数。自动重置不写操作流水，只有管理员的
发放 / 手动重置才落 account_quota_logs，否则每个周期首个请求都要多写一次库。

计数范围是账号：同一账号下所有 evkey 共用一份额度。
"""
from modules.database.core import _exec, is_db_available
from modules.utils.timezone import now_in_timezone

PERIODS = ('day', 'week', 'month', 'year', 'trial')

# 发放 / 手动重置的操作流水动作名
ACTION_GRANT = 'grant'
ACTION_RESET = 'reset'


def normalize_period(period):
    """非法/缺省一律按 day 处理，避免坏值被带进 period_start 的计算"""
    p = str(period or '').strip().lower()
    return p if p in PERIODS else 'day'


def period_start(period, now=None):
    """当前周期的起点标识。trial 返回空串——它永不重置"""
    period = normalize_period(period)
    if period == 'trial':
        return ''
    dt = now or now_in_timezone()
    if period == 'day':
        return dt.date().isoformat()
    if period == 'week':
        iso = dt.isocalendar()
        return f'{iso[0]}-W{iso[1]:02d}'
    if period == 'month':
        return f'{dt.year}-{dt.month:02d}'
    return str(dt.year)


def _as_limit(limit):
    try:
        return int(limit)
    except (TypeError, ValueError):
        return 0


def _ensure_row(account_id):
    """占位一行，供后续的原子 UPDATE 有目标可改（已存在则什么都不做）。

    period_start 留空串：下一次 consume 会发现与当前周期不符而当场归零，
    等于「还没开始计数」，不会把发放前的余额算进本周期。
    """
    _exec(
        'INSERT OR IGNORE INTO account_quotas (account_id, period_start, used, granted) '
        "VALUES (?, '', 0, 0)",
        (account_id,), commit=True,
    )


def get_granted(account_id):
    """该账号已发放的额外额度（回收会记负数）。无记录返回 0"""
    if account_id is None or not is_db_available():
        return 0
    row = _exec(
        'SELECT granted FROM account_quotas WHERE account_id = ?', (account_id,), fetch_one=True,
    )
    return int(row['granted']) if row else 0


def consume(account_id, limit, period):
    """记一次额度消耗，返回 (是否放行, 本周期已用, 周期起点, 实际额度)。

    limit <= 0 表示不限：直接放行且完全不落库，无配额的组（默认值就是 0）
    在热路径上不该为配额付任何数据库开销。
    """
    if account_id is None or not is_db_available():
        return True, 0, '', 0
    limit = _as_limit(limit)
    if limit <= 0:
        return True, 0, '', 0
    start = period_start(period)
    # 惰性重置：只有周期变了的那一次把 used 归零，同周期内是空操作。
    # granted 不在 SET 里，发放额跨周期保留。
    _exec(
        'INSERT INTO account_quotas (account_id, period_start, used) VALUES (?, ?, 0) '
        'ON CONFLICT(account_id) DO UPDATE SET used = 0, period_start = excluded.period_start '
        'WHERE account_quotas.period_start <> excluded.period_start',
        (account_id, start), commit=True,
    )
    # 条件自增：used < limit + granted 时才写得进去，rowcount 就是「放不放行」的答案。
    # 上限随 granted 一起在 SQL 里求和，读-判-写合成一条语句，并发下也不会超额放行，
    # 也不会出现「读到旧 granted → 算出旧上限 → 多放行」的窗口。
    allowed = _exec(
        'UPDATE account_quotas SET used = used + 1 WHERE account_id = ? AND used < ? + granted',
        (account_id, limit), commit=True, rowcount=True,
    )
    row = _exec(
        'SELECT used, granted FROM account_quotas WHERE account_id = ?', (account_id,), fetch_one=True,
    )
    if row is None:
        return bool(allowed), 1 if allowed else 0, start, limit
    effective = limit + int(row['granted'])
    # 未放行时返回的是上限本身，而不是已经超出的 used：展示「已用 X / 共 X」比
    # 「已用 X+3 / 共 X」更符合直觉
    used = int(row['used']) if allowed else min(int(row['used']), effective)
    return bool(allowed), used, start, effective


def get_status(account_id, limit, period):
    """只读查看当前周期用量（不消耗额度），供个人控制台展示。

    返回 (实际额度, 已用, 周期, 周期起点)；limit <= 0 表示不限，此时已用恒为 0。
    """
    period = normalize_period(period)
    limit = _as_limit(limit)
    if limit <= 0 or account_id is None or not is_db_available():
        return limit, 0, period, period_start(period)
    start = period_start(period)
    row = _exec(
        'SELECT period_start, used, granted FROM account_quotas WHERE account_id = ?',
        (account_id,), fetch_one=True,
    )
    effective = limit + (int(row['granted']) if row else 0)
    # 还没开始新周期的计数：库里存的仍是上个周期的数字，展示要按 0 算
    used = int(row['used']) if row and row['period_start'] == start else 0
    return effective, used, period, start


def _log_action(account_id, action, amount, period, reason, admin_name):
    _exec(
        'INSERT INTO account_quota_logs (account_id, action, amount, period, reason, admin_name) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (account_id, action, int(amount or 0), str(period or ''), str(reason or '')[:200],
         str(admin_name or '')[:64]),
        commit=True,
    )


def list_logs(account_id, limit=50, offset=0):
    """账号的额度操作流水，新的在前"""
    if account_id is None or not is_db_available():
        return []
    return _exec(
        'SELECT id, action, amount, period, reason, admin_name, created_at '
        'FROM account_quota_logs WHERE account_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
        (account_id, max(1, int(limit)), max(0, int(offset))), fetch_all=True,
    )


def count_logs(account_id):
    if account_id is None or not is_db_available():
        return 0
    row = _exec(
        'SELECT COUNT(*) AS cnt FROM account_quota_logs WHERE account_id = ?',
        (account_id,), fetch_one=True,
    )
    return int(row['cnt']) if row else 0


def grant(account_id, amount, base_limit, period='', reason='', admin_name=''):
    """发放（amount > 0）或回收（amount < 0）账号级额外额度。

    base_limit 是该账号所属组的配额：<= 0 表示不限，此时发放没有意义（本来就不限）。
    返回 (是否成功, 失败原因, 调整后的实际额度)。调整后总额度必须 >= 1——
    0 在项目里等于「不限」，负数则永远放行不了，两者都是会静默走样的坏状态。
    """
    if account_id is None or not is_db_available():
        return False, '数据库不可用', 0
    amount = _as_limit(amount)
    if amount == 0:
        return False, '发放数量不能为 0', 0
    base = _as_limit(base_limit)
    if base <= 0:
        return False, '该账号所属用户组未设置配额（不限），无需发放', 0
    _ensure_row(account_id)
    # 原子累加，并在同一条语句里保证调整后总额度 >= 1
    changed = _exec(
        'UPDATE account_quotas SET granted = granted + ? WHERE account_id = ? AND ? + granted + ? >= 1',
        (amount, account_id, base, amount), commit=True, rowcount=True,
    )
    if not changed:
        return False, '调整后总额度需至少为 1 次', 0
    row = _exec(
        'SELECT granted FROM account_quotas WHERE account_id = ?', (account_id,), fetch_one=True,
    )
    total = base + (int(row['granted']) if row else 0)
    _log_action(account_id, ACTION_GRANT, amount, period, reason, admin_name)
    return True, '', total


def reset(account_id, period='', reason='', admin_name=''):
    """手动重置：本周期已用归零，已发放额度保留（不是把额度收回去）。

    自动重置（到期 used 归零）由 consume 的惰性重置完成，不经过这里、也不记流水。
    """
    if account_id is None or not is_db_available():
        return False
    _exec('UPDATE account_quotas SET used = 0 WHERE account_id = ?', (account_id,), commit=True)
    _log_action(account_id, ACTION_RESET, 0, period, reason, admin_name)
    return True