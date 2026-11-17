from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body
from modules.cache.cache import stats as cache_stats, clear as cache_clear
from modules.errors.errors import error_response
from modules.i18n.registry import lang_of, t, t_req
from modules.utils.timezone import utc_now_iso

router = APIRouter()

CONFIG_LABELS = {
    'DEFAULT_ROTATE':            {'label':'默认旋转角度','desc':'图片默认旋转角度（0/90/180/270）','category':'图像参数'},
    'DEFAULT_INVERT':            {'label':'默认反色','desc':'True=反色显示, False=正常','category':'图像参数'},
    'DEFAULT_JPEG_QUALITY':      {'label':'JPEG 质量','desc':'0-100，越高越清晰文件越大','category':'图像参数'},
    'DEFAULT_WEBP_QUALITY':      {'label':'WebP 质量','desc':'0-100，越高越清晰文件越大','category':'图像参数'},
    'DEFAULT_PNG_COMPRESS_LEVEL':{'label':'PNG 压缩等级','desc':'0-9，0=无压缩, 9=最高压缩','category':'图像参数'},
    'DEFAULT_TIFF_COMPRESSION':  {'label':'TIFF 压缩方式','desc':'tiff_lzw / tiff_zlib / raw','category':'图像参数'},
    'DEFAULT_IMAGE_FORMAT':      {'label':'默认输出格式','desc':'jpg / png / bmp / webp / tiff / gif','category':'图像参数'},
    'IMAGE_FORMAT_BLACKLIST':    {'label':'输出格式黑名单','desc':'禁止生成的图片格式，节省恶意请求开销','category':'图像参数'},
    'DEFAULT_TIMEZONE_OFFSET':   {'label':'默认时区偏移','desc':'小时，如中国=8，印度=5.5','category':'时区'},
    'AUTH_ENABLE':               {'label':'启用鉴权','desc':'True=启用用户认证, False=跳过鉴权','category':'鉴权'},
    'AUTH_WHITELIST':            {'label':'鉴权白名单','desc':'免鉴权的路径前缀列表','category':'鉴权'},
    'EVKEY_APPROVAL_REQUIRED':   {'label':'EVkey 申请需审批','desc':'True=管理员审批后发放, False=自动批准','category':'鉴权'},
    'CACHE_MAXSIZE':             {'label':'字体缓存条目','desc':'字体缓存（LRU，不过期）最多保留的字号条目数','category':'缓存'},
    'RATE_LIMIT_ENABLE':         {'label':'启用限流','desc':'True=开启请求频率限制','category':'限流'},
    'RATE_LIMIT_PER_MINUTE':     {'label':'每分钟最大请求','desc':'无用户组身份时的兜底：每个 EVkey 每分钟最多请求数','category':'限流'},
    'RATE_LIMIT_PER_HOUR':       {'label':'每小时最大请求','desc':'无用户组身份时的兜底：每个 EVkey 每小时最多请求数','category':'限流'},
    'RATE_LIMIT_WHITELIST':      {'label':'限流白名单','desc':'不参与限流的路径前缀','category':'限流'},
    'RATE_LIMITER_STORE_MAXSIZE':{'label':'限流器存储上限','desc':'限流器内存中最多追踪的 EVkey 数','category':'限流'},
    'MAX_REQUEST_BODY_MB':       {'label':'请求体大小上限','desc':'MB；单个请求体超过该大小直接返回 413，不再读进内存；0=不限。备份上传按自己的「备份上传上限」判定，不适用此项。仅本地部署生效（Vercel 由平台限制）','category':'限流'},
    'MAX_CONCURRENT_RENDERS':    {'label':'最大并发渲染数','desc':'同时渲染视图的上限，CPU密集型；0 = 不限；用户组自身的并发设置优先级高于此项','category':'并发'},
    'RENDER_SEMAPHORE_MAXSIZE':  {'label':'渲染信号量上限','desc':'内存中最多缓存的账号并发信号量数，超出按最久未用淘汰；0 = 不限','category':'并发'},
    'RENDER_SLOW_MS':            {'label':'渲染慢阈值','desc':'单次渲染超过该毫秒数时健康检查给出告警','category':'并发'},
    'DB_READ_POOL_SIZE':         {'label':'只读连接池上限','desc':'只读查询的并发连接数；0 = 不限。写仍为单连接 + 全局锁，此项只影响读查询的并发度','category':'并发'},
    'STATS_FLUSH_INTERVAL':      {'label':'统计刷入间隔','desc':'统计数据写入数据库的间隔秒数','category':'统计'},
    'LOG_QUEUE_MAXSIZE':         {'label':'日志队列上限','desc':'内存中排队等待写入的日志条目数','category':'统计'},
    'REQUEST_LOG_RETENTION_DAYS':{'label':'日志保留天数','desc':'超过天数的日志自动清理','category':'统计'},
    'REQUEST_LOG_MAX_ROWS':      {'label':'日志栈深度','desc':'日志表最大条数，超出淘汰最旧记录（0=不限）','category':'统计'},
    'LOG_CLEANUP_CYCLES':        {'label':'日志清理周期','desc':'STATS_FLUSH_INTERVAL 的倍数','category':'统计'},
    'LOG_EXPORT_MAX_ROWS':       {'label':'日志导出上限','desc':'单次导出最多行数','category':'统计'},
    'AUDIT_LOG_MAX_ROWS':        {'label':'审计保留条数','desc':'审计日志最大条数，超出淘汰最旧记录（0=不限）','category':'统计'},
    'LOG_FILE':                  {'label':'进程日志文件','desc':'进程日志（启动提示/告警/异常堆栈）的文件出口；留空 = 只写 stdout。请求日志进数据库，不受此项影响','category':'统计'},
    'LOG_MAX_BYTES':             {'label':'日志文件上限','desc':'字节；单个进程日志文件超过该大小即轮转；0 = 不按大小轮转（一直追加）','category':'统计'},
    'LOG_BACKUP_COUNT':          {'label':'日志保留份数','desc':'轮转时保留 xxx.log.1 / .2 … 的份数；0 = 不留历史（超出即清空当前文件）','category':'统计'},
    'AUTH_CACHE_TTL':            {'label':'认证缓存 TTL','desc':'用户查询缓存过期秒数','category':'缓存'},
    'AUTH_CACHE_MAXSIZE':        {'label':'认证缓存上限','desc':'认证缓存最大条目数；建议不小于在线设备数（每个活跃 EVkey 一条），偏小会让每个请求都回落到查库','category':'缓存'},
    'LOGIN_GUARD_ENABLE':        {'label':'启用登录防撞库','desc':'True=连续登录失败达阈值后临时锁定','category':'鉴权'},
    'LOGIN_MAX_FAILS':           {'label':'失败次数阈值','desc':'窗口内连续失败达到该次数即锁定（按账号与来源 IP 分别计数）','category':'鉴权'},
    'LOGIN_WINDOW_SECONDS':      {'label':'失败计数窗口','desc':'秒；只统计该时间窗内的失败次数','category':'鉴权'},
    'LOGIN_LOCK_SECONDS':        {'label':'锁定时长','desc':'秒；触发后需等待多久才能再次尝试登录','category':'鉴权'},
    'LOGIN_GUARD_MAXSIZE':       {'label':'防撞库存储上限','desc':'内存中最多追踪的账号/IP 条目数','category':'鉴权'},
    'TRUST_PROXY_HEADERS':       {'label':'信任代理来源 IP','desc':'True=取 X-Forwarded-For 最右一跳（代理后部署必须开，否则所有人共用一份限流额度、还能把管理员一起锁在门外）；False=只认直连地址，伪造头无效','category':'鉴权'},
    'PRERENDER_ENABLE':          {'label':'启用定时预渲染','desc':'False=停止调度，同时不再命中成品图缓存','category':'定时'},
    'PRERENDER_TICK_SECONDS':    {'label':'调度轮询间隔','desc':'秒；调度循环多久检查一次到期任务','category':'定时'},
    'PRERENDER_TIMEOUT_SECONDS': {'label':'单次渲染超时','desc':'秒；超时的任务记为失败并跳过本轮','category':'定时'},
    'PRERENDER_MAX_CONCURRENCY': {'label':'预渲染并发数','desc':'同时渲染的任务数，建议保持 1 以免抢走屏端算力','category':'定时'},
    'PRERENDER_STARTUP_GRACE_SECONDS':{'label':'启动宽限','desc':'秒；进程启动后延迟多久开始首轮调度','category':'定时'},
    'PRERENDER_CACHE_MAX_ROWS':  {'label':'成品图最大条数','desc':'超出后淘汰最旧的成品图（0=不限）','category':'定时'},
    'PRERENDER_CACHE_MAX_MB':    {'label':'成品图最大体积','desc':'MB，超出后从最旧的开始淘汰（0=不限）','category':'定时'},
    'PRERENDER_MEMORY_CACHE_MB': {'label':'命中内存缓存预算','desc':'MB，缓存已编码好的响应体以免每次命中都重新编码；0=关闭（多实例时各实例独立）','category':'定时'},
    'PRERENDER_ALERT_WEBHOOK':   {'label':'失败告警 Webhook','desc':'任务失败时 POST 一份 JSON 到该地址；留空 = 关闭告警','category':'定时'},
    'PRERENDER_ALERT_MIN_INTERVAL':{'label':'告警最小间隔','desc':'秒；同一任务重复失败在此时长内只发一次，0=每次都发','category':'定时'},
    'EVKEY_REGISTRATION_ENABLED':{'label':'允许自助注册','desc':'True=用户可以自行注册申请 EVkey','category':'鉴权'},
    'REGISTER_DEFAULT_GROUP_ID': {'label':'默认注册用户组','desc':'未填激活码时新注册账号进入的用户组 ID；0=内置 Free 组。建议在「用户组」列表里点「设为默认」修改','category':'鉴权'},
    'METRICS_TOKEN':             {'label':'指标出口令牌','desc':'留空 = /metrics 免鉴权；非空时须带 ?token= 或 Authorization: Bearer','category':'管理面板'},
    'REDIS_URL':                 {'label':'Redis 连接串','desc':'留空 = 单实例（状态全在进程内存）；非空启用多实例共享限流与登录防撞库','category':'共享存储'},
    'SHARED_KEY_PREFIX':         {'label':'共享 key 前缀','desc':'多套部署共用同一个 Redis 时靠它互相隔离，同一套部署内必须一致','category':'共享存储'},
    'SHARED_LEADER_TTL_SECONDS': {'label':'单例锁租约','desc':'秒；多实例下仅 leader 执行调度与清理类任务','category':'共享存储'},
    'SHARED_POLL_SECONDS':       {'label':'失效轮询周期','desc':'秒；跨实例内存态失效（鉴权/权限/限额）的最大生效延迟','category':'共享存储'},
    'SHARED_TIMEOUT_MS':         {'label':'共享命令超时','desc':'毫秒；单条 Redis 命令超时即视为不可用并回落本地','category':'共享存储'},
    'SHARED_FALLBACK_LOCAL':     {'label':'不可用时回落本地','desc':'True=Redis 不可用时本实例继续内存计数；False=直接放行（都不返回 503）','category':'共享存储'},
    'ADMIN_STATS_REFRESH':       {'label':'统计刷新间隔','desc':'管理面板统计页刷新间隔秒数','category':'管理面板'},
    'ADMIN_LOGS_REFRESH':        {'label':'日志刷新间隔','desc':'管理面板日志页刷新间隔秒数','category':'管理面板'},
    'ADMIN_APPS_REFRESH':        {'label':'申请刷新间隔','desc':'管理面板申请列表刷新间隔秒数','category':'管理面板'},
    'ADMIN_PLUGINS_REFRESH':     {'label':'插件刷新间隔','desc':'管理面板插件页刷新间隔秒数','category':'管理面板'},
    'ADMIN_STATUS_REFRESH':      {'label':'概览刷新间隔','desc':'管理面板概览页刷新间隔秒数','category':'管理面板'},
    'LANG':                      {'label':'界面语言','desc':'auto=跟随浏览器 Accept-Language；也可直接指定（zh-CN / en）。面板与用户控制台的全部文案、登录/注册/找回密码/首次改密页，以及接口返回的提示信息都随之切换','category':'管理面板'},
    'BACKUP_UPLOAD_MAX_MB':      {'label':'备份上传上限','desc':'MB；上传恢复的备份文件大小上限，0=不限（不建议，超大文件会把进程内存吃掉）','category':'备份'},
    'BACKUP_KEEP_COUNT':         {'label':'备份保留份数','desc':'data/backups/ 最多留几份（恢复前的自动快照），超出的从最旧开始删；0=不限。目录只进不出，建议留个上限','category':'备份'},
    'BACKUP_KEEP_DAYS':          {'label':'备份保留天数','desc':'超过这些天的备份自动删除；0=不限。与保留份数是"超出任一即删"','category':'备份'},
    'BACKUP_AUTO_ENABLE':        {'label':'启用自动备份','desc':'0=关闭，1=开启。开启后按下面的时刻做整库快照，多实例时只有 leader 执行','category':'备份'},
    'BACKUP_AUTO_TIMES':         {'label':'自动备份时刻','desc':'HH:MM，空格或逗号分隔可写多个（如 03:30 15:00）；按面板配置的时区解释','category':'备份'},
    'UPDATE_MODE':               {'label':'更新模式','desc':'off=不更新；download=仅下载备用；auto=自动更新，成功后重启（只更新框架，不影响插件与数据）','category':'更新'},
    'UPDATE_REMOTE':             {'label':'git 远端名','desc':'默认 origin。更新从该远端拉取','category':'更新'},
    'UPDATE_BRANCH':             {'label':'更新分支','desc':'留空=当前所在分支','category':'更新'},
    'UPDATE_AUTO_TIMES':         {'label':'自动更新时刻','desc':'HH:MM，空格或逗号分隔可写多个（如 04:00 16:00）；按面板配置的时区解释，仅在更新模式为 auto 时生效','category':'更新'},
}

