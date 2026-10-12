import sys
sys.dont_write_bytecode = True

import asyncio
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from modules.plugins.plugin_loader import register_plugins
from modules.errors.errors import register_error_handlers, AuthError, auth_error_handler, error_response
from modules.i18n.registry import t_req
from modules.register.random_view_route import router as random_router
from modules.register.template_routes import router as template_router, health_router, render_index
from modules.auth.auth import check_auth, is_https_request
from modules import config_store
from modules.config_store import apply_overrides
from modules import lifecycle
from modules.utils.timezone import utc_now_iso, now_in_timezone
from modules.utils import plog

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
public_dir = os.path.join(project_root, 'public')

# 不写请求日志的路径前缀（静态资源、管理面板自身、登录/注册/找回密码、访客导航页、探针与指标出口）。
# /metrics 会进这里至关重要：监控按秒轮询，记进 request_logs 就是拿日志表换指标，
# 日志保留期一到还得反复删除——探针与指标本就不该占用业务日志。
# /device 进这里是为了把设备面与插件统计彻底隔开：设备请求的首段路径是 device，
# 若哪天真有个叫 device 的插件被装上，设备心跳就会被记成该插件的请求、污染统计口径。
# 设备侧的在线状态由 devices.last_seen_at / last_status 自己记，不依赖 request_logs。
_LOG_SKIP_PREFIXES = ('/public', '/favicon.ico', '/admin', '/login', '/register',
                      '/reset-password', '/explore', '/healthz', '/metrics', '/device')
_LOCAL_MODES = ('dev', 'prod')

# 请求体上限的放行名单（见 BodyLimitMiddleware）：探针、指标出口与静态资源都没有 body，
# 判它们纯属浪费一次可能上百 MB 的读取。
_BODY_LIMIT_SKIP_PREFIXES = ('/public', '/favicon.ico', '/healthz', '/metrics')
# 备份上传走自己的 BACKUP_UPLOAD_MAX_MB（默认 64MB，比全局上限松），必须从全局上限里豁免，
# 否则默认配置下超过 8MB 的备份上传会被全局中间件以「请求体超过 8 MB 上限」挡掉。
# 插件安装同理，走 PLUGIN_UPLOAD_MAX_MB（默认 32MB）。
_BODY_LIMIT_SKIP_PATHS = ('/admin/api/backup/restore', '/admin/api/plugins/install')

# 框架版本：/healthz 的返回值、FastAPI app.version 与插件清单的 min_framework_version
# 判定共用这一份来源，避免三处各写一个字面量。
FRAMEWORK_VERSION = '26.13.0'

# 未完成初始化时插件路由的拒绝文案（与首页提示同一件事，见 setup_gate_middleware）
_SETUP_MESSAGE = '系统尚未完成初始化：请先在 /login 用初始账号 admin / admin123 登录并立即修改密码'

# 管理后台的 CSP：面板是内联 <style>/<script>/onclick 的单页，不放行 'unsafe-inline'
# 会整片白屏；除此之外不放开任何外部来源。只下发给面板与登录/注册/找回密码/访客导航页
# 这些**同源内联页面**——插件自带的 page/*.html 可能引用任意外部资源，给它们加 CSP 等于把
# 别人的页面弄白。登录页与访客导航页迁/挂在 /login、/explore（不再落在 '/admin' 前缀
# 里），故单独列出。
_ADMIN_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
_CSP_PATH_PREFIXES = ('/admin', '/login', '/register', '/reset-password', '/explore')

# 请求 ID 的字符白名单：它会被原样写回响应头，直接信任请求头等于让调用方能注入响应头内容
_REQUEST_ID_RE = re.compile(r'[^0-9A-Za-z._-]')


