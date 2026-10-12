#--------------------------------图像参数配置----------------------------------#
# 默认旋转角度
DEFAULT_ROTATE = 0
# 默认是否反色
DEFAULT_INVERT = False
# 默认JPEG质量 (0-100)
DEFAULT_JPEG_QUALITY = 100
# 默认WEBP质量 (0-100)
DEFAULT_WEBP_QUALITY = 100
# 默认PNG压缩等级 (0-9, 0=无压缩, 9=最高压缩)
DEFAULT_PNG_COMPRESS_LEVEL = 6
# 默认TIFF压缩方式 (tiff_lzw 无损 / tiff_zlib 无损 / tiff_adobe_deflate 无损 / raw 无压缩)
DEFAULT_TIFF_COMPRESSION = 'tiff_lzw'
# 默认输出格式：jpg / png / bmp / webp / tiff / gif / 数组格式族
# 数组格式族：array（= bwarray，白黑 1bpp）/ bwrarray / bwyarray / bwryarray（2bpp）/ 7carray（3bpp）
DEFAULT_IMAGE_FORMAT = 'jpg'
# 输出格式黑名单，禁止列表中的格式被渲染（节省恶意开销）
IMAGE_FORMAT_BLACKLIST = ['webp', 'tiff', 'gif', 'bmp', 'png']
#-----------------------------------时区配置-----------------------------------#
# 默认时区偏移（小时），如中国为8，印度为5.5，英国为0
DEFAULT_TIMEZONE_OFFSET = 8

#----------------------鉴权系统配置--------------------------------------------#
# 是否启用鉴权。这是基础默认值，实际由 modules/app_core.py 在启动时覆盖：
#   dev 模式强制 False；prod / vercel 模式取环境变量 AUTH_ENABLE（默认开启，设为 0/false/no 可关闭）
AUTH_ENABLE = True
# 鉴权白名单（路径精确匹配或以该字符串为前缀的路径免鉴权）
# 注意 '/' 是精确匹配项：若按前缀匹配会放行所有路径
# 这里只列**真实存在**的路径。静态资源只有 app.mount('/public', ...) 一处挂载，登录 /
# 注册 / 找回密码三个页面真实路径是 /login、/register、/reset-password（见
# modules/register/auth_pages_routes.py）——写不存在的 /static、/pages、/index.html
# 只会让面板上多出几个改了也没用的假开关。
AUTH_WHITELIST = [
    '/',
    '/login',
    '/register',
    '/reset-password',
    '/explore',
    '/healthz',
    '/metrics',
    '/public',
    '/favicon.ico',
    '/admin',
    # 设备面：/device/** 自带 X-Device-Token 鉴权，且不属于任何账号的 evkey，
    # 走全站鉴权中间件会被当成未登录访客直接 401。放行不等于不设防——每条 /device
    # 路由内部都要自己复核令牌与用户组权限（见 modules/device/routes.py）。
    '/device',
]
# evkey 申请是否需要管理员审批（True=需审批，False=自动批准）
EVKEY_APPROVAL_REQUIRED = True

#----------------------缓存系统配置--------------------------------------------#
# 字体缓存最大条目数（LRU，不过期）。只缓存字体，图片不进池。
# 2GB 生产内存下的经验值：插件数 × 每视图字号数
CACHE_MAXSIZE = 64

#----------------------边缘缓存（仅 Vercel）------------------------------------#
# 图像响应的 Vercel CDN 边缘缓存秒数，0 = 关闭。**只在 vercel 模式生效**，本地 dev/prod 不受影响。
# 用 Vercel 独占的 Vercel-CDN-Cache-Control 下发：该头不会被返回给客户端，因此不会
# 触发 ESP32 / 浏览器端的缓存（项目明确不接受设备端缓存机制）。
# 命中边缘缓存时函数不执行，也就不产生鉴权、限流、日志与统计——这是刻意取舍：
# Vercel 侧的 evkey 只为挡住恶意请求，而命中缓存的请求本就不消耗函数算力。
EDGE_CACHE_TTL = 300

