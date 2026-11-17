# 面板页文档头（<style> 之前）
ADMIN_HEAD = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:app.panel_title}}</title>'''
# 面板页内嵌样式（<style> 整块）
# 设计令牌（:root 浅色 + .dark 深色）由 {{SHARED_UI_CSS}} 一并带进来，这里不再自建一份
ADMIN_CSS = r'''<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);color:var(--fg);font-size:14px;min-height:100vh;-webkit-font-smoothing:antialiased}
/* 浏览器默认把 <b>/<strong> 设成 700，项目统一用 600；不重置的话同一段文案字重会跳变 */
b,strong{font-weight:600}
a{color:var(--blue);text-decoration:none}
/* ---------- 侧边栏（左侧竖排菜单） ---------- */
/* 面板骨架 = 左列固定侧边栏 + 右列内容区。用 .shell 包一层而不是把 grid 挂在 body 上：
   用户控制台与登录页共用同一份共享层样式，body 的布局不该被这里改掉 */
.shell{display:grid;grid-template-columns:232px 1fr;min-height:100vh;align-items:start}
/* 无侧栏：除「我的」外一个可用分页都没有时整条侧栏不存在，内容区占满（判定见 admin_js_boot） */
.shell.nonav{grid-template-columns:1fr}
.shell.nonav .sidebar{display:none}
/* 侧栏都没了，窄屏那个开抽屉的汉堡按钮也得跟着收掉，否则点开是个空抽屉 */
.shell.nonav .snav-toggle{display:none}
.sidebar{position:sticky;top:0;z-index:120;height:100vh;display:flex;flex-direction:column;background:var(--ds-background-100);border-right:1px solid var(--line)}
/* 品牌区：侧栏的 logo 比顶栏那份放大一档（26px 标记 + 16px 字），头部才撑得住这一列宽度 */
.side-brand{display:flex;align-items:center;justify-content:space-between;gap:8px;height:56px;padding:0 16px;flex-shrink:0}
.logo{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:16px;letter-spacing:-.4px;color:var(--fg)}
/* 侧栏里的标记单独放大：共享层的 .logo-mark 是全局 20×20，顶栏与概览缩略图都在用，
   直接改全局会把别处一起撑大 */
.side-brand .logo-mark{width:26px;height:26px}
/* 菜单图标统一 18×18 */
.ic{width:18px;height:18px;flex-shrink:0}
/* 侧栏内的图标再放大一档（20px）：导航项、设置分类项、栏底按钮组都走这一条。
   顶栏那份在 .sidebar 之外，仍是全局 18px，不受影响 */
.sidebar .ic{width:20px;height:20px}
/* 「返回主页」：只在设置模式下出现（侧栏整条已换成设置分类菜单，主业菜单收起来了） */
.snav-back{width:30px;height:30px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:var(--r-sm);background:none;color:var(--fg3);cursor:pointer;padding:0}
.snav-back:hover{color:var(--fg);background:var(--soft)}
.snav-back[hidden]{display:none}
/* 导航列表：列向排布 + 4px 项间距。行高 36px、内边距 8px，配上 20px 的图标，
   整条侧栏的节奏才不至于稀疏 */
.snav{flex:1;overflow-y:auto;padding:8px 8px 16px;display:flex;flex-direction:column;gap:4px}
/* 加了 display:flex 会盖掉 UA 的 [hidden]{display:none}，两份菜单靠 hidden 互斥，这里补回来 */
.snav[hidden]{display:none}
/* 菜单项：行高 36px，默认中性灰、hover 浅底、选中浅底 + 墨色加粗。
   选中态**不再画左缘指示条**：Geist 的 selected 只用底下那一块浅灰，左指示条是另一套语言 */
.snav .tab{position:relative;display:flex;align-items:center;gap:8px;min-height:36px;font-size:14px;font-weight:500;color:var(--fg2);padding:8px;border-radius:var(--r-sm);cursor:pointer;transition:background var(--motion-fast),color var(--motion-fast)}
.snav .tab:hover{color:var(--fg);background:var(--soft)}
.snav .tab.on{background:var(--soft-2);color:var(--fg)}
.snav-group{position:relative}
.snav-arrow{position:absolute;right:4px;top:50%;transform:translateY(-50%);width:24px;height:24px;display:flex;align-items:center;justify-content:center;border:none;background:none;color:var(--fg3);cursor:pointer;border-radius:4px}
.snav-arrow:hover{background:var(--ds-background-100);color:var(--fg)}
.snav-arrow svg{width:14px;height:14px;transition:transform .18s}
.snav-arrow[aria-expanded="true"] svg{transform:rotate(180deg)}
/* 二级菜单与一级项之间留出 8px（容器 gap 4px + 这里的 4px 外边距）：两块浅灰底块
   直接贴住会连成一坨，看不出层级 */
.snav-sub{display:flex;flex-direction:column;gap:4px;padding-left:16px;margin:4px 0}
.snav-sub[hidden]{display:none}
.snav-sub .tab{font-size:12px;font-weight:400;min-height:32px;padding:4px 8px}
/* 侧栏底部：头像 + 用户名 + 图标按钮组（设置 / 返回 / 退出）。
   有侧栏时这一组恒在这里；无侧栏的用户（普通用户）改由顶栏右侧承载同一份 */
.snav-foot{border-top:1px solid var(--line);padding:8px 16px;display:flex;align-items:center;gap:8px;font-size:14px;color:var(--fg2);flex-shrink:0}
/* 头像 = 黑底 + 用户名首字母，没有独立的上传/图片资源 */
.avatar{width:30px;height:30px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:50%;background:var(--ds-gray-1000);color:var(--ds-background-100);font-size:12px;font-weight:600;text-transform:uppercase;cursor:pointer;padding:0}
.avatar:hover{background:var(--ds-gray-900)}
.snav-foot .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:var(--fg);cursor:pointer}
.snav-foot .nm:hover{text-decoration:underline}
.icon-btn{width:30px;height:30px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:var(--r-sm);background:none;color:var(--fg3);cursor:pointer;padding:0}
.icon-btn:hover{color:var(--fg);background:var(--soft)}
.icon-btn[hidden]{display:none}
/* 折叠按钮贴在 logo 与站名右侧，两个箭头互斥显示：展开态「<」（点了往左收），
   折叠态「>」（点了往右展），箭头方向就是侧栏接下来要移动的方向 */
[data-act="snav-fold-toggle"] .chev-out{display:none}
.shell.folded [data-act="snav-fold-toggle"] .chev-in{display:none}
.shell.folded [data-act="snav-fold-toggle"] .chev-out{display:block}
.snav-mask{display:none}
/* 导航角标：该分页有待处理项时显示的红点；与状态圆点 .dot 是两回事，类名分开避免级联互相污染 */
.nav-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--red);flex-shrink:0}
/* ---------- Layout ---------- */
.workspace{min-width:0;display:flex;flex-direction:column;min-height:100vh}
/* 内容区顶栏：面包屑常驻，窄屏时才露出汉堡按钮（侧边栏转为抽屉） */
.topbar{position:sticky;top:0;z-index:110;height:56px;display:flex;align-items:center;gap:16px;padding:0 24px;background:var(--topbar);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.crumbs{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--fg3);min-width:0;overflow:hidden;white-space:nowrap}
.crumbs .sep{color:var(--faint)}
.crumbs .cur{color:var(--fg);font-weight:500}
/* 顶栏右端：主题切换常驻，用户组（无侧栏时才出现）跟在它后面。
   margin-left:auto 挪到主题按钮上，用户组那侧的自动边距要归零，否则两块之间会被平分出一段空白 */
