"""备份与恢复：整库导出下载 / 上传一份备份整体替换当前库。

为什么要有面板入口：原先前置条件是管理员能登服务器敲一条 `sqlite3 .backup`，
而实际部署里（容器、面板托管）多数人拿不到 shell；等库损坏了再去开 shell 已经太晚。

导出用 sqlite3 官方的 `Connection.backup()`：它按页拷贝，并在源库仍在写入时自动重来，
拿到的是一致性快照。**不用 `VACUUM INTO`**——项目明确禁止 `VACUUM`（会复位
`sqlite_sequence`，让用户组/账号编号被重新复用，静默串号）。

恢复是**整体替换**：先把当前库自动备份到 `data/backups/`（后悔药），再换文件、重建连接、
逐项重载内存态（见 `lifecycle.reload_after_restore`）。

上传走**原始二进制 body**而不是 multipart：multipart 需要额外依赖 `python-multipart`，
而项目对新增依赖是收紧的；两端都是自家代码，直接 POST 文件字节最省事。
"""
import asyncio
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

import config
from modules.errors.errors import error_response
from modules.i18n.registry import t_req
from modules.utils import body_limit
from modules.utils import plog

router = APIRouter()

# SQLite 文件头（前 16 字节）。先看魔数能挡掉绝大多数误传（图片、zip、导出的 CSV）
_SQLITE_MAGIC = b'SQLite format 3\x00'

# 恢复出来的库必须含这两张表，否则换上去等于把服务打瘫（连登录都做不到）
_REQUIRED_TABLES = ('user_groups', 'accounts')


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _backups_dir(db_file):
    """备份目录：与数据库同目录的 backups/，跟随 set_db_path 的重定向（测试可用）"""
    path = os.path.join(os.path.dirname(db_file), 'backups')
    os.makedirs(path, exist_ok=True)
    return path


def _stamp():
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def _size_text(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{int(n)} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _copy_db(src_file, dst_file):
    """一致性快照：源库仍在被写入也安全（backup API 会在页被改动时重来）"""
    src = sqlite3.connect(src_file)
    try:
        dst = sqlite3.connect(dst_file)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _list_backups(backups_dir):
    items = []
    try:
        names = os.listdir(backups_dir)
    except OSError:
        return items
    for name in names:
        full = os.path.join(backups_dir, name)
        if not os.path.isfile(full):
            continue
        try:
            st = os.stat(full)
        except OSError:
            continue
        items.append({
            'name': name,
            'size': st.st_size,
            'size_text': _size_text(st.st_size),
            # 统一给 UTC ISO：面板的 fmtDT 会换算到配置时区
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(st.st_mtime)),
        })
    items.sort(key=lambda i: i['created_at'], reverse=True)
    return items


def _age_days(created_at):
    """备份距今多少天（created_at 是 _list_backups 写的 UTC ISO）；解析不了按 0 天算。

    「现在」用项目统一的 utc_now_iso() 取，避免各处自己拼时间格式。
    """
    from modules.utils.timezone import utc_now_iso
    try:
        made = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ')
        now = datetime.strptime(utc_now_iso()[:19], '%Y-%m-%dT%H:%M:%S')
    except (TypeError, ValueError):
        return 0
    return max(0, (now - made).days)


def _backup_path(backups_dir, name):
    """把请求里的文件名解析成目录内的真实文件；非法或不存在返回 None。

    删文件是唯一一个拿用户输入直接拼路径的地方：只接受**单段文件名**且必须已经存在于
    目录里（拒绝 `..`、路径分隔符与 URL 编码进来的 `%2F`），越界与不存在的都当 404。
    """
    if not name or name in ('.', '..') or name != os.path.basename(name):
        return None
    if os.sep in name or (os.altsep and os.altsep in name):
        return None
    full = os.path.join(backups_dir, name)
    return full if os.path.isfile(full) else None