#----------------------限流系统配置--------------------------------------------#
# 每 evkey 每分钟最大请求数
RATE_LIMIT_PER_MINUTE = 30
# 每 evkey 每小时最大请求数
RATE_LIMIT_PER_HOUR = 1000
# 是否启用限流
RATE_LIMIT_ENABLE = True
# 限流白名单路径（不参与限流的路径前缀，如静态资源、管理后台）
RATE_LIMIT_WHITELIST = [
    '/login',
    '/register',
    '/reset-password',
    '/explore',
    '/healthz',
    '/metrics',
    '/public',
    '/favicon.ico',
    '/admin',
    # 设备面不走全站按 evkey 的限流（设备没有 evkey），改按 `device:<id>` 与来源 IP
    # 单独计数，见 modules/device/routes.py 与 config.DEVICE_RATE_PER_MINUTE
    '/device',
]
# 限流器内部存储最大条目数
RATE_LIMITER_STORE_MAXSIZE = 10000

#----------------------请求体上限----------------------------------------------#
# 单个请求体的最大字节数（MB），超出直接返回 413、不再往内存里读。原先只有备份上传
# 有自己的上限，其余接口没有：一个超大 POST 就能把进程内存吃掉。0 = 不限。
# 备份上传（/admin/api/backup/restore）不受这一项管辖，由 BACKUP_UPLOAD_MAX_MB 单独负责
# ——它默认 64MB，比这里的默认值松，套上全局上限会把正常大小的备份挡在门外。
# 仅本地部署生效：Vercel 侧请求体由平台自身限制，且该链路不新增功能代码。
MAX_REQUEST_BODY_MB = 8

#----------------------并发控制--------------------------------------------#
# 最大并发渲染数（视图生成是 CPU 密集型操作）
MAX_CONCURRENT_RENDERS = 4
# 单次渲染超过该毫秒数视为偏慢，健康检查里给告警
RENDER_SLOW_MS = 2000
# 渲染并发信号量按账号缓存，超出后淘汰最久未访问的条目（0 = 不限制）
# 正常部署不会到这个量级，它只是防「账号被大量增删 / 轮换」时字典只增不减
RENDER_SEMAPHORE_MAXSIZE = 2000
# 只读数据库连接池上限（0 = 不限）。写路径仍是一条连接 + 全局写锁，这里只管读查询：
# 只读连接带 query_only=1，WAL 下读不阻塞写，因此不再和写操作抢同一把锁。
# 取值按「同时可能有多少个读查询」定，默认 4 覆盖单机常态；调大只在读密集型负载下有意义，
# 每个连接各自占用约几十 KB 内存。
DB_READ_POOL_SIZE = 4

#----------------------持久化统计--------------------------------------------#
# 统计数据刷入数据库间隔（秒）
STATS_FLUSH_INTERVAL = 30
# 请求日志队列最大条目数（超出丢弃）
LOG_QUEUE_MAXSIZE = 5000
# 请求日志保留天数（超过自动清理）
REQUEST_LOG_RETENTION_DAYS = 7
# 日志栈最大条数，超出后淘汰最旧记录（0 = 不限制）
REQUEST_LOG_MAX_ROWS = 10000
# 日志清理间隔（STATS_FLUSH_INTERVAL 的倍数）
LOG_CLEANUP_CYCLES = 20
# 日志导出最大行数
LOG_EXPORT_MAX_ROWS = 10000
# 审计日志最大条数，超出淘汰最旧记录（0=不限）
AUDIT_LOG_MAX_ROWS = 5000

#----------------------Auth 缓存----------------------------------------------#
# 用户查询缓存 TTL（秒）
AUTH_CACHE_TTL = 60
# 用户查询缓存最大条目。按**活跃 evkey 数**取：条目数小于在线设备数时缓存会持续
# 抖动（每次请求都退化成查库），而查库要过全局数据库锁，是这个缓存唯一要防的情况。
# 1000 条对应千台设备的部署规模，单条约几百字节，内存开销可忽略。
AUTH_CACHE_MAXSIZE = 1000

