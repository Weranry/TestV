"""恢复出厂设置：三档不可逆清理，入口在「备份」页。

- `plugins`：删除 `plugins/` 下全部插件目录，并清空插件启用状态 / 路由开关 /
  插件配置覆盖 / 用户组插件权限，随后热重载；
- `records`：只清日志与运行记录（请求日志、审计、统计、设备运行痕迹、预渲染产物、
  已处理的找回密码申请），账号、用户组、EVkey、激活码、设备注册与配对关系全部保留；
- `full`：在 `plugins` 基础上删除数据库文件与 `data/backups/` 快照，再重建全新库
  （默认账号 admin / admin123，首次登录强制改密），等价于一次全新安装。

安全边界与整库恢复一致：只允许内置兜底管理组调用，且请求体必须带
`confirm: "RESET"`——两处都过了才会真的动手。操作本身由管理端审计中间件留痕。
"""
import asyncio
import os
import shutil
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from modules.admin.common import _body, _fmt_bytes, super_admin_only
from modules.errors.errors import error_response
from modules.i18n.registry import t_req
from modules.utils import plog

router = APIRouter()

MODES = ('plugins', 'full', 'records')

# 确认词：必须原样出现在请求体里。防的是脚本误调与面板误点，不是安全边界
CONFIRM_WORD = 'RESET'

# 同一时刻只允许一个恢复出厂操作：两档并发会互相删掉对方正在用的文件，
# 落盘状态无法解释。非阻塞抢锁，第二个请求直接 409。
_OP_LOCK = threading.Lock()


def _plugins_dir():
    """插件目录：与 register_plugins 的默认值 'plugins' 同一处（仓库根下）"""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(project_root, 'plugins')


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _list_plugin_names():
    """按 register_plugins 的识别规则列出插件名：直接子目录且目录下有 routes.py"""
    root = _plugins_dir()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    result = []
    for name in names:
        if name.startswith('.'):
            continue
        full = os.path.join(root, name)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, 'routes.py')):
            result.append(name)
    return result


def _count_rows(table, where=''):
    """单表计数；表不存在或库不可用时返回 0（信息接口不该因为一行 SQL 直接 500）"""
    from modules.database.core import _exec
    clause = f' WHERE {where}' if where else ''
    try:
        row = _exec(f'SELECT COUNT(*) AS cnt FROM {table}{clause}', fetch_one=True)
        return row['cnt'] if row else 0
    except Exception:
        return 0


def _collect_info():
    """面板要的统计（同步查库/列目录，调用方负责放线程）"""
    from modules.database.core import db_path, db_file_size
    from modules.database.maintenance import _RUNTIME_TABLES
    from modules.admin.backup_routes import _backups_dir, _list_backups

    db_file = db_path()
    size = db_file_size()
    plugins = _list_plugin_names()

    counts = {}
    backups = []
    if db_file:
        counts['request_logs'] = _count_rows('request_logs')
        counts['audit_logs'] = _count_rows('audit_logs')
        for table, _pk in _RUNTIME_TABLES:
            counts[table] = _count_rows(table)
        counts['prerender_cache'] = _count_rows('prerender_cache')
        counts['password_reset_requests'] = _count_rows(
            'password_reset_requests', "status != 'pending'")
        backups = _list_backups(_backups_dir(db_file))

    return {
        'db_enabled': bool(db_file),
        'db_size': size,
        'db_size_text': _fmt_bytes(size),
        'plugins': plugins,
        'plugin_count': len(plugins),
        'records': counts,
        'records_total': sum(counts.values()),
        'backups': {
            'count': len(backups),
            'size': sum(b['size'] for b in backups),
            'size_text': _fmt_bytes(sum(b['size'] for b in backups)),
        },
        'retention': {
            'request_days': int(getattr(config, 'REQUEST_LOG_RETENTION_DAYS', 0) or 0),
            'audit_days': int(getattr(config, 'AUDIT_LOG_RETENTION_DAYS', 0) or 0),
            'telemetry_days': int(getattr(config, 'DEVICE_TELEMETRY_RETENTION_DAYS', 0) or 0),
        },
    }


@router.get('/api/factory/info')
async def admin_factory_info(request: Request = None):
    """三档恢复分别会动到多少数据（插件数 / 记录数 / 备份份数 / 库大小）"""
    payload = await asyncio.to_thread(_collect_info)
    payload['success'] = True
    return JSONResponse(payload)


