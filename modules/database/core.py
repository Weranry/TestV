import sqlite3
import os
import hashlib
import hmac
import secrets
import threading
import queue

from modules.database import migrations

DB_DIR_NAME = 'data'
DB_FILE_NAME = 'einkviews.db'

_db_path = None
_db_lock = threading.Lock()
# 惰性建连接 / 建日志队列时的互斥：并发首次调用会各自建一份，被覆盖的那份永远
# 无人关闭或排空（连接泄漏 + 队列里的日志静默丢失），所以用双重检查加锁。
_init_lock = threading.Lock()
_pool_conn = None
_log_queue = None
_initialized = False
_db_disabled = False

# --- 只读连接池 ---
# 写路径保持「单连接 + 全局写锁」不变（SQLite 单写者是既定取向），只给**读查询**另开
# 一组只读连接：WAL 下读不阻塞写，读查询因此不必再排队等 _db_lock——原先所有查询
# （包括每个请求都要跑的鉴权、配额、日志列表）都被同一把锁串起来，是并发上限的硬瓶颈。
#
# 只读连接带 PRAGMA query_only=1：即使代码写错，也不可能通过这些连接改库。
_read_cond = threading.Condition(threading.Lock())
_read_idle = []       # 空闲的只读连接（当栈用，后进先出，热点连接更不容易被回收）
_read_in_use = 0      # 已借出的连接数（含正在创建的），用于按上限限流
_read_epochs = {}     # id(conn) -> 借出时的池代次，用于识别跨代的陈旧连接
_read_epoch = 0       # 池代次：set_db_path / close_connection 时 +1，旧连接随之作废


class DatabaseUnavailable(RuntimeError):
    """当前运行模式禁用了 SQLite（Vercel Serverless 无持久存储）"""


def set_db_disabled(disabled):
    """停用后所有数据库调用直接抛错，不解析路径、不建目录、不建连接"""
    global _db_disabled
    _db_disabled = bool(disabled)


def is_db_available():
    return not _db_disabled


def _ensure_log_queue():
    global _log_queue
    if _log_queue is None:
        with _init_lock:
            if _log_queue is None:
                from config import LOG_QUEUE_MAXSIZE
                _log_queue = queue.Queue(maxsize=LOG_QUEUE_MAXSIZE)
    return _log_queue


def _get_db_path():
    """数据库统一放在项目根目录的 data/ 下。

    data/ 不属于 public/ 静态目录，不会被 HTTP 直接下载（数据库含密码哈希与 evkey）。
    """
    global _db_path
    if _db_path is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        db_dir = os.path.join(project_root, DB_DIR_NAME)
        os.makedirs(db_dir, exist_ok=True)
        new_path = os.path.join(db_dir, DB_FILE_NAME)
        legacy_path = os.path.join(project_root, DB_FILE_NAME)
        # 一次性迁移：历史版本把数据库放在项目根目录
        if not os.path.exists(new_path) and os.path.exists(legacy_path):
            try:
                os.replace(legacy_path, new_path)
            except OSError:
                pass
        _db_path = new_path
    return _db_path


def db_file_size():
    """数据库主文件字节数（健康检查用）。不可用/尚未建库时返回 0，且不触发建目录"""
    if _db_disabled:
        return 0
    try:
        path = _get_db_path()
        return os.path.getsize(path) if os.path.exists(path) else 0
    except OSError:
        return 0


def db_path():
    """当前数据库文件路径（备份/恢复用）。停用或路径不可解析时返回空串，且不建目录"""
    if _db_disabled:
        return ''
    try:
        return _get_db_path()
    except OSError:
        return ''


