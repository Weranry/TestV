"""配置变更审计：记录管理员对 /admin/api/** 的写操作（谁改了什么）。

直接同步写库，不进日志队列：管理员的写操作频率极低（不会成为热路径），
而审计记录恰恰是最不该被"队列满后静默丢弃"丢掉的那类数据。
"""
from modules.database.core import _exec, _delete_batched, is_db_available


def log_audit(account_id, actor, ip, method, path, status_code, summary):
    """记一条审计。入库失败不能影响业务请求，调用方负责兜底"""
    _exec(
        'INSERT INTO audit_logs (account_id, actor, ip, method, path, status_code, summary) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (account_id, actor or '', ip or '', method, path, status_code, summary or ''),
        commit=True,
    )


def get_audit_logs(limit=100, offset=0):
    return _exec(
        'SELECT * FROM audit_logs ORDER BY id DESC LIMIT ? OFFSET ?',
        (limit, offset), fetch_all=True,
    )


def get_audit_log_count():
    row = _exec('SELECT COUNT(*) as cnt FROM audit_logs', fetch_one=True)
    return row['cnt'] if row else 0


def clear_audit_logs():
    row = _exec('SELECT COUNT(*) as cnt FROM audit_logs', fetch_one=True)
    deleted = row['cnt'] if row else 0
    # 整表单条 DELETE 会长时间占住全局写锁，与保留期清理同一处理：切成小批
    _delete_batched('DELETE FROM audit_logs WHERE id IN ('
                    'SELECT id FROM audit_logs LIMIT ?)', ())
    return deleted


def trim_audit_logs(max_rows):
    """超出上限时淘汰最旧记录。用 OFFSET 直接定位阈值 id，不跑全表 COUNT(*)"""
    if max_rows <= 0 or not is_db_available():
        return
    row = _exec(
        'SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1 OFFSET ?',
        (max_rows,), fetch_one=True,
    )
    if not row:
        return
    _delete_batched(
        'DELETE FROM audit_logs WHERE id IN ('
        'SELECT id FROM audit_logs WHERE id <= ? LIMIT ?)',
        (row['id'],),
    )


def prune_audit_logs(days):
    """删除超过保留期的审计日志（0 = 不按天数清理），返回删除条数。

    与请求日志的保留期清理同一套分批语义：单条大 DELETE 会长时间占住全局锁。
    """
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        return 0
    if days <= 0 or not is_db_available():
        return 0
    return _delete_batched(
        'DELETE FROM audit_logs WHERE id IN ('
        "SELECT id FROM audit_logs WHERE timestamp < datetime('now', ?) LIMIT ?)",
        (f'-{days} days',),
    )