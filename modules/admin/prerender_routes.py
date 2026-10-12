import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body, _int_field
from modules.errors.errors import error_response
from modules.i18n.registry import t_req

router = APIRouter()

# ---- 定时预渲染 ----

def _prerender_plugin_dir(plugin_name):
    return os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', plugin_name)


def _prerender_target(request, body):
    """校验并解析预渲染目标：路由必须指向真实存在的视图/JSON 模块。

    返回 (info, 错误消息)。route_kind 由路由本身推出，不信任前端传值，
    避免建出"路径是视图、类型是 JSON"这种执行时必然失败的任务。
    size 是业务参数（填在 params 里），视图任务必须给且对应文件要存在。
    """
    plugin_name = str(body.get('plugin_name') or '').strip()
    route_path = str(body.get('route_path') or '').strip()
    parts = route_path.strip('/').split('/')
    if len(parts) != 3 or parts[0] != plugin_name or parts[1] not in ('view', 'json'):
        return None, t_req(request, 'prerender.err_route_format')
    kind, name = parts[1], parts[2]
    plugin_dir = _prerender_plugin_dir(plugin_name)
    if not os.path.isdir(plugin_dir):
        return None, t_req(request, 'prerender.err_plugin_missing', name=plugin_name)
    if kind == 'json':
        if not os.path.isfile(os.path.join(plugin_dir, 'json_module', f'{name}.py')):
            return None, t_req(request, 'prerender.err_json_missing', name=name)
        size = ''
    else:
        size = str((body.get('params') or {}).get('size') or '').strip()
        if not size:
            return None, t_req(request, 'prerender.err_need_size')
        if not os.path.isfile(os.path.join(plugin_dir, 'view', name, f'{size}.py')):
            return None, t_req(request, 'prerender.err_view_missing', name=name, size=size)
    return {'plugin_name': plugin_name, 'route_path': route_path,
            'route_kind': kind, 'size': size}, None


def _prerender_params(info, body):
    """请求体 → 与运行时完全一致的最终参数。

    必须和路由层用同一份解析：否则缓存键与请求时算出的键对不上，
    表现为"任务跑得好好的，请求却永远不命中"，且不报任何错。

    参数**只**来自面板填的查询参数文本（与「测试」页同款），旋转/反色/cmode/格式
    不是任务属性——它们不进缓存键，每个请求现场套用即可。
    """
    from modules.prerender.params import resolve_view_params, resolve_json_params
    plugin_dir = _prerender_plugin_dir(info['plugin_name'])
    query = {k: str(v) for k, v in (body.get('params') or {}).items() if v is not None}

    if info['route_kind'] == 'json':
        return resolve_json_params(info['plugin_name'], plugin_dir, query)

    return resolve_view_params(info['plugin_name'], plugin_dir, info['size'], query)


def _prerender_payload(request, body):
    """请求体 → 可落库的字段集合；返回 (字段 dict, 错误消息)"""
    from modules.prerender.keying import build_identity, dump_params
    from modules.prerender.scheduler import compute_next_run, normalize_cron, normalize_daily_times
    info, err = _prerender_target(request, body)
    if err:
        return None, err
    try:
        params = _prerender_params(info, body)
    except Exception as exc:
        return None, t_req(request, 'prerender.err_param_parse', msg=exc)
    schedule_type = str(body.get('schedule_type') or 'interval').lower()
    if schedule_type not in ('interval', 'daily', 'cron'):
        schedule_type = 'interval'
    interval = _int_field(body, 'interval_seconds', 0)
    # 落库统一成 'HH:MM,HH:MM'，避免同一组时刻因写法不同（空格 / 全角逗号）在列表里显示得五花八门
    daily_time = normalize_daily_times(body.get('daily_time'))
    cron_expr = normalize_cron(body.get('cron_expr'))
    next_run = compute_next_run({
        'schedule_type': schedule_type, 'interval_seconds': interval,
        'daily_time': daily_time, 'cron_expr': cron_expr,
    })
    if next_run is None:
        return None, t_req(request, 'prerender.err_schedule')
    name = str(body.get('name') or '').strip() or f"{info['plugin_name']} {info['route_path']}"
    return {
        **info,
        'name': name[:100],
        'params_json': dump_params(params),
        'cache_key': build_identity(info['plugin_name'], info['route_path'], params,
                                    info['route_kind']),
        'enabled': 1 if body.get('enabled', True) else 0,
        'schedule_type': schedule_type,
        'interval_seconds': interval,
        'daily_time': daily_time,
        'cron_expr': cron_expr,
        # 0 = 不过期（项目约定：0 代表无限，不填写视同 0）
        'cache_ttl_hours': max(0, _int_field(body, 'cache_ttl_hours', 0)),
        'next_run_at': next_run,
    }, None


