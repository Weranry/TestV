# Wikipedia

中文维基百科首页摘要，支持竖屏与大、中、小三种横屏墨水屏。把首页当天的「正在发生 / 最近逝世」「新闻动态」「你知道吗」「典范条目（或特色列表）」压进一屏，适合做为每日晨间信息板。

## 路由

```text
http://127.0.0.1:5000/wikipedia/view/daily?size=v4xl   # 480×800
http://127.0.0.1:5000/wikipedia/view/daily?size=h4xl   # 800×480
http://127.0.0.1:5000/wikipedia/view/daily?size=h2xl   # 400×300
http://127.0.0.1:5000/wikipedia/view/daily?size=hxl    # 384×184
http://127.0.0.1:5000/wikipedia/view/featured?size=h2xl  # 400×300，只放特色内容
http://127.0.0.1:5000/wikipedia/view/dyk?size=h2xl       # 400×300，只放你知道吗
http://127.0.0.1:5000/wikipedia/view/news?size=h2xl      # 400×300，只放新闻动态
http://127.0.0.1:5000/wikipedia/json/summary
```

`format` 支持框架通用取值，例如 `jpg`、`bwrarray`。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `page_url` | `https://zh.wikipedia.org/zh-cn/Wikipedia:%E9%A6%96%E9%A1%B5` | 首页地址；网络无法直连时可指向可访问的镜像（需保持 mp-2012 版式） |
| `tz` | 框架默认时区 | 日期与页脚时间的显示时区 |
| `size` | 无 | `v4xl` / `h4xl` / `h2xl` / `hxl` |

## 版面

- `v4xl`（480×800）：红色顶条、48px 日期、快讯条、新闻动态 / 你知道吗 / 特色内容三个分区
- `h4xl`（800×480）：紧凑日期头 + 全宽快讯条，下方左右双栏；左栏新闻动态与你知道吗，右栏特色内容
- `h2xl`（400×300）：紧凑日期头 + 快讯条 + 新闻动态；新闻较短时剩余空间自动补「你知道吗？」
- `hxl`（384×184）：日期行 + 快讯条 + 三条单行新闻标题，小屏不做分区标题和页脚
- 聚焦版 `featured` / `dyk` / `news`（仅 h2xl）：页头直接标栏目（维基百科 · 特色条目 / 你知道吗 / 新闻动态），不再重复分区标题，也不显示快讯条
- 快讯条：红色标签「正在发生」「最近逝世」，各一行，超长省略（仅综合版使用）
- 正文 16px / 行高 22px，分区标签 16px，日期与特色标题 32px（竖屏日期 48px）
- 折行对中文友好：英文/数字串不拆开，标点不出现在行首，开引号/开括号不留在行尾

## 数据来源与解析

解析按桌面版首页中与语言无关的区块 id 定位：

- `#mp-2012-column-feature-block`：典范条目 / 特色列表（缺失时退回 `#mp-2012-column-good-block`）
- `#mp-2012-column-itn-block`：新闻动态、正在发生、最近逝世
- `#mp-2012-column-dyk-block`：你知道吗

因此首页在「典范条目 / 特色列表」「正在发生 / 最近逝世」之间轮换时无需改代码。正文会去掉引用角标、`（图）` 标记与链接边界带来的多余空格。

## 目录结构

```text
wikipedia/
├── lib/fetcher.py            # 抓取 + 解析，异步/同步两条取数链路
├── json_module/summary.py    # JSON 输出
└── view/
    ├── daily/                # 综合版
    │   ├── v4xl.py           # 480×800 竖屏
    │   ├── h4xl.py           # 800×480 横屏双栏
    │   ├── h2xl.py           # 400×300 横屏
    │   ├── hxl.py            # 384×184 小屏横屏
    │   └── utils.py          # 中文折行、省略号、分区与列表绘制
    ├── featured/h2xl.py      # 聚焦特色内容
    ├── dyk/h2xl.py           # 聚焦你知道吗
    ├── news/h2xl.py          # 聚焦新闻动态
    └── focus_h2xl.py         # 聚焦版共用头部、快讯与页脚
```
