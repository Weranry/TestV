"""恢复出厂设置用到的数据清理：只删「运行记录」与「插件相关状态」。

账号 / 用户组 / EVkey / 激活码 / 设备注册与配对关系 / 公告都属于账号内容或业务配置，
任何一档清理都不碰；「完整恢复」不在这里逐表删除，而是直接删库文件后重建。

所有删除都走 `_delete_batched`：单条大 DELETE 会长时间占住全局写锁，期间所有请求
一起卡住；分批之间释放锁，请求只短暂让行。
"""
from modules.database.core import _delete_batched

# 运行记录：统计、设备运行痕迹、预渲染任务、已处理的找回密码申请。
# 表名与主键列都是代码里的常量（不接收外部输入），因此可以直接拼进 SQL。
_RUNTIME_TABLES = (
    ('server_sessions', 'id'),
    ('plugin_stats', 'rowid'),
    ('account_stats', 'rowid'),
    ('account_quota_logs', 'id'),
    ('account_membership_logs', 'id'),
    ('notifications', 'id'),
    ('device_telemetry', 'id'),
    ('device_signins', 'id'),
    ('device_tasks', 'id'),
    ('device_idempotency', 'rowid'),
    ('prerender_tasks', 'id'),
)

# 插件相关状态：启用开关、路由开关、插件配置覆盖、用户组插件/路由权限。
# 插件目录本身由 plugins.plugin_install.uninstall_all_plugins 负责删除。
_PLUGIN_TABLES = (
    ('plugin_states', 'rowid'),
    ('route_states', 'rowid'),
    ('plugin_config_overrides', 'rowid'),
    ('group_plugins', 'rowid'),
    ('group_routes', 'rowid'),
)


def _clear_table(table, pk, where=''):
    """按主键/rowid 分批删空一张表，返回删除条数。where 只接受代码里的常量。"""
    clause = f' WHERE {where}' if where else ''
    sql = (f'DELETE FROM {table} WHERE {pk} IN ('
           f'SELECT {pk} FROM {table}{clause} LIMIT ?)')
    return _delete_batched(sql, ())


def clear_plugin_data():
    """清空全部插件相关状态与用户组插件权限，返回 {表名: 删除条数}"""
    return {table: _clear_table(table, pk) for table, pk in _PLUGIN_TABLES}


def clear_runtime_records():
    """清空日志与运行记录，返回 {表名: 删除条数}。

    request_logs / audit_logs 走各自模块里的清理函数（顺带失效统计短缓存）；
    prerender_cache 走 prerender.store.clear_cache（同时清内存成品缓存与探测标志）。
    """
    from modules.database.logs import clear_request_logs, clear_stats_cache
    from modules.database.audit import clear_audit_logs
    from modules.prerender import store as prerender_store

    cleared = {
        'request_logs': clear_request_logs(),
        'audit_logs': clear_audit_logs(),
    }
    for table, pk in _RUNTIME_TABLES:
        cleared[table] = _clear_table(table, pk)
    # 成品图：clear_cache 自己分批删除并清内存缓存，这里只补一个清空前的条数
    cleared['prerender_cache'] = prerender_store.cache_summary().get('rows', 0)
    prerender_store.clear_cache()
    # 已处理的找回密码申请单：待处理的一条都不动（用户还在等管理员处理）
    cleared['password_reset_requests'] = _clear_table(
        'password_reset_requests', 'id', "status != 'pending'")
    clear_stats_cache()
    return cleared