def _request_id(request):
    """生成或复用请求 ID。

    上游（网关/调用方）已带 X-Request-ID 时复用，链路上下游才能对上同一次请求；
    否则现场生成一个 16 位十六进制。非法字符一律剔除、长度截断到 64。
    """
    raw = request.headers.get('x-request-id') or ''
    rid = _REQUEST_ID_RE.sub('', raw)[:64]
    return rid or uuid.uuid4().hex[:16]

# 审计：只留痕管理 API 的写方法；敏感字段一律脱敏，摘要截断
_AUDIT_METHODS = ('POST', 'PUT', 'DELETE', 'PATCH')
_AUDIT_BODY_MAX = 4096
_AUDIT_SENSITIVE = ('password', 'token', 'evkey', 'secret')


async def _audit_body_summary(request):
    """管理 API 写操作的请求体摘要（脱敏 + 截断）

    只在确实是 JSON 时才读；返回空串表示"没读到可记的内容"。
    读取发生在 call_next 之前，供中间件后续与响应状态码一起落库：
    BaseHTTPMiddleware 的 _CachedRequest 会把 body 缓存并回放给下游，提前读不影响路由解析
    （注意只能读 body()，改用 stream() 会让下游收到空 body）。

    content-length 只用于"提前拒绝明显超大的请求"，不能作为"是否读 body"的依据：
    分块传输（chunked）没有这个头，按它判断会让这类请求的摘要恒为空，等于没留痕。
    """
    if 'application/json' not in request.headers.get('content-type', '').lower():
        return ''
    try:
        length = int(request.headers.get('content-length') or 0)
    except (TypeError, ValueError):
        length = 0
    if length > _AUDIT_BODY_MAX:
        return '(请求体过大，已省略)'
    try:
        raw = await request.body()
    except Exception:
        return ''
    if len(raw) > _AUDIT_BODY_MAX:
        return '(请求体过大，已省略)'
    if not raw:
        return ''
    try:
        data = json.loads(raw)
    except Exception:
        return ''
    if not isinstance(data, dict):
        return str(data)[:500]
    safe = {}
    for k, v in data.items():
        if any(s in str(k).lower() for s in _AUDIT_SENSITIVE):
            safe[k] = '***'
        else:
            safe[k] = v
    try:
        return json.dumps(safe, ensure_ascii=False)[:500]
    except (TypeError, ValueError):
        return ''


def _write_audit(request, path, status_code, summary):
    """写一条审计记录。审计失败不能影响业务请求，全部兜底"""
    if status_code >= 400:
        return
    try:
        from modules.database.core import is_db_available
        if not is_db_available():
            return
        from modules.database.audit import log_audit
        from modules.utils.client_ip import client_ip
        user = getattr(request.state, 'user', None) or {}
        account_id = user.get('id') if isinstance(user, dict) else None
        actor = user.get('name') if isinstance(user, dict) else None
        ip = client_ip(request)
        log_audit(account_id, actor, ip, request.method, path, status_code, summary)
    except Exception:
        pass

# /admin/api/* 全部落在鉴权白名单的前缀 '/admin' 里，白名单只代表"不校验 evkey"，
# 不代表免授权：管理接口必须校验后台登录态，否则生产模式下任何人都能直接读写后台数据。
# 以下前缀属于登录页/个人控制台自身的接口，由各自函数内部校验身份。
_ADMIN_API_OPEN_PREFIXES = ('/admin/api/auth/', '/admin/api/my/')


def _load_persisted_states(app):
    """恢复插件/路由开关与全局配置覆盖（依赖 register_plugins 先填充 app.state）"""
    from modules.database.states import get_plugin_states, get_route_states

    for name, enabled in get_plugin_states().items():
        if name in app.state.plugin_states:
            app.state.plugin_states[name] = enabled

    for path, enabled in get_route_states().items():
        if enabled:
            app.state.disabled_routes.discard(path)
        else:
            app.state.disabled_routes.add(path)

    apply_overrides()


