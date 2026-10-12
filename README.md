# eInkViews

eInkViews 是为 Open ePaper Link 设计的墨水屏图像渲染与分发服务，基于 FastAPI 构建（全异步），采用插件化架构，使用 Pillow 进行像素级排版与图像生成，面向多尺寸、多色电子纸硬件输出图像。

## 项目定位

这个项目的目标不是通用 Web UI，而是面向墨水屏硬件的渲染和分发中枢。它负责：

- 从插件中获取数据
- 按尺寸和调色板生成图像
- 提供 RESTful API 给设备或其他系统拉取
- 支持 Vercel Serverless 部署

## 运行方式（双入口）

项目有两个入口，职责严格区分，不要混用：

### `run.py` — 本地完整版服务（本地测试与生产共用）

```bash
python -B run.py        # 开发模式（默认）：跳过鉴权，启用缓存和管理面板
python -B run.py -prod  # 生产模式：启用鉴权，其余同 dev
```

包含全部能力：资源缓存、SQLite 数据库（账号/用户组/权限/统计）、请求日志、管理面板 `/admin`。本地测试和自托管生产都用这个入口。

存活探针 `GET /healthz`（**只在本地链路注册**，Vercel 侧没有）返回 `{"success":true,"status":"ok","mode":"dev","version":"26.9.1"}`。它不查库、不渲染、不写请求日志、不占限流额度，也不需要 evkey，专门给 Uptime Kuma / systemd / Docker healthcheck 这类外部监控轮询用——用 `/` 去探活会把 `request_logs` 刷满、还可能被限流。

Prometheus 指标出口 `GET /metrics`（同样只在本地链路注册，Prometheus 文本格式，手写于 `modules/utils/metrics.py`，不引第三方库）与 `/healthz` 同源：免鉴权、不占限流额度、不写请求日志。默认完全公开，配 `METRICS_TOKEN` 后需带 `?token=` 或 `Authorization: Bearer`，否则 403。指标覆盖进程（模式/版本/运行时长/RSS/库大小）、渲染（并发占用/累计/缓存命中/最近与最慢耗时）、插件请求数、限流拒绝数、共享后端与 leader 状态、日志队列、字体缓存、**鉴权缓存命中率**、预渲染缓存。每个请求还会带 `X-Request-ID`（请求头已有则复用）并在响应头回写，错误堆栈前会打一行 `[req=xxx] METHOD PATH STATUS ms`。

数据统一存放在项目根目录 `data/`（目录与数据库文件自动创建）：

```
data/einkviews.db        # SQLite 数据库，启用 WAL 模式
data/einkviews.db-wal    # WAL 日志
data/einkviews.db-shm    # 共享内存索引
```

`data/` **不是静态目录**，数据库不会被 HTTP 下载。不要把它移到 `public/`——`public/**` 会被 `/public` 路由与 Vercel static build 直接对外提供，数据库内含密码哈希与 evkey，放进去等于公开可下载。从旧版本升级时，根目录下的 `einkviews.db` 会在首次启动时自动迁移到 `data/`。

连接固定开三项 PRAGMA：`journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`。前两项是既有要求，第三项是给**多实例共享同一个库文件**用的——SQLite 是单写者模型，默认不等锁，并发写会直接抛 `database is locked`。相应地，多实例时库文件必须在同一台机器上（**禁止 NFS / SMB 等网络文件系统**，WAL 依赖共享内存与文件锁，网络文件系统上会静默损坏）。

备份与恢复两条路：有面板时用面板「备份」页（下载走 SQLite 在线备份接口，一致性快照；上传恢复前会自动把当前库存到 `data/backups/`，而 `data/backups/` 里的每一份历史快照都能单独下载或直接拿去恢复，不必先下载再上传），拿不到面板时用 `sqlite3 data/einkviews.db ".backup 'backup.db'"`——**不要直接 `cp` 主文件**，只拷 `.db` 会丢掉还在 WAL 里的最近提交。

### `app.py` — 专为 Vercel Serverless 服务

`app.py` 仅作为 Vercel 的 ASGI 入口（`create_app(mode='vercel')`），以纯 Serverless 方式运行：

