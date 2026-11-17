import asyncio
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from modules.admin.common import _body, _int_field
from modules.errors.errors import error_response
from modules.register.auto_view_routes import available_view_sizes
from modules.i18n.registry import t_req
from modules.utils import body_limit, plog

router = APIRouter()


def _plugins_dir():
    """插件目录的绝对路径：与 register_plugins 的默认值 'plugins' 同一处（仓库根下的 plugins/）"""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(project_root, 'plugins')

@router.get('/api/plugins')
async def admin_plugins(request: Request):
    s = request.app.state
    result = getattr(s, 'plugin_result', {})
    plugins = result.get('plugins', [])
    states = getattr(s, 'plugin_states', {})
    disabled_routes = getattr(s, 'disabled_routes', set())

    plugin_routes = {}
    pnames = [p['name'] for p in plugins]
    for pn in pnames:
        plugin_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', pn)
        routes = []
        for sub in ('view', 'json_module', 'page'):
            sub_dir = os.path.join(plugin_dir, sub)
            if not os.path.isdir(sub_dir):
                continue
            suffix = sub.replace('_module', '')
            for entry in sorted(os.listdir(sub_dir)):
                # 与 auto_view_routes 同一套规则：跳过 __pycache__ 等下划线/点开头的条目，
                # 否则面板会把幽灵路由列出来并算进 route_count
                if entry.startswith('_') or entry.startswith('.'):
                    continue
                e_path = os.path.join(sub_dir, entry)
                sizes = []
                if os.path.isdir(e_path):
                    rp = f'/{pn}/{suffix}/{entry}'
                    # 视图种类的可选尺寸是真正实现了 generate_image 的模块（hxl / h2xl），
                    # 不是目录下的全部 .py——utils.py / drawer.py 会被排除。预渲染建任务要用
                    if sub == 'view':
                        sizes = available_view_sizes(pn, sub_dir, entry)
                elif entry.endswith('.py'):
                    rp = f'/{pn}/{suffix}/{entry[:-3]}'
                else:
                    continue
                routes.append({
                    'path': rp,
                    'name': '',
                    'disabled': rp in disabled_routes,
                    'sizes': sizes,
                })
        if routes:
            plugin_routes[pn] = routes

    return JSONResponse({
        'plugins': [{
            'name': p['name'],
            'description': p.get('description', ''),
            # 元信息全部来自 plugin.json；没写清单的插件这里给空值并带 manifest_missing
            'version': p.get('version', ''),
            'author': p.get('author', ''),
            'min_framework_version': p.get('min_framework_version', ''),
            'dependencies': p.get('dependencies') or {'plugins': [], 'python': []},
            'manifest_missing': bool(p.get('manifest_missing')),
            'enabled': states.get(p['name'], True),
            'route_count': len(plugin_routes.get(p['name'], [])),
        } for p in plugins],
        'routes': plugin_routes,
        # 加载失败的插件不在 plugins 里（路由压根没注册），单独回传给面板展示原因
        'failures': result.get('failures', []),
    })

@router.post('/api/plugins/reload')
async def admin_reload_plugins(request: Request):
    """热重载插件：重扫目录、重建路由、清空插件代码缓存，无需重启服务。

    只重载 plugins/ 下的代码；modules/ 等框架代码改动仍需重启（不在 sys.modules 清理范围内）。
    """
    from modules.plugins.plugin_loader import reload_plugins
    s = request.app.state
    result = reload_plugins(request.app)
    s.plugin_result = result
    return JSONResponse({
        'success': True,
        'total': result['total'],
        'loaded': result['success'],
        'failed': result['failed'],
        'failures': result['failures'],
    })

def _reload_payload(request):
    """装卸后同请求内热重载：新代码当场生效，不必让人再点一次「热重载」。

    装成功但 import 失败**不回滚**——目录已经落盘，回滚等于丢用户产物；失败原因随
    `failures` 回传面板，由管理员决定是改包重装还是卸载。
    """
    from modules.plugins.plugin_loader import bump_generation, reload_plugins
    result = reload_plugins(request.app)
    request.app.state.plugin_result = result
    # /explore 访客导航页按「插件世代号」缓存渲染结果，插件变了必须推进它
    bump_generation()
    return {
        'total': result['total'], 'loaded': result['success'],
        'failed': result['failed'], 'failures': result['failures'],
    }


def _install_error(request, exc):
    """InstallError → 统一错误体。

    「已存在」用 409 并附上插件名：前端据此弹「覆盖」二次确认，弹窗里要显示是哪个插件。
    """
    message = t_req(request, exc.key, **exc.params)
    if exc.key == 'plugin.install_exists':
        return error_response(message, 409, extra={'name': exc.params.get('name', '')})
    return error_response(message, 404 if exc.key == 'plugin.uninstall_missing' else 400)