def cleanup_backups(db_file):
    """按保留策略清理 `data/backups/`，返回删除的份数。

    `BACKUP_KEEP_COUNT` / `BACKUP_KEEP_DAYS` 都是 0 = 不限，两个都设了就按「超出任一即删」
    处理（留最近 N 份，且不超过 M 天）。这个目录只进不出，必须有个自动兜底，否则每次恢复
    留一份快照、迟早把磁盘吃满。只删这个目录里的文件，下载导出走系统临时目录、不经过这里。
    """
    keep_count = int(getattr(config, 'BACKUP_KEEP_COUNT', 0) or 0)
    keep_days = int(getattr(config, 'BACKUP_KEEP_DAYS', 0) or 0)
    if keep_count <= 0 and keep_days <= 0:
        return 0
    backups_dir = _backups_dir(db_file)
    deleted = 0
    # _list_backups 已按时间倒序，下标即"第几新"
    for idx, item in enumerate(_list_backups(backups_dir)):
        over_count = keep_count > 0 and idx >= keep_count
        over_days = keep_days > 0 and _age_days(item['created_at']) > keep_days
        if not (over_count or over_days):
            continue
        try:
            os.remove(os.path.join(backups_dir, item['name']))
            deleted += 1
        except OSError:
            pass
    return deleted


def _validate_backup(path, request=None):
    """校验上传的备份是否可用，返回错误文案（None = 通过）"""
    try:
        # 只读方式打开：校验过程绝不能改动或创建出 `-wal` / `-shm` 之类的旁挂文件
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    except sqlite3.Error as exc:
        return t_req(request, 'backup.open_failed', err=exc)
    try:
        try:
            row = conn.execute('PRAGMA integrity_check').fetchone()
        except sqlite3.Error as exc:
            return t_req(request, 'backup.corrupt', err=exc)
        if not row or str(row[0]).lower() != 'ok':
            return t_req(request, 'backup.integrity_failed',
                         result=row[0] if row else t_req(request, 'backup.no_result'))
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.Error as exc:
        return t_req(request, 'backup.not_sqlite', err=exc)
    finally:
        conn.close()
    missing = [t for t in _REQUIRED_TABLES if t not in names]
    if missing:
        return t_req(request, 'backup.missing_tables', tables='、'.join(missing))
    return None


async def _commit_restore(request, db_file, staged):
    """把已通过校验的 `staged`（必须与 db_file 同盘）整体换成当前库。

    上传恢复与「用 data/backups/ 里的快照恢复」共用这一段，差别只在 staged 从哪来。

    先落盘内存里排队的日志与统计：落库目标由连接决定，换完库再刷就会把这些旧记录写进
    刚恢复出来的库里。再留一份后悔药快照，最后换文件并重建全部内存态。

    返回 `(错误响应, 自动快照文件名)`；错误响应非 None 表示中止，`staged` 由调用方清理。
    """
    from modules import lifecycle
    try:
        lifecycle.persist_counters(request.app)
        lifecycle.persist_account_usage(request.app)
    except Exception:
        plog.exception('恢复前落盘统计数据失败')
    try:
        from modules.database.logs import flush_log_queue
        flush_log_queue()
    except Exception:
        plog.exception('恢复前落盘请求日志失败')

    # 后悔药：先把当前库快照进 data/backups/，恢复错了还能把文件捞回来
    auto_path = os.path.join(_backups_dir(db_file), f'einkviews-auto-{_stamp()}.db')
    try:
        if os.path.exists(db_file):
            await asyncio.to_thread(_copy_db, db_file, auto_path)
    except Exception:
        plog.exception('恢复前的自动备份失败')
        return error_response(t_req(request, 'backup.auto_snapshot_failed'), 500), None

    # 顺手按保留策略清一次：新快照刚落地，正是份数/占用会增长的时刻，
    # 不必等后台线程那一轮。失败不影响恢复本身（策略只在"超出"时才删，删的是更旧的）
    try:
        await asyncio.to_thread(cleanup_backups, db_file)
    except Exception:
        plog.exception('清理过期备份失败')

    from modules.database import core
    try:
        with core._db_lock:
            # 闭连接用 _close_pool_locked（调用方持锁版）：close_connection() 会再取一次
            # 同一把非重入锁，在这里调就是死锁
            core._close_pool_locked()
            # 只读池也要整体作废：里面的连接仍绑定在即将被替换掉的旧文件上
            core._close_read_pool_locked()
            # 正常关闭时 SQLite 会 checkpoint 并删掉 -wal/-shm；这里再显式清一次，
            # 万一是异常退出留下的残留 WAL，拼到新库上会直接读成"库损坏"
            for suffix in ('-wal', '-shm'):
                _unlink(db_file + suffix)
            os.replace(staged, db_file)
    except OSError as exc:
        plog.exception('替换数据库文件失败')
        return error_response(t_req(request, 'backup.replace_failed', err=exc), 500), None

    lifecycle.reload_after_restore(request.app)
    return None, os.path.basename(auto_path)