#----------------------登录防撞库----------------------------------------------#
# 是否启用登录失败锁定（公网自托管建议开启）
LOGIN_GUARD_ENABLE = True
# 窗口内连续失败达到该次数即锁定（按账号、按来源 IP 分别计数）
LOGIN_MAX_FAILS = 5
# 失败计数窗口（秒）
LOGIN_WINDOW_SECONDS = 300
# 触发后锁定时长（秒）
LOGIN_LOCK_SECONDS = 600
# 防撞库内存表最大条目数，超出后清理过期项
LOGIN_GUARD_MAXSIZE = 1000

#----------------------反向代理----------------------------------------------#
# 是否信任代理写入的 X-Forwarded-For 作为客户端 IP（默认 False = 只认直连地址）。
#
# 关：伪造该头无效，但挂在反向代理后面时所有客户端都是同一个 IP——限流额度被所有人
#     共用，而且攻击者连续失败 5 次就能把「该 IP」维度的登录锁定打开（见 login_guard），
#     把管理员一起锁在门外。公网 + 反向代理部署建议开启。
# 开：取该头的**最右一跳**（本机代理写入的那一段；Nginx 的 $proxy_add_x_forwarded_for
#     与 Caddy 默认行为都是追加，客户端伪造的值只会在左边，取最左等于白送绕过）。
#     前提是代理确实会追加/覆盖该头，且服务只监听回环或代理网段。
TRUST_PROXY_HEADERS = False

#----------------------定时预渲染----------------------------------------------#
# 是否启用定时预渲染（仅本地 dev/prod 生效；Vercel 无持久存储）
PRERENDER_ENABLE = True
# 调度循环的检查间隔（秒）
PRERENDER_TICK_SECONDS = 10
# 单个任务渲染超时（秒）
PRERENDER_TIMEOUT_SECONDS = 30
# 同时执行的预渲染任务数；默认串行，避免后台渲染抢屏端请求的 CPU
PRERENDER_MAX_CONCURRENCY = 1
# 进程启动后延迟多久开始首轮调度，避开启动期
PRERENDER_STARTUP_GRACE_SECONDS = 30
# 成品图缓存最大条目数与最大总字节数（超出按「最久未被请求」淘汰，0 = 不启用该上限）
# 量纲对齐：产物是 P 模式索引 PNG，实测 hxl 单张仅 1~2KB、照片类 h2xl 也就几百 KB，
# 200 条典型占用在 10MB 量级。所以条数是主闸，体积只作兜底（防超大尺寸/照片类撑爆库），
# 给到 200 条 × 约 320KB 的量级即可；设得过大（如 200MB）等于这条线永不触发。
PRERENDER_CACHE_MAX_ROWS = 200
PRERENDER_CACHE_MAX_MB = 64
# 命中路径的内存成品缓存预算（MB，0 = 关闭）。存的是**已编码好的响应体**，
# 命中一次就从「读 BLOB + 解索引 PNG + 重新编码」降成一次内存查表。
# 32MB 对应默认 jpg（q100 单张约 36KB）约 900 份；一份产物按不同格式/旋转各占一份，
# 条数上限是 PRERENDER_CACHE_MAX_ROWS 的 200 条，因此正常部署根本到不了这个预算。
# 多实例部署时它只作用于本实例（各实例各自缓存、各自淘汰）。
PRERENDER_MEMORY_CACHE_MB = 32
# 任务失败告警 webhook（URL，空 = 关闭）。只在任务状态为 error / invalid 时 POST 一份
# JSON（任务名、插件、路由、状态、错误、耗时、发生时间、实例标识），可对接任意通用
# 接收端（钉钉/飞书/自建网关的转发脚本）。发送失败只打印堆栈，绝不影响调度。
PRERENDER_ALERT_WEBHOOK = ''
# 同一任务重复失败的最小发送间隔（秒）；0 = 每次都发。防止一个坏任务每个周期都刷一条
PRERENDER_ALERT_MIN_INTERVAL = 600

