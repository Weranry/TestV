/* ================= 登录态 ================= */
/* 系统主管理员（内置管理账号）标记：整库级操作（备份恢复/删除、恢复出厂）与
   管理员账号/用户组管理只对它开放。后端同样按这个口径判定，这里只负责显隐。
   初始为 false：未知身份时先按普通管理员渲染，拿到结果再放开，避免错露高危按钮 */
window.IS_SUPER=false;
function isSuper(){return window.IS_SUPER===true}
/* 非主管理员把整库级入口整块收掉：按钮点下去必被 403，摆在那里只会让人以为是坏了 */
function applySuperUI(){
  var sup=isSuper();
  ['bk-actions-card','bk-files-card'].forEach(function(id){
    var el=document.getElementById(id);
    if(el)el.hidden=!sup;
  });
  // 「关于」里的恢复出厂卡片按身份渲染：恰好已经打开并停在该页时重绘一次
  var aboutBox=document.getElementById('set-about');
  if(aboutBox&&!aboutBox.hidden&&typeof loadAbout==='function')loadAbout();
  // 用户页两个列表的重绘各自读 isSuper()，拿到身份后刷一次把按钮状态纠正过来
  if(tabAllowed('users')){
    if(typeof refreshGroups==='function')refreshGroups();
    if(typeof refreshAccounts==='function')refreshAccounts();
  }
}
function checkLoginStatus(){
  R.get('/admin/api/auth/me').then(function(d){
    if(!d.authenticated){window.location.href='/login';return}
    if(!d.is_admin){window.location.href='/admin';return}
    window.IS_SUPER=!!d.is_super;
    applySuperUI();
    var nm=((d.user&&d.user.name)||'').trim();
    /* 名字写进三处：侧栏栏底（有侧栏时）、顶栏右侧那组（没侧栏时）、以及「我的」页顶栏的
       用户名（只在「我的」页露出，见 paintNotifSlot）；哪一份可见由 .shell.nonav 与当前分页决定 */
    ['nav-user-name','top-user-name','top-name'].forEach(function(id){
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
/* ALLOWED_TABS / SHOW_ANNOUNCEMENT / REFRESH 由页面里的内联 <script data-inline> 声明：
   它们随管理组与配置变化，必须留在 HTML 里；本文件其余部分整块外链缓存。 */
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
/* 站内信可由管理组单独关闭（服务端按 user_groups.show_announcement 注入，SHOW_ANNOUNCEMENT
   由内联启动脚本声明）。关掉时把「用户 ▾」下的站内信入口与子视图一起收掉（留一个点进去
   空白的菜单项没有意义），并且不去拉数据——接口那边同样的判定会返回 403 */
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
if(tabAllowed('users')){checkApps();checkResets();}
if(tabAllowed('devices'))checkDeviceSignins();
if(tabAllowed('plugins')||tabAllowed('test'))loadPluginOptions();
if(tabAllowed('test'))syncTestMode();

/* 自动刷新的分页与间隔（REFRESH）由内联启动脚本声明：只覆盖「数据会自己变」的页
   （概览/插件/用户/日志/统计/我的）。缓存 / 定时 / 备份是快照式列表，切页时与每次操作后
   各刷一次就够；配置页与测试页不自动刷新，否则会覆盖正在编辑的内容。REFRESH 里没有的页，
   refreshActiveSection 也不处理。 */
/* 「我的」页自己也有一条 15 秒固定间隔轮询，而这里的 tick 只要 REFRESH.account>0 就已经
   在刷同一批数据（refreshAccount 覆盖得还更全）。把这个结论告诉 account.js，
   让它别再开第二条——同一份数据每 15 秒被拉两遍纯属白跑 */
window.__SHELL_TICKS_ACCOUNT=!!REFRESH.account;
var _lastTick={};
/* 只刷新当前标签页真实可见的数据，且不动配置页/测试页（会覆盖正在编辑的内容） */
function refreshActiveSection(){
  if(_activeTab==='overview')refreshOverview();
  else if(_activeTab==='plugins')refreshPlugins();
  else if(_activeTab==='users')refreshUserSection();
  else if(_activeTab==='devices')refreshDeviceSection();
  else if(_activeTab==='logs')refreshLogView();
  else if(_activeTab==='stats')refreshStats();
  else if(_activeTab==='account')refreshAccount();
}
function refreshUserSection(){
  if(_userSub==='groups')refreshGroups();
  else if(_userSub==='accounts')refreshAccounts();
  else if(_userSub==='codes')refreshCodes();
  else if(_userSub==='resets')refreshPasswordResets();
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
},1000);