/* ================= 设备（分组：设备总列表 / 设备签入审批） ================= */
var _deviceSub='list';
function switchDeviceSubTab(name){
  _deviceSub=name;
  document.getElementById('device-sub-list').style.display=name==='list'?'':'none';
  document.getElementById('device-sub-approvals').style.display=name==='approvals'?'':'none';
  /* 点亮由 switchTab 对 .tab[data-sub] 统一处理；面包屑要跟子视图走，这里刷一次 */
  paintCrumbs('devices');
  if(name==='list'){refreshDevices();checkDeviceSignins()}
  else{refreshDeviceSignins()}
}
/* 当前在设备分页时，自动刷新只重载当前那一个子视图，不去动另一个的 DOM。
   待审计数（红点）与当前子视图无关，两种情况下都顺手刷一次 */
function refreshDeviceSection(){
  if(_deviceSub==='approvals')refreshDeviceSignins();
  else refreshDevices();
  checkDeviceSignins();
}
/* 设备上限文案（devLimitText）由共享层提供：-1 = 不限、0 = 禁止、N = 最多 N 台 */

/* ---------- 设备总列表：每个账号一行（账号 / 用户名 / 用户组 / 设备数 / 上限） ---------- */
var _devList=[],_devQuery='';
function devSearch(){
  var el=document.getElementById('dev-search');
  _devQuery=(el&&el.value||'').trim().toLowerCase();
  _pg['dev-list']=1;
  devListRender();
}
function refreshDevices(){
  R.get('/admin/api/devices').then(function(d){
    if(d.success===false){document.getElementById('devices-area').innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _devList=d.accounts||[];
    var info=document.getElementById('dev-page-info');
    if(info)info.textContent=T('device.page_info','共 {a} 个账号 · {b} 台设备',{a:num(d.total||0),b:num(d.device_total||0)});
    _pg['dev-list']=1;_pgRender['dev-list']=devListRender;
    devListRender();
  }).catch(function(){document.getElementById('devices-area').innerHTML='<div class="empty">'+T('msg.network_error','网络错误')+'</div>'});
}
function devListRender(){
  var rows=_devList.filter(function(a){
    return matchQuery(_devQuery,[a.account_name,a.group_name,a.uid,a.account_id]);
  });
  if(!rows.length){document.getElementById('devices-area').innerHTML='<div class="empty">'+T('device.no_accounts','暂无账号')+'</div>';return}
  // 一页 20 条，与账号列表同一套分页（pgSlice 自带「当前页越界回夹」）
  var pg=pgSlice(rows,'dev-list',_PER_PAGE);
  var h='<table><thead><tr><th class="num" style="width:92px">'+T('device.col_uid','账号')+'</th>'+
    '<th style="width:26%">'+T('device.col_username','用户名')+'</th><th>'+T('user.col_group','用户组')+'</th>'+
    '<th class="num">'+T('device.col_count','设备数 / 上限')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(a){
    var used=num(a.device_count||0),maxv=devLimitText(a.max_devices);
    h+='<tr><td class="dim num">'+_intVal(a.uid,0)+'</td>'+
      '<td class="strong">'+esc(a.account_name||('#'+a.account_id))+'</td>'+
      '<td class="dim">'+esc(a.group_name||'-')+'</td>'+
      '<td class="num mono">'+T('device.used_of_max','{used} / {max}',{used:used,max:maxv})+'</td>'+
      '<td><div class="acts"><button class="btn btn-sm" data-act="device-user" data-id="'+a.account_id+'" title="'+T('device.view_detail','查看设备列表')+'" aria-label="'+T('device.view_detail','查看设备列表')+'">'+T('device.detail','详情')+'</button></div></td></tr>';
  });
  document.getElementById('devices-area').innerHTML=h+'</tbody></table>'+pg.bar;
}

