# Lunar

将当天公历、农历、干支纪年与黄历信息渲染到墨水屏，另有黄历宜忌与 JSON 数据接口。

## 功能特性

- **纯本地日期计算**：全部数据由 `lunar-python` 在本地算出，无网络请求、无 API key。
- **日历视图（`rili`）**：公历日期 + 星期、农历日期、干支纪年 / 月 / 日与生肖、数九或伏、物候与节气、节日，并放大了阳历「日」。
- **黄历视图（`huangli` / `huangliA`）**：`huangli` 展示喜神 / 福神 / 财神等吉神方位、太岁 / 胎神、冲煞、二十八宿与彭祖百忌；`huangliA` 以「宜 / 忌」列表为主，附干支与星座。
- **多尺寸自适应**：同一视图按画布尺寸切换字号与排版，覆盖横屏、竖屏与正方形。

## 数据来源

完全没有网络请求，日期与黄历数据由本地库 [`lunar-python`](https://pypi.org/project/lunar-python/) 现算：
公历 / 农历 / 干支 / 生肖来自 `Solar` / `Lunar`，宜忌、吉神、彭祖百忌、二十八宿等来自 `Lunar` 的黄历接口。
时区由 `tz` 参数决定，换日以该时区的「今天」为准。

## 支持的尺寸

| 视图 | size | 分辨率 | 方向 |
| :--- | :--- | :--- | :--- |
| `rili` | `m` | 200×200 | 正方形 |
| `rili` | `hxl` | 384×184 | 横屏 |
| `rili` | `h2xl` | 400×300 | 横屏 |
| `rili` | `vxl` | 184×384 | 竖屏 |
| `rili` | `v2xl` | 300×400 | 竖屏 |
| `huangli` | `hxl` | 384×184 | 横屏 |
| `huangli` | `h2xl` | 400×300 | 横屏 |
| `huangliA` | `hxl` | 384×184 | 横屏 |
| `huangliA` | `h2xl` | 400×300 | 横屏 |

调色板固定为 `bwr`（黑 / 白 / 红，节日信息用红色）。

## 配置参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `tz` | string | 否 | 框架默认 | 计算「今天」用的时区，如 `8` 或 `Asia/Shanghai` |

## 快速预览链接

在运行主程序后，可直接点击查看效果：

**日历 `rili`：**
[http://127.0.0.1:5000/lunar/view/rili?size=m](http://127.0.0.1:5000/lunar/view/rili?size=m)
[http://127.0.0.1:5000/lunar/view/rili?size=hxl](http://127.0.0.1:5000/lunar/view/rili?size=hxl)
[http://127.0.0.1:5000/lunar/view/rili?size=h2xl](http://127.0.0.1:5000/lunar/view/rili?size=h2xl)
[http://127.0.0.1:5000/lunar/view/rili?size=vxl](http://127.0.0.1:5000/lunar/view/rili?size=vxl)
[http://127.0.0.1:5000/lunar/view/rili?size=v2xl](http://127.0.0.1:5000/lunar/view/rili?size=v2xl)

**黄历 `huangli`：**
[http://127.0.0.1:5000/lunar/view/huangli?size=hxl](http://127.0.0.1:5000/lunar/view/huangli?size=hxl)
[http://127.0.0.1:5000/lunar/view/huangli?size=h2xl](http://127.0.0.1:5000/lunar/view/huangli?size=h2xl)

**黄历宜忌 `huangliA`：**
[http://127.0.0.1:5000/lunar/view/huangliA?size=hxl](http://127.0.0.1:5000/lunar/view/huangliA?size=hxl)
[http://127.0.0.1:5000/lunar/view/huangliA?size=h2xl](http://127.0.0.1:5000/lunar/view/huangliA?size=h2xl)

**JSON 数据：**
[http://127.0.0.1:5000/lunar/json/datejson](http://127.0.0.1:5000/lunar/json/datejson)

## 目录结构

```text
lunar/
├── __init__.py
├── README.md
├── plugin.json
├── plugin_config.py
├── routes.py
├── lib/
│   ├── date_calculator.py     # 公历 / 农历 / 干支 / 节气 / 节日
│   ├── today_huangli.py       # 黄历（吉神 / 太岁 / 冲煞 / 二十八宿 / 彭祖百忌）
│   └── today_huangli_A.py     # 黄历（宜 / 忌 + 星座）
├── json_module/
│   └── datejson.py            # /lunar/json/datejson
└── view/
    ├── rili/                  # m / hxl / h2xl / vxl / v2xl
    ├── huangli/               # hxl / h2xl
    └── huangliA/              # hxl / h2xl
```