.theme-btn{margin-left:auto}
/* 无侧栏时的用户组：与侧栏底部那份同构（头像 + 名字 + 设置 + 退出），贴在最右端。有侧栏时隐藏 */
.topbar-user{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--fg2)}
.topbar-user[hidden]{display:none}
.topbar-user .nm{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:var(--fg);cursor:pointer}
.topbar-user .nm:hover{text-decoration:underline}
.snav-toggle{display:none;width:32px;height:32px;align-items:center;justify-content:center;border:none;border-radius:var(--r-sm);background:var(--ds-background-100);box-shadow:0 0 0 1px var(--line);color:var(--fg2);cursor:pointer;flex-shrink:0;padding:0}
.snav-toggle:hover{color:var(--fg);background:var(--soft)}
/* 内容区宽度：与用户控制台取同一个值，同一块屏幕换一边看卡片宽度才不会跳 */
main{padding:24px 24px 64px;max-width:1400px;margin:0 auto;width:100%}
.page{display:none;animation:fadeIn .18s ease}.page.on{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(2px)}to{opacity:1;transform:none}}
.dim{color:var(--fg2)}.small{font-size:12px}.strong{font-weight:600}
/* ---------- Page head ---------- */
/* 分页大标题与描述已移除（层级由侧栏菜单 + 面包屑承担），这里只剩右上角的操作按钮行 */
.page-head{display:flex;align-items:center;justify-content:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.page-head .acts{justify-content:flex-end}
/* ---------- Cards ---------- */
.card{background:var(--ds-background-100);border-radius:var(--r-md);box-shadow:var(--card-shadow);margin-bottom:16px;overflow:hidden}
.card-header{padding:16px 24px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.card-header h2{font-size:16px;font-weight:600;letter-spacing:-.4px}
.card-title{display:flex;flex-direction:column;gap:4px;min-width:0}
.card-desc{font-size:12px;color:var(--fg2);font-weight:400}
/* 卡片头右上角的计数小字（「已使用 N 个 / M」这类）：中文的 min-content 只有一个字宽，
   被按钮挤压时会逐字竖排、看上去像被按钮盖住。禁止收缩，并把「计数 ↔ 按钮」的间距从
   6px 提到 16px（与「标题 ↔ 计数」一致），深色按钮才不会把灰字压得贴在一起 */
.card-header small,.card-header .acts .dim{white-space:nowrap;flex-shrink:0}
.card-header .acts>.dim+.btn{margin-left:8px}
.card-body{padding:24px}
/* 设置类卡片：与数据类卡片在视觉上区分开（只靠底色，不再给 h2 加前置圆点——
   那个圆点会把标题文字右移 14px，而下面的 .card-desc 不跟着移，同一个卡片内
   标题与说明的左边缘就对不齐了，跨卡片看标题也会比别的卡片缩进一截） */
.card.cfg .card-header{background:var(--soft);border-bottom-color:var(--line)}
.sec-title{font-size:14px;font-weight:600;margin:24px 0 8px;color:var(--fg);letter-spacing:-.2px}
.panel{background:var(--soft);border-radius:var(--r-sm);box-shadow:var(--ring);padding:16px;font-size:12px}
/* ---------- Metrics ---------- */
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px}
/* 页面直属的 KPI 卡片组：下方必然跟着卡片，间距在这里统一给（以前靠各页手写内联
   margin-top:18px 兜，概览页两处、备份页一处，索性收进样式表，新增页面不必再记这条） */
.page>.metrics{margin-bottom:16px}
/* 卡片体里后面还有内容的 KPI 组：与下方区块留出一致的间距（不再各页内联 margin-bottom） */
.card-body>.metrics:not(:last-child){margin-bottom:16px}
.metric{padding:16px 24px;border-radius:var(--r-md);box-shadow:var(--card-shadow);background:var(--ds-background-100)}
.metric .l{font-size:12px;color:var(--fg2);margin-bottom:8px}
.metric .k{font-size:32px;font-weight:600;letter-spacing:-1.28px;font-variant-numeric:tabular-nums}
.metric .k.red{color:var(--red)}
/* KPI 主数值里的次级说明（如「/ 200 条」上限）：字号字重降一档，与主数值同基线 */
.metric .k .sub{font-size:14px;font-weight:500;color:var(--fg2);letter-spacing:0}
/* ---------- Controls ---------- */
input,select,button,textarea{font-family:inherit;font-size:inherit}
/* 控件描边与 hover 一律走 gray-alpha（黑透明 → 深色下自动变白透明）；焦点统一用官方焦点环：
   内圈取当前表面底色、外圈取焦点色，控件贴在白底/黑底上都能把环「切」出来 */
.input{height:32px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;background:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);color:var(--fg);transition:box-shadow var(--motion-fast)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.input::placeholder{color:var(--faint)}
select.input{-webkit-appearance:none;appearance:none;cursor:pointer;padding-right:28px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M4 6.5l4 4 4-4' fill='none' stroke='%238f8f8f' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;background-size:12px}
/* 卡片头里的下拉更矮更窄，箭头跟着缩，否则会压到选项文字上 */
.card-header select.input{padding-right:24px;background-position:right 8px center;background-size:10px}
/* 复选框统一成面板的扁平风格：自绘 16px 方框，选中即 Geist 蓝填充 + 白色对勾。
   与下面的开关（.sw.on）取同一个蓝，两者摆在一行才像一套控件。
   vertical-align 只在非 flex 的行内排布（如弹窗里「允许反复激活」那种）起作用，flex 容器里会被忽略 */
input[type=checkbox]{-webkit-appearance:none;appearance:none;flex-shrink:0;width:16px;height:16px;margin:0;vertical-align:-2px;
  border-radius:4px;background:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);cursor:pointer;transition:background var(--motion-fast),box-shadow var(--motion-fast)}
input[type=checkbox]:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
input[type=checkbox]:checked{background-color:var(--ds-blue-700);background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3.6 8.4l3.1 3.1 5.7-6.6' fill='none' stroke='%23fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:center;background-size:12px;box-shadow:inset 0 0 0 1px var(--ds-blue-700)}
input[type=checkbox]:focus-visible{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500),var(--ds-focus-ring)}
input[type=checkbox]:disabled{opacity:.45;cursor:not-allowed}
/* 弹窗里堆叠的表单控件（.field-row 内的除外）占满整行：弹窗自带 24px 内边距，
   100% 即「随卡片宽度、左右各留一圈空隙」。不写宽度时输入框取浏览器默认尺寸、
   下拉框按最长选项自适应，同一列里右边缘参差。.field-row 里的输入框是 flex 项，
   由 .field-row .input 单独定宽，不是 .modal 的直接子元素，不受这条影响 */
.modal>.input{width:100%}
/* 卡片头里的下拉/输入与 .btn-sm 等高，否则同一行控件高低不齐 */
.card-header .input{height:26px;font-size:12px;padding:0 8px}
/* 中文的 min-content 宽度是「一个字」：按钮放在 flex 行里被挤压时，浏览器会一路缩到
   一字宽，文字就逐字竖排堆起来。nowrap 让 min-content 变成整段文字宽度，收缩到此为止；
   flex-shrink:0 再兜一层，宁可撑宽容器（表格走 .card-body 的横向滚动）也不压扁按钮。 */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:32px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;background:var(--ds-background-100);color:var(--fg);box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);transition:all var(--motion-fast);white-space:nowrap;flex-shrink:0}
.btn:hover{background:var(--ds-gray-100)}
.btn:active{background:var(--ds-gray-200)}
/* 主按钮 = 反色（浅色下近黑底白字、深色下近白底黑字）：两种主题里都保持最高对比度 */
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-1000)}
.btn-primary:hover{background:var(--ds-gray-900)}
.btn-primary:active{background:var(--ds-gray-800)}
.btn-danger{color:var(--red)}
.btn-danger:hover{background:var(--ds-red-100)}
.btn-sm{height:26px;padding:0 8px;font-size:12px}
/* .btn-ghost 在共享层（两个外壳都用它） */
/* 原生 <input type="file"> 的按钮部分是浏览器内部控件（::file-selector-button），
   套不上 .btn 的圆角/字重/hover，各浏览器渲染还互不一致。改为隐藏原生 input、
   用 <label class="btn" for="..."> 当按钮：点 label 即点 input。input 仍留在 DOM 里
   且可聚焦，:focus-within 把 focus ring 透到 label 上，键盘照样能用。 */
.file-pick{position:relative;display:inline-flex;flex-shrink:0}
.file-pick>label{cursor:pointer}
.file-pick>input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}
.file-pick:focus-within>label{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500),var(--ds-focus-ring)}
/* ---------- Tables ---------- */
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;padding:8px 16px;font-size:12px;font-weight:500;color:var(--fg2);border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 16px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--soft)}
/* 停用行只压淡内容列：整行 opacity 会让操作按钮也变淡，看起来像被禁用实际却能点 */
tbody tr.off td{opacity:.55}
tbody tr.off td:last-child{opacity:1}
tbody tr.off:hover td{opacity:.85}
/* 数值列右对齐 + 等宽数字：同一列的数字才能上下对位 */
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
/* 操作列按内容收窄（按钮个数与文字宽度都由内容决定，写死宽度必然溢出） */
.col-act{width:1%;white-space:nowrap}
/* 状态列同理：徽章宽度由文字决定，各页写死 110/120/180px 只会互不一致 */
.col-state{width:1%;white-space:nowrap}
/* 只放圆点的列（用户组「标记」、账号「状态」、激活码「重复激活 / 状态」、权限记录「类型」、
   额度记录「操作」、API 文档「鉴权」、路由「状态」）：整列居中，圆点不偏在格子左侧。
   表头单元格也要带这个类，否则表头文字与底下的圆点各偏一边。 */
