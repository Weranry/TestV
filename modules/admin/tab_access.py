"""后台分页 ↔ 管理接口的对应关系。

管理组只能在 admin_tabs 勾选的分页里操作，但「分页」是界面概念、接口是按领域划分的，
所以这里显式登记每个管理接口归属哪些分页。少数接口被多个分页共用（配置项、插件列表、
快速测试），就同时归属多个分页 —— 勾选其中任意一个即可访问。

未登记的路径一律放行：类别（管理组）已在调用前校验过，漏登记一条新接口的后果是
「受限管理组能多调一个接口」，而 fail-closed 的后果是「受限管理组的面板整片 403」——
后者是无人值守的线上故障，前者由 tests 里的路由覆盖断言兜底。
"""
from modules.database.groups import ALL_ADMIN_TABS, ACCOUNT_TAB

# 「所有分页都可用」的标记：配置项被多个页面共用（鉴权配置在用户页、日志配置在日志页、
# 缓存/统计配置在各自页面），按分页切分只会把面板切坏
_SHARED = frozenset(ALL_ADMIN_TABS)

# 路径前缀 → 允许的分页集合。匹配时长前缀优先（'/admin/api/evkeys' 不能被
# '/admin/api/evkey' 抢走，否则兄弟路径会串到同一个分页上）。
TAB_PREFIXES = {
    '/admin/api/accounts': frozenset(('users',)),
    '/admin/api/groups': frozenset(('users',)),
    '/admin/api/activation-codes': frozenset(('users',)),
    '/admin/api/applications': frozenset(('users',)),
    '/admin/api/evkeys': frozenset(('users',)),
    '/admin/api/evkey': frozenset(('users',)),
    # 插件列表同时被用户页的「权限设置」弹窗读取；快速测试在插件页与测试页各有一处入口
    '/admin/api/plugins': frozenset(('plugins', 'users')),
    # 上传安装是插件页独有的管理员级操作（包内代码会以服务进程权限执行），
    # 比上面那条长，靠「长前缀优先」抢在它前面
    '/admin/api/plugins/install': frozenset(('plugins',)),
    '/admin/api/routes': frozenset(('plugins',)),
    '/admin/api/test-route': frozenset(('test', 'plugins')),
    # 接口清单卡片就放在「测试」页，与快速测试同属一个场景
    '/admin/api/api-docs': frozenset(('test',)),
    '/admin/api/status': frozenset(('overview',)),
    '/admin/api/announcements': frozenset(('users',)),
    '/admin/api/request-logs': frozenset(('logs',)),
    '/admin/api/audit-logs': frozenset(('logs',)),
    '/admin/api/statistics': frozenset(('stats',)),
    '/admin/api/stats': frozenset(('stats',)),
    '/admin/api/cache': frozenset(('cache',)),
    '/admin/api/prerender': frozenset(('prerender',)),
    '/admin/api/config': _SHARED,
    # 备份/恢复只在「备份」页：整库替换是不可逆操作，不该跟着共用配置图的 _SHARED 一起放开
    '/admin/api/backup': frozenset(('backup',)),
    # 运行时信息 / 更新 / 重启都挂在「设置」页的「关于」下，与配置项同一个分页
    '/admin/api/runtime': frozenset(('config',)),
    '/admin/api/update': frozenset(('config',)),
    '/admin/api/system': frozenset(('config',)),
}

# 少数接口的归属由**路径后缀**决定：插件名是路径段，写不成固定前缀。
# `/admin/api/plugins/<名字>/uninstall` 必须是「插件」分页独有——前缀表里那条
# `/admin/api/plugins` 是为了让用户页的权限弹窗能读插件列表才共用给 users 的，
# 不能顺带把「卸载」也放给 users。
TAB_SUFFIXES = {
    '/uninstall': frozenset(('plugins',)),
}

# 按长度倒序的前缀表：匹配时先看最长的前缀
_ORDERED_PREFIXES = tuple(
    sorted(TAB_PREFIXES.items(), key=lambda kv: len(kv[0]), reverse=True)
)
_ORDERED_SUFFIXES = tuple(
    sorted(TAB_SUFFIXES.items(), key=lambda kv: len(kv[0]), reverse=True)
)


def tabs_for_path(path):
    """该管理接口归属的分页集合；未登记返回 None（放行）"""
    for suffix, tabs in _ORDERED_SUFFIXES:
        if path.endswith(suffix):
            return tabs
    for prefix, tabs in _ORDERED_PREFIXES:
        if path.startswith(prefix):
            return tabs
    return None


def can_access_path(allowed_tabs, path):
    """allowed_tabs 为 allowed_admin_tabs() 的结果（含恒可用的 'account'）"""
    tabs = tabs_for_path(path)
    if tabs is None:
        return True
    return bool(tabs & set(allowed_tabs))


__all__ = ['TAB_PREFIXES', 'TAB_SUFFIXES', 'tabs_for_path', 'can_access_path', 'ACCOUNT_TAB']