- **不碰 SQLite**：数据库在 `create_app` 阶段就被停用，所有数据库调用直接抛 `DatabaseUnavailable`，连 `data/` 目录都不会创建（对齐 Serverless 只读文件系统）
- **不开缓存**：`modules/cache/cache.py` 被停用，字体每次实时加载，LRU 池一个条目都不写
- **不起后台线程**：无统计刷盘线程、无请求日志中间件、无限流中间件、无管理面板路由
- **首页走边缘**：`vercel.json` 把 `/` 直接指到静态文件 `public/pages/index.html`，该请求完全不经过 Python 函数（零冷启动）。这个文件是「Vercel 静态直出版」——凡是随环境变化的文案/入口，文件里存的都是 **Vercel 版**并用 `<!-- 名字:start -->…<!-- 名字:end -->` 锚点包住，所以静态直出时不会出现指向 `/login` 的死链（`/admin` 路由只在 `run.py` 下存在）。目前有两个锚点：副标题 `env-note`（Vercel 上显示「eInkViews is working on Vercel」，本地显示「eInkViews is working!」）与 footer `admin-entry`（静态文件里为空，本地才注入「登录 / 注册」）；本地 dev/prod 下 `/` 路由按 `template_routes._LOCAL_BLOCKS` 改写这些块
- 鉴权走**单 key**：只需配置环境变量 `EVKEY`，请求带上 `evkey`（请求头或查询参数）即可
- 图像处理全部使用 `io.BytesIO`，禁止本地临时文件写入
- **装的是最小依赖集**：Vercel 构建只装 `requirements.txt`（`@vercel/python` 只认它），里面只有 Serverless 链路真正用得到的库——`cachetools` / `uvicorn` / `PyJWT` / `redis` 都在 `requirements-local.txt`；而且四者都只在真正需要时才被导入（`cachetools` 在字体与鉴权缓存的构建函数内、`uvicorn` 在 `run_core` 函数内、`PyJWT` 在会话签发/校验函数内、`redis` 在配置了 `REDIS_URL` 且建连时），Serverless 侧一律碰不到。这条保证由 `.trae/tests/test_app_smoke.py` 的 `ServerlessEntryTest` 在独立进程里断言（`app.py` 的导入链拿不到 redis / uvicorn / jwt / cachetools / `modules.run_core` / 本地后台线程模块），以后有人加一句模块级可选依赖导入就会红
- 本地调试不要用 `app.py` 启动，也不要把依赖数据库/缓存的功能加进 Vercel 链路

环境变量总表（代码真实读取的全部变量）：

| 环境变量 | 默认值 | 生效范围 | 说明 |
| :--- | :--- | :--- | :--- |
| `EVKEY` | 无 | 全部模式 | 鉴权密钥。未配置时所有需鉴权请求返回 401（fail-closed） |
| `AUTH_ENABLE` | 开启 | `prod` / `vercel` | 设为 `0` / `false` / `no` 关闭鉴权（关闭后接口裸奔，不推荐）；`dev` 强制关闭，不受此变量影响 |
| `PORT` | `5000` | 本地（`run.py`） | 监听端口，固定绑定 `0.0.0.0`；Vercel 由平台注入，无需配置 |
| `JWT_SECRET` | 进程内随机值 | 本地（`run.py`） | 管理面板会话 JWT 的签名密钥（`HS256`）。未配置时每次启动随机生成，重启后旧会话全部失效，启动摘要会显式告警 |
| `JWT_EXPIRY_HOURS` | `24` | 本地（`run.py`） | 管理面板会话有效期（小时） |
| `PYTHONDONTWRITEBYTECODE` | `1` | 本地（`run.py`） | `run.py` 启动时自行设置，禁止生成 `__pycache__` |

Vercel 侧只需配置前两个（`EVKEY` 必填，`AUTH_ENABLE` 可选）：`PORT` 由平台注入，`JWT_SECRET` / `JWT_EXPIRY_HOURS` 只服务于本地管理面板，而 Vercel 模式下没有面板路由，配了也不会被用到。

鉴权流程：白名单路径（`/`、`/public`、`/favicon.ico` 等静态页）免鉴权，其余路径必须带正确的 `evkey`。

## 鉴权说明

| 运行模式 | `AUTH_ENABLE` |
| :--- | :--- |
| `dev`（`python -B run.py`） | 强制 `False`，跳过鉴权（注入 dev 用户），方便本地调试 |
| `prod`（`python -B run.py -prod`） | 默认 `True`，可用环境变量 `AUTH_ENABLE=0` 关闭 |
| `vercel`（`app.py`） | 默认 `True`，可用环境变量 `AUTH_ENABLE=0` 关闭 |

启用鉴权后的校验顺序：数据库用户（账号下的 evkey）→ 环境变量 `EVKEY`。本地模式若数据库里已有账号，则优先按数据库匹配；Vercel 模式不查库，直接比对 `EVKEY` 环境变量。

## 代码结构（关键模块）