.col-dot{width:1%;white-space:nowrap;text-align:center}
/* 长文本单行省略：宽度统一在这里，不再各页各写一串 overflow/ellipsis（且宽度互不相同） */
.ellip{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
table th:first-child,table td:first-child{padding-left:24px}
table th:last-child,table td:last-child{padding-right:24px}
/* 表格里的操作按钮强制单行：列宽不足时整列撑开并横向滚动，而不是把最后一个按钮挤到下一行 */
td .acts{flex-wrap:nowrap}
.card-body{overflow-x:auto}
/* ---------- 状态圆点（全站统一用彩色小圆点承担状态语义，hover 有说明） ---------- */
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;flex-shrink:0;cursor:help;vertical-align:middle;background:var(--fg3)}
.dot-on{background:var(--blue)}
.dot-off{background:var(--fg3)}
.dot-warn{background:var(--orange)}
.dot-error{background:var(--red)}
.dot-violet{background:var(--violet)}
.dot-idle{background:var(--faint)}
/* 兼容别名：用户组列表沿用旧类名，只换色不动 JS */
.dot-in{background:var(--orange)}
.dot-def{background:var(--blue)}
.dot-admin{background:var(--violet)}
.dot-user{background:var(--faint)}
.dot-cell{display:inline-flex;align-items:center;gap:8px}
/* 状态圆点图例：表格里的状态列只有圆点、不带文字，含义统一挪到卡片头说明。
   不同类别的图例各占一行（如激活码的「重复激活」与「状态」两组），所以外层用纵向 flex；
   图例里的圆点只是色样，不该带悬停手势，光标统一成默认 */
.dot-legend{display:flex;flex-direction:column;gap:4px;margin-top:8px;font-size:12px;color:var(--fg2)}
.dot-legend .lg-row{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px}
.dot-legend .lg-row>em{font-style:normal;color:var(--fg3)}
.dot-legend .lg-item{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.dot-legend .dot{cursor:default}
/* 状态码图例：日志表里状态码是彩色文本（不是圆点），图例也跟着用彩色等宽文本，与表格所见一致 */
.lgd-code{font-family:var(--mono);font-size:12px;font-weight:500;margin-right:16px;white-space:nowrap}
/* ---------- 状态文字 ---------- */
/* 颜色语义一律交给 ::before 的圆点，文字保持中性灰：同一行出现两种颜色语义会互相打架。
   圆点必须用伪元素：插件/路由开关会覆写 .badge 的 className 与 textContent，
   往里插 <i class="dot"> 会在开关一次之后被 textContent 抹掉。 */
.badge{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:400;line-height:16px;white-space:nowrap;flex-shrink:0;color:var(--fg2)}
.badge::before{content:'';width:8px;height:8px;border-radius:50%;background:var(--fg3);flex-shrink:0}
.badge-on::before{background:var(--blue)}
.badge-off::before{background:var(--fg3)}
.badge-warn::before{background:var(--orange)}
.badge-error::before{background:var(--red)}
.badge-custom::before{background:var(--violet)}
.tag{display:inline-flex;align-items:center;padding:1px 8px;border-radius:9999px;font-size:12px;background:var(--soft);color:var(--fg2);margin:4px;cursor:pointer;border:none;transition:all .15s;white-space:nowrap;flex-shrink:0}
/* .tag.active 表示「该参数已被禁止」：用琥珀（警示）而非绿色（成功），否则语义正好反了 */
.tag.active{background:var(--orange-soft);color:var(--orange-deep);box-shadow:inset 0 0 0 1px var(--ds-amber-600)}
.mono{font-family:var(--mono);font-size:12px;word-break:break-all}
/* ---------- Sub tabs ---------- */
.subtabs{display:flex;gap:8px;flex-wrap:wrap}
.stab{display:inline-flex;align-items:center;gap:8px;height:32px;padding:0 16px;border-radius:64px;font-size:14px;font-weight:500;color:var(--fg2);cursor:pointer;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);transition:all var(--motion-fast);background:var(--ds-background-100);white-space:nowrap;flex-shrink:0}
.stab:hover{color:var(--fg);background:var(--ds-gray-100)}
.stab.on{background:var(--ds-gray-1000);color:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-1000)}
.stab .cnt{font-size:11px;opacity:.7}
/* ---------- Misc ---------- */
.empty{text-align:center;padding:40px 0;color:var(--fg3);font-size:14px}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.share{height:4px;border-radius:2px;background:var(--track);overflow:hidden;margin-top:4px;max-width:160px}
.share>div{height:100%;background:var(--fg);border-radius:2px}
.stat-line{font-size:12px;margin-bottom:16px}
/* 可点单元格：整格可点并给 hover 反馈，否则用户看不出这里能点开 */
.lnk{cursor:pointer}
.lnk:hover{color:var(--blue)}
.lnk:hover .strong{text-decoration:underline}
/* 面板变体：失败原因用红字，替代每处内联 color */
.panel.err{color:var(--red-deep)}
.err-text{color:var(--red-deep)}
/* 成品预览：浅底 + ring 兜住白底索引图，否则图和卡片背景糊在一起看不出边界 */
.pv{text-align:center}
.pv img{max-width:100%;display:block;margin:0 auto;border-radius:6px;background:var(--ds-background-100);box-shadow:0 0 0 1px var(--line)}
/* ---------- 概览大卡 ---------- */
/* 上卡：左侧「主页缩略图」预览 + 右侧运行信息。两栏 grid，窄屏降单列（见文件末尾媒体查询）。
   两栏等宽：缩略图是等比框，分到的列宽直接决定它多大，偏窄会把它挤成一张小图 */
.ovhero{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
/* 预览那一栏不铺底色：缩略图本身就是一张带阴影的白卡，再垫一层灰底会在它上下各留一块灰块。
   只保留右边界这条线把两栏分开 */
.ovshot{display:flex;align-items:center;justify-content:center;padding:24px;border-right:1px solid var(--line)}
/* Vercel 部署页那套「等比截图框」——固定 640/400 比例、圆角裁切，
   1px 内描边走 ::after 的 inset ring（不用 border，圆角处才不会露出直角） */
.ovshot-frame{position:relative;display:block;width:100%;max-width:460px;aspect-ratio:640/400;border-radius:var(--r-md);overflow:hidden;background:var(--ds-background-100);box-shadow:var(--ds-shadow-large);transition:transform var(--motion-pop),box-shadow var(--motion-pop)}
.ovshot-frame::after{content:'';position:absolute;inset:0;border-radius:inherit;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-400);pointer-events:none}
.ovshot-frame:hover{transform:translateY(-2px);box-shadow:var(--ds-shadow-xl)}
.ovshot-frame:focus-visible{outline:none;box-shadow:var(--ds-shadow-xl),var(--ds-focus-ring)}
/* 画布内部分辨率是显示尺寸的 2 倍，缩到框宽后边缘不发虚 */
.ovshot-frame canvas{display:block;width:100%;height:100%}
.ovinfo{display:flex;flex-direction:column;gap:16px;padding:24px}
/* KPI 组与上面的定义栅格之间用细分隔线分段 */
.ovinfo-kpi{padding-top:16px;border-top:1px solid var(--line-soft)}
/* 定义栅格：小号灰标签在上、值在下（参考图的「属性表」观感），概览页所有数值都走这一套 */
.def-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px 24px}
.def-k{font-size:12px;color:var(--fg2);margin-bottom:8px}
.def-v{font-size:14px;font-weight:500;word-break:break-word}
.def-v.big{font-size:32px;font-weight:600;letter-spacing:-1.28px;line-height:1.1;font-variant-numeric:tabular-nums}
.def-v.red{color:var(--red)}
.def-grid.kpi .def-v{font-size:20px;font-variant-numeric:tabular-nums}
/* 下卡上排：左健康度 + 右定义栅格；底部那组 KPI 与它之间的分隔线由 .ovlow 的下边框给出 */
.ovlow{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:24px;align-items:center;padding-bottom:16px;margin-bottom:16px;border-bottom:1px solid var(--line-soft)}
/* ---------- 健康度：只给评分与等级，不展开逐项明细 ---------- */
.health-score{display:flex;align-items:center;gap:16px}
/* 大号数字用 ink：48px 的蓝会看起来像可点的链接，这里只是评分 */
.hs-num{font-size:48px;font-weight:600;letter-spacing:-2.4px;line-height:1;font-variant-numeric:tabular-nums;color:var(--fg)}
.hs-num.warn{color:var(--orange-deep)}
.hs-num.error{color:var(--red)}
.hs-grade{font-size:14px;font-weight:600}
.hs-note{font-size:12px;color:var(--fg2);margin-top:4px}
/* ---------- 运行信息 ---------- */
.info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 24px}
.info-item{display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid var(--line-soft);font-size:14px}
.info-item .ik{color:var(--fg2);font-size:12px;white-space:nowrap}
.info-item .iv{font-weight:500;text-align:right;font-variant-numeric:tabular-nums;word-break:break-all}
/* ---------- 批量操作条 ---------- */
.batchbar{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:8px 16px;margin-bottom:16px;border-radius:var(--r-sm);background:var(--ds-blue-100);box-shadow:inset 0 0 0 1px var(--ds-blue-300);font-size:14px}
.batchbar .cnt{font-weight:600}
.batchbar .sp{flex:1}
/* ---------- Expand rows ---------- */
.expander{display:inline-block;width:16px;cursor:pointer;color:var(--fg2);font-family:var(--mono);text-align:center;user-select:none}
.expander:hover{color:var(--fg)}
.detail-row>td{padding:0!important;border-bottom:none!important;background:var(--soft)}
/* 展开明细：左边距 24px 让路径与父表插件列文字对齐，右边距 0 让末列与父表末列对齐 */
.detail-row table{background:var(--ds-background-100);border-radius:6px;margin:8px 0 8px 24px;width:calc(100% - 24px)}
/* 固定列宽，父表与展开子表的数值列才能上下对齐 */
.stat-table{table-layout:fixed}
/* ---------- 站内信 ---------- */
/* 概览页的站内信卡片与用户控制台的站内信卡片渲染的是同一种条目，这一组取值必须与
   other_pages.py 里那份逐字相同：底色/圆角/正文字号一旦分头改动，同一条消息在两个
   界面里就长得不一样了 */
