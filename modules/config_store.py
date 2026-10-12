"""全局配置覆盖的读写 + 运行模式约束。

数据库 config_overrides 表中持久化的配置项，需要同时应用到运行中的 config 模块。
这段逻辑原先在 app_core（启动加载）和 admin_routes（保存/重置）里各写了一份。

运行模式（dev / prod / vercel）对个别配置有强制约束，例如 dev 必须关闭鉴权、
prod/vercel 的 AUTH_ENABLE 以环境变量为准。这份裁定**不能只在启动时做一次**：
面板保存配置或重置配置都会重新套用覆盖项，必须再裁定一次，否则 dev 模式会被数据库里
残留的 AUTH_ENABLE=True 静默打开鉴权（全站 401）。
"""
import os

from modules.utils.config_value import parse_config_value

_MODE = None


def set_mode(mode):
    """记录当前进程的运行模式（app_core 启动时调用一次）"""
    global _MODE
    _MODE = mode


def get_mode():
    """当前进程的运行模式（dev / prod / vercel），未初始化时返回 None"""
    return _MODE


def enforce_mode_constraints():
    """按运行模式强制约束被模式接管的配置项。

    dev 恒为关（本地调试必须跳过鉴权）；prod / vercel 一律以环境变量 AUTH_ENABLE
    为准，未设置时默认开启。

    这两个模式必须**无视数据库里的配置覆盖**：AUTH_ENABLE 归环境变量独占。否则在
    dev 面板里随手关过一次鉴权，同一条覆盖项就会被带到 prod，让 prod 静默变成
    「无需鉴权」，而管理 API 的授权检查依赖注入的登录态，届时会一并敞开。
    """
    import config
    if _MODE == 'dev':
        config.AUTH_ENABLE = False
        return
    env = os.environ.get('AUTH_ENABLE')
    config.AUTH_ENABLE = True if env is None else env.lower() not in ('0', 'false', 'no')


def apply_overrides():
    """把数据库中的配置覆盖全部应用到 config 模块"""
    import config
    from modules.database.states import get_config_overrides
    for key, val in get_config_overrides().items():
        setattr(config, key, parse_config_value(val))
    enforce_mode_constraints()


def apply_one(key, value):
    """应用单个配置覆盖到 config 模块（不落库）"""
    import config
    setattr(config, key, parse_config_value(value))
    enforce_mode_constraints()


def reload_and_apply():
    """重置某项后：先把 config 模块恢复成文件里的默认值，再重新套用剩余覆盖项"""
    import importlib
    import config
    importlib.reload(config)
    apply_overrides()