def _reload_after_plugin_clear(app):
    """插件目录删完后的内存态复位。

    必须先清 `plugin_states` 再重扫目录：reload_plugins 会保留「已注册插件」的开关，
    不清的话旧开关会跟着插件名残留下来（虽然目录已经没了，但面板/库里的脏数据还在）。
    """
    from modules.plugins.plugin_loader import (
        bump_generation, clear_plugin_config_cache, reload_plugins,
    )
    from modules.auth.auth import invalidate_auth_cache

    app.state.plugin_states = {}
    app.state.disabled_routes = set()
    clear_plugin_config_cache()
    app.state.plugin_result = reload_plugins(app)
    bump_generation()
    invalidate_auth_cache()


async def _reset_plugins(request):
    from modules.database.maintenance import clear_plugin_data
    from modules.plugins.plugin_install import uninstall_all_plugins

    def _work():
        return uninstall_all_plugins(_plugins_dir()), clear_plugin_data()

    removed, cleared = await asyncio.to_thread(_work)
    _reload_after_plugin_clear(request.app)
    return JSONResponse({
        'success': True,
        'message': t_req(request, 'factory.done_plugins', n=len(removed)),
        'plugins': removed,
        'cleared': cleared,
    })


async def _reset_records(request):
    from modules import lifecycle
    from modules.database.core import is_db_available
    from modules.database.maintenance import clear_runtime_records

    if not is_db_available():
        return error_response(t_req(request, 'factory.db_unavailable'), 400)
    cleared = await asyncio.to_thread(clear_runtime_records)
    lifecycle.reset_after_record_clear(request.app)
    total = sum(cleared.values())
    return JSONResponse({
        'success': True,
        'message': t_req(request, 'factory.done_records', n=total),
        'cleared': cleared,
    })


async def _reset_full(request):
    from modules import lifecycle
    from modules.database import core
    from modules.database.logs import flush_log_queue
    from modules.plugins.plugin_install import uninstall_all_plugins

    db_file = core.db_path()
    if not db_file:
        return error_response(t_req(request, 'factory.db_unavailable'), 400)

    app = request.app
    # 先落盘内存里排队的日志与统计：它们的目标由连接决定，删库后再刷就会写进新库
    try:
        lifecycle.persist_counters(app)
        lifecycle.persist_account_usage(app)
        flush_log_queue()
    except Exception:
        plog.exception('恢复出厂前落盘统计数据失败')

    def _drop_files():
        removed = uninstall_all_plugins(_plugins_dir())
        # 历史快照一并删除：留着等于把旧账号与旧配置的完整副本继续放在磁盘上
        from modules.admin.backup_routes import _backups_dir
        shutil.rmtree(_backups_dir(db_file), ignore_errors=True)
        return removed

    removed = await asyncio.to_thread(_drop_files)
    # 先卸路由：插件代码已删，但内存里的路由还指向不存在的模块
    _reload_after_plugin_clear(app)

    try:
        with core._db_lock:
            # 闭连接用 _close_pool_locked（调用方持锁版）：close_connection() 会再取一次
            # 同一把非重入锁，在这里调就是死锁
            core._close_pool_locked()
            core._close_read_pool_locked()
            # 主库与 WAL 一起删：残留的 -wal 拼到重建出来的新库上会直接读成「库损坏」
            for suffix in ('', '-wal', '-shm'):
                _unlink(db_file + suffix)
    except OSError as exc:
        plog.exception('删除数据库文件失败')
        return error_response(t_req(request, 'factory.db_delete_failed', err=exc), 500)

    # 删库后走与「恢复备份」同一套重建流程：重开连接、建全新库、重载全部内存态
    lifecycle.reload_after_restore(app)

    response = JSONResponse({
        'success': True,
        'message': t_req(request, 'factory.done_full'),
        'plugins': removed,
        'login_required': True,
    })
    # 旧会话令牌在页面上已经没有意义：顺手清掉，避免浏览器带着它访问登录页
    from modules.auth.auth import clear_session_cookie
    clear_session_cookie(response)
    return response


@router.post('/api/factory/reset')
async def admin_factory_reset(request: Request):
    """执行一档恢复出厂操作；`mode` 与确认词都合法才会动手"""
    denied = super_admin_only(request)
    if denied:
        return denied
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)

    mode = (body.get('mode') or '').strip()
    if mode not in MODES:
        return error_response(t_req(request, 'factory.bad_mode'), 400)
    if (body.get('confirm') or '').strip() != CONFIRM_WORD:
        return error_response(
            t_req(request, 'factory.confirm_required', word=CONFIRM_WORD), 400)

    if not _OP_LOCK.acquire(blocking=False):
        return error_response(t_req(request, 'factory.busy'), 409)
    try:
        if mode == 'plugins':
            return await _reset_plugins(request)
        if mode == 'records':
            return await _reset_records(request)
        return await _reset_full(request)
    except Exception:
        plog.exception('恢复出厂设置失败')
        return error_response(t_req(request, 'factory.failed'), 500)
    finally:
        _OP_LOCK.release()