def _run_auto_backup(db_file):
    """执行一次自动备份，返回错误文案（'' = 成功）。

    同步函数，由调度循环下放线程调用（见 `_auto_backup_step`）。
    """
    if not os.path.exists(db_file):
        return '数据库文件不存在'
    target = os.path.join(_backups_dir(db_file), f'einkviews-sched-{_stamp()}.db')
    try:
        _copy_db(db_file, target)
    except Exception as exc:
        plog.exception('自动备份失败')
        return f'自动备份失败：{exc}'
    try:
        cleanup_backups(db_file)
    except Exception:
        plog.exception('清理过期备份失败')
    return ''


def _auto_backup_step():
    """自动备份的完整一轮（同步）：判断是否到点 → 备份 → 记录。

    整段都跑在 worker 线程里（见 maybe_run_scheduled_backup）：里面的查库、拷库、
    写 server_info 全是同步 IO，放在事件循环里会卡住正在出图的请求。
    """
    from modules.database.core import is_db_available, db_path
    from modules.database.stats import get_server_info, set_server_info
    from modules.prerender.scheduler import last_daily_occurrence

    try:
        enabled = int(getattr(config, 'BACKUP_AUTO_ENABLE', 0) or 0)
    except (TypeError, ValueError):
        enabled = 0
    if enabled <= 0 or not is_db_available():
        return None
    db_file = db_path()
    if not db_file:
        return None
    occurrence = last_daily_occurrence(getattr(config, 'BACKUP_AUTO_TIMES', ''))
    if not occurrence:
        return None
    served = get_server_info('backup_auto_last') or ''
    # ISO 字符串（秒精度 + Z）字典序即时间序，直接比大小即可
    if occurrence <= served:
        return None
    error = _run_auto_backup(db_file)
    set_server_info('backup_auto_last', occurrence)
    set_server_info('backup_auto_error', error or '')
    if error:
        # 失败也记已处理：不记的话调度循环每 10 秒就重试一次，磁盘满这类持续性故障
        # 会变成高频失败风暴
        plog.error(f'[备份] {error}')
    return occurrence


async def maybe_run_scheduled_backup():
    """调度循环每轮调用一次；由 leader 实例执行（见 prerender.scheduler.scheduler_loop）"""
    await asyncio.to_thread(_auto_backup_step)


def _auto_backup_info():
    """面板要的自动备份状态（同步查库，调用方负责放线程）"""
    from modules.database.stats import get_server_info

    try:
        enabled = int(getattr(config, 'BACKUP_AUTO_ENABLE', 0) or 0)
    except (TypeError, ValueError):
        enabled = 0
    return {
        'auto_enabled': enabled,
        'auto_times': str(getattr(config, 'BACKUP_AUTO_TIMES', '') or ''),
        'auto_last': get_server_info('backup_auto_last') or '',
        'auto_error': get_server_info('backup_auto_error') or '',
    }


