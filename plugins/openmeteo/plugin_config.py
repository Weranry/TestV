"""openmeteo 插件默认配置。

元信息唯一来源是 `plugin.json`；这里只放会被请求读到的默认值与参数声明。
"""

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

DEFAULT_ARGS = {
    "city": "北京",
    "lat": None,
    "lon": None,
    "days": 3,
    "host": None,
    "tz": None,
}
DEFAULT_ROTATE = 0
DEFAULT_INVERT = False

# 业务参数声明：入口强转 + 范围校验，避免类型错误拖到渲染层才炸
VIEW_ARGS_SCHEMA = {
    "city": {"type": "str", "label": "城市名", "description": "支持中文，走 Open-Meteo 地理编码；传了 lat/lon 时忽略"},
    "lat": {"type": "float", "label": "纬度", "min": -90, "max": 90},
    "lon": {"type": "float", "label": "经度", "min": -180, "max": 180},
    "days": {"type": "int", "label": "预报天数", "min": 1, "max": 7, "default": 3},
    "host": {"type": "str", "label": "预报端点域名",
             "description": "默认 api.open-meteo.com；网络不通时可换 0.api.open-meteo.com 等镜像实例"},
}
