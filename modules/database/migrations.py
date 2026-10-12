"""数据库结构迁移的唯一入口。

**为什么要有这张表**：原先十余条 `ALTER TABLE ... ADD COLUMN` 全部写成

    try:
        conn.execute("ALTER TABLE x ADD COLUMN y ...")
    except sqlite3.OperationalError:
        pass

「列已存在」和「ALTER 因为别的原因失败」被吞成同一种结果，既看不出当前库是哪一版，
也无法判断某个字段到底补齐了没有。现在每条结构变更登记一个版本号，落在
`schema_migrations` 里，启动时只跑未应用的项并记录结果。

**旧库升级**：存量库里的列是历史上某次启动加上的，版本表里没有记录。迁移的 `check`
就是「这一版的目标状态是否已经成立」——列已存在/表还没有（建表语句自带该列）都算成立，
成立就只补一条版本记录、不重复执行。因此对任意旧库跑一次 init_db 都是幂等的。

**新库**：建表语句已经是最新形状，所有迁移的 check 都成立，只写版本记录、不做任何 DDL。

新增结构变更时**必须**往 MIGRATIONS 末尾追加一条（版本号递增），不得再往 init_db 里
写吞异常的 ALTER —— 这是项目规则。
"""

TABLE = 'schema_migrations'


def _table_exists(conn, table):
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return cur.fetchone() is not None


def _columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _add_column(version, name, table, column, ddl):
    """登记一条「加列」迁移。

    check 的两个分支缺一不可：
    - 表不存在 → 成立。这类表由 init_db 后面的建表语句创建，且建表语句里已经带上了这一列
      （历史上这些 ALTER 写在建表之前，靠 OperationalError 静默跳过）；
    - 列已存在 → 成立。旧库升级时就靠这一条把版本号回填，不重复执行 DDL。
    """

    def check(conn):
        if not _table_exists(conn, table):
            return True
        return column in _columns(conn, table)

    def apply(conn):
        conn.execute(ddl)

    return (version, name, check, apply)


def _add_index(version, name, table, index_name, ddl):
    """登记一条「加索引」迁移。

    check 的两个分支缺一不可（与 _add_column 同理）：
    - 表不存在 → 成立。这类表由 init_db 后半段的建表语句创建，且建表语句里已经带上了
      这个索引；迁移跑在它之前时表还不存在，不能真去 CREATE INDEX；
    - 索引已存在 → 成立。新库与已升级过的库都靠这条把版本号回填，不重复执行 DDL。
    """

    def check(conn):
        if not _table_exists(conn, table):
            return True
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (index_name,))
        return cur.fetchone() is not None

    def apply(conn):
        conn.execute(ddl)

    return (version, name, check, apply)


def _add_table(version, name, table, ddl):
    """登记一条「建表」迁移。

    只有一条分支：表已存在 → 成立。新库的建表语句（init_db）已经带上了这张表，此时只补一条
    版本记录、不重复建；老库没有这张表则真正执行 DDL。
    """

    def check(conn):
        return _table_exists(conn, table)

    def apply(conn):
        conn.execute(ddl)

    return (version, name, check, apply)


def _daily_request_limit_migration(version):
    """旧「每日请求限量」列并入 quota_limit（period='day'），随后删列。

    迁完必须把旧列清零：留着的话，管理员之后把配额改成 0（不限）会在下次启动被这段
    重新写回旧值。删列在旧 SQLite 上会失败，此时列仍在但值已是 0，重跑也不会再改数据。
    """

    def check(conn):
        if not _table_exists(conn, 'user_groups'):
            return True
        return 'daily_request_limit' not in _columns(conn, 'user_groups')

    def apply(conn):
        conn.execute(
            'UPDATE user_groups SET quota_limit = daily_request_limit, daily_request_limit = 0 '
            'WHERE daily_request_limit <> 0'
        )
        try:
            conn.execute('ALTER TABLE user_groups DROP COLUMN daily_request_limit')
        except Exception:
            pass

    return (version, 'user_groups.daily_request_limit → quota_limit', check, apply)


def _prerender_cache_rebuild_migration(version):
    """成品缓存语义变更：payload 从「按格式编码好的成品图」改为「与格式无关的索引数组(P) PNG」。

    旧行无法按新语义解读，只能整表重建（成品可重建，任务下个周期会重新生成）。
    表还不存在（新库）时视为已成立——后面的建表语句直接就是新形状。
    """

    def check(conn):
        if not _table_exists(conn, 'prerender_cache'):
            return True
        return 'art_kind' in _columns(conn, 'prerender_cache')

    def apply(conn):
        conn.execute('DROP TABLE prerender_cache')

    return (version, 'prerender_cache 语义重建（art_kind）', check, apply)