@router.get('/api/backup/info')
async def admin_backup_info(request: Request = None):
    """库大小、备份列表与占用、上传上限、自动备份状态"""
    from modules.database.core import is_db_available, db_path, db_file_size
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)
    db_file = db_path()
    if not db_file:
        return error_response(t_req(request, 'backup.db_path_unavailable'), 500)
    size = db_file_size()
    # 列目录要逐个 stat，量小但仍是 IO，放线程里做，别占着事件循环
    backups = await asyncio.to_thread(_list_backups, _backups_dir(db_file))
    # 备份目录的保留策略见 config.BACKUP_KEEP_COUNT；占用空间也要摆到面板上，
    # 这份数只增不减时磁盘吃紧才看得见
    backups_size = sum(b['size'] for b in backups)
    payload = {
        'db_size': size,
        'db_size_text': _size_text(size),
        'backups_size': backups_size,
        'backups_size_text': _size_text(backups_size),
        'upload_max_mb': int(getattr(config, 'BACKUP_UPLOAD_MAX_MB', 64) or 0),
        'backups': backups,
    }
    payload.update(await asyncio.to_thread(_auto_backup_info))
    return JSONResponse(payload)


def _require_db(request=None):
    """各接口统一的库可用性前置检查，返回 (db_file, 错误响应)"""
    from modules.database.core import is_db_available, db_path
    if not is_db_available():
        return None, error_response(t_req(request, 'config.db_unavailable'), 400)
    db_file = db_path()
    if not db_file:
        return None, error_response(t_req(request, 'backup.db_path_unavailable'), 500)
    return db_file, None


@router.delete('/api/backup/files/{name}')
async def admin_backup_delete_file(name: str, request: Request = None):
    """删除 `data/backups/` 下的一份备份（文件名取自列表，越界与不存在的都当 404）"""
    db_file, err = _require_db(request)
    if err:
        return err
    path = _backup_path(_backups_dir(db_file), name)
    if not path:
        return error_response(t_req(request, 'backup.file_not_found'), 404)
    try:
        os.remove(path)
    except OSError as exc:
        plog.exception(f'删除备份文件失败: {name}')
        return error_response(t_req(request, 'backup.delete_failed', err=exc), 500)
    return JSONResponse({'success': True, 'message': t_req(request, 'backup.deleted')})


@router.get('/api/backup/files/{name}/download')
async def admin_backup_download_file(name: str, request: Request = None):
    """下载 data/backups/ 里的一份快照。

    与 `/api/backup/download`（导出**当前**库到临时文件）不同，这里直接流式返回目录里
    的正式文件，所以**不能**挂后台删除任务——那份快照要留在原地继续可用。
    """
    db_file, err = _require_db(request)
    if err:
        return err
    path = _backup_path(_backups_dir(db_file), name)
    if not path:
        return error_response(t_req(request, 'backup.file_not_found'), 404)
    return FileResponse(path, filename=name, media_type='application/octet-stream')


@router.post('/api/backup/files/{name}/restore')
async def admin_backup_restore_file(name: str, request: Request):
    """用 data/backups/ 里的一份快照整体替换当前库（不必先下载再上传）"""
    db_file, err = _require_db(request)
    if err:
        return err
    src = _backup_path(_backups_dir(db_file), name)
    if not src:
        return error_response(t_req(request, 'backup.file_not_found'), 404)
    # 完整性校验要扫全库（integrity_check），同步跑会卡住事件循环
    reason = await asyncio.to_thread(_validate_backup, src, request)
    if reason:
        return error_response(reason, 400)

    # 先复制到同盘的临时文件再替换：快照本身要留在 backups/ 里，恢复错了还能再用它
    fd, staged = tempfile.mkstemp(prefix='einkviews-restore-', suffix='.db',
                                  dir=os.path.dirname(db_file))
    os.close(fd)
    try:
        await asyncio.to_thread(shutil.copyfile, src, staged)
        err, auto_name = await _commit_restore(request, db_file, staged)
        if err:
            return err
    except Exception:
        plog.exception('用历史快照恢复失败')
        return error_response(t_req(request, 'backup.restore_error'), 500)
    finally:
        _unlink(staged)

    return JSONResponse({
        'success': True,
        'message': t_req(request, 'backup.restored'),
        'auto_backup': auto_name,
        'restored': name,
    })


