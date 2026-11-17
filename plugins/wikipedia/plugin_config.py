"""插件默认配置。

元信息（名称、版本、描述、作者、最低框架版本、依赖）的唯一来源是 `plugin.json`，
本文件只放**真正会被请求读到的默认值**；面板「插件配置」弹窗列出的就是这里的配置项。
"""

# 配置项的可读名称与说明（面板「插件配置」弹窗用）。
# 未登记的键回落到显示原始键名，所以新增配置项时记得在这里补一行。
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

# page_url：中文维基百科桌面版首页。网络无法直连时，可改指到可访问的镜像站
#           （页面需保持 mp-2012 版式，解析按区块 id 定位）。
# tz：日期标头与页脚时间的显示时区，留空则按框架默认时区。
DEFAULT_ARGS = {
    "page_url": "https://zh.wikipedia.org/zh-cn/Wikipedia:%E9%A6%96%E9%A1%B5",
    "tz": None,
}
DEFAULT_ROTATE = 0
DEFAULT_INVERT = False
