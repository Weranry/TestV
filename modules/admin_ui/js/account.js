/* ================= 「我的」页（用户控制台 / 管理面板「我的」分页共用） ================= */
/* 分页切换：概览 / EVkey / 我的设备。纯 DOM 显隐，不走面板那套 .page / switchTab
   ——用户控制台整页没有分页机制，用面板的 tab 的话那边点了什么都不会发生 */
function acctTab(name){
  var tabs=document.querySelectorAll('[data-act="acct-tab"]');
  for(var i=0;i<tabs.length;i++)tabs[i].classList.toggle('on',tabs[i].dataset.tab===name);
  var panes=document.querySelectorAll('.acc-pane');
  for(var j=0;j<panes.length;j++)panes[j].style.display=(panes[j].id==='acct-pane-'+name)?'':'none';
}
/* EVkey 持有上限三态：-1 = 不限，0 = 该组禁止创建，N = 最多 N 个；审批中的申请同样占名额 */
var _keyLimit={max:-1,current:0,pending:0};
function keyFull(){return _keyLimit.max>=0&&_keyLimit.current+_keyLimit.pending>=_keyLimit.max}
function keyLimitNote(){
  var s=T('account.evkey_used','已使用 {n}',{n:_keyLimit.current});
  if(_keyLimit.max>0)s+=' / '+_keyLimit.max;
  else if(_keyLimit.max<0)s+=T('account.evkey_unlimited','（不限）');
  if(_keyLimit.pending)s+=T('account.evkey_pending','（审批中 {n}）',{n:_keyLimit.pending});
  return s;
}
function keyFullMsg(){
  if(_keyLimit.max===0)return T('account.evkey_forbidden_msg','当前用户组不允许创建 EVkey，如需使用请联系管理员调整用户组配额。');
  return T('account.evkey_limit_msg','已持有 {cur}、审批中 {pending}、上限 {max}；请先删除多余的 EVkey。',{cur:_keyLimit.current,pending:_keyLimit.pending,max:_keyLimit.max});
}
/* 已发放的 EVkey 与「审批中」的申请合成一张表、统一分页：一行一种状态，翻页后不会漏看申请。
   审批中的申请也是一行：只回「已提交」四个字的话，用户回到列表里看不到任何东西，
   会以为申请丢了、反复提交（每次提交都占一个名额） */
var _keyItems=[],_KEY_PER=5;
function keyRowHtml(k){
  var on=!!k.enabled;
  return '<tr><td class="mono">'+esc(k.evkey)+'</td><td class="dim">'+esc(k.description||'-')+'</td>'+
    '<td class="col-dot">'+dotHtml(on?'dot-on':'dot-off',on?T('prerender.kpi_enabled','启用中'):T('account.state_off','已禁用'))+'</td>'+
    '<td class="dim">'+esc(fmtDT(k.created_at))+'</td>'+
    '<td><div class="acts"><button class="btn btn-sm" data-act="key-copy" data-key="'+esc(k.evkey)+'">'+T('btn.copy','复制')+'</button>'+
    '<button class="btn btn-sm" data-act="key-toggle" data-id="'+k.id+'" data-en="'+(on?'1':'0')+'">'+(on?T('user.disabled','禁用'):T('user.enabled','启用'))+'</button>'+
    '<span class="sep"></span><button class="btn btn-sm btn-danger" data-act="key-del" data-id="'+k.id+'" data-key="'+esc(k.evkey)+'">'+T('btn.delete','删除')+'</button></div></td></tr>';
}
function appRowHtml(a){
  return '<tr><td class="dim">'+T('account.pending_gen','待生成')+'</td><td class="dim">'+esc(a.applicant_note||'-')+'</td>'+
    '<td class="col-dot">'+dotHtml('dot-warn',T('account.key_pending_msg','申请已提交，等待管理员审核'))+'</td>'+
    '<td class="dim">'+esc(fmtDT(a.created_at))+'</td>'+
    '<td><div class="acts"><span class="dim small">'+T('account.state_pending','审批中')+'</span></div></td></tr>';
}
/* 表格指纹：数据与页码都没变就不重建 DOM。轮询会周期性回来重绘整表，行内按钮
   （复制 / 停用 / 删除）若正好在按下与抬起之间被换掉，click 就落不到新节点上，
   表现成「点了没反应」。指纹相同直接返回，顺带省掉一次表格重排 */