@router.post('/api/backup/cleanup')
async def admin_backup_cleanup(request: Request = None):
    """按保留策略立刻清理一次（保留份数 / 天数都在「备份配置」里改，0 = 不限）"""
    db_file, err = _require_db(request)
    if err:
        return err
    deleted = await asyncio.to_thread(cleanup_backups, db_file)
    if deleted <= 0:
        return JSONResponse({'success': True, 'message': t_req(request, 'backup.nothing_to_clean'), 'deleted': 0})
    return JSONResponse({'success': True, 'message': t_req(request, 'backup.cleaned_n', n=deleted), 'deleted': deleted})


@router.get('/api/backup/download')
async def admin_backup_download(request: Request = None):
    """导出一致性快照并直接下载；临时文件由响应流读完后的后台任务删除"""
    db_file, err = _require_db(request)
    if err:
        return err
    if not os.path.exists(db_file):
        return error_response(t_req(request, 'backup.db_missing'), 404)

    fd, tmp = tempfile.mkstemp(prefix='einkviews-export-', suffix='.db')
    os.close(fd)
    try:
        # 整库拷贝是纯同步 IO（几十 MB 量级要几百毫秒），必须下放线程：占着事件循环
        # 期间同一进程里正在出图的设备请求会一起被卡住
        await asyncio.to_thread(_copy_db, db_file, tmp)
    except Exception:
        plog.exception('导出数据库快照失败')
        _unlink(tmp)
        return error_response(t_req(request, 'backup.export_error'), 500)

    # 删除必须挂在 background 上：FileResponse 是流式读文件的，在 handler 的 finally 里删
    # 会把还没读的文件先删掉，客户端拿到 0 字节
    return FileResponse(
        tmp,
        filename=f'einkviews-{_stamp()}.db',
        media_type='application/octet-stream',
        background=BackgroundTask(_unlink, tmp),
    )


@router.post('/api/backup/restore')
async def admin_backup_restore(request: Request):
    """上传备份并整体替换当前库。成功后必须重新登录（恢复出的账号体系可能完全不同）"""
    db_file, err = _require_db(request)
    if err:
        return err

    # 上限判定与全局请求体上限共用同一份实现（见 modules.utils.body_limit）：
    # 先看 Content-Length 再读 body，等 body 全读进内存再判，这个上限就防不住内存
    # （浏览器选大文件一定会带这个头）。没有该头（分块上传）时读完后下面还会再判一次。
    limit = body_limit.limit_bytes(getattr(config, 'BACKUP_UPLOAD_MAX_MB', 64))
    if body_limit.exceeds(limit, declared=body_limit.declared_length(request.headers)):
        return error_response(t_req(request, 'backup.file_too_large', mb=limit // body_limit.MB), 400)

    try:
        raw = await request.body()
    except Exception:
        return error_response(t_req(request, 'backup.read_failed'), 400)

    if body_limit.exceeds(limit, actual=len(raw)):
        return error_response(t_req(request, 'backup.file_too_large', mb=limit // body_limit.MB), 400)
    if not raw:
        return error_response(t_req(request, 'backup.upload_empty'), 400)
    if not raw.startswith(_SQLITE_MAGIC):
        return error_response(t_req(request, 'backup.not_sqlite_magic'), 400)

    # 临时文件必须落在 data/ 内：os.replace 要求同盘，跨盘会退化成复制或直接失败
    fd, tmp = tempfile.mkstemp(prefix='einkviews-restore-', suffix='.db',
                               dir=os.path.dirname(db_file))
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(raw)
        # 完整性校验要扫全库（integrity_check），同步跑会卡住事件循环
        reason = await asyncio.to_thread(_validate_backup, tmp, request)
        if reason:
            return error_response(reason, 400)
        err, auto_name = await _commit_restore(request, db_file, tmp)
        if err:
            return err
    except Exception:
        plog.exception('上传恢复失败')
        return error_response(t_req(request, 'backup.restore_error'), 500)
    finally:
        _unlink(tmp)

    return JSONResponse({
        'success': True,
        'message': t_req(request, 'backup.restored'),
        'auto_backup': auto_name,
    })