# 分类名 → 稳定 slug：分类名本身是中文（前端拿它分组 / 排序 / 跳过，不能翻），
# 取词时靠它换成 config.cat.<slug>，两种语言共用同一个 slug。
_CATEGORY_SLUGS = {
    '图像参数': 'image',
    '时区': 'timezone',
    '鉴权': 'auth',
    '缓存': 'cache',
    '限流': 'rate_limit',
    '并发': 'concurrency',
    '统计': 'stats',
    '定时': 'prerender',
    '管理面板': 'admin',
    '共享存储': 'shared',
    '备份': 'backup',
    '更新': 'update',
}

def _labels_with_options(lang=None):
    """CONFIG_LABELS + 那些「取值集合固定」项的候选值（面板据此渲染下拉 / 复选）。

    候选一律从代码里现取：输出格式来自 `image_output` 的注册表，不能在面板侧另抄一份
    字面量（注册表加了新格式，抄来的那份会照旧不认）。放在函数里而不是模块级常量，
    是因为它会拉起 PIL，而这份标签只在打开配置页时才需要。

    返回前把 label / desc 覆盖成当前语言的词条；`category` 保持中文原值不动——前端
    拿它分组 / 排序 / 跳过，翻了会把英文界面下的分组逻辑打散，另给 category_label 供显示。
    """
    from modules.generate_views.image_output import supported_formats
    out = {k: dict(v) for k, v in CONFIG_LABELS.items()}
    fmt = supported_formats()
    out['DEFAULT_IMAGE_FORMAT']['options'] = fmt
    out['IMAGE_FORMAT_BLACKLIST']['options'] = fmt
    out['DEFAULT_ROTATE']['options'] = [0, 90, 180, 270]
    out['DEFAULT_TIFF_COMPRESSION']['options'] = ['tiff_lzw', 'tiff_zlib', 'raw']
    # 界面语言：候选来自 i18n 注册表自己（加了语言这里自动多一项，不在面板侧另抄字面量）
    from modules.i18n.registry import SUPPORTED_LANGS
    out['LANG']['options'] = ['auto'] + list(SUPPORTED_LANGS)
    # 更新模式：候选固定三个，与 modules/updater.update_mode 的判定逐字对齐
    out['UPDATE_MODE']['options'] = ['off', 'download', 'auto']
    for key, item in out.items():
        item['label'] = t('config.lbl.' + key, lang)
        item['desc'] = t('config.desc.' + key, lang)
        slug = _CATEGORY_SLUGS.get(item['category'])
        item['category_label'] = t('config.cat.' + slug, lang) if slug else item['category']
    return out