#----------------------设备（ESP32 / ESP8266 墨水屏）----------------------------#
# 计时器跑在设备上：后端只下发「相对秒数 + 下次要请求的 URL」，设备自己睡够再来。
# 因此这里全是**下发间隔的钳制区间**，而不是服务端排期参数——后端不存任务、不主动推送。
# 下限防设备打爆后端（也防配置写成 0 秒变成忙轮询）；上限强制设备定期回连，
# 好让 daily/cron 这类墙上时间排期的漂移被封在一天以内。
DEVICE_MIN_SLEEP_SECONDS = 60
DEVICE_MAX_SLEEP_SECONDS = 21600
# 配对会话有效期（秒）。设备把配对码画在屏上、用户去「我的设备」里输入，10 分钟足够。
DEVICE_PAIR_TTL_SECONDS = 600
# 单个配对会话的配对码最多被输错几次，超限即作废（防 8 位码被暴力枚举）
DEVICE_PAIR_MAX_ATTEMPTS = 5
# 设备面每分钟请求上限，按 `device:<id>` 作用域计数：既不占属主账号的 evkey 配额，
# 也不与同 NAT 下的其他设备共用额度。未鉴权的 register / pair 入口按来源 IP 复用这个上限。
DEVICE_RATE_PER_MINUTE = 20

#----------------------备份与恢复-----------------------------------------------#
# 上传恢复时接受的备份文件大小上限（MB）。整库会被读进内存做校验再落盘，因此必须有上限；
# 正常库到不了这个量级（默认配置下日志保留 7 天 / 上限 1 万条，库通常在几十 MB 内）。
# 0 = 不限制（不建议：一个超大文件就能把进程内存吃掉）。
BACKUP_UPLOAD_MAX_MB = 64
# 备份保留份数：`data/backups/` 最多留几份（按时间从新到旧），超出的自动删除。
# 这个目录只进不出——每次恢复前都会写一份 `einkviews-auto-*.db` 当后悔药，没有别的入口删它，
# 长期运行的机器迟早被吃满磁盘。默认留 30 份（这类快照的价值只在"刚恢复错、要捞回来"的窗口内，
# 30 份足够；管理员自己归档的备份是从浏览器下载到本机的，不在这个目录里，不会被清）。
# 0 = 不限。
BACKUP_KEEP_COUNT = 30
# 备份保留天数：超过这些天的备份自动删除。0 = 不限。
BACKUP_KEEP_DAYS = 0
# 自动备份开关：0 = 关闭（默认），1 = 开启。开启后按 BACKUP_AUTO_TIMES 在配置时区里的
# 每日时刻各做一次整库快照，落到 data/backups/——与手动导出、恢复前的"后悔药"同一目录，
# 共用 BACKUP_KEEP_COUNT / BACKUP_KEEP_DAYS 的保留策略。多实例部署只有 leader 实例执行。
BACKUP_AUTO_ENABLE = 0
# 自动备份的每日时刻（HH:MM，空格或逗号分隔，可写多个，如 '03:30 15:00'）。
# 时刻按面板配置的时区解释，语义与定时预渲染的 daily 排期完全一致；非法值会导致不排期。
BACKUP_AUTO_TIMES = '03:30'

#----------------------插件安装-----------------------------------------------#
# 上传安装插件的 zip 包大小上限（MB）。整个包会被读进内存再解压校验，因此必须有上限。
# 注意这一项脱离全局 MAX_REQUEST_BODY_MB 单独判定（见 app_core._BODY_LIMIT_SKIP_PATHS），
# 否则默认 8MB 的全局上限会把稍大一点的插件包先挡在门外。0 = 不限（不建议）。
PLUGIN_UPLOAD_MAX_MB = 32
# 插件包**解压后**的总体积上限（MB），防 zip bomb。单文件另有 8MB 硬上限、条目数 2000 硬上限，
# 这两个写在 modules/plugins/plugin_install.py 里，不做成配置项。0 = 不限（不建议）。
PLUGIN_UNPACK_MAX_MB = 64

#----------------------框架更新-----------------------------------------------#
# 更新模式：'off' = 不更新（默认）；'download' = 只把远端对象拉回本地备用，工作区不改；
# 'auto' = 到点自动拉取并覆盖框架文件，成功则重启进程。
# 更新范围只含框架与 requirements（见 modules/updater.FRAMEWORK_PATHS），
# plugins/ 与 data/ 永远不动——那是使用方的插件与运行数据，被自动更新覆盖就是事故。
UPDATE_MODE = 'off'
# git 远端名与分支名；分支留空 = 当前所在分支
UPDATE_REMOTE = 'origin'
UPDATE_BRANCH = ''
# 自动更新的每日时刻（HH:MM，空格或逗号分隔，可写多个，如 '04:00 16:00'）。
# 时刻按面板配置的时区解释，语义与 BACKUP_AUTO_TIMES 完全一致；仅在 UPDATE_MODE='auto' 时生效。
UPDATE_AUTO_TIMES = '04:00'

