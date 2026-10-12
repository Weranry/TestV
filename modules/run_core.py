import sys
import os
import time
import threading

from modules import lifecycle
from modules.utils import plog
from modules.utils.timezone import fmt_duration, utc_now_iso, utc_string_to_local


def _attach_log_file():
    """按当前配置挂进程日志的文件出口（留空 / 挂不上都退化成只写 stdout）。

    启动期要调两次：第一次在 create_app 之前（应用初始化就崩的情况也得留下日志），
    第二次在 create_app 之后——面板里存的配置覆盖要等 create_app 内部应用完才生效。
    重复挂载由 plog.attach_file 自己替换旧出口，不会泄漏。
    """
    import config
    plog.attach_file(getattr(config, 'LOG_FILE', ''),
                     getattr(config, 'LOG_MAX_BYTES', 0),
                     getattr(config, 'LOG_BACKUP_COUNT', 0))


def startup_banner():
    print(
        '===================================================================\n'
        '███████╗██╗███╗   ██╗██╗  ██╗██╗   ██╗██╗███████╗██╗    ██╗███████╗\n'
        '██╔════╝██║████╗  ██║██║ ██╔╝██║   ██║██║██╔════╝██║    ██║██╔════╝\n'
        '█████╗  ██║██╔██╗ ██║█████╔╝ ██║   ██║██║█████╗  ██║ █╗ ██║███████╗\n'
        '██╔══╝  ██║██║╚██╗██║██╔═██╗ ╚██╗ ██╔╝██║██╔══╝  ██║███╗██║╚════██║\n'
        '███████╗██║██║ ╚████║██║  ██╗ ╚████╔╝ ██║███████╗╚███╔███╔╝███████║\n'
        '╚══════╝╚═╝╚═╝  ╚═════╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚══════╝\n'
        '====================================================================='
    )


def print_help():
    print('\n 可用命令:')
    print('  help     - 显示此帮助信息')
    print('  routes   - 列出所有路由及其参数')
    print('  plugins  - 列出所有插件及其描述')
    print('  config   - 显示当前配置参数')
    print('  auth     - 显示鉴权状态与白名单')
    print('  cache    - 显示缓存统计')
    print('  clearcache - 清除所有缓存')
    print('  stats    - 显示持久化统计信息')
    print('  exit     - 退出程序')


def _iter_routes(routes):
    """递归展开路由表。

    FastAPI 0.141 起 include_router 不再把子路由摊平进 app.routes，而是塞一个懒加载的
    _IncludedRouter（没有 path/methods），必须顺着 original_router 往下钻才能拿到真实路由。
    """
    for route in routes:
        sub = getattr(route, 'original_router', None)
        if sub is not None:
            yield from _iter_routes(getattr(sub, 'routes', []))
            continue
        yield route


def print_routes(app):
    print('\n路由列表:')
    routes = [
        r for r in _iter_routes(app.routes)
        if getattr(r, 'methods', None) and hasattr(r, 'path')
    ]
    routes.sort(key=lambda r: r.path)
    for route in routes:
        methods = ','.join(sorted(route.methods - {'OPTIONS', 'HEAD'}))
        print(f'  [{methods}] {route.path}')
        if route.name:
            print(f'    name: {route.name}')
    print(f'  共 {len(routes)} 条路由')


def print_plugins(plugin_result):
    plugins = plugin_result.get('plugins', [])
    if not plugins:
        print('\n无已加载插件')
        return
    print(f'\n已加载插件 ({plugin_result.get("success", 0)}/{plugin_result.get("total", 0)}):')
    if plugin_result.get('failed', 0) > 0:
        print(f'  加载失败: {plugin_result["failed"]} 个')
    for p in plugins:
        print(f'  {p["name"]} | {p["description"]}')


