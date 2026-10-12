"""框架侧进程日志：统一的格式与出口。

约定：普通信息只写消息本身，告警与错误带 `[WARN]` / `[ERROR]` 前缀，默认写 stdout。

请求日志是**另一条链路**——它进数据库、由面板查询（见 modules/database/logs.py）；
这里只管进程自身的诊断输出：启动提示、告警、异常堆栈。

刻意不打印时间：整行带时间戳只是噪声，而需要时间的话，容器 `docker logs -t`、
journald、面板里的请求日志/审计都各有一份更权威的时间（且那些是 UTC、能对得上）。

文件出口是可选的（`LOG_FILE` 留空 = 只写 stdout，即默认行为），由 run_core 启动期经
`attach_file()` 挂上，`LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` 控制轮转。容器与 systemd
部署建议交给 log driver / journald 收 stdout，那时不必再开文件轮转（见部署.md）。

告警与错误的**终端**出口由 `set_terminal_alerts()` 控制：启动阶段开着（初始化失败、
插件加载失败的堆栈必须当场看得见），启动信息打完由 run_core 关掉，此后终端只留
用户敲的命令输出；关掉不影响文件出口，问题一律去日志文件与面板里查。
"""
import logging
import os
import threading
import traceback
from logging.handlers import RotatingFileHandler

_FILE_LEVELS = {'INFO': logging.INFO, 'WARN': logging.WARNING, 'ERROR': logging.ERROR}

# 写 stdout 与写文件必须串行：请求线程、刷盘线程、调度循环都会打日志，
# 不串行的话行与行会交错，读起来对不上号
_lock = threading.Lock()
_handler = None

# 终端是否继续输出 WARN / ERROR：启动阶段开着，启动信息打完由 run_core 关掉。
# 只作用于终端，文件出口照写不误。
_terminal_alerts = True

# 文件出口用 logging 自己的 handler（RotatingFileHandler 的轮转与重开久经考验，
# 没必要手写一份）。它不挂到 root、也不向 root 传播——否则 root 没配 handler 时
# 会把消息丢给 lastResort 再往 stderr 打一份。
# 格式器原样输出：整行（含 WARN / ERROR 的级别前缀）已在 _write 里拼好，两处出口因此永远同构。
_file_logger = logging.getLogger('einkviews.plog')
_file_logger.setLevel(logging.INFO)
_file_logger.propagate = False
_raw_formatter = logging.Formatter('%(message)s')


def attach_file(path, max_bytes=0, backup_count=0):
    """挂文件日志出口；返回是否挂上。`path` 留空 = 只写 stdout（默认）。

    `max_bytes` <= 0 = 不按大小轮转（文件一直追加）；> 0 时按该字节数轮转，
    保留 `backup_count` 份历史（0 = 不留历史，超出即清空当前文件）。

    重复调用替换旧出口：run_core 在 create_app 前后各调一次——面板里的配置覆盖要等
    create_app 内部应用完才生效，只挂一次就漏掉了面板设的路径。
    """
    global _handler
    handlers = []
    if path:
        try:
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            if max_bytes and int(max_bytes) > 0:
                handler = RotatingFileHandler(
                    path, maxBytes=int(max_bytes),
                    backupCount=max(0, int(backup_count or 0)), encoding='utf-8')
            else:
                handler = logging.FileHandler(path, encoding='utf-8')
            handler.setFormatter(_raw_formatter)
            handlers.append(handler)
        except (OSError, TypeError, ValueError) as exc:
            # 出口挂不上不该拦住启动：退化成只写 stdout，并把原因说清楚
            warn(f'日志文件出口挂载失败，仅写 stdout：{exc}')
    with _lock:
        old = _handler
        _file_logger.handlers[:] = list(handlers)
        _handler = handlers[0] if handlers else None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    return _handler is not None


def set_terminal_alerts(enabled):
    """开关终端上的 WARN / ERROR 输出（文件出口不受影响）。

    run_core 在启动信息打完后关掉：终端只留启动信息与用户敲的命令，
    告警与错误仍进日志文件，需要时去日志文件或面板查。
    """
    global _terminal_alerts
    _terminal_alerts = bool(enabled)


def _write(level, message):
    # INFO 是最常态的一档，前缀纯属噪声；WARN / ERROR 留 `[级别]`，好让问题行在一屏里跳出来
    text = message if level == 'INFO' else f'[{level}] {message}'
    with _lock:
        # flush=True：容器/管道下 stdout 是块缓冲，不刷就看不到实时日志
        if level == 'INFO' or _terminal_alerts:
            print(text, flush=True)
        if _handler is not None:
            _file_logger.log(_FILE_LEVELS[level], text)


def info(message):
    """启动提示、状态变化等常规信息"""
    _write('INFO', message)


def warn(message):
    """需要注意但不影响继续运行的情况（配置缺失、能力降级等）"""
    _write('WARN', message)


def error(message):
    """失败但已兜住的情况"""
    _write('ERROR', message)


def exception(message=''):
    """ERROR + 当前异常堆栈，**必须在 except 块内调用**。

    取代 `traceback.print_exc()`：后者不带级别、也不进日志文件。
    """
    detail = traceback.format_exc().rstrip()
    _write('ERROR', f'{message}\n{detail}' if message else detail)