var _keysSig=null;
function keysSig(){
  return _keyItems.map(function(it){
    return it.kind==='key'?(it.k.id+':'+(it.k.enabled?1:0)):('a'+it.a.id);
  }).join(',')+'|'+pgPage('my-keys');
}
function keysRender(){
  var t=document.getElementById('keys-table'),bar=document.getElementById('keys-bar');
  if(!t)return;
  var sig=keysSig();
  if(sig===_keysSig)return;
  _keysSig=sig;
  if(!_keyItems.length){
    t.innerHTML='<div class="empty">'+T('user.no_data','暂无数据')+'</div>';
    if(bar)bar.style.display='none';
    return;
  }
  var pg=pgSlice(_keyItems,'my-keys',_KEY_PER);
  var h='<table><thead><tr><th>EVkey</th><th>'+T('user.col_desc','说明')+'</th><th class="col-dot">'+T('user.legend_status','状态')+'</th><th>'+T('prerender.detail_created','创建时间')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(it){h+=it.kind==='key'?keyRowHtml(it.k):appRowHtml(it.a)});
  t.innerHTML=h+'</tbody></table>';
  if(bar){bar.innerHTML=pg.bar;bar.style.display=''}
}
function loadKeys(){
  R.get('/admin/api/my/evkeys').then(function(d){
    var t=document.getElementById('keys-table');
    if(d.success===false){t.innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _keyLimit={max:_intVal(d.max,-1),current:d.current||0,pending:d.pending||0};
    document.getElementById('key-count').textContent=keyLimitNote();
    var btn=document.querySelector('[data-act="key-apply"]');
    if(btn){btn.disabled=keyFull();btn.title=keyFull()?(_keyLimit.max===0?T('account.evkey_no_create','当前用户组不允许创建 EVkey'):T('account.evkey_limit_hit','已达 EVkey 上限，请先删除多余的 EVkey')):''}
    var keys=d.evkeys||[],apps=d.applications||[];
    _keyItems=keys.map(function(k){return {kind:'key',k:k}}).concat(apps.map(function(a){return {kind:'app',a:a}}));
    _pgRender['my-keys']=keysRender;
    keysRender();
  }).catch(function(){toast(T('account.load_keys_failed','加载 EVkey 列表失败'),'error')});
}
function applyKey(btn){
  if(keyFull()){
    alertModal(_keyLimit.max===0?T('account.evkey_cannot','无法创建 EVkey'):T('account.evkey_limit_title','已达 EVkey 上限'),keyFullMsg());
    return;
  }
  var d=document.getElementById('key-desc').value.trim();
  btnBusy(btn,true,T('user.generating','生成中…'));
  R.post('/admin/api/my/evkeys/apply',{description:d}).then(function(r){
    btnBusy(btn,false);
    if(r.success){
      document.getElementById('key-desc').value='';
      if(r.evkey)showSecret(T('account.key_generated','新 EVkey 已生成'),r.evkey);
      else toast(r.message||T('account.key_pending_msg','申请已提交，等待管理员审核'),'success');
      loadKeys();
    }else if(r.code===400&&/上限|不允许创建/.test(r.message||'')){
      alertModal(T('account.evkey_cannot','无法创建 EVkey'),r.message);loadKeys();
    }else toast(r.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function keyToggle(id,enabled,btn){
  btnBusy(btn,true);
  R.put('/admin/api/my/evkeys/'+id,{enabled:enabled}).then(function(d){
    btnBusy(btn,false);
    if(d.success){toast(enabled?T('account.key_enabled','EVkey 已启用'):T('account.key_disabled','EVkey 已禁用'),'success');loadKeys()}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function deleteKey(id){
  uiConfirm({
    title:T('account.del_key_title','删除 EVkey'),
    message:T('user.del_evkey_confirm','删除后使用该 EVkey 的设备将立即失效，且不可恢复。'),
    confirmText:T('btn.delete','删除'),danger:true
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/my/evkeys/'+id).then(function(r){
      if(r.success){toast(T('account.key_deleted','已删除该 EVkey'),'success');loadKeys()}
      else toast(r.message||T('core.op_failed','操作失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
function changePw(btn){
  var p0=document.getElementById('pw0').value,p1=document.getElementById('pw1').value,p2=document.getElementById('pw2').value;
  if(!p0){toast(T('chpass.need_old','请输入当前密码'),'error');return}
  if(!p1||p1.length<6){toast(T('auth.pw_short','密码至少 6 位'),'error');return}
  if(p1!==p2){toast(T('auth.pw_mismatch','两次输入的密码不一致'),'error');return}
  btnBusy(btn,true,T('auth.submitting','提交中…'));
  R.post('/admin/api/auth/change-password',{old_password:p0,password:p1}).then(function(d){
    btnBusy(btn,false);
    if(d.success){
      document.getElementById('pw0').value='';document.getElementById('pw1').value='';document.getElementById('pw2').value='';
      toast(T('account.pw_updated','密码已更新'),'success');
    }else toast(d.message||T('chpass.failed','修改失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 额度记录：8 条一页，无记录时整张卡片隐藏，不占版面 */
var _qlogItems=[],_QLOG_PER=8;
function qlogRender(){
  var box=document.getElementById('qlog-table'),bar=document.getElementById('qlog-bar');
  var pg=pgSlice(_qlogItems,'my-qlog',_QLOG_PER);
  var h='<table><thead><tr><th>'+T('user.col_time','时间')+'</th><th class="col-dot">'+T('core.col_action','操作')+'</th><th class="num">'+T('user.col_amount','数量')+'</th><th>'+T('user.col_period','周期')+'</th><th>'+T('user.col_reason','原因')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(l){
    var n=_intVal(l.amount,0),isGrant=l.action==='grant';
    h+='<tr><td class="dim">'+esc(fmtDT(l.created_at))+'</td>'+
      '<td class="col-dot">'+dotHtml(isGrant?'dot-on':'dot-off',isGrant?T('user.grant','发放'):T('user.reset','重置'))+'</td>'+
      '<td class="num mono">'+esc(isGrant?((n>0?'+':'')+n):'—')+'</td>'+
      '<td class="dim">'+esc(l.period?_periodLabel(l.period):'—')+'</td>'+
      '<td class="dim">'+esc(l.reason||'—')+'</td></tr>';
  });
  box.innerHTML=h+'</tbody></table>';
  document.getElementById('qlog-count').textContent=T('account.count_n','共 {n} 条',{n:_qlogItems.length});
  /* 与他人分页同一套翻页条（位置、文案、按钮完全一致），不再手搓上一页 / 下一页 */
  bar.innerHTML=pg.bar;
  bar.style.display='';
}
_pgRender['my-qlog']=qlogRender;
function loadQuotaLogs(){
  R.get('/admin/api/my/quota/logs?limit=100').then(function(d){
    if(!d||d.success===false)return;
    _qlogItems=d.items||[];
    if(!_qlogItems.length)return;
    document.getElementById('qlog-card').style.display='';
    qlogRender();
  }).catch(function(){});
}
/* 实时用量：只读查询限流器的内存窗口，不消耗额度 */
function loadQuota(){
  R.get('/admin/api/my/quota').then(function(d){
    var el=document.getElementById('quota-usage');
    if(!el)return;
    if(!d||d.success===false){el.innerHTML='';return}
    if(d.enabled===false){el.innerHTML='<div class="stat"><div class="k">'+T('account.live_usage','实时用量')+'</div><div class="v">'+T('account.rate_disabled','限流未启用')+'</div></div>';return}
    function cell(label,used,limit){
      if(!(limit>0))return '<div class="stat"><div class="k">'+esc(label)+'</div><div class="v">'+T('user.unlimited','不限')+'</div></div>';
      return '<div class="stat"><div class="k">'+esc(label)+'</div><div class="v">'+esc(T('user.times','{n}',{n:(used||0)+' / '+limit}))+'</div></div>';
    }
    el.innerHTML=cell(T('account.minute_used','本分钟已用'),d.minute_used,d.per_minute)+cell(d.long_label||T('account.window_used','窗口内已用'),d.long_used,d.long_limit);
  }).catch(function(){});
}
/* 会员：激活码开通的账号带到期日与「到期回落组」，到期由服务端自动归位 */
function todayStr(){
  var off=(TZ_OFFSET===null)?(-new Date().getTimezoneOffset()/60):TZ_OFFSET;
  return new Date(Date.now()+off*3600000).toISOString().substring(0,10);
}
function renderMembership(m){
  var box=document.getElementById('mem-grid'),st=document.getElementById('mem-state');
  m=m||{};
  var exp=m.expires_on||'';
  var fb=m.fallback_group_name||(m.fallback_group_id>0?T('account.group_hash','用户组 #{id}',{id:m.fallback_group_id}):'');
  var left=null;
  /* 两个日期都按 UTC 零点解析，差值就是整天数，不会被本地时区带偏 */
  if(exp)left=Math.round((Date.parse(exp+'T00:00:00Z')-Date.parse(todayStr()+'T00:00:00Z'))/86400000);
  var state,cls;
  if(!exp){state=T('account.valid_forever','永久有效');cls='badge-on'}
  /* 用 !(left>=0)：日期解析失败时 left 是 NaN，同样落到「已过期」，不会显示「剩余 NaN 天」 */
  else if(!(left>=0)){state=T('user.expired','已过期');cls='badge-off'}
  else{state=(left===0?T('account.expires_today','今日到期'):T('account.days_left','剩余 {n} 天',{n:left}));cls='badge-on'}
  st.innerHTML='<span class="badge '+cls+'">'+esc(state)+'</span>';
  var items=[[T('account.member_expires','会员到期'),exp||T('account.valid_forever','永久有效')],[T('account.expire_to','过期后转入'),fb||T('user.no_transfer','不转移')]];
  box.innerHTML=items.map(function(q){
    return '<div class="stat"><div class="k">'+esc(q[0])+'</div><div class="v">'+esc(q[1])+'</div></div>';
  }).join('');
}
function redeemCode(btn){
  var el=document.getElementById('mem-code'),code=(el.value||'').trim();
  if(!code){toast(T('account.need_code','请输入激活码'),'error');return}
  btnBusy(btn,true,T('account.redeeming','激活中…'));
  R.post('/admin/api/my/activation',{code:code}).then(function(d){
    btnBusy(btn,false);
    if(!d.success){toast(d.message||T('account.redeem_failed','激活失败'),'error');return}
    el.value='';
    toast(d.message||T('account.redeem_done','激活成功'),'success');
    /* 用户组与额度都变了，整页数据重新拉一遍 */
    refreshAccount();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function loadMe(){
  R.get('/admin/api/auth/me').then(function(d){
    if(!d.authenticated){window.location.href='/login';return}
    var name=d.user.name||'';
    var gn=(d.group&&d.group.name)||d.user.group_name||'';
    document.getElementById('nav-user-name').textContent=name;
    document.getElementById('group-name').textContent=T('account.group_line','用户组：{name}',{name:gn});
    /* 账号信息卡：uid 是账号的对外编号（登录可用它替代账号名），缺号时显示 -
       （d.user.uid 可能是 0，用 ==null 判定而不是 !uid） */
    var uid=d.user.uid;
    document.getElementById('acct-info').innerHTML=[[T('auth.username','用户名'),name,0],[T('user.groups','用户组'),gn,0],['UID',uid==null?'-':uid,1]].map(function(q){
      return '<span>'+esc(q[0])+'<b'+(q[2]?' class="num"':'')+'>'+esc(q[1])+'</b></span>';
    }).join('');
    renderMembership(d.membership);
    /* 管理组账号（含主管理员）不开放自助激活：核销一张码就是把自己降级到码里写的用户组，
       等于主动交出管理权限（服务端 my/activation 同样是拒绝的），入口直接不摆出来 */
    var act=document.getElementById('mem-activate');
    if(act)act.style.display=d.is_admin?'none':'';

    var g=d.group||{};
    var qs=[[T('account.rate_label','每分钟请求速率'),(g.rate_limit_per_minute>0?T('user.times','{n}',{n:g.rate_limit_per_minute}):T('user.unlimited','不限'))],
            [T('account.quota_label','请求配额'),quotaText(g)],
            [T('user.col_max_evkeys','EVkey 上限'),evkeyLimitText(g.max_evkeys)],
            /* 设备名额：与限额判定同一口径（管理组不限、0 = 禁止绑定），已绑定台数由 /me 一并带回 */
            [T('device.col_count','设备数 / 上限'),(d.device_count==null?'-':num(d.device_count))+' / '+devLimitText(g.max_devices)],
            [T('account.concurrent_label','最大并发渲染'),(g.max_concurrent_renders>0?g.max_concurrent_renders:T('user.unlimited','不限'))]];
    document.getElementById('quota-grid').innerHTML=qs.map(function(q){
      return '<div class="stat"><div class="k">'+esc(q[0])+'</div><div class="v">'+esc(q[1])+'</div></div>';
    }).join('');

    _perms=(d.permissions&&d.permissions.plugins)||[];
    renderPermPlugins();

    var rs=(d.permissions&&d.permissions.routes)||[];
    if(rs.length){
      document.getElementById('perm-routes-wrap').style.display='block';
      document.getElementById('perm-routes').innerHTML=permCards(rs,function(r){return r.path});
    }
  });
}
/* 权限小卡片：大卡片里按可用宽度自动排行列，一行放几个由容器宽度决定。
   每张小卡只放「圆点 + 名称」：圆点绿=启用、灰=禁用，完整状态放 title / 读屏文本 */
var _perms=[],PERM_PAGE=12;
function permCard(p,name){
  var on=!!p.enabled;
  var label=on?T('account.perm_on','已启用'):T('account.perm_off','已禁用');
  return '<div class="perm-card'+(on?'':' off')+'" title="'+esc(name)+' · '+esc(label)+'">'+
    '<i class="perm-dot" aria-hidden="true"></i><span class="name">'+esc(name)+'</span>'+
    '<span class="sr-only">'+esc(label)+'</span></div>';
}
function permCards(items,nameOf){
  return '<div class="perm-grid">'+items.map(function(p){return permCard(p,nameOf(p))}).join('')+'</div>';
}
function renderPermPlugins(){
  var box=document.getElementById('perm-plugins');if(!box)return;
  if(!_perms.length){box.innerHTML='<div class="perm-empty">'+esc(T('user.no_data','暂无数据'))+'</div>';return}
  var pg=pgSlice(_perms,'account-perms',PERM_PAGE);
  box.innerHTML=permCards(pg.rows,function(p){return p.name})+pg.bar;
}
_pgRender['account-perms']=renderPermPlugins;
/* 本页全部数据。管理面板切到「我的」分页与自动刷新都调它 */
function refreshAccount(){
  loadMe();loadKeys();loadQuota();loadQuotaLogs();loadDevices();
}
/* 统一事件委托：动态内容不写内联 onclick。不接管 logout——各页壳自己处理登录态 */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act]'):null;
  if(!el)return;
  switch(el.dataset.act){
    case 'acct-tab':acctTab(el.dataset.tab);break;
    case 'key-apply':applyKey(el);break;
    case 'key-copy':copyText(el.dataset.key||'');break;
    case 'key-toggle':keyToggle(parseInt(el.dataset.id),el.dataset.en!=='1',el);break;
    case 'key-del':deleteKey(parseInt(el.dataset.id));break;
    case 'chpass':changePw(el);break;
    case 'redeem':redeemCode(el);break;
    case 'dev-claim':claimDevice(el);break;
    case 'dev-item':openDeviceModal(parseInt(el.dataset.id,10));break;
  }
});
document.getElementById('key-desc').addEventListener('keydown',function(e){if(e.key==='Enter')applyKey(document.querySelector('[data-act="key-apply"]'))});
document.getElementById('mem-code').addEventListener('keydown',function(e){if(e.key==='Enter')redeemCode(document.querySelector('[data-act="redeem"]'))});
document.getElementById('dev-code').addEventListener('keydown',function(e){if(e.key==='Enter')claimDevice(document.querySelector('[data-act="dev-claim"]'))});
refreshAccount();
/* 审批通过后的新 Key 与实时用量都靠这一拍带出来，不用手动刷新页面。
   面板外壳的节流 tick 已经在刷这一页（见 ADMIN_JS_BOOT 的 __SHELL_TICKS_ACCOUNT），
   那边接管时这里就不重复开；标签页在后台也不刷，用户看不到，只是白占一次请求 */
setInterval(function(){
  if(document.hidden||window.__SHELL_TICKS_ACCOUNT)return;
  loadQuota();loadKeys();
},15000);

/* ================= 我的设备（用户控制台 / 管理面板「我的」分页共用） ================= */
/* 设备卡片直接铺在分页里：卡片只放概览，点卡片进设置弹窗看详情。
   面板与控制台共用同一份 HTML/CSS/JS，不依赖面板那套 data-act 委托 */
var _devItems=[],_devPer=9,_devOpts=null,_devOptsCache={};
/* 设备卡片三行：型号/屏幕 · 最后在线 · 渲染项条数。
   未配对一律「等待设备上线」——认领只绑归属，明文令牌要等设备下次轮询 /device/pair 才换取 */
/* 调色板键 → 展示名；未知键原样返回，避免设备上报新值时就变成空白 */
function paletteLabel(key){
  var names={bw:'account.palette_bw',bwr:'account.palette_bwr',bwy:'account.palette_bwy',
             bwry:'account.palette_bwry','7color':'account.palette_7color'};
  if(!key)return '—';
  return names[key]?T(names[key],key):key;
}
/* 设备默认名 = MAC 去掉分隔符（与后端 create_device 的口径一致）；老档案没名字时也走这里 */
function devMac(d){
  return String((d&&d.hw_uid)||'').replace(/[^0-9A-Za-z]/g,'');
}
/* 卡片上的时间压到「MM-DD HH:MM」：完整年月日在卡片里会把一行撑成两行 */
function devShortDT(value){
  var s=fmtDT(value);
  return s==='-'?s:s.slice(5,16);
}
function devBatteryText(mv){
  return mv>0?(mv/1000).toFixed(2)+' V':'';
}
/* 信号评级：rssi 是负 dBm，越接近 0 越好 */
function devSignalGrade(rssi){
  if(rssi>=-55)return T('account.dev_grade_excellent','优');
  if(rssi>=-67)return T('account.dev_grade_good','良');
  if(rssi>=-75)return T('account.dev_grade_fair','中');
  if(rssi>=-85)return T('account.dev_grade_weak','弱');
  return T('account.dev_grade_poor','差');
}
/* 电量图标：3.3V→0%、4.2V→100%（只用于填充比例与配色，不冒充精确电量） */
function devBatteryPct(mv){
  return mv>0?Math.max(0,Math.min(100,Math.round((mv-3300)/900*100))):0;
}
function devBatteryColor(pct){
  return pct>=60?'var(--green)':pct>=25?'var(--orange)':'var(--red)';
}
function devBatteryIcon(mv){
  var pct=devBatteryPct(mv),fill=Math.max(1.2,pct/100*10.5);
  var tip=T('account.dev_battery','电量')+' '+devBatteryText(mv)+' · '+pct+'%';
  return '<span class="ic" title="'+esc(tip)+'">'+
    '<svg viewBox="0 0 20 12" width="18" height="12" aria-hidden="true">'+
    '<rect x=".6" y=".6" width="15.8" height="10.8" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.2"/>'+
    '<rect x="17.6" y="3.8" width="1.8" height="4.4" rx=".9" fill="currentColor"/>'+
    '<rect x="2.2" y="2.2" width="'+fill.toFixed(1)+'" height="7.6" rx="1.2" fill="'+devBatteryColor(pct)+'"/></svg></span>';
}
/* 信号格：4 格按评级点亮，颜色随强弱从绿到红，与手机上的信号指示器同一种读法 */
function devSignalLevel(rssi){
  if(rssi>=-55)return 4;
  if(rssi>=-67)return 3;
  if(rssi>=-75)return 2;
  return 1; /* 再差也留一格，全空会被误读成「没有信号数据」 */
}
function devSignalColor(rssi){
  if(rssi>=-67)return 'var(--green)';
  if(rssi>=-85)return 'var(--orange)';
  return 'var(--red)';
}
function devSignalIcon(rssi){
  var lvl=devSignalLevel(rssi),color=devSignalColor(rssi);
  var bars=[[0,3.5],[4.5,6],[9,8.5],[13.5,11]];
  var tip=T('account.dev_rssi','信号')+' '+rssi+' dBm · '+devSignalGrade(rssi);
  return '<span class="ic" title="'+esc(tip)+'">'+
    '<svg viewBox="0 0 18 12" width="18" height="12" aria-hidden="true">'+bars.map(function(b,i){
      return '<rect x="'+b[0]+'" y="'+(12-b[1])+'" width="3" height="'+b[1]+'" rx="1" '+
        (i<lvl?'fill="'+color+'"':'fill="currentColor" opacity=".22"')+'/>';
    }).join('')+'</svg></span>';
}
/* 统一状态口径：未认领=等待设备上线，从未上线=离线，报错或超过预计回连 10 分钟=超时 */
function devStatusOf(d){
  if(!d.paired)return {dot:'dot-warn',text:T('account.dev_pending_claim','已认领，等待设备上线')};
  if(!d.last_seen_at)return {dot:'dot-off',text:T('account.dev_status_offline','离线')};
  var late=d.next_refresh_at?Date.now()-Date.parse(d.next_refresh_at):0;
  if(d.last_status==='error'||late>600000)return {dot:'dot-error',text:T('account.dev_status_timeout','超时')};
  return {dot:'dot-on',text:T('account.dev_status_online','在线')};
}
/* 状态点带可见文字：绿=在线、红=超时、灰=离线，读屏与肉眼拿到的是同一句 */
function devStatusHtml(st){
  return '<span class="dv-state">'+dotHtml(st.dot,st.text)+'<span>'+esc(st.text)+'</span></span>';
}
/* 卡片只留四件事：名称（状态点）、电量、下次刷新。详细参数与日志都在设置弹窗里 */
function devItemHtml(d){
  var st=devStatusOf(d);
  var meta=[];
  if(d.battery_mv>0)meta.push('<span class="dev-meta">'+devBatteryIcon(d.battery_mv)+esc(devBatteryText(d.battery_mv))+'</span>');
  if(d.next_refresh_at)meta.push('<span class="dev-meta">'+esc(T('account.dev_next_refresh','下次刷新')+' '+devShortDT(d.next_refresh_at))+'</span>');
  return '<div class="dev-item" data-act="dev-item" data-id="'+d.id+'">'+
    '<div class="t">'+esc(d.name||devMac(d)||('#'+d.id))+devStatusHtml(st)+'</div>'+
    '<div class="m">'+(meta.join('')||'—')+'</div></div>';
}
function devGridRender(){
  var grid=document.getElementById('dev-grid'),bar=document.getElementById('dev-bar');
  if(!grid)return;
  if(!_devItems.length){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1">'+esc(T('user.no_data','暂无数据'))+'</div>';
    if(bar)bar.style.display='none';
    return;
  }
  var pg=pgSlice(_devItems,'my-devices',_devPer);
  grid.innerHTML=pg.rows.map(devItemHtml).join('');
  if(bar){bar.innerHTML=pg.bar;bar.style.display=''}
}
function loadDevices(){
  return R.get('/admin/api/my/devices').then(function(d){
    if(!d||d.success===false)return;
    _devItems=d.devices||[];
    var max=_intVal(d.max,-1),n=_devItems.length;
    var lcnt=document.getElementById('dev-list-count');
    if(lcnt)lcnt.textContent=n?T('account.dev_count','共 {n} 台',{n:n})+(max>0?' / '+max:''):'';
    _pgRender['my-devices']=devGridRender;
    devGridRender();
  }).catch(function(){toast(T('account.dev_load_failed','加载设备列表失败'),'error')});
}
function claimDevice(btn){
  var el=document.getElementById('dev-code'),code=el?String(el.value||'').trim():'';
  /* 只在本地做「是不是 8 位码」的粗校验（带不带连字符都收），规范化与过期判定都在服务端 */
  if(!/^[A-Za-z0-9]{4}-?[A-Za-z0-9]{4}$/.test(code)){toast(T('account.dev_need_code','请输入 8 位配对码'),'error');return}
  btnBusy(btn,true,T('account.dev_claiming','认领中…'));
  R.post('/admin/api/my/devices/claim',{pair_code:code}).then(function(d){
    btnBusy(btn,false);
    if(d&&d.success){
      if(el)el.value='';
      toast(d.message||T('account.dev_claim_ok','设备已认领，正在等待设备上线'),'success');
      loadDevices();
    }else toast((d&&d.message)||T('account.dev_claim_bad','配对码无效或已过期'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* ---------- 设置弹窗 ---------- */
/* 渲染项表单的可选项（插件 → 路由 → 参数 schema）：按设备尺寸过滤，同一设备同一尺寸只拉一次。
   缓存键带上尺寸，设备重新注册换了屏幕也不会拿旧尺寸的路由去套 */
function loadDevOptions(deviceId,sizeKey){
  var key=String(deviceId)+':'+(sizeKey||'');
  if(_devOptsCache[key]){_devOpts=_devOptsCache[key];return Promise.resolve(_devOpts)}
  var url='/admin/api/my/device-options'+(deviceId?'?device_id='+encodeURIComponent(deviceId):'');
  return R.get(url).then(function(d){
    if(d&&d.plugins){_devOptsCache[key]=d;_devOpts=d}
    return _devOpts;
  }).catch(function(){return null});
}
function devPlugin(name){
  var list=(_devOpts&&_devOpts.plugins)||[];
  for(var i=0;i<list.length;i++)if(list[i].name===name)return list[i];
  return null;
}
/* 两项选择也是切换器：白底描边的胶囊，隐藏单选保证 change 事件与保存口径不变 */
function dvSwitchHtml(name,current,items){
  return '<span class="dev-switch">'+items.map(function(it){
    var on=String(current)===it[0];
    return '<label class="dev-switch-btn'+(on?' on':'')+'">'+
      '<input type="radio" name="'+name+'" value="'+it[0]+'"'+(on?' checked':'')+'>'+
      '<span>'+esc(it[1])+'</span></label>';
  }).join('')+'</span>';
}
/* 参数控件按插件声明的 VIEW_ARGS_SCHEMA 生成，不猜类型：enum→select、bool→checkbox、
   int/float→number（带 min/max/step）、其余→text */
function dvFieldHtml(key,spec,val){
  var v=(val===undefined||val===null)?'':String(val);
  if(spec.type==='enum'){
    return '<select class="input" data-dvp="'+esc(key)+'"><option value=""></option>'+
      (spec.options||[]).map(function(o){
        return '<option value="'+esc(o.value)+'"'+(String(o.value)===v?' selected':'')+'>'+esc(o.label)+'</option>';
      }).join('')+'</select>';
  }
  if(spec.type==='bool')return '<input type="checkbox" data-dvp="'+esc(key)+'"'+(v==='true'||v==='1'||v==='on'?' checked':'')+'>';
  var extra='';
  if(spec.type==='int'||spec.type==='float'){
    extra=' type="number" step="'+(spec.type==='float'?'any':'1')+'"'+
      (spec.min!==undefined?' min="'+spec.min+'"':'')+(spec.max!==undefined?' max="'+spec.max+'"':'');
  }
  return '<input class="input"'+extra+' data-dvp="'+esc(key)+'" value="'+esc(v)+'">';
}
function dvTaskHtml(t,idx,state){
  var plugin=devPlugin(t.plugin_name),routes=(plugin&&plugin.routes)||[];
  var route=routes.filter(function(r){return r.path===t.route_path})[0];
  var schema=(plugin&&plugin.schema)||{};
  var single=!!(state&&state.mode==='single');
  var last=!!(state&&idx>=state.tasks.length-1);
  var pluginOpts=((_devOpts&&_devOpts.plugins)||[]).map(function(p){
    return '<option value="'+esc(p.name)+'"'+(p.name===t.plugin_name?' selected':'')+'>'+esc(p.name)+'</option>';
  }).join('');
  /* 旧渲染项 / 设备换过屏幕：当前插件或路由已不在过滤后的清单里，也要让它可见可改 */
  if(t.plugin_name&&!plugin){
    pluginOpts='<option value="'+esc(t.plugin_name)+'" selected>'+
      esc(t.plugin_name+' · '+T('account.dev_task_no_route','该尺寸无可用路由'))+'</option>'+pluginOpts;
  }
  var routeOpts=routes.map(function(r){
    return '<option value="'+esc(r.path)+'"'+(r.path===t.route_path?' selected':'')+'>'+esc(r.name||r.path)+'</option>';
  }).join('');
  if(t.route_path&&!route){
    routeOpts='<option value="'+esc(t.route_path)+'" selected>'+
      esc(t.route_path+' · '+T('account.dev_task_size_mismatch','尺寸不符，请重选'))+'</option>'+routeOpts;
  }
  /* 单图模式用「显示」单选锁定唯一一条；轮播模式用「启用」勾选 + 上下移决定顺序 */
  var h='<div class="dev-task" data-idx="'+idx+'"><div class="dev-task-hd">'+
    '<div class="grow"><input class="input" data-dvf="name" placeholder="'+esc(T('account.dev_task_name','名称'))+'" value="'+esc(t.name||'')+'"></div>'+
    '<div class="acts">'+
      (single
        ?'<label class="dev-pin" title="'+esc(T('account.dev_pin_tip','单图模式下显示这一项'))+'">'+
          '<input type="radio" name="dv-pin" data-dvpin="'+idx+'"'+(state.pin===idx?' checked':'')+'>'+
          esc(T('account.dev_display','显示'))+'</label>'
        :'<button class="btn btn-sm" data-dvact="task-up"'+(!idx?' disabled':'')+'>'+esc(T('account.dev_task_up','上移'))+'</button>'+
         '<button class="btn btn-sm" data-dvact="task-down"'+(last?' disabled':'')+'>'+esc(T('account.dev_task_down','下移'))+'</button>')+
      '<button class="btn btn-sm btn-danger" data-dvact="task-del">'+esc(T('btn.delete','删除'))+'</button>'+
    '</div></div><div class="pick">'+
    '<label>'+esc(T('account.dev_task_plugin','插件'))+'<select class="input" data-dvf="plugin">'+
      '<option value="">'+esc(T('account.dev_task_plugin','插件'))+'</option>'+pluginOpts+'</select></label>'+
    '<label>'+esc(T('account.dev_task_route','路由'))+'<select class="input" data-dvf="route">'+
      '<option value="">'+esc(T('account.dev_task_route','路由'))+'</option>'+routeOpts+'</select></label></div>';
  var keys=Object.keys(schema);
  if(keys.length){
    h+='<div class="dev-params">'+keys.map(function(k){
      var spec=schema[k]||{};
      return '<label class="dev-param"><span>'+esc(spec.label||k)+'</span>'+
        dvFieldHtml(k,spec,t.params?t.params[k]:undefined)+'</label>';
    }).join('')+'</div>';
  }
  if(!single){
    h+='<label class="dev-sw"><input type="checkbox" data-dvf="enabled"'+(t.enabled?' checked':'')+'>'+
      '<span class="dev-sw-track"></span>'+esc(T('account.dev_task_enabled','启用'))+'</label>';
  }
  return h+'</div>';
}
/* 表单 → state：改完没触发 change 的（名称、参数）也要在保存前同步一次 */
function dvReadRow(state,idx,row){
  var t=state.tasks[idx];if(!t||!row)return;
  function val(key){var el=row.querySelector('[data-dvf="'+key+'"]');return el?String(el.value||'').trim():''}
  t.plugin_name=val('plugin');t.route_path=val('route');t.name=val('name');
  t.size=state.sizeKey||t.size||''; /* 尺寸不由表单决定，跟随设备上报值 */
  /* 单图模式没有启用勾选框：缺元素时保持原值，不能当成「取消启用」写回去 */
  var en=row.querySelector('[data-dvf="enabled"]');
  if(en)t.enabled=!!en.checked;
  var plugin=devPlugin(t.plugin_name),schema=(plugin&&plugin.schema)||{},params={};
  var fields=row.querySelectorAll('[data-dvp]');
  for(var i=0;i<fields.length;i++){
    var f=fields[i],key=f.dataset.dvp,spec=schema[key]||{};
    if(f.type==='checkbox'){if(f.checked)params[key]=true;continue}
    var raw=String(f.value||'').trim();
    if(raw==='')continue;
    if(spec.type==='int'||spec.type==='float'){
      var n=spec.type==='int'?parseInt(raw,10):parseFloat(raw);
      if(!isNaN(n))params[key]=n;
    }else params[key]=raw;
  }
  t.params=params;
}
function dvSyncAll(box,state){
  var rows=box.querySelectorAll('.dev-task');
  for(var i=0;i<rows.length;i++)dvReadRow(state,parseInt(rows[i].dataset.idx,10),rows[i]);
}
function dvTasksRender(box,state){
  var wrap=box.querySelector('#dv-tasks');if(!wrap)return;
  var unsupported=!!state.sizeUnsupported;
  wrap.innerHTML=state.tasks.length?state.tasks.map(function(t,i){return dvTaskHtml(t,i,state)}).join('')
    :'<div class="empty">'+esc(unsupported
        ? T('account.dev_size_unsupported','设备上报的屏幕尺寸 {w}×{h} 没有可用的视图尺寸，暂时无法添加渲染项',{w:state.width||0,h:state.height||0})
        : T('user.no_data','暂无数据'))+'</div>';
  var add=box.querySelector('[data-dvact="task-add"]');
  if(add)add.disabled=unsupported;
}
/* 渲染项是多条写入，且顺序由整体 reorder 决定：串行发，避免并发插入拿到错乱的 sort_order */
function dvChain(jobs){
  var p=Promise.resolve({ok:true});
  jobs.forEach(function(job){p=p.then(function(r){return r.ok?job():r})});
  return p;
}
function dvSaveTasks(deviceId,state){
  var ids=[];
  var jobs=[];
  state.removed.forEach(function(rid){
    jobs.push(function(){
      return R.del('/admin/api/my/device-tasks/'+rid).then(function(r){
        return (r&&r.success===false)?{ok:false,message:r.message}:{ok:true};
      });
    });
  });
  state.tasks.forEach(function(t){
    /* 尺寸由服务端按设备上报值推导，这里不再随请求体发送 */
    var body={plugin_name:t.plugin_name,route_path:t.route_path,
              params:t.params||{},name:t.name||'',enabled:!!t.enabled};
    if(t.id){
      jobs.push(function(){
        return R.put('/admin/api/my/device-tasks/'+t.id,body).then(function(r){
          if(r&&r.success===false)return {ok:false,message:r.message};
          ids.push(t.id);return {ok:true};
        });
      });
    }else{
      jobs.push(function(){
        return R.post('/admin/api/my/devices/'+deviceId+'/tasks',body).then(function(r){
          if(!r||r.success===false||!r.task)return {ok:false,message:(r&&r.message)||''};
          ids.push(r.task.id);return {ok:true};
        });
      });
    }
  });
  jobs.push(function(){
    return R.post('/admin/api/my/devices/'+deviceId+'/tasks/reorder',{ids:ids}).then(function(r){
      if(!r||r.success===false)return {ok:false,message:(r&&r.message)||''};
      /* 用 reorder 回传的权威顺序原地刷新 state：新加的项这下才有 id */
      state.tasks=(r.tasks||[]).map(function(x){
        return {id:x.id,name:x.name,plugin_name:x.plugin_name,route_path:x.route_path,
                size:x.size,params:x.params||{},enabled:!!x.enabled};
      });
      state.removed=[];
      return {ok:true};
    });
  });
  return jobs.length?dvChain(jobs):Promise.resolve({ok:true});
}
function dvSave(box,state,d,btn){
  dvSyncAll(box,state);
  for(var i=0;i<state.tasks.length;i++){
    var t=state.tasks[i];
    if(!t.plugin_name||!t.route_path){
      toast(T('account.dev_task_incomplete','请为每条渲染项选择插件与路由'),'error');return;
    }
  }
  /* 单图 = 只启用被点选的那一条；轮播 = 按各条自己的启用勾选 */
  if(state.mode==='single'&&state.tasks.length){
    if(!(state.pin>=0&&state.pin<state.tasks.length))state.pin=0;
    state.tasks.forEach(function(x,idx){x.enabled=(idx===state.pin)});
  }
  var paletteEl=box.querySelector('#dv-palette');
  var body={
    name:String(box.querySelector('#dv-name').value||'').trim(),
    enabled:box.querySelector('#dv-enabled').checked,
    /* 空串 = 跟随设备上报；非空 = 用户主动降级。输出格式恒由服务端推导 */
    palette_override:paletteEl?String(paletteEl.value||''):'',
    timezone:String(box.querySelector('#dv-tz').value||'').trim(),
    carousel_mode:state.mode==='carousel'?state.sw:'sequence'
  };
  if(state.refresh==='daily'){
    var times=String(box.querySelector('#dv-daily').value||'').trim();
    if(times){body.schedule_type='daily';body.daily_times=times}
    /* 原本是 cron 且时刻留空 = 不改排期：保留设备现有表达式，不被顺手改成间隔 */
    else if(state.origSched!=='cron'){
      toast(T('account.dev_sched_invalid','排期配置不合法，请检查间隔与时刻'),'error');return;
    }
  }else{
    var mins=parseInt(box.querySelector('#dv-interval').value,10);
    if(!(mins>0)||mins<state.lowMin||mins>state.highMin){
      toast(T('account.dev_sched_invalid','排期配置不合法，请检查间隔与时刻'),'error');return;
    }
    body.schedule_type='interval';
    body.interval_seconds=mins*60;
  }

  btnBusy(btn,true,T('msg.processing','处理中…'));
  R.put('/admin/api/my/devices/'+d.id,body).then(function(r){
    if(!r||r.success===false)return {ok:false,message:(r&&r.message)||T('account.dev_save_failed','保存失败')};
    return dvSaveTasks(d.id,state);
  }).then(function(r){
    btnBusy(btn,false);
    if(!r||!r.ok){toast((r&&r.message)||T('account.dev_save_failed','保存失败'),'error');return}
    toast(T('account.dev_saved','已保存'),'success');
    dvTasksRender(box,state);
    loadDevices();
  }).catch(function(){
    btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error');
  });
}
function dvUnbind(d,ov){
  var need=d.name||d.hw_uid||String(d.id);
  uiConfirm({
    title:T('account.dev_unbind_title','删除设备'),
    message:T('account.dev_unbind_msg','删除后设备令牌立即失效，需在设备上重新配对；该设备的渲染项也会一并删除。'),
    confirmText:T('account.dev_unbind','解绑并删除'),danger:true,requireText:need
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/my/devices/'+d.id).then(function(r){
      if(r&&r.success){ov.remove();toast(r.message||T('account.dev_unbound','设备已删除'),'success');loadDevices()}
      else toast((r&&r.message)||T('core.op_failed','操作失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
/* 颜色档位超过三项，用「色块」图标切换 + 悬停提示：一排文字标签会把弹窗撑成两行，
   而调色板之间的差别本来就是颜色本身，色块比文字更直观 */
var _dvAutoIcon='<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'+
  '<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.5 2"/></svg>';
/* 调色板图标是圆形色饼：双色对半、三色三等分、七色七等分，
   一块饼直接读出「几种颜色、哪几种」，比一排竖条更接近屏幕上的观感 */
function dvPaletteSwatch(key){
  var map={bw:['#111111','#ffffff'],bwr:['#111111','#ffffff','#e5484d'],
           bwy:['#111111','#ffffff','#f5a623'],bwry:['#111111','#ffffff','#e5484d','#f5a623'],
           '7color':['#111111','#ffffff','#e5484d','#f5a623','#30a46c','#0091ff','#8e4ec6']};
  var list=map[key]||['#111111'],n=list.length,cx=8,cy=8,r=6.2;
  var parts=list.map(function(c,i){
    if(n===1)return '<circle cx="8" cy="8" r="'+r+'" fill="'+c+'"/>';
    var a0=-Math.PI/2+i*2*Math.PI/n,a1=-Math.PI/2+(i+1)*2*Math.PI/n;
    var x0=(cx+r*Math.cos(a0)).toFixed(3),y0=(cy+r*Math.sin(a0)).toFixed(3);
    var x1=(cx+r*Math.cos(a1)).toFixed(3),y1=(cy+r*Math.sin(a1)).toFixed(3);
    return '<path d="M8 8 L'+x0+' '+y0+' A'+r+' '+r+' 0 0 1 '+x1+' '+y1+' Z" fill="'+c+'"/>';
  }).join('');
  return '<svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">'+parts+
    '<circle cx="8" cy="8" r="'+r+'" fill="none" stroke="rgba(0,0,0,.28)"/></svg>';
}
/* 只列颜色数不高于上报值的档位（降级）；空值 = 跟随设备，输出格式恒由服务端推导 */
function dvPaletteHtml(limits,d){
  var colors=limits.palette_colors||{},cur=d.palette_override||'';
  var maxColors=colors[d.palette||'']||0;
  var items=[{key:'',tip:T('account.dev_palette_auto','自动（{name}）',{name:paletteLabel(d.palette)}),icon:_dvAutoIcon}];
  (limits.palettes||['bw','bwr','bwy','bwry','7color']).forEach(function(p){
    var n=colors[p]||0;
    if(maxColors&&n>maxColors&&p!==cur)return;
    items.push({key:p,tip:paletteLabel(p),icon:dvPaletteSwatch(p)});
  });
  return '<input type="hidden" id="dv-palette" value="'+esc(cur)+'">'+
    '<span class="dev-switch">'+items.map(function(it){
      return '<button type="button" class="dev-switch-btn'+(it.key===cur?' on':'')+'" data-dvpal="'+esc(it.key)+'"'+
        ' title="'+esc(it.tip)+'" aria-label="'+esc(it.tip)+'">'+it.icon+'</button>';
    }).join('')+'</span>';
}
function openDeviceModal(id){
  R.get('/admin/api/my/devices/'+id).then(function(d){
    if(!d||d.success===false||!d.id){
      toast((d&&d.message)||T('account.dev_not_found','设备不存在或不属于你'),'error');
      return null;
    }
    /* 路由选项按设备尺寸过滤，必须等详情回来知道 size_key 后再拉；同设备同尺寸走缓存 */
    return loadDevOptions(id,d.size_key||'').then(function(opts){return {d:d,opts:opts||{}}});
  }).then(function(res){
    if(!res)return;
    var d=res.d,opts=res.opts,limits=d.limits||opts.limits||{};
    if(!Array.isArray(opts.plugins))toast(T('account.dev_opts_failed','插件选项加载失败，渲染项暂时无法编辑'),'error');
    var lo=_intVal(limits.min_interval,60),hi=_intVal(limits.max_interval,21600);
    /* 间隔按分钟填：后端存秒，界面只暴露分钟，上下限跟着 config 现算 */
    var lowMin=Math.max(1,Math.ceil(lo/60)),highMin=Math.max(lowMin,Math.floor(hi/60));
    var sizeKey=opts.device_size||d.size_key||'';
    var taskList=(d.tasks||[]).map(function(t){
      return {id:t.id,name:t.name,plugin_name:t.plugin_name,route_path:t.route_path,
              size:t.size,params:t.params||{},enabled:!!t.enabled};
    });
    var enabledRows=taskList.filter(function(t){return t.enabled}).length;
    var state={
      tasks:taskList,
      removed:[],
      sizeKey:sizeKey,
      width:d.width||0,height:d.height||0,
      sizeUnsupported:opts.size_unsupported!==undefined?!!opts.size_unsupported:!sizeKey,
      /* 显示方式由启用条数推导：只启用一条 = 单图，多条 = 轮播 */
      mode:enabledRows>1?'carousel':'single',
      pin:(function(){for(var i=0;i<taskList.length;i++)if(taskList[i].enabled)return i;return 0})(),
      refresh:(d.schedule_type==='daily'||d.schedule_type==='cron')?'daily':'interval',
      sw:d.carousel_mode==='random'?'random':'sequence',
      origSched:d.schedule_type||'interval',
      lowMin:lowMin,highMin:highMin
    };
    var curMin=d.interval_seconds>0?Math.round(d.interval_seconds/60):Math.min(Math.max(5,lowMin),highMin);
    curMin=Math.max(lowMin,Math.min(highMin,curMin));
    var st=devStatusOf(d);
    var title=d.name||devMac(d)||('#'+d.id);
    /* 副标题只放不重复的信息：屏幕尺寸 · 电量 · 信号 · 状态圆点
       （绿在线 / 红超时 / 灰离线）。型号与 MAC 就是设备名本身，标题里已有，
       不再在这里重复一遍 */
    var headMeta=[];
    if(d.width&&d.height)headMeta.push(d.width+'×'+d.height);
    if(d.battery_mv>0)headMeta.push(devBatteryIcon(d.battery_mv)+esc(devBatteryText(d.battery_mv)));
    if(d.rssi)headMeta.push(devSignalIcon(d.rssi)+esc(d.rssi+' dBm'));
    /* 只读参数：上次在线 / 下次刷新（电量、信号已提到副标题） */
    var info=[
      [T('account.dev_last_seen','上次在线'),esc(d.last_seen_at?fmtDT(d.last_seen_at):'—')],
      [T('account.dev_next_refresh','下次刷新'),esc(d.next_refresh_at?fmtDT(d.next_refresh_at):'—')]
    ];

    var h='<h3>'+esc(title)+'</h3>'+
      '<p class="modal-sub dim small">'+(headMeta.length?headMeta.join(' · ')+' · ':'')+devStatusHtml(st)+'</p>'+
      '<div class="acc-tabs">'+
        '<button type="button" class="acc-tab on" data-dvtab="basic">'+esc(T('account.dev_tab_basic','基础'))+'</button>'+
        '<button type="button" class="acc-tab" data-dvtab="display">'+esc(T('account.dev_tab_refresh','刷新'))+'</button>'+
        (d.owner===false?'':'<button type="button" class="acc-tab" data-dvtab="share">'+esc(T('account.dev_tab_share','共享'))+'</button>')+
      '</div>'+
      /* ---- 基础：名称 / 颜色 / 启用 / 只读参数 / 日志 ---- */
      '<div class="dv-pane" data-dvpane="basic">'+
        (d.owner===false?'<div class="sub">'+esc(T('account.dev_shared_by_line','由「{name}」共享给你',{name:d.shared_by_name||'-'}))+'</div>':'')+
        '<label>'+esc(T('account.dev_name','设备名称'))+
          '<input class="input" id="dv-name" value="'+esc(d.name||devMac(d))+'"></label>'+
        '<div class="sub dv-gap">'+esc(T('account.dev_palette_downgrade','颜色'))+'</div>'+
        /* 色板包一层块级容器：否则切换器是行内盒，会和下面的启用开关挤在同一行 */
        '<div>'+dvPaletteHtml(limits,d)+'</div>'+
        '<label class="dev-sw"><input type="checkbox" id="dv-enabled"'+(d.enabled?' checked':'')+'>'+
          '<span class="dev-sw-track"></span>'+esc(T('account.dev_enabled','启用该设备'))+'</label>'+
        '<div class="panel dv-gap"><div class="idline">'+info.map(function(x){
          return '<span>'+esc(x[0])+'<b>'+x[1]+'</b></span>';
        }).join('')+'</div></div>'+
      '</div>'+
      /* ---- 刷新：显示方式 + 刷新方式 + 渲染项（原「刷新」「渲染项」两页合成一页） ---- */
      '<div class="dv-pane" data-dvpane="display" hidden>'+
        '<div class="sub">'+esc(T('account.dev_display','显示'))+'</div>'+
        dvSwitchHtml('dv-mode',state.mode,[
          ['single',T('account.dev_mode_single','单图')],
          ['carousel',T('account.dev_mode_carousel','轮播')]])+
        '<div class="sub dv-gap">'+esc(T('account.dev_tab_refresh','刷新'))+'</div>'+
        dvSwitchHtml('dv-refresh',state.refresh,[
          ['interval',T('account.dev_sched_interval','按间隔')],
          ['daily',T('account.dev_sched_daily','定时')]])+
        '<div id="dv-int-row"><label>'+esc(T('account.dev_interval_min','间隔（分钟）'))+
          '<input class="input" id="dv-interval" type="number" min="'+lowMin+'" max="'+highMin+'" step="1" value="'+curMin+'"></label></div>'+
        '<div id="dv-daily-row" hidden>'+
          '<label>'+esc(T('account.dev_daily_times','时刻'))+
            '<input class="input" id="dv-daily" placeholder="'+esc(T('account.dev_daily_ph','如 08:00 12:00'))+'" value="'+esc(d.daily_times||'')+'"></label>'+
          '<label>'+esc(T('account.dev_tz','时区'))+
            '<input class="input" id="dv-tz" placeholder="'+esc(T('account.dev_tz_ph','留空用站点默认'))+'" value="'+esc(d.timezone||'')+'"></label>'+
          (state.origSched==='cron'?'<div class="sub dv-gap-sm">'+
            esc(T('account.dev_cron_keep','当前排期：Cron {expr}',{expr:d.cron_expr||'-'}))+'</div>':'')+
        '</div>'+
        '<div id="dv-sw-row" hidden>'+
          '<div class="sub dv-gap">'+esc(T('account.dev_switch','切换'))+'</div>'+
          dvSwitchHtml('dv-switch',state.sw,[
            ['sequence',T('account.dev_switch_seq','顺序')],
            ['random',T('account.dev_switch_random','随机')]])+
        '</div>'+
        '<div class="sub dv-gap">'+esc(T('account.dev_tab_tasks','渲染项'))+'</div>'+
        '<div id="dv-tasks"></div>'+
        '<div class="dv-gap"><button class="btn btn-sm" data-dvact="task-add">'+esc(T('account.dev_task_add','添加渲染项'))+'</button></div>'+
      '</div>'+
      /* ---- 共享（仅属主）：添加栏在上，名单在下并留间距 ---- */
      (d.owner===false?'':'<div class="dv-pane" data-dvpane="share" hidden>'+
        '<div class="apply-row">'+
          '<input class="input" id="dv-share" placeholder="'+esc(T('account.dev_share_ph','对方账号 ID 或账号名'))+'" autocomplete="off">'+
          '<button class="btn btn-sm btn-primary" data-dvact="share-add">'+esc(T('account.dev_share_add','共享'))+'</button></div>'+
        '<div id="dv-shares" class="dv-gap"></div></div>')+
      '<div class="modal-actions">'+(d.owner===false?'':'<button class="btn btn-danger" data-dvact="unbind">'+esc(T('account.dev_unbind','解绑并删除'))+'</button>')+
      '<span style="flex:1"></span>'+
      '<button class="btn btn-primary" data-dvact="save">'+esc(T('account.dev_save','保存'))+'</button></div>';

    var ov=openModal(h,'dv-modal');
    var box=ov.querySelector('.modal');
    box.classList.add('dev-modal');
    /* 共享名单就地重绘：新增 / 解除后只换这一块，不整窗刷新（渲染项表单里可能填了一半） */
    function renderShares(list){
      var wrap=box.querySelector('#dv-shares');
      if(!wrap)return;
      if(!list.length){wrap.innerHTML='<div class="sub" style="margin:0">'+esc(T('user.no_data','暂无数据'))+'</div>';return}
      wrap.innerHTML=list.map(function(s){
        return '<div class="dev-share-row"><span class="grow">'+esc(s.account_name||('#'+s.account_id))+'</span>'+
          '<button class="btn btn-sm btn-danger" data-dvact="share-del" data-uid="'+s.account_id+'">'+esc(T('account.dev_share_remove','解除'))+'</button></div>';
      }).join('');
    }
    if(d.owner!==false)renderShares(d.shares||[]);
    /* 页签只切显隐，所有字段都留在 DOM 里，保存时照旧能一次收齐 */
    function showTab(name){
      var i,bs=box.querySelectorAll('[data-dvtab]'),ps=box.querySelectorAll('[data-dvpane]');
      for(i=0;i<bs.length;i++)bs[i].classList.toggle('on',bs[i].dataset.dvtab===name);
      for(i=0;i<ps.length;i++)ps[i].hidden=ps[i].dataset.dvpane!==name;
    }
    /* 模式只切显隐，字段都留在 DOM 里，保存时一次收齐 */
    function syncDisplay(){
      var sw=box.querySelector('#dv-sw-row'),ir=box.querySelector('#dv-int-row'),dr=box.querySelector('#dv-daily-row');
      if(sw)sw.hidden=state.mode!=='carousel';
      if(ir)ir.hidden=state.refresh!=='interval';
      if(dr)dr.hidden=state.refresh!=='daily';
    }
    function firstEnabled(){
      for(var i=0;i<state.tasks.length;i++)if(state.tasks[i].enabled)return i;
      return 0;
    }
    ov.addEventListener('change',function(e){
      var t=e.target;
      if(t.name==='dv-mode'){
        dvSyncAll(box,state);
        state.mode=t.value;
        /* 切到单图：沿用当前启用的第一条；切到轮播：勾选状态保持原样 */
        if(state.mode==='single')state.pin=firstEnabled();
        dvTasksRender(box,state);syncDisplay();return;
      }
      if(t.name==='dv-pin'){state.pin=parseInt(t.dataset.dvpin,10)||0;return}
      if(t.name==='dv-refresh'){state.refresh=t.value;syncDisplay();return}
      if(t.name==='dv-switch'){state.sw=t.value;return}
      var field=t.dataset.dvf,row=t.closest?t.closest('.dev-task'):null;
      if(!field||!row)return;
      /* 换插件等于换一整套路由与参数；换路由可能换参数 schema。尺寸不在这里，由设备决定 */
      if(field!=='plugin'&&field!=='route')return;
      var idx=parseInt(row.dataset.idx,10);
      dvReadRow(state,idx,row);
      var task=state.tasks[idx];
      if(!task)return;
      if(field==='plugin')task.route_path='';
      task.params={};
      dvTasksRender(box,state);
    });
    ov.addEventListener('click',function(e){
      var tab=e.target.closest?e.target.closest('[data-dvtab]'):null;
      if(tab){showTab(tab.dataset.dvtab);return}
      /* 颜色：色块按钮 + 悬停提示，选中值放隐藏域，保存时口径不变 */
      var pal=e.target.closest?e.target.closest('[data-dvpal]'):null;
      if(pal){
        var hidden=box.querySelector('#dv-palette');
        if(hidden)hidden.value=pal.dataset.dvpal||'';
        var opts=box.querySelectorAll('[data-dvpal]');
        for(var i=0;i<opts.length;i++)opts[i].classList.toggle('on',opts[i]===pal);
        return;
      }
      var el=e.target.closest?e.target.closest('[data-dvact]'):null;
      if(!el)return;
      var act=el.dataset.dvact;
      if(act==='save'){dvSave(box,state,d,el);return}
      if(act==='unbind'){dvUnbind(d,ov);return}
      if(act==='share-add'){
        var inp=box.querySelector('#dv-share'),val=inp?String(inp.value||'').trim():'';
        if(!val){toast(T('account.dev_share_need','请输入对方账号 ID 或账号名'),'error');return}
        /* 纯数字按账号 ID 提交，其余按账号名（服务端两种都收） */
        var payload=/^\d+$/.test(val)?{account_id:parseInt(val,10)}:{account_name:val};
        btnBusy(el,true);
        R.post('/admin/api/my/devices/'+d.id+'/shares',payload).then(function(r){
          btnBusy(el,false);
          if(r&&r.success){if(inp)inp.value='';renderShares(r.shares||[]);toast(r.message||T('account.dev_share_done','已共享'),'success')}
          else toast((r&&r.message)||T('account.dev_share_failed','共享失败'),'error');
        }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
        return;
      }
      if(act==='share-del'){
        R.del('/admin/api/my/devices/'+d.id+'/shares/'+el.dataset.uid).then(function(r){
          if(r&&r.success){renderShares(r.shares||[]);toast(r.message||T('account.dev_share_removed','已解除共享'),'success')}
          else toast((r&&r.message)||T('core.op_failed','操作失败'),'error');
        }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
        return;
      }
      if(act==='task-add'){
        if(state.sizeUnsupported)return;
        /* 单图模式新加的条目不抢当前显示位置；列表本来是空的，它就是唯一一条 */
        var on=state.mode==='carousel'||!state.tasks.length;
        state.tasks.push({plugin_name:'',route_path:'',size:state.sizeKey,params:{},enabled:on,name:''});
        if(state.mode==='single'&&on)state.pin=state.tasks.length-1;
        dvTasksRender(box,state);return;
      }
      var row=el.closest('.dev-task');
      if(!row)return;
      var idx=parseInt(row.dataset.idx,10);
      dvReadRow(state,idx,row);
      if(act==='task-del'){
        var gone=state.tasks.splice(idx,1)[0];
        if(gone&&gone.id)state.removed.push(gone.id);
        if(state.mode==='single'&&state.pin>=state.tasks.length)state.pin=Math.max(0,state.tasks.length-1);
      }else{
        var to=act==='task-up'?idx-1:idx+1;
        if(to<0||to>=state.tasks.length)return;
        var tmp=state.tasks[idx];state.tasks[idx]=state.tasks[to];state.tasks[to]=tmp;
        if(state.mode==='single')state.pin=firstEnabled();
      }
      dvTasksRender(box,state);
    });
    syncDisplay();
    dvTasksRender(box,state);
  }).catch(function(){toast(T('account.dev_load_failed','加载设备列表失败'),'error')});
}
