# Steam

把 Steam 玩家统计渲染到墨水屏：等级（LEVEL）、总时长（HOURS）、游戏数（GAMES）、
最后在线时间与最近两周常玩的游戏列表。

## 功能特性

- **三列数据网格**：等级 / 总时长 / 游戏数横向排布，带竖向分栏线，数值列内居中。
- **顶部标题**：红色 `STEAM` 字样 + 昵称；昵称过长时自动截断加省略号，不会顶出画布。
- **最后在线时间**：右上角对齐显示；放不下时自动缩写成 `在线: ...`。
- **最近常玩列表**：按近两周游玩时长列出，超出画布高度的条目自动截断（不越界绘制）。
- **横竖屏自适应**：字号按画布宽度分档（16 的整数倍），同一套渲染逻辑覆盖横屏与竖屏。

## 数据来源

全部来自 Steam 官方 Web API（`https://api.steampowered.com`），共四次请求：
`GetRecentlyPlayedGames`（最近两周）、`GetOwnedGames`（总时长 / 游戏数）、
`GetSteamLevel`（等级）、`GetPlayerSummaries`（昵称 / 最后在线）。

需要两个凭据：

- `api_key`：Steam Web API Key，申请入口 <https://steamcommunity.com/dev/apikey>
- `steam_id`：目标账号的 Steam 64 位 ID

**凭据如何提供**：本插件不在任何文件里内置密钥或 SteamID。二者按原有方式从请求的
URL 查询参数读取（`?api_key=...&steam_id=...`），也可以管理面板「插件配置」里把
`DEFAULT_ARGS` 的 `api_key` / `steam_id` 预置为默认值，之后 URL 里就不必再带。
本插件不读取任何环境变量。查询参数缺失时请求返回 400。

每次请求之间有 0.3s 间隔以规避频率限制；上游超时 / 连接失败按「取数失败」抛错。

## 支持的尺寸

| size | 分辨率 | 方向 | 对应屏幕 |
| :--- | :--- | :--- | :--- |
| `hxl` | 384×184 | 横屏 | 3.5 寸 |
| `h2xl` | 400×300 | 横屏 | 4.2 寸 |
| `v2xl` | 300×400 | 竖屏 | 4.2 寸（竖屏） |

调色板固定为 `bwr`（黑 / 白 / 红）。渲染引擎按画布宽度自动分档字号，因此这些尺寸
共用同一套布局代码。

## 配置参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `api_key` | string | 是 | 无（可在面板预置） | Steam Web API Key |
| `steam_id` | string | 是 | 无（可在面板预置） | Steam 64 位 ID |
| `size` | enum | 是 | 无 | `hxl` / `h2xl` / `v2xl` |
| `rotate` | enum | 否 | `0` | `0` / `90` / `180` / `270`；URL 传了以 URL 为准 |
| `invert` | bool | 否 | `false` | 是否反色显示 |

> 说明：`api_key` 与 `steam_id` 没有内置默认值，必须由 URL 传入或在面板「插件配置」
> 的 `DEFAULT_ARGS` 里预设；两者缺一即返回 400。

## 快速预览链接

在运行主程序后，可直接点击查看效果（把 `你的KEY` / `你的ID` 换成实际值）：

**横屏 3.5 寸 (384×184)：**
[http://127.0.0.1:5000/steam/view/stats?size=hxl&api_key=你的KEY&steam_id=你的ID](http://127.0.0.1:5000/steam/view/stats?size=hxl&api_key=你的KEY&steam_id=你的ID)

**横屏 4.2 寸 (400×300)：**
[http://127.0.0.1:5000/steam/view/stats?size=h2xl&api_key=你的KEY&steam_id=你的ID](http://127.0.0.1:5000/steam/view/stats?size=h2xl&api_key=你的KEY&steam_id=你的ID)

**竖屏 4.2 寸 (300×400)：**
[http://127.0.0.1:5000/steam/view/stats?size=v2xl&api_key=你的KEY&steam_id=你的ID](http://127.0.0.1:5000/steam/view/stats?size=v2xl&api_key=你的KEY&steam_id=你的ID)

## 目录结构

```text
steam/
├── __init__.py
├── README.md
├── plugin.json
├── plugin_config.py
├── routes.py
├── lib/
│   └── fetcher.py            # Steam Web API 取数（httpx 异步）
└── view/
    └── stats/
        ├── hxl.py            # 384×184
        ├── h2xl.py           # 400×300
        ├── v2xl.py           # 300×400
        └── utils.py          # 网格渲染引擎（按宽度自适应字号）
```
