from modules.database.core import _exec, _get_conn, _db_lock

# ---- Server Info ----

def get_server_info(key):
    row = _exec('SELECT value FROM server_info WHERE key = ?', (key,), fetch_one=True)
    return row['value'] if row else None


def set_server_info(key, value):
    _exec(
        'INSERT OR REPLACE INTO server_info (key, value) VALUES (?, ?)',
        (key, str(value)), commit=True,
    )


# ---- Server Sessions ----

def create_session(start_time, mode, version):
    return _exec(
        'INSERT INTO server_sessions (start_time, mode, version) VALUES (?, ?, ?)',
        (start_time, mode, version), commit=True,
    )


def close_session(session_id, end_time):
    _exec(
        'UPDATE server_sessions SET end_time = ? WHERE id = ?',
        (end_time, session_id), commit=True,
    )


def close_stale_sessions():
    """启动时关闭所有未正常结束的历史会话（上次进程被强杀遗留）。

    结束时间取心跳 last_seen 而非当前时间：进程被杀后可能隔很久才重启，
    用当前时间会把「已停机但没重启」的那段空白也算成运行时长（凭空多出十几小时）。
    没有心跳的旧会话退化为 start_time，时长记 0。
    """
    _exec(
        'UPDATE server_sessions SET end_time = COALESCE(last_seen, start_time) WHERE end_time IS NULL',
        commit=True,
    )


def touch_session(session_id, ts):
    """运行中会话的心跳，由后台刷盘线程周期调用"""
    _exec('UPDATE server_sessions SET last_seen = ? WHERE id = ?', (ts, session_id), commit=True)


def get_all_sessions():
    return _exec(
        'SELECT * FROM server_sessions ORDER BY id DESC',
        fetch_all=True,
    )


def get_session_count():
    """启动会话总数（概览页展示用，只 COUNT 不 JOIN）"""
    row = _exec('SELECT COUNT(*) as cnt FROM server_sessions', fetch_one=True)
    return row['cnt'] if row else 0


def get_total_uptime_seconds():
    row = _exec(
        "SELECT COALESCE(SUM(CAST((julianday(COALESCE(end_time, datetime('now'))) - julianday(start_time)) * 86400 AS INTEGER)), 0) AS total "
        'FROM server_sessions',
        fetch_one=True,
    )
    return row['total'] if row else 0


def get_session_stats(limit=100):
    """每次启动会话：持续时间 + 期间请求量/错误量（单次 JOIN 聚合，避免逐会话子查询）"""
    return _exec(
        'SELECT s.id, s.start_time, s.end_time, s.mode, s.version, '
        "CAST((julianday(COALESCE(s.end_time, datetime('now'))) - julianday(s.start_time)) * 86400 AS INTEGER) AS uptime_seconds, "
        'COUNT(r.id) AS requests, '
        # 与 request_logs 的错误口径一致：只有 5xx 算错误（4xx 是调用方的问题）
        'COALESCE(SUM(CASE WHEN r.status_code >= 500 THEN 1 ELSE 0 END), 0) AS errors '
        'FROM server_sessions s '
        'LEFT JOIN request_logs r ON r.timestamp >= s.start_time AND (s.end_time IS NULL OR r.timestamp <= s.end_time) '
        'GROUP BY s.id ORDER BY s.id DESC LIMIT ?',
        (limit,), fetch_all=True,
    )


# ---- Plugin Stats ----

def load_plugin_request_counts():
    rows = _exec('SELECT plugin_name, request_count FROM plugin_stats', fetch_all=True)
    return {r['plugin_name']: r['request_count'] for r in rows}


def get_all_plugin_stats():
    rows = _exec('SELECT * FROM plugin_stats ORDER BY request_count DESC', fetch_all=True)
    return rows


def flush_plugin_request_counts(deltas):
    """把内存里的插件请求计数**增量**刷入数据库。

    参数是「自上次成功落库以来新增的数量」，落库走累加：整值覆盖在多实例部署下会让
    后写的实例把别的实例的计数抹掉（静默丢数据），而累加对单实例同样正确。

    整体一条 executemany：逐插件单条 UPSERT 时，N 个插件就要 N 次 execute +
    N 次 commit，而这段是在全局锁内跑的，会拖住同期的渲染请求。
    """
    now_iso = _exec("SELECT datetime('now')", fetch_one=True)["datetime('now')"]
    rows = [
        (plugin_name, count, plugin_name, now_iso, now_iso)
        for plugin_name, count in deltas.items()
    ]
    if not rows:
        return
    conn = _get_conn()
    with _db_lock:
        conn.executemany(
            'INSERT INTO plugin_stats (plugin_name, request_count, first_request, last_request) '
            'VALUES (?, ?, COALESCE((SELECT first_request FROM plugin_stats WHERE plugin_name = ?), ?), ?) '
            'ON CONFLICT(plugin_name) DO UPDATE SET '
            'request_count = request_count + excluded.request_count, '
            'last_request = excluded.last_request',
            rows,
        )
        conn.commit()


# ---- Account Stats（账号维度长期累计用量） ----

def load_account_usage(date):
    """载入指定日期已有的账号用量，作为进程内累计的基线。

    启动时载入后内存里继续累加，落库只写「自上次成功落库以来的增量」（累加写入），
    因此既是幂等的，重启后也不会把当天已落库的部分覆盖成 0。
    """
    rows = _exec(
        'SELECT account_id, plugin_name, request_count, error_count, total_ms '
        'FROM account_stats WHERE date = ?',
        (date,), fetch_all=True,
    )
    return {
        (date, r['account_id'], r['plugin_name']): [
            r['request_count'] or 0, r['error_count'] or 0, r['total_ms'] or 0,
        ]
        for r in rows
    }


def flush_account_usage(rows):
    """rows: [(date, account_id, plugin_name, request_count, error_count, total_ms)]，增量累加。

    与 flush_plugin_request_counts 同一条理由：整值覆盖在多实例下会互相抹掉计数。
    """
    if not rows:
        return
    conn = _get_conn()
    with _db_lock:
        conn.executemany(
            'INSERT INTO account_stats (date, account_id, plugin_name, request_count, error_count, total_ms) '
            'VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(date, account_id, plugin_name) DO UPDATE SET '
            'request_count = request_count + excluded.request_count, '
            'error_count = error_count + excluded.error_count, '
            'total_ms = total_ms + excluded.total_ms',
            rows,
        )
        conn.commit()


def get_account_usage_daily(account_id, days=30):
    """某账号的按天用量（跨插件汇总）"""
    return _exec(
        'SELECT date, SUM(request_count) as total, SUM(error_count) as errors, '
        'ROUND(SUM(total_ms) / SUM(request_count), 1) as avg_ms '
        'FROM account_stats WHERE account_id = ? AND date >= date(\'now\', ?) '
        'GROUP BY date ORDER BY date DESC',
        (account_id, f'-{days} days'), fetch_all=True,
    )


def get_account_usage_by_plugin(account_id, days=30):
    """某账号的按插件用量"""
    return _exec(
        'SELECT plugin_name, SUM(request_count) as total, SUM(error_count) as errors, '
        'ROUND(SUM(total_ms) / SUM(request_count), 1) as avg_ms '
        'FROM account_stats WHERE account_id = ? AND date >= date(\'now\', ?) '
        'GROUP BY plugin_name ORDER BY total DESC',
        (account_id, f'-{days} days'), fetch_all=True,
    )