.ann-list{display:flex;flex-direction:column;gap:16px}
.ann-item{padding:16px;border-radius:var(--r-sm);background:var(--soft);box-shadow:var(--ring)}
.ann-item .h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ann-item .h b{font-size:14px;font-weight:600}
.ann-item .h .sp{flex:1}
.ann-item .body{font-size:14px;color:var(--fg2);margin-top:8px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.ann-item .meta{font-size:12px;color:var(--fg3);white-space:nowrap}
/* meta 的两种落位：概览页把它放在正文下方独立一行，控制台把它塞进标题行右侧。
   用子选择器区分，避免同一个 .meta 在两种结构里互相带上对方的边距 */
.ann-item>.meta{margin-top:8px;display:flex;gap:16px;flex-wrap:wrap}
.ann-item .h .meta{margin-left:auto}
.ann-scope{padding:3px 8px;border-radius:9999px;font-size:12px;box-shadow:0 0 0 1px var(--line);color:var(--fg2)}
/* 站内信主页的触发卡：只有一个只读输入框和一个「新建」按钮，点任一处都开弹窗填写。
   输入框只作触发与示意（真正的内容在弹窗里录入），因此换成手型光标；
   flex 项不写宽度会被压成浏览器默认宽度，flex:1 + min-width:0 让它随卡片宽度伸缩 */
.ann-new{display:flex;gap:16px}
.ann-new .input{flex:1;min-width:0;cursor:pointer}
/* 历次发送表格里的内容缩略：限宽 + 灰字，避免长正文把表格撑变形 */
.ann-excerpt{max-width:420px;color:var(--fg2)}
/* 可见范围勾选组 */
.ck-row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
/* margin/font-weight 必须显式归零：共享层 .modal label 的 `margin:16px 0 8px`（同为 0,1,1
   特异性、源序在前）会漏到这里的胶囊标签上，把 8px 的 flex 间距顶成参差不齐的行距 */
.ck-row label{display:inline-flex;align-items:center;gap:8px;margin:0;font-weight:400;padding:4px 8px;border-radius:9999px;box-shadow:0 0 0 1px var(--line);font-size:12px;cursor:pointer;color:var(--fg2)}
/* 平铺的「复选框 / 单选 + 文字」行（与上面 .ck-row 的胶囊样式相对）。
   **不要**写成 <label class="flex">：共享层的 .modal label{display:block}（特异性 0,1,1）
   比 .flex（0,1,0）更具体，display:flex 被压掉后 gap 一并失效，而 input[type=checkbox]
   的 margin 又是 0，复选框就会与文字贴死——这正是「新增用户组里复选框没间距」的成因。
   复选框与文字之间的间距只在这条规则里出一次，禁止在 JS 里写内联 gap/margin 去补 */
.ck-list{display:flex;flex-wrap:wrap;gap:8px 16px;margin:8px 0}
.ck-list>label{display:inline-flex;align-items:center;gap:8px;margin:0;font-weight:400;font-size:14px;cursor:pointer}
/* 分页勾选这类成列排的选项：定宽让它们上下对齐成列，比自然流更易扫读 */
.ck-list.cols>label{min-width:92px}
/* ---------- Chart ---------- */
.chart-box{padding:8px 4px 0}
.chart{display:flex;align-items:flex-end;gap:4px;height:150px}
.bar-col{flex:1;height:100%;display:flex;align-items:flex-end;min-width:4px;cursor:default}
.bar{width:100%;background:var(--ds-gray-alpha-500);border-radius:2px 2px 0 0;position:relative;overflow:hidden;min-height:2px;transition:background var(--motion-fast)}
.bar-col:hover .bar{background:var(--fg)}
.bar-err{position:absolute;bottom:0;left:0;width:100%;background:var(--red)}
.chart-x{display:flex;gap:4px;padding:8px 4px 0}
.chart-x span{flex:1;min-width:4px;font-size:11px;font-family:var(--mono);color:var(--fg3);text-align:center;overflow:hidden;white-space:nowrap}
.stackbar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--track)}
.stackbar>div{height:100%}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--fg2)}
.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:4px}
/* ---------- 开关 ---------- */
.sw{display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none;font-size:12px;color:var(--fg2);white-space:nowrap}
.sw-track{width:34px;height:20px;border-radius:9999px;background:var(--track);position:relative;transition:background var(--motion-pop);flex-shrink:0}
.sw-track::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--ds-background-100);transition:transform .18s;box-shadow:0 1px 2px rgba(0,0,0,.2)}
.sw.on{color:var(--fg)}
/* 开关与复选框取同一个 Geist 蓝：两者并排时不能像两套控件 */
.sw.on .sw-track{background:var(--ds-blue-700)}
.sw.on .sw-track::after{transform:translateX(14px)}
.sw.sm .sw-track{width:30px;height:18px}
.sw.sm .sw-track::after{width:14px;height:14px}
.sw.sm.on .sw-track::after{transform:translateX(12px)}
/* ---------- 操作列 ---------- */
.acts{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.acts .sep{width:1px;height:18px;background:var(--line);margin:0 4px;flex-shrink:0}
/* 卡片头右侧的状态行（如备份页「最近备份 / 自动备份」）里也用 .sep 分段：
   这里是行内文本，.sep 必须转成行内块，高度也收到文字高度，否则把行撑高 */
.acts .dim .sep{display:inline-block;vertical-align:middle;height:12px;margin:0 8px}
.field-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.field-row .input{flex:1 1 200px;min-width:160px}
/* ---------- Config ---------- */
/* 配置项只显示可读中文名（悬停给出 desc 说明），不再挂 DEFAULT_ROTATE 这类变量名字样 */
.cfg-name{font-weight:500}
.cfg-val{max-width:340px}
/* 「插件配置」弹窗里配置项的说明：挂在可读名下方单独一行（父级 label 是 block，
   这里必须自己也 block，否则会接在名字同一行）；显示名与说明都来自插件自报，不是键名 */
.pcfg-desc{display:block;font-weight:400;font-size:12px;color:var(--fg3);margin-top:4px}
/* 字典 / 数组配置项在行内只放只读预览：单行省略，完整内容看悬停提示，编辑在弹窗里做 */
.pcfg-json{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg3)}
/* JSON 编辑弹窗的文本框与提示行：间距只在这里给一份，不在标记里写内联样式。
   选择器必须带 .modal> 前缀：上面那条 `.modal>.input{width:100%}` 是 (0,2,0)，
   单写 .json-edit 的 (0,1,0) 压不住它，height / min-height 会被 .input 的行高约束吃掉 */