| 模块 | 职责 |
| :--- | :--- |
| `modules/app_core.py` | FastAPI 应用组装、插件注册、中间件链（本地模式下只负责编排，持久化细节委托给 lifecycle） |
| `modules/lifecycle.py` | 本地模式的持久化生命周期：建库、加载权限缓存、登记启动会话、统计刷盘、退出收尾 |
| `modules/config_store.py` | 全局配置覆盖的读写：数据库中的覆盖项 ↔ 运行中的 `config` 模块 |
| `modules/database/` | 全部 SQLite 访问（按领域拆分为 core/accounts/groups/access/states/stats/logs/applications/activations/quotas/announcements/membership 子模块，含公共查询函数与权限缓存） |
| `modules/auth/auth.py` | JWT 会话与鉴权流程、鉴权缓存 |
| `modules/cache/cache.py` | 字体 LRU 缓存（图片不进池，`get_image` 只做实时解码） |
| `modules/admin_routes.py` | 管理面板路由聚合层（`router` 加 `/admin` 前缀后 include 各领域子路由） |
| `modules/admin/` | 管理面板 API 按领域拆分：`common`（共享工具）/`status_routes`/`plugin_routes`/`config_routes`/`user_routes`/`announce_routes`（站内信）/`log_routes`/`prerender_routes`/`backup_routes`（整库下载与恢复）/`api_docs_routes`（接口清单，替代 prod 下打不开的 `/docs`）/`auth_routes`/`page_routes`/`tab_access`（后台分页 → 管理接口映射，供管理组分页级授权）；只做参数校验与响应组装，SQL 一律下沉到 database |
| `modules/shared/` | 跨实例共享状态（**仅在配置 `REDIS_URL` 时启用**）：`backend.py`（统一接口 + `get_backend()`，Redis 不可用即回落 `memory`）/`memory.py`（默认单实例实现）/`redis_backend.py`（滑动窗口与防撞库合到一次 Lua 往返、失败自动降级）/`leader.py`（单例租约，多实例下只有 leader 做调度与集群级清理）/`events.py`（版本号轮询广播内存态失效） |
| `modules/plugins/` | 插件子系统：`plugin_loader`（扫描 `plugins/` 并注册路由、热重载）/`manifest`（`plugin.json` 解析与依赖排序）/`plugin_install`（上传 zip 包的校验与原子安装 / 卸载，纯逻辑、不依赖 FastAPI） |
| `modules/utils/metrics.py` | Prometheus 文本出口 `/metrics`（手写，不引第三方库；只读内存里已有的计数，每段各自兜底） |
| `modules/utils/route_walk.py` | 展开 FastAPI 惰性 include 的路由（`include_router` 不再把子路由摊平到 `app.router.routes`，`route_walk.iter_routes()` 负责递归展开） |
| `modules/utils/timezone.py` | 统一时区与时间戳工具（`utc_now_iso()` 等），其他模块不得自行拼时间字符串 |
| `modules/prerender/` | 定时预渲染：`keying`（缓存键）/`params`（参数解析，与路由共用）/`artifact`（成品编码为索引数组与按 `cmode` 解码）/`store`（任务与成品缓存读写、命中路径、寿命回收）/`runner`（渲染单个任务）/`scheduler`（排期与调度循环，支持固定间隔 / 每日多时刻 / 5 段 cron）/`memcache`（命中路径的内存成品缓存）/`alerts`（任务失败时 POST 通用 JSON webhook） |
| `modules/utils/login_guard.py` | 登录防撞库（未启用共享后端时是进程内内存，按账号与来源 IP 分别计数锁定） |
| `modules/database/audit.py` | 配置变更审计日志（谁在什么时候改过哪个管理接口） |
| `modules/generate_views/render_metrics.py` | 渲染耗时打点（内存，只供健康检查与最近耗时展示） |

约定：所有包的 `__init__.py` 保持为空，实现放在具名子模块中（如 `database/accounts.py`、`auth/auth.py`、`cache/cache.py`），导入时写完整子模块路径。

依赖只有两个文件，判据只有一句「Vercel 上用不用得到」：`requirements.txt`（**Vercel 最小集**，`@vercel/python` 只装这一个：`fastapi` / `httpx` / `Pillow` / `beautifulsoup4` / `qrcode` / `lunar-python`）与 `requirements-local.txt`（本地 / 自托管 / 多实例，以 `-r requirements.txt` 起头，再加 `cachetools`、`uvicorn[standard]`、`PyJWT` 与可选的多实例 `redis`）。用不到就不许进 `requirements.txt`，否则会被打进函数包、白白撑大体积并拖慢冷启动。可选依赖必须可缺席（导入失败能回落）。两个文件的依赖都按当前版本**精确锁定**（`==`）；原先的 `requirements-multi.txt` 已删除，多实例统一用 `requirements-local.txt`。

## 测试

```bash
python -B -m unittest discover -s .trae/tests
```