def _check_admin_api_access(request):
    """管理接口授权检查。返回 JSONResponse 表示拒绝，None 表示放行。

    管理面板只认 Session Cookie（登录态）产生的 request.state.user，不认 evkey：
    面板是浏览器页面，凭据只可能来自登录。

    两道判定：
    1) 身份必须是管理组（category='admin'）——用户组登录后只有「我的」，管理接口一律不放行；
    2) 该接口归属的后台分页必须在这个管理组勾选的范围内（内置兜底管理组恒为全部，
       否则误关一格就再没人能改回来）。
    """
    if getattr(request.app.state, 'mode', '') not in _LOCAL_MODES:
        return None
    path = request.url.path
    if not path.startswith('/admin/api/') or path.startswith(_ADMIN_API_OPEN_PREFIXES):
        return None
    user = getattr(request.state, 'user', None)
    if not user:
        return error_response(t_req(request, 'msg.need_admin_login'), 401)
    from modules.database.groups import allowed_admin_tabs, get_group, is_admin_user
    if not is_admin_user(user):
        return error_response(t_req(request, 'msg.admin_required'), 403)
    from modules.admin.tab_access import can_access_path
    allowed = allowed_admin_tabs(get_group(user.get('group_id')))
    if not can_access_path(allowed, path):
        return error_response(t_req(request, 'msg.no_tab_permission'), 403)
    return None


@asynccontextmanager
async def _lifespan(app):
    """应用启停钩子。

    原先挂在 `@app.on_event('startup'/'shutdown')` 上，那套 API 已被 FastAPI 废弃
    （仅转发到 lifespan，且导入期就开始告警）。调度循环是 asyncio 任务，必须在事件
    循环内创建，因此启动动作只能放在这里，不能提前到 create_app 组装期。
    """
    if app.state.mode in _LOCAL_MODES:
        lifecycle.start_prerender_scheduler(app)
        # 共享存储的后台维护线程（单例租约 + 失效事件轮询）。它必须在调度器之后启动：
        # 首个 tick 就会把 prerender_enabled 改写成本实例是否为 leader。
        lifecycle.start_shared_loop(app)
    yield
    if app.state.mode in _LOCAL_MODES:
        app.state._shutdown = True
        lifecycle.stop_prerender_scheduler(app)
        await lifecycle.stop_shared_loop(app)
        lifecycle.flush_and_close(app)


