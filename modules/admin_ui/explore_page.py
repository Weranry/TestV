"""访客导航页（`/explore`）的骨架与样式。

这是**唯一一个面向未登录访客**的展示页：把实例里正在运行的插件铺成卡片网格，让人一眼
看清「这台实例能出哪些图、参数怎么传」。因此它不套管理面板的侧栏外壳（访客没有导航权限，
套上只会露出一堆点了就 401 的入口），只复用 `shared_ui` 的设计令牌与主题初始化。

卡片是**单面**：宽屏一行三个，只放身份信息（名称 / 作者 / 描述 / 可用用户组）。四段的行数
定死（标题 1 行、作者 1 行、描述 3 行、用户组 2 行，超出截断），卡片高度因此恒定、同一行
严格齐平；版本号等明细收进弹窗。
点开卡片弹出的弹窗才放明细（路由、可选尺寸、插件参数），明细内容作为 `<template>` 内联在
每张卡片里，脚本只做「取出来塞进弹窗」，不在前端二次拉数据——访客页没有登录态，多一个
接口就多一处要保证「不泄露内部路由」的地方。
"""

EXPLORE_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:explore.title}}</title>
<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);color:var(--fg);min-height:100vh}
.wrap{max-width:1140px;margin:0 auto;padding:32px 24px 64px}
/* 顶栏：logo 回首页，右侧给一个登录入口（访客页唯一的跳出点） */
.hd{display:flex;align-items:center;gap:8px;margin-bottom:24px}
.hd .brand{display:flex;align-items:center;gap:8px;font-size:16px;font-weight:600;letter-spacing:-.3px;color:var(--fg);text-decoration:none}
.hd .brand:hover{opacity:.75}
/* 顶栏品牌放大：只动访客页顶栏这一处——共享层的 .logo-mark 是全局 20×20
   （侧栏、概览缩略图都在用），不能改。高度必须一起给：这个 svg 的 viewBox 是竖版，
   只改宽度的话高度仍被 20px 钉住、图形反而更小，宽度也白留 */
.hd .brand .logo-mark{width:32px;height:32px}
.hd .brand>span{font-size:24px}
.hd .sp{flex:1}
.hd .lnk{font-size:12px;color:var(--fg2);text-decoration:none;padding:8px 16px;border-radius:var(--r-sm);box-shadow:inset 0 0 0 1px var(--line);transition:all var(--motion-fast)}
.hd .lnk:hover{color:var(--fg);background:var(--soft)}
/* 框架版本号：挂在顶栏品牌旁，说明这一页由哪个框架版本渲染。
   等宽小字 + 淡色胶囊，不抢标题与卡片的层级 */
.hd .ver{font-family:var(--mono);font-size:11px;color:var(--fg3);padding:2px 8px;border-radius:999px;background:var(--soft);align-self:center}
h1{font-size:32px;font-weight:600;letter-spacing:-1px}
/* 分区栏：页头（这一页是什么）与卡片网格（有哪些插件）之间的结构线。
   没有它时，标题、数量、卡片是三层同样口吻的堆叠，层次读不出来 */
.secbar{display:flex;align-items:baseline;justify-content:space-between;gap:16px;
  margin-top:24px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.secbar-t{font-size:14px;font-weight:600;letter-spacing:-.2px;color:var(--fg)}
.secbar-c{font-size:12px;color:var(--fg3)}
/* 网格：宽屏一行三个，窄屏逐级降到两列 / 单列。卡片高度由内容（四段固定行数）决定，
   不再用 aspect-ratio 撑正方形——内容之外的地方全成了空白 */
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}
/* 空态：真没插件（或占位兜底页）时铺在这一格网格里。它跨满整行，纵向排一句说明 + 一个
   「阅读文档」按钮——留白但不至于让人以为页面坏了 */
.empty{grid-column:1/-1;display:flex;flex-direction:column;align-items:flex-start;gap:12px;
  font-size:14px;color:var(--fg3);padding:32px 0}
.empty-btn{display:inline-flex;align-items:center;font-size:13px;font-weight:500;color:var(--fg);
  text-decoration:none;padding:8px 16px;border-radius:var(--r-sm);box-shadow:inset 0 0 0 1px var(--line);
  transition:all var(--motion-fast)}
