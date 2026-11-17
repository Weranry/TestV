# Schedule

将本地课程表 JSON 渲染到墨水屏，按「周次 + 星期」自动算出当天要上的课，节次数量与上课时间由 JSON 自定义。

## 功能特性

- **节次与时间自由配置**：当天有几节课、每节课几点到几点，全部由 JSON 里的 `timeSlots`
  决定；不写这一项时按旧的 5 节（M1 / M2 / A1 / A2 / EV）兼容。
- **时间轴版式**：只列出当天真正有课的节次，一条课一行——左侧黑色竖条做锚点，课名在上、
  教室与教师在下，右侧上下两行显示开始 / 结束时间；空节次留白，不排一排空行。
- **纯黑白**：不使用红色或其他彩色，层级靠字号、留白和竖条建立，适合任何双色 / 三色屏。
- **字号按内容选**：课名在 32 / 16 两档间自动选择——行高与列宽都够用 32，否则退回 16，
  窄屏还能折成两行；课多行矮时自动压缩成单行版式。
- **溢出兜底**：课名与教室/教师都先按各自预算截断并补 `..`，同一行两段文字不会互相压字。
- **无课提示**：整天没课时显示「今天没有课」。
- **同节多课合并**：同一节次落多门课（如分班实验）时合并显示为 `课程A / 课程B`，不再静默覆盖。

## 课程表 JSON 格式

```json
{
  "semesterStartDate": "2026-08-08",
  "timeSlots": [
    { "label": "M1", "start": "08:00", "end": "08:45" },
    { "label": "M2", "start": "08:55", "end": "09:40" }
  ],
  "courses": [
    {
      "courseName": "高等数学",
      "teacher": "张老师",
      "classroom": [
        { "week": [1, 2, 3], "dayOfWeek": 1, "lesson": 1, "room": "教1-203" }
      ]
    }
  ]
}
```

| 字段 | 说明 |
| :--- | :--- |
| `timeSlots` | 节次表。数组长度即当天节次数，`lesson` 取 1 到该长度；每项 `label` 为节次名（可省略，自动用「第N节」），`start` / `end` 为 `HH:MM`，可只填其一或都不填 |
| `semesterStartDate` | 学期开始日期，用来算当前第几周 |
| `courses[].classroom[].lesson` | 第几节，对应 `timeSlots` 的下标 + 1 |
| `courses[].classroom[].week` | 上课周次列表 |

不配置 `start` / `end` 时，屏幕右侧改为显示节次名，方便只想要「第几节」的场景。

## 数据来源

完全没有网络请求，数据来自插件自带的本地文件 `assets/course/<json_name>.json`。
换成自己的课程表只需往该目录里放一个同结构的 JSON，再用 `json_name` 参数指定文件名。
节次的数量与时间也可以在可视化编辑器里改：`/schedule/page/converter`。

## 支持的尺寸

| size | 分辨率 | 方向 |
| :--- | :--- | :--- |
| `hxl` | 384×184 | 横屏 |
| `h2xl` | 400×300 | 横屏 |
| `vxl` | 184×384 | 竖屏 |
| `v2xl` | 300×400 | 竖屏 |

调色板固定为 `bwr`（黑 / 白 / 红）。

## 配置参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `json_name` | string | 否 | `course_schedule` | `assets/course/` 下的课程表文件名（不含 `.json`） |
| `tz` | string | 否 | 框架默认 | 计算周次与星期用的时区，如 `8` 或 `Asia/Shanghai` |

## 快速预览链接

在运行主程序后，可直接点击查看效果：

**横屏：**
[http://127.0.0.1:5000/schedule/view/schedule_view?size=hxl](http://127.0.0.1:5000/schedule/view/schedule_view?size=hxl)
[http://127.0.0.1:5000/schedule/view/schedule_view?size=h2xl](http://127.0.0.1:5000/schedule/view/schedule_view?size=h2xl)

**竖屏：**
[http://127.0.0.1:5000/schedule/view/schedule_view?size=vxl](http://127.0.0.1:5000/schedule/view/schedule_view?size=vxl)
[http://127.0.0.1:5000/schedule/view/schedule_view?size=v2xl](http://127.0.0.1:5000/schedule/view/schedule_view?size=v2xl)

**课程表编辑器（生成符合格式的 JSON）：**
[http://127.0.0.1:5000/schedule/page/converter](http://127.0.0.1:5000/schedule/page/converter)

## 目录结构

```text
schedule/
├── __init__.py
├── README.md
├── plugin.json
├── plugin_config.py
├── routes.py
├── assets/
│   └── course/
│       └── course_schedule.json
├── lib/
│   └── fetcher.py            # 课程表 JSON 读取与当天课表计算
├── page/
│   └── converter.html        # 课程表编辑器页面
└── view/
    └── schedule_view/
        ├── hxl.py
        ├── h2xl.py
        ├── vxl.py
        ├── v2xl.py
        └── utils.py          # 网格渲染引擎（含自动换行）
```