def create_app(mode='vercel'):
    app = FastAPI(title='eInkViews', version=FRAMEWORK_VERSION, lifespan=_lifespan)
    app.state.mode = mode
    # 按账号缓存、按访问顺序淘汰（见 get_render_semaphore）：用 OrderedDict 而不是普通 dict，
    # 否则删除账号 / 账号反复切换后条目只增不减，是长期运行的隐性内存增长
    app.state.render_semaphores = OrderedDict()
    app.state.account_usage = {}
    # 统计刷盘的基线（见 lifecycle.persist_counters）：本地模式由 setup_persistence 用
    # 库中已有值覆盖，这里的空表只是保证「没建库也能安全调用刷盘」。
    app.state.counts_flushed = {}
    app.state.account_usage_flushed = {}
    app.state._session_id = None
    app.state._shutdown = False
    # 预渲染的 app 级开关：本实例是否**负责调度**预渲染任务（多实例下只有 leader 为真）。
    # 命中成品缓存不看这个标志——非 leader 实例照样要把预渲染出来的图直接返回，
    # 否则预渲染只在 leader 上省事，其它实例全在实时渲染（见 prerender.store.try_serve）。
    app.state.prerender_enabled = False
    # 是否持有共享租约（由 lifecycle.start_shared_loop 的维护线程按周期刷新）
    app.state.is_leader = False

    is_local = mode in _LOCAL_MODES

    import config
    config_store.set_mode(mode)
    # prod / vercel 的 AUTH_ENABLE 由 config_store.enforce_mode_constraints() 统一裁定
    # （环境变量为准、默认开启），这里不再重复设一遍
    config_store.enforce_mode_constraints()

    if is_local:
        lifecycle.setup_persistence(app)
        lifecycle.start_flush_thread(app)
        # 初始化门禁的判定只在这里算一次（见 setup_gate_middleware）：每个请求都查库不值得，
        # 改密接口会在成功后当场重算。读取必须在 setup_persistence（内含 init_db）之后，
        # 否则内置管理账号那行还没插入，第一次启动会被判成「已初始化」。
        from modules.database.accounts import is_setup_required
        app.state.setup_required = is_setup_required()
    else:
        # Vercel Serverless：无持久存储、进程不复用，不碰 SQLite、不开缓存、不起后台线程
        from modules.database.core import set_db_disabled
        from modules.cache.cache import set_enabled as set_cache_enabled
        set_db_disabled(True)
        set_cache_enabled(False)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*'],
    )

    if is_local:
        # 只给 HTML 页面（管理面板 / 登录页 / 个人控制台）加防护头：
        # 防被嵌到别的站点里做点击劫持、防 MIME 嗅探、Referer 不外发给第三方。
        # 图片响应不加：设备直接用 <img> 取图，加了没有收益还可能影响嵌入场景。
        @app.middleware('http')
        async def security_headers_middleware(request: Request, call_next):
            response = await call_next(request)
            if response.headers.get('content-type', '').startswith('text/html'):
                response.headers.setdefault('X-Frame-Options', 'DENY')
                response.headers.setdefault('X-Content-Type-Options', 'nosniff')
                response.headers.setdefault('Referrer-Policy', 'same-origin')
                if request.url.path.startswith(_CSP_PATH_PREFIXES):
                    response.headers.setdefault('Content-Security-Policy', _ADMIN_CSP)
            # HSTS 只在请求确实走 HTTPS 时下发：自托管常见 http://ip:5000 直连，
            # 明文下发会让浏览器把该主机永久锁在 HTTPS，连管理面板都再打不开。
            if is_https_request(request):
                response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
            return response

    # Starlette 的 add_middleware 是 insert(0)，所以**后注册者在最外层、先执行**。
    # 这里按「内层 → 外层」的顺序注册，最终执行顺序（外 → 内）为：
    #   body_limit → gzip → setup_gate → request_log → auth → rate_limit → plugin_disable
    #   → security_headers → CORS
    # auth 必须早于 rate_limit / plugin_disable，否则它们拿不到 request.state.user_group_id，
    # 用户组的限流与插件/路由权限都会失效。
    @app.middleware('http')
    async def plugin_disable_middleware(request: Request, call_next):
        path = request.url.path.strip('/')
        if not path or '/' not in path:
            return await call_next(request)
        plugin_name = path.split('/')[0]

        states = getattr(request.app.state, 'plugin_states', {})
        if plugin_name in states and states[plugin_name] is False:
            return error_response(f'插件 {plugin_name} 已禁用', 503)

        disabled_routes = getattr(request.app.state, 'disabled_routes', set())
        if request.url.path in disabled_routes:
            return error_response(f'路由 {request.url.path} 已禁用', 503)

        user_group_id = getattr(request.state, 'user_group_id', None)
        if user_group_id is not None:
            try:
                from modules.database.access import check_user_plugin_access, check_user_route_access
                plugin_ok = check_user_plugin_access(user_group_id, plugin_name)
                route_ok = plugin_ok and check_user_route_access(user_group_id, request.url.path)
            except Exception:
                # 判定失败必须拒绝（fail-closed）。这里原先是 except + pass，等于把整个
                # 用户组访问控制静默旁路掉：一旦权限缓存/模块导入出问题，所有受限插件与
                # 路由对所有人开放，而且不留任何痕迹。宁可误拒也不放行。
                plog.exception('用户组权限校验失败，已拒绝访问')
                return error_response('权限校验失败，已拒绝访问', 503)
            if not plugin_ok:
                return error_response(f'用户组无权访问插件 {plugin_name}', 403)
            if not route_ok:
                return error_response(f'用户组无权访问路由 {request.url.path}', 403)

        response = await call_next(request)
        if plugin_name in states:
            counts = getattr(request.app.state, 'request_counts', {})
            counts[plugin_name] = counts.get(plugin_name, 0) + 1
        return response

    if is_local:
        @app.middleware('http')
        async def rate_limit_middleware(request: Request, call_next):
            from modules.utils.rate_limiter import rate_limit_middleware as _rlm
            return await _rlm(request, call_next)

    @app.middleware('http')
    async def auth_middleware(request: Request, call_next):
        try:
            await check_auth(request)
            denied = _check_admin_api_access(request)
        except AuthError as exc:
            # 中间件位于 ExceptionMiddleware 外层，异常处理器捕获不到，这里直接返回统一错误体
            return await auth_error_handler(request, exc)
        if denied is not None:
            return denied
        response = await call_next(request)
        if response.headers.get('content-type', '').startswith('application/json'):
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

    if is_local:
        @app.middleware('http')
        async def request_log_middleware(request: Request, call_next):
            start = time.perf_counter()
            path = request.url.path

            # 请求 ID 在 call_next 之前落到 state：下游的路由与异常处理器都要读它
            # （dev 模式的 500 错误体会带上它），运行期抛错时也必须已存在
            request_id = _request_id(request)
            request.state.request_id = request_id

            # 配置变更审计：只盯管理 API 的写操作。摘要必须在 call_next 之前取，
            # 之后 body 流已被下游消费（BaseHTTPMiddleware 的 _CachedRequest 会缓存
            # 并 replay 给下游，因此这里提前读不会影响路由解析）。
            audit_summary = None
            if path.startswith('/admin/api/') and request.method in _AUDIT_METHODS:
                audit_summary = await _audit_body_summary(request)

            response = await call_next(request)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            # 请求 ID 回写响应头：调用方拿着它就能在控制台/日志表里定位这一次请求
            response.headers['X-Request-ID'] = request_id
            if response.status_code >= 400:
                # 与异常处理器打印的堆栈相邻，把一次报错和一个请求 ID 对上。
                # 静态资源/管理面板的 4xx 也打——排查时不需要先去猜它是不是被记录
                plog.warn(f'[req={request_id}] {request.method} {path} '
                          f'{response.status_code} {elapsed_ms}ms')

            # 审计分支要放在 _LOG_SKIP_PREFIXES 提前 return 之前，否则 /admin/api/**
            # 会被跳过（它本来就不需要写请求日志，但写操作必须留痕）
            if audit_summary is not None:
                # 审计是同步 SQLite 写（走全局数据库锁），放 worker 线程执行，
                # 别让一次后台留痕把事件循环占住
                await asyncio.to_thread(
                    _write_audit, request, path, response.status_code, audit_summary)

            if path.startswith(_LOG_SKIP_PREFIXES):
                return response

            try:
                parts = path.strip('/').split('/')
                plugin_name = parts[0] if parts else None

                # 只记录真实插件的请求：/、/openapi.json、/@vite/client、/user 这类
                # 首段不是已加载插件的流量记进来只是噪音，统计口径也与 plugin_stats 不符
                if plugin_name not in getattr(request.app.state, 'plugin_states', {}):
                    return response

                # 这一列存的是「响应信息」（日志页表头也是这个叫法），4xx 也留：
                # 「参数写错 / 没鉴权」的原因对排障有用，但它不参与错误数与错误率——
                # 那两项只认 5xx（见 modules/database/logs.py 的口径说明）
                error = None
                if response.status_code >= 400:
                    body = getattr(response, 'body', b'')
                    if body:
                        try:
                            payload = json.loads(body)
                            error = payload.get('message', '')
                        except (ValueError, TypeError):
                            error = ''
                    if not error:
                        error = str(response.status_code)

                # 落到日志时 auth 中间件已写好 request.state.user；环境变量 EVKEY
                # 鉴权没有账号身份，account_id 记 NULL
                user = getattr(request.state, 'user', None) or {}
                account_id = user.get('id') if isinstance(user, dict) else None

                from modules.database.logs import log_request
                log_request(
                    utc_now_iso(), path, request.method, plugin_name,
                    response.status_code, elapsed_ms,
                    error,
                    account_id,
                    getattr(request.state, 'prerender_hit', False),
                    request_id,
                )

                # 账号维度用量：内存里按天累计，由后台刷盘线程落库到 account_stats。
                # 只统计真实插件的请求，口径与 plugin_stats 保持一致；error_count 与
                # request_logs 同口径，只认 5xx，4xx 不算错误。
                if account_id is not None and plugin_name in getattr(request.app.state, 'plugin_states', {}):
                    usage = request.app.state.account_usage
                    key = (now_in_timezone().date().isoformat(), account_id, plugin_name)
                    entry = usage.get(key)
                    if entry is None:
                        usage[key] = [1, 1 if response.status_code >= 500 else 0, elapsed_ms]
                    else:
                        entry[0] += 1
                        if response.status_code >= 500:
                            entry[1] += 1
                        entry[2] += elapsed_ms
            except Exception:
                pass
            return response

        # setup 门禁：注册在 request_log 之外，命中的请求在进入 request_log 之前就被挡下
        # ——不计请求日志、不计插件统计、不计配额，也不吃限流。
        #
        # 目的是「内置管理账号还在用公开初始口令」这段时间里，别让站点看起来像正常在跑：
        # 首页大标题下换成初始化引导，插件路由（含设备端的取图地址）直接返回统一错误体。
        # /admin/**、静态资源、探针一律放行——否则连去改密的入口都没了。
        # 只有本地模式存在这个状态：Vercel 侧数据库被停用，app.state.setup_required 恒不存在。
        @app.middleware('http')
        async def setup_gate_middleware(request: Request, call_next):
            if not getattr(request.app.state, 'setup_required', False):
                return await call_next(request)
            path = request.url.path
            if path == '/':
                return await render_index(request)
            first = path.strip('/').split('/')[0]
            if first and (first in getattr(request.app.state, 'plugin_states', {})
                          or first == 'device'):
                return error_response(_SETUP_MESSAGE, 503)
            return await call_next(request)

        from modules.admin_routes import router as admin_router
        from modules.register.auth_pages_routes import router as auth_pages_router
        from modules.register.explore_routes import router as explore_router
        app.include_router(admin_router)
        # 登录 / 注册 / 找回密码挂在站点根下，注册顺序在插件路由之前（见 register_plugins）：
        # 真有个叫 login 的插件时，页面入口仍然优先命中，不会被插件抢走。
        # /explore（访客导航页）同理，同样必须在 register_plugins 之前挂上。
        app.include_router(auth_pages_router)
        app.include_router(explore_router)
        app.include_router(health_router)
        # 设备面（ESP32 / ESP8266 墨水屏）：自带 X-Device-Token 鉴权，在 AUTH_WHITELIST
        # 里整体放行，因此每条路由内部自行复核令牌与用户组权限（见 modules/device/routes.py）。
        # 必须在 register_plugins 之前挂上：真有个叫 device 的插件时，设备入口优先命中。
        from modules.device.routes import router as device_router
        app.include_router(device_router)

        # 文本响应压缩：注册在 body_limit 之前，让 body_limit 保持最外层（最先执行、
        # 在读 body 之前就能拒掉超限请求）。只压文本族，设备端取回的图片一律放行。
        from modules.utils.compression import GZipMiddleware
        app.add_middleware(GZipMiddleware)

        # 请求体上限：**最后注册 = 最外层 = 最先执行**，保证在读 body 之前就拒掉超限请求。
        # 只挂本地模式：Vercel 侧的请求体上限由平台自己管（4.5MB，比这里的默认值还严），
        # 那条链路不新增功能代码。
        from modules.utils.body_limit import BodyLimitMiddleware
        app.add_middleware(
            BodyLimitMiddleware,
            skip_prefixes=_BODY_LIMIT_SKIP_PREFIXES,
            skip_paths=_BODY_LIMIT_SKIP_PATHS,
        )

    try:
        if os.path.isdir(public_dir):
            app.mount('/public', StaticFiles(directory=public_dir), name='public')
    except Exception:
        pass

    plugin_result = register_plugins(app)
    app.state.plugin_result = plugin_result

    if is_local:
        try:
            _load_persisted_states(app)
        except Exception:
            pass

    # 配置覆盖可能在上面把 AUTH_ENABLE 改掉（数据库里存过 True），这里按运行模式重新裁定：
    # dev 必须恒为关；prod 下显式设置的环境变量优先于面板里的配置覆盖
    config_store.enforce_mode_constraints()

    register_error_handlers(app)
    app.include_router(random_router)
    app.include_router(template_router)

    return app, plugin_result