def _derive_device_format_migration(version):
    """设备输出格式改由 palette 推导：把存量设备的 `format` 回填成其调色板对应的 array 格式。

    旧库的 `format` 都是建表默认值 / 硬编码的 `array`，三色、四色、七色设备拿到的格式与
    实际调色板不符（取图会落到错误的位流）。回填幂等：已是目标值的行不动。表还没有
    （全新库，migrations 在建表之后跑，表存在但为空）时视为已成立。
    """

    def _want(palette):
        from modules.generate_views.array_formats import format_for_palette
        return format_for_palette(palette or 'bw') or 'array'

    def check(conn):
        if not _table_exists(conn, 'devices'):
            return True
        for palette, fmt in conn.execute('SELECT palette, format FROM devices'):
            if fmt != _want(palette):
                return False
        return True

    def apply(conn):
        for (palette,) in conn.execute('SELECT DISTINCT palette FROM devices').fetchall():
            conn.execute('UPDATE devices SET format = ? WHERE COALESCE(palette, "") = ?',
                         (_want(palette), palette or ''))

    return (version, 'devices.format 由 palette 推导回填', check, apply)


# 版本号必须递增，且**只追加不修改**（已发布的版本号一旦改动，老库会重复执行或漏执行）。
# 加列迁移按依赖顺序排列：数据迁移必须排在被它引用的列之后。
MIGRATIONS = [
    _add_column(1, 'accounts.password', 'accounts', 'password',
                "ALTER TABLE accounts ADD COLUMN password TEXT NOT NULL DEFAULT ''"),
    _add_column(2, 'accounts.must_change_password', 'accounts', 'must_change_password',
                'ALTER TABLE accounts ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0'),
    # 邮箱：注册时必填，用作「忘记密码」的唯一凭据。默认空串是为了让老库升级后能直接跑，
    # 老账号在面板「编辑」里补上即可（补之前用不了自助找回）。
    _add_column(3, 'accounts.email', 'accounts', 'email',
                "ALTER TABLE accounts ADD COLUMN email TEXT NOT NULL DEFAULT ''"),
    _add_column(4, 'user_groups.max_concurrent_renders', 'user_groups', 'max_concurrent_renders',
                'ALTER TABLE user_groups ADD COLUMN max_concurrent_renders INTEGER NOT NULL DEFAULT 5'),
    # 用户组级限流：0 = 不限制
    _add_column(5, 'user_groups.rate_limit_per_minute', 'user_groups', 'rate_limit_per_minute',
                'ALTER TABLE user_groups ADD COLUMN rate_limit_per_minute INTEGER NOT NULL DEFAULT 0'),
    # 配额模型：原先的「日请求限量」升级为「限额 + 周期」
    _add_column(6, 'user_groups.quota_limit', 'user_groups', 'quota_limit',
                'ALTER TABLE user_groups ADD COLUMN quota_limit INTEGER NOT NULL DEFAULT 0'),
    _add_column(7, 'user_groups.quota_period', 'user_groups', 'quota_period',
                "ALTER TABLE user_groups ADD COLUMN quota_period TEXT NOT NULL DEFAULT 'day'"),
    # 用户组类别：admin = 管理组（可进后台，分页权限见 admin_tabs），user = 普通用户组（只能进「我的」）。
    _add_column(8, 'user_groups.category', 'user_groups', 'category',
                "ALTER TABLE user_groups ADD COLUMN category TEXT NOT NULL DEFAULT 'user'"),
    _add_column(9, 'user_groups.builtin', 'user_groups', 'builtin',
                'ALTER TABLE user_groups ADD COLUMN builtin INTEGER NOT NULL DEFAULT 0'),
    # 管理组可访问的后台分页（逗号分隔的 data-page 值，不含恒可用的 account）。
    _add_column(10, 'user_groups.admin_tabs', 'user_groups', 'admin_tabs',
                "ALTER TABLE user_groups ADD COLUMN admin_tabs TEXT NOT NULL DEFAULT ''"),
    # 管理组是否显示概览页里的站内信卡片：1（默认）= 显示，0 = 隐藏。
    _add_column(11, 'user_groups.show_announcement', 'user_groups', 'show_announcement',
                'ALTER TABLE user_groups ADD COLUMN show_announcement INTEGER NOT NULL DEFAULT 1'),
    # 账号级额外额度池：管理员「发放」的次数累加在这里，实际额度 = 组配额 + granted。
    _add_column(12, 'account_quotas.granted', 'account_quotas', 'granted',
                'ALTER TABLE account_quotas ADD COLUMN granted INTEGER NOT NULL DEFAULT 0'),
    # 激活码开通的账号有效期：'' = 永久有效；YYYY-MM-DD = 到期日（含当天仍有效）。
    _add_column(13, 'accounts.expires_on', 'accounts', 'expires_on',
                "ALTER TABLE accounts ADD COLUMN expires_on TEXT NOT NULL DEFAULT ''"),
    # 到期后的回落组，0 = 不转移（账号留在原组，仅面板标记已过期）。
    # 两列都冗余在账号上：激活码随后可能被删除，账号必须自带完整的到期归属信息。
    _add_column(14, 'accounts.fallback_group_id', 'accounts', 'fallback_group_id',
                'ALTER TABLE accounts ADD COLUMN fallback_group_id INTEGER NOT NULL DEFAULT 0'),
    # 对外编号 uid：注册顺序号，从 10000 起、不设位宽。id 是内部主键（删号会断号且被
    # 外键引用，不能重排），uid 才是对外展示与登录用的编号。存量值由 init_db 按 id 升序回填。
    _add_column(15, 'accounts.uid', 'accounts', 'uid', 'ALTER TABLE accounts ADD COLUMN uid INTEGER'),
    # 激活码开关：0（默认）= 同一账号对同一张码只能生效一次；1 = 允许反复激活（续期语义）。
    _add_column(16, 'activation_codes.allow_repeat', 'activation_codes', 'allow_repeat',
                'ALTER TABLE activation_codes ADD COLUMN allow_repeat INTEGER NOT NULL DEFAULT 0'),
    _daily_request_limit_migration(17),
    _add_column(18, 'evkey_applications.account_id', 'evkey_applications', 'account_id',
                'ALTER TABLE evkey_applications ADD COLUMN account_id INTEGER'),
    # 会话心跳：进程被强杀时用它作为结束时间，否则下次启动才知道要收尾，
    # 会把「已停机但没重启」的那段时间也算进运行时长。
    _add_column(19, 'server_sessions.last_seen', 'server_sessions', 'last_seen',
                'ALTER TABLE server_sessions ADD COLUMN last_seen TEXT'),
    # 请求日志归属账号：用量统计按账号下钻要用，环境变量 EVKEY 鉴权无账号，留 NULL。
    _add_column(20, 'request_logs.account_id', 'request_logs', 'account_id',
                'ALTER TABLE request_logs ADD COLUMN account_id INTEGER'),
    # 是否命中成品图缓存：命中的请求只有 ~1ms，分位聚合要靠这列把它们排除掉。
    _add_column(21, 'request_logs.cache_hit', 'request_logs', 'cache_hit',
                'ALTER TABLE request_logs ADD COLUMN cache_hit INTEGER NOT NULL DEFAULT 0'),
    # 请求 ID：把一次请求的日志、审计与控制台报错串起来（响应头 X-Request-ID 回写同值）。
    _add_column(22, 'request_logs.request_id', 'request_logs', 'request_id',
                'ALTER TABLE request_logs ADD COLUMN request_id TEXT'),
    _prerender_cache_rebuild_migration(23),
    # 缓存寿命：每个任务一个，0 = 不过期（项目约定：0 代表无限，不填写视同 0）。
    _add_column(24, 'prerender_tasks.cache_ttl_hours', 'prerender_tasks', 'cache_ttl_hours',
                'ALTER TABLE prerender_tasks ADD COLUMN cache_ttl_hours INTEGER NOT NULL DEFAULT 0'),
    # Cron 排期表达式（schedule_type='cron' 时生效）：空串 = 该任务不用 cron。
    _add_column(25, 'prerender_tasks.cron_expr', 'prerender_tasks', 'cron_expr',
                "ALTER TABLE prerender_tasks ADD COLUMN cron_expr TEXT NOT NULL DEFAULT ''"),
    # request_logs 按账号查询的索引：加了 account_id 列（第 20 版）之后，日志列表的
    # 账号筛选、统计页的按账号下钻、个人控制台的「我的统计」都按这一列过滤/分组，
    # 而当时建的三个索引（timestamp / plugin_name / (timestamp, plugin_name)）都用不上。
    _add_index(26, 'request_logs 账号索引', 'request_logs', 'idx_request_logs_account',
               'CREATE INDEX IF NOT EXISTS idx_request_logs_account ON request_logs(account_id, id)'),
    # 站内信发送人：历史记录列表要显示「谁发的」，存的是名字快照（不 join accounts，
    # 管理员改名或删号后历史记录仍保持当时的署名）。与 account_quota_logs.admin_name 同口径。
    _add_column(27, 'announcements.admin_name', 'announcements', 'admin_name',
                "ALTER TABLE announcements ADD COLUMN admin_name TEXT NOT NULL DEFAULT ''"),
    # 用户组可挂设备数上限，与 max_evkeys 并列。默认 1 台：普通用户组不该一上来就能绑一堆
    # 设备；内置管理组沿用「全部不限」口径（由读取侧折算，不靠库里的值）。
    _add_column(28, 'user_groups.max_devices', 'user_groups', 'max_devices',
                'ALTER TABLE user_groups ADD COLUMN max_devices INTEGER NOT NULL DEFAULT 1'),
    # 设备共享表：属主把设备共享给其他账号协作（建表语句的形状见 core.py 的 schema 块）。
    # 老库在这里真正建表，新库因建表语句已带此表而只回填版本记录。
    _add_table(29, 'device_shares 建表', 'device_shares', '''CREATE TABLE IF NOT EXISTS device_shares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        UNIQUE (device_id, account_id))'''),
    _add_index(30, 'device_shares 账号索引', 'device_shares', 'idx_device_shares_account',
               'CREATE INDEX IF NOT EXISTS idx_device_shares_account ON device_shares(account_id, device_id)'),
    # 设备输出格式改由 palette 推导（设备只上报支持颜色），回填存量行。
    _derive_device_format_migration(31),
]