只用标准库 `unittest`（不引入项目依赖之外的第三方库）。`.trae/tests/test_core_logic.py` 是纯逻辑用例（限流滑动窗口、配置值解析、权限默认放行），零副作用；`.trae/tests/test_app_smoke.py` 用 **dev 模式**建 app 覆盖 run 端链路（`/healthz`、`/metrics`、插件热重载），并把数据库重定向到临时目录，不会碰 `data/einkviews.db`。其余为纯函数用例：分位数边界（`test_percentiles.py`）、预渲染缓存键与后处理参数剔除（`test_prerender_keying.py`）、排期时区换算与落库格式（`test_prerender_schedule.py`）、成品索引数组编解码往返与缓存寿命回收（`test_prerender_artifact.py`）、登录防撞库窗口与锁定（`test_login_guard.py`）、后台分页权限映射的全量路由覆盖（`test_admin_tab_access.py`）、共享后端与单例租约/失效广播（`test_shared_backend.py`，用假 Redis 断言命令形状，不依赖真实 Redis）。

## 核心特性

- 插件化架构，支持自动发现与自动注册，支持**热重载**（面板插件页「热重载」按钮 / `POST /admin/api/plugins/reload`）：重扫 `plugins/`、重建路由、清空插件代码缓存，改完插件代码、新增或删除插件目录都不必重启服务
- **插件清单 `plugin.json`**（`plugins/<插件名>/plugin.json`，示例见 `plugins/plugin_template/plugin.json`）：插件元信息的唯一来源，可声明名称、版本、描述、作者、最低框架版本与依赖（其它插件、建议的 Python 包）。加载按依赖顺序进行，框架版本不足、依赖缺失或循环依赖的插件会被跳过并在插件页说明原因；没有清单的插件照旧加载，只标记「未声明清单」，插件表格新增「版本」列，启动摘要会报告「其中未声明清单 M 个」。
- **插件添加 / 卸载**（面板插件页「添加插件」按钮 / `POST /admin/api/plugins/install`、`POST /admin/api/plugins/{name}/uninstall`）：上传 zip 包即完成「校验清单 → 安装到 `plugins/` → 立即热重载」，全程不必重启。zip 支持两种结构（根下就是插件内容，或顶层只有一个插件目录）；校验覆盖包内路径安全（拒绝 `..` / 绝对路径 / 反斜杠 / 盘符）、扩展名白名单（嵌套包与未知类型一律拒收）、条目数 / 单文件大小 / 解压总量 / 压缩比上限、清单合法性（名字、最低框架版本）与源码 UTF-8。同名插件已存在时返回 `409` 并提示「覆盖」，确认后**直接删掉**旧目录再装入（卸载同样不留备份）。安装与卸载共用一把锁串行化；解压中转目录 `plugins/.staging` 是点目录、不会被当成插件扫描，`finally` 里清掉。装成功但 `routes.py` 导入失败时**不回滚**（目录保留），面板弹窗列出具体导入错误
- 多尺寸适配，覆盖横屏和竖屏的常见墨水屏规格
- 多色支持与降级
- 支持旋转、反色和调色板映射
- 支持 Unicode、TrueType 字体和精确排版
- 支持 JSON、HTML 页面和随机视图路由
- 内置鉴权（数据库用户 + EVKey，dev 模式跳过）
- 管理面板 `/admin`（仅 `run.py` 启用时）：插件/路由开关、用户与权限、请求日志、缓存、统计、全局配置、定时预渲染
- 用户组级限额：每分钟请求速率与请求配额。配额有两种模式，**所有用户组都可自由切换**——「按时间周期」（每日/每周/每月/每年，到期自动重置）与「按次总量」（该账号一共就这么多，用完即止、永不重置）。`0` = 不限，按账号独立计数、同账号下多个 evkey 共享；内置 `Try` 试用组即「按次总量」模式（默认 1000 次）。两种模式只作用于配额，evkey 上限/并发/速率不受影响
- **额度发放与重置**（面板账号列表「额度」按钮，`GET/POST /admin/api/accounts/{id}/quota[/grant|/reset]`）：实际额度 = 用户组配额 + 账号级发放额，可一键 `+500 / +1000 / +2000` 或自定义次数（填负数即回收，调整后总额度不得小于 1 次）；发放额记在账号上、**跨周期保留**，按时间周期的账号还可「手动重置」把本周期已用归零（不收回已发放额度）。到期自动重置 = `used` 归零且未用部分不结转（**额度不累加**）。所有人为操作落到 `account_quota_logs`，管理端弹窗与用户控制台「额度记录」卡都能看到（自动重置不入账）
- 普通用户登录后进入 `/login` 对应的个人控制台，可查看自己的额度与额度记录、**权限记录**、插件/路由权限并管理 API Key。个人控制台与管理面板「我的」页**共用同一份卡片与脚本**（`modules/admin_ui/account_page.py`），两边唯一的差别是个人控制台多一张**站内信**卡片（管理端的站内信在概览页）。页头与其余分页统一为左上角「标题 + 一行说明」（`我的` / `账号信息、额度与会员、API Key 与登录密码`），账号名、用户组、UID 三项由第一张「账号信息」卡承载；页面宽度与其余分页一致（1280px）
- **申请中的 evkey 也列在「我的 API Key」里**：开启「EVKey 申请需审批」时，提交完回到列表能看到一行「待生成 / 审批中」（琥珀圆点），由 15 秒轮询自动换成批准后的真 Key，不会出现「提交完看不到任何东西」
- 密码框右侧是**眼睛图标**按钮（内联 SVG，随手型切换「显示 / 隐藏」），登录、注册、首次改密与「我的」页改密四处同一套
- **账号 UID**：每个账号注册时自动分配一个对外编号 `uid`（注册顺序，从 10000 起、不设位宽），面板账号列表展示 UID 并默认按其升序排序（可切换按用户组 / 名字）。**登录可用账号名或 UID**（纯数字一律按 UID 解释），因此账号名不能是纯数字（注册 / 建号 / 改名三处都会拒绝）
- **账号名不区分大小写**：`Admin` 与 `admin` 是同一个账号——登录、查重、改名、防撞库计数全部按同一口径处理，唯一索引建在 `lower(name)` 上，因此不可能存在两个只有大小写不同的账号
- **注册必填邮箱 + 忘记密码**：注册页（`/register`）与「新增账号」弹窗都要求填邮箱（必须含 `@`）——项目没有邮件服务，它只作找回凭据，所以多个账号可以填同一个邮箱。登录页底部「忘记密码」指向 `/reset-password`，填**用户名 + 注册邮箱 + 新密码**，两者同时对得上才允许改密（`POST /admin/api/auth/reset-password`，失败按独立的 `reset:` 维度计入防撞库）；老账号（邮箱为空）需管理员在「编辑账号」里补上邮箱后才能自助找回。**邮箱不占账号列表的列**，只在点开「详情」弹窗时可见
- **站内信卡片可按管理组关闭**：用户组编辑里的「站内信」开关（`user_groups.show_announcement`，默认开）关掉后，该管理组进后台看不到概览页的站内信卡片，相关接口也会拒绝（403）；只影响管理端概览页，普通用户的个人控制台不受影响；内置兜底管理组恒为显示
- evkey 上限按用户组配置：`-1` = 不限、`0` = 禁止创建、`N` = 最多 N 个；**管理组不受此限**（与并发上限一样由服务端折算成「不限」，面板按同一口径显示）
- **用户组类别**：每个用户组有一个类别——`admin`（管理组，能进后台，可访问的分页按 `admin_tabs` 勾选开放）与 `user`（普通用户组，登录后只有个人控制台）。组名（`admin` / `Free`）只是**显示名**，真实类别只在管理面板的用户组列表「标记」列可见（该列同时承载「内置 / 默认注册组」标记与类别两组圆点）。管理组也能进「我的」，也有自己的权限升降记录。新增/编辑组时可选类别，选管理组后可**多选**其能操作的后台分页（「我的」任何身份都可用，不参与勾选）
- **内置兜底组**：系统内置一个不可删除的兜底管理组（`id=1` admin）与一个不可删除的兜底用户组（`id=2` Free），`Try`(id=3) 保持普通可删。内置组**类别与可访问分页固定不可改写**（名称与限额仍可改）——改掉内置管理组的类别会让所有人同时失去后台入口
- **内置兜底管理组整组不可编辑、且无条件最高权限**：它是整个后台的兜底入口，改坏它等于把自己锁在后台外面且没有界面能改回来，所以「权限」与「编辑」按钮直接置灰，`PUT /admin/api/groups/1`、`POST /admin/api/groups/1/permissions|params` 一律 400（「内置管理组拥有全部权限，不可编辑 / 无需配置」），`update_group()` 在库层也直接不写。同时它的插件 / 路由 / 参数规则**不参与判定**（库里即使留着旧数据也忽略），即它永远拥有全部权限。判定是 `builtin` + 类别为管理组一起看——内置普通用户组 Free 仍可自由编辑
- **内置管理账号不可删除、不可编辑**：建库时自动生成的管理组账号（内置管理组里最早创建的那个）在账号列表里删除与编辑按钮双双置灰（提示「内置管理账号不可删除 / 不可编辑」），`DELETE` 与 `PUT /admin/api/accounts/{id}` 也直接返回 400——删掉或改坏它后台就没有兜底的管理入口了。账号名可以随便改，所以判定取「内置管理组里最小的 id」，不按名字认；它自己的密码走「我的 → 修改密码」，不受编辑接口拦截影响
- **删除用户组的三条约束**（`DELETE /admin/api/groups/{id}`，违反一律 400）：
  - ① **内置组不可删除**；普通用户组可自由删除
  - ② 组内还有**激活码开通且未到期**的账号时不可删除——那是用户花激活码换来的限期权限，删组等于单方面终止已售出的时长，提示会带上这类账号数。判定看 `account_membership_logs` 里该账号**最近一条**会员变动是否为 `activate`（且落点就是本组），所以管理员手动提级 / 手动建号进来的账号不算，激活后被管理员手动改过组或到期日的也不再算（口径即「手动提级不算」）
  - ③ 被删的组若正担任**默认注册组**，这个标记随删除的落点走：转移 → 跟着转到目标组；连带删除 → 落到内置兜底用户组。目标组是管理组时不能继承该标记（否则不带激活码注册一次就是管理员）
  - 删除时面板会先询问：**把该组账号转移到另一个用户组**（`?transfer_to=新组id`，返回 `transferred` 数量），或**连同账号一起彻底删除**（不带 `transfer_to`，按外键级联删掉账号与 evkey），还需要输入组名二次确认。该组的激活码会被一并清理、指向它的账号到期回落组归零；**不允许把账号转移到管理组**（转进管理组等于批量授予后台权限）