def print_config():
    from config import (
        DEFAULT_ROTATE, DEFAULT_INVERT,
        DEFAULT_JPEG_QUALITY, DEFAULT_WEBP_QUALITY,
        DEFAULT_PNG_COMPRESS_LEVEL, DEFAULT_TIFF_COMPRESSION,
        DEFAULT_IMAGE_FORMAT, DEFAULT_TIMEZONE_OFFSET,
        CACHE_MAXSIZE,
    )
    print('\n参数配置:')
    print(f'  DEFAULT_ROTATE             = {DEFAULT_ROTATE}')
    print(f'  DEFAULT_INVERT             = {DEFAULT_INVERT}')
    print(f'  DEFAULT_JPEG_QUALITY       = {DEFAULT_JPEG_QUALITY}')
    print(f'  DEFAULT_WEBP_QUALITY       = {DEFAULT_WEBP_QUALITY}')
    print(f'  DEFAULT_PNG_COMPRESS_LEVEL = {DEFAULT_PNG_COMPRESS_LEVEL}')
    print(f'  DEFAULT_TIFF_COMPRESSION   = {DEFAULT_TIFF_COMPRESSION}')
    print(f'  DEFAULT_IMAGE_FORMAT       = {DEFAULT_IMAGE_FORMAT}')
    print(f'  DEFAULT_TIMEZONE_OFFSET    = {DEFAULT_TIMEZONE_OFFSET}')
    print(f'  CACHE_MAXSIZE              = {CACHE_MAXSIZE}')


def print_auth():
    from config import AUTH_ENABLE, AUTH_WHITELIST
    import os as _os
    env_key = _os.environ.get('EVKEY')
    print('\n鉴权状态:')
    status = '已启用' if AUTH_ENABLE else '未启用'
    print(f'  鉴权: {status}')
    if AUTH_ENABLE:
        print(f'  EVKEY 环境变量: {"已设置" if env_key else "未设置"}')
    print(f'  白名单路径:')
    for path in AUTH_WHITELIST:
        print(f'    - {path}')


def print_cache():
    from modules.cache.cache import stats
    s = stats()
    print('\n缓存统计:')
    print(f'  字体条目数: {s["size"]} / {s["maxsize"]}')
    print(f'  命中: {s["hits"]}')
    print(f'  未命中: {s["misses"]}')
    print(f'  命中率: {s["hit_rate"]}%')


def clear_cache():
    from modules.cache.cache import clear
    clear()
    print('\n缓存已清除')


def print_stats(app):
    try:
        from modules.database.stats import get_server_info, get_total_uptime_seconds, get_all_sessions, get_all_plugin_stats
        first_startup = get_server_info('first_startup')
        last_startup = get_server_info('last_startup')
        total_uptime = get_total_uptime_seconds()
        sessions = get_all_sessions()

        print('\n持久化统计:')
        print(f'  首次启动: {utc_string_to_local(first_startup) or "未知"}')
        print(f'  最近启动: {utc_string_to_local(last_startup) or "未知"}')
        print(f'  累计运行: {fmt_duration(total_uptime)}')
        print(f'  启动次数: {len(sessions)} 次')

        counts = getattr(app.state, 'request_counts', {})
        total_req = sum(counts.values()) if counts else 0
        print(f'  累计请求: {total_req}')

        stats = get_all_plugin_stats()
        if stats:
            print(f'  插件统计 ({len(stats)} 个):')
            for s in stats:
                print(f'    {s["plugin_name"]}: {s["request_count"]} 次 (首次: {s["first_request"]}, 最近: {s["last_request"]})')

        if sessions:
            print(f'  历次启动 ({len(sessions)} 次):')
            for s in sessions[:10]:
                end = s['end_time'] or '运行中'
                print(f'    #{s["id"]} | {s["start_time"]} → {end} | 模式: {s["mode"]}')
            if len(sessions) > 10:
                print(f'    ... 还有 {len(sessions) - 10} 条记录')
    except Exception as e:
        print(f'  统计读取失败: {e}')