def _connect(readonly=False):
    # 放在最前面：停用时连路径都不解析，保证 Vercel 只读文件系统上零 IO
    if _db_disabled:
        raise DatabaseUnavailable('当前运行模式已禁用 SQLite 数据库')
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if readonly:
        # 不设 journal_mode：那是需要写权限的 PRAGMA，而这条连接只读（而且库的
        # journal 模式已经在文件头里，写连接启动时就设成 WAL 了）。逐条设 query_only
        # 之后，任何写入都会直接报 "attempt to write a readonly database" 而不是静默写进去。
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')
        conn.execute('PRAGMA query_only=1')
        return conn
    # WAL：读不阻塞写。日志中间件每个请求都写 request_logs，DELETE 模式下写会阻塞所有读
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    # 等锁而不是立刻抛 'database is locked'：多实例（各自进程各一条连接）共享同一个库文件时，
    # 一个实例正在写的瞬间另一个实例的写会直接失败；SQLite 默认 busy_timeout=0 即不等。
    # 单实例下本项的代价为零（永不争锁），多实例下则是必需的容错。
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def _close_quiet(conn):
    try:
        conn.close()
    except Exception:
        pass


def _read_pool_limit():
    """只读连接池上限；0 = 不限（项目通用语义），非法值退回默认 4"""
    import config

    try:
        value = int(getattr(config, 'DB_READ_POOL_SIZE', 4) or 0)
    except (TypeError, ValueError):
        return 4
    return value if value > 0 else 0


def _acquire_read():
    """借一条只读连接（优先复用空闲连接；上限内新建；达到上限时等归还）"""
    global _read_in_use

    limit = _read_pool_limit()
    with _read_cond:
        while True:
            if _read_idle:
                conn = _read_idle.pop()
                _read_in_use += 1
                _read_epochs[id(conn)] = _read_epoch
                return conn
            if limit <= 0 or _read_in_use < limit:
                # 先占额度再建连接：否则并发进来的线程会各自看到"未达上限"而一起新建，
                # 上限形同虚设
                _read_in_use += 1
                break
            _read_cond.wait(5)
    # 建连接是 IO，放在锁外做，别让整池等它
    try:
        conn = _connect(readonly=True)
    except Exception:
        with _read_cond:
            _read_in_use -= 1
            _read_cond.notify()
        raise
    with _read_cond:
        _read_epochs[id(conn)] = _read_epoch
    return conn


def _release_read(conn, broken=False):
    """归还只读连接；broken 或跨代（库文件已被替换）的连接直接丢弃

    跨代识别是必需的：备份恢复会把库文件整体换掉，之前借出的连接仍绑定在旧文件上，
    直接塞回池里会让后续查询读到旧库（静默错配，比报错难查）。
    """
    global _read_in_use

    with _read_cond:
        epoch = _read_epochs.pop(id(conn), _read_epoch)
        _read_in_use -= 1
        stale = broken or epoch != _read_epoch
        if not stale:
            _read_idle.append(conn)
        _read_cond.notify()
    if stale:
        _close_quiet(conn)


def _close_read_pool_locked():
    """作废整个只读池（调用方必须已持有 _db_lock）。

    代次 +1 让仍在别处的借用连接归还时自动丢弃；_read_in_use 不能清零——那些借出的
    连接还没回来，清了会让计数永久漂移、上限逐渐失效。
    """
    global _read_epoch

    with _read_cond:
        _read_epoch += 1
        idle = list(_read_idle)
        _read_idle.clear()
    for conn in idle:
        _close_quiet(conn)


def _hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + dk.hex()