async def get_render_semaphore(app, group_id, user_id=None):
    """渲染并发信号量。

    按用户（账号）计数，同一账号下所有 evkey 共享一份并发额度；用户组只提供
    并发上限数值。无用户身份（如环境变量 EVKEY 鉴权）时用全局上限，不缓存。

    缓存按访问顺序淘汰（OrderedDict 头部是最久未访问的）：账号删除 / 大量账号
    轮换后条目若不回收，字典只增不减。淘汰正在使用的信号量只会让那个账号短暂
    回落到全局上限（等价于重建），而并发上限本就是 CPU 软保护，这个代价远小于
    「重启进程才能回收」。
    """
    from config import MAX_CONCURRENT_RENDERS

    def _semaphore(limit):
        """0 / 空值 = 不限制；用一个远大于实际并发的数值代替"无限"信号量"""
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = 0
        return asyncio.Semaphore(n if n > 0 else 1000000)

    if user_id is None:
        return _semaphore(MAX_CONCURRENT_RENDERS)

    semaphores = app.state.render_semaphores
    entry = semaphores.get(user_id)
    if entry is not None:
        semaphores.move_to_end(user_id)
        return entry[1]

    # 用户组设置的并发量优先于全局 MAX_CONCURRENT_RENDERS
    limit = MAX_CONCURRENT_RENDERS
    if group_id is not None:
        try:
            from modules.database.groups import get_group, is_admin_category
            # 查库是同步 SQLite（单连接 + 全局锁），下放 worker 线程：
            # 这里在事件循环里跑，直接调用会把并发的所有请求一起卡住
            g = await asyncio.to_thread(get_group, group_id)
            if g is not None:
                # 管理组不受并发限制，组配置与全局配置都不套用：它是后台自己的取图通道，
                # 卡住它只会让管理面板先于外部用户失去响应。0 = 不限（见 _semaphore）
                if is_admin_category(g.get('category')):
                    limit = 0
                elif g['max_concurrent_renders'] is not None:
                    limit = g['max_concurrent_renders']
        except Exception:
            pass
    # 一并记下所属用户组，改组配置时按组丢弃缓存；元组形状被
    # modules/admin/common.py 的 _drop_group_semaphores 依赖（取 e[0]），不能改
    entry = (group_id, _semaphore(limit))
    semaphores[user_id] = entry
    _evict_semaphores(semaphores)
    return entry[1]


def _evict_semaphores(semaphores):
    """超过 RENDER_SEMAPHORE_MAXSIZE 时丢弃最久未访问的条目（0 = 不限制）"""
    import config
    try:
        maxsize = int(getattr(config, 'RENDER_SEMAPHORE_MAXSIZE', 2000))
    except (TypeError, ValueError):
        maxsize = 2000
    if maxsize <= 0:
        return
    while len(semaphores) > maxsize:
        semaphores.popitem(last=False)