- **自助注册落组**（`POST /admin/api/auth/register`）：不带激活码时进入「默认注册用户组」——在面板用户组列表点「设为默认」即可切换（底层配置项 `REGISTER_DEFAULT_GROUP_ID`，`0` = 内置 `Free` 组，当前默认组在列表里带蓝色小圆点）。**管理组不能设为默认注册组**（按钮置灰、接口拒绝）。配置的组被删掉时自动回落 `Free`、两者都缺则现场重建，不把组 id 写死——写死会在组被删后撞 `FOREIGN KEY constraint failed`，导致谁都注册不进来
- **权限记录**（面板账号列表「权限记录」按钮 / 用户控制台与面板「我的」页的同名卡片）：一张 `account_membership_logs` 表统管会员属性的四类变动——`set`（管理端改组 / 改到期日 / 改回落组，含批量转移，可填原因）、`activate`（激活码开通）、`expire`（到期自动归位）。记录存变动前后快照（用户组 + 到期日 + 回落组）与操作人、时间，两端都只读；管理端 `GET /admin/api/accounts/{id}/membership-logs`（配合 `PUT /admin/api/accounts/{id}` 改会员属性），用户端只看自己 `GET /admin/api/my/membership-logs`。无变化不写记录
- **激活码**（面板「用户 → 激活码」子标签，与用户组卡片平齐，独立管理）：`GET/POST /admin/api/activation-codes`（列表支持 `?group_id=` / `?status=` 筛选，返回每行的目标用户组与状态）、`PUT/DELETE /admin/api/activation-codes/{id}`。生成时**选择目标用户组**，注册页填入即进入该组（注册页直接填激活码，选填）。可设**可激活账号数**（`0` = 不限、永不销毁；有限次的码用满即销毁）、**有效日期**（留空 = 码永不过期）、**账号有效期**（自激活当日起 N 天，`0` = 永久）、**到期回落组**（到期自动转入该组，留空 = 仅标记过期、不转移）与**「允许同一账号反复激活」开关**（默认关闭）
  - **允许反复激活**（每张码一个开关，生成时勾选、列表里点「重复激活」徽章即可切换）：开启后同一账号可以反复输入这张码，到期日**在现有到期日上叠加**（未用完的天数不丢，已过期则从今天起算；账号当前是永久或首次被限期码激活都从今天起算），**每次激活照常占一个可激活账号名额**——所以设了上限的码会被一个账号自己用光、用满后立即销毁。适合「续费码」场景；关掉开关后该账号最多再激活一次（开启期间的激活没留记录，无从追溯）
  - **生命周期**：生成 → 注册或登录后自助激活即核销 → **用满（有限次码）或过期当场销毁**，面板列表里只留还能用的码（列表接口读到「过期 / 用满」的码也会先清掉，后台扫描周期是分钟级，不靠它兜底）；默认**同一账号对同一张码只能生效一次**，重复输入会明确提示「该激活码你已经使用过了」而不是再报一次激活成功（`max_uses = 0` 的码也不例外）。核销与各项上限判定合成同一条原子 `UPDATE`，并发注册不会超发；建号/落组失败自动归还名额并撤掉核销记录
  - **注册之后也能激活**：登录后在个人控制台「我的会员」卡片输入激活码即可自助升级/续期（`POST /admin/api/my/activation`），页面展示会员到期日与「过期后转入」的用户组名；激活码自身的有效日期不对用户展示。账号到期归位由「启动扫一次 + 后台刷盘线程周期性扫描」完成，不需要定时任务；账号列表带「有效期」列可看到到期日
  - **管理组（类别为 `admin` 的组）不参与激活体系的任何一环**（判定按类别而非组名）：既不能作为码的目标组，也不能作为到期回落组或账号批量转移的目标组（生成入口与两条核销路径一并堵死）——等于把管理权限交给任何拿到码的人