def _verify_password(password, stored):
    try:
        salt_hex, dk_hex = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        # 定长比较：`==` 会在第一个不同字节处短路，逐字节泄露前缀信息；
        # compare_digest 全程等时。两侧都是十六进制串，非 ASCII 时它抛 TypeError，
        # 由下面的 except 兜成 False。
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def init_db():
    # 幂等：建表与迁移只在进程内执行一次，避免重复调用产生额外 IO
    global _initialized
    if _initialized:
        return
    conn = _connect()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            max_evkeys INTEGER DEFAULT 3,
            max_devices INTEGER NOT NULL DEFAULT 1,
            max_concurrent_renders INTEGER DEFAULT 5,
            rate_limit_per_minute INTEGER NOT NULL DEFAULT 0,
            quota_limit INTEGER NOT NULL DEFAULT 0,
            quota_period TEXT NOT NULL DEFAULT 'day',
            category TEXT NOT NULL DEFAULT 'user',
            builtin INTEGER NOT NULL DEFAULT 0,
            admin_tabs TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            group_id INTEGER NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS evkeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            evkey TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS group_plugins (
            group_id INTEGER NOT NULL,
            plugin_name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY (group_id, plugin_name),
            FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS group_routes (
            group_id INTEGER NOT NULL,
            route_path TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY (group_id, route_path),
            FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS plugin_states (
            plugin_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS route_states (
            route_path TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS config_overrides (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS plugin_config_overrides (
            plugin_name TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (plugin_name, key)
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            group_ids TEXT DEFAULT '',
            admin_name TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS group_params (
            group_id INTEGER NOT NULL,
            param_key TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY (group_id, param_key),
            FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS account_quotas (
            account_id INTEGER PRIMARY KEY,
            period_start TEXT NOT NULL DEFAULT '',
            used INTEGER NOT NULL DEFAULT 0,
            granted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        -- 设备档案。account_id 为 NULL 表示尚未配对（此时只有配对会话关联它）。
        -- token_hash 只存哈希，与账号密码同口径：库被读走也拿不到可用令牌。
        -- 排期列（schedule_type/interval_seconds/daily_times/cron_expr）只是「用户设的间隔」，
        -- 由 /device/status、/device/image 现算成相对秒数下发；计时器跑在设备上，
        -- next_run_at 仅作诊断字段，不驱动任何服务端任务（见设备接入地基实施方案）。
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            name TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            hw_uid TEXT NOT NULL UNIQUE,
            token_hash TEXT NOT NULL DEFAULT '',
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            palette TEXT NOT NULL DEFAULT 'bw',
            format TEXT NOT NULL DEFAULT 'array',
            firmware TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            timezone TEXT NOT NULL DEFAULT '',
            schedule_type TEXT NOT NULL DEFAULT 'interval',
            interval_seconds INTEGER NOT NULL DEFAULT 300,
            daily_times TEXT NOT NULL DEFAULT '',
            cron_expr TEXT NOT NULL DEFAULT '',
            next_run_at TEXT,
            last_seen_at TEXT,
            last_status TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            last_ip TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        -- 配对会话：设备侧的「待认领」凭据，account_id 落库即代表配对完成。
        -- id 是 pair_id（不透明随机串），pair_code 才是给人看/输入的短码。
        CREATE TABLE IF NOT EXISTS device_pairings (
            id TEXT PRIMARY KEY,
            hw_uid TEXT NOT NULL,
            pair_code TEXT NOT NULL,
            secret_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            account_id INTEGER,
            device_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pair_code ON device_pairings(pair_code, status);
        -- 渲染项：一台设备挂多个「插件 + 路由 + 尺寸 + 参数」，sort_order 即轮播顺序。
        -- cache_key 与 prerender_tasks.cache_key 同构，供以后直接复用成品图。
        CREATE TABLE IF NOT EXISTS device_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            plugin_name TEXT NOT NULL,
            route_path TEXT NOT NULL,
            route_kind TEXT NOT NULL DEFAULT 'view',
            size TEXT NOT NULL DEFAULT '',
            params_json TEXT NOT NULL DEFAULT '{}',
            cache_key TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_devtask_device ON device_tasks(device_id, sort_order);
        -- 设备共享：属主把设备共享给其他账号协作。被共享者可共同编辑设备的设置与渲染项，
        -- 但删除设备 / 改变归属仍只有属主可做（判定在账号面路由层，库里只记「谁共享给了谁」）。
        -- account_id 是**被共享方**；设备属主仍是 devices.account_id。
        CREATE TABLE IF NOT EXISTS device_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE (device_id, account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_device_shares_account ON device_shares(account_id, device_id);
    ''')
    conn.execute("INSERT OR IGNORE INTO user_groups(id, name, description) VALUES(1, 'admin', 'Default admin group')")
    conn.execute("INSERT OR IGNORE INTO user_groups(id, name, description, max_evkeys) VALUES(2, 'Free', 'Default group for self-registered accounts', 5)")
    # Free 组替代内置的 user 组：老库里 id=2 还叫 user 时改名，避免出现两个「默认组」；
    # 已经手动建过 Free 组则不动，注册流程会落到那个组上
    conn.execute(
        "UPDATE user_groups SET name = 'Free', description = 'Default group for self-registered accounts'"
        " WHERE id = 2 AND name = 'user' AND NOT EXISTS (SELECT 1 FROM user_groups WHERE name = 'Free')"
    )

    # 结构迁移全部收敛到 migrations.py（版本表 + 幂等 check），不再在这里写吞异常的
    # ALTER TABLE。存量库只回填版本记录；新库的建表语句已是最新形状，一条 DDL 都不执行。
    migrations.apply_migrations(conn)

    # 内置组不变量（每次启动强制拉回，这两个值不可被面板改写）：
    #   id=1 = 兜底管理组，id=2 = 兜底用户组（删除默认注册组且连带删账号时的落点）。
    conn.execute("UPDATE user_groups SET category = 'admin', builtin = 1 WHERE id = 1")
    conn.execute("UPDATE user_groups SET builtin = 1 WHERE id = 2")
    # 老库与新建的兜底管理组都没有分页配置：补一份全量，避免升级后管理入口整片消失。
    # 只在空串时补，管理员之后自己关掉的分页不会被重新打开。
    from modules.database.groups import ALL_ADMIN_TABS
    conn.execute(
        "UPDATE user_groups SET admin_tabs = ? WHERE id = 1 AND admin_tabs = ''",
        (','.join(ALL_ADMIN_TABS),),
    )

    # 内置试用组：总量额度（trial 周期永不重置），用完即止；额度与 evkey 数管理员可改可删
    conn.execute(
        "INSERT OR IGNORE INTO user_groups(id, name, description, max_evkeys, quota_limit, quota_period) "
        "VALUES(3, 'Try', '试用组：总量额度用完即止', 1, 1000, 'trial')"
    )

    cur = conn.execute("SELECT COUNT(*) FROM accounts WHERE group_id = 1")
    if cur.fetchone()[0] == 0:
        pw = _hash_password('admin123')
        conn.execute(
            "INSERT INTO accounts (name, password, group_id, description, enabled, must_change_password) VALUES ('admin', ?, 1, 'Default administrator', 1, 1)",
            (pw,)
        )

    # uid 回填必须放在建库账号插入之后：首次启动时 admin 就是第 1 个账号，应拿到 10000。
    # 只处理 uid 为空的行（已分配的不重排），起点取现有最大 uid + 1，因此重复启动是幂等的。
    _pending = conn.execute("SELECT id FROM accounts WHERE uid IS NULL ORDER BY id").fetchall()
    if _pending:
        _base = conn.execute("SELECT COALESCE(MAX(uid), 9999) FROM accounts").fetchone()[0]
        for _i, (_aid,) in enumerate(_pending, start=1):
            conn.execute("UPDATE accounts SET uid = ? WHERE id = ?", (_base + _i, _aid))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_uid ON accounts(uid)")
    # 账号名不区分大小写：`name` 上的 UNIQUE 是 BINARY 排序，只挡得住完全相同的写法，
    # 「Admin」与「admin」能同时存在——登录时光看名字无法消歧，注册查重也会误放行。
    # 用 lower(name) 的唯一索引把这条约束落到库上（应用层的查重会被并发绕过）。
    # 老库里若已存在仅大小写不同的重名，建索引会失败：这种库本来就已经有歧义了，
    # 不因为一个索引把服务挡在门外，保持现有应用层校验即可（新库/干净库不会有问题）。
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_name_nocase ON accounts(lower(name))")
    except sqlite3.IntegrityError:
        pass

    # 老库的 `users` 表（accounts/evkeys 之前的那套账号体系）一次性导入。
    # 这不是结构变更、也没有版本可言，所以留在初始化流程里，不进 migrations。
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    has_old_users = cur.fetchone() is not None
    cur = conn.execute("SELECT COUNT(*) as cnt FROM accounts")
    has_accounts = cur.fetchone()[0] > 0

    if has_old_users and not has_accounts:
        conn.executescript('''
            INSERT OR IGNORE INTO accounts (id, name, password, group_id, description, enabled, created_at)
            SELECT id, COALESCE(description, 'User-' || id), '', group_id, '', enabled, created_at FROM users;
            INSERT OR IGNORE INTO evkeys (account_id, evkey, description, enabled, created_at)
            SELECT id, evkey, '', enabled, created_at FROM users;
        ''')

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS server_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS server_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            last_seen TEXT,
            mode TEXT,
            version TEXT
        );
        CREATE TABLE IF NOT EXISTS plugin_stats (
            plugin_name TEXT PRIMARY KEY,
            request_count INTEGER DEFAULT 0,
            first_request TEXT,
            last_request TEXT
        );
        -- 账号维度的长期累计用量：按「天 + 账号 + 插件」聚合，与 plugin_stats 一样由
        -- 后台刷盘线程写入。不靠 request_logs 聚合是因为日志会被 retention 清掉。
        CREATE TABLE IF NOT EXISTS account_stats (
            date TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            plugin_name TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            total_ms REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (date, account_id, plugin_name)
        );
        CREATE INDEX IF NOT EXISTS idx_account_stats_account ON account_stats(account_id, date);
        -- 额度操作流水：发放（grant，amount 可负）/ 手动重置（reset）。自动到期重置不写这里，
        -- 否则每个周期首个请求都要多写一次库。用户控制台与管理端共用这份记录。
        CREATE TABLE IF NOT EXISTS account_quota_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            action TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL DEFAULT 0,
            period TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            admin_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_account_quota_logs_account ON account_quota_logs(account_id, id);
        -- 会员变动记录：用户组升降（含激活码开通、到期自动归位）与有效期增减共用一张表。
        -- 组名与到期日一起冗余存下来：用户组事后可能被删除，只留 id 的话历史记录会变成无字天书。
        CREATE TABLE IF NOT EXISTS account_membership_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            action TEXT NOT NULL DEFAULT '',
            old_group_id INTEGER NOT NULL DEFAULT 0,
            new_group_id INTEGER NOT NULL DEFAULT 0,
            old_group_name TEXT NOT NULL DEFAULT '',
            new_group_name TEXT NOT NULL DEFAULT '',
            old_expires_on TEXT NOT NULL DEFAULT '',
            new_expires_on TEXT NOT NULL DEFAULT '',
            old_fallback_group_id INTEGER NOT NULL DEFAULT 0,
            new_fallback_group_id INTEGER NOT NULL DEFAULT 0,
            old_fallback_name TEXT NOT NULL DEFAULT '',
            new_fallback_name TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            admin_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_account_membership_logs_account
            ON account_membership_logs(account_id, id);
        -- 激活码：注册时填写即进入指定用户组。max_uses 是「可激活账号数」（0 = 不限），
        -- expires_on 是码本身的有效日期，duration_days / fallback_group_id 决定激活出的
        -- 账号多久到期、到期后落到哪个组。核销用一条带条件的原子 UPDATE，避免并发超发。
        CREATE TABLE IF NOT EXISTS activation_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            group_id INTEGER NOT NULL DEFAULT 1,
            max_uses INTEGER NOT NULL DEFAULT 0,
            used_count INTEGER NOT NULL DEFAULT 0,
            expires_on TEXT NOT NULL DEFAULT '',
            duration_days INTEGER NOT NULL DEFAULT 0,
            fallback_group_id INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT '',
            allow_repeat INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_activation_codes_group ON activation_codes(group_id, id);
        -- 激活码使用记录：同一账号同一张码只能生效一次。没有这张表的话，
        -- max_uses = 0（不限次数）的码会被同一个账号反复核销，每次都提示激活成功。
        CREATE TABLE IF NOT EXISTS code_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            code TEXT NOT NULL DEFAULT '',
            redeemed_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (code_id, account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_code_redemptions_account ON code_redemptions(account_id, id);
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            path TEXT,
            method TEXT,
            plugin_name TEXT,
            status_code INTEGER,
            duration_ms REAL,
            evkey TEXT,
            error TEXT,
            account_id INTEGER,
            cache_hit INTEGER NOT NULL DEFAULT 0,
            request_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_request_logs_plugin ON request_logs(plugin_name);
        -- 统计页的窗口聚合走 (timestamp, plugin_name)：既能裁掉窗口外的行，又能直接按插件分组
        CREATE INDEX IF NOT EXISTS idx_request_logs_time_plugin ON request_logs(timestamp, plugin_name);
        -- 按账号过滤/分组的查询（日志列表的账号筛选、统计页的按账号下钻、个人控制台的
        -- 「我的统计」）在以上索引上都用不上，只能全表扫。日志表虽有保留上限兜底，
        -- 但面板按秒轮询会反复触发这几条查询，单独建一条按账号的索引
        CREATE INDEX IF NOT EXISTS idx_request_logs_account ON request_logs(account_id, id);
        CREATE TABLE IF NOT EXISTS evkey_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            account_name TEXT NOT NULL,
            applicant_note TEXT DEFAULT '',
            admin_note TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            group_id INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        -- 配置变更审计：只记管理员（/admin/api/**）的写操作，量小，直接同步落库
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            account_id INTEGER,
            actor TEXT,
            ip TEXT,
            method TEXT,
            path TEXT,
            status_code INTEGER,
            summary TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
        -- 定时预渲染任务：到期后台渲染一次成品图并写入 prerender_cache
        CREATE TABLE IF NOT EXISTS prerender_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            plugin_name TEXT NOT NULL,
            route_path TEXT NOT NULL,
            route_kind TEXT NOT NULL DEFAULT 'view',
            size TEXT DEFAULT '',
            params_json TEXT NOT NULL DEFAULT '{}',
            cache_key TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            schedule_type TEXT NOT NULL DEFAULT 'interval',
            interval_seconds INTEGER NOT NULL DEFAULT 600,
            daily_time TEXT DEFAULT '',
            cron_expr TEXT NOT NULL DEFAULT '',
            cache_ttl_hours INTEGER NOT NULL DEFAULT 0,
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            last_ms REAL,
            run_count INTEGER NOT NULL DEFAULT 0,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        -- 成品缓存：一份与请求参数（旋转/反色/cmode/格式）无关的产物，
        -- 命中时按当次请求现场套用，因此 mime/文件名/格式都不属于这里。
        -- last_hit_at 是寿命回收的唯一依据：光看 rendered_at 会让"任务在跑但没人读"的条目一直续命
        CREATE TABLE IF NOT EXISTS prerender_cache (
            cache_key TEXT PRIMARY KEY,
            task_id INTEGER,
            art_kind TEXT NOT NULL DEFAULT 'p',
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            payload BLOB,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            rendered_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_hit_at TEXT,
            render_ms REAL
        );
        CREATE INDEX IF NOT EXISTS idx_prerender_cache_rendered ON prerender_cache(rendered_at);
    ''')
    conn.commit()
    conn.close()
    _initialized = True


def _row_to_dict(row):
    return dict(row) if row else None


def _rows_to_list(rows):
    return [dict(r) for r in rows]


def _get_conn():
    global _pool_conn
    if _pool_conn is None:
        with _init_lock:
            if _pool_conn is None:
                _pool_conn = _connect()
    return _pool_conn


def _close_pool_locked():
    """关闭池连接（调用方必须已持有 _db_lock）"""
    global _pool_conn
    if _pool_conn is not None:
        try:
            _pool_conn.close()
        except Exception:
            pass
        _pool_conn = None


def set_db_path(path):
    """测试专用：把数据库文件重定向到 path（None = 恢复默认路径解析），返回原路径。

    顺带断开池连接：连接是绑定到具体文件的，换了路径还留着旧连接会让后续读写
    落到原来的库上（静默写错库，比直接报错更难查）。只读池同理。
    """
    global _db_path
    with _db_lock:
        _close_pool_locked()
        _close_read_pool_locked()
        previous = _db_path
        _db_path = path
    return previous


def reset_initialized():
    """测试专用：清掉 init_db 的幂等标记，允许对另一个库重新执行建表与迁移"""
    global _initialized
    _initialized = False


def close_connection():
    """关闭池中的连接，下次使用时重新建立（测试收尾与进程退出用）"""
    with _db_lock:
        _close_pool_locked()
        _close_read_pool_locked()


def _exec(sql, params=(), fetch_one=False, fetch_all=False, commit=False, rowcount=False):
    # 纯查询走只读连接池：WAL 下读不阻塞写，也就没必要再去抢全局写锁——
    # 原先每个请求的鉴权/配额/列表查询都排在同一个 _db_lock 后面，是该模型下的硬瓶颈。
    if (fetch_one or fetch_all) and not commit:
        conn = _acquire_read()
        broken = False
        try:
            cur = conn.execute(sql, params)
            if fetch_one:
                return _row_to_dict(cur.fetchone())
            return _rows_to_list(cur.fetchall())
        except Exception:
            # 连接出了问题（库文件被换、句柄损坏）不能再放回池里复用
            broken = True
            raise
        finally:
            _release_read(conn, broken=broken)

    conn = _get_conn()
    with _db_lock:
        cur = conn.execute(sql, params)
        if commit:
            conn.commit()
        if fetch_one:
            return _row_to_dict(cur.fetchone())
        if fetch_all:
            return _rows_to_list(cur.fetchall())
        if commit:
            # rowcount=True 用于需要知道「删/改了几行」的调用方：DELETE 的 lastrowid
            # 是连接上最近一次插入的 rowid，与本次删除无关，拿它当结果必然错
            return cur.rowcount if rowcount else cur.lastrowid
        return None


def _exec_many(statements):
    """在一个事务里执行多条写语句（statements 为 (sql, params) 序列）。

    逐条 _exec(commit=True) 会让每条都单独提交一次，WAL 下就是一次 fsync；批量写
    （如预渲染命中计数落库）时开销随条数线性增长。同一事务里只需提交一次。
    """
    conn = _get_conn()
    with _db_lock:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()


# 单条大 DELETE 会长时间持有全局锁、卡住所有请求，统一切成小批
_DELETE_BATCH = 5000


def _delete_batched(sql, params):
    """分批执行 DELETE（sql 末尾需带 `LIMIT ?`），返回删除行数。

    清理周期里一次删掉上万行会让写事务长时间占住全局锁，期间所有请求一起卡住；
    切成小批后每批之间释放锁，请求只会短暂让行、不再出现毛刺。
    request_logs 与 audit_logs 的清理共用这一份实现。
    """
    deleted = 0
    conn = _get_conn()
    while True:
        with _db_lock:
            cur = conn.execute(sql, tuple(params) + (_DELETE_BATCH,))
            conn.commit()
            n = cur.rowcount
        deleted += n
        if n < _DELETE_BATCH:
            return deleted