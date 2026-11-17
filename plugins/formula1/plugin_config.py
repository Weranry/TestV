"""插件默认配置。

元信息（名称、版本、描述、作者、最低框架版本、依赖）的唯一来源是 `plugin.json`，
本文件只放**真正会被请求读到的默认值**；面板「插件配置」弹窗列出的就是这里的配置项。
"""

# 配置项的可读名称与说明（面板「插件配置」弹窗用）。
CONFIG_LABELS = {
    "DEFAULT_ARGS": {
        "label": "默认参数",
        "desc": "视图 / JSON 的默认查询参数；URL 显式传了的参数以 URL 为准",
    },
    "DEFAULT_ROTATE": {
        "label": "默认旋转角度",
        "desc": "0 / 90 / 180 / 270；URL 传了 rotate 时以 URL 为准",
    },
    "DEFAULT_INVERT": {
        "label": "默认反色",
        "desc": "开启后默认反色显示；URL 传了 invert 时以 URL 为准",
    },
}

# 参数表必须是扁平的：框架在 resolve_view_params() 里直接 update 合并。
# round：next（默认，下一站）/ last（当前赛季最后一站）/ 站号整数（如 18）
# tz：站次时间的显示时区，留空则按框架默认时区
DEFAULT_ARGS = {
    "round": "next",
    "tz": None,
}
DEFAULT_ROTATE = 0
DEFAULT_INVERT = False
