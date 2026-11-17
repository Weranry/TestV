# Open-Meteo 天气插件

基于 [Open-Meteo](https://open-meteo.com/) 免密钥天气 API 的墨水屏天气插件，提供两种视图：

- `current`：实况天气卡（大温度 + 图标 + 湿度/风力/气压/降水 + 日出日落）
- `forecast`：多日预报（等宽分栏，星期/图标/天气名/高低温/降水概率）

天气图标使用根目录 `assets/fonts/weather-icon.ttf`。注意该字体的 cmap 字形名（墨迹编号）与**实际形状不符**（名为「阵雨」的是月亮、「小雪」的是雨），因此 `lib/wmo_codes.py` 按逐个渲染核对后的**实际字形**映射 WMO 码，并支持夜间月亮变体（实况视图按 `is_day` 切换）。

## 参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `city` | str | `北京` | 城市名（中文可用），走 Open-Meteo 地理编码 |
| `lat` / `lon` | float | 无 | 直接指定经纬度；两者都传时忽略 `city` |
| `days` | int | `3` | 预报天数（1~7），影响 `forecast` 视图列数与 `current` 的逐日数据 |
| `host` | str | `api.open-meteo.com` | 预报端点域名；网络只放行镜像实例时可换 `0.api.open-meteo.com` 等 |

框架通用参数（`size` / `rotate` / `invert` / `cmode` / `format` / `tz`）照常可用。

## 测试链接

```text
http://127.0.0.1:5000/openmeteo/view/current?size=hxl&city=北京
http://127.0.0.1:5000/openmeteo/view/current?size=h2xl&city=上海
http://127.0.0.1:5000/openmeteo/view/forecast?size=hxl&city=北京&days=3
http://127.0.0.1:5000/openmeteo/view/forecast?size=h2xl&city=广州&days=5
http://127.0.0.1:5000/openmeteo/json/weatherjson?city=北京
```

## 结构

```text
openmeteo/
├── routes.py               # 路由装配
├── plugin.json             # 元信息
├── plugin_config.py        # 默认参数 + VIEW_ARGS_SCHEMA
├── lib/
│   ├── fetcher.py          # 地理编码 + 预报取数（异步给视图、同步给 JSON）
│   └── wmo_codes.py        # WMO 码 → 中文名 + 图标码点
├── json_module/
│   └── weatherjson.py      # 结构化 JSON 输出
└── view/
    ├── common.py           # 共用排版原语（墨迹对齐、图标居中、指标列）
    ├── current/            # 实况卡：hxl / h2xl 独立坐标
    └── forecast/           # 多日预报：hxl / h2xl 独立坐标
```

## 排版约定

- **文字字号只允许 16 的倍数**（16/32/48/64/80/96，项目硬性约定）：层级靠字号差与留白拉开，不靠小字；窄列（≥6 栏）整体降一档而不是缩字号。图标字体不受此限，按版面需要任意缩放
- 所有文字按**墨迹包围盒**落位（`view/common.py` 的 `draw_at` 系列），避免 CJK/数字/图标字体的字身框偏差造成的视觉错位
- 红色（`fill=2`）只做点缀：温度单位、最高温；大面积文字保持黑色，`cmode=bw` 下层级不塌
- 图标一律按墨迹框居中（`draw_icon`），不同天气图形的留白差异不会破坏对齐
- 超宽文本自动逐字截断补 `…`（`fit_text`），窄列（7 日预报）不越界

## 注意事项

- 地理编码域名（`geocoding-api.open-meteo.com`）与预报域名（`api.open-meteo.com`）是不同端点；若部署网络只放行其一，用 `host` 参数切换镜像实例
- 所有请求带 10s 超时；取数失败返回 4xx 参数错误，不产出半成品图