/* ---------- 账号设备详情弹窗（复用账号详情里那张设备表的列 + 管理端治理操作） ---------- */
var _devUserItems=[],_devUserName='',_devUserAcct=0,_devUserGroup='-',_devUserMax=-1;
function devUserSub(used){
  return T('device.owner_line','用户组：{group} · 设备数 {used} / {max}',
    {group:esc(_devUserGroup||'-'),used:num(used||0),max:devLimitText(_devUserMax)});
}
function devUserRender(){
  var el=document.getElementById('dev-user-body');
  if(!el)return;
  var rows=_devUserItems;
  if(!rows.length){el.innerHTML='<div class="empty">'+T('user.no_devices','暂无设备')+'</div>';return}
  var pg=pgSlice(rows,'dev-user',5);
  var h='<table><thead><tr><th>'+T('user.col_device','设备')+'</th><th>'+T('user.col_belong','归属')+'</th>'+
    '<th>'+T('user.col_screen','屏幕')+'</th><th class="num">'+T('user.col_tasks','渲染项')+'</th>'+
    '<th class="col-dot">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(d){
    var dot,status;
    if(!d.paired){dot='dot-warn';status=T('account.dev_pending_claim','已认领，等待设备上线')}
    else if(d.last_seen_at){dot='dot-on';status=T('account.dev_status_online','在线')}
    else{dot='dot-off';status=T('account.dev_status_offline','离线')}
    var belong=d.owner?T('user.dev_owner','自有'):T('user.dev_shared_by','由 {name} 共享',{name:d.shared_by_name||'-'});
    // 启用/停用按钮的文字随当前状态取反；删除是不可逆操作，走二次确认
    var toggleLabel=d.enabled?T('device.disable','停用设备'):T('device.enable','启用设备');
    h+='<tr><td>'+esc(d.name||d.model||('#'+d.id))+'</td>'+
      '<td class="dim">'+esc(belong)+'</td>'+
      '<td class="mono dim">'+(d.width&&d.height?d.width+'×'+d.height:'-')+'</td>'+
      '<td class="num">'+num(d.task_count)+'</td>'+
      '<td class="col-dot">'+dotHtml(dot,status)+'</td>'+
      '<td><div class="acts">'+
      '<button class="btn btn-sm" data-act="dadmin-dev-toggle" data-id="'+d.id+'" data-en="'+(d.enabled?'1':'0')+'">'+esc(toggleLabel)+'</button>'+
      '<button class="btn btn-sm btn-danger" data-act="dadmin-dev-del" data-id="'+d.id+'">'+esc(T('device.del_title','删除设备'))+'</button>'+
      '</div></td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+pg.bar;
}
function loadDeviceUser(){
  R.get('/admin/api/devices/'+_devUserAcct).then(function(d){
    if(!document.getElementById('dev-user-body'))return;   // 响应回来前弹窗已关，不再回填
    if(d.success===false){document.getElementById('dev-user-body').innerHTML='<div class="empty">'+esc(d.message||T('user.load_devices_failed','加载设备失败'))+'</div>';return}
    _devUserItems=d.devices||[];
    var sub=document.getElementById('dev-user-sub');
    if(sub)sub.innerHTML=devUserSub(d.owned);   // 增删之后头部那行计数跟着走，不留旧数
    devUserRender();
  }).catch(function(){
    var el=document.getElementById('dev-user-body');
    if(el)el.innerHTML='<div class="empty">'+T('user.load_devices_failed','加载设备失败')+'</div>';
  });
}
function showDeviceUserModal(id){
  var a=_devList.find(function(x){return x.account_id===id})||{};
  _devUserName=a.account_name||('#'+id);
  _devUserAcct=id;_devUserGroup=a.group_name||'-';_devUserMax=a.max_devices;
  var h='<h3>'+esc(_devUserName)+'</h3>'+
    '<p class="dim small modal-sub" id="dev-user-sub">'+devUserSub(a.device_count)+'</p>'+
    '<div id="dev-user-body"><div class="empty">'+T('msg.loading','加载中...')+'</div></div>';
  var old=document.getElementById('dev-user-modal');if(old)old.remove();
  openModal(h,'dev-user-modal');
  _pg['dev-user']=1;_pgRender['dev-user']=devUserRender;
  loadDeviceUser();
}
/* 启用 / 停用：单条静默生效（与 evkey 开关同一套体验），失败才提示 */
function toggleAdminDevice(id,en,el){
  btnBusy(el,true);
  R.put('/admin/api/devices/'+id,{enabled:!en}).then(function(d){
    btnBusy(el,false);
    if(!d||d.success===false){toast((d&&d.message)||T('core.op_failed','操作失败'),'error');return}
    loadDeviceUser();
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 删除：不可逆，先二次确认；成功同时刷新弹窗内列表与背后的设备总列表（计数会变） */
function deleteAdminDevice(id){
  uiConfirm({title:T('device.del_title','删除设备'),message:T('device.del_confirm','删除后该设备立即失效且不可恢复。'),
    confirmText:T('device.del_title','删除设备'),danger:true}).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/devices/'+id).then(function(d){
      if(!d||d.success===false){toast((d&&d.message)||T('core.op_failed','操作失败'),'error');return}
      toast(T('device.del_done','设备已删除'),'success');
      loadDeviceUser();refreshDevices();
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}

/* ---------- 设备签入审批：单条静默、批量二次确认（只报数量） ---------- */
var _dsignin=[],_dsigninSel={};
function _setDsigninDot(n){
  ['dsignin-dot','dsignin-dot2'].forEach(function(id){
    var el=document.getElementById(id);
    if(!el)return;
    el.style.display=n>0?'inline-block':'none';
    if(n>0)el.title=T('device.pending_count','{n} 条待审批',{n:n});
  });
}
function checkDeviceSignins(){
  if(!tabAllowed('devices'))return;
  R.get('/admin/api/device-signins').then(function(d){
    if(d&&d.success!==false)_setDsigninDot(d.pending_count||0);
  }).catch(function(){});
}
function dsigninSelIds(){
  return Object.keys(_dsigninSel).map(function(k){return parseInt(k,10)});
}
function dsigninBarHtml(){
  var n=dsigninSelIds().length;
  return '<div class="batchbar"><span>'+T('device.sel_note','已选 {n} 条',{n:'<span class="cnt">'+n+'</span>'})+'</span><span class="sp"></span>'+
    '<button class="btn btn-sm btn-primary" data-act="dsignin-batch" data-op="approve"'+(n?'':' disabled')+'>'+T('user.batch_approve','批量批准')+'</button>'+
    '<button class="btn btn-sm btn-danger" data-act="dsignin-batch" data-op="reject"'+(n?'':' disabled')+'>'+T('user.batch_reject','批量拒绝')+'</button>'+
    '<button class="btn btn-sm btn-ghost" data-act="dsignin-clear">'+T('user.clear_sel','取消选择')+'</button></div>';
}
function renderDsigninBar(){
  var el=document.getElementById('dsignin-bar');if(el)el.innerHTML=dsigninBarHtml();
  syncDsigninCheckAll();
}
function syncDsigninCheckAll(){
  var box=document.querySelector('#dsignin-area input[data-act="dsignin-check-all"]');
  if(!box)return;
  var page=document.querySelectorAll('#dsignin-area input[data-act="dsignin-check"]');
  var all=page.length>0;
  page.forEach(function(c){if(!c.checked)all=false});
  box.checked=all;
}
function toggleDsigninCheck(el){
  if(el.checked)_dsigninSel[el.dataset.id]=1;else delete _dsigninSel[el.dataset.id];
  renderDsigninBar();
}
function toggleDsigninCheckAll(el){
  var on=el.checked;
  document.querySelectorAll('#dsignin-area input[data-act="dsignin-check"]').forEach(function(c){
    c.checked=on;
    if(on)_dsigninSel[c.dataset.id]=1;else delete _dsigninSel[c.dataset.id];
  });
  renderDsigninBar();
}
function clearDsigninSel(){
  _dsigninSel={};
  document.querySelectorAll('#dsignin-area input[data-act="dsignin-check"]').forEach(function(c){c.checked=false});
  renderDsigninBar();
}
function dsigninRender(){
  var area=document.getElementById('dsignin-area');
  if(!area)return;
  var rows=_dsignin;
  var info=document.getElementById('dsignin-page-info');
  if(info)info.textContent=T('device.pending_count','{n} 条待审批',{n:num(rows.length)});
  if(!rows.length){area.innerHTML='<div class="empty">'+T('device.no_signins','暂无待审批的签入')+'</div>';return}
  // 与 evkey 审批同一套前端分页：一页 20 条、底部 pager；批量只作用于当前页勾选项
  var pg=pgSlice(rows,'dsignin',_PER_PAGE);
  var h='<table><thead><tr><th style="width:36px"><input type="checkbox" data-act="dsignin-check-all" title="'+T('user.select_page_tip','选择本页')+'"></th>'+
    '<th class="num" style="width:92px">'+T('device.col_uid','账号')+'</th><th>'+T('device.col_username','用户名')+'</th>'+
    '<th>'+T('device.col_device','设备')+'</th><th>'+T('user.col_group','用户组')+'</th>'+
    '<th>'+T('user.col_submitted','提交时间')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(s){
    h+='<tr><td><input type="checkbox" data-act="dsignin-check" data-id="'+s.id+'"'+(_dsigninSel[String(s.id)]?' checked':'')+'></td>'+
      '<td class="dim num">'+_intVal(s.uid,0)+'</td>'+
      '<td class="strong">'+esc(s.account_name||('#'+s.account_id))+'</td>'+
      '<td>'+esc(s.device_name||s.hw_uid||'-')+'</td>'+
      '<td class="dim">'+esc(s.group_name||'-')+'</td>'+
      '<td class="dim">'+fmtDT(s.created_at)+'</td>'+
      '<td><div class="acts"><button class="btn btn-sm btn-primary" data-act="dsignin-approve" data-id="'+s.id+'">'+T('user.approve','批准')+'</button>'+
      '<button class="btn btn-sm btn-danger" data-act="dsignin-reject" data-id="'+s.id+'">'+T('user.reject','拒绝')+'</button></div></td></tr>';
  });
  area.innerHTML='<div id="dsignin-bar">'+dsigninBarHtml()+'</div>'+h+'</tbody></table>'+pg.bar;
  syncDsigninCheckAll();
}
function refreshDeviceSignins(){
  var area=document.getElementById('dsignin-area');
  if(!area)return;
  R.get('/admin/api/device-signins').then(function(d){
    if(d.success===false){area.innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _dsignin=d.items||[];
    // 已被处理掉（别处批过）的条目从选择集里摘掉，避免批量提交带上无效 id
    var live={};_dsignin.forEach(function(s){live[String(s.id)]=1});
    Object.keys(_dsigninSel).forEach(function(k){if(!live[k])delete _dsigninSel[k]});
    _setDsigninDot(d.pending_count||0);
    _pgRender['dsignin']=dsigninRender;
    dsigninRender();
  }).catch(function(){area.innerHTML='<div class="empty">'+T('msg.network_error','网络错误')+'</div>'});
}
/* 单条批准：直接提交，不弹窗、不提示。失败（名额已满、已被别处处理、网络错误）仍旧提示 */
function approveDeviceSignin(id,el){
  btnBusy(el,true);
  R.post('/admin/api/device-signins/'+id+'/approve',{}).then(function(d){
    btnBusy(el,false);
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    refreshDeviceSignins();refreshDevices();checkDeviceSignins();
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
function rejectDeviceSignin(id,el){
  btnBusy(el,true);
  R.post('/admin/api/device-signins/'+id+'/reject',{}).then(function(d){
    btnBusy(el,false);
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    refreshDeviceSignins();checkDeviceSignins();
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 批量：二次确认，且只报数量（不列 id、不给备注栏）；已处理的条目由后端自动跳过 */
function batchDeviceSignins(op){
  var ids=dsigninSelIds();
  if(!ids.length){toast(T('device.need_pick_signin','请先勾选要处理的签入'),'error');return}
  var approve=op==='approve';
  uiConfirm({title:approve?T('user.batch_approve','批量批准'):T('user.batch_reject','批量拒绝'),
    message:T('device.batch_confirm','共 {n} 条设备签入',{n:ids.length}),
    confirmText:approve?T('user.batch_approve','批量批准'):T('user.batch_reject','批量拒绝'),
    danger:!approve}).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/device-signins/batch',{action:op,ids:ids}).then(function(d){
      if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      clearDsigninSel();
      refreshDeviceSignins();refreshDevices();checkDeviceSignins();
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