.empty-btn:hover{color:var(--fg);background:var(--soft)}
/* ============ 卡片（单面，点击开弹窗） ============ */
/* 高度不靠 aspect-ratio 撑：四段各自的行数是硬上限——标题 1 行、作者 1 行、描述 3 行、
   用户组 2 行，加起来高度恒定，同一行的卡片因此天然齐平，内容超了截断 */
.xcard{display:flex;flex-direction:column;padding:16px;border-radius:var(--r-md);
  background:var(--ds-background-100);box-shadow:var(--sh-1);cursor:pointer;outline:none;overflow:hidden;
  transition:box-shadow var(--motion-fast),transform var(--motion-fast)}
.xcard:hover{box-shadow:var(--sh-2);transform:translateY(-1px)}
.xcard:focus-visible{box-shadow:var(--ds-focus-ring)}
/* 名称一行；作者一行——**没有作者也占着这一行的高度**，否则有 / 没作者的卡片会差出一行 */
.xname{flex-shrink:0;font-size:16px;font-weight:600;letter-spacing:-.4px;line-height:24px;height:24px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xby{flex-shrink:0;margin-top:4px;font-size:12px;line-height:18px;height:18px;color:var(--fg3);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* 描述固定三行：短的留白、长的在第三行收省略号，卡片高度不随描述长短变 */
.xdesc{flex-shrink:0;margin-top:8px;font-size:14px;line-height:20px;height:60px;color:var(--fg2);
  overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
/* 可用用户组直接铺标签、不再先写一行「可用用户组」：固定两行高度，超出的组裁掉。
   align-content:flex-end——单排标签沉在第二排（底部）对齐，只有一排放不下、
   溢出成两排时才从第一排开始铺满这两排 */
.xtags{flex-shrink:0;display:flex;flex-wrap:wrap;align-content:flex-end;gap:8px;margin-top:8px;
  height:48px;overflow:hidden}
.xtags .xnone{font-size:12px;color:var(--fg3)}
.chip{display:inline-block;font-size:11px;line-height:1.7;padding:1px 8px;border-radius:999px;
  background:var(--soft);color:var(--fg2);box-shadow:inset 0 0 0 1px var(--line)}
/* 「全部用户组」用蓝色区分：它是一条覆盖全组的结论，与逐个列出的组名不是一回事 */
.chip-all{background:var(--blue-soft);color:var(--blue);box-shadow:none}
/* ============ 明细弹窗 ============ */
/* 宽屏居中定宽，窄屏（媒体查询里）边距收窄、铺满可用宽度；超出高度只滚正文，
   标题与关闭按钮留在原地 */
.xmodal{position:fixed;inset:0;z-index:300;display:flex;align-items:center;justify-content:center;padding:24px}
.xmodal[hidden]{display:none}
.xm-bg{position:absolute;inset:0;background:var(--scrim)}
.xm-box{position:relative;display:flex;flex-direction:column;width:100%;max-width:640px;max-height:calc(100vh - 48px);
  background:var(--ds-background-100);border-radius:var(--r-lg);box-shadow:var(--sh-2);overflow:hidden}
.xm-hd{flex-shrink:0;display:flex;align-items:flex-start;gap:8px;padding:16px 24px;border-bottom:1px solid var(--line-soft)}
.xm-ttl{flex:1;min-width:0}
.xm-name{display:block;font-size:16px;font-weight:600;letter-spacing:-.3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xm-meta{display:block;margin-top:4px;font-size:12px;color:var(--fg3)}
.xm-x{flex-shrink:0;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;border:none;padding:0;
  border-radius:var(--r-sm);background:none;color:var(--fg3);font-size:18px;line-height:1;cursor:pointer;transition:all var(--motion-fast)}
.xm-x:hover{color:var(--fg);background:var(--soft)}
.xm-bd{flex:1;min-height:0;overflow-y:auto;padding:0 24px 24px}
/* 弹窗两段：路由是主角（深色 + 稍大），插件参数次之 */
.sec{font-size:12px;font-weight:600;letter-spacing:-.1px;color:var(--fg2);margin:16px 0 8px}
.rt{display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:1px solid var(--line-soft)}
.rt:last-child{border-bottom:none}
.rt .m{flex-shrink:0;font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--fg3);background:var(--soft);
  padding:0 8px;border-radius:4px;margin-top:1px}
.rtb{flex:1;min-width:0}
.rt .p{display:block;font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--fg);word-break:break-all}
/* 从属层：尺寸属于「这条路由的可选项」，缩进挂在路由下面，用左侧竖线表达从属关系 */
.rtsub{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px;padding-left:8px;
  border-left:2px solid var(--line)}
.rtsub-k{font-size:11px;color:var(--fg3)}
.rtsub-v{font-family:var(--mono);font-size:11px;color:var(--fg2);background:var(--soft);padding:1px 8px;border-radius:4px}
/* 参数只列名字：默认值是插件自带的、装完就不会变，列出来只会盖过参数名本身 */
.pmrow{display:flex;flex-wrap:wrap;gap:8px}
.pmk{font-family:var(--mono);font-size:11px;color:var(--fg2);background:var(--soft);padding:2px 8px;border-radius:4px}
.none{font-size:12px;color:var(--fg3);padding:4px 0}
@media (max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:560px){
  .wrap{padding:24px 16px 48px}
  .grid{grid-template-columns:1fr;gap:16px}
  .xmodal{padding:16px}
  .xm-box{max-height:calc(100vh - 32px);border-radius:var(--r-md)}
  .xm-hd{padding:16px}
  .xm-bd{padding:0 16px 16px}
}
</style>
{{THEME_INIT}}
</head>
<body>
<div class="wrap">
  <div class="hd">
    <a class="brand" href="/">{{LOGO}}<span>eInkViews</span></a>
    <span class="ver">v{{FRAMEWORK_VERSION}}</span>
    <span class="sp"></span>
    <!-- login-entry:start --><a class="lnk" href="/login">{{T:explore.login}}</a><!-- login-entry:end -->
  </div>
  <h1>{{T:explore.title}}</h1>
  <div class="secbar">
    <span class="secbar-t">{{T:explore.section_plugins}}</span>
    <span class="secbar-c">{{EXPLORE_COUNT}}</span>
  </div>
  <div class="grid" id="explore-grid">
{{EXPLORE_CARDS}}
  </div>
</div>
<div class="xmodal" id="xmodal" hidden>
  <div class="xm-bg" data-act="xmodal-close"></div>
  <div class="xm-box" role="dialog" aria-modal="true" aria-labelledby="xm-name">
    <div class="xm-hd">
      <div class="xm-ttl">
        <span class="xm-name" id="xm-name"></span>
        <span class="xm-meta" id="xm-meta"></span>
      </div>
      <button class="xm-x" type="button" data-act="xmodal-close" title="{{T:btn.close}}" aria-label="{{T:btn.close}}">&times;</button>
    </div>
    <div class="xm-bd" id="xm-bd"></div>
  </div>
</div>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
/* 卡片的明细内联在自身的 <template class="xdetail"> 里，打开时原样搬到弹窗——
   前端不新增任何接口（见文件头说明） */
var xm=document.getElementById('xmodal'),xmBd=document.getElementById('xm-bd'),
    xmName=document.getElementById('xm-name'),xmMeta=document.getElementById('xm-meta'),
    xmLast=null;
function xmOpen(card){
  if(!card)return;
  var tpl=card.querySelector('template.xdetail'),nm=card.querySelector('.xname');
  xmName.textContent=nm?nm.textContent:'';
  xmMeta.textContent=card.getAttribute('data-meta')||'';
  xmBd.innerHTML=tpl?tpl.innerHTML:'';
  xm.hidden=false;
  document.body.style.overflow='hidden';
  var btn=xm.querySelector('.xm-x');if(btn)btn.focus();
}
function xmClose(){
  if(xm.hidden)return;
  xm.hidden=true;
  document.body.style.overflow='';
  /* 关掉后把焦点还给刚才那张卡，键盘用户不必从头 Tab 回来 */
  if(xmLast&&xmLast.focus)xmLast.focus();
}
document.addEventListener('click',function(e){
  var t=e.target;
  if(!t||!t.closest)return;
  if(t.closest('[data-act="xmodal-close"]')){xmClose();return}
  var card=t.closest('.xcard');
  if(card){xmLast=card;xmOpen(card)}
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){xmClose();return}
  if(e.key!=='Enter'&&e.key!==' ')return;
  var t=e.target;
  if(!t||!t.closest)return;
  var card=t.closest('.xcard');
  if(!card)return;
  e.preventDefault();
  xmLast=card;xmOpen(card);
});
</script>
</body>
</html>
'''
