# Plugin Template

这是一个通用、正式的 eInkViews 插件模板。它不绑定任何具体应用场景，目标是让开发者先看到参数流、数据流和排版分工，再去替换成自己的业务内容。

## 设计目标

- 用最少的业务假设展示完整插件骨架
- 让参数、数据处理、JSON 输出和视图排版各司其职
- 让 `utils.py` 专注复用代码，避免在视图里重复写测量、对齐和布局辅助函数
- 用通用参数 `a`、`b` 演示插件如何接收、组合和展示数据

## 推荐结构

```text
plugin_template/
├── __init__.py
├── README.md
├── plugin.json
├── plugin_config.py
├── routes.py
├── lib/
│   ├── __init__.py
│   └── demo_data.py
├── json_module/
│   ├── __init__.py
│   └── demojson.py
└── view/
    ├── __init__.py
    ├── summary/
    │   ├── __init__.py
    │   ├── hxl.py
    │   ├── h2xl.py
    │   └── utils.py
    └── detail/
        ├── __init__.py
        ├── hxl.py
        ├── h2xl.py
        └── utils.py
```

## 模板内容

- `lib/demo_data.py`：根据参数 `a`、`b` 生成可展示的数据
- `json_module/demojson.py`：返回结构化 JSON，用于接口调试或二次开发
- `view/summary/`：展示摘要型内容，适合做单屏总览
- `view/detail/`：展示细节型内容，适合做分区布局
- `utils.py`：放复用的测量、格式化、布局辅助函数，避免重复代码散落在每个视图里

## 参数示例

模板默认演示以下参数：

- `a`：主参数，通常代表主标题、主类别或主数据源
- `b`：辅参数，通常代表补充信息、第二组数据或说明文本
- `title`：页面主标题
- `subtitle`：副标题或说明
- `left` / `right`：左右分区内容示例
- `note`：底部说明文字
- `tz`：时区参数，可选

示例调用：

```text
http://127.0.0.1:5000/plugin_template/view/summary?size=hxl&a=alpha&b=beta&title=Demo&subtitle=Summary
http://127.0.0.1:5000/plugin_template/view/detail?size=h2xl&a=alpha&b=beta&title=Demo&left=Left&right=Right
http://127.0.0.1:5000/plugin_template/view/detail?size=h2xl&format=jpg
http://127.0.0.1:5000/plugin_template/view/detail?size=h2xl&format=bwrarray
```

`format` 参数支持：`jpg`（默认）/ `jpeg` / `png` / `bmp` / `webp` / `tiff` / `gif`，以及**数组格式族** `array`（= `bwarray`，白黑 1bpp）/ `bwrarray` / `bwyarray` / `bwryarray`（2bpp）/ `7carray`（3bpp）——数组格式返回按调色板索引打包的位流（码表 白=0、黑=1、红=2、黄=3、绿=4、蓝=5、橙=6，MSB 在前、行末补 0 bit 到整字节），用哪个由视图的调色板决定。注意全局配置 `IMAGE_FORMAT_BLACKLIST` 默认会拒绝 `png` / `bmp` / `webp` / `tiff` / `gif`，因此**默认配置下实际可用的只有 `jpg` / `jpeg` 与整个数组格式族**；要开放其它格式需在管理面板或 `config.py` 中调整黑名单。

## 文件职责

### routes.py

负责定义插件名常量与蓝图注册。它只做路由装配，不承载业务逻辑。其中的 `PLUGIN_DESCRIPTION` 只是描述兜底值：面板显示的描述优先取 `plugin.json` 的 `description`。

### plugin.json

负责声明插件元信息（版本、描述、作者、最低框架版本、依赖）。这是元信息的唯一来源，改名时记得同步 `name` 与目录名。

### plugin_config.py

负责定义插件默认参数与配置项的显示名（`CONFIG_LABELS`）。这里建议只放真正需要的默认值，避免把业务逻辑写进去。

### lib/

负责把参数转换成可展示的数据结构。视图层只消费这里的结果，不再做复杂判断。

### json_module/

负责输出结构化数据，便于调试、集成和联调。

### view/<kind>/

负责绘制图像。每个 `kind` 都应该有独立的 `hxl` 和 `h2xl` 实现，不要简单缩放同一份布局。

## 代码约定

- 视图文件必须提供 `generate_image(rotate=0, invert=False, tz=None, cmode=None, **kwargs)`
- 视图层先取数据，再创建画布
- 默认同时提供 `hxl` 和 `h2xl` 两个横屏版本
- 黑色绘制必须使用 `fill=1` 或 `fill=(0, 0, 0)`
- 不要在视图层做参数降级
- 所有网络请求都要带 `timeout`
- `utils.py` 只放复用代码，不放具体业务
- 开发时优先关注布局、间距、字号和对齐方式，而不是重复写工具函数

## 开发流程

1. 先定义参数和数据结构
2. 再实现 `lib/` 的数据构造或抓取逻辑
3. 然后实现 `json_module/` 的数据输出
4. 最后在 `view/` 中做两个尺寸的独立排版
5. 完成后同步更新 README 与测试链接

## 适用场景

这个模板适合任何“从参数生成一张墨水屏图”的插件，例如：摘要看板、状态卡片、任务概览、数据总览、简单信息板等。

## 使用方式

1. 复制 `plugin_template` 并改成真实插件名。
2. 修改 `plugin.json` 的 `name` / `description`、`routes.py` 里的 `PLUGIN_NAME`，以及 `plugin_config.py` 的默认参数与 `CONFIG_LABELS`。
3. 用自己的数据逻辑替换 `lib/demo_data.py`。
4. 在 `view/summary` 和 `view/detail` 中专注排版。
5. 把重复的计算放进 `utils.py`。

## 参考链接

- [plugin_config.py](plugin_config.py)
- [routes.py](routes.py)
- [lib/demo_data.py](lib/demo_data.py)
- [json_module/demojson.py](json_module/demojson.py)