LATEST_VERSION = max(item[0] for item in MIGRATIONS)


def apply_migrations(conn):
    """应用所有未登记的迁移，返回 `(本次执行, 版本回填)` 两个版本号列表。

    只跑版本表里没有的项：已登记的跳过（哪怕 check 判定为不成立也不重跑——一旦执行过，
    再执行就不该由框架替管理员决定）。执行前先问 check，成立的只补一条记录。
    """
    conn.execute(
        f'CREATE TABLE IF NOT EXISTS {TABLE} ('
        ' version INTEGER PRIMARY KEY,'
        " name TEXT NOT NULL DEFAULT '',"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    applied = {row[0] for row in conn.execute(f'SELECT version FROM {TABLE}')}
    executed = []
    backfilled = []
    for version, name, check, apply in MIGRATIONS:
        if version in applied:
            continue
        try:
            satisfied = bool(check(conn))
        except Exception:
            # 探测失败（表刚被删、PRAGMA 读不到）一律按"未满足"处理：宁可跑一次幂等的
            # DDL，也不要因为探测异常把一条结构变更静默漏掉
            satisfied = False
        if satisfied:
            backfilled.append(version)
        else:
            apply(conn)
            executed.append(version)
        conn.execute(
            f'INSERT OR REPLACE INTO {TABLE} (version, name) VALUES (?, ?)', (version, name))
    return executed, backfilled


def schema_status():
    """库的 schema 版本信息（面板自检与测试用）；库不可用或尚未建库时版本按 0 报"""
    from modules.database import core

    if not core.is_db_available():
        return {'version': 0, 'latest': LATEST_VERSION, 'up_to_date': True, 'applied': 0}
    try:
        row = core._exec(
            f'SELECT COUNT(*) AS n, COALESCE(MAX(version), 0) AS v FROM {TABLE}', fetch_one=True)
    except Exception:
        return {'version': 0, 'latest': LATEST_VERSION, 'up_to_date': False, 'applied': 0}
    version = int(row['v'] or 0) if row else 0
    count = int(row['n'] or 0) if row else 0
    return {
        'version': version,
        'latest': LATEST_VERSION,
        'applied': count,
        # 版本号等于最新不代表中间没有断层，但断层只可能来自手工改库；
        # 这里按「最新版本已登记」判定，够面板自检用
        'up_to_date': version >= LATEST_VERSION,
    }