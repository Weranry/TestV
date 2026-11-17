# 知乎日报（zhihu）

把当日知乎日报的标题渲染到墨水屏，右下角附上原文二维码，扫码直达当天日报。

## 功能特性

- **顶部标头**：左侧红色「知乎日报 ZHIHU DAILY」，右侧按插件时区显示日期与星期。
- **标题自动折行**：长标题按画布宽度按字符折行，最多显示 5 行。
- **避让二维码**：折行进入二维码所在高度后自动收窄行宽，标题不会压到二维码上。
- **原文二维码**：右下角 96×96 二维码，扫码打开当天知乎日报原文。
- **红黑双色**：沿用 `bwr` 调色板，仅标头用红，正文与二维码用黑。

## 数据来源

来自 RSSHub 的知乎日报订阅源 `<rsshub_base>/zhihu/daily`，返回 RSS 或 Atom
格式的 XML。插件用 BeautifulSoup（`html.parser`）解析出最新一条的标题与原文链接。

默认实例为 `https://rsshub.rssforever.com`（原默认实例 `rsshub.umi.im` 已无法解析，
DNS 找不到主机）。公共 RSSHub 实例的可用性会波动，建议用 `rsshub_base` 改指到自建实例。

该接口没有官方 key，也无需登录；能否取到数据取决于上游 RSSHub 实例的可用性。

## 支持的尺寸

| size | 分辨率 | 方向 |
| :--- | :--- | :--- |
| `h2xl` | 400×300 | 横屏（4.20" 墨屏） |

调色板固定为 `bwr`（黑 / 白 / 红）。

## 配置参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `tz` | string | 否 | 框架默认 | 日期标头的显示时区，如 `8` 或 `Asia/Shanghai` |
| `rsshub_base` | string | 否 | `https://rsshub.rssforever.com` | RSSHub 实例地址；公共实例不稳时改指到自建实例 |

## 快速预览链接

在运行主程序后，可直接点击查看效果：

[http://127.0.0.1:5000/zhihu/view/daily?size=h2xl](http://127.0.0.1:5000/zhihu/view/daily?size=h2xl)

## 目录结构

```text
zhihu/
├── __init__.py
├── README.md
├── plugin.json
├── plugin_config.py
├── routes.py
├── lib/
│   └── fetcher.py      # 知乎日报 RSS 取数、解析标题与原文链接
└── view/
    └── daily/
        └── h2xl.py     # 400×300 渲染：标头 + 折行标题 + 二维码
```