@router.get('/api/config')
async def admin_config(request: Request):
    from modules.database.states import get_config_overrides
    overrides = get_config_overrides()
    defaults = {}
    try:
        import config as cfg
        for k, v in vars(cfg).items():
            if k.isupper() and not k.startswith('_'):
                if isinstance(v, (str, int, float, bool, list)):
                    defaults[k] = v
    except: pass
    return JSONResponse({'overrides': overrides, 'defaults': defaults,
                         'labels': _labels_with_options(lang_of(request))})

def _validate_config_value(key, value, lang=None):
    """配置项取值的服务端校验。返回 (错误文案, 状态码)，None 表示放行。

    面板是唯一入口，但校验必须落在服务端：前端只管渲染，绕过前端直接 POST 一样能写库。
    返回文案而不是现成的响应对象：单条保存要把它包成错误响应，导入要把它并进逐项报告，
    两条路径共用同一份判定（导入侧不该另写一套「哪些键不许写」的规则）。
    """
    from modules import config_store
    if key == 'AUTH_ENABLE' and config_store.get_mode() != 'dev':
        # 非本地模式（prod / vercel）的 AUTH_ENABLE 归环境变量独占，写库不会生效
        # （config_store.enforce_mode_constraints 会覆盖回来）。放任保存等于给管理员
        # 一个「点了没反应」的假开关，所以直接拒绝并说明真正的入口。
        return (t('config.err_auth_env', lang), 400)
    if key == 'REGISTER_DEFAULT_GROUP_ID':
        from modules.database.groups import get_group, is_admin_category
        try:
            gid = int(value or 0)
        except (TypeError, ValueError):
            return (t('config.err_group_id', lang), 400)
        if gid:
            g = get_group(gid)
            if g is None:
                return (t('config.err_group_missing', lang), 404)
            # 默认注册组指向管理组：任何人不带激活码注册一次就成管理员。激活码的三条路径
            # 与组编辑都已堵死管理组，这第四条路径同样要堵（groups.ensure_register_group 有兜底）。
            # 判定看 category 而不是 id：管理组可以被改名，也可以新建。
            if is_admin_category(g.get('category')):
                return (t('config.err_group_admin', lang), 400)
    return None