@router.get('/api/prerender/tasks')
async def admin_prerender_tasks(request: Request):
    """定时预渲染：任务列表 + 运行中任务 + 成品缓存概览"""
    import config as _config
    from modules.prerender import store, scheduler
    try:
        tasks = store.list_tasks()
        total_hits = sum(int(t.get('hit_count') or 0) for t in tasks)
        total_runs = sum(int(t.get('run_count') or 0) for t in tasks)
        return JSONResponse({
            'tasks': tasks,
            'running': sorted(scheduler.running_ids()),
            'cache': store.cache_summary(),
            'enabled': bool(_config.PRERENDER_ENABLE),
            'tick_seconds': _config.PRERENDER_TICK_SECONDS,
            'cache_max_rows': _config.PRERENDER_CACHE_MAX_ROWS,
            'cache_max_mb': _config.PRERENDER_CACHE_MAX_MB,
            # 一次"执行"= 重渲一次，所以这个比值就是"命中 vs 重渲"的比例（无数据时前端显示 -）
            'total_hits': total_hits,
            'total_runs': total_runs,
            'hit_rate': (total_hits / (total_hits + total_runs)) if (total_hits + total_runs) else None,
            'expired_rows': store.count_expired(),
        })
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/prerender/tasks/clear-cache')
async def admin_clear_prerender_cache():
    """清空全部成品缓存（任务保留，下个周期会重新生成）"""
    from modules.prerender import store
    try:
        before = store.cache_summary()
        store.clear_cache()
        return JSONResponse({'success': True, 'deleted': before.get('rows', 0)})
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/prerender/tasks')
async def admin_create_prerender_task(request: Request):
    body = await _body(request)
    if not body:
        return error_response(t_req(request, 'prerender.bad_body'), 400)
    from modules.prerender import store
    try:
        fields, err = _prerender_payload(request, body)
        if err:
            return error_response(err, 400)
        if store.get_task_by_cache_key(fields['cache_key']):
            return error_response(t_req(request, 'prerender.err_duplicate'), 409)
        task_id = store.create_task(
            fields['name'], fields['plugin_name'], fields['route_path'], fields['route_kind'],
            fields['size'], fields['params_json'], fields['cache_key'], fields['enabled'],
            fields['schedule_type'], fields['interval_seconds'], fields['daily_time'],
            fields['cache_ttl_hours'], fields['next_run_at'], fields['cron_expr'])
        return JSONResponse({'success': True, 'id': task_id, 'task': store.get_task(task_id)})
    except Exception as e:
        return error_response(str(e), 500)


@router.put('/api/prerender/tasks/{task_id}')
async def admin_update_prerender_task(task_id: int, request: Request):
    body = await _body(request)
    if not body:
        return error_response(t_req(request, 'prerender.bad_body'), 400)
    from modules.prerender import store
    try:
        task = store.get_task(task_id)
        if not task:
            return error_response(t_req(request, 'prerender.not_found'), 404)
        fields, err = _prerender_payload(request, body)
        if err:
            return error_response(err, 400)
        other = store.get_task_by_cache_key(fields['cache_key'])
        if other and other['id'] != task_id:
            return error_response(t_req(request, 'prerender.err_duplicate'), 409)
        # 参数变了缓存键就变了，旧键的成品图再没有任何请求会命中，顺手清掉
        if task['cache_key'] != fields['cache_key']:
            store.delete_cache(task['cache_key'])
        store.update_task(
            task_id, name=fields['name'], plugin_name=fields['plugin_name'],
            route_path=fields['route_path'], route_kind=fields['route_kind'],
            size=fields['size'], params_json=fields['params_json'],
            cache_key=fields['cache_key'], enabled=fields['enabled'],
            schedule_type=fields['schedule_type'], interval_seconds=fields['interval_seconds'],
            daily_time=fields['daily_time'], cache_ttl_hours=fields['cache_ttl_hours'],
            next_run_at=fields['next_run_at'], cron_expr=fields['cron_expr'])
        return JSONResponse({'success': True, 'task': store.get_task(task_id)})
    except Exception as e:
        return error_response(str(e), 500)


@router.delete('/api/prerender/tasks/{task_id}')
async def admin_delete_prerender_task(task_id: int, request: Request):
    from modules.prerender import store
    try:
        if not store.get_task(task_id):
            return error_response(t_req(request, 'prerender.not_found'), 404)
        # delete_task 会一并清掉该任务的成品缓存
        store.delete_task(task_id)
        return JSONResponse({'success': True})
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/prerender/tasks/{task_id}/run')
async def admin_run_prerender_task(task_id: int, request: Request):
    """立即执行一次（不改动 next_run_at 之外的计划，跑完照常重排）"""
    from modules.prerender import store, scheduler
    try:
        task = store.get_task(task_id)
        if not task:
            return error_response(t_req(request, 'prerender.not_found'), 404)
        return JSONResponse({'success': True, 'task': await scheduler.run_now(request.app, task)})
    except Exception as e:
        return error_response(str(e), 500)


@router.get('/api/prerender/tasks/{task_id}/preview')
async def admin_prerender_preview(task_id: int, request: Request):
    """预览成品：默认回二进制（供 <img> 引用），meta=1 时回 JSON 元信息

    图片回的是缓存的 canonical PNG 本身——它是内部存储编码，浏览器能直接显示，
    且与黑名单里 png 是否被禁无关（禁的是"输出格式"，不是这里的存储容器）。
    """
    from fastapi.responses import Response
    from modules.prerender import store
    task = store.get_task(task_id)
    if not task:
        return error_response(t_req(request, 'prerender.not_found'), 404)
    row = store.get_cache(task['cache_key'])
    if not row:
        return error_response(t_req(request, 'prerender.no_art'), 404)
    payload = row['payload'] or b''
    art_kind = str(row['art_kind'] or '')
    if request.query_params.get('meta') == '1':
        meta = {'art_kind': art_kind, 'bytes': len(payload),
                'width': row['width'], 'height': row['height'],
                'rendered_at': row['rendered_at'], 'last_hit_at': row['last_hit_at'],
                'render_ms': row['render_ms']}
        if art_kind == 'json':
            meta['text'] = payload.decode('utf-8', 'replace')[:20000]
        return JSONResponse(meta)
    if art_kind == 'json':
        return Response(content=payload, media_type='application/json',
                        headers={'Cache-Control': 'no-store'})
    # 预览必须绕开浏览器缓存，否则改了参数看到的还是旧图
    return Response(content=payload, media_type='image/png',
                    headers={'Cache-Control': 'no-store'})