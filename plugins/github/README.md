# GitHub 

该插件用于在墨水屏上展示 GitHub 用户的状态与贡献图。

## 视图效果

包含用户的关键信息（Followers、Following、Star 数、Repo 数）以及仿原生的 GitHub 贡献图。

支持的尺寸：
- **`hxl`** (384x184): 简化尺寸，显示基础信息及贡献图。
- **`h2xl`** (400x300): 丰富尺寸，支持展示用户的最大置顶仓库信息（带描述与语言）。

调色板建议：
- 推荐使用 `bwr` 色彩模式。高亮标题及最高等级贡献方块（level=4）将会以醒目的红色渲染。

## 配置参数

| 参数名     | 类型   | 必填 | 默认值    | 说明             |
| :--------- | :----- | :--- | :-------- | :--------------- |
| `username` | string | 是   | `atc1441` | GitHub 用户名    |

## 快速预览链接

在运行主程序后，您可以直接点击以下链接查看该插件的效果：

**hxl 尺寸 (384x184):**
[http://127.0.0.1:5000/github/view/dashboard?size=hxl&username=atc1441](http://127.0.0.1:5000/github/view/dashboard?size=hxl&username=atc1441)

**h2xl 尺寸 (400x300):**
[http://127.0.0.1:5000/github/view/dashboard?size=h2xl&username=atc1441](http://127.0.0.1:5000/github/view/dashboard?size=h2xl&username=atc1441)

## 使用建议
直接通过 URL 参数中的 `username` 获取对应用户的状态：
`/github/view/dashboard?size=h2xl&username=your_github_id`