def console_listener(app, plugin_result, server):
    while True:
        try:
            cmd = input('>>> ').strip().lower()
            if cmd == 'help':
                print_help()
            elif cmd == 'routes':
                print_routes(app)
            elif cmd == 'plugins':
                # 现取 app.state：插件热重载会整体替换 plugin_result，
                # 用启动时捕获的那份会显示过期的插件列表
                print_plugins(getattr(app.state, 'plugin_result', plugin_result))
            elif cmd == 'config':
                print_config()
            elif cmd == 'auth':
                print_auth()
            elif cmd == 'cache':
                print_cache()
            elif cmd == 'clearcache':
                clear_cache()
            elif cmd == 'stats':
                print_stats(app)
            elif cmd == 'exit':
                print('正在保存统计数据...')
                app.state._shutdown = True
                lifecycle.flush_and_close(app)
                print('正在退出...')
                # 本函数跑在守护线程里：sys.exit() 只会结束这个线程，uvicorn 主循环照旧，
                # 必须置 should_exit 才能真正让服务器退出
                server.should_exit = True
                return
            elif cmd == '':
                continue
            else:
                print(f"未知命令: '{cmd}', 输入 'help' 查看可用命令.")
        except EOFError:
            break


def refresh_static_explore():
    """启动时把静态访客页 `public/pages/explore.html` 刷到与当前插件目录一致。

    这一页在 Vercel 上是边缘静态直出（`vercel.json` 把 `/explore` 指向该文件），但它是在
    **构建机上生成的**，所以仓库里那份必须跟插件目录保持同步。这一步把「记得手动跑生成器」
    从人的脑子里挪到启动流程里：只要发布前起过一次本地服务，提交时那份就已经是最新的。

    必须开子进程跑，不能在本进程里直接调 `build_static_html`：生成器内部用
    `create_app(mode='vercel')` 取插件清单，而那会 `set_db_disabled(True)` 并
    `config_store.set_mode('vercel')`——都是**进程级全局开关**，在本地服务进程里直接调会把
    正在跑的这套服务一起关掉（库不可用、缓存停用）。子进程跑的就是手动那条命令本身，
    生成结果与手动执行完全一致。

    终端保持静默：调用点在启动摘要之后、`set_terminal_alerts(False)` 之后，终端不该再多出
    一行（见 rules「本地启动输出保持安静」）。**成功时一个字都不输出**——子进程的 stdout
    直接丢弃：`plog.info` 是无条件打终端的（见 plog._write），拿它报「已刷新」正好会破坏那条
    约定；而且刷新成功与否看 `git status` 里那份文件就够了。失败只用 `plog.warn` 记一笔
    （`set_terminal_alerts(False)` 之后 WARN 只进日志文件），绝不中断启动——静态页旧一版，
    好过服务起不来。
    """
    import subprocess
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    cmd = [sys.executable, '-B', '-m', 'modules.register.explore_static', '--if-stale']
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=180)
    except Exception as e:
        plog.warn(f'静态访客页自动刷新失败: {e}')
        return
    if proc.returncode != 0:
        tail = (proc.stderr or '').strip().splitlines()
        plog.warn(f'静态访客页自动刷新失败: {tail[-1] if tail else "未知错误"}')