- **定时预渲染（成品图缓存）**：面板「定时」页可对任意视图/JSON 路由建任务，表单与「测试」页同款——只填**请求路径 + 查询参数**，再选排期（**固定间隔**、**每日多个 `HH:MM`**（空格/逗号分隔，按配置时区），或 **5 段 cron 表达式**：分 时 日 月 周，支持 `*` / `n` / `a-b` / `*/n` / `a-b/n` / 逗号列表，非法表达式直接 400）；后台按排期渲染成品字节存入数据库，请求参数完全一致即直接命中，延迟从「渲染耗时」降到「发文件」
  - **产物按索引数组存**（`P` 模式索引 + 调色板，PNG 作容器；调色板超过 256 色时回退 RGB PNG）。因此 `rotate` / `invert` / `cmode` / `format` 一律**不进缓存键**，命中时按当次请求现场套用：`cmode` 是对调色板表的精确重映射，`rotate` / `invert` 是纯几何后处理，所以**同一次渲染能服务于任意 `jpeg` / `png` / `webp` / `tiff` / `gif` / `bmp` 与数组格式族（`array` / `bwrarray` / `7carray` 等）请求**（除非该格式被用户组禁用或框架关闭），不必为每种格式各缓存一份
  - **缓存寿命**：每个任务一个 `cache_ttl_hours`（面板「缓存寿命」），`0` = 不因空闲过期，只由下次任务运行覆盖（项目约定：`0` 代表无限，不填写视同 `0`）。判定看「最后一次被请求」而非「最后一次渲染」——周期重渲会一直刷新渲染时间，只看它则没人读的条目永远死不掉；因此新增 `last_hit_at` 与内存累计命中一起落库，判定用 `COALESCE(last_hit_at, rendered_at)`，回收挂在 `lifecycle.py` 既有周期清理里，不新起线程
  - 面板「定时」页分两张卡片：**定时任务**展示任务列表与总命中/总执行/命中率（`hits / (hits + runs)`，无数据显示 `-`），**成品缓存**展示条目数与占用字节，附「清空缓存」按钮
  - 任务列表只留「任务/排期/命中/执行」四个关键值，路由明细、业务参数、耗时、错误原因与成品信息都在点击任务名打开的**详情弹窗**里。参数解析与路由共用 `modules/prerender/params.py`，默认值变化会让缓存键跟着变，无需额外失效逻辑。命中不经过 Pillow，但仍重跑格式与用户组权限校验；插件/路由被禁用时任务记 `skipped` 且**保留缓存**，插件目录被删才记 `invalid`。仅 `run.py` 本地链路生效（Vercel 无持久存储，整体降级为「没有预渲染」）
  - **失败告警**：任务状态为「失败」或「路由失效」时，向 `PRERENDER_ALERT_WEBHOOK`（留空 = 关闭）POST 一份通用 JSON（含任务名、插件、路由、状态、错误、耗时、发生时间与实例标识）；同一任务在 `PRERENDER_ALERT_MIN_INTERVAL`（默认 600 秒，`0` = 每次都发）内只发一次，发送失败只打印堆栈、不影响调度
