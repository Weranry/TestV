import asyncio
import io
import csv
import json
import re

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from modules.errors.errors import error_response
from modules.i18n.registry import t_req

router = APIRouter()

# ---- Stats & Logs ----

@router.get('/api/stats')
async def admin_stats():
    try:
        from modules.database.stats import get_server_info, get_total_uptime_seconds, get_all_plugin_stats, get_session_stats
        def _load_stats():
            return (get_server_info('first_startup'), get_server_info('last_startup'),
                    get_total_uptime_seconds(), get_session_stats(), get_all_plugin_stats())
        first, last, uptime, sessions, plugin_stats = await asyncio.to_thread(_load_stats)
        return {
            'first_startup': first, 'last_startup': last,
            'total_uptime_seconds': uptime, 'session_count': len(sessions),
            'sessions': sessions, 'plugin_stats': [dict(s) for s in plugin_stats],
        }
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/request-logs')
async def admin_request_logs(request: Request):
    try:
        limit = max(1, min(int(request.query_params.get('limit', 100)), 500))
        offset = max(0, int(request.query_params.get('offset', 0)))
        plugin_name = request.query_params.get('plugin', None)
        min_status_str = request.query_params.get('min_status', None)
        min_status = int(min_status_str) if min_status_str else None
        account_str = request.query_params.get('account', None)
        account_id = int(account_str) if account_str else None
        from modules.database.logs import (
            get_request_logs, get_request_log_count, log_queue_size, dropped_log_count,
        )
        logs, total = await asyncio.to_thread(
            lambda: (get_request_logs(limit=limit, offset=offset, plugin_name=plugin_name,
                                      min_status=min_status, account_id=account_id),
                     get_request_log_count(plugin_name=plugin_name, min_status=min_status, account_id=account_id)))
        from config import REQUEST_LOG_RETENTION_DAYS
        qsize, qmax = log_queue_size()
        return {
            'logs': [dict(r) for r in logs], 'total': total, 'limit': limit, 'offset': offset,
            'retention_days': REQUEST_LOG_RETENTION_DAYS,
            'log_queue': {'size': qsize, 'maxsize': qmax, 'dropped': dropped_log_count()},
        }
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/request-logs/export')
async def admin_export_request_logs(request: Request):
    try:
        format_type = request.query_params.get('format', 'csv')
        plugin_name = request.query_params.get('plugin', None)
        min_status_str = request.query_params.get('min_status', None)
        min_status = int(min_status_str) if min_status_str else None
        # 导出跟随页面上的筛选：列表按账号筛过、导出却是全量，两边对不上会很难解释
        account_str = request.query_params.get('account', None)
        account_id = int(account_str) if account_str else None
        from modules.database.logs import get_request_logs
        from modules.utils.timezone import utc_string_to_local
        from config import LOG_EXPORT_MAX_ROWS
        logs = await asyncio.to_thread(
            get_request_logs, limit=LOG_EXPORT_MAX_ROWS, offset=0, plugin_name=plugin_name,
            min_status=min_status, account_id=account_id)
        output = io.StringIO()
        if format_type == 'csv':
            writer = csv.writer(output)
            writer.writerow([
                t_req(request, 'log.col_time'), t_req(request, 'log.col_method'),
                t_req(request, 'log.col_path'), t_req(request, 'log.col_plugin'),
                t_req(request, 'log.csv_account_id'), t_req(request, 'log.csv_status_code'),
                t_req(request, 'log.csv_duration_ms'), t_req(request, 'log.col_error'),
                t_req(request, 'log.csv_request_id'),
            ])
            for l in logs:
                writer.writerow([utc_string_to_local(l['timestamp']), l['method'], l['path'], l['plugin_name'] or '', l['account_id'] if l['account_id'] is not None else '', l['status_code'], l['duration_ms'] or '', l['error'] or '', l['request_id'] or ''])
        else:
            json.dump([dict(l) for l in logs], output, ensure_ascii=False, indent=2)
        content = output.getvalue()
        output.close()
        # plugin 与 format 都来自 query，拼进 Content-Disposition 前必须洗掉引号/换行，
        # 否则响应头结构会被输入破坏；扩展名按实际内容定，避免出现 .xml 里装 JSON
        safe_name = re.sub(r'[^0-9A-Za-z_.-]', '_', plugin_name or 'all')[:64]
        safe_ext = 'csv' if format_type == 'csv' else 'json'
        filename = f'request_logs_{safe_name}.{safe_ext}'
        return Response(content=content.encode('utf-8'), media_type='text/csv; charset=utf-8' if format_type == 'csv' else 'application/json; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/request-logs/clear')
async def admin_clear_request_logs():
    from modules.database.logs import clear_request_logs
    return JSONResponse({'success': True, 'deleted': await asyncio.to_thread(clear_request_logs)})


@router.get('/api/audit-logs')
async def admin_audit_logs(request: Request):
    """配置变更审计：谁在什么时候改了哪个管理接口"""
    try:
        limit = max(1, min(int(request.query_params.get('limit', 100)), 500))
        offset = max(0, int(request.query_params.get('offset', 0)))
        from modules.database.audit import get_audit_logs, get_audit_log_count
        logs, total = await asyncio.to_thread(
            lambda: (get_audit_logs(limit, offset), get_audit_log_count()))
        return JSONResponse({
            'logs': logs,
            'total': total,
            'limit': limit, 'offset': offset,
        })
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/audit-logs/clear')
async def admin_clear_audit_logs():
    from modules.database.audit import clear_audit_logs
    return JSONResponse({'success': True, 'deleted': await asyncio.to_thread(clear_audit_logs)})


@router.get('/api/statistics/plugin-routes')
async def admin_statistics_plugin_routes(request: Request):
    """某插件在时间范围内的按路由请求统计（统计页按插件展开明细）"""
    try:
        days = max(1, min(int(request.query_params.get('days', 7)), 90))
        plugin = request.query_params.get('plugin', '')
        if not plugin:
            return error_response(t_req(request, 'stats.missing_plugin'), 400)
        from modules.database.logs import get_plugin_route_stats
        routes = await asyncio.to_thread(get_plugin_route_stats, plugin, days)
        return JSONResponse({'plugin': plugin, 'days': days, 'routes': routes})
    except Exception as e:
        return error_response(str(e), 500)


@router.get('/api/statistics/slowest-routes')
async def admin_statistics_slowest_routes(request: Request):
    """最慢路由榜：按 p95 渲染耗时降序，取前 N 条（统计页用）"""
    try:
        days = max(1, min(int(request.query_params.get('days', 7)), 90))
        limit = max(1, min(int(request.query_params.get('limit', 10)), 50))
        from modules.database.logs import get_route_percentiles
        rows = (await asyncio.to_thread(get_route_percentiles, None, days))[:limit]
        return JSONResponse({'days': days, 'routes': rows})
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/statistics')
async def admin_statistics(request: Request):
    try:
        days = max(1, min(int(request.query_params.get('days', 7)), 90))
        from modules.database.logs import get_request_statistics
        from modules.utils.timezone import get_timezone_offset
        try:
            tz_offset = get_timezone_offset()
        except Exception:
            tz_offset = None
        stats = await asyncio.to_thread(get_request_statistics, days, offset_hours=tz_offset)
        return {'days': days, **stats}
    except Exception as e:
        return error_response(str(e), 500)