def run_server(mode):
    from modules.app_core import create_app
    import uvicorn

    startup_banner()
    # 下面这些启动信息都走 plog（统一 `[UTC] [LEVEL] message` 格式，并落到可选的日志文件）；
    # help / routes / stats 这类**用户敲出来的命令输出**仍用 print，它们不是日志
    _attach_log_file()

    EINKVIEWS_START_TIME = utc_now_iso()
    plog.info(f'启动时间: {utc_string_to_local(EINKVIEWS_START_TIME)}')

    startup_start = time.time()
    try:
        app, plugin_result = create_app(mode=mode)
    except Exception as e:
        plog.error(f'致命错误: FastAPI 应用初始化失败 - {e}')
        sys.exit(1)
    startup_elapsed = time.time() - startup_start
    # 配置覆盖到这里才生效（create_app 内部应用），重新挂一次文件出口
    _attach_log_file()

    total = plugin_result.get('total', 0)
    success = plugin_result.get('success', 0)
    failed = plugin_result.get('failed', 0)
    plog.info(f'发现插件 {total} 个，加载成功 {success} 个，失败 {failed} 个')
    missing_manifest = plugin_result.get('manifest_missing', 0)
    if missing_manifest:
        plog.info(f'  其中未声明清单 {missing_manifest} 个')

    from config import AUTH_ENABLE
    auth_status = '已启用' if AUTH_ENABLE else '未启用（测试模式）'
    plog.info(f'运行模式: {mode}')
    plog.info(f'鉴权状态: {auth_status}')
    if AUTH_ENABLE:
        from modules.auth.auth import uses_ephemeral_jwt_secret
        if uses_ephemeral_jwt_secret():
            plog.warn('未设置 JWT_SECRET，管理面板会话密钥为本次进程随机值，重启后所有登录态失效')

    if mode in ('dev', 'prod'):
        try:
            # 建库时写入的内置管理员口令是公开的（admin/admin123），首次登录会强制改密；
            # 但「部署完一直没人进面板」的机器上它就一直是有效凭据，启动时明确提示一次
            from modules.database.accounts import default_admin_needs_password_change
            if default_admin_needs_password_change():
                plog.warn('内置管理账号仍在使用初始口令，请登录管理面板后立即修改密码')
        except Exception:
            pass

        try:
            from modules.database.stats import get_server_info, get_total_uptime_seconds, get_all_sessions
            first_startup = get_server_info('first_startup')
            total_uptime = get_total_uptime_seconds()
            sessions = get_all_sessions()
            if first_startup:
                plog.info(f'首次启动: {utc_string_to_local(first_startup)}')
            plog.info(f'累计运行: {fmt_duration(total_uptime)}')
            plog.info(f'启动次数: {len(sessions)} 次')
            saved_counts = getattr(app.state, 'request_counts', {})
            total_req = sum(saved_counts.values()) if saved_counts else 0
            plog.info(f'累计请求: {total_req}')
        except Exception:
            plog.exception('读取持久化统计失败')

    port = int(os.environ.get('PORT', '5000'))
    plog.info(f'管理面板: http://127.0.0.1:{port}/admin')
    plog.info(f'启动耗时: {startup_elapsed:.3f}s')
    # 版本号单一来源：这里以前硬编码过一个和 FRAMEWORK_VERSION 不一致的字符串，
    # 「关于」页与启动日志对不上时会让人怀疑是不是更新没生效
    from modules.app_core import FRAMEWORK_VERSION
    plog.info(f'版本: {FRAMEWORK_VERSION}')
    plog.info(f'访问地址: http://127.0.0.1:{port}')
    print("注意: 仅供本地使用。输入 'help' 获取指令。")
    # 启动信息到此为止：之后终端只留用户敲的命令输出，WARN / ERROR 照旧进日志文件
    plog.set_terminal_alerts(False)

    # 启动摘要之后的自动维护：把静态访客页刷到与当前插件目录一致（详见该函数说明）。
    # 放在 set_terminal_alerts 之后是刻意的——这一步的成败都只写日志，终端不再多出一行
    refresh_static_explore()

    # 自己持有 Server 实例（不用 uvicorn.run）：控制台的 exit 命令在另一个线程里，
    # 需要拿到实例把 should_exit 置真才能优雅退出
    # log_level=warning + access_log=False：只保留上面打印的启动信息，不刷 uvicorn 的日志
    uv_config = uvicorn.Config(app, host='0.0.0.0', port=port,
                               log_level='warning', access_log=False)
    server = uvicorn.Server(uv_config)

    t = threading.Thread(target=console_listener, args=(app, plugin_result, server), daemon=True)
    t.start()

    server.run()