# JS 核心：时间换算/分页/统一事件委托/标签切换/配置区块通用逻辑
ADMIN_JS_CORE = r'''/* ================= 基础工具 ================= */
var TZ_OFFSET={{TZ_OFFSET}};
/* fmtDT（UTC → 配置时区）是两份外壳共用的通用件，只有一份，在共享层里 */
function fmtUptime(s){s=Math.max(0,parseInt(s)||0);if(s<60)return T('core.uptime_lt_min','小于1分钟');var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?T('core.uptime_days','{n}天',{n:d}):'')+(h?T('core.uptime_hours','{n}小时',{n:h}):'')+T('core.uptime_mins','{n}分钟',{n:m})}
/* num / 分页（pgPage / pgBar / pgSlice）都由共享层提供，两份同为「通用件」，只此一份 */
/* 列表搜索：把要参与匹配的几个字段拼成小写串做子串匹配（各列表共用一套判定） */
function matchQuery(q,vals){
  if(!q)return true;
  var s=vals.map(function(v){return String(v===null||v===undefined?'':v)}).join(' ').toLowerCase();
  return s.indexOf(q)>=0;
}

/* ================= 统一事件委托 ================= */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act]'):null;
  if(!el)return;
  var act=el.dataset.act;
  switch(act){
    case 'modal-close':{var m=el.closest('.modal-overlay');if(m)m.remove();break}
    case 'plugin-toggle':togglePlugin(el.dataset.name,el);break;
    case 'plugin-routes':showPluginRoutes(el.dataset.name);break;
    case 'plugin-config':showPluginConfig(el.dataset.name);break;
    case 'plugins-reload':reloadPlugins(el);break;
    case 'plugin-uninstall':uninstallPlugin(el.dataset.name,el);break;
    case 'route-toggle':toggleRoute(el.dataset.path,el.dataset.en!=='1',el);break;
    case 'pcfg-save':savePluginCfg(el.dataset.plugin,el.dataset.key,el);break;
    case 'pcfg-sw':pcfgFlip(el);break;
    case 'pcfg-reset':resetPluginCfg(el.dataset.plugin,el.dataset.key);break;
    case 'pcfg-json':pcfgEditJson(el.dataset.plugin,el.dataset.key);break;
    case 'pcfg-save-all':saveAllPluginCfg(el.dataset.plugin,el);break;
    case 'group-edit':showGroupModal(parseInt(el.dataset.id));break;
    case 'group-save':saveGroup(parseInt(el.dataset.id),el);break;
    case 'group-del':delGroup(parseInt(el.dataset.id),el.dataset.name);break;
    case 'group-del-confirm':confirmDelGroup(el);break;
    case 'group-perms':showGroupPerms(parseInt(el.dataset.id),el.dataset.name);break;
    case 'group-default':setDefaultGroup(parseInt(el.dataset.id),el.dataset.name);break;
    case 'group-codes':gotoCodes(parseInt(el.dataset.id));break;
    case 'code-save':createCode(el);break;
    case 'code-toggle':toggleCode(parseInt(el.dataset.id),el.dataset.en!=='1',el);break;
    case 'code-repeat':toggleCodeRepeat(parseInt(el.dataset.id),el.dataset.en!=='1',el);break;
    case 'code-del':delCode(parseInt(el.dataset.id),el.dataset.code);break;
    case 'perm-fold':{
      var fold=document.getElementById('grp-routes-'+el.dataset.id+'-'+el.dataset.idx);
      if(fold){var open=fold.style.display==='none';fold.style.display=open?'':'none';el.textContent=open?T('core.routes_expand','路由 ▴'):T('core.routes_collapse','路由 ▾')}
      break
    }
    case 'perm-toggle':permToggle(el,parseInt(el.dataset.gid),el.dataset.type,el.dataset.name);break;
    case 'param-quick':quickToggleParam(parseInt(el.dataset.gid),el.dataset.key,el.dataset.label,el.dataset.off==='1');break;
    case 'param-del':delGroupParam(parseInt(el.dataset.gid),el.dataset.key);break;
    case 'param-add':addGroupParam(parseInt(el.dataset.gid));break;
    case 'acct-edit':showAccountModal(parseInt(el.dataset.id));break;
    case 'acct-save':saveAccount(parseInt(el.dataset.id),el);break;
    case 'acct-del':delAccount(parseInt(el.dataset.id),el.dataset.name);break;
    case 'acct-detail':showAccountDetail(parseInt(el.dataset.id),el.dataset.name);break;
    case 'acct-detail-tab':setAccountDetailTab(el.dataset.tab);break;
    case 'quota-grant':quotaGrantQuick(parseInt(el.dataset.id),_intVal(el.dataset.amount,0),el);break;
    case 'quota-grant-custom':quotaGrantCustom(parseInt(el.dataset.id),el);break;
    case 'quota-reset':quotaReset(parseInt(el.dataset.id),el);break;
    case 'acct-membership':showMembership(parseInt(el.dataset.id),el.dataset.name);break;
    case 'mem-save':saveMembership(parseInt(el.dataset.id),el);break;
    case 'acct-check':toggleAcctCheck(el);break;
    case 'acct-check-all':toggleAcctCheckAll(el);break;
    case 'acct-clear':clearAcctSel();break;
    case 'acct-transfer':showAcctTransfer();break;
    case 'acct-batch':{
      var op=el.dataset.op;
      if(op==='delete')batchDeleteAccounts();
      else batchAccounts(op);
      break
    }
    case 'evkey-gen':genEvkey(parseInt(el.dataset.id),el);break;
    case 'evkey-toggle':toggleEvkey(parseInt(el.dataset.id),el.dataset.en!=='1',el);break;
    case 'evkey-del':delEvkey(parseInt(el.dataset.id));break;
    case 'copy-text':copyText(el.dataset.copy);break;
    case 'ad-fill':adFill(el.dataset.path);break;
    case 'bk-download':bkDownload(el);break;
    case 'bk-restore':bkRestore();break;
    case 'bk-file-del':bkDeleteFile(el.dataset.name);break;
    case 'bk-file-dl':bkFileDownload(el.dataset.name);break;
    case 'bk-file-restore':bkFileRestore(el.dataset.name);break;
    case 'bk-clean':bkCleanup();break;
    case 'app-approve':approveApp(parseInt(el.dataset.id));break;
    case 'app-reject':rejectApp(parseInt(el.dataset.id));break;
    case 'app-expand':toggleAppGroup(el);break;
    case 'app-check':toggleAppCheck(el);break;
    case 'app-check-all':toggleAppCheckAll(el);break;
    case 'app-clear':clearAppSel();break;
    case 'app-batch':{
      if(el.dataset.op==='approve')batchApproveApps();else batchRejectApps();
      break
    }
    case 'log-page':refreshRequestLogs(parseInt(el.dataset.dir));break;
    case 'log-view':switchLogSubTab(el.dataset.lv);break;
    case 'audit-page':refreshAuditLogs(parseInt(el.dataset.dir));break;
    case 'pr-new':showPrerenderModal(0);break;
    case 'pr-edit':showPrerenderModal(parseInt(el.dataset.id));break;
    case 'pr-save':prSave(el);break;
    case 'pr-del':prDel(parseInt(el.dataset.id));break;
    case 'pr-run':prRun(parseInt(el.dataset.id),el);break;
    case 'pr-detail':prDetail(parseInt(el.dataset.id));break;
    case 'pr-preview':prPreview(parseInt(el.dataset.id));break;
    case 'pr-toggle':prToggle(parseInt(el.dataset.id),el.dataset.en!=='1');break;
    case 'pr-clear-cache':prClearCache();break;
    case 'plugin-expand':togglePluginRoutes(el);break;
    case 'cfg-edit':cfgEdit(el.dataset.key,el);break;
    case 'cfg-json':cfgEditJson(el.dataset.key,el);break;
    case 'cfg-multi':cfgEditMulti(el.dataset.key,el);break;
    case 'cfg-toggle':cfgToggle(el.dataset.key,el.dataset.val,el);break;
    case 'cfg-save':cfgSave(el.dataset.key,el);break;
    case 'cfg-cancel':cfgEdit(null,el);break;
    case 'cfg-reset':cfgReset(el.dataset.key,el);break;
    case 'logout':doLogout();break;
    case 'ann-new':showAnnounceModal();break;
    case 'ann-create':createAnnouncement(el);break;
    case 'ann-del':delAnnouncement(parseInt(el.dataset.id),el.dataset.title);break;
    case 'ann-all':annToggleAll(el);break;
    case 'snav-fold':toggleSnavFold(el.dataset.group);break;
    case 'snav-fold-toggle':toggleSnavFolded();break;
    case 'snav-toggle':setSidebar(!document.getElementById('sidebar').classList.contains('open'));break;
    case 'snav-close':setSidebar(false);break;
    case 'set-cat':setSelect(el.dataset.cat);break;
    case 'set-enter':enterSettings();break;
    case 'set-home':exitSettings();break;
    case 'go-account':switchTab('account');break;
  }
});

/* ================= 侧边栏 ================= */
/* 可展开分组的「组 key → 子菜单容器 id」。分组本身不建新分页键：二级项复用的就是
   本组一级项的分页键（用户下设用户组/账号/激活码/注册申请，日志下设两种视图与统计） */
var SNAV_FOLDS={'users':'snav-sub-users','logs':'snav-sub-logs'};
/* 面包屑：分页 → 取词键。分组归属在 paintCrumbs 里判定，不额外维护一份表 */
var CRUMBS={overview:'nav.overview',plugins:'nav.plugins',users:'nav.users',test:'nav.test',
  logs:'nav.logs',cache:'nav.cache',prerender:'nav.prerender',stats:'nav.stats',
  config:'nav.config',backup:'nav.backup',account:'nav.account'};
/* 「用户」下面的五个子视图 → 取词键。键要写成完整的字面量：静态扫描（test_i18n）
   靠它核对键是否存在，拼字符串拼出来的键扫不到 */
var USER_SUB_CRUMBS={groups:'user.groups',accounts:'user.accounts',codes:'user.codes',apps:'user.apps',announce:'announce.nav'};
function setSnavFold(group,open){
  var box=document.getElementById(SNAV_FOLDS[group]||'');
  if(!box)return;
  box.hidden=!open;
  var arrow=document.querySelector('.snav-arrow[data-group="'+group+'"]');
  if(arrow)arrow.setAttribute('aria-expanded',open?'true':'false');
}
function toggleSnavFold(group){
  var box=document.getElementById(SNAV_FOLDS[group]||'');
  if(box)setSnavFold(group,box.hidden);
}
/* 窄屏抽屉：侧边栏 + 遮罩一起开合，按钮同步 aria-expanded */
function setSidebar(open){
  var sb=document.getElementById('sidebar'),mk=document.getElementById('snav-mask'),
      bt=document.querySelector('.snav-toggle');
  if(sb)sb.classList.toggle('open',open);
  if(mk)mk.classList.toggle('open',open);
  if(bt)bt.setAttribute('aria-expanded',open?'true':'false');
}
/* 折叠成窄图标条：只作用于宽屏（窄屏侧栏是抽屉，由 CSS 兜住），状态记在 localStorage */
var SNAV_FOLD_KEY='ink_snav_folded';
function isSnavFolded(){
  var sh=document.querySelector('.shell');
  return !!(sh&&sh.classList.contains('folded'));
}
function setSnavFolded(fold){
  var sh=document.querySelector('.shell');
  if(!sh)return;
  fold=!!fold;
  sh.classList.toggle('folded',fold);
  try{localStorage.setItem(SNAV_FOLD_KEY,fold?'1':'0')}catch(e){}
  var bt=document.querySelector('[data-act="snav-fold-toggle"]');
  if(bt){
    bt.setAttribute('aria-expanded',fold?'false':'true');
    var lb=fold?T('nav.expand_sidebar','展开侧边栏'):T('nav.collapse','收起侧边栏');
    bt.setAttribute('aria-label',lb);
    /* 提示文案跟着状态走：折叠态写着「收起侧边栏」会把人指反 */
    bt.setAttribute('title',lb);
  }
  syncNavTitles();
}
function toggleSnavFolded(){setSnavFolded(!isSnavFolded())}
/* 折叠后菜单文字是 display:none，鼠标停在图标上认不出是什么；把文字挂到原生 title 上补回提示。
   展开态移除——文字已经写在旁边，再叠一个 tooltip 只会碍事 */
function syncNavTitles(){
  var folded=isSnavFolded();
  document.querySelectorAll('.snav .tab,.set-item').forEach(function(el){
    var lb=el.querySelector('.lbl');
    if(folded&&lb)el.title=lb.textContent.trim();else el.removeAttribute('title');
  });
}

/* 设置模式：整条侧栏换成设置分类菜单，右侧只剩配置项。侧栏与右侧是一对一的，
   进入/退出必须两边一起切，只换一边就会出现「左边列着 A、右边显示 B」 */
var _setMode=false;
function _paintSetMode(on){
  document.getElementById('snav').hidden=on;
  document.getElementById('snav-set').hidden=!on;
  var back=document.querySelector('.snav-back');
  if(back)back.hidden=!on;
  /* 无 config 权限的用户本来就没有设置入口，退出设置时不能把它露出来 */
  var st=document.getElementById('nav-set-btn');
  if(st)st.hidden=on||!tabAllowed('config');
  var hm=document.getElementById('nav-home-btn');
  if(hm)hm.hidden=!on;
  syncNavTitles();
}
function enterSettings(){
  switchTab('config');
  _setMode=true;
  _paintSetMode(true);
}
function exitSettings(){
  if(!_setMode)return;
  _setMode=false;
  _paintSetMode(false);
  switchTab(_lastMainTab||'overview');
}
function paintCrumbs(name){
  var el=document.getElementById('crumbs');
  if(!el)return;
  var parts;
  if(_setMode){
    /* 设置模式右侧是「设置 / 分类」，与侧栏那份分类菜单同一层级。
       分类名要等配置数据回来才知道，setSelect 里会再刷一次 */
    parts=[T('nav.config','设置'),(_setCat&&_cfg)?_setCatName(_setCat,_cfg):''];
    parts=parts.filter(function(x){return x});
  }else if(name==='users'){
    /* 二级视图在前面补一段分组名（用户组 / 账号 / 激活码 / 注册申请），与侧边栏层级一致 */
    parts=[T('nav.users','用户'),_userSub?T(USER_SUB_CRUMBS[_userSub]||'user.groups',''):''];
    parts=parts.filter(function(x){return x});
  }else if(name==='logs'||name==='stats'){
    parts=[T('nav.logs','日志'),T(CRUMBS[name],name)];
  }else{
    parts=[T(CRUMBS[name]||name,name)];
  }
  el.innerHTML=parts.map(function(x,i){
    return (i?'<span class="sep">/</span>':'')+'<span'+(i===parts.length-1?' class="cur"':'')+'>'+esc(x)+'</span>';
  }).join('');
}

/* ================= 标签切换 ================= */
var _activeTab='overview',_activeSub='',_lastMainTab='overview';
function switchTab(name,sub){
  /* 设置模式下点任何别的分页（如头像 → 我的）都要先把侧栏切回主菜单 */
  if(_setMode&&name!=='config'){_setMode=false;_paintSetMode(false)}
  _activeTab=name;_activeSub=sub||'';
  /* 记下最后一个「主页」分页，退出设置时回到它（config 自己不算） */
  if(name!=='config')_lastMainTab=name;
  /* 折叠成图标条时右侧的二级项根本看不见：先把侧栏展回完整宽度，再谈展开分组 */
  if(SNAV_FOLDS[name]&&isSnavFolded())setSnavFolded(false);
  /* 契约：data-page ↔ id="page-"+name。带 data-sub 的二级项只在子视图也匹配时点亮；
     分组标题（无 data-sub）在本组任一子视图下都保持点亮 */
  document.querySelectorAll('.tab').forEach(function(t){
    t.classList.toggle('on',t.dataset.page===name&&(!t.dataset.sub||t.dataset.sub===_activeSub));
  });
  document.querySelectorAll('.page').forEach(function(p){p.classList.toggle('on',p.id==='page-'+name)});
  // 切到二级菜单里的页面时自动展开所在分组，否则选中的项藏在收起的分组里看不见
  var cur=document.querySelector('.tab.on');
  if(cur){
    var box=cur.closest('.snav-sub');
    if(box&&box.hidden&&box.dataset.group)setSnavFold(box.dataset.group,true);
  }
  paintCrumbs(name);
  setSidebar(false);
  // 切页时清掉未完成的配置编辑态；页内重新渲染（cfgEdit → _cfgReloadMap）绝不能清，否则编辑框永远出不来
  _cfgEdit=null;
  if(name==='overview')refreshOverview();
  else if(name==='plugins')refreshPlugins();
  else if(name==='users')switchUserSubTab(sub||_userSub||'groups');
  else if(name==='test'){syncTestMode();refreshApiDocs()}
  else if(name==='logs'){if(sub)switchLogSubTab(sub);else refreshLogView()}
  else if(name==='cache')refreshCache();
  else if(name==='prerender')refreshPrerender();
  else if(name==='stats')refreshStats();
  else if(name==='account')refreshAccount();
  else if(name==='backup')refreshBackup();
  else if(name==='config')refreshConfig();
}

/* ================= 配置项（统一渲染，见 admin_js_config） ================= */
var _cfg=null,_cfgEdit=null,_cfgCache=null,_cfgCacheTime=0;
/* 每个配置区块按容器 id 各存一个「重载自身」的函数。快速切标签页时，
   先发起的区块请求可能晚于后发起的返回，用单个全局指针会停在旧区块，
   之后保存就刷新不到当前编辑的区块 */
var _cfgReloadMap={};
function fetchCfg(force){
  var now=Date.now();
  if(!force&&_cfgCache&&now-_cfgCacheTime<30000)return Promise.resolve(_cfgCache);
  return R.get('/admin/api/config').then(function(d){_cfgCache=d;_cfgCacheTime=Date.now();return d});
}
/* 配置值 → 布尔。库里统一存字符串，前端存的是 JSON（'true'/'false'），
   手写的可能是 Python 字面量（'True'/'False'）或 0/1，都要认 */
function _cfgBool(v){
  if(typeof v==='boolean')return v;
  var s=String(v===null||v===undefined?'':v).trim().toLowerCase();
  return s==='true'||s==='1'||s==='yes'||s==='on';
}
/* 值该用什么控件编辑：按**代码默认值**的类型判定，不能按当前值——覆盖值在库里统一是
   字符串（'False'、'["webp"]'），拿它判类型会把布尔项和列表项都当成普通文本。

   取值集合固定的项由 CONFIG_LABELS 的 `options` 声明（如输出格式、TIFF 压缩方式）：
   默认值是数组 → 多选复框，否则 → 单选下拉。手打这两种值没有意义，只会拼错。 */
function _cfgKind(k){
  var d=(_cfg&&_cfg.defaults||{})[k];
  var opts=((_cfg&&_cfg.labels||{})[k]||{}).options;
  if(Array.isArray(opts)&&opts.length)return Array.isArray(d)?'multi':'enum';
  if(typeof d==='boolean')return 'bool';
  if(Array.isArray(d))return 'list';
  return 'text';
}
function cfgTableHtml(keys){
  var ov=_cfg.overrides||{},defs=_cfg.defaults||{},labels=_cfg.labels||{};
  var h='<table><thead><tr><th style="width:34%">'+T('core.col_param','参数')+'</th><th>'+T('core.col_current','当前值')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  if(!keys.length)h+='<tr><td colspan="3" class="empty">'+T('core.no_config_items','无配置项')+'</td></tr>';
  keys.forEach(function(k){
    var lb=labels[k]||{};
    var isOv=ov[k]!==undefined;
    var eff=isOv?ov[k]:defs[k];
    var kind=_cfgKind(k);
    var display=typeof eff==='object'?JSON.stringify(eff):String(eff);
    // 多选项把数组摊成顿号分隔：JSON 原文（["webp","tiff"]）在行里读不出实际勾了哪些
    if(kind==='multi')display=(Array.isArray(eff)&&eff.length)?eff.join('、'):T('core.empty_value','（空）');
    /* 只显示可读中文名，完整说明挂在悬停提示上；变量名（DEFAULT_ROTATE 这类）不展示 */
    h+='<tr><td><div class="cfg-name" title="'+esc(lb.desc||'')+'">'+esc(lb.label||k)+'</div></td>';
    if(kind==='bool'){
      // 布尔项直接用开关：点一下即存，不再需要「编辑 → 输入 true/false → 保存」三步
      var on=_cfgBool(eff);
      h+='<td><span class="sw'+(on?' on':'')+'" data-act="cfg-toggle" data-key="'+esc(k)+'" data-val="'+(on?'0':'1')+'"><span class="sw-track"></span>'+(on?T('core.on','开启'):T('core.off','关闭'))+'</span></td>';
      h+='<td><div class="flex">'+(isOv?'<button class="btn btn-sm btn-danger" data-act="cfg-reset" data-key="'+esc(k)+'">'+T('core.reset','还原')+'</button>':'')+'</div></td>';
    }else if(kind==='enum'){
      // 取值集合固定：下拉选一个，选完即存（与布尔开关同样是"点一下即生效"）
      // select 绝不能挂 data-act：全局 click 委托会把「点开下拉」那一下当成已选完，
      // 当场提交并重绘区块 → 下拉被销毁，用户根本来不及选。提交只认 change 事件
      h+='<td><select class="input mono cfg-val" data-key="'+esc(k)+'" onchange="cfgSelect(this.dataset.key,this)">'+
        lb.options.map(function(o){
          var v=String(o);
          return '<option value="'+esc(v)+'"'+(String(eff)===v?' selected':'')+'>'+esc(v)+'</option>';
        }).join('')+'</select></td>';
      h+='<td><div class="flex">'+(isOv?'<button class="btn btn-sm btn-danger" data-act="cfg-reset" data-key="'+esc(k)+'">'+T('core.reset','还原')+'</button>':'')+'</div></td>';
    }else if(_cfgEdit===k){
      h+='<td><input class="input mono" id="cfg-input" value="'+esc(display)+'" style="width:100%"></td>';
      h+='<td><div class="flex"><button class="btn btn-primary btn-sm" data-act="cfg-save" data-key="'+esc(k)+'">'+T('btn.save','保存')+'</button><button class="btn btn-sm" data-act="cfg-cancel">'+T('btn.cancel','取消')+'</button></div></td>';
    }else{
      h+='<td class="mono cfg-val">'+esc(display)+'</td>';
      // 列表 / 对象类配置（白名单、黑名单等）挤在单行输入框里没法看：
      // 取值集合固定的用复选弹窗，其余用 JSON 弹窗
      var act=kind==='multi'?'cfg-multi':(kind==='list'?'cfg-json':'cfg-edit');
      h+='<td><div class="flex"><button class="btn btn-sm" data-act="'+act+'" data-key="'+esc(k)+'">'+T('core.edit','编辑')+'</button>'+
        (isOv?'<button class="btn btn-sm btn-danger" data-act="cfg-reset" data-key="'+esc(k)+'">'+T('core.reset','还原')+'</button>':'')+'</div></td>';
    }
    h+='</tr>';
  });
  return h+'</tbody></table>';
}
function bindCfgInput(){
  var inp=document.getElementById('cfg-input');
  if(inp){
    inp.focus();
    inp.addEventListener('keydown',function(e){
      if(e.key==='Enter')cfgSave(_cfgEdit);
      if(e.key==='Escape')cfgEdit(null);
    });
  }
}
/* 从触发元素定位它所在的配置区块（容器 id 形如 cfg-xxx），再重载该区块 */
function _cfgBoxId(el){var b=el&&el.closest?el.closest('[id^="cfg-"]'):null;return b?b.id:''}
function _cfgReloadId(id){var fn=id?_cfgReloadMap[id]:null;if(fn)fn()}
function cfgEdit(key,el){
  _cfgEdit=key;
  _cfgReloadId(_cfgBoxId(el||document.getElementById('cfg-input')));
}
function cfgSave(key,el){
  var inp=document.getElementById('cfg-input');if(!inp)return;
  var v=inp.value;
  if(!v){toast(T('core.need_value','请输入配置值'),'error');return}
  var ctxId=_cfgBoxId(el||inp);
  R.post('/admin/api/config',{key:key,value:v}).then(function(d){
    // 保存成功后必须先退出编辑态，否则重绘时该行仍是输入框，看不到保存结果
    if(d.success){toast(T('core.saved','{key} 已保存',{key:key}),'success');_cfgEdit=null;_cfgCacheTime=0;_cfgReloadId(ctxId)}
    else toast(d.message||T('core.save_failed','保存失败'),'error');
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function cfgReset(key,el){
  var ctxId=_cfgBoxId(el);
  uiConfirm({title:T('core.reset_title','还原为默认值'),message:T('core.reset_confirm','确定将 {key} 还原为默认值吗？',{key:key}),confirmText:T('core.reset','还原')}).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/config',{key:key,value:null}).then(function(d){
      if(d.success){toast(T('core.reset_done','已还原为默认值'),'success');_cfgCacheTime=0;_cfgReloadId(ctxId)}
      else toast(d.message||T('core.reset_failed','还原失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
/* 布尔项开关：点一下即存（不经过编辑态），存完重载本区块把开关状态刷新成库里的真实值 */
function cfgToggle(key,val,el){
  var v=val==='1',ctxId=_cfgBoxId(el);
  btnBusy(el,true);
  R.post('/admin/api/config',{key:key,value:v}).then(function(d){
    btnBusy(el,false);
    if(d.success){toast(v?T('core.key_on','{key} 已开启',{key:key}):T('core.key_off','{key} 已关闭',{key:key}),'success');_cfgCacheTime=0;_cfgReloadId(ctxId)}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 取值集合固定的单项：下拉选完即存（与布尔开关同为"点一下即生效"，不进编辑态） */
function cfgSelect(key,el){
  var ctxId=_cfgBoxId(el);
  btnBusy(el,true);
  R.post('/admin/api/config',{key:key,value:el.value}).then(function(d){
    btnBusy(el,false);
    if(d.success){toast(T('core.key_updated','{key} 已更新为 {val}',{key:key,val:el.value}),'success');_cfgCacheTime=0;_cfgReloadId(ctxId)}
    else toast(d.message||T('core.save_failed','保存失败'),'error');
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 取值集合固定的多项：复选弹窗。比 JSON 弹窗省掉「记住合法取值 + 手写数组语法」这件事，
   仍按字符串提交（JSON 数组原文），后端照旧走 parse_config_value() */
function cfgEditMulti(key,el){
  var ctxId=_cfgBoxId(el);
  var lb=(_cfg&&_cfg.labels||{})[key]||{},ov=(_cfg&&_cfg.overrides)||{},defs=(_cfg&&_cfg.defaults)||{};
  var eff=ov[key]!==undefined?ov[key]:defs[key];
  var cur={};
  (Array.isArray(eff)?eff:[]).forEach(function(v){cur[String(v)]=1});
  var h='<h3>'+esc(lb.label||key)+'</h3>'+
    (lb.desc?'<p class="dim small modal-sub">'+esc(lb.desc)+'</p>':'')+
    '<label class="mono">'+esc(key)+'</label>'+
    '<div class="ck-row">'+lb.options.map(function(o){
      var v=String(o);
      return '<label><input type="checkbox" value="'+esc(v)+'"'+(cur[v]?' checked':'')+'>'+esc(v)+'</label>';
    }).join('')+'</div>'+
    '<div class="modal-actions"><button class="btn btn-primary" id="cfg-multi-save">'+T('btn.save','保存')+'</button></div>';
  var m=openModal(h,'cfg-multi-modal');
  var save=m.querySelector('#cfg-multi-save');
  save.addEventListener('click',function(){
    var vals=[];
    m.querySelectorAll('.ck-row input:checked').forEach(function(c){vals.push(c.value)});
    btnBusy(save,true);
    R.post('/admin/api/config',{key:key,value:JSON.stringify(vals)}).then(function(d){
      btnBusy(save,false);
      if(d.success){toast(T('core.saved','{key} 已保存',{key:key}),'success');_cfgCacheTime=0;m.remove();_cfgReloadId(ctxId)}
      else toast(d.message||T('core.save_failed','保存失败'),'error');
    }).catch(function(){btnBusy(save,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
/* 列表 / 对象类配置：弹窗里用 textarea 编辑 JSON。白名单、黑名单这类值动辄十来个元素，
   行内单行输入框既看不全也改不动，弹窗能给足空间并做格式校验 */
function cfgEditJson(key,el){
  var ctxId=_cfgBoxId(el);
  var lb=(_cfg&&_cfg.labels||{})[key]||{},ov=(_cfg&&_cfg.overrides)||{},defs=(_cfg&&_cfg.defaults)||{};
  var eff=ov[key]!==undefined?ov[key]:defs[key];
  var text=typeof eff==='object'?JSON.stringify(eff):String(eff);
  var hint=T('core.json_hint','JSON 数组，例如 ["webp","tiff"]；保存后立即生效');
  var h='<h3>'+esc(lb.label||key)+'</h3>'+
    (lb.desc?'<p class="dim small modal-sub">'+esc(lb.desc)+'</p>':'')+
    '<label class="mono">'+esc(key)+'</label>'+
    '<textarea class="input mono" id="cfg-json" rows="6" autocomplete="off" spellcheck="false"'+
    ' style="width:100%;height:auto;min-height:132px;padding:8px 10px;line-height:1.6;resize:vertical">'+esc(text)+'</textarea>'+
    '<p class="dim small" id="cfg-json-hint" style="margin-top:6px">'+esc(hint)+'</p>'+
    '<div class="modal-actions"><button class="btn btn-primary" id="cfg-json-save">'+T('btn.save','保存')+'</button></div>';
  var m=openModal(h,'cfg-json-modal');
  var ta=m.querySelector('#cfg-json'),tip=m.querySelector('#cfg-json-hint');
  ta.focus();
  function fail(msg){tip.textContent=msg;tip.style.color='var(--red)';tip.style.fontWeight='500'}
  ta.addEventListener('input',function(){tip.textContent=hint;tip.style.color='';tip.style.fontWeight=''});
  m.querySelector('#cfg-json-save').addEventListener('click',function(){
    var raw=ta.value.trim();
    if(!raw){fail(T('core.json_required','不能为空；想恢复默认值请用列表里的「还原」'));return}
    try{JSON.parse(raw)}catch(e){fail(T('core.json_invalid','JSON 格式有误：{msg}',{msg:e.message}));return}
    R.post('/admin/api/config',{key:key,value:raw}).then(function(d){
      if(d.success){toast(T('core.saved','{key} 已保存',{key:key}),'success');_cfgCacheTime=0;m.remove();_cfgReloadId(ctxId)}
      else fail(d.message||T('core.save_failed','保存失败'));
    }).catch(function(){fail(T('msg.network_error','网络错误'))});
  });
}
'''