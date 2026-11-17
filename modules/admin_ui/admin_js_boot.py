# JS 登录态与启动/自动刷新
ADMIN_JS_BOOT = r'''/* ================= 登录态 ================= */
function checkLoginStatus(){
  R.get('/admin/api/auth/me').then(function(d){
    if(!d.authenticated){window.location.href='/login';return}
    if(!d.is_admin){window.location.href='/admin';return}
    var nm=((d.user&&d.user.name)||'').trim();
    /* 名字与头像各两份：有侧栏时在栏底，没侧栏时在顶栏右侧（哪一份可见由 .shell.nonav 决定） */
    ['nav-user-name','top-user-name'].forEach(function(id){
      var el=document.getElementById(id);if(el)el.textContent=nm;
    });
    var ini=nm?nm.charAt(0).toUpperCase():'?';
    ['nav-avatar','top-avatar'].forEach(function(id){
      var el=document.getElementById(id);if(el)el.textContent=ini;
    });
  });
}
/* doLogout 是两份外壳共用的通用件，只有一份，在共享层里 */

/* ================= 启动 & 自动刷新 ================= */
/* 当前管理组可访问的后台分页（服务端按用户组 category/admin_tabs 注入，'account' 恒在）。
   标签页隐藏 + 启动请求过滤都在前端做一遍：无权分页的初始化请求会被后端 403，
   留在启动流程里只会在控制台刷一屏红字。 */
var ALLOWED_TABS={{ALLOWED_TABS}};
function tabAllowed(n){return ALLOWED_TABS.indexOf(n)>=0}
/* 除「我的」外一个分页都没有 → 侧栏没有存在意义：整条收掉，头像/设置/退出改放顶栏右侧。
   只要被允许访问任意一个别的分页，侧栏就出现，同时也就可以折叠 */
var HAS_NAV=ALLOWED_TABS.some(function(t){return t!=='account'});
(function initShell(){
  var sh=document.querySelector('.shell'),top=document.getElementById('topbar-user');
  if(!HAS_NAV){
    if(sh)sh.classList.add('nonav');
    if(top)top.hidden=false;
  }
  /* 设置入口受 config 权限控制：没有这个权限的用户连图标都不该看见 */
  var canCfg=tabAllowed('config');
  ['nav-set-btn','top-set-btn'].forEach(function(id){
    var el=document.getElementById(id);if(el)el.hidden=!canCfg;
  });
  /* 折叠状态记在 localStorage：上次收成图标条，这次打开还是图标条 */
  try{if(HAS_NAV&&localStorage.getItem(SNAV_FOLD_KEY)==='1')setSnavFolded(true)}catch(e){}
  syncNavTitles();
})();
/* 站内信可由管理组单独关闭（服务端按 user_groups.show_announcement 注入）。
   关掉时把「用户 ▾」下的站内信入口与子视图一起收掉（留一个点进去空白的菜单项没有意义），
   并且不去拉数据——接口那边同样的判定会返回 403 */
var SHOW_ANNOUNCEMENT={{SHOW_ANNOUNCEMENT}};
(function initAnnouncementCard(){
  if(SHOW_ANNOUNCEMENT)return;
  ['nav-ann','user-sub-announce'].forEach(function(id){
    var el=document.getElementById(id);
    if(el)el.style.display='none';
  });
})();
(function initTabs(){
  var first=null;
  document.querySelectorAll('.tab').forEach(function(t){
    /* first 只认顶层菜单项：无权分页要切走时，切到二级项会让分组标题看着像没选中 */
    if(tabAllowed(t.dataset.page)){if(!first&&!t.closest('.snav-sub'))first=t;return}
    t.style.display='none';
  });
  /* 可展开分组：本组（含二级项）全部无权时，把标题与展开箭头一起收掉——
     只隐藏子项会留下一个点不开的空标题 */
  document.querySelectorAll('.snav-sub').forEach(function(box){
    var g=box.dataset.group,any=tabAllowed(g);
    box.querySelectorAll('.tab').forEach(function(t){if(tabAllowed(t.dataset.page))any=true});
    var grp=g?document.getElementById('snav-group-'+g):null;
    if(grp)grp.style.display=any?'':'none';
    if(!any)box.style.display='none';
  });
  /* 无侧栏（普通用户）：只剩「我的」可去，直接落在那儿 */
  if(!HAS_NAV)switchTab('account');
  // 概览页被关掉时页面还停在概览上：切到第一个可用分页（没有可用分页时保持原样）
  else if(!tabAllowed(_activeTab)&&first)switchTab(first.dataset.page);
  else paintCrumbs(_activeTab);
})();
checkLoginStatus();
if(tabAllowed('overview'))refreshOverview();
if(tabAllowed('users'))checkApps();
if(tabAllowed('plugins')||tabAllowed('test'))loadPluginOptions();
if(tabAllowed('test'))syncTestMode();

/* 自动刷新的分页与间隔：只覆盖「数据会自己变」的页（概览/插件/用户/日志/统计/我的）。
   缓存 / 定时 / 备份是快照式列表，切页时与每次操作后各刷一次就够；配置页与测试页不自动
   刷新，否则会覆盖正在编辑的内容。REFRESH 里没有的页，refreshActiveSection 也不处理。 */
var REFRESH={overview:{{ADMIN_STATUS_REFRESH}},plugins:{{ADMIN_PLUGINS_REFRESH}},users:{{ADMIN_APPS_REFRESH}},logs:{{ADMIN_LOGS_REFRESH}},stats:{{ADMIN_STATS_REFRESH}},account:{{ADMIN_STATUS_REFRESH}}};
/* 「我的」页自己也有一条 15 秒固定间隔轮询，而这里的 tick 只要 REFRESH.account>0 就已经
   在刷同一批数据（refreshAccount 覆盖得还更全）。把这个结论告诉 account_page，
   让它别再开第二条——同一份数据每 15 秒被拉两遍纯属白跑 */
window.__SHELL_TICKS_ACCOUNT=!!REFRESH.account;
var _lastTick={};
/* 只刷新当前标签页真实可见的数据，且不动配置页/测试页（会覆盖正在编辑的内容） */
function refreshActiveSection(){
  if(_activeTab==='overview')refreshOverview();
  else if(_activeTab==='plugins')refreshPlugins();
  else if(_activeTab==='users')refreshUserSection();
  else if(_activeTab==='logs')refreshLogView();
  else if(_activeTab==='stats')refreshStats();
  else if(_activeTab==='account')refreshAccount();
}
function refreshUserSection(){
  if(_userSub==='groups')refreshGroups();
  else if(_userSub==='accounts')refreshAccounts();
  else if(_userSub==='codes')refreshCodes();
  else if(_userSub==='announce')refreshAnnouncements();
  else{refreshApplications();checkApps()}
}
setInterval(function(){
  if(document.hidden)return;
  var iv=REFRESH[_activeTab]||0;if(!iv)return;
  var now=Date.now();
  if(_lastTick[_activeTab]&&now-_lastTick[_activeTab]<iv*1000)return;
  _lastTick[_activeTab]=now;
  refreshActiveSection();
},1000);'''