.modal>textarea.json-edit{width:100%;height:auto;min-height:200px;padding:8px 16px;line-height:1.6;resize:vertical}
.json-edit-hint{margin-top:8px}
.cfg-group{margin-bottom:16px;border-radius:var(--r-md);box-shadow:var(--ring);overflow:hidden;background:var(--ds-background-100)}
.cfg-group:last-child{margin-bottom:0}
.cfg-group-h{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;padding:16px;background:var(--soft);border-bottom:1px solid var(--line)}
.cfg-group table th:first-child,.cfg-group table td:first-child{padding-left:16px}
.cfg-group table th:last-child,.cfg-group table td:last-child{padding-right:16px}
/* 分页条样式在共享层（.pager）：用户控制台同样用它，不能只放在面板 CSS 里 */
/* ---------- 测试 ---------- */
.test-form{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}
.test-field{display:flex;flex-direction:column;gap:4px;min-width:0}
.test-field>span{font-size:12px;color:var(--fg2)}
.test-field.sel{width:120px;flex:0 0 auto}
.test-field.num{width:100px;flex:0 0 auto}
.payload{max-height:220px;overflow:auto;white-space:pre-wrap;line-height:1.6}
.res-err{color:var(--red-deep);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ---------- 设置（分类菜单在侧栏里，右侧只剩配置项） ---------- */
/* 进入设置后整条左侧栏换成设置分类菜单（#set-menu，见 admin_js_config.renderSetMenu），
   右侧这一栏只渲染选中分类的配置表。原先散在各分页的配置卡片全部收敛到这里，
   所以这一页是所有配置项的唯一入口 */
.set-menu{display:flex;flex-direction:column;gap:4px}
/* 分类项外观与主菜单项一致（同底、同选中态、同行高），折叠成图标条后同样只剩图标 */
.set-item{position:relative;display:flex;align-items:center;gap:8px;min-height:36px;padding:8px;border-radius:var(--r-sm);font-size:14px;font-weight:500;color:var(--fg2);cursor:pointer;transition:background var(--motion-fast),color var(--motion-fast);white-space:nowrap}
.set-item:hover{color:var(--fg);background:var(--soft)}
.set-item.on{background:var(--soft-2);color:var(--fg)}
.set-item .cnt{margin-left:auto;font-size:11px;font-weight:400;color:var(--fg3)}
.set-sep{height:1px;background:var(--line);margin:8px}
/* 右侧配置栏：原先是 .set-shell 的内右栏，现在自己就是一张卡片 */
.set-body{min-width:0;display:flex;flex-direction:column;background:var(--ds-background-100);border-radius:var(--r-md);box-shadow:var(--card-shadow);overflow:hidden}
.set-head{display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding:16px 24px;border-bottom:1px solid var(--line)}
.set-head h2{font-size:16px;font-weight:600;letter-spacing:-.3px}
.set-head .dim{white-space:nowrap}
#set-cfg,#set-about{display:flex;flex-direction:column}
#set-cfg[hidden],#set-about[hidden]{display:none}
/* 关于页：版本信息与操作两组卡片，边距与配置表所在的这一栏保持一致 */
#set-about>.card{margin:16px 24px}
#set-about>.card:last-child{margin-bottom:24px}
.about-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.about-note{margin-top:16px;font-size:12px;line-height:1.6}
/* 折叠成图标条。只作用于宽屏：窄屏侧栏本来就是抽屉，「窄条」没有意义，
   折叠态在那边必须当作不存在，否则抽屉会被压成 56px */
@media (min-width:901px){
  .shell.folded{grid-template-columns:56px 1fr}
  /* 无侧栏时折叠态没有意义：侧栏整条隐藏，再留一列 56px 就是一块空白 */
  .shell.nonav{grid-template-columns:1fr}
  /* 折叠态窄到 56px：站名收起的规则在上面，logo 也一并收起——否则 26px 的标记
     与 26px 的按钮加起来就撑破了这一列；此时品牌区只剩那个「>」按钮 */
  .shell.folded .side-brand{justify-content:center;gap:4px;padding:0}
  .shell.folded .side-brand .logo{display:none}
  .shell.folded .side-brand .icon-btn,
  .shell.folded .side-brand .snav-back{width:26px;height:26px}
  .shell.folded .brand-text,
  .shell.folded .snav .tab .lbl,
  .shell.folded .set-item .lbl,
  .shell.folded .set-item .cnt,
  .shell.folded .snav-foot .nm{display:none}
  .shell.folded .snav .tab,
  .shell.folded .set-item{justify-content:center;padding:8px 0}
  /* 折叠态不展开二级菜单：点击带分组的项会先把侧栏展开回来（见 switchTab） */
  .shell.folded .snav-sub,
  .shell.folded .snav-arrow{display:none}
  .shell.folded .snav-foot{flex-direction:column;gap:8px;padding:16px 0}
}
/* 窄屏：侧边栏转为抽屉 */
@media (max-width:900px){
  .shell,.shell.folded{grid-template-columns:1fr}
  .sidebar{position:fixed;top:0;left:0;bottom:0;width:252px;height:100%;transform:translateX(-100%);transition:transform .2s ease;box-shadow:var(--sh-2)}
  .sidebar.open{transform:none}
  .snav-mask{display:block;position:fixed;inset:0;z-index:115;background:var(--scrim);opacity:0;pointer-events:none;transition:opacity var(--motion-pop)}
  .snav-mask.open{opacity:1;pointer-events:auto}
  .snav-toggle{display:inline-flex}
  /* 抽屉本身就是「收起」形态，窄屏不再提供图标条折叠 */
  .side-brand [data-act="snav-fold-toggle"]{display:none}
  /* 概览上下卡的分栏在窄屏降为单列：分隔线由右边界改成下边界 */
  .ovhero,.ovlow{grid-template-columns:1fr}
  .ovshot{border-right:none;border-bottom:1px solid var(--line)}
}
/* 窄屏取值与用户控制台那一份逐字对齐（other_pages.py 的同名断点）：同一个卡片在两个
   界面里必须缩成一样，否则同一块屏幕换一边看内边距就变了 */
@media (max-width:640px){
  main{padding:16px 16px 40px}
  .topbar{padding:0 16px}
  .card-header{padding:16px}
  .card-body{padding:16px}
  th,td{padding-left:8px;padding-right:8px}
  .set-head{padding:16px}
  #set-about>.card{margin:16px}
}
{{ACCOUNT_CSS}}
</style>'''
# 面板页 HTML 骨架，到内联 <script> 开标签为止
# {{THEME_INIT}} 必须在 <head> 里、样式生效之前跑完，否则会先按浅色画一帧再翻黑（闪白）
ADMIN_BODY = r'''{{THEME_INIT}}
</head>
<body>
<div class="shell">
<aside class="sidebar" id="sidebar">
  <div class="side-brand">
    <span class="logo">{{LOGO}}<span class="brand-text">eInkViews</span></span>
    <button class="snav-back" type="button" data-act="set-home" hidden title="{{T:nav.back_home}}" aria-label="{{T:nav.back_home}}"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 3.5L2.5 8 7 12.5M3 8h10.5"/></svg></button>
    <!-- 折叠/展开侧栏：贴着 logo 与站名，箭头指向侧栏将要移动的方向——
         展开态显示「<」（点了往左收），折叠态显示「>」（点了往右展） -->
    <button class="icon-btn" type="button" data-act="snav-fold-toggle" aria-expanded="true" title="{{T:nav.collapse}}" aria-label="{{T:nav.collapse}}"><svg class="ic chev-in" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.8 3.5L5.3 8l4.5 4.5"/></svg><svg class="ic chev-out" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.2 3.5L10.7 8l-4.5 4.5"/></svg></button>
  </div>
  <nav class="snav" id="snav">
    <div class="snav-group"><span class="tab" data-page="overview" onclick="switchTab('overview')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/></svg><span class="lbl">{{T:nav.overview}}</span></span></div>
    <div class="snav-group"><span class="tab" data-page="plugins" onclick="switchTab('plugins')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 1.8l5.5 2.7v7L8 14.2 2.5 11.5v-7z"/><path d="M2.5 4.5L8 7.2l5.5-2.7M8 7.2v7"/></svg><span class="lbl">{{T:nav.plugins}}</span><span class="nav-dot" id="plugins-dot" style="display:none"></span></span></div>
    <div class="snav-group" id="snav-group-users">
      <span class="tab" data-page="users" onclick="toggleSnavFold('users')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="5.5" r="2.3"/><path d="M1.8 13.5c0-2.3 1.9-3.6 4.2-3.6s4.2 1.3 4.2 3.6"/><path d="M11.2 3.7a2.2 2.2 0 0 1 0 4.1M12.4 13.5c0-1.4-.5-2.5-1.4-3.2"/></svg><span class="lbl">{{T:nav.users}}</span><span class="nav-dot" id="apps-dot" style="display:none"></span></span>
      <button class="snav-arrow" type="button" data-act="snav-fold" data-group="users" aria-expanded="false" aria-label="{{T:nav.expand}}"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.5l4 4 4-4"/></svg></button>
    </div>
    <div class="snav-sub" id="snav-sub-users" data-group="users" hidden>
      <span class="tab" data-page="users" data-sub="groups" onclick="switchTab('users','groups')"><span class="lbl">{{T:user.groups}}</span></span>
      <span class="tab" data-page="users" data-sub="accounts" onclick="switchTab('users','accounts')"><span class="lbl">{{T:user.accounts}}</span></span>
      <span class="tab" data-page="users" data-sub="codes" onclick="switchTab('users','codes')"><span class="lbl">{{T:user.codes}}</span></span>
      <span class="tab" data-page="users" data-sub="apps" onclick="switchTab('users','apps')"><span class="lbl">{{T:user.apps}}</span><span class="nav-dot" id="apps-dot2" style="display:none"></span></span>
      <span class="tab" id="nav-ann" data-page="users" data-sub="announce" onclick="switchTab('users','announce')"><span class="lbl">{{T:announce.nav}}</span></span>
    </div>
    <div class="snav-group"><span class="tab" data-page="test" onclick="switchTab('test')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 2.5h3v3l3.1 5.9a1.5 1.5 0 0 1-1.3 2.1H4.7a1.5 1.5 0 0 1-1.3-2.1L6.5 5.5z"/><path d="M5.3 9.5h5.4"/></svg><span class="lbl">{{T:nav.test}}</span></span></div>
    <div class="snav-group" id="snav-group-logs">
      <span class="tab" data-page="logs" onclick="toggleSnavFold('logs')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 2.5h6l3 3v8h-9z"/><path d="M9.5 2.5v3h3M5.7 8.7h4.6M5.7 11.2h4.6"/></svg><span class="lbl">{{T:nav.logs}}</span></span>
      <button class="snav-arrow" type="button" data-act="snav-fold" data-group="logs" aria-expanded="false" aria-label="{{T:nav.expand}}"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.5l4 4 4-4"/></svg></button>
    </div>
    <div class="snav-sub" id="snav-sub-logs" data-group="logs" hidden>
      <span class="tab" data-page="logs" data-sub="request" onclick="switchTab('logs','request')"><span class="lbl">{{T:log.tab_request}}</span></span>
      <span class="tab" data-page="logs" data-sub="audit" onclick="switchTab('logs','audit')"><span class="lbl">{{T:log.tab_audit}}</span></span>
      <span class="tab" data-page="stats" onclick="switchTab('stats')"><span class="lbl">{{T:nav.stats}}</span></span>
    </div>
    <div class="snav-group"><span class="tab" data-page="cache" onclick="switchTab('cache')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><ellipse cx="8" cy="4" rx="4.5" ry="1.8"/><path d="M3.5 4v4c0 1 2 1.8 4.5 1.8s4.5-.8 4.5-1.8V4"/><path d="M3.5 8v4c0 1 2 1.8 4.5 1.8s4.5-.8 4.5-1.8V8"/></svg><span class="lbl">{{T:nav.cache}}</span></span></div>
    <div class="snav-group"><span class="tab" data-page="prerender" onclick="switchTab('prerender')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.2l2.2 1.4"/></svg><span class="lbl">{{T:nav.prerender}}</span></span></div>
    <div class="snav-group"><span class="tab" data-page="backup" onclick="switchTab('backup')"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 2.8h12v2.6H2z"/><path d="M3 5.4h10v7.8H3z"/><path d="M6.4 8.6h3.2"/></svg><span class="lbl">{{T:nav.backup}}</span></span></div>
  </nav>
  <!-- 设置模式：整条侧栏换成设置分类菜单（内容由 renderSetMenu 生成），主菜单同时收起 -->
  <nav class="snav" id="snav-set" hidden>
    <div class="set-menu" id="set-menu" aria-label="{{T:set.categories}}"></div>
  </nav>
  <div class="snav-foot">
    <button class="avatar" type="button" id="nav-avatar" data-act="go-account" title="{{T:nav.account}}" aria-label="{{T:nav.account}}"></button>
    <span class="nm" id="nav-user-name" data-act="go-account"></span>
    <button class="icon-btn" type="button" id="nav-set-btn" data-act="set-enter" title="{{T:nav.config}}" aria-label="{{T:nav.config}}"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/><circle cx="12" cy="12" r="3"/></svg></button>
    <button class="icon-btn" type="button" id="nav-home-btn" data-act="set-home" hidden title="{{T:nav.back_home}}" aria-label="{{T:nav.back_home}}"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 3.5L2.5 8 7 12.5M3 8h10.5"/></svg></button>
    <button class="icon-btn" type="button" data-act="logout" title="{{T:nav.logout}}" aria-label="{{T:nav.logout}}"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 2.5h-3v11h3"/><path d="M10 5.5L12.5 8 10 10.5M12.6 8H6.5"/></svg></button>
  </div>
</aside>
<div class="snav-mask" id="snav-mask" data-act="snav-close"></div>
<div class="workspace">
<header class="topbar">
  <button class="snav-toggle" type="button" data-act="snav-toggle" aria-expanded="false" title="{{T:nav.menu}}" aria-label="{{T:nav.menu}}"><svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11"/></svg></button>
  <nav class="crumbs" id="crumbs" aria-label="{{T:nav.breadcrumb}}"></nav>
  <!-- 深浅色切换：常驻顶栏右端（有无侧栏都一样），图标与悬停说明由共享层的 themePaint 刷 -->
  <button class="icon-btn theme-btn" type="button" data-act="theme-toggle" title="{{T:theme.to_dark}}" aria-label="{{T:theme.to_dark}}"></button>
  <!-- 无侧栏时（除「我的」外没有任何分页权限）这一组落在顶栏右侧 -->
  <div class="topbar-user" id="topbar-user" hidden>
    <button class="avatar" type="button" id="top-avatar" data-act="go-account" title="{{T:nav.account}}" aria-label="{{T:nav.account}}"></button>
    <span class="nm" id="top-user-name" data-act="go-account"></span>
    <button class="icon-btn" type="button" id="top-set-btn" data-act="set-enter" title="{{T:nav.config}}" aria-label="{{T:nav.config}}"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/><circle cx="12" cy="12" r="3"/></svg></button>
    <button class="icon-btn" type="button" data-act="logout" title="{{T:nav.logout}}" aria-label="{{T:nav.logout}}"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 2.5h-3v11h3"/><path d="M10 5.5L12.5 8 10 10.5M12.6 8H6.5"/></svg></button>
  </div>
</header>
<main>

<!-- ============ 概览 ============ -->
<div class="page on" id="page-overview">
  <div class="page-head">
    <div class="acts"><button class="btn btn-sm" onclick="refreshOverview()">{{T:btn.refresh}}</button></div>
  </div>
  <!-- 上卡：左「主页缩略图」预览，右运行信息（状态 / 运行时间 / 版本 + 一组 KPI）。
       缩略图不用 iframe —— 首页对 HTML 响应发 X-Frame-Options: DENY，嵌不进来；
       改由脚本按首页真实结构在 <canvas> 上等比绘制（见 admin_js_overview.py），
       整块是一个指向主页的链接，点开即新标签页访问。 -->
  <div class="card ovhero">
    <div class="ovshot">
      <a class="ovshot-frame" href="/" target="_blank" rel="noopener noreferrer" title="{{T:overview.shot_open}}" aria-label="{{T:overview.shot_open}}">
        <canvas id="ov-shot" width="1280" height="800" aria-hidden="true"></canvas>
      </a>
    </div>
    <div class="ovinfo">
      <div class="def-grid">
        <div class="def"><div class="def-k">{{T:overview.status_label}}</div><div class="def-v" id="ov-status">-</div></div>
        <div class="def"><div class="def-k">{{T:overview.uptime_label}}</div><div class="def-v big" id="ov-uptime">-</div></div>
      </div>
      <div class="def-grid" id="ov-info-top">{{T:msg.loading}}</div>
      <div class="ovinfo-kpi"><div class="def-grid kpi" id="ov-kpi-top">{{T:msg.loading}}</div></div>
    </div>
  </div>
  <!-- 下卡：健康度 + 其余运行信息 + 一组 KPI -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:overview.info_title}}</h2></div>
    </div>
    <div class="card-body">
      <div class="ovlow">
        <div id="ov-health">{{T:msg.loading}}</div>
        <div class="def-grid" id="ov-info-bottom">{{T:msg.loading}}</div>
      </div>
      <div class="def-grid kpi" id="ov-kpi-bottom">{{T:msg.loading}}</div>
    </div>
  </div>