@router.post('/api/config')
async def admin_save_config(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    key, value = body.get('key'), body.get('value')
    if not key: return error_response(t_req(request, 'msg.missing_field', name='key'), 400)
    if value is not None:
        err = _validate_config_value(key, value, lang_of(request))
        if err is not None:
            return error_response(err[0], err[1])
    from modules.database.states import save_config_override, delete_config_override
    from modules import config_store
    if value is None:
        delete_config_override(key)
        config_store.reload_and_apply()
    else:
        save_config_override(key, value)
        config_store.apply_one(key, value)
    return JSONResponse({'success': True})


@router.post('/api/config/reset-all')
async def admin_reset_config(request: Request):
    """清空全部全局配置覆盖，回到 config.py 的默认值。

    只动 config_overrides 这张表：插件配置覆盖、用户组限额、账号数据都不在「恢复默认
    设置」的语义里，它们各自有独立的入口（插件页 / 用户组页）。删完统一热应用一次，
    避免出现「A 已还原、B 还是旧值」的中间态。
    """
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)

    def _clear():
        from modules.database.states import get_config_overrides, delete_config_override
        keys = list(get_config_overrides().keys())
        for key in keys:
            delete_config_override(key)
        return len(keys)

    removed = await asyncio.to_thread(_clear)
    from modules import config_store
    config_store.reload_and_apply()
    return JSONResponse({'success': True, 'removed': removed})