@router.post('/api/plugins/install')
async def admin_install_plugin(request: Request):
    """上传插件 zip 包：解压校验 → 安装到 plugins/ → 立即热重载。

    走**裸二进制 body**而不是 multipart（项目没有 python-multipart，且两端都是自家代码），
    与 /api/backup/restore 同一套路。`replace=1` 走查询参数——body 已被 zip 占用；
    覆盖安装会删掉同名旧目录，不留备份。
    """
    from modules.plugins.plugin_install import InstallError, install_from_zip

    limit = body_limit.limit_bytes(getattr(config, 'PLUGIN_UPLOAD_MAX_MB', 32))
    too_large = t_req(request, 'plugin.upload_too_large', mb=limit // body_limit.MB)
    if body_limit.exceeds(limit, declared=body_limit.declared_length(request.headers)):
        return error_response(too_large, 400)
    raw = await request.body()
    if body_limit.exceeds(limit, actual=len(raw)):
        return error_response(too_large, 400)
    if not raw:
        return error_response(t_req(request, 'plugin.install_empty'), 400)
    if not raw.startswith(b'PK\x03\x04'):
        return error_response(t_req(request, 'plugin.install_not_zip'), 400)

    replace = (request.query_params.get('replace') or '').lower() in ('1', 'true', 'yes')
    try:
        # 解压 + 校验 + 搬目录都是同步重活，放线程里别卡事件循环
        result = await asyncio.to_thread(
            install_from_zip, raw, _plugins_dir(), request.app.version, replace=replace)
    except InstallError as exc:
        return _install_error(request, exc)
    except Exception as exc:
        plog.exception('安装插件失败')
        return error_response(t_req(request, 'plugin.install_failed', err=exc), 500)

    result['warnings'] = [
        t_req(request, w['key'], **w.get('params', {})) for w in result.get('warnings') or []
    ]
    result['reload'] = _reload_payload(request)
    return JSONResponse({'success': True, **result})


@router.post('/api/plugins/{name}/uninstall')
async def admin_uninstall_plugin(name: str, request: Request):
    """卸载插件：删除插件目录并立即热重载（不留备份）"""
    from modules.plugins.plugin_install import InstallError, uninstall_plugin

    try:
        result = await asyncio.to_thread(uninstall_plugin, name, _plugins_dir())
    except InstallError as exc:
        return _install_error(request, exc)
    except Exception as exc:
        plog.exception('卸载插件失败')
        return error_response(t_req(request, 'plugin.uninstall_failed', err=exc), 500)

    result['reload'] = _reload_payload(request)
    return JSONResponse({'success': True, **result})

@router.post('/api/plugins/{name}/toggle')
async def admin_toggle_plugin(name: str, request: Request):
    from modules.database.states import save_plugin_state
    from modules.plugins.plugin_loader import bump_generation
    s = request.app.state
    cur = s.plugin_states.get(name, True)
    s.plugin_states[name] = not cur
    save_plugin_state(name, not cur)
    # 停用的插件要从对外页面（/explore）上消失，推进世代号让缓存重算
    bump_generation()
    return JSONResponse({'success': True, 'enabled': not cur})

@router.post('/api/routes/toggle')
async def admin_toggle_route(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    path, enabled = body.get('path'), body.get('enabled')
    if not path: return error_response(t_req(request, 'msg.missing_field', name='path'), 400)
    if enabled is None: return error_response(t_req(request, 'msg.missing_field', name='enabled'), 400)
    # 前端发的是 JSON 布尔；这里兼容字符串写法，避免 'false' 被当成 truthy 反而启用
    enabled = bool(enabled) if not isinstance(enabled, str) else enabled.lower() not in ('0', 'false', 'no', '')
    from modules.database.states import save_route_state
    from modules.plugins.plugin_loader import bump_generation
    s = request.app.state
    if enabled:
        s.disabled_routes.discard(path)
    else:
        s.disabled_routes.add(path)
    save_route_state(path, enabled)
    # 被停用的路由要从对外页面（/explore）上消失，推进世代号让缓存重算
    bump_generation()
    return JSONResponse({'success': True})

@router.get('/api/plugins/{name}/config')
async def admin_plugin_config_get(name: str):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    plugin_dir = os.path.join(project_root, 'plugins', name)
    from modules.plugins.plugin_loader import load_plugin_config, get_plugin_config_labels
    file_cfg = load_plugin_config(name, plugin_dir)
    labels = get_plugin_config_labels(name, plugin_dir)
    from modules.database.states import get_plugin_config_overrides
    overrides = get_plugin_config_overrides(name)
    return JSONResponse({
        'config': {k: str(v) if not isinstance(v, (dict, list, bool, int, float, str, type(None))) else v for k, v in file_cfg.items()},
        # 标签由插件在 plugin_config.py 的 CONFIG_LABELS 里自报，面板据此显示中文名而不是键名
        # （loader 已保证它与 config 同键，这里不再过滤）
        'labels': labels,
        # 只剩「当前真的还是配置项」的覆盖：历史脏数据（例如元信息常量）不再显示成「已修改」
        'overrides': {k: True for k in overrides if k in file_cfg},
    })

@router.post('/api/plugins/{name}/config')
async def admin_plugin_config_save(name: str, request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    key, value = body.get('key'), body.get('value')
    if not key: return error_response(t_req(request, 'msg.missing_field', name='key'), 400)
    from modules.database.states import save_plugin_config_override, delete_plugin_config_override
    from modules.plugins.plugin_loader import load_plugin_config, clear_plugin_config_cache
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    # 只接受 plugin_config.py 里声明过的配置项：元信息常量、私有名、任意键都不能被写进
    # 覆盖表，否则「插件配置」会凭空多出可编辑项（元信息的唯一来源是 plugin.json）
    if key not in load_plugin_config(name, os.path.join(project_root, 'plugins', name)):
        return error_response(t_req(request, 'plugin.cfg_no_key', name=name, key=key), 400)
    # value 为 null 视为还原默认，否则会被 str(None) 存成 'None' 脏值
    if value is None:
        delete_plugin_config_override(name, key)
    else:
        save_plugin_config_override(name, key, value)
    clear_plugin_config_cache()
    return JSONResponse({'success': True})

@router.delete('/api/plugins/{name}/config')
async def admin_plugin_config_delete(name: str, request: Request):
    key = request.query_params.get('key', '')
    if not key: return error_response(t_req(request, 'msg.missing_field', name='key'), 400)
    # 删除只是撤下一条覆盖，任何键都放行：留作清理历史覆盖的通道，不设白名单
    from modules.database.states import delete_plugin_config_override
    delete_plugin_config_override(name, key)
    from modules.plugins.plugin_loader import clear_plugin_config_cache
    clear_plugin_config_cache()
    return JSONResponse({'success': True})

@router.post('/api/test-route')
async def admin_test_route(request: Request):
    """服务端自测：单次 / 顺序连发 / 并发压力，返回每次请求的状态、耗时、大小与错误"""
    import asyncio
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    path = (body.get('path') or '').strip()
    if not path: return error_response(t_req(request, 'test.need_path'), 400)
    params = body.get('params') or {}
    if not isinstance(params, dict):
        return error_response(t_req(request, 'test.bad_params'), 400)
    mode = body.get('mode', 'single')
    if mode not in ('single', 'sequence', 'concurrent'):
        mode = 'single'
    count = 1 if mode == 'single' else max(1, min(_int_field(body, 'count', 1), 200))
    concurrency = max(1, min(_int_field(body, 'concurrency', 4), min(count, 50)))

    from httpx import AsyncClient
    from urllib.parse import urlparse
    evkey = request.headers.get('evkey') or request.query_params.get('evkey') or ''
    if path.startswith('/'):
        url = f'{request.base_url}{path.lstrip("/")}'
    else:
        # 只允许指向本服务：这个工具是「测本服务的路由」用的，放开任意绝对 URL
        # 等于把服务端变成可探测内网的代理
        base = urlparse(str(request.base_url))
        target = urlparse(path)
        if target.scheme not in ('http', 'https') or target.netloc != base.netloc:
            return error_response(t_req(request, 'test.only_local'), 400)
        url = path
    headers = {'evkey': evkey} if evkey else {}

    sem = asyncio.Semaphore(concurrency)

    async def one(index):
        async def call():
            started = time.time()
            rec = {'index': index, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started))}
            try:
                resp = await client.get(url, params=params, headers=headers)
                rec.update({
                    'status': resp.status_code, 'ok': resp.status_code < 400,
                    'size': len(resp.content),
                    'content_type': resp.headers.get('content-type', ''),
                    'error': '',
                })
            except Exception as exc:
                rec.update({'status': 0, 'ok': False, 'size': 0, 'content_type': '', 'error': str(exc)})
            rec['duration_ms'] = round((time.time() - started) * 1000, 1)
            return rec
        if mode == 'concurrent':
            async with sem:
                return await call()
        return await call()

    test_start = time.time()
    async with AsyncClient(timeout=60) as client:
        if mode == 'sequence':
            results = [await one(i + 1) for i in range(count)]
        else:
            results = await asyncio.gather(*[one(i + 1) for i in range(count)])
    total_ms = round((time.time() - test_start) * 1000, 1)

    durations = sorted(r['duration_ms'] for r in results)
    sizes = [r['size'] for r in results]
    ok = sum(1 for r in results if r['ok'])
    return JSONResponse({
        'success': True, 'target': url, 'mode': mode, 'count': count, 'concurrency': concurrency,
        'payload': {
            'method': 'GET', 'url': url, 'params': params,
            'headers': {'evkey': (evkey[:4] + '…') if evkey else ''},
        },
        'summary': {
            'count': count, 'ok': ok,
            'avg_ms': round(sum(durations) / len(durations), 1) if durations else 0,
            'min_ms': durations[0] if durations else 0,
            'max_ms': durations[-1] if durations else 0,
            'p95_ms': durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else 0,
            'avg_size': round(sum(sizes) / len(sizes)) if sizes else 0,
            'total_ms': total_ms,
        },
        'results': results,
    })