</div>

<!-- ============ 插件 ============ -->
<div class="page" id="page-plugins">
  <div class="page-head">
    <div class="acts"><span class="file-pick">
        <label class="btn btn-sm" for="plugin-zip">{{T:plugin.install_btn}}</label>
        <input type="file" id="plugin-zip" accept=".zip,application/zip" onchange="addPlugin(this)">
      </span><button class="btn btn-sm" data-act="plugins-reload">{{T:plugin.reload}}</button><button class="btn btn-sm" onclick="refreshPlugins()">{{T:btn.refresh}}</button></div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:plugin.title}}</h2></div>
    </div>
    <div class="card-body" id="plugins-area">{{T:msg.loading}}</div>
  </div>
</div>

<!-- ============ 测试 ============ -->
<div class="page" id="page-test">
  <div class="page-head">
    <div class="acts"><button class="btn btn-sm" onclick="clearTestResults()">{{T:test.clear_results}}</button></div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:test.req_config}}</h2></div>
    </div>
    <div class="card-body">
      <div class="test-form">
        <div class="test-field" style="flex:1 1 260px"><span>{{T:test.path}}</span><input class="input" id="t-path" placeholder="{{T:test.path_ph}}"></div>
        <div class="test-field" style="flex:2 1 320px"><span>{{T:test.params}}</span><input class="input" id="t-params" placeholder="lat=39.9&amp;lon=116.4&amp;tz=8"></div>
      </div>
      <div class="test-form" style="margin-top:16px">
        <div class="test-field sel"><span>{{T:test.mode}}</span>
          <select class="input" id="t-mode" onchange="syncTestMode()">
            <option value="single">{{T:test.mode_single}}</option>
            <option value="sequence">{{T:test.mode_sequence}}</option>
            <option value="concurrent">{{T:test.mode_concurrent}}</option>
          </select>
        </div>
        <div class="test-field num"><span>{{T:test.count}}</span><input class="input" type="number" id="t-count" value="1" min="1" max="200" onchange="syncTestMode()"></div>
        <div class="test-field num"><span>{{T:test.conc}}</span><input class="input" type="number" id="t-conc" value="4" min="1" max="50" disabled></div>
        <button class="btn btn-primary" id="t-run" onclick="runTest(this)">{{T:test.run}}</button>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:test.payload_title}}</h2><div class="card-desc" id="t-payload-note">{{T:test.payload_note}}</div></div>
    </div>
    <div class="card-body"><div class="panel mono payload" id="t-payload">{{T:test.no_request}}</div></div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:test.result_title}}</h2><div class="card-desc" id="t-summary-note">{{T:test.waiting}}</div></div>
    </div>
    <div class="card-body">
      <div class="metrics" id="t-summary"></div>
      <div id="t-results" style="overflow-x:auto"><div class="empty">{{T:test.no_result}}</div></div>
    </div>
  </div>
  <div class="card">
    <!-- 接口清单：替代 prod 下打不开的 /docs。这里是「业务接口」，不含后台自身端点 -->
    <div class="card-header">
      <div class="card-title"><h2>{{T:test.api_title}}</h2><div class="card-desc" id="ad-note">{{T:test.api_note}}</div>
        <div class="dot-legend">
          <div class="lg-row"><em>{{T:test.auth_legend}}</em>
            <span class="lg-item" title="{{T:test.evkey_needed_tip}}"><i class="dot dot-on"></i>{{T:test.evkey_needed}}</span>
            <span class="lg-item" title="{{T:test.free_auth_tip}}"><i class="dot dot-off"></i>{{T:test.free_auth}}</span>
          </div>
        </div></div>
      <div class="acts">
        <input class="input" id="ad-search" placeholder="{{T:test.search_ph}}" style="width:180px" oninput="adSearch()">
        <button class="btn btn-sm" onclick="refreshApiDocs()">{{T:btn.refresh}}</button>
      </div>
    </div>
    <div class="card-body" id="ad-list" style="overflow-x:auto"><span class="dim small">{{T:msg.loading}}</span></div>
  </div>
