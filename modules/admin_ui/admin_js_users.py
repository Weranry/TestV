# JS 用户页（用户组 / 账号 / 激活码 / 注册申请 / 站内信）
ADMIN_JS_USERS = r'''/* ================= 用户组 ================= */
var _userSub='groups';
function switchUserSubTab(name){
  _userSub=name;
  document.getElementById('user-sub-groups').style.display=name==='groups'?'':'none';
  document.getElementById('user-sub-accounts').style.display=name==='accounts'?'':'none';
  document.getElementById('user-sub-codes').style.display=name==='codes'?'':'none';
  document.getElementById('user-sub-apps').style.display=name==='apps'?'':'none';
  document.getElementById('user-sub-announce').style.display=name==='announce'?'':'none';
  /* 页内那行子标签已删（入口统一在侧栏），点亮由 switchTab 对 .tab[data-sub] 统一处理；
     面包屑要跟着子视图走，所以这里刷一次 */
  paintCrumbs('users');
  if(name==='groups')refreshGroups();
  else if(name==='accounts')refreshAccounts();
  else if(name==='codes')refreshCodes();
  else if(name==='apps')refreshApplications();
  else if(name==='announce')refreshAnnouncements();
}
var _groupList=[],_PER_PAGE=20,_registerDefaultId=0;
/* _intVal / evkeyLimitText / _periodLabel / quotaText 定义在共享层（shared_ui.py），
   用户控制台与「我的」页用的是同一套取值口径 */
/* 用户组类别：admin = 管理组（能进后台，分页按勾选开放），user = 普通用户组（只有个人控制台）。
   组名（admin / Free）只是显示名，类别才是权限依据 */
/* 分页清单只留名字：顶层常量不能调 T()（此时 #i18n-data 与共享脚本还没执行），
   展示文案一律走 _tabLabel 取词 */
var _ADMIN_TABS=[['overview'],['plugins'],['users'],['test'],['logs'],
  ['cache'],['prerender'],['stats'],['config'],['backup']];
/* 分页名 → 文案：与导航栏同源（nav.*），两边不会各写一套名字 */
function _tabLabel(name){
  if(name==='overview')return T('nav.overview','概览');
  if(name==='plugins')return T('nav.plugins','插件');
  if(name==='users')return T('nav.users','用户');
  if(name==='test')return T('nav.test','测试');
  if(name==='logs')return T('nav.logs','日志');
  if(name==='cache')return T('nav.cache','缓存');
  if(name==='prerender')return T('nav.prerender','定时');
  if(name==='stats')return T('nav.stats','统计');
  if(name==='config')return T('nav.config','设置');
  if(name==='backup')return T('nav.backup','备份');
  return name;
}
function _tabSetCsv(){
  var csv=[];
  document.querySelectorAll('#gtabs-wrap .gtab:checked').forEach(function(c){csv.push(c.value)});
  return csv.join(',');
}
/* 内置管理组的分页存在库里是空的（读的时候恒为「全部」），展示要按「全部」说 */
function groupTabsText(g){
  if(g.builtin&&g.category==='admin')return T('user.all_tabs','全部');
  var set={};String(g.admin_tabs||'').split(',').forEach(function(t){if(t)set[t]=1});
  return _ADMIN_TABS.filter(function(t){return set[t[0]]}).map(function(t){return _tabLabel(t[0])}).join('、');
}
/* 类别列只留圆点：紫点 = 管理组、灰点 = 普通用户组。含义在卡片头「类别」图例那一行 */
function groupCategoryBadge(g){
  if(g.category!=='admin')return dotHtml('dot-user',T('user.user_tip','普通用户组：登录后只有个人控制台'));
  var labs=groupTabsText(g);
  return dotHtml('dot-admin',T('user.admin_group_tabs_tip','管理组 · 可访问分页：{tabs}',{tabs:labs||T('user.only_account','仅「我的」')}));
}
/* 列表搜索关键字：模块级变量 + 独立的重绘函数。刷新数据（1 秒 tick 自动刷新）不重置
   关键字，否则用户刚输入的条件会被冲掉；只有搜索框内容变化时才回到第 1 页 */
var _grpQuery='';
/* 组名是否已被别的组占用（编辑自己时排除自己）。判定口径与库里的 UNIQUE(name) 对齐：
   只忽略首尾空白，不做大小写折叠——前端比后端严格的话，会出现「界面说重名、后端却放行」
   或者反过来「界面放行、后端报错」的错位。 */
function _isGroupNameTaken(name,selfId){
  var key=String(name||'').trim();
  return _groupList.some(function(g){
    return g.id!==selfId && String(g.name||'').trim()===key;
  });
}
function grpSearch(){
  var el=document.getElementById('grp-search');
  _grpQuery=el?el.value.trim().toLowerCase():'';
  _pg['groups']=1;
  renderGroups();
}
function renderGroups(){
  var list=_groupList.filter(function(g){return matchQuery(_grpQuery,[g.name,g.id])});
  var pg=pgSlice(list,'groups',_PER_PAGE);
  var h='<table><thead><tr><th class="num">ID</th><th>'+T('user.col_name','名称')+'</th><th class="col-dot">'+T('user.legend_mark','标记')+'</th><th class="num">'+T('user.col_max_evkeys','EVkey 上限')+'</th><th class="num">'+T('user.col_max_concurrent','最大并发')+'</th><th class="num">'+T('user.col_rate','每分钟速率')+'</th><th class="num">'+T('user.col_quota','请求配额')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(g){
    var isDefault=g.id===_registerDefaultId,isAdmin=g.category==='admin';
    // 内置管理组拥有全部权限，整组锁定：编辑与权限配置都禁用（后端同样会拒）
    var locked=isAdmin&&!!g.builtin;
    // 组标记与类别都是「一眼看属性」的圆点，合到同一列（表头「标记」）：
    // 金 = 内置兜底组、绿 = 默认注册组、紫 = 管理组、灰 = 普通用户组，悬停看说明
    var marks=(g.builtin?dotHtml('dot-in',locked?T('user.builtin_admin_tip','内置管理组：拥有全部权限，不可编辑、不可删除'):T('user.builtin_user_tip','内置兜底用户组：不可删除，类别与可访问分页不可改')):'')
      +(isDefault?dotHtml('dot-def',T('user.default_tip','默认注册组：不带激活码注册即进入该组')):'');
    h+='<tr><td class="dim num">'+g.id+'</td><td class="strong">'+esc(g.name)+'</td>'+
      '<td class="col-dot"><span class="dot-cell">'+marks+groupCategoryBadge(g)+'</span></td>'+
      // 管理组的两项限额在服务端被折算成「不限」，表格照库里的值显示就成了假信息
      '<td class="num">'+esc(isAdmin?T('user.unlimited','不限'):evkeyLimitText(g.max_evkeys))+'</td>'+
      '<td class="num">'+(isAdmin?T('user.unlimited','不限'):((g.max_concurrent_renders||0)||T('user.unlimited','不限')))+'</td>';
    h+='<td class="num">'+((g.rate_limit_per_minute||0)||T('user.unlimited','不限'))+'</td><td class="num">'+esc(quotaText(g))+'</td>';
    // 删除按钮保留但禁用：内置组与「还有激活码开通的未到期账号」的组都删不得，
    // 后端也会拒；禁用而不是隐藏，各行格子数才一致、按钮不参差不齐
    var blocked=g.builtin?T('user.builtin_del_blocked','内置用户组不可删除')
      :(_intVal(g.unexpired_count,0)>0?T('user.group_del_blocked','该组下还有 {n} 个激活码开通的未到期账号，暂不可删除',{n:g.unexpired_count}):'');
    h+='<td><div class="acts"><button class="btn btn-sm" data-act="group-perms" data-id="'+g.id+'" data-name="'+esc(g.name)+'"'+
      (locked?' disabled title="'+T('user.builtin_admin_no_perm','内置管理组拥有全部权限，无需配置')+'"':'')+'>'+T('user.btn_perms','权限')+'</button>'+
      // 管理组不能生成激活码（后端也拒），按钮同样禁用而不是隐藏，各行格子数才一致
      '<button class="btn btn-sm" data-act="group-codes" data-id="'+g.id+'"'+
      (isAdmin?' disabled title="'+T('user.admin_no_code','管理组不能生成激活码')+'"':'')+'>'+T('user.codes','激活码')+'</button>'+
      '<button class="btn btn-sm" data-act="group-edit" data-id="'+g.id+'"'+
      (locked?' disabled title="'+T('user.builtin_admin_no_edit','内置管理组拥有全部权限，不可编辑')+'"':'')+'>'+T('core.edit','编辑')+'</button>'+
      // 「默认组」是三个字、「设为默认」是四个字：不锁宽度两个按钮对不齐，
      // 所以两种状态都用同一个 min-width
      (isAdmin
        ? '<button class="btn btn-sm" style="min-width:76px;justify-content:center" disabled title="'+T('user.admin_no_default','管理组不能设为默认注册组')+'">'+T('user.set_default','设为默认')+'</button>'
        : (isDefault
          ? '<button class="btn btn-sm" style="min-width:76px;justify-content:center" disabled title="'+T('user.already_default','当前已是默认注册组')+'">'+T('user.default_group_btn','默认组')+'</button>'
          : '<button class="btn btn-sm" style="min-width:76px;justify-content:center" data-act="group-default" data-id="'+g.id+'" data-name="'+esc(g.name)+'">'+T('user.set_default','设为默认')+'</button>'))+
      '<span class="sep"></span>'+
      '<button class="btn btn-sm btn-danger" data-act="group-del" data-id="'+g.id+'" data-name="'+esc(g.name)+'"'+
      (blocked?' disabled title="'+esc(blocked)+'"':'')+'>'+T('btn.delete','删除')+'</button>'+
      '</div></td></tr>';
  });
  // 搜不到与本来就没有要分开说：否则加了搜索框会让人以为用户组全没了
  if(!pg.rows.length)h+='<tr><td colspan="8" class="empty">'+(_grpQuery?T('user.no_match_groups','没有匹配的用户组'):T('user.no_groups','暂无用户组'))+'</td></tr>';
  document.getElementById('groups-area').innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender['groups']=renderGroups;
}
function refreshGroups(){
  R.get('/admin/api/groups').then(function(d){
    _groupList=d.groups||[];
    _registerDefaultId=_intVal(d.register_default_id,0);
    renderGroups();
  });
}
/* 默认注册组：写进全局配置 REGISTER_DEFAULT_GROUP_ID（0 = 内置 Free 组）。
   配的组事后被删除时，注册会自动回落到 Free，不会报外键错误 */
function setDefaultGroup(id,name){
  R.post('/admin/api/config',{key:'REGISTER_DEFAULT_GROUP_ID',value:String(id)}).then(function(d){
    if(d.success===false){toast(d.message||T('user.set_failed','设置失败'),'error');return}
    toast(T('user.default_set','已将「{name}」设为默认注册组',{name:name}),'success');
    refreshGroups();
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function syncGroupTabs(){
  var sel=document.getElementById('gcat'),wrap=document.getElementById('gtabs-wrap');
  var isAdmin=!!sel&&sel.value==='admin';
  if(sel&&wrap)wrap.style.display=isAdmin?'':'none';
  /* 管理组的 evkey 上限与并发上限在服务端被折算成「不限」（group_max_evkeys /
     app_core 的信号量），面板就不能把它们留成可改项：填了也不生效，切回用户组时
     又会被当成一份真配置。禁用而不是隐藏，表单的行距与其它项保持一致。
     框里显示的是生效值（evkey -1 / 并发 0）而不是库里的数：表格列与「我的」页都报
     「不限」，这里再摆一个 3 就成了自相矛盾。库里那份留在 data-orig，改回用户组时
     还原，保存时也照它写回，展示用的占位值不会被存进库 */
  [['gmax',-1],['gconc',0]].forEach(function(p){
    var el=document.getElementById(p[0]);
    if(!el)return;
    el.disabled=isAdmin;
    if(isAdmin)el.value=p[1];
    else if(el.dataset.orig!==undefined)el.value=el.dataset.orig;
  });
  var note=document.getElementById('glim-note');
  if(note)note.style.display=isAdmin?'':'none';
}
function showGroupModal(id){
  var g=id?_groupList.find(function(x){return x.id===id}):{};
  var period=(g.quota_period||'day');
  var isAdmin=g.category==='admin';
  /* 内置管理组的分页恒为「全部」（库层也不接受改写），展示时全勾上并禁用 */
  var tabCsv=(g.builtin&&isAdmin)?_ADMIN_TABS.map(function(t){return t[0]}).join(','):(g.admin_tabs||'');
  var tabSet={};String(tabCsv).split(',').forEach(function(t){if(t)tabSet[t]=1});
  var tabChecks=_ADMIN_TABS.map(function(t){
    /* 复选框与文字的间距由 .ck-list>label 统一给（见 admin_shell 的注释），
       这里不写内联 gap——写成 <label class="flex"> 会被 .modal label{display:block} 压掉 */
    return '<label><input type="checkbox" class="gtab" value="'+t[0]+'"'+(tabSet[t[0]]?' checked':'')+
      (g.builtin?' disabled':'')+'>'+_tabLabel(t[0])+'</label>';
  }).join('');
  var ov=openModal(
    '<h3>'+(id?T('user.edit_group','编辑用户组'):T('user.new_group_title','新增用户组'))+'</h3>'+
    (g.builtin?'<p class="dim small modal-sub">'+T('user.builtin_group_note','内置兜底用户组：名称与限额可改，类别与分页固定不可改，也不可删除')+'</p>':'')+
    '<label>'+T('user.col_name','名称')+'</label><input class="input" id="gname" value="'+esc(g.name||'')+'">'+
    '<label>'+T('user.category_label','类别（管理组可进后台、可用激活码生效；用户组只有个人控制台）')+'</label>'+
    '<select class="input" id="gcat" onchange="syncGroupTabs()"'+(g.builtin?' disabled':'')+'>'+
      '<option value="user"'+(isAdmin?'':' selected')+'>'+T('user.user_group','普通用户组')+'</option>'+
      '<option value="admin"'+(isAdmin?' selected':'')+'>'+T('user.admin_group','管理组')+'</option>'+
    '</select>'+
    '<div id="gtabs-wrap" style="display:'+(isAdmin?'':'none')+'">'+
      '<label>'+T('user.tabs_label','可访问的后台分页（「我的」始终可用）')+'</label>'+
      '<div class="ck-list cols">'+tabChecks+'</div>'+
      /* 分页之外的单卡片开关：可见概览页但不想看/发站内信的管理组可以单独关掉它 */
      '<div class="ck-list">'+
        '<label><input type="checkbox" id="gann"'+(g.builtin||_intVal(g.show_announcement,1)?' checked':'')+
        (g.builtin?' disabled':'')+'>'+T('user.show_announce','显示概览页的站内信卡片')+'</label></div></div>'+
    '<label>'+T('user.max_evkeys_label','EVkey 上限（-1 = 不限，0 = 禁止创建，N = 最多 N 个）')+'</label><input class="input" type="number" id="gmax" data-orig="'+_intVal(g.max_evkeys,3)+'" value="'+_intVal(g.max_evkeys,3)+'" min="-1"'+(isAdmin?' disabled':'')+'>'+
    '<label>'+T('user.max_concurrent_label','最大并发渲染（0 = 不限，按账号独立计数，优先级高于全局配置）')+'</label><input class="input" type="number" id="gconc" data-orig="'+(g.max_concurrent_renders||0)+'" value="'+(g.max_concurrent_renders||0)+'" min="0"'+(isAdmin?' disabled':'')+'>'+
    '<div class="dim small" id="glim-note" style="display:'+(isAdmin?'':'none')+';margin-top:8px">'+T('user.admin_limit_note','管理组不受 EVkey 数量与并发数量限制，这两项始终按「不限」执行。')+'</div>'+
    '<label>'+T('user.rate_label','每分钟请求速率（0 = 不限，按账号独立计数）')+'</label><input class="input" type="number" id="gmr" value="'+(g.rate_limit_per_minute||0)+'" min="0">'+
    '<label>'+T('user.quota_label','请求配额上限（0 = 不限，按账号独立计数，同账号下所有 EVkey 共用）')+'</label><input class="input" type="number" id="gquota" value="'+_intVal(g.quota_limit,0)+'" min="0">'+
    '<label>'+T('user.quota_period_label','配额模式')+'</label><select class="input" id="gperiod">'+
      '<optgroup label="'+T('user.period_group','按时间周期（到期自动重置）')+'">'+
        _QUOTA_UNITS.map(function(p){return '<option value="'+p[0]+'"'+(period===p[0]?' selected':'')+'>'+T(p[1],p[2])+'</option>'}).join('')+
      '</optgroup>'+
      '<optgroup label="'+T('user.trial_group','按次总量（该账号一共就这么多，用完即止）')+'">'+
        '<option value="trial"'+(period==='trial'?' selected':'')+'>'+T('user.period_trial','总量（永不重置）')+'</option>'+
      '</optgroup>'+
    '</select>'+
    '<div class="modal-actions"><button class="btn btn-primary" data-act="group-save" data-id="'+(id||0)+'">'+T('btn.save','保存')+'</button></div>',
    'group-modal');
  /* 渲染时把限额框刷成生效值（管理组显示「不限」而不是库里那份数），口径与 syncGroupTabs 同源 */
  syncGroupTabs();
  modalForm(ov,function(){saveGroup(id,ov.querySelector('[data-act="group-save"]'))});
}
function saveGroup(id,btn){
  var n=document.getElementById('gname').value.trim();
  var gmr=_intVal(document.getElementById('gmr').value,0);
  var gquota=_intVal(document.getElementById('gquota').value,0);
  var gperiod=document.getElementById('gperiod').value;
  var gcat=(document.getElementById('gcat')||{}).value||'user';
  /* 管理组看到的这两项是「不限」的占位值（-1 / 0），不代表组配置：写回库里原本那份，
     否则每次编辑管理组都会把配置悄悄改写成 -1/0，将来改成用户组就变成真·不限了 */
  var maxv=_intVal(gcat==='admin'?document.getElementById('gmax').dataset.orig:document.getElementById('gmax').value,3);
  var gconc=_intVal(gcat==='admin'?document.getElementById('gconc').dataset.orig:document.getElementById('gconc').value,0);
  if(!n){toast(T('user.need_group_name','请输入用户组名称'),'error');return}
  /* 名称在库里是唯一的（后端也会拒），这里先按已加载的列表拦一道：
     重名是高频的输入失误，当场提示比等一个来回更直接。后端那道是最终关口，不重复删 */
  if(_isGroupNameTaken(n,id)){toast(T('msg.group_name_taken','已存在名为「{name}」的用户组，请换一个名称',{name:n}),'error');return}
  if(gcat==='admin'&&!_tabSetCsv()){toast(T('user.need_admin_tab','管理组至少要勾选一个后台分页'),'error');return}
  var body={name:n,max_evkeys:maxv,max_concurrent_renders:gconc,
    rate_limit_per_minute:gmr,quota_limit:gquota,quota_period:gperiod,
    category:gcat,admin_tabs:gcat==='admin'?_tabSetCsv():'',
    /* 站内信开关只对管理组有意义；用户组一律写 1，避免从管理组改成用户组时把 0 留在库里 */
    show_announcement:gcat==='admin'?((document.getElementById('gann')||{}).checked?1:0):1};
  btnBusy(btn,true);
  var p=id?R.put('/admin/api/groups/'+id,body):R.post('/admin/api/groups',body);
  p.then(function(d){
    btnBusy(btn,false);
    if(d.success===false)toast(d.message||T('core.op_failed','操作失败'),'error');
    else{
      toast(id?T('user.group_updated','用户组「{name}」已更新',{name:n}):T('user.group_created','用户组「{name}」已创建',{name:n}),'success');
      refreshGroups();var m=document.getElementById('group-modal');if(m)m.remove();
    }
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function delGroup(id,name){
  var g=_groupList.find(function(x){return x.id===id})||{};
  var cnt=g.account_count||0;
  var label=esc(name||String(id));
  var h='<h3>'+T('user.del_group_title','删除用户组')+'</h3>';
  h+='<p class="dim small modal-sub">'+T('user.del_group_confirm','「{name}」的权限配置与参数限制会一并删除，且不可恢复。',{name:label})+'</p>';
  if(cnt>0){
    h+='<div class="panel" style="margin-bottom:16px">'+T('user.del_group_has_accounts','该用户组下还有 <b>{n}</b> 个账号（含名下全部 EVkey）。',{n:cnt})+'</div>';
    h+='<label>'+T('user.acct_handling','账号处理方式')+'</label>';
    h+='<div class="ck-list">'+
      '<label><input type="radio" name="dg-mode" value="transfer" checked>'+T('user.transfer_to','转移到其他用户组')+'</label>'+
      '<label><input type="radio" name="dg-mode" value="delete">'+T('user.del_with_accounts','连同账号一起删除')+'</label></div>';
    var others=_groupList.filter(function(x){return x.id!==id&&x.category!=='admin'});
    h+='<label>'+T('user.target_group','目标用户组')+'</label><select class="input" id="dg-target" style="width:100%">'+
      others.map(function(x){return '<option value="'+x.id+'">'+esc(x.name)+'</option>'}).join('')+'</select>';
    if(!others.length)h+='<div class="small err-text" style="margin-top:8px">'+T('user.no_other_group','没有其它用户组可接收，只能连同账号一起删除')+'</div>';
  }
  h+='<label>'+T('user.type_to_confirm','输入 {name} 以确认',{name:'<span class="mono">'+label+'</span>'})+'</label><input class="input" id="dg-text" autocomplete="off" style="width:100%">';
  h+='<div class="modal-actions"><button class="btn" data-act="modal-close">'+T('btn.cancel','取消')+'</button>'+
    '<button class="btn btn-danger-solid" data-act="group-del-confirm" data-id="'+id+'" data-name="'+label+'" disabled>'+T('user.delete_forever','永久删除')+'</button></div>';
  var ov=openModal(h,'group-del-modal');
  var box=ov.querySelector('.modal');box.classList.add('confirm');box.classList.add('danger');
  var yes=ov.querySelector('[data-act="group-del-confirm"]');
  var inp=ov.querySelector('#dg-text');
  var sel=ov.querySelector('#dg-target');
  function transferring(){
    if(!cnt||!sel)return false;
    var r=ov.querySelector('input[name="dg-mode"]:checked');
    return !!r&&r.value==='transfer';
  }
  function sync(){
    var need=name||String(id);
    yes.disabled=inp.value.trim()!==need||(transferring()&&!sel.value);
  }
  ov.querySelectorAll('input[name="dg-mode"]').forEach(function(r){
    r.addEventListener('change',function(){if(sel)sel.disabled=!transferring();sync()});
  });
  inp.addEventListener('input',sync);
  inp.focus();
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'&&!yes.disabled)confirmDelGroup(yes)});
}
function confirmDelGroup(btn){
  var id=parseInt(btn.dataset.id);
  var ov=btn.closest('.modal-overlay');
  var sel=ov.querySelector('#dg-target');
  var r=ov.querySelector('input[name="dg-mode"]:checked');
  var transfer=(sel&&r&&r.value==='transfer')?sel.value:'';
  if(sel&&!sel.value&&!transfer){toast(T('user.no_target_group','没有可接收的用户组'),'error');return}
  btnBusy(btn,true,T('user.deleting','删除中…'));
  R.del('/admin/api/groups/'+id+(transfer?'?transfer_to='+transfer:'')).then(function(d){
    if(d.success===false){btnBusy(btn,false);toast(d.message||T('core.op_failed','操作失败'),'error');return}
    toast(d.transferred?T('user.group_deleted_transferred','用户组已删除，{n} 个账号已转移',{n:d.transferred}):T('user.group_deleted','用户组已删除'),'success');
    ov.remove();
    refreshGroups();refreshAccounts();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* ================= 激活码（跨用户组独立管理） ================= */
/* 激活码属于某个用户组：注册时填写即进入该组，登录后也能在个人控制台自助激活。
   「可激活账号数」「账号有效期天数」都是 0 = 不限，与项目其它限额语义一致。
   有限次的码用尽、过了有效日期的码一律由后端当场销毁，所以列表里只会看到还能用的码。 */
var _codeList=[],_codeFilter=0;
/* 状态列只留圆点（含义见卡片头「状态」图例那一行）：蓝 = 可用，灰 = 已失效。
   过期与用尽的码后端当场销毁，列表里只会看到还能用的码 */
function _codeStatusMap(){
  return {active:[T('user.available','可用'),'dot-on'],disabled:[T('user.inactive','已停用'),'dot-off'],
    expired:[T('user.expired','已过期'),'dot-off'],exhausted:[T('user.exhausted','已用尽'),'dot-off']};
}
function codeStatusBadge(s){
  var hit=_codeStatusMap()[s]||[T('user.unknown','未知'),'dot-off'];
  return dotHtml(hit[1],hit[0]);
}
/* 「重复激活」列本身就是开关：可重复 = 蓝，仅一次 = 灰，点一下即切换。
   列里只留圆点（含义见卡片头「重复激活」图例那一行），语义靠 title 与点击行为承载。
   开关状态由读屏侧的 .sr-only 念出：这个圆点没有键盘入口，读屏至少要知道它当前是哪一态 */
function codeRepeatBadge(c){
  var on=_intVal(c.allow_repeat,0)?1:0;
  var tip=on?T('user.repeat_on_tip','可重复：同一账号可反复激活（点此改为「仅一次」）'):T('user.repeat_off_tip','仅一次：同一账号只能激活一次（点此允许反复激活）');
  return '<i class="dot '+(on?'dot-on':'dot-off')+'" style="cursor:pointer" data-act="code-repeat" '+
    'data-id="'+c.id+'" data-en="'+on+'" title="'+esc(tip)+'" aria-hidden="true"></i>'+
    '<span class="sr-only">'+esc(tip)+'</span>';
}
function codeUsesText(c){
  var lim=_intVal(c.max_uses,0),used=_intVal(c.used_count,0);
  return lim>0?(used+' / '+lim):T('user.uses_unlimited','{n} / 不限',{n:used});
}
function codeDurationText(c){
  var d=_intVal(c.duration_days,0);
  return d>0?T('user.days','{n} 天',{n:d}):T('user.permanent','永久');
}
function codeFallbackText(c){
  var gid=_intVal(c.fallback_group_id,0);
  return gid?groupNameOf(gid):T('user.no_transfer','不转移');
}
function groupNameOf(gid){
  var g=_groupList.find(function(x){return x.id===gid});
  return g?g.name:('#'+gid);
}
/* 用户组行里的「激活码」入口：直接跳到本标签页并预筛该组，不再为每组开一个弹窗 */
function gotoCodes(groupId){
  _codeFilter=_intVal(groupId,0);
  _pg['codes']=1;
  switchUserSubTab('codes');
}
function setCodeFilter(v){
  _codeFilter=_intVal(v,0);
  _pg['codes']=1;
  refreshCodes();
}
function codeFilterHtml(){
  var h='<option value="0">'+T('user.all_groups','全部用户组')+'</option>';
  _groupList.forEach(function(g){
    h+='<option value="'+g.id+'"'+(_codeFilter===g.id?' selected':'')+'>'+esc(g.name)+'</option>';
  });
  return h;
}
/* 组名要给筛选下拉与「到期回落」列用；用户从没进过用户组标签页时 _groupList 还是空的 */
function ensureGroups(){
  if(_groupList.length)return Promise.resolve();
  return R.get('/admin/api/groups').then(function(d){_groupList=(d&&d.groups)||[]});
}
function refreshCodes(){
  ensureGroups().then(function(){
    return R.get('/admin/api/activation-codes'+(_codeFilter?('?group_id='+_codeFilter):''));
  }).then(function(d){
    if(d.success===false){toast(d.message||T('user.load_codes_failed','加载激活码失败'),'error');return}
    _codeList=d.codes||[];
    renderCodes();
  }).catch(function(){toast(T('user.load_codes_failed','加载激活码失败'),'error')});
}
function renderCodes(){
  var sel=document.getElementById('code-group-filter');
  if(sel)sel.innerHTML=codeFilterHtml();
  var pg=pgSlice(_codeList,'codes',_PER_PAGE);
  var h='<table><thead><tr><th>'+T('user.codes','激活码')+'</th><th>'+T('user.target_group','目标用户组')+'</th><th class="num">'+T('user.col_used','已激活')+'</th>'+
    '<th>'+T('user.col_expires','有效日期')+'</th><th>'+T('user.col_duration','账号有效期')+'</th><th>'+T('user.col_fallback','到期回落')+'</th><th>'+T('user.col_note','备注')+'</th><th class="col-dot">'+T('user.legend_repeat','重复激活')+'</th><th class="col-dot">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(c){
    h+='<tr><td class="mono">'+esc(c.code)+'</td>'+
      '<td class="strong">'+esc(c.group_name||('#'+c.group_id))+'</td>'+
      '<td class="num">'+esc(codeUsesText(c))+'</td>'+
      '<td class="dim">'+esc(c.expires_on||T('user.never_expires','永不过期'))+'</td>'+
      '<td class="dim">'+esc(codeDurationText(c))+'</td>'+
      '<td class="dim">'+esc(codeFallbackText(c))+'</td>'+
      '<td class="dim ellip" title="'+esc(c.note||'')+'">'+esc(c.note||'-')+'</td>'+
      '<td class="col-dot">'+codeRepeatBadge(c)+'</td>'+
      '<td class="col-dot">'+codeStatusBadge(c.status)+'</td>'+
      '<td><div class="acts"><button class="btn btn-sm" data-act="copy-text" data-copy="'+esc(c.code)+'">'+T('btn.copy','复制')+'</button>'+
      '<button class="btn btn-sm" data-act="code-toggle" data-id="'+c.id+'" data-en="'+(c.enabled?'1':'0')+'">'+(c.enabled?T('user.disable','停用'):T('user.enabled','启用'))+'</button>'+
      '<span class="sep"></span>'+
      '<button class="btn btn-sm btn-danger" data-act="code-del" data-id="'+c.id+'" data-code="'+esc(c.code)+'">'+T('btn.delete','删除')+'</button></div></td></tr>';
  });
  if(!pg.rows.length)h+='<tr><td colspan="10" class="empty">'+(_codeFilter?T('user.no_codes_group','该用户组暂无激活码'):T('user.no_codes','暂无激活码'))+'</td></tr>';
  document.getElementById('codes-area').innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender['codes']=refreshCodes;
}
/* 时长到期后转入的组不能是激活的目标组本身，也不能是 admin（后端同样会拒） */
function rebuildCodeFallback(){
  var gsel=document.getElementById('c-group'),fsel=document.getElementById('c-fallback');
  if(!gsel||!fsel)return;
  var gid=_intVal(gsel.value,0),keep=_intVal(fsel.value,0);
  var opts='<option value="0">'+T('user.no_transfer_keep','不转移（留在原组）')+'</option>';
  _groupList.forEach(function(g){
    if(g.id===gid||g.category==='admin')return;
    opts+='<option value="'+g.id+'"'+(g.id===keep?' selected':'')+'>'+esc(g.name)+'</option>';
  });
  fsel.innerHTML=opts;
}
function showCodeModal(){
  ensureGroups().then(function(){
    // 管理组不做目标：用管理组的码注册等于当场拿到后台权限，后端也会拒
    var targets=_groupList.filter(function(g){return g.category!=='admin'});
    if(!targets.length){toast(T('user.need_group_first','请先创建一个用户组'),'error');return}
    var opts=targets.map(function(g){
      return '<option value="'+g.id+'"'+(_codeFilter===g.id?' selected':'')+'>'+esc(g.name)+'</option>';
    }).join('');
    var h='<h3>'+T('user.gen_codes_title','生成激活码')+'</h3>'+
      '<p class="dim small modal-sub">'+T('user.code_note','激活码属于某个用户组：用户在注册页填写，或登录后在个人控制台「我的会员」里输入，即可进入该组')+'</p>'+
      '<label>'+T('user.target_group','目标用户组')+'</label><select class="input" id="c-group" onchange="rebuildCodeFallback()">'+opts+'</select>'+
      '<label>'+T('user.uses_label','可激活账号数（0 = 不限；填 N 则第 N 个账号激活后该码立即销毁）')+'</label><input class="input" type="number" min="0" id="c-max" placeholder="0">'+
      '<label>'+T('user.expires_label','激活码有效日期（留空 = 永不过期，过期后自动销毁）')+'</label><input class="input" type="date" id="c-exp">'+
      '<label>'+T('user.duration_label','激活后账号有效期（天，0 = 永久有效）')+'</label><input class="input" type="number" min="0" id="c-days" placeholder="0">'+
      '<label>'+T('user.fallback_label','账号到期后转入')+'</label><select class="input" id="c-fallback"></select>'+
      '<div class="ck-list"><label><input type="checkbox" id="c-repeat">'+T('user.repeat_label','允许同一账号反复激活（续期叠加，每次照常占一个可激活账号名额）')+'</label></div>'+
      '<label>'+T('user.note_label','备注（选填）')+'</label><input class="input" id="c-note" placeholder="'+T('user.note_ph','例如：双十一活动')+'" autocomplete="off">'+
      '<div class="modal-actions"><button class="btn" data-act="modal-close">'+T('btn.cancel','取消')+'</button>'+
      '<button class="btn btn-primary" data-act="code-save">'+T('user.gen','生成')+'</button></div>';
    var ov=openModal(h,'code-modal');
    rebuildCodeFallback();
    modalForm(ov,function(){createCode(ov.querySelector('[data-act="code-save"]'))});
  }).catch(function(){toast(T('user.load_groups_failed','加载用户组失败'),'error')});
}
function createCode(btn){
  var gsel=document.getElementById('c-group');
  var gid=_intVal(gsel?gsel.value:0,0);
  var body={
    group_id:gid,
    max_uses:_intVal((document.getElementById('c-max')||{}).value,0),
    expires_on:((document.getElementById('c-exp')||{}).value||'').trim(),
    duration_days:_intVal((document.getElementById('c-days')||{}).value,0),
    fallback_group_id:_intVal((document.getElementById('c-fallback')||{}).value,0),
    allow_repeat:!!(document.getElementById('c-repeat')||{}).checked,
    note:((document.getElementById('c-note')||{}).value||'').trim()
  };
  if(!gid){toast(T('user.need_target_group','请选择目标用户组'),'error');return}
  var gname=gsel.options[gsel.selectedIndex]?gsel.options[gsel.selectedIndex].text:groupNameOf(gid);
  btnBusy(btn,true,T('user.generating','生成中…'));
  R.post('/admin/api/activation-codes',body).then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('user.gen_failed','生成失败'),'error');return}
    var m=document.getElementById('code-modal');if(m)m.remove();
    showSecret(T('user.code_generated','激活码已生成'),d.code,T('user.code_generated_note','交给用户：注册页填写，或登录后在个人控制台「我的会员」里输入，即可进入「{name}」；仅此一次完整展示。',{name:gname}));
    refreshCodes();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function toggleCode(cid,en,el){
  btnBusy(el,true);
  R.put('/admin/api/activation-codes/'+cid,{enabled:en}).then(function(d){
    btnBusy(el,false);
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    toast(en?T('user.code_enabled','激活码已启用'):T('user.code_disabled','激活码已停用'),'success');
    refreshCodes();
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
function toggleCodeRepeat(cid,on,el){
  // el 是那个 badge（span），没有 btnBusy 的禁用态，用指针态挡重复点击
  if(el){el.style.pointerEvents='none';el.style.opacity='.6'}
  R.put('/admin/api/activation-codes/'+cid,{allow_repeat:on}).then(function(d){
    if(el){el.style.pointerEvents='';el.style.opacity=''}
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    toast(on?T('user.repeat_allowed','已允许同一账号反复激活'):T('user.repeat_limited','已改为同一账号只能激活一次'),'success');
    refreshCodes();
  }).catch(function(){if(el){el.style.pointerEvents='';el.style.opacity=''};toast(T('msg.network_error','网络错误'),'error')});
}
function delCode(cid,code){
  uiConfirm({
    title:T('user.del_code_title','删除激活码'),
    message:T('user.del_code_confirm','删除后该激活码立即作废（已用它激活的账号不受影响），且不可恢复。'),
    confirmText:T('btn.delete','删除'),danger:true,requireText:code||String(cid)
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/activation-codes/'+cid).then(function(d){
      if(d.success===false){toast(d.message||T('announce.del_failed','删除失败'),'error');return}
      toast(T('user.code_deleted','激活码已删除'),'success');
      refreshCodes();
    });
  });
}

var _permCtx=null,_permParams={};
function permParamsHtml(id){
  var h='<div class="flex" style="margin-bottom:8px">';
  var COMMON_PARAMS=[
    {key:'format_bmp',label:'BMP'},{key:'format_png',label:'PNG'},{key:'format_jpg',label:'JPG'},
    {key:'format_webp',label:'WebP'},{key:'format_tiff',label:'TIFF'},{key:'format_gif',label:'GIF'},
    {key:'format_array',label:T('user.p_format_array','Raw数组')},{key:'format_bwrarray',label:T('user.p_format_bwrarray','白黑红数组')},{key:'format_bwyarray',label:T('user.p_format_bwyarray','白黑黄数组')},
    {key:'format_bwryarray',label:T('user.p_format_bwryarray','白黑红黄数组')},{key:'format_7carray',label:T('user.p_format_7carray','七色数组')},
    {key:'rotate',label:T('user.p_rotate','旋转')},{key:'invert',label:T('user.p_invert','反色')},{key:'cmode',label:T('user.p_cmode','色彩模式')}
  ];
  COMMON_PARAMS.forEach(function(cp){
    // 规则值为 false 才是"禁止该参数"，缺规则 = 默认允许（与插件/路由权限同一套语义）
    var off=_permParams[cp.key]===false;
    h+='<span class="tag'+(off?' active':'')+'" data-act="param-quick" data-gid="'+id+'" data-key="'+cp.key+'" data-label="'+cp.label+'" data-off="'+(off?1:0)+'">'+cp.label+'</span>';
  });
  h+='</div>';
  var paramKeys=Object.keys(_permParams).filter(function(k){return _permParams[k]===false});
  if(paramKeys.length===0)h+='<div class="dim small" style="margin-bottom:8px">'+T('user.no_param_limit','当前无生效限制，点击上方标签即可禁止对应参数')+'</div>';
  else{
    h+='<div class="dim small" style="margin-bottom:8px">'+T('user.forbidden_params','当前禁止的参数')+'</div>';
    paramKeys.forEach(function(pk){
      h+='<div class="flex" style="margin-bottom:4px"><span class="strong" style="min-width:120px;font-size:14px">'+esc(pk)+'</span><button class="btn btn-sm btn-danger" data-act="param-del" data-gid="'+id+'" data-key="'+esc(pk)+'">'+T('user.remove_limit','移除限制')+'</button></div>';
    });
  }
  h+='<div class="flex" style="margin-top:8px;border-top:1px solid var(--line);padding-top:16px"><input class="input" id="new-gparam-'+id+'" placeholder="'+T('user.custom_param_ph','自定义参数名')+'" style="width:180px"><button class="btn btn-sm btn-primary" data-act="param-add" data-gid="'+id+'">'+T('user.add_forbid','添加禁止')+'</button></div>';
  return h;
}
function renderPermParams(id){
  var box=document.getElementById('grp-params-'+id);
  if(box)box.innerHTML=permParamsHtml(id);
}
function showGroupPerms(id,name){
  _permCtx={id:id,name:name};
  R.get('/admin/api/groups/'+id+'/permissions').then(function(p){
    R.get('/admin/api/groups/'+id+'/params').then(function(pr){
      R.get('/admin/api/plugins').then(function(pd){
        var pl=pd.plugins||[];var routes=pd.routes||{};
        _permParams=pr.params||{};
        var h='<h3>'+T('user.perms_title','{name} · 权限设置',{name:esc(name)})+'</h3><p class="dim small modal-sub">'+T('user.perms_sub','开关即时生效；未显式配置的项默认允许')+'</p>';
        h+='<div class="sec-title" style="margin-top:8px">'+T('user.perm_plugins_routes','插件与路由')+'</div>';
        pl.forEach(function(x,pi){
          var on=p.plugins[x.name]!==false;
          h+='<div class="flex" style="margin-bottom:8px"><span class="sw'+(on?' on':'')+'" data-act="perm-toggle" data-gid="'+id+'" data-type="plugin" data-name="'+esc(x.name)+'"><span class="sw-track"></span></span><span style="flex:1;font-size:14px">'+esc(x.name)+'</span><span class="small" style="cursor:pointer;color:var(--fg2)" data-act="perm-fold" data-id="'+id+'" data-idx="'+pi+'">'+T('core.routes_collapse','路由 ▾')+'</span></div>';
          var proutes=routes[x.name]||[];
          /* id 用插件在列表中的索引而非插件名：名字可能含空格等字符，直接拼进 id 会产生非法/重复 id */
          h+='<div id="grp-routes-'+id+'-'+pi+'" style="display:none;margin:2px 0 8px 40px;font-size:12px">';
          proutes.forEach(function(rr){
            var ron=p.routes['/'+rr.path]!==false;
            if(ron===undefined)ron=p.routes[rr.path]!==false;
            if(ron===undefined)ron=true;
            h+='<div class="flex" style="margin-bottom:4px"><span class="sw sm'+(ron?' on':'')+'" data-act="perm-toggle" data-gid="'+id+'" data-type="route" data-name="'+esc(rr.path)+'"><span class="sw-track"></span></span><span class="mono dim">'+esc(rr.path)+'</span></div>';
          });
          if(proutes.length===0)h+='<span class="dim">'+T('plugin.no_routes','该插件暂无路由')+'</span>';
          h+='</div>';
        });
        h+='<div class="sec-title" style="border-top:1px solid var(--line);padding-top:16px">'+T('user.param_limit_title','参数限制')+'</div>';
        h+='<div id="grp-params-'+id+'">'+permParamsHtml(id)+'</div>';
        openModal(h,'perm-modal');
      });
    });
  });
}
function permToggle(el,gid,type,name){
  var on=!el.classList.contains('on');
  el.classList.toggle('on',on);
  var body={plugins:{},routes:{}};
  if(type==='plugin')body.plugins[name]=on;else body.routes[name]=on;
  R.post('/admin/api/groups/'+gid+'/permissions',body).then(function(d){
    if(!d.success){el.classList.toggle('on',!on);toast(d.message||T('user.perm_save_failed','权限保存失败'),'error')}
  });
}
function quickToggleParam(gid,key,label,forbidden){
  // 已禁止 → 传 null 删除规则（恢复默认允许）；未禁止 → 传 false 写入显式禁用
  R.post('/admin/api/groups/'+gid+'/params',{param_key:key,enabled:forbidden?null:false}).then(function(d){
    if(d.success){
      if(forbidden)delete _permParams[key];else _permParams[key]=false;
      renderPermParams(gid);
      toast(forbidden?T('user.param_restored','已恢复 {name}',{name:label}):T('user.param_forbidden','已禁止 {name}',{name:label}),'success');
    }else toast(d.message||T('core.op_failed','操作失败'),'error');
  });
}
function addGroupParam(gid){
  var inp=document.getElementById('new-gparam-'+gid);
  var pk=inp.value.trim();
  if(!pk){toast(T('user.need_param_name','请输入参数名'),'error');return}
  R.post('/admin/api/groups/'+gid+'/params',{param_key:pk,enabled:false}).then(function(d){
    if(d.success){_permParams[pk]=false;renderPermParams(gid);toast(T('user.param_forbidden','已禁止 {name}',{name:pk}),'success')}
    else toast(d.message||T('user.add_failed','添加失败'),'error');
  });
}
function delGroupParam(gid,pk){
  R.post('/admin/api/groups/'+gid+'/params',{param_key:pk,enabled:null}).then(function(d){
    if(d.success){delete _permParams[pk];renderPermParams(gid);toast(T('user.param_limit_removed','已移除参数限制 {name}',{name:pk}),'success')}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  });
}

/* ================= 账号 ================= */
var _acctList=[],_acctSel={};
function acctSelIds(){return Object.keys(_acctSel).map(Number)}
/* 管理组账号（category='admin'，主管理员也在其中）不参与任何批量操作：服务端在批处理入口
   就把它们整批挡掉了，界面上勾选框直接置灰，免得勾完点下去才吃一条错误提示 */
function _acctLocked(a){return !!a.is_default_admin||a.group_category==='admin'}
function acctBarHtml(){
  var ids=acctSelIds();
  if(!ids.length)return '';
  return '<div class="batchbar"><span>'+T('user.selected_accounts','已选 {n} 个账号',{n:'<span class="cnt">'+ids.length+'</span>'})+'</span><span class="sp"></span>'+
    '<button class="btn btn-sm" data-act="acct-transfer">'+T('user.transfer_group','转移用户组')+'</button>'+
    '<button class="btn btn-sm" data-act="acct-batch" data-op="enable">'+T('user.batch_enable','批量启用')+'</button>'+
    '<button class="btn btn-sm" data-act="acct-batch" data-op="disable">'+T('user.batch_disable','批量禁用')+'</button>'+
    '<button class="btn btn-sm btn-danger" data-act="acct-batch" data-op="delete">'+T('user.batch_delete','批量删除')+'</button>'+
    '<button class="btn btn-sm btn-ghost" data-act="acct-clear">'+T('user.clear_sel','取消选择')+'</button></div>';
}
function renderAcctBar(){
  var el=document.getElementById('acct-bar');if(el)el.innerHTML=acctBarHtml();
  syncAcctCheckAll();
}
/* 表头全选框只需反映当前页：跨页选择保留在 _acctSel 里，不改变当前页的勾选态 */
function syncAcctCheckAll(){
  var box=document.querySelector('#accounts-area input[data-act="acct-check-all"]');
  if(!box)return;
  var page=document.querySelectorAll('#accounts-area input[data-act="acct-check"]:not([disabled])');
  var all=page.length>0;
  page.forEach(function(c){if(!c.checked)all=false});
  box.checked=all;
}
/* 激活码开通的账号才有到期日：'' = 永久。到期日按站点配置时区的自然日比较
   （与后端一致）——取浏览器本地日期会在管理员时区与站点时区不同时误判「已过期」，
   故复用 fmtDT 同源的 TZ_OFFSET 换算 */
function _todayLocal(){
  return fmtDT(new Date().toISOString()).substring(0,10);
}
function acctExpiryHtml(a){
  var on=(a.expires_on||'').trim();
  if(!on)return T('user.permanent','永久');
  return on+(on<_todayLocal()?' <span class="badge badge-warn">'+T('user.expired','已过期')+'</span>':'');
}
/* 搜索关键字与用户组同理：数据刷新不重置，只有搜索框变化才回到第 1 页 */
var _acctQuery='',_acctSort='uid';
function acctSearch(){
  var el=document.getElementById('acct-search');
  _acctQuery=el?el.value.trim().toLowerCase():'';
  _pg['accounts']=1;
  renderAccounts();
}
function acctSortChange(){
  var el=document.getElementById('acct-sort');
  _acctSort=el?el.value:'uid';
  _pg['accounts']=1;
  renderAccounts();
}
/* 默认按 UID 升序；名称/用户组用 localeCompare('zh') 让中文按拼音而不是码点排 */
function _sortedAccounts(list){
  var arr=list.slice();
  var byUid=function(a,b){return _intVal(a.uid,0)-_intVal(b.uid,0)};
  if(_acctSort==='name')arr.sort(function(a,b){return String(a.name).localeCompare(String(b.name),'zh')});
  else if(_acctSort==='group')arr.sort(function(a,b){
    return String(a.group_name||'').localeCompare(String(b.group_name||''),'zh')||byUid(a,b);
  });
  else if(_acctSort==='uid-desc')arr.sort(function(a,b){return byUid(b,a)});
  else arr.sort(byUid);
  return arr;
}
function renderAccounts(){
  var list=_acctList.filter(function(a){return matchQuery(_acctQuery,[a.name,a.uid,a.group_name])});
  list=_sortedAccounts(list);
  var pg=pgSlice(list,'accounts',_PER_PAGE);
  // 批量操作条由 #acct-bar 容器负责渲染（renderAcctBar 就地更新它），表体里不再重复一份
  var h='<table><thead><tr><th style="width:36px"><input type="checkbox" data-act="acct-check-all" title="'+T('user.select_page_tip','选择本页')+'"></th>'+
    '<th class="num">UID</th><th>'+T('user.col_name','名称')+'</th><th>'+T('user.groups','用户组')+'</th><th class="num">'+T('user.col_evkey_count','EVkey 数')+'</th><th>'+T('user.col_expiry','有效期')+'</th><th class="col-dot">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(a){
    h+='<tr><td><input type="checkbox" data-act="acct-check" data-id="'+a.id+'"'+
      (_acctLocked(a)?' disabled title="'+T('user.admin_acct_no_batch','管理组账号不参与批量操作')+'"':'')+
      (_acctSel[a.id]?' checked':'')+'></td>';
    // UID 是注册顺序号，登录时可直接用它；内部 id 继续做接口主键，不出现在界面上
    h+='<td class="dim num">'+_intVal(a.uid,0)+'</td><td class="strong">'+esc(a.name)+'</td><td class="dim">'+esc(a.group_name||'')+'</td><td class="num">'+num(a.evkey_count||0)+'</td>';
    h+='<td class="dim">'+acctExpiryHtml(a)+'</td>';
    h+='<td class="col-dot">'+dotHtml(a.enabled?'dot-on':'dot-off',a.enabled?T('user.enabled','启用'):T('user.disabled','禁用'))+'</td>';
    // EVkeys / 额度 / 用量三块合成「详情」一个入口，弹窗内用子标签切换
    h+='<td><div class="acts"><button class="btn btn-sm" data-act="acct-detail" data-id="'+a.id+'" data-name="'+esc(a.name)+'">'+T('user.detail_btn','详情')+'</button>'+
      '<button class="btn btn-sm" data-act="acct-membership" data-id="'+a.id+'" data-name="'+esc(a.name)+'">'+T('user.membership_btn','权限记录')+'</button>'+
      '<button class="btn btn-sm" data-act="acct-edit" data-id="'+a.id+'"'+
      (a.is_default_admin?' disabled title="'+T('user.builtin_acct_no_edit','内置管理账号不可编辑')+'"':'')+'>'+T('core.edit','编辑')+'</button>'+
      '<span class="sep"></span>'+
      '<button class="btn btn-sm btn-danger" data-act="acct-del" data-id="'+a.id+'" data-name="'+esc(a.name)+'"'+
      (a.is_default_admin?' disabled title="'+T('user.builtin_acct_no_delete','内置管理账号不可删除')+'"':'')+'>'+T('btn.delete','删除')+'</button></div></td></tr>';
  });
  if(!pg.rows.length)h+='<tr><td colspan="8" class="empty">'+(_acctQuery?T('user.no_match_accounts','没有匹配的账号'):T('user.no_accounts','暂无账号'))+'</td></tr>';
  document.getElementById('accounts-area').innerHTML='<div id="acct-bar">'+acctBarHtml()+'</div>'+h+'</tbody></table>'+pg.bar;
  syncAcctCheckAll();
  _pgRender['accounts']=renderAccounts;
}
function refreshAccounts(){
  R.get('/admin/api/accounts').then(function(d){
    _acctList=d.accounts||[];
    // 已删除的账号要从选择集里摘掉，否则批量操作会带着不存在的 id 提交；管理组账号
    // （含主管理员）永远不参与批量，历史上万一留下过也一并摘掉
    var live={};_acctList.forEach(function(a){if(!_acctLocked(a))live[a.id]=1});
    Object.keys(_acctSel).forEach(function(k){if(!live[k])delete _acctSel[k]});
    renderAccounts();
  }).catch(function(){
    var el=document.getElementById('accounts-area');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function toggleAcctCheck(el){
  var id=parseInt(el.dataset.id);
  if(el.checked)_acctSel[id]=1;else delete _acctSel[id];
  renderAcctBar();
}
function toggleAcctCheckAll(el){
  var on=el.checked;
  document.querySelectorAll('#accounts-area input[data-act="acct-check"]:not([disabled])').forEach(function(c){
    var id=parseInt(c.dataset.id);
    c.checked=on;
    if(on)_acctSel[id]=1;else delete _acctSel[id];
  });
  renderAcctBar();
}
function clearAcctSel(){
  _acctSel={};
  document.querySelectorAll('#accounts-area input[data-act="acct-check"]:not([disabled])').forEach(function(c){c.checked=false});
  renderAcctBar();
}
function batchAccounts(action,group){
  var ids=acctSelIds();
  if(!ids.length){toast(T('user.need_pick_account','请先勾选账号'),'error');return}
  R.post('/admin/api/accounts/batch',{action:action,ids:ids,group_id:group}).then(function(d){
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    toast(T('user.batch_done','已处理 {n} 个账号',{n:d.affected}),'success');
    clearAcctSel();
    refreshAccounts();
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function showAcctTransfer(){
  var ids=acctSelIds();
  if(!ids.length){toast(T('user.need_pick_account','请先勾选账号'),'error');return}
  R.get('/admin/api/groups').then(function(gd){
    // 管理组不接受批量转入：那等于批量授予后台权限，需要逐个在「权限记录」里明确调整
    var opts=(gd.groups||[]).filter(function(g){return g.category!=='admin'})
      .map(function(g){return '<option value="'+g.id+'">'+esc(g.name)+'</option>'}).join('');
    if(!opts){toast(T('user.no_transfer_group','没有可转移到的用户组'),'error');return}
    var ov=openModal(
      '<h3>'+T('user.batch_transfer_title','批量转移用户组')+'</h3>'+
      '<p class="dim small modal-sub">'+T('user.batch_transfer_note','将 {n} 个账号转移到目标用户组，其 EVkey 与额度用量保持不变。',{n:ids.length})+'</p>'+
      '<label>'+T('user.target_group','目标用户组')+'</label><select class="input" id="ba-group">'+opts+'</select>'+
      '<label>'+T('user.type_to_confirm','输入 {name} 以确认',{name:'<span class="mono">TRANSFER</span>'})+'</label><input class="input" id="ba-text" autocomplete="off">'+
      '<div class="modal-actions"><button class="btn" data-act="modal-close">'+T('btn.cancel','取消')+'</button>'+
      '<button class="btn btn-primary" data-act="acct-transfer-confirm" disabled>'+T('user.confirm_transfer','确认转移')+'</button></div>','acct-transfer-modal');
    var yes=ov.querySelector('[data-act="acct-transfer-confirm"]');
    var inp=ov.querySelector('#ba-text');
    inp.focus();
    inp.addEventListener('input',function(){yes.disabled=inp.value.trim()!=='TRANSFER'});
    inp.addEventListener('keydown',function(e){if(e.key==='Enter'&&!yes.disabled)yes.click()});
    yes.addEventListener('click',function(){
      var gid=parseInt(ov.querySelector('#ba-group').value);
      ov.remove();
      batchAccounts('transfer',gid);
    });
  });
}
function batchDeleteAccounts(){
  var ids=acctSelIds();
  if(!ids.length){toast(T('user.need_pick_account','请先勾选账号'),'error');return}
  uiConfirm({
    title:T('user.batch_del_title','批量删除账号'),
    message:T('user.batch_del_confirm','将删除 {n} 个账号及其名下全部 EVkey，使用这些 EVkey 的设备会立即失效，且不可恢复。',{n:ids.length}),
    confirmText:T('user.delete_forever','永久删除'),danger:true
  }).then(function(ok){if(ok)batchAccounts('delete')});
}
function showAccountModal(id){
  var a=id?_acctList.find(function(x){return x.id===id}):{};
  R.get('/admin/api/groups').then(function(gd){
    var opts=(gd.groups||[]).map(function(g){return '<option value="'+g.id+'"'+(a.group_id===g.id?' selected':'')+'>'+esc(g.name)+'</option>'}).join('');
    var ov=openModal(
      '<h3>'+(id?T('user.edit_account','编辑账号'):T('user.new_account_title','新增账号'))+'</h3>'+
      '<label>'+T('user.account_name_label','账号名')+'</label><input class="input" id="aname" value="'+esc(a.name||'')+'">'+
      // 邮箱只在详情/编辑里出现，不占列表列（用户明确要求）；它是「忘记密码」的唯一凭据
      '<label>'+(id?T('user.email_label_clear','邮箱（留空则清除）'):T('user.email_label','邮箱'))+'</label><input class="input" id="aemail" value="'+esc(a.email||'')+'" placeholder="'+(id?'':T('user.email_ph','用于找回密码'))+'">'+
      '<label>'+(id?T('user.password_keep','密码（留空则不修改）'):T('user.password_label','密码'))+'</label><input class="input" type="password" id="apass" placeholder="'+(id?T('user.password_ph_keep','留空则不修改'):T('user.password_ph','至少 6 位字符'))+'">'+
      '<label>'+T('user.groups','用户组')+'</label><select class="input" id="agroup">'+opts+'</select>'+
      '<div class="modal-actions"><button class="btn btn-primary" data-act="acct-save" data-id="'+(id||0)+'">'+T('btn.save','保存')+'</button></div>',
      'acct-modal');
    modalForm(ov,function(){saveAccount(id,ov.querySelector('[data-act="acct-save"]'))});
  });
}
function saveAccount(id,btn){
  var n=document.getElementById('aname').value.trim();
  var e=document.getElementById('aemail').value.trim();
  var g=parseInt(document.getElementById('agroup').value);
  if(!n){toast(T('user.need_account_name','请输入账号名'),'error');return}
  var body={name:n,email:e,group_id:g};
  if(!e&&!id){toast(T('user.need_email','请输入邮箱'),'error');return}
  if(e&&e.indexOf('@')<0){toast(T('register.bad_email','邮箱格式不正确'),'error');return}
  var p=document.getElementById('apass').value;
  if(p){
    if(p.length<6){toast(T('user.pw_short','密码至少 6 位字符'),'error');return}
    body.password=p;
  }else if(!id){toast(T('user.need_new_password','新账号必须设置密码'),'error');return}
  btnBusy(btn,true);
  var req=id?R.put('/admin/api/accounts/'+id,body):R.post('/admin/api/accounts',body);
  req.then(function(dd){
    btnBusy(btn,false);
    if(dd.success===false)toast(dd.message||T('core.op_failed','操作失败'),'error');
    else{toast(id?T('user.account_updated','账号「{name}」已更新',{name:n}):T('user.account_created','账号「{name}」已创建',{name:n}),'success');refreshAccounts();var m=document.getElementById('acct-modal');if(m)m.remove()}
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function delAccount(id,name){
  uiConfirm({
    title:T('user.del_account_title','删除账号'),
    message:T('user.del_account_confirm','将同时删除「{name}」名下的全部 EVkey，使用这些 EVkey 的设备会立即失效。',{name:(name||id)}),
    confirmText:T('user.delete_forever','永久删除'),danger:true,requireText:name||String(id)
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/accounts/'+id).then(function(d){
      if(d.success===false)toast(d.message||T('core.op_failed','操作失败'),'error');
      else{toast(T('user.account_deleted','账号已删除'),'success');refreshAccounts()}
    });
  });
}
/* ================= 账号详情（EVkeys / 额度 / 用量） ================= */
/* 三块内容原来各占一个并排按钮，现在合成一个「详情」入口，弹窗内用子标签切换；
   子标签各自懒加载，切到哪块才拉哪块的数据，避免打开弹窗就打三个接口 */
var _currentAccountId=0,_currentAccountName='',_acctDetailTab='evkeys';
/* 顶层常量不能调 T()：子标签文案在函数里现取 */
function _acctDetailTabs(){
  return [['evkeys',T('user.tab_evkeys','EVkey')],['quota',T('user.tab_quota','额度')],['usage',T('user.tab_usage','用量')],['devices',T('user.tab_devices','设备')]];
}
// 邮箱只从列表数据里取：它不占表格列，只在详情弹窗里露一行（用户要求）
function _acctEmail(id){
  var a=_acctList.find(function(x){return x.id===id});
  return a?(a.email||''):'';
}
function showAccountDetail(id,name){
  _currentAccountId=id;
  if(name)_currentAccountName=name;
  if(!_acctDetailTab)_acctDetailTab='evkeys';
  var h='<h3>'+esc(_currentAccountName||('#'+id))+'</h3>'+
    '<p class="dim small modal-sub">'+T('user.email_line','邮箱：{value}',{value:esc(_acctEmail(id)||T('user.not_set','未设置'))})+'</p>'+
    '<div class="subtabs" style="margin:8px 0 16px">'+
      _acctDetailTabs().map(function(t){
        return '<span class="stab'+(_acctDetailTab===t[0]?' on':'')+'" data-act="acct-detail-tab" data-tab="'+t[0]+'">'+t[1]+'</span>';
      }).join('')+'</div>'+
    '<div id="acct-detail-body"><div class="empty">'+T('msg.loading','加载中...')+'</div></div>';
  var old=document.getElementById('acct-detail-modal');if(old)old.remove();
  openModal(h,'acct-detail-modal');
  loadAccountDetailTab();
}
function setAccountDetailTab(tab){
  _acctDetailTab=tab;
  var ov=document.getElementById('acct-detail-modal');
  if(ov)ov.querySelectorAll('.stab').forEach(function(s){s.classList.toggle('on',s.dataset.tab===tab)});
  loadAccountDetailTab();
}
/* 就地重绘当前子标签：evkey 增删改 / 额度发放重置后调用，标题与子标签栏不动 */
function refreshAccountDetail(){
  if(document.getElementById('acct-detail-modal'))loadAccountDetailTab();
}
function _acctDetailBody(html){
  var el=document.getElementById('acct-detail-body');
  if(el)el.innerHTML=html;
}
function loadAccountDetailTab(){
  var id=_currentAccountId;
  // 弹窗已被关掉时不再回填：异步响应晚于关闭会把 DOM 写进已脱离文档的容器
  if(!id||!document.getElementById('acct-detail-body'))return;
  _acctDetailBody('<div class="empty">'+T('msg.loading','加载中...')+'</div>');
  if(_acctDetailTab==='quota')loadAccountQuota();
  else if(_acctDetailTab==='usage')loadAccountUsage(id);
  else if(_acctDetailTab==='devices')loadAccountDevices(id);
  else loadAccountEvkeys(id);
}
/* 账号详情弹窗里的 evkey 列表：一个账号可能攒下很多 Key，5 条一页 */
var _acctEvkeys={id:0,items:[],max:0};
function acctEvkeysRender(){
  var evkeys=_acctEvkeys.items,maxv=_acctEvkeys.max,id=_acctEvkeys.id;
  // -1 = 不限，0 = 禁止创建，N = 最多 N 个（0 是禁止，不能标成「上限 0 个」被读成不限）
  var note=maxv<0?T('user.group_unlimited_note','（该组不限数量）'):(maxv===0?T('user.group_forbid_note','（该组禁止创建）'):T('user.group_max_note','（上限 {n} 个）',{n:maxv}));
  var h='<p class="dim small modal-sub">'+T('user.evkey_used_note','已使用 {n} 个{note}',{n:evkeys.length,note:note})+'</p>';
  if(evkeys.length){
    var pg=pgSlice(evkeys,'acct-evkeys',5);
    h+='<table><thead><tr><th>EVkey</th><th>'+T('plugin.col_desc','描述')+'</th><th class="col-state">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
    pg.rows.forEach(function(e){
      h+='<tr><td class="mono">'+esc(e.evkey)+'</td>';
      h+='<td class="dim">'+esc(e.description||'-')+'</td>';
      h+='<td><span class="sw sm'+(e.enabled?' on':'')+'" data-act="evkey-toggle" data-id="'+e.id+'" data-en="'+(e.enabled?'1':'0')+'"><span class="sw-track"></span>'+(e.enabled?T('user.enabled','启用'):T('user.disabled','禁用'))+'</span></td>';
      h+='<td><div class="acts"><button class="btn btn-sm" data-act="copy-text" data-copy="'+esc(e.evkey)+'">'+T('btn.copy','复制')+'</button>'+
        '<span class="sep"></span>'+
        '<button class="btn btn-sm btn-danger" data-act="evkey-del" data-id="'+e.id+'">'+T('btn.delete','删除')+'</button></div></td></tr>';
    });
    h+='</tbody></table>'+pg.bar;
  }else h+='<div class="empty">'+T('user.no_evkeys','暂无 EVkey')+'</div>';
  // -1 = 不限，恒可生成；0 = 禁止，不给按钮（后端也会拒）
  if(maxv===0)h+='<p class="dim small" style="margin-top:8px">'+T('user.evkey_forbidden','该用户组不允许创建 EVkey')+'</p>';
  else if(maxv<0||evkeys.length<maxv)h+='<div class="field-row" style="margin-top:8px">'+
    '<button class="btn btn-sm btn-primary" data-act="evkey-gen" data-id="'+id+'">'+T('user.gen_evkey','+ 生成新 EVkey')+'</button></div>';
  _acctDetailBody(h);
}
function loadAccountEvkeys(id){
  R.get('/admin/api/accounts/'+id+'/evkeys').then(function(d){
    var evkeys=d.evkeys||[];
    R.get('/admin/api/groups').then(function(gd){
      if(!document.getElementById('acct-detail-body'))return;
      var g=_acctList.find(function(x){return x.id===id})||{};
      var hit=(gd.groups||[]).find(function(x){return x.id===g.group_id});
      // 组查不到按 0（禁止）处理，与后端 group_max_evkeys 一致
      // 管理组则恒为不限：后端把它折算成 -1，库里存的数值对它不生效，不能照原值念
      var maxv=(hit&&hit.category==='admin')?-1:(hit?_intVal(hit.max_evkeys,0):0);
      _acctEvkeys={id:id,items:evkeys,max:maxv};
      _pg['acct-evkeys']=1;
      _pgRender['acct-evkeys']=acctEvkeysRender;
      acctEvkeysRender();
    });
  }).catch(function(){_acctDetailBody('<div class="empty">'+T('user.load_evkeys_failed','加载 EVkey 失败')+'</div>')});
}
function genEvkey(id,btn){
  btnBusy(btn,true,T('user.generating','生成中…'));
  R.post('/admin/api/accounts/'+id+'/evkeys',{}).then(function(d){
    btnBusy(btn,false);
    if(d.evkey){
      showSecret(T('user.evkey_generated','新 EVkey 已生成'),d.evkey,T('user.evkey_generated_note','请复制并妥善保存，设备侧使用该 EVkey 鉴权。'));
      refreshAccountDetail();
    }
    else toast(d.message||T('user.gen_failed','生成失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function toggleEvkey(eid,en,el){
  btnBusy(el,true);
  R.put('/admin/api/evkeys/'+eid,{enabled:en}).then(function(d){
    btnBusy(el,false);
    if(d.success){toast(en?T('user.evkey_enabled','EVkey 已启用'):T('user.evkey_disabled','EVkey 已禁用'),'success');refreshAccountDetail()}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
function delEvkey(eid){
  uiConfirm({title:T('user.del_evkey_title','删除 EVkey'),message:T('user.del_evkey_confirm','删除后使用该 EVkey 的设备将立即失效，且不可恢复。'),confirmText:T('btn.delete','删除'),danger:true}).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/evkeys/'+eid).then(function(d){
      if(d.success===false)toast(d.message||T('core.op_failed','操作失败'),'error');
      else{toast(T('user.evkey_deleted','EVkey 已删除'),'success');refreshAccountDetail()}
    });
  });
}

/* 账号用量：按天/按插件来自长期累计表，按 evkey 只能取日志窗口（表里没有 evkey 维度）。
   两个维度各自 5 条一页：窗口 30 天就是 30 行，插件数也没有上限 */
var _acctUsage={days:30,daily:[],plugins:[]};
function acctUsageRender(){
  var days=_acctUsage.days;
  function section(title,head,rows,key,row){
    var s='<h3 class="sec-title">'+title+'</h3>';
    if(!rows.length)return s+'<div class="empty">'+T('user.no_data','暂无数据')+'</div>';
    var pg=pgSlice(rows,key,5);
    s+='<table><thead><tr>'+head+'</tr></thead><tbody>';
    pg.rows.forEach(function(r){s+=row(r)});
    return s+'</tbody></table>'+pg.bar;
  }
  var h='<p class="dim small modal-sub">'+T('user.usage_note','按天与按插件为长期累计，不受日志清理影响；窗口为最近 {days} 天',{days:days})+'</p>';
  h+=section(T('user.by_day','按天'),'<th>'+T('user.col_date','日期')+'</th><th class="num">'+T('stats.col_requests','请求')+'</th><th class="num">'+T('stats.col_errors','错误')+'</th><th class="num">'+T('test.kpi_avg','平均耗时')+'</th>',_acctUsage.daily,'acct-usage-day',function(r){
    return '<tr><td class="mono">'+esc(r.date)+'</td><td class="num">'+num(r.total)+'</td><td class="num'+(r.errors>0?' err-text':'')+'">'+num(r.errors)+'</td><td class="mono dim num">'+(r.avg_ms!=null?r.avg_ms+'ms':'-')+'</td></tr>';
  });
  h+=section(T('stats.rank_plugin','按插件'),'<th>'+T('nav.plugins','插件')+'</th><th class="num">'+T('stats.col_requests','请求')+'</th><th class="num">'+T('stats.col_errors','错误')+'</th><th class="num">'+T('test.kpi_avg','平均耗时')+'</th>',_acctUsage.plugins,'acct-usage-plugin',function(r){
    return '<tr><td class="strong">'+esc(r.plugin_name)+'</td><td class="num">'+num(r.total)+'</td><td class="num'+(r.errors>0?' err-text':'')+'">'+num(r.errors)+'</td><td class="mono dim num">'+(r.avg_ms!=null?r.avg_ms+'ms':'-')+'</td></tr>';
  });
  _acctDetailBody(h);
}
function loadAccountUsage(id){
  var days=30;
  R.get('/admin/api/accounts/'+id+'/usage?days='+days).then(function(d){
    if(!document.getElementById('acct-detail-body'))return;
    if(d.success===false){_acctDetailBody('<div class="empty">'+esc(d.message||T('user.load_usage_failed','加载用量失败'))+'</div>');return}
    _acctUsage={days:days,daily:d.daily||[],plugins:d.by_plugin||[]};
    _pg['acct-usage-day']=1;_pg['acct-usage-plugin']=1;
    _pgRender['acct-usage-day']=acctUsageRender;
    _pgRender['acct-usage-plugin']=acctUsageRender;
    acctUsageRender();
  }).catch(function(){_acctDetailBody('<div class="empty">'+T('user.load_usage_failed','加载用量失败')+'</div>')});
}

/* 账号设备目录：自有的 ∪ 别人共享给它的（与用户端「我的设备」同一份口径）。
   只读列表——管理端不代账号改设备，编辑仍走用户自己的「我的设备」 */
var _acctDevices=[];
function acctDevicesRender(){
  var rows=_acctDevices;
  if(!rows.length){_acctDetailBody('<div class="empty">'+T('user.no_devices','暂无设备')+'</div>');return}
  var pg=pgSlice(rows,'acct-devices',5);
  var h='<table><thead><tr><th>'+T('user.col_device','设备')+'</th><th>'+T('user.col_belong','归属')+'</th>'+
    '<th>'+T('user.col_screen','屏幕')+'</th><th class="num">'+T('user.col_tasks','渲染项')+'</th>'+
    '<th class="col-dot">'+T('user.legend_status','状态')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(d){
    var dot,status;
    if(!d.paired){dot='dot-warn';status=T('account.dev_pending_claim','已认领，等待设备上线')}
    else if(d.last_seen_at){dot='dot-on';status=T('account.dev_status_online','在线')}
    else{dot='dot-off';status=T('account.dev_status_offline','离线')}
    var belong=d.owner?T('user.dev_owner','自有'):T('user.dev_shared_by','由 {name} 共享',{name:d.shared_by_name||'-'});
    h+='<tr><td>'+esc(d.name||d.model||('#'+d.id))+'</td>'+
      '<td class="dim">'+esc(belong)+'</td>'+
      '<td class="mono dim">'+(d.width&&d.height?d.width+'×'+d.height:'-')+'</td>'+
      '<td class="num">'+num(d.task_count)+'</td>'+
      '<td class="col-dot">'+dotHtml(dot,status)+'</td></tr>';
  });
  h+='</tbody></table>'+pg.bar;
  _acctDetailBody(h);
}
function loadAccountDevices(id){
  R.get('/admin/api/accounts/'+id+'/devices').then(function(d){
    if(!document.getElementById('acct-detail-body'))return;
    if(d.success===false){_acctDetailBody('<div class="empty">'+esc(d.message||T('user.load_devices_failed','加载设备失败'))+'</div>');return}
    _acctDevices=d.devices||[];
    _pg['acct-devices']=1;_pgRender['acct-devices']=acctDevicesRender;
    acctDevicesRender();
  }).catch(function(){_acctDetailBody('<div class="empty">'+T('user.load_devices_failed','加载设备失败')+'</div>')});
}

/* ================= 账号额度（发放 / 重置 / 变动记录） ================= */
/* 实际额度 = 用户组配额 + 累计发放额。发放额记在账号上、跨周期保留；
   按时间周期到期自动重置（未用不结转，额度不累加），按次总量用完即止。 */
function _quotaLogRows(logs){
  if(!logs||!logs.length)return '<div class="empty">'+T('user.no_quota_logs','暂无额度变动记录')+'</div>';
  var h='<table><thead><tr><th>'+T('user.col_time','时间')+'</th><th class="col-dot">'+T('core.col_action','操作')+'</th><th class="num">'+T('user.col_amount','数量')+'</th><th>'+T('user.col_period','周期')+'</th><th>'+T('user.col_reason','原因')+'</th><th>'+T('user.col_operator','操作人')+'</th></tr></thead><tbody>';
  logs.forEach(function(l){
    var n=_intVal(l.amount,0);
    var isGrant=l.action==='grant';
    var amt=isGrant?((n>0?'+':'')+n):'—';
    h+='<tr><td class="dim">'+fmtDT(l.created_at)+'</td>'+
      '<td class="col-dot">'+dotHtml(isGrant?'dot-on':'dot-off',isGrant?T('user.grant','发放'):T('user.reset','重置'))+'</td>'+
      '<td class="num mono">'+esc(String(amt))+'</td>'+
      '<td class="dim">'+esc(l.period?_periodLabel(l.period):'—')+'</td>'+
      '<td class="dim ellip" title="'+esc(l.reason||'')+'">'+esc(l.reason||'—')+'</td>'+
      '<td class="dim">'+esc(l.admin_name||'—')+'</td></tr>';
  });
  return h+'</tbody></table>';
}
function quotaPaneHtml(d){
  var unlimited=_intVal(d.base_limit,0)<=0;
  var note=(String(d.period)==='trial')
    ?T('user.trial_note','按次总量：用完即止、永不自动重置')
    :T('user.periodic_note','{period}：到期自动重置，未用部分不结转（额度不累加）',{period:_periodLabel(d.period)});
  var h='<p class="dim small modal-sub">'+T('user.quota_note','实际额度 = 用户组配额 + 累计发放额；当前为 {note}',{note:note})+'</p>';
  /* 弹窗宽度 680px：默认的 minmax(180px,1fr) 会把四个指标排成 3+1，这里收窄到 140px 让它们一行排满 */
  h+='<div class="metrics" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:4px">'+
    kpi(T('user.kpi_actual','实际额度'),unlimited?T('user.unlimited','不限'):T('user.times','{n}',{n:num(d.limit)}))+
    kpi(T('user.kpi_used','本周期已用'),unlimited?'—':T('user.times','{n}',{n:num(d.used)}))+
    kpi(T('user.kpi_remaining','剩余'),unlimited?T('user.unlimited','不限'):T('user.times','{n}',{n:num(d.remaining)}))+
    kpi(T('user.kpi_granted','累计发放'),T('user.times','{n}',{n:num(_intVal(d.granted,0))}))+
    '</div>';
  h+='<div class="sec-title">'+T('user.grant_title','发放额度')+'</div>';
  if(unlimited){
    h+='<div class="panel" style="margin-bottom:8px">'+T('user.quota_unlimited_note','用户组「{name}」的配额为 <b>不限</b>，无需发放；若要限制用量，请先在用户组里设置配额上限。',{name:esc(d.group_name||'')})+'</div>';
  }
  h+='<div class="field-row">'+
    [500,1000,2000].map(function(n){
      return '<button class="btn btn-sm" data-act="quota-grant" data-id="'+d.account_id+'" data-amount="'+n+'"'+(unlimited?' disabled':'')+'>+'+n+'</button>';
    }).join('')+
    '<input class="input" id="q-amount" type="number" placeholder="'+T('user.amount_ph','自定义次数')+'" style="flex:0 0 190px" title="'+T('user.amount_tip','填负数即回收额度')+'" '+(unlimited?'disabled':'')+'>'+
    '<button class="btn btn-sm btn-primary" data-act="quota-grant-custom" data-id="'+d.account_id+'"'+(unlimited?' disabled':'')+'>'+T('user.grant','发放')+'</button>'+
    '</div>';
  /* 原因单独一行并占满宽度：跟在按钮后面挤成 160px 时，稍微长一点的原因就被截断看不全 */
  h+='<div class="field-row" style="margin-top:8px">'+
    '<input class="input" id="q-greason" placeholder="'+T('user.grant_reason_ph','发放原因（选填，会记入变动记录）')+'"'+(unlimited?' disabled':'')+'>'+
    '</div>';
  h+='<div class="sec-title">'+T('user.reset_used_title','重置本周期已用')+'</div>';
  h+='<div class="field-row">'+
    '<input class="input" id="q-rreason" placeholder="'+T('user.reset_reason_ph','重置原因（选填，会记入变动记录）')+'"'+(unlimited?' disabled':'')+'>'+
    '<button class="btn btn-sm" data-act="quota-reset" data-id="'+d.account_id+'"'+(unlimited?' disabled':'')+'>'+T('user.manual_reset','手动重置')+'</button>'+
    '</div>';
  h+='<div class="small dim" style="margin-top:8px">'+T('user.quota_help','发放累加在账号上、跨周期保留，填负数即回收（调整后总额度不能小于 1）；重置只把「已用」归零，不动已发放的额度。')+'</div>';
  /* 图例挂在标题右侧而不是独占一行：弹窗空间紧凑，多一行会把表格再往下推 */
  h+='<div class="sec-title" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap">'+T('user.log_title','变动记录')+
    '<span class="dot-legend" style="margin-top:0"><span class="lg-row">'+
    '<span class="lg-item" title="'+T('user.legend_grant_tip','管理员发放（或回收）额外额度')+'"><i class="dot dot-on"></i>'+T('user.grant','发放')+'</span>'+
    '<span class="lg-item" title="'+T('user.legend_reset_tip','管理员手动把本周期已用量归零，已发放额度保留')+'"><i class="dot dot-off"></i>'+T('user.reset','重置')+'</span>'+
    '</span></span></div>';
  /* 变动记录会随发放 / 重置不断累积，5 条一页；翻页用缓存重绘，不再打一次接口 */
  var logs=d.logs||[];
  if(logs.length){
    var lp=pgSlice(logs,'acct-quota-logs',5);
    h+=_quotaLogRows(lp.rows)+lp.bar;
  }else h+=_quotaLogRows([]);
  return h;
}
function loadAccountQuota(){
  var id=_currentAccountId;
  R.get('/admin/api/accounts/'+id+'/quota').then(function(d){
    if(!document.getElementById('acct-detail-body'))return;
    if(d.success===false){_acctDetailBody('<div class="empty">'+esc(d.message||T('user.load_quota_failed','加载额度失败'))+'</div>');return}
    _pg['acct-quota-logs']=1;
    _pgRender['acct-quota-logs']=function(){_acctDetailBody(quotaPaneHtml(d))};
    _acctDetailBody(quotaPaneHtml(d));
  }).catch(function(){_acctDetailBody('<div class="empty">'+T('user.load_quota_failed','加载额度失败')+'</div>')});
}
function quotaGrant(id,amount,reason,btn){
  btnBusy(btn,true);
  R.post('/admin/api/accounts/'+id+'/quota/grant',{amount:amount,reason:reason}).then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('user.grant_failed','发放失败'),'error');return}
    toast(T('user.grant_done','已发放 {n}，当前额度 {total}',{n:amount,total:d.limit}),'success');
    refreshAccountDetail();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function quotaGrantQuick(id,amount,btn){
  var el=document.getElementById('q-greason');
  quotaGrant(id,amount,el?el.value.trim():'',btn);
}
function quotaGrantCustom(id,btn){
  var el=document.getElementById('q-amount');
  var n=_intVal(el?el.value:NaN,0);
  if(!n){toast(T('user.need_amount','请输入发放次数（可为负）'),'error');return}
  var r=document.getElementById('q-greason');
  quotaGrant(id,n,r?r.value.trim():'',btn);
}
function quotaReset(id,btn){
  var r=document.getElementById('q-rreason');
  btnBusy(btn,true);
  R.post('/admin/api/accounts/'+id+'/quota/reset',{reason:r?r.value.trim():''}).then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('user.reset_failed','重置失败'),'error');return}
    toast(T('user.reset_done','已重置本周期用量'),'success');
    refreshAccountDetail();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}

/* ================= 账号权限记录（会员属性调整 + 变动记录） ================= */
/* 改组 / 改到期日 / 改到期回落组集中在这里改：三者任一变化都会写一条
   account_membership_logs，编辑账号弹窗不碰这些字段，免得一次保存混进一堆隐式变更。
   只有一个例外：用户组可以选管理组——那是有意为之的提权，记录里会留下前后值与操作人 */
/* 弹窗里的变动记录单独占一块、5 条一页：翻页只重绘这一块，
   上方「改组 / 改到期日」的表单里填了一半的内容不会被清掉 */
var _memLogs=[];
function memLogRender(){
  var box=document.getElementById('mem-log-body'),bar=document.getElementById('mem-log-bar');
  if(!box)return;
  var pg=pgSlice(_memLogs,'mem-logs',5);
  box.innerHTML=memberLogRows(pg.rows);
  if(bar)bar.innerHTML=pg.bar;
}
function showMembership(id,name){
  var a=_acctList.find(function(x){return x.id===id})||{};
  ensureGroups().then(function(){
    return R.get('/admin/api/accounts/'+id+'/membership-logs?limit=100');
  }).then(function(d){
    if(!d||d.success===false){toast((d&&d.message)||T('user.load_mem_failed','加载权限记录失败'),'error');return}
    var gid=_intVal(a.group_id,0),fb=_intVal(a.fallback_group_id,0);
    var gh=_groupList.map(function(g){
      return '<option value="'+g.id+'"'+(gid===g.id?' selected':'')+'>'+esc(g.name)+(g.category==='admin'?T('user.admin_group_paren','（管理组）'):'')+'</option>';
    }).join('');
    // 回落组不给管理组：会员一到期就自动升成管理员，等于一条没人盯着的提权通道
    var fh='<option value="0"'+(fb?'':' selected')+'>'+T('user.no_transfer_keep','不转移（留在原组）')+'</option>';
    _groupList.forEach(function(g){
      if(g.category==='admin')return;
      fh+='<option value="'+g.id+'"'+(fb===g.id?' selected':'')+'>'+esc(g.name)+'</option>';
    });
    var h='<h3>'+T('user.mem_title','{name} · 权限记录',{name:esc(name||('#'+id))})+'</h3>';
    /* 主管理员（内置管理账号）的会员属性整体锁死：它是后台唯一的兜底入口，被改到别的
       用户组或改了到期日都等于把这个入口改掉。服务端 PUT /accounts 也是整条拒的，
       这里把表单置灰只留「变动记录」，不摆一套点了必失败的控件 */
    if(a.is_default_admin){
      h+='<p class="dim small modal-sub">'+T('user.builtin_acct_mem_locked','内置管理账号不可改组或调整会员，仅可查看变动记录')+'</p>';
    }else{
      h+='<p class="dim small modal-sub">'+T('user.mem_sub','改组、提前结束或延长会员到期日、改到期回落组都会留一条记录，含前后值与操作人')+'</p>'+
        '<label>'+T('user.groups','用户组')+'</label><select class="input" id="m-group">'+gh+'</select>'+
        '<label>'+T('user.membership_expires_label','会员到期日（留空 = 永久有效）')+'</label><input class="input" type="date" id="m-exp" value="'+esc(a.expires_on||'')+'">'+
        '<label>'+T('user.membership_fallback_label','到期后转入（不能是管理组）')+'</label><select class="input" id="m-fallback">'+fh+'</select>'+
        '<label>'+T('user.reason_label','操作原因（选填，会记入下方记录）')+'</label><input class="input" id="m-reason" autocomplete="off" placeholder="'+T('user.reason_ph','例如：活动赠送 / 用户申请延长')+'">'+
        '<div class="modal-actions"><button class="btn btn-primary" data-act="mem-save" data-id="'+id+'">'+T('user.save_changes','保存变更')+'</button></div>';
    }
    h+='<div class="sec-title" style="border-top:1px solid var(--line);padding-top:16px">'+T('user.log_title_count','变动记录（共 {n} 条）',{n:num(d.total||0)})+'</div>'+
      '<div id="mem-log-body"></div><div id="mem-log-bar"></div>';
    var old=document.getElementById('mem-modal');if(old)old.remove();
    openModal(h,'mem-modal');
    _memLogs=d.items||[];
    _pg['mem-logs']=1;
    _pgRender['mem-logs']=memLogRender;
    memLogRender();
  }).catch(function(){toast(T('user.load_mem_failed','加载权限记录失败'),'error')});
}
function saveMembership(id,btn){
  var gid=_intVal((document.getElementById('m-group')||{}).value,0);
  if(!gid){toast(T('user.need_group','请选择用户组'),'error');return}
  var body={
    group_id:gid,
    expires_on:((document.getElementById('m-exp')||{}).value||'').trim(),
    fallback_group_id:_intVal((document.getElementById('m-fallback')||{}).value,0),
    reason:((document.getElementById('m-reason')||{}).value||'').trim()
  };
  btnBusy(btn,true);
  R.put('/admin/api/accounts/'+id,body).then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('core.save_failed','保存失败'),'error');return}
    var m=document.getElementById('mem-modal');if(m)m.remove();
    toast(T('user.mem_updated','权限已更新'),'success');
    refreshAccounts();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}

/* ================= 注册申请 ================= */
/* 这里只处理待审批：一个账号的申请折叠成一行，展开才逐条列出；批量处理的单位同样是账号。
   已批准/已拒绝属于历史，审批时用不上，不进列表也就没有状态列 */
/* 展开明细是 4 列，固定列宽：不固定的话展开瞬间各列宽度会重排，看着像整块跳了一下 */
var APP_COLS='<colgroup><col style="width:64px"><col><col style="width:180px"><col style="width:150px"></colgroup>';
var _appGroups=[],_appSel={},_appExpanded={};
/* 老库的申请可能没有 account_id，用账号名兜底做标识 */
function appKey(g){return g.account_id?('a'+g.account_id):('n'+g.account_name)}
/* 所选账号下仍待审批的申请 id：只提交这些，后端还会再校验一次状态 */
function appSelPendingIds(){
  var ids=[];
  _appGroups.forEach(function(g){
    if(!_appSel[appKey(g)])return;
    (g.applications||[]).forEach(function(a){if(a.status==='pending')ids.push(a.id)});
  });
  return ids;
}
function appBarHtml(){
  var keys=Object.keys(_appSel);
  if(!keys.length)return '';
  var n=appSelPendingIds().length;
  return '<div class="batchbar"><span>'+T('user.sel_apps','已选 {a} 个账号 · {b} 个待审批申请',{a:'<span class="cnt">'+keys.length+'</span>',b:'<span class="cnt">'+n+'</span>'})+'</span><span class="sp"></span>'+
    '<button class="btn btn-sm btn-primary" data-act="app-batch" data-op="approve"'+(n?'':' disabled')+'>'+T('user.batch_approve','批量批准')+'</button>'+
    '<button class="btn btn-sm btn-danger" data-act="app-batch" data-op="reject"'+(n?'':' disabled')+'>'+T('user.batch_reject','批量拒绝')+'</button>'+
    '<button class="btn btn-sm btn-ghost" data-act="app-clear">'+T('user.clear_sel','取消选择')+'</button></div>';
}
function renderAppBar(){
  var el=document.getElementById('apps-bar');if(el)el.innerHTML=appBarHtml();
  syncAppCheckAll();
}
/* 表头全选框只反映当前页：跨页选择本来就会在刷新时按当前页裁剪 */
function syncAppCheckAll(){
  var box=document.querySelector('#apps-area input[data-act="app-check-all"]');
  if(!box)return;
  var page=document.querySelectorAll('#apps-area input[data-act="app-check"]');
  var all=page.length>0;
  page.forEach(function(c){if(!c.checked)all=false});
  box.checked=all;
}
function clearAppSel(){
  _appSel={};
  document.querySelectorAll('#apps-area input[data-act="app-check"]').forEach(function(c){c.checked=false});
  renderAppBar();
}
function toggleAppCheck(el){
  if(el.checked)_appSel[el.dataset.key]=1;else delete _appSel[el.dataset.key];
  renderAppBar();
}
function toggleAppCheckAll(el){
  var on=el.checked;
  document.querySelectorAll('#apps-area input[data-act="app-check"]').forEach(function(c){
    c.checked=on;
    if(on)_appSel[c.dataset.key]=1;else delete _appSel[c.dataset.key];
  });
  renderAppBar();
}
function appDetailHtml(g,cols){
  var apps=g.applications||[];
  var h='<td colspan="'+cols+'">';
  if(!apps.length)h+='<div class="empty" style="padding:16px 0">'+T('user.no_pending','暂无待审批申请')+'</div>';
  else{
    h+='<table class="stat-table">'+APP_COLS+'<thead><tr><th class="num">ID</th><th>'+T('user.col_desc','说明')+'</th><th>'+T('user.col_submitted','提交时间')+'</th><th>'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
    apps.forEach(function(a){
      h+='<tr><td class="dim num">'+a.id+'</td>'+
        '<td class="dim ellip" title="'+esc(a.applicant_note||'')+'">'+esc(a.applicant_note||'-')+'</td>'+
        '<td class="dim">'+fmtDT(a.created_at)+'</td>'+
        '<td><div class="acts"><button class="btn btn-sm btn-primary" data-act="app-approve" data-id="'+a.id+'">'+T('user.approve','批准')+'</button>'+
        '<button class="btn btn-sm btn-danger" data-act="app-reject" data-id="'+a.id+'">'+T('user.reject','拒绝')+'</button></div></td></tr>';
    });
    h+='</tbody></table>';
  }
  return h+'</td>';
}
function toggleAppGroup(el){
  var key=el.dataset.key;
  var tr=el.closest('tr');
  var next=tr.nextElementSibling;
  if(next&&next.classList.contains('detail-row')){next.remove();el.textContent='▸';delete _appExpanded[key];return}
  var g=null;
  _appGroups.forEach(function(x){if(appKey(x)===key)g=x});
  if(!g)return;
  // colspan 必须等于父行实际格子数：写多会撑出多余空列，table-layout:fixed 下
  // 空列照样平分宽度，首列就被压窄、上半部分跟着错位
  var det=document.createElement('tr');
  det.className='detail-row';
  det.dataset.dkey=key;
  det.innerHTML=appDetailHtml(g,tr.children.length||5);
  tr.after(det);
  el.textContent='▾';
  _appExpanded[key]=1;
}
/* 自动刷新会重建整张表，这里把展开过的账号重新展开，避免明细莫名收起 */
function restoreAppExpanded(){
  var els=document.querySelectorAll('#apps-area .expander');
  var found={};
  for(var i=0;i<els.length;i++){
    var k=els[i].dataset.key;
    if(!_appExpanded[k])continue;
    found[k]=1;
    toggleAppGroup(els[i]);
  }
  Object.keys(_appExpanded).forEach(function(k){if(!found[k])delete _appExpanded[k]});
}
function refreshApplications(){
  var page=pgPage('apps');
  R.get('/admin/api/applications?limit='+_PER_PAGE+'&offset='+((page-1)*_PER_PAGE)).then(function(d){
    if(d.success===false){document.getElementById('apps-area').innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    var groups=d.groups||[];
    _appGroups=groups;
    // 不在当前页的账号要从选择集里摘掉：批量只提交当前页的 id，留着会和条数对不上
    var live={};groups.forEach(function(g){live[appKey(g)]=1});
    Object.keys(_appSel).forEach(function(k){if(!live[k])delete _appSel[k]});
    var total=d.total||0;
    var pending=d.pending_count||0;
    var dot=document.getElementById('apps-dot'),dot2=document.getElementById('apps-dot2');
    dot.style.display=pending>0?'inline-block':'none';
    if(dot2)dot2.style.display=pending>0?'inline-block':'none';
    var h='<table><thead><tr><th style="width:36px"><input type="checkbox" data-act="app-check-all" title="'+T('user.select_page_tip','选择本页')+'"></th>'+
      '<th>'+T('user.accounts','账号')+'</th><th class="num">'+T('user.col_pending','待审批')+'</th><th>'+T('user.col_latest','最近提交')+'</th></tr></thead><tbody>';
    if(!groups.length)h+='<tr><td colspan="4" class="empty">'+T('user.no_pending','暂无待审批申请')+'</td></tr>';
    groups.forEach(function(g){
      var k=appKey(g);
      h+='<tr><td><input type="checkbox" data-act="app-check" data-key="'+esc(k)+'"'+(_appSel[k]?' checked':'')+'></td>';
      h+='<td><span class="expander" data-act="app-expand" data-key="'+esc(k)+'">▸</span> <span class="strong">'+esc(g.account_name)+'</span>'+(g.account_id?' <span class="dim mono">#'+g.account_id+'</span>':'')+'</td>';
      h+='<td class="num">'+num(g.pending)+'</td><td class="dim">'+fmtDT(g.latest_at)+'</td></tr>';
    });
    document.getElementById('apps-area').innerHTML='<div id="apps-bar">'+appBarHtml()+'</div>'+h+'</tbody></table>'+pgBar('apps',total,_PER_PAGE);
    _pgRender['apps']=refreshApplications;
    syncAppCheckAll();
    restoreAppExpanded();
    // 总条数变少导致当前页越界时，pgBar 已把页码夹回有效范围，这里按新页码重取一次
    if(!groups.length&&total>0&&page!==pgPage('apps')){refreshApplications()}
  });
}
/* 单个批准：直接提交，不弹窗、不提示、不展示 evkey。evkey 由申请人在个人控制台
   自行查看，管理员没必要转抄一遍；只有批量操作才给一次二次确认，且只报数量。
   失败（超出持有上限、网络错误等）仍旧提示，否则会被误当成已批准 */
function approveApp(id){
  R.post('/admin/api/applications/'+id+'/approve',{}).then(function(d){
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    refreshApplications();refreshAccounts();
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function batchApproveApps(){
  var ids=appSelPendingIds();
  if(!ids.length){toast(T('user.no_pending_selected','所选账号没有待审批的申请'),'error');return}
  uiConfirm({title:T('user.batch_approve','批量批准'),
    message:T('user.approve_keys_confirm','批准 {n} 个 EVkey？',{n:ids.length})}).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/applications/batch',{action:'approve',ids:ids}).then(function(d){
      if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      // 批量里被上限挡下的账号：不提示的话会被误当成已批准
      if(d.skipped&&d.skipped.length)toast(T('user.app_skipped','有 {n} 个申请因超过 EVkey 持有上限未批准：{first}',{n:d.skipped.length,first:d.skipped[0]}),'error');
      clearAppSel();refreshApplications();refreshAccounts();
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
/* 单个拒绝同样静默；批量才一次二次确认 */
function rejectApp(id){
  R.post('/admin/api/applications/'+id+'/reject',{}).then(function(d){
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    refreshApplications();
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function batchRejectApps(){
  var ids=appSelPendingIds();
  if(!ids.length){toast(T('user.no_pending_selected','所选账号没有待审批的申请'),'error');return}
  uiConfirm({danger:true,title:T('user.batch_reject','批量拒绝'),
    message:T('user.reject_keys_confirm','拒绝 {n} 个 EVkey？',{n:ids.length}),
    confirmText:T('user.reject','拒绝')}).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/applications/batch',{action:'reject',ids:ids}).then(function(d){
      if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      clearAppSel();refreshApplications();
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
function checkApps(){
  R.get('/admin/api/applications?limit=1').then(function(d){
    var n=d.pending_count||0;
    var dot=document.getElementById('apps-dot'),dot2=document.getElementById('apps-dot2');
    dot.style.display=n>0?'inline-block':'none';
    if(dot2)dot2.style.display=n>0?'inline-block':'none';
    dot.title=T('user.pending_count','{n} 个待审批',{n:n});
  });
}
'''