# ---- 配置导入 / 导出 ----

# 载荷标识与格式版本。导入先认这两个字段，避免把随手一个 JSON（插件自带的配置文件、
# 别家的导出清单）当成配置包灌进库。版本号只在「导入方比导出方新」时拒收：
# 老版本服务读不了新版本多出来的结构，反过来（新服务读老包）是安全的。
CONFIG_SCHEMA = 'einkviews-config'
CONFIG_SCHEMA_VERSION = 1

# 导入允许写回的组字段：只留限额 / 配额这类可重算的运行参数。组名、类别、builtin、
# admin_tabs 一律不进导入——一次误导入就能把某个管理组的分页清空，或把内置组改名，
# 而这几项在面板上本该逐个确认。
_GROUP_IMPORT_FIELDS = ('max_evkeys', 'max_devices', 'max_concurrent_renders',
                        'rate_limit_per_minute', 'quota_limit', 'quota_period')
_GROUP_INT_FIELDS = ('max_evkeys', 'max_devices', 'max_concurrent_renders',
                     'rate_limit_per_minute', 'quota_limit')


def _as_int(value):
    """导入值转 int；bool 与非法值返回 None（True 会被 int() 当成 1，不能放进来）"""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _export_config():
    """配置导出的载荷（同步查库，调用方负责放线程）

    config_overrides 里可能残留已经改名的历史键，导出按 CONFIG_LABELS 过滤：
    导出文件只应包含当前版本真的认识、也真的能导入回来的项。
    """
    from modules.database.states import get_config_overrides, get_all_plugin_config_overrides
    from modules.database.groups import get_all_groups

    version = ''
    try:
        from modules.app_core import FRAMEWORK_VERSION
        version = FRAMEWORK_VERSION
    except Exception:
        pass

    groups = []
    for g in get_all_groups():
        item = {'id': g.get('id'), 'name': g.get('name')}
        for field in _GROUP_IMPORT_FIELDS:
            item[field] = g.get(field)
        groups.append(item)

    overrides = get_config_overrides()
    return {
        'schema': CONFIG_SCHEMA,
        'version': CONFIG_SCHEMA_VERSION,
        'framework_version': version,
        'exported_at': utc_now_iso(),
        'config': {k: v for k, v in overrides.items() if k in CONFIG_LABELS},
        'plugins': get_all_plugin_config_overrides(),
        'groups': groups,
    }