</div>

<!-- ============ 用户 ============ -->
<div class="page" id="page-users">
  <div id="user-sub-groups">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><h2>{{T:user.groups}}</h2><div class="card-desc">{{T:user.limit_note}}</div>
          <div class="dot-legend">
            <div class="lg-row"><em>{{T:user.legend_mark}}</em>
              <span class="lg-item" title="{{T:user.builtin_tip}}"><i class="dot dot-in"></i>{{T:user.builtin}}</span>
              <span class="lg-item" title="{{T:user.default_tip}}"><i class="dot dot-def"></i>{{T:user.default_group}}</span>
            </div>
            <div class="lg-row"><em>{{T:user.legend_category}}</em>
              <span class="lg-item" title="{{T:user.admin_tip}}"><i class="dot dot-admin"></i>{{T:user.admin_group}}</span>
              <span class="lg-item" title="{{T:user.user_tip}}"><i class="dot dot-user"></i>{{T:user.user_group}}</span>
            </div>
          </div></div>
        <div class="acts">
          <input class="input" id="grp-search" placeholder="{{T:user.search_groups_ph}}" style="width:180px" oninput="grpSearch()">
          <button class="btn btn-primary btn-sm" onclick="showGroupModal(0)">{{T:user.new_group}}</button>
        </div>
      </div>
      <div class="card-body" id="groups-area">{{T:msg.loading}}</div>
    </div>
  </div>
  <div id="user-sub-accounts" style="display:none">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><h2>{{T:user.accounts_title}}</h2>
          <div class="dot-legend">
            <div class="lg-row"><em>{{T:user.legend_status}}</em>
              <span class="lg-item"><i class="dot dot-on"></i>{{T:user.enabled}}</span>
              <span class="lg-item"><i class="dot dot-off"></i>{{T:user.disabled}}</span>
            </div>
          </div></div>
        <div class="acts">
          <input class="input" id="acct-search" placeholder="{{T:user.search_accounts_ph}}" style="width:200px" oninput="acctSearch()">
          <select class="input" id="acct-sort" onchange="acctSortChange()" title="{{T:user.sort_tip}}">
            <option value="uid">{{T:user.sort_uid_asc}}</option>
            <option value="uid-desc">{{T:user.sort_uid_desc}}</option>
            <option value="name">{{T:user.sort_name}}</option>
            <option value="group">{{T:user.groups}}</option>
          </select>
          <button class="btn btn-primary btn-sm" onclick="showAccountModal(0)">{{T:user.new_account}}</button>
        </div>
      </div>
      <div class="card-body" id="accounts-area">{{T:msg.loading}}</div>
    </div>
  </div>
  <div id="user-sub-codes" style="display:none">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><h2>{{T:user.codes}}</h2>
          <div class="dot-legend">
            <div class="lg-row"><em>{{T:user.legend_repeat}}</em>
              <span class="lg-item"><i class="dot dot-on"></i>{{T:user.repeatable}}</span>
              <span class="lg-item"><i class="dot dot-off"></i>{{T:user.once}}</span>
            </div>
            <div class="lg-row"><em>{{T:user.legend_status}}</em>
              <span class="lg-item"><i class="dot dot-on"></i>{{T:user.available}}</span>
              <span class="lg-item"><i class="dot dot-off"></i>{{T:user.inactive}}</span>
            </div>
          </div></div>
        <div class="acts">
          <select class="input" id="code-group-filter" onchange="setCodeFilter(this.value)" title="{{T:user.filter_group_tip}}"></select>
          <button class="btn btn-sm" onclick="refreshCodes()">{{T:btn.refresh}}</button>
          <button class="btn btn-primary btn-sm" onclick="showCodeModal()">{{T:user.gen_codes}}</button>
        </div>
      </div>
      <div class="card-body" id="codes-area">{{T:msg.loading}}</div>
    </div>
  </div>
  <div id="user-sub-apps" style="display:none">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><h2>{{T:user.apps_title}}</h2></div>
        <div class="acts">
          <button class="btn btn-sm" onclick="refreshApplications()">{{T:btn.refresh}}</button>
        </div>
      </div>
      <div class="card-body" id="apps-area">{{T:msg.loading}}</div>
    </div>
  </div>
  <div id="user-sub-announce" style="display:none">
    <!-- 发信入口只留一个只读输入框 + 一个「新建」按钮：点任一处开弹窗，
         标题 / 内容 / 可见范围都在弹窗里填（表单堆叠在卡片里会把页面撑得很长） -->
    <div class="card">
      <div class="card-body">
        <div class="ann-new">
          <input class="input" id="ann-open" readonly autocomplete="off" placeholder="{{T:announce.compose_ph}}" data-act="ann-new">
          <button class="btn btn-primary" data-act="ann-new">{{T:announce.new}}</button>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><h2>{{T:announce.history_title}}</h2></div>
        <div class="acts"><button class="btn btn-sm" onclick="refreshAnnouncements()">{{T:btn.refresh}}</button></div>
      </div>
      <div class="card-body" id="ann-area">{{T:msg.loading}}</div>
    </div>
  </div>
</div>