- 请求日志**双重上限**：既按 `REQUEST_LOG_RETENTION_DAYS` 按天清理，也按 `REQUEST_LOG_MAX_ROWS` 限制总条数（超出淘汰最旧），队列溢出丢弃的条数在日志页可见，不再无声丢日志
- 每路由渲染耗时 **p50/p95 与最慢路由榜**（统计页），按 `request_logs.cache_hit` 排除预渲染命中，避免命中把分位整体拉低
- 健康检查除基础设施外还包含**渲染维度**（信号量占用、最近一次渲染耗时），`/admin/api/status` 的结果带短 TTL 缓存，面板轮询不会每次重做 `disk_usage` 等真开销
- **登录防撞库**：同一账号或同一来源 IP 连续失败到阈值（默认 5 次 / 5 分钟）即锁定一段时间（默认 10 分钟），阈值与时长可在面板调整；账号维度按**小写账号名**归一，换大小写重试不会另开一份计数。密码找回也走同一套（独立的 `reset:` 维度）
- **配置变更审计**：管理接口的写操作（谁、何时、改了哪个接口、结果如何）记入 `audit_logs`，可在面板日志页查看与清空
- **可观测性**：`GET /metrics`（Prometheus 文本，免鉴权，可用 `METRICS_TOKEN` 加令牌）+ 每个请求的 `X-Request-ID`（透传或生成、响应头回写、错误日志按 `[req=xxx]` 对齐）。
- **请求体大小上限**：单个请求体超过上限（默认 8MB）直接返回 413，`0` = 不限；仅本地部署生效（Vercel 由平台自身限制）。备份上传与插件包上传另有更宽松的独立上限（`BACKUP_UPLOAD_MAX_MB` 默认 64MB、`PLUGIN_UPLOAD_MAX_MB` 默认 32MB，均 `0` = 不限），不受这一项影响；插件包解压后的总量另受 `PLUGIN_UNPACK_MAX_MB`（默认 64MB）限制。
- **备份与恢复**（面板「备份」页）：`GET /admin/api/backup/download` 走 SQLite 在线备份接口导出**一致性快照**，`POST /admin/api/backup/restore` 上传整库替换（先校验魔数 / `integrity_check` / 关键表，替换前自动把当前库存到 `data/backups/`，成功后重建全部内存态并让所有登录态失效）。上传上限 `BACKUP_UPLOAD_MAX_MB`（默认 64，`0` = 不限；带 `Content-Length` 时先看长度再读 body，不必等整个文件进内存）。`data/backups/` 只进不出（每次恢复前留一份后悔药），所以有保留策略兜底：`GET /admin/api/backup/info` 返回快照列表与占用，`DELETE /admin/api/backup/files/{name}` 删单份，`POST /admin/api/backup/cleanup` 按 `BACKUP_KEEP_COUNT`（默认 30 份）/ `BACKUP_KEEP_DAYS`（默认 0 天）立刻清一次，后台每轮也自动兜底清（`0` = 该维度不限）。`data/backups/` 里的每一份快照还能单独下载（`GET /admin/api/backup/files/{name}/download`）或直接用来恢复（`POST /admin/api/backup/files/{name}/restore`，源快照留在原地可反复使用）。
- **自动备份**（面板「备份」页）：可开启每日定时备份并填写时刻（`HH:MM`，空格或逗号分隔可写多个，如 `03:30 15:00`，按面板时区解释）；快照落到 `data/backups/`，与恢复前自动留的「后悔药」同一目录、共用同一保留策略（保留份数默认 30、保留天数默认不限）；面板上的「导出数据库」是直接下载到本机的一次性导出，不落在该目录。多实例部署只有 leader 实例执行，不会重复备份。
- **配置导入 / 导出**（面板「设置」页）：导出为可读 JSON（全局配置项 + 插件配置项 + 各用户组限额 / 配额），可跨实例搬配置、可 diff；导入时校验包结构、只接受本系统认识的配置项，不认识的项与取值非法的项会跳过或拒绝并给出摘要，不会整包失败。与「备份」的分工：备份是整库快照用于回滚，配置导出只含配置、用于迁移与比对。
- **面板可用性**：用户组 / 账号列表带即时搜索框，请求日志可按账号筛选（并显示账号名，CSV 导出跟随筛选），取值固定的配置项（输出格式、格式黑名单、默认旋转角、TIFF 压缩方式）直接给下拉 / 复选候选而不必手打（下拉改成 `onchange` 提交，点开列表时不会误触发保存、来得及选）；下拉与复选框统一成面板自绘的扁平风格（近黑填充），弹窗里堆叠的表单项宽度一致；弹窗带 `role="dialog"` 与焦点陷阱、浮层提示带 `aria-live`，关闭后焦点回到原处。
- **界面语言**（设置 → 管理面板 → 界面语言）：`auto`（默认，跟随浏览器语言）/ `zh-CN` / `en` 三档，改完即生效、无需重启。已全量迁移：面板与用户控制台的全部文案（导航与分页名、按钮、提示与空态、分页条、配置项名称与说明、状态圆点图例）、登录 / 注册 / 找回密码 / 首次改密页，以及接口返回的提示信息都随之切换；界面里不再有硬编码中文，新增文案一律加进 `modules/i18n/` 的两份词条表。
- **接口清单**（面板「测试」页，`GET /admin/api/api-docs`）：自研页面，替代 prod 下被鉴权挡死的 `/docs`，列出全部路由（含插件视图/JSON 路由）、方法与是否需要 evkey。
- **多实例横向扩展**：配置 `REDIS_URL` 后，限流计数、登录防撞库、单例租约与内存态失效广播改走 Redis（`modules/shared/`），可跑多个实例；Redis 不可用会自动回落进程内存并置降级标志（`/metrics` 与面板可见），服务照常出图。**内存态不跨实例**（并发信号量、字体缓存、预渲染内存成品缓存各算各的），且多实例时 SQLite 库文件必须在同一台机器上（禁止网络文件系统）。
- **部署交付件**：仓库 `deploy/` 目录提供 `Dockerfile`、`docker-compose.yml`、`einkviews.service`（systemd）、`nginx.conf` 与 `Caddyfile`，直接拿去部署即可，详见 [`.trae/wiki/部署.md`](.trae/wiki/部署.md)。
- 可直接部署到 Vercel