def _import_config(app, payload, lang=None):
    """把导出包写回库（同步，调用方负责放线程）；返回逐项处理结果

    三条判定贯穿始终：**结构对不对**（schema / version）、**这项认不认识**（白名单）、
    **这个值收不收**（复用面板保存时的 _validate_config_value）。认不出的键一律
    落到 skipped 而不是整包拒收——配置包常常是「从新版本的部署导出、导进旧版本」，
    里面混着几项本版本没有的配置是常态，为此整包失败反而更危险（用户会去手改库）。
    """
    result = {
        'config': {'applied': [], 'skipped': [], 'rejected': []},
        'groups': {'applied': 0, 'skipped': [], 'rejected': []},
        'plugins': {'applied': 0, 'skipped': []},
    }

    from modules.database.states import save_config_override, save_plugin_config_override

    # 1) 全局配置项：白名单 = CONFIG_LABELS 登记的键
    incoming = payload.get('config') or {}
    for key, value in incoming.items():
        if key not in CONFIG_LABELS:
            result['config']['skipped'].append(key)
            continue
        err = _validate_config_value(key, value, lang)
        if err is not None:
            result['config']['rejected'].append({'key': key, 'message': err[0]})
            continue
        save_config_override(key, value)
        result['config']['applied'].append(key)

    # 2) 插件配置项：白名单 = 当前真的加载成功的插件 + 该插件 plugin_config.py 里声明过的键
    plugins = payload.get('plugins') or {}
    if plugins:
        import os
        from modules.plugins.plugin_loader import load_plugin_config, clear_plugin_config_cache
        loaded = {p.get('name') for p in
                  getattr(app.state, 'plugin_result', {}).get('plugins', [])}
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        for name, kv in plugins.items():
            if name not in loaded or not isinstance(kv, dict):
                result['plugins']['skipped'].append(name)
                continue
            declared = load_plugin_config(name, os.path.join(project_root, 'plugins', name))
            for key, value in kv.items():
                if key not in declared:
                    result['plugins']['skipped'].append(f'{name}.{key}')
                    continue
                save_plugin_config_override(name, key, value)
                result['plugins']['applied'] += 1
        clear_plugin_config_cache()

    # 3) 用户组的限额 / 配额：按 id 对上号才写，对不上（换了库、组被删过）只报告不改，
    #    绝不新建组——组 id 是关联账号、激活码的外键锚点，凭空造一组比不导入更糟
    from modules.database.groups import get_group, update_group
    from modules.database.quotas import normalize_period
    for item in (payload.get('groups') or []):
        if not isinstance(item, dict):
            result['groups']['rejected'].append({'id': None, 'message': t('config.err_item_not_object', lang)})
            continue
        gid = _as_int(item.get('id'))
        if not gid or get_group(gid) is None:
            result['groups']['skipped'].append(item.get('id'))
            continue
        changes = {}
        bad = None
        for field in _GROUP_IMPORT_FIELDS:
            if field not in item or item[field] is None:
                continue
            if field in _GROUP_INT_FIELDS:
                num = _as_int(item[field])
                if num is None or (field != 'max_evkeys' and num < 0):
                    bad = t('config.err_field_invalid', lang, field=field)
                    break
                changes[field] = num
            else:
                changes[field] = normalize_period(item[field])
        if bad:
            result['groups']['rejected'].append({'id': gid, 'message': bad})
            continue
        if changes:
            update_group(gid, **changes)
            result['groups']['applied'] += 1
    return result