<!-- ============ 日志 ============ -->
<div class="page" id="page-logs">
  <div class="page-head">
    <div class="acts">
      <button class="btn btn-sm" onclick="refreshLogView()">{{T:btn.refresh}}</button>
    </div>
  </div>
  <div id="log-view-request">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:log.title}}</h2><div class="card-desc" id="log-page-info">{{T:msg.loading}}</div>
        <div class="card-desc" style="margin-top:8px">
          <span class="lgd-code" style="color:var(--fg)">{{T:log.code_2xx}}</span>
          <span class="lgd-code" style="color:var(--blue-deep)">{{T:log.code_3xx}}</span>
          <span class="lgd-code" style="color:var(--orange-deep)">{{T:log.code_4xx}}</span>
          <span class="lgd-code" style="color:var(--red-deep)">{{T:log.code_5xx}}</span>
        </div></div>
      <div class="acts">
        <select class="input" id="log-plugin" onchange="logResetAndRefresh()"><option value="">{{T:log.all_plugins}}</option></select>
        <select class="input" id="log-account" onchange="logResetAndRefresh()"><option value="">{{T:log.all_accounts}}</option></select>
        <select class="input" id="log-status" onchange="logResetAndRefresh()"><option value="">{{T:log.all_status}}</option><option value="400">4xx+</option><option value="500">5xx</option></select>
        <select class="input" id="log-pagesize" onchange="_logPageSize=parseInt(this.value);logResetAndRefresh()"><option value="50">{{T:log.rows_50}}</option><option value="100" selected>{{T:log.rows_100}}</option><option value="200">{{T:log.rows_200}}</option></select>
        <span class="sep"></span>
        <button class="btn btn-sm btn-ghost" id="log-prev" data-act="log-page" data-dir="-1">{{T:pager.prev}}</button>
        <button class="btn btn-sm btn-ghost" id="log-next" data-act="log-page" data-dir="1">{{T:pager.next}}</button>
        <span class="sep"></span>
        <button class="btn btn-sm" onclick="exportLogs('csv')">CSV</button>
        <button class="btn btn-sm" onclick="exportLogs('json')">JSON</button>
        <button class="btn btn-sm btn-danger" onclick="clearLogs()">{{T:log.clear}}</button>
      </div>
    </div>
    <div class="card-body" id="logs-area" style="overflow-x:auto">{{T:msg.loading}}</div>
  </div>
  </div>
  <div id="log-view-audit" style="display:none">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:log.tab_audit}}</h2><div class="card-desc" id="audit-page-info">{{T:msg.loading}}</div></div>
      <div class="acts">
        <button class="btn btn-sm btn-ghost" id="audit-prev" data-act="audit-page" data-dir="-1">{{T:pager.prev}}</button>
        <button class="btn btn-sm btn-ghost" id="audit-next" data-act="audit-page" data-dir="1">{{T:pager.next}}</button>
        <span class="sep"></span>
        <button class="btn btn-sm btn-danger" onclick="clearAuditLogs()">{{T:log.clear}}</button>
      </div>
    </div>
    <div class="card-body" id="audit-area" style="overflow-x:auto">{{T:msg.loading}}</div>
  </div>
  </div>
</div>

<!-- ============ 缓存 ============ -->
<div class="page" id="page-cache">
  <div class="page-head">
    <div class="acts">
      <button class="btn btn-sm" onclick="refreshCache()">{{T:btn.refresh}}</button>
      <span class="sep"></span>
      <button class="btn btn-sm btn-danger" onclick="clearCache()">{{T:cache.clear_all}}</button>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:cache.overview_title}}</h2></div>
    </div>
    <div class="card-body" id="cache-metrics">{{T:msg.loading}}</div>
  </div>
</div>

<!-- ============ 定时 ============ -->
<div class="page" id="page-prerender">
  <div class="page-head">
    <div class="acts">
      <span class="dim small" id="pr-info">{{T:msg.loading}}</span>
      <span class="sep"></span>
      <button class="btn btn-sm" onclick="refreshPrerender()">{{T:btn.refresh}}</button>
      <button class="btn btn-primary btn-sm" data-act="pr-new">{{T:prerender.new_task}}</button>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:prerender.title}}</h2>
        <div class="dot-legend">
          <div class="lg-row"><em>{{T:prerender.legend_last}}</em>
            <span class="lg-item" title="{{T:prerender.ok_tip}}"><i class="dot dot-on"></i>{{T:prerender.status_ok}}</span>
            <span class="lg-item" title="{{T:prerender.skip_tip}}"><i class="dot dot-warn"></i>{{T:prerender.status_skip}}</span>
            <span class="lg-item" title="{{T:prerender.stale_tip}}"><i class="dot dot-warn"></i>{{T:prerender.status_stale}}</span>
            <span class="lg-item" title="{{T:prerender.fail_tip}}"><i class="dot dot-error"></i>{{T:prerender.status_fail}}</span>
          </div>
        </div></div>
    </div>
    <div class="card-body">
      <div class="metrics" id="pr-metrics">{{T:msg.loading}}</div>
      <div id="pr-list" style="overflow-x:auto">{{T:msg.loading}}</div>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:prerender.cache_title}}</h2></div>
      <div class="acts"><button class="btn btn-sm btn-danger" data-act="pr-clear-cache">{{T:prerender.clear_cache}}</button></div>
    </div>
    <div class="card-body"><div class="metrics" id="pr-cache-metrics">{{T:msg.loading}}</div></div>
  </div>
</div>

<!-- ============ 统计 ============ -->
<div class="page" id="page-stats">
  <div class="page-head">
    <div class="acts">
      <select class="input" id="stats-days" onchange="refreshStats()"><option value="1">{{T:stats.days_1}}</option><option value="7" selected>{{T:stats.days_7}}</option><option value="30">{{T:stats.days_30}}</option><option value="90">{{T:stats.days_90}}</option></select>
      <button class="btn btn-sm" onclick="refreshStats()">{{T:btn.refresh}}</button>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:stats.title}}</h2></div>
    </div>
    <div class="card-body">
      <div class="metrics" id="stats-kpis"></div>
      <h3 class="sec-title">{{T:stats.daily}}</h3>
      <div class="chart-box" id="stats-chart"></div>
      <h3 class="sec-title">{{T:stats.status_dist}}</h3>
      <div id="stats-status"></div>
      <h3 class="sec-title">{{T:stats.rank_title}}</h3>
      <div class="subtabs" style="margin-bottom:16px">
        <span class="stab on" data-sv="plugin" onclick="switchStatView('plugin')">{{T:stats.rank_plugin}}</span>
        <span class="stab" data-sv="account" onclick="switchStatView('account')">{{T:stats.rank_account}}</span>
      </div>
      <div id="stats-rank"></div>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:stats.slow_title}}</h2><div class="card-desc">{{T:stats.slow_desc}}</div></div>
    </div>
    <div class="card-body" id="stats-slow">{{T:msg.loading}}</div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:stats.sessions_title}}</h2></div>
    </div>
    <div class="card-body" id="st-sessions">{{T:msg.loading}}</div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:stats.lifetime_title}}</h2></div>
    </div>
    <div class="card-body" id="stats-lifetime">{{T:msg.loading}}</div>
  </div>
</div>

<!-- ============ 设置（所有配置项的唯一入口） ============ -->
<div class="page" id="page-config">
  <div class="page-head">
    <div class="acts">
      <button class="btn btn-sm" onclick="cfgExport()">{{T:config.export}}</button>
      <span class="file-pick">
        <label class="btn btn-sm" for="cfg-import-file">{{T:config.import}}</label>
        <input type="file" id="cfg-import-file" accept=".json,application/json" onchange="cfgImport()">
      </span>
      <button class="btn btn-sm" onclick="refreshConfig()">{{T:btn.refresh}}</button>
    </div>
  </div>
  <div class="set-body">
    <div id="set-cfg">
      <div class="set-head"><h2 id="set-title"></h2><span class="dim small" id="set-count"></span></div>
      <div id="cfg-body">{{T:msg.loading}}</div>
    </div>
    <div id="set-about" hidden></div>
  </div>
</div>

<!-- ============ 备份 ============ -->
<div class="page" id="page-backup">
  <div class="page-head">
    <div class="acts"><button class="btn btn-sm" onclick="refreshBackup()">{{T:btn.refresh}}</button></div>
  </div>
  <div class="metrics" id="bk-metrics">{{T:msg.loading}}</div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:backup.actions_title}}</h2><div class="card-desc">{{T:backup.actions_desc}}</div></div>
      <div class="acts"><span class="dim small" id="bk-last">{{T:msg.loading}}</span></div>
    </div>
    <div class="card-body">
      <div class="test-form">
        <button class="btn btn-primary" data-act="bk-download">{{T:backup.download}}</button>
        <span class="file-pick">
          <label class="btn" for="bk-file">{{T:backup.pick_file}}</label>
          <input type="file" id="bk-file" accept=".db,application/octet-stream" onchange="bkPick()">
        </span>
        <button class="btn btn-danger-solid" id="bk-restore" data-act="bk-restore" disabled>{{T:backup.restore}}</button>
      </div>
      <p class="dim small" id="bk-file-note" style="margin-top:16px">{{T:backup.no_file}}</p>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:backup.files_title}}</h2><div class="card-desc">{{T:backup.files_desc}}</div></div>
      <div class="acts"><button class="btn btn-sm" data-act="bk-clean">{{T:backup.cleanup}}</button></div>
    </div>
    <div class="card-body" id="bk-files"><span class="dim small">{{T:msg.loading}}</span></div>
  </div>
</div>

<!-- ============ 账号 ============ -->
<div class="page" id="page-account">
  <!-- 卡片与用户控制台共用同一份（account_page.ACCOUNT_CARDS）：两边只有「站内信」卡片的差别，
       管理端的站内信在概览页，这里不再重复一张 -->
  {{ACCOUNT_CARDS}}
</div>

</main>
</div>
</div>
<!-- 语言包：服务端按当前语言注入整份注册表，共享脚本里的 T() 据此取词 -->
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>

<script>'''
# 面板页收尾（</script></body></html>）
ADMIN_TAIL = r'''</script>
</body>
</html>'''
