"""进程自重启（`os.execv`）。

不依赖 systemd / Docker 的 Restart 策略：把当前进程镜像原地换成一份新的自己，
PID 不变、监听端口不换，对调用方就是「服务闪断一下又回来了」。适用于面板上点
「重启服务」和「更新后自动重启」两个场景。

执行顺序是有意的：**先置停机标志并 flush 收尾，再 execv**。execv 会立刻替换掉
整个进程镜像——事件循环、后台线程、未落库的内存计数全都随之消失，所以收尾必须
在它之前完成（会话闭合、日志队列落盘、统计增量刷库）。
"""
import os
import sys

from modules.utils import plog


def restart_process(app):
    """flush 收尾后原地重启进程。正常情况下**不返回**（进程已被新镜像替换）。

    只在 execv 失败时返回 False（例如可执行文件被删、权限不足），由调用方决定
    是否把失败反馈给用户——此时进程状态已被置为停机，调用方应避免继续提供服务。
    """
    # 先把重启命令算出来：拿不到（argv 不完整）时直接抛错，此时进程还没被置为停机，
    # 服务可以继续跑。放到收尾之后算就晚了——那时标志已置、收尾已做，却重启不了
    argv = _restart_argv()
    _prepare_shutdown(app)
    try:
        os.execv(argv[0], argv)
    except Exception:
        plog.exception('进程自重启失败，请手动重启服务')
        return False
    return True


def can_restart():
    """当前启动方式是否支持自重启。

    判断依据就是「能不能算出重启命令」：`run.py` 直启的部署拿得到 `sys.argv`，
    而被平台托管（Serverless / 用 `-c` 内嵌执行）的部署拿不到，后者点了重启只会
    换出一个什么都不做的新进程，不如提前拒绝。
    """
    try:
        _restart_argv()
        return True
    except RuntimeError:
        return False


def _prepare_shutdown(app):
    """停机收尾：与 console `exit` 命令走同一套（置标志 → flush）。"""
    try:
        app.state._shutdown = True
    except Exception:
        pass
    try:
        from modules import lifecycle
        lifecycle.flush_and_close(app)
    except Exception:
        plog.exception('重启前的收尾流程失败')


def _restart_argv():
    """重启命令：`sys.executable` + 原始 `sys.argv`。

    用 `sys.executable` 而不是字面量 `python`：部署里常见 venv / 系统 python 混用，
    写死名字会让重启后的进程换一个解释器（依赖装在那个 venv 里，换了就 import 失败）。
    `sys.argv[0]` 保留原样（`run.py` 这类相对路径），execv 不改变工作目录，相对路径仍然有效。
    """
    argv = [sys.executable] + list(sys.argv)
    # argv[0] 为空（被嵌入执行 / 用 -c 启动）时退化为交互式解释器，等于重启后不提供任何服务。
    # 这种部署本就不是 run.py 直启，明确拒绝比静默换成一个空进程好。
    if len(argv) < 2 or not argv[1]:
        raise RuntimeError('无法确定启动参数，不能自重启')
    return argv


__all__ = ['restart_process', 'can_restart']