@router.get('/api/config/export')
async def admin_config_export(request: Request):
    """把当前配置导出成可迁移的 JSON（配置覆盖 + 插件配置 + 各组限额）"""
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)
    # 导出要查好几张表，且面板点一次就走一次全量
    payload = await asyncio.to_thread(_export_config)
    return JSONResponse(payload)


@router.post('/api/config/import')
async def admin_config_import(request: Request):
    """导入配置包。结构校验 → 白名单过滤 → 批量写回 → 热应用 → 变更摘要"""
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)
    payload = await _body(request)
    if payload is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    if payload.get('schema') != CONFIG_SCHEMA:
        return error_response(t_req(request, 'config.err_pkg_schema', schema=CONFIG_SCHEMA), 400)
    version = _as_int(payload.get('version'))
    if version is None or version > CONFIG_SCHEMA_VERSION:
        return error_response(t_req(request, 'config.err_pkg_version', version=CONFIG_SCHEMA_VERSION), 400)

    lang = lang_of(request)
    result = await asyncio.to_thread(_import_config, request.app, payload, lang)

    # 热应用：全部覆盖项一起重算，比逐项 apply_one 少一次 config 模块重载，
    # 也不会出现「A 已生效、B 还是旧值」的中间态（_validate_config_value 已挡下
    # 被运行模式独占的键，这里不必再逐项裁定）
    from modules import config_store
    config_store.reload_and_apply()

    applied = len(result['config']['applied'])
    skipped = result['config']['skipped'] + result['plugins']['skipped'] + result['groups']['skipped']
    rejected = result['config']['rejected'] + result['groups']['rejected']
    message = t('config.imported_summary', lang, config=applied,
                plugins=result['plugins']['applied'], groups=result['groups']['applied'])
    if skipped:
        message += t('config.imported_skipped', lang, n=len(skipped))
    if rejected:
        message += t('config.imported_rejected', lang, n=len(rejected))
    return JSONResponse({'success': True, 'message': message, 'result': result})


@router.get('/api/cache')
async def admin_cache():
    return JSONResponse(cache_stats())

@router.post('/api/cache/clear')
async def admin_clear_cache():
    cache_clear()
    return JSONResponse({'success': True})