#----------------------进程日志----------------------------------------------#
# 进程日志的文件出口：留空 = 只写 stdout（默认，容器 / systemd 交给 log driver / journald 收）。
# 注意这是**进程侧**日志；请求日志走的是另一条链路——进数据库、由面板查询，不受这里影响。
LOG_FILE = ''
# 单个日志文件的字节上限。0 = 不按大小轮转（文件一直追加）。
LOG_MAX_BYTES = 0
# 轮转时保留的历史文件份数（xxx.log.1、.2 …）。0 = 不留历史，超出即清空当前文件。
LOG_BACKUP_COUNT = 0

#----------------------EVKEY 自助注册------------------------------------------#
# 是否允许用户自行申请 evkey
EVKEY_REGISTRATION_ENABLED = True
# 自助注册（未填写激活码时）默认进入的用户组 id；0 = 用内置的 Free 组。
# 配的组被删除时会自动回落到 Free，不会让注册报外键错误。
# 注意：admin 组（id=1）永远不能被设为默认注册组——那等于让任何注册者直接拿到管理权限，
# 数据库层（groups._valid_register_group）与配置接口都会拒绝。
REGISTER_DEFAULT_GROUP_ID = 0

#----------------------可观测性-------------------------------------------------#
# /metrics 指标出口的访问令牌。留空（默认）= 与 /healthz 同级、完全免鉴权；
# 非空时须带 ?token= 或 Authorization: Bearer <token> 才能取到指标。
# 该端点与 /healthz 一样不查库、不写日志、不吃限流额度，可以放心被监控轮询。
METRICS_TOKEN = ''

#----------------------共享存储（多实例）---------------------------------------#
# Redis 连接串，留空（默认）= 单实例：全部状态走进程内存，行为与未启用共享后端一致。
# 非空时启用跨实例共享——限流计数、登录防撞库落在 Redis，多个实例共用同一份额度。
# 约束：同一套部署必须共用同一个 REDIS_URL 与同一个 SHARED_KEY_PREFIX。
REDIS_URL = ''
# 共享 key 前缀；多套部署共用同一个 Redis 实例时靠它互相隔离
SHARED_KEY_PREFIX = 'einkviews'
# 单例 leader 锁的租约时长（秒），按 1/3 周期续租；仅多实例下用于调度与清理类任务
SHARED_LEADER_TTL_SECONDS = 30
# 跨实例内存态失效（鉴权缓存 / 权限缓存 / 组限额缓存）的轮询周期（秒）：
# 其它实例改了权限后，本实例最长这么久之后失效生效
SHARED_POLL_SECONDS = 5
# 单条 Redis 命令的超时（毫秒），超时即视为不可用
SHARED_TIMEOUT_MS = 200
# 共享后端不可用时是否回落本地内存计数：True（默认）= 本实例继续限流；
# False = 直接放行（不再本地计数）。两者都不会把 Redis 抖动放大成全站 503。
SHARED_FALLBACK_LOCAL = True

#----------------------管理面板 UI----------------------------------------------#
# 管理面板各项数据刷新间隔（秒），仅刷新当前标签页可见的数据
ADMIN_STATS_REFRESH = 15
ADMIN_LOGS_REFRESH = 10
ADMIN_APPS_REFRESH = 30
ADMIN_PLUGINS_REFRESH = 30
ADMIN_STATUS_REFRESH = 10
# 界面语言（面板 / 登录 / 注册 / 找回密码 / 首次改密）：'auto' = 跟随浏览器 Accept-Language，
# 或直接指定 'zh-CN' / 'en'。改完即热生效（config_store 会把库里的值 setattr 回 config）。
# 未迁移的分页正文仍是中文，按 tab 增量迁移，见 modules/i18n/
LANG = 'auto'