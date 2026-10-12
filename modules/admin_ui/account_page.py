"""「我的」页：用户控制台整页 与 管理面板「我的」分页 共用同一套卡片与脚本。

两边展示的是同一份个人数据（额度 / 会员 / 额度记录 / 权限记录 / 权限 / API Key / 改密），
以前是两份各自实现的界面，改一边忘一边就会出现「用户端和管理端长得不一样」。
卡片（ACCOUNT_CARDS）、样式（ACCOUNT_CSS）、脚本（ACCOUNT_JS）都只此一份：
用户控制台整页引用，管理面板的 #page-account 分页同样引用，管理端少一张「站内信」卡片
（管理端的站内信在概览页）。
"""

# 「我的」页用到的类里，管理面板 CSS 没有的那几个（.grid/.stat/.chips/.sub/.apply-row）
# 连带行内表单的宽度规则一起放在这里，两边共用
ACCOUNT_CSS = r'''
/* ============ 「我的」页共用卡片（用户控制台 / 管理面板「我的」分页） ============ */
/* 宽度不在这里收窄：管理面板其余分页的主体是 main{max-width:1280px}，单独给「我的」页
   设 900px 会让它的卡片比别的分页窄一截。用户控制台的 main 同样是 1280px，两端一致 */
/* 账号信息：一行 label: value 平铺。这里**不要**用 .grid/.stat —— 那是带 ring 的小方块，
   套在卡片里就成了「卡片内套卡片」 */
.idline{display:flex;flex-wrap:wrap;gap:10px 36px;font-size:13px}
.idline>span{color:var(--fg3)}
.idline b{margin-left:8px;font-weight:500;color:var(--fg)}
.idline b.num{font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{padding:16px 20px;border-radius:var(--r-md);box-shadow:var(--ring)}
.stat .k{font-size:12px;color:var(--fg2);margin-bottom:6px}
/* 数值用等宽数字对齐即可：整行改等宽字体会让「不限」「1000 次 / 每月」这类中文混排露出字体切换痕迹 */
.stat .v{font-size:20px;font-weight:600;letter-spacing:-.5px;font-variant-numeric:tabular-nums}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:9999px;font-size:12px;font-weight:500;box-shadow:0 0 0 1px var(--line);color:var(--fg2)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--blue)}
.chip.off{color:var(--fg3);text-decoration:line-through}
.chip.off .dot{background:var(--faint)}
.sub{font-size:12px;color:var(--fg2);margin-bottom:10px}
/* 行内表单：输入框撑满剩余宽度，密码框外面多包一层 .pw（可见切换），一并在这里撑宽 */
.apply-row{display:flex;gap:10px;align-items:center}
.apply-row .input,.apply-row .pw>.input{width:100%}
.apply-row .input{margin-bottom:0}
.apply-row>.pw{flex:1 1 160px;min-width:0}

/* ============ 我的设备：入口卡片 + 页内子视图 ============
   子视图是**纯 DOM 切换**的页内视图，不依赖面板那套 .page / switchTab——
   用户控制台整页没有分页机制，做成 tab 的话那边点进去什么都不会发生 */
.dev-card{cursor:pointer}
.dev-card:hover .card-title h2{color:var(--blue)}
/* 3 列响应式：断点与列数照访客导航页的先例（explore_page）。**不复用上面的 .grid**
   ——那是 auto-fit 的统计小方块，列数由容器宽度决定，这里要的是固定 3 列 */
.dev-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
@media (max-width:900px){.dev-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:560px){.dev-grid{grid-template-columns:1fr}}
.dev-item{padding:14px 16px;border-radius:var(--r-md);box-shadow:var(--ring);cursor:pointer;transition:box-shadow var(--motion-fast)}
.dev-item:hover{box-shadow:var(--card-shadow)}
.dev-item .t{display:flex;align-items:center;gap:8px;font-weight:500;margin-bottom:8px}
.dev-item .m{font-size:12px;color:var(--fg2);line-height:1.7}
.dev-item .m.dim{color:var(--fg3)}
.dev-sec{margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}
.dev-sec:first-of-type{border-top:none;padding-top:0}
.dev-radios{display:flex;gap:18px;flex-wrap:wrap}
.dev-radios label{display:inline-flex;align-items:center;gap:6px;margin:0;font-size:13px;color:var(--fg)}
.dev-check{display:flex!important;align-items:center;gap:8px;margin:16px 0 0!important;font-size:13px;color:var(--fg)!important}
.dev-two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:560px){.dev-two{grid-template-columns:1fr}}
.dev-task{padding:14px 16px;border-radius:var(--r-sm);box-shadow:var(--ring);margin-top:12px}
.dev-task-hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.dev-task-hd .grow{flex:1 1 160px;min-width:0}
.dev-task-hd .grow .input{margin-bottom:0}
.dev-task .acts{display:flex;gap:6px;align-items:center}
.dev-task .pick{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:12px}
@media (max-width:560px){.dev-task .pick{grid-template-columns:1fr}}
.dev-task .pick .input{margin-bottom:0}
.dev-params{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
@media (max-width:560px){.dev-params{grid-template-columns:1fr}}
.dev-param{display:flex!important;flex-direction:column;gap:4px;margin:0!important}
.dev-param>span{font-size:12px;color:var(--fg3)}
.dev-param .input{margin-bottom:0}
/* 共享协作：属主一行一个已共享的账号（名字 + 解除），被共享方只有一行说明 */
.dev-share-row{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:var(--r-sm);box-shadow:var(--ring);margin-top:8px}
.dev-share-row .grow{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
'''

# 卡片列表。管理端与用户端逐字相同，用户端在它前面多插一张「站内信」卡片
ACCOUNT_CARDS = r'''
<div class="card">
  <div class="card-header"><div class="card-title"><h2>{{T:account.info_title}}</h2></div></div>
  <div class="card-body"><div class="idline" id="acct-info"></div></div>
</div>

<div class="card">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.quota_title}}</h2><div class="card-desc">{{T:account.quota_desc}}</div></div>
    <small class="dim" id="group-name"></small>
  </div>
  <div class="card-body"><div class="grid" id="quota-grid"></div><div class="grid" id="quota-usage" style="margin-top:12px"></div></div>
</div>

<div class="card">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.member_title}}</h2></div>
    <small id="mem-state"></small>
  </div>
  <div class="card-body">
    <div class="grid" id="mem-grid"></div>
    <div class="apply-row" id="mem-activate" style="margin-top:14px">
      <input class="input" id="mem-code" placeholder="{{T:account.activation_ph}}" autocomplete="off">
      <button class="btn btn-primary" data-act="redeem">{{T:account.redeem}}</button>
    </div>
  </div>
</div>

<div class="card" id="qlog-card" style="display:none">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.quota_log_title}}</h2>
      <div class="dot-legend">
        <div class="lg-row"><em>{{T:core.col_action}}</em>
          <span class="lg-item" title="{{T:user.legend_grant_tip}}"><i class="dot dot-on"></i>{{T:user.grant}}</span>
          <span class="lg-item" title="{{T:user.legend_reset_tip}}"><i class="dot dot-off"></i>{{T:user.reset}}</span>
        </div>
      </div></div>
    <small class="dim" id="qlog-count"></small>
  </div>
  <div class="card-body">
    <div id="qlog-table"></div>
    <div class="flex" id="qlog-bar" style="justify-content:flex-end;margin-top:12px;display:none"></div>
  </div>
</div>

<div class="card" id="mlog-card" style="display:none">
  <div class="card-header">
    <div class="card-title"><h2>{{T:user.membership_btn}}</h2>
      <div class="dot-legend">
        <div class="lg-row"><em>{{T:prerender.detail_kind}}</em>
          <span class="lg-item" title="{{T:account.legend_admin_tip}}"><i class="dot dot-violet"></i>{{T:account.action_admin}}</span>
          <span class="lg-item" title="{{T:account.legend_code_tip}}"><i class="dot dot-on"></i>{{T:account.action_code}}</span>
          <span class="lg-item" title="{{T:account.legend_expire_tip}}"><i class="dot dot-off"></i>{{T:account.action_expire}}</span>
        </div>
      </div></div>
    <small class="dim" id="mlog-count"></small>
  </div>
  <div class="card-body">
    <div id="mlog-table"></div>
    <div class="flex" id="mlog-bar" style="justify-content:flex-end;margin-top:12px;display:none"></div>
  </div>
</div>

<div class="card cfg">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.perm_title}}</h2><div class="card-desc">{{T:account.perm_desc}}</div></div>
  </div>
  <div class="card-body">
    <div class="sub">{{T:account.perm_plugins}}</div>
    <div class="chips" id="perm-plugins"><span class="dim">{{T:msg.loading}}</span></div>
    <div id="perm-routes-wrap" style="margin-top:18px;display:none">
      <div class="sub">{{T:account.perm_routes}}</div>
      <div class="chips" id="perm-routes"></div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.apikey_title}}</h2><div class="card-desc">{{T:account.apikey_desc}}</div>
      <div class="dot-legend">
        <div class="lg-row"><em>{{T:user.legend_status}}</em>
          <span class="lg-item" title="{{T:account.key_tip_on}}"><i class="dot dot-on"></i>{{T:prerender.kpi_enabled}}</span>
          <span class="lg-item" title="{{T:account.key_tip_off}}"><i class="dot dot-off"></i>{{T:account.state_off}}</span>
          <span class="lg-item" title="{{T:account.key_tip_pending}}"><i class="dot dot-warn"></i>{{T:account.state_pending}}</span>
        </div>
      </div></div>
    <small class="dim" id="key-count"></small>
  </div>
  <div class="card-body">
    <div id="keys-table">{{T:msg.loading}}</div>
    <div id="keys-bar" style="display:none"></div>
  </div>
</div>

<div class="card cfg">
  <div class="card-header"><div class="card-title"><h2>{{T:account.apikey_new_title}}</h2></div></div>
  <div class="card-body">
    <div class="apply-row">
      <input class="input" id="key-desc" placeholder="{{T:account.apikey_note_ph}}" autocomplete="off">
      <button class="btn btn-primary" data-act="key-apply">{{T:account.apikey_gen}}</button>
    </div>
  </div>
</div>

<div class="card cfg">
  <div class="card-header"><div class="card-title"><h2>{{T:account.chpass_title}}</h2></div></div>
  <div class="card-body">
    <div class="apply-row">
      <div class="pw"><input class="input" type="password" id="pw1" placeholder="{{T:account.new_pw_ph}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
      <div class="pw"><input class="input" type="password" id="pw2" placeholder="{{T:reset.confirm_password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
      <button class="btn btn-primary" data-act="chpass">{{T:account.chpass_submit}}</button>
    </div>
  </div>
</div>

<!-- ============ 我的设备：入口卡片 + 页内子视图 ============
     卡片本体也挂 data-act="dev-open"：点整张卡都能进入，不必去瞄那个按钮。
     子视图初始 display:none，靠 devOpen/devClose 与兄弟节点互换显隐 -->
<div class="card dev-card" id="acct-dev-card" data-act="dev-open">
  <div class="card-header">
    <div class="card-title"><h2>{{T:account.dev_title}}</h2><div class="card-desc">{{T:account.dev_desc}}</div></div>
    <small class="dim" id="dev-count"></small>
  </div>
  <div class="card-body">
    <div class="sub" id="dev-summary"></div>
    <div style="margin-top:14px"><button class="btn" data-act="dev-open">{{T:account.dev_manage}}</button></div>
  </div>
</div>

<div id="acct-dev-view" style="display:none">
  <div class="flex" style="align-items:center;gap:12px;margin-bottom:16px">
    <button class="btn btn-sm" data-act="dev-back">{{T:account.dev_back}}</button>
    <h2 style="margin:0;font-size:18px;font-weight:600;letter-spacing:-.4px">{{T:account.dev_title}}</h2>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:account.dev_add_title}}</h2><div class="card-desc">{{T:account.dev_add_desc}}</div></div>
    </div>
    <div class="card-body">
      <div class="apply-row">
        <input class="input" id="dev-code" maxlength="9" placeholder="{{T:account.dev_code_ph}}" autocomplete="off" spellcheck="false">
        <button class="btn btn-primary" data-act="dev-claim">{{T:account.dev_claim}}</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><h2>{{T:account.dev_title}}</h2></div>
      <small class="dim" id="dev-list-count"></small>
    </div>
    <div class="card-body">
      <div class="dev-grid" id="dev-grid"></div>
      <div id="dev-bar" style="display:none"></div>
    </div>
  </div>
</div>
'''

# 页面脚本。依赖各页壳提供的基础件：R / esc / toast / btnBusy / uiConfirm / alertModal /
# showSecret / copyText / fmtDT / TZ_OFFSET / pgSlice。分页器在共享层，两个页壳都注入了它，
# 所以 API Key 列表可以直接用；额度记录与权限记录两张卡仍是自带上一页/下一页的旧写法。
ACCOUNT_JS = r'''/* ================= 「我的」页（用户控制台 / 管理面板「我的」分页共用） ================= */
/* evkey 持有上限三态：-1 = 不限，0 = 该组禁止创建，N = 最多 N 个；审批中的申请同样占名额 */
var _keyLimit={max:-1,current:0,pending:0};
function keyFull(){return _keyLimit.max>=0&&_keyLimit.current+_keyLimit.pending>=_keyLimit.max}
function keyLimitNote(){
  var s=T('account.evkey_used','已使用 {n} 个',{n:_keyLimit.current});
  if(_keyLimit.max>0)s+=' / '+_keyLimit.max;
  else if(_keyLimit.max<0)s+=T('account.evkey_unlimited','（不限）');
  if(_keyLimit.pending)s+=T('account.evkey_pending','（审批中 {n} 个）',{n:_keyLimit.pending});
  return s;
}
function keyFullMsg(){
  if(_keyLimit.max===0)return T('account.evkey_forbidden_msg','当前用户组不允许创建 evkey，如需使用请联系管理员调整用户组配额。');
  return T('account.evkey_limit_msg','已持有 {cur} 个、审批中 {pending} 个，上限 {max} 个。如需继续，请先删除多余的 Key。',{cur:_keyLimit.current,pending:_keyLimit.pending,max:_keyLimit.max});
}
/* 已发放的 Key 与「审批中」的申请合成一张表、统一分页：一行一种状态，翻页后不会漏看申请。
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
    t.innerHTML='<div class="empty">'+T('account.no_keys','还没有 API Key，可在下方申请一个。')+'</div>';
    if(bar)bar.style.display='none';
    return;
  }
  var pg=pgSlice(_keyItems,'my-keys',_KEY_PER);
  var h='<table><thead><tr><th>Key</th><th>'+T('user.col_desc','说明')+'</th><th class="col-dot">'+T('user.legend_status','状态')+'</th><th>'+T('prerender.detail_created','创建时间')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
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
    if(btn){btn.disabled=keyFull();btn.title=keyFull()?(_keyLimit.max===0?T('account.evkey_no_create','当前用户组不允许创建 evkey'):T('account.evkey_limit_hit','已达 evkey 上限，请先删除多余的 Key')):''}
    var keys=d.evkeys||[],apps=d.applications||[];
    _keyItems=keys.map(function(k){return {kind:'key',k:k}}).concat(apps.map(function(a){return {kind:'app',a:a}}));
    _pgRender['my-keys']=keysRender;
    keysRender();
  }).catch(function(){toast(T('account.load_keys_failed','加载 Key 列表失败'),'error')});
}
function applyKey(btn){
  if(keyFull()){
    alertModal(_keyLimit.max===0?T('account.evkey_cannot','无法创建 evkey'):T('account.evkey_limit_title','已达 evkey 上限'),keyFullMsg());
    return;
  }
  var d=document.getElementById('key-desc').value.trim();
  btnBusy(btn,true,T('user.generating','生成中…'));
  R.post('/admin/api/my/evkeys/apply',{description:d}).then(function(r){
    btnBusy(btn,false);
    if(r.success){
      document.getElementById('key-desc').value='';
      if(r.evkey)showSecret(T('account.key_generated','新 API Key 已生成'),r.evkey,T('user.evkey_generated_note','请复制并妥善保存，设备侧使用该 Key 鉴权。'));
      else toast(r.message||T('account.key_pending_msg','申请已提交，等待管理员审核'),'success');
      loadKeys();
    }else if(r.code===400&&/上限|不允许创建/.test(r.message||'')){
      alertModal(T('account.evkey_cannot','无法创建 evkey'),r.message);loadKeys();
    }else toast(r.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function keyToggle(id,enabled,btn){
  btnBusy(btn,true);
  R.put('/admin/api/my/evkeys/'+id,{enabled:enabled}).then(function(d){
    btnBusy(btn,false);
    if(d.success){toast(enabled?T('account.key_enabled','Key 已启用'):T('account.key_disabled','Key 已禁用'),'success');loadKeys()}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function deleteKey(id){
  uiConfirm({
    title:T('account.del_key_title','删除 API Key'),
    message:T('user.del_evkey_confirm','删除后使用该 Key 的设备将立即失效，且不可恢复。'),
    confirmText:T('btn.delete','删除'),danger:true
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/my/evkeys/'+id).then(function(r){
      if(r.success){toast(T('account.key_deleted','已删除该 Key'),'success');loadKeys()}
      else toast(r.message||T('core.op_failed','操作失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
function changePw(btn){
  var p1=document.getElementById('pw1').value,p2=document.getElementById('pw2').value;
  if(!p1||p1.length<6){toast(T('auth.pw_short','密码至少 6 位'),'error');return}
  if(p1!==p2){toast(T('auth.pw_mismatch','两次输入的密码不一致'),'error');return}
  btnBusy(btn,true,T('auth.submitting','提交中…'));
  R.post('/admin/api/auth/change-password',{password:p1}).then(function(d){
    btnBusy(btn,false);
    if(d.success){
      document.getElementById('pw1').value='';document.getElementById('pw2').value='';
      toast(T('account.pw_updated','密码已更新'),'success');
    }else toast(d.message||T('chpass.failed','修改失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 额度记录：8 条一页，无记录时整张卡片隐藏，不占版面 */
var _qlogItems=[],_qlogPage=1,_QLOG_PER=8;
function qlogRender(){
  var box=document.getElementById('qlog-table'),bar=document.getElementById('qlog-bar');
  var tp=Math.max(1,Math.ceil(_qlogItems.length/_QLOG_PER));
  if(_qlogPage>tp)_qlogPage=tp;
  var h='<table><thead><tr><th>'+T('user.col_time','时间')+'</th><th class="col-dot">'+T('core.col_action','操作')+'</th><th class="num">'+T('user.col_amount','数量')+'</th><th>'+T('user.col_period','周期')+'</th><th>'+T('user.col_reason','原因')+'</th></tr></thead><tbody>';
  _qlogItems.slice((_qlogPage-1)*_QLOG_PER,_qlogPage*_QLOG_PER).forEach(function(l){
    var n=_intVal(l.amount,0),isGrant=l.action==='grant';
    h+='<tr><td class="dim">'+esc(fmtDT(l.created_at))+'</td>'+
      '<td class="col-dot">'+dotHtml(isGrant?'dot-on':'dot-off',isGrant?T('user.grant','发放'):T('user.reset','重置'))+'</td>'+
      '<td class="num mono">'+esc(isGrant?((n>0?'+':'')+n):'—')+'</td>'+
      '<td class="dim">'+esc(l.period?_periodLabel(l.period):'—')+'</td>'+
      '<td class="dim">'+esc(l.reason||'—')+'</td></tr>';
  });
  box.innerHTML=h+'</tbody></table>';
  document.getElementById('qlog-count').textContent=T('account.count_n','共 {n} 条',{n:_qlogItems.length});
  if(_qlogItems.length>_QLOG_PER){
    bar.style.display='flex';
    bar.innerHTML='<button class="btn btn-sm" data-act="qlog-prev"'+(_qlogPage<=1?' disabled':'')+'>'+T('pager.prev','上一页')+'</button>'+
      '<span class="dim small">'+T('account.page_of','{cur} / {total} 页',{cur:_qlogPage,total:tp})+'</span>'+
      '<button class="btn btn-sm" data-act="qlog-next"'+(_qlogPage>=tp?' disabled':'')+'>'+T('pager.next','下一页')+'</button>';
  }else bar.style.display='none';
}
function loadQuotaLogs(){
  R.get('/admin/api/my/quota/logs?limit=100').then(function(d){
    if(!d||d.success===false)return;
    _qlogItems=d.items||[];
    if(!_qlogItems.length)return;
    document.getElementById('qlog-card').style.display='';
    qlogRender();
  }).catch(function(){});
}
function _qlogTurn(dir){
  var tp=Math.max(1,Math.ceil(_qlogItems.length/_QLOG_PER));
  var p=_qlogPage+dir;
  if(p<1||p>tp)return;
  _qlogPage=p;
  qlogRender();
}
/* 权限记录：8 条一页，无记录时整张卡片隐藏（表体由共享的 memberLogRows 渲染） */
var _mlogItems=[],_mlogPage=1,_MLOG_PER=8;
function mlogRender(){
  var box=document.getElementById('mlog-table'),bar=document.getElementById('mlog-bar');
  var tp=Math.max(1,Math.ceil(_mlogItems.length/_MLOG_PER));
  if(_mlogPage>tp)_mlogPage=tp;
  box.innerHTML=memberLogRows(_mlogItems.slice((_mlogPage-1)*_MLOG_PER,_mlogPage*_MLOG_PER));
  document.getElementById('mlog-count').textContent=T('account.count_n','共 {n} 条',{n:_mlogItems.length});
  if(_mlogItems.length>_MLOG_PER){
    bar.style.display='flex';
    bar.innerHTML='<button class="btn btn-sm" data-act="mlog-prev"'+(_mlogPage<=1?' disabled':'')+'>'+T('pager.prev','上一页')+'</button>'+
      '<span class="dim small">'+T('account.page_of','{cur} / {total} 页',{cur:_mlogPage,total:tp})+'</span>'+
      '<button class="btn btn-sm" data-act="mlog-next"'+(_mlogPage>=tp?' disabled':'')+'>'+T('pager.next','下一页')+'</button>';
  }else bar.style.display='none';
}
function loadMembershipLogs(){
  R.get('/admin/api/my/membership-logs?limit=100').then(function(d){
    if(!d||d.success===false)return;
    _mlogItems=d.items||[];
    if(!_mlogItems.length)return;
    document.getElementById('mlog-card').style.display='';
    mlogRender();
  }).catch(function(){});
}
function _mlogTurn(dir){
  var tp=Math.max(1,Math.ceil(_mlogItems.length/_MLOG_PER));
  var p=_mlogPage+dir;
  if(p<1||p>tp)return;
  _mlogPage=p;
  mlogRender();
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
            [T('user.col_max_evkeys','evkey 上限'),evkeyLimitText(g.max_evkeys)],
            [T('account.concurrent_label','最大并发渲染'),(g.max_concurrent_renders>0?g.max_concurrent_renders:T('user.unlimited','不限'))]];
    document.getElementById('quota-grid').innerHTML=qs.map(function(q){
      return '<div class="stat"><div class="k">'+esc(q[0])+'</div><div class="v">'+esc(q[1])+'</div></div>';
    }).join('');

    var ps=(d.permissions&&d.permissions.plugins)||[];
    document.getElementById('perm-plugins').innerHTML=ps.length?ps.map(function(p){
      return '<span class="chip'+(p.enabled?'':' off')+'"><span class="dot"></span>'+esc(p.name)+'</span>';
    }).join(''):'<span class="dim">'+T('account.no_plugins','暂无插件')+'</span>';

    var rs=(d.permissions&&d.permissions.routes)||[];
    if(rs.length){
      document.getElementById('perm-routes-wrap').style.display='block';
      document.getElementById('perm-routes').innerHTML=rs.map(function(r){
        return '<span class="chip'+(r.enabled?'':' off')+'"><span class="dot"></span>'+esc(r.path)+'</span>';
      }).join('');
    }
  });
}
/* 本页全部数据。管理面板切到「我的」分页与自动刷新都调它 */
function refreshAccount(){
  loadMe();loadKeys();loadQuota();loadQuotaLogs();loadMembershipLogs();loadDevices();
}
/* 统一事件委托：动态内容不写内联 onclick。不接管 logout——各页壳自己处理登录态 */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act]'):null;
  if(!el)return;
  switch(el.dataset.act){
    case 'key-apply':applyKey(el);break;
    case 'key-copy':copyText(el.dataset.key||'');break;
    case 'key-toggle':keyToggle(parseInt(el.dataset.id),el.dataset.en!=='1',el);break;
    case 'key-del':deleteKey(parseInt(el.dataset.id));break;
    case 'chpass':changePw(el);break;
    case 'redeem':redeemCode(el);break;
    case 'qlog-prev':_qlogTurn(-1);break;
    case 'qlog-next':_qlogTurn(1);break;
    case 'mlog-prev':_mlogTurn(-1);break;
    case 'mlog-next':_mlogTurn(1);break;
    case 'dev-open':devOpen();break;
    case 'dev-back':devClose();break;
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
/* 子视图是**页内 DOM 切换**，不走面板那套 .page / switchTab：用户控制台整页没有分页机制，
   做成 tab 的话那边点进去什么都不会发生。#acct-dev-view 的父节点在两个页壳里并不相同
   （面板是 #page-account、控制台是 main，后者还多一张 #ann-card 与站内信卡），
   所以逐个把原 display 记到 dataset._d 再还原——统一置空会把本该隐藏的卡片也亮出来 */
var _devItems=[],_devPer=9,_devOpts=null;
function devOpen(){
  var view=document.getElementById('acct-dev-view');if(!view)return;
  var box=view.parentNode,i,el;
  for(i=0;i<box.children.length;i++){
    el=box.children[i];if(el===view)continue;
    if(el.dataset._d===undefined)el.dataset._d=el.style.display||'';
    el.style.display='none';
  }
  view.style.display='';
  loadDevices();
  el=document.getElementById('dev-code');if(el)try{el.focus()}catch(e){}
}
function devClose(){
  var view=document.getElementById('acct-dev-view');if(!view)return;
  var box=view.parentNode,i,el;
  for(i=0;i<box.children.length;i++){
    el=box.children[i];if(el===view)continue;
    if(el.dataset._d!==undefined){el.style.display=el.dataset._d;delete el.dataset._d}
  }
  view.style.display='none';
}
/* 设备卡片三行：型号/屏幕 · 最后在线 · 渲染项条数。
   未配对一律「等待设备上线」——认领只绑归属，明文令牌要等设备下次轮询 /device/pair 才换取 */
function devItemHtml(d){
  var dot,status;
  if(!d.paired){dot='dot-warn';status=T('account.dev_pending_claim','已认领，等待设备上线')}
  else if(d.last_seen_at){dot='dot-on';status=T('account.dev_status_online','在线')}
  else{dot='dot-off';status=T('account.dev_status_offline','离线')}
  var spec=[];
  if(d.model)spec.push(d.model);
  if(d.width&&d.height)spec.push(d.width+'×'+d.height);
  var last=d.last_seen_at?fmtDT(d.last_seen_at):T('account.dev_never','从未上线');
  return '<div class="dev-item" data-act="dev-item" data-id="'+d.id+'">'+
    '<div class="t">'+esc(d.name||d.model||('#'+d.id))+dotHtml(dot,status)+'</div>'+
    '<div class="m">'+esc(spec.join(' · ')||'—')+'</div>'+
    '<div class="m dim">'+esc(T('account.dev_last_seen','最后在线')+'：'+last)+'</div>'+
    '<div class="m dim">'+esc(T('account.dev_tasks_title','渲染项')+'：'+(d.task_count||0))+'</div></div>';
}
function devGridRender(){
  var grid=document.getElementById('dev-grid'),bar=document.getElementById('dev-bar');
  if(!grid)return;
  if(!_devItems.length){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1">'+esc(T('account.dev_empty_hint','在设备上查看 8 位配对码，输入后即可认领'))+'</div>';
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
    var cnt=document.getElementById('dev-count');
    if(cnt)cnt.textContent=T('account.dev_count','共 {n} 台',{n:n})+(max>0?' / '+max:'');
    var lcnt=document.getElementById('dev-list-count');
    if(lcnt)lcnt.textContent=n?T('account.dev_count','共 {n} 台',{n:n}):'';
    var sum=document.getElementById('dev-summary');
    if(sum)sum.textContent=n?_devItems.map(function(x){return x.name||x.hw_uid||('#'+x.id)}).join('、'):T('account.dev_none','还没有设备');
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
/* 渲染项表单的可选项（插件 → 路由 → 尺寸 → 参数 schema）：一个会话里插件不会变，拉一次就缓存 */
function loadDevOptions(){
  if(_devOpts)return Promise.resolve(_devOpts);
  return R.get('/admin/api/my/device-options').then(function(d){
    if(d&&d.plugins)_devOpts=d;
    return _devOpts;
  }).catch(function(){return null});
}
function devPlugin(name){
  var list=(_devOpts&&_devOpts.plugins)||[];
  for(var i=0;i<list.length;i++)if(list[i].name===name)return list[i];
  return null;
}
function dvRadio(name,value,current,label){
  return '<label><input type="radio" name="'+name+'" value="'+value+'"'+(String(current)===value?' checked':'')+'>'+esc(label)+'</label>';
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
function dvTaskHtml(t,idx){
  var plugin=devPlugin(t.plugin_name),routes=(plugin&&plugin.routes)||[];
  var route=routes.filter(function(r){return r.path===t.route_path})[0];
  var sizes=(route&&route.sizes)||[],schema=(plugin&&plugin.schema)||{};
  var h='<div class="dev-task" data-idx="'+idx+'"><div class="dev-task-hd">'+
    '<div class="grow"><input class="input" data-dvf="name" placeholder="'+esc(T('account.dev_task_name','名称'))+'" value="'+esc(t.name||'')+'"></div>'+
    '<div class="acts">'+
      '<button class="btn btn-sm" data-dvact="task-up"'+(!idx?' disabled':'')+'>'+esc(T('account.dev_task_up','上移'))+'</button>'+
      '<button class="btn btn-sm" data-dvact="task-down">'+esc(T('account.dev_task_down','下移'))+'</button>'+
      '<button class="btn btn-sm btn-danger" data-dvact="task-del">'+esc(T('btn.delete','删除'))+'</button>'+
    '</div></div><div class="pick">'+
    '<select class="input" data-dvf="plugin"><option value="">'+esc(T('account.dev_task_plugin','插件'))+'</option>'+
      ((_devOpts&&_devOpts.plugins)||[]).map(function(p){
        return '<option value="'+esc(p.name)+'"'+(p.name===t.plugin_name?' selected':'')+'>'+esc(p.name)+'</option>';
      }).join('')+'</select>'+
    '<select class="input" data-dvf="route"><option value="">'+esc(T('account.dev_task_route','路由'))+'</option>'+
      routes.map(function(r){
        return '<option value="'+esc(r.path)+'"'+(r.path===t.route_path?' selected':'')+'>'+esc(r.name||r.path)+'</option>';
      }).join('')+'</select>'+
    '<select class="input" data-dvf="size"><option value="">'+esc(T('account.dev_task_size','尺寸'))+'</option>'+
      sizes.map(function(s){
        return '<option value="'+s+'"'+(s===t.size?' selected':'')+'>'+esc(s)+'</option>';
      }).join('')+'</select></div>';
  var keys=Object.keys(schema);
  if(keys.length){
    h+='<div class="dev-params">'+keys.map(function(k){
      var spec=schema[k]||{};
      return '<label class="dev-param"><span>'+esc(spec.label||k)+'</span>'+
        dvFieldHtml(k,spec,t.params?t.params[k]:undefined)+'</label>';
    }).join('')+'</div>';
  }
  return h+'<label class="dev-check"><input type="checkbox" data-dvf="enabled"'+(t.enabled?' checked':'')+'>'+
    esc(T('account.dev_task_enabled','启用'))+'</label></div>';
}
/* 表单 → state：改完没触发 change 的（名称、参数）也要在保存前同步一次 */
function dvReadRow(state,idx,row){
  var t=state.tasks[idx];if(!t||!row)return;
  function val(key){var el=row.querySelector('[data-dvf="'+key+'"]');return el?String(el.value||'').trim():''}
  t.plugin_name=val('plugin');t.route_path=val('route');t.size=val('size');t.name=val('name');
  var en=row.querySelector('[data-dvf="enabled"]');t.enabled=!!(en&&en.checked);
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
  wrap.innerHTML=state.tasks.length?state.tasks.map(dvTaskHtml).join('')
    :'<div class="empty">'+esc(T('account.dev_task_none','还没有渲染项，添加一条后设备才有内容可显示'))+'</div>';
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
    var body={plugin_name:t.plugin_name,route_path:t.route_path,size:t.size,
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
    if(!t.plugin_name||!t.route_path||!t.size){
      toast(T('account.dev_task_incomplete','请选择插件 / 路由 / 尺寸'),'error');return;
    }
  }
  var picked=box.querySelector('input[name="dv-sched"]:checked');
  var kind=picked?picked.value:'interval';
  var body={
    name:String(box.querySelector('#dv-name').value||'').trim(),
    enabled:box.querySelector('#dv-enabled').checked,
    timezone:String(box.querySelector('#dv-tz').value||'').trim(),
    schedule_type:kind
  };
  if(kind==='interval')body.interval_seconds=parseInt(box.querySelector('#dv-interval').value,10)||0;
  else if(kind==='daily')body.daily_times=String(box.querySelector('#dv-daily').value||'').trim();
  else body.cron_expr=String(box.querySelector('#dv-cron').value||'').trim();

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
function openDeviceModal(id){
  Promise.all([R.get('/admin/api/my/devices/'+id),loadDevOptions()]).then(function(res){
    var d=res[0];
    if(!d||d.success===false||!d.id){toast((d&&d.message)||T('account.dev_not_found','设备不存在或不属于你'),'error');return}
    var limits=d.limits||{},lo=_intVal(limits.min_interval,60),hi=_intVal(limits.max_interval,21600);
    var state={
      tasks:(d.tasks||[]).map(function(t){
        return {id:t.id,name:t.name,plugin_name:t.plugin_name,route_path:t.route_path,
                size:t.size,params:t.params||{},enabled:!!t.enabled};
      }),
      removed:[]
    };
    var meta=[];
    if(d.model)meta.push(T('account.dev_model','型号')+'：'+d.model);
    if(d.width&&d.height)meta.push(T('account.dev_screen','屏幕')+'：'+d.width+'×'+d.height);
    if(d.hw_uid)meta.push(T('account.dev_hw_uid','硬件标识')+'：'+d.hw_uid);
    meta.push(T('account.dev_last_seen','最后在线')+'：'+(d.last_seen_at?fmtDT(d.last_seen_at):T('account.dev_never','从未上线')));

    var h='<h3>'+esc(T('account.dev_modal_title','设备设置'))+'</h3>'+
      '<div class="modal-sub dim small">'+esc(d.name||d.hw_uid||('#'+d.id))+'</div>'+
      /* 1) 基础信息 */
      '<div class="dev-sec"><label>'+esc(T('account.dev_name','设备名称'))+'</label>'+
      '<input class="input" id="dv-name" placeholder="'+esc(T('account.dev_name_ph','给这台设备取个名字'))+'" value="'+esc(d.name||'')+'">'+
      '<div class="dev-two"><label>'+esc(T('account.dev_palette','调色板'))+
      '<input class="input" id="dv-palette" value="'+esc(d.palette||'bw')+'" readonly></label>'+
      '<label>'+esc(T('account.dev_format','输出格式'))+
      '<input class="input" id="dv-format" value="'+esc(d.format||'array')+'" readonly></label></div>'+
      '<div class="sub" style="margin-top:6px">'+esc(T('account.dev_color_auto','调色板与输出格式由设备上报的颜色自动确定'))+'</div>'+
      '<label class="dev-check"><input type="checkbox" id="dv-enabled"'+(d.enabled?' checked':'')+'>'+esc(T('account.dev_enabled','启用该设备'))+'</label>'+
      '<div class="sub" style="margin-top:14px">'+meta.map(esc).join('<br>')+'</div></div>'+
      /* 1.5) 共享协作：属主可增删共享账号；被共享方只显示「由 XX 共享」一行。
         共享关系只在这个详情弹窗里出现，设备卡片上不标（用户要求） */
      '<div class="dev-sec"><label>'+esc(T('account.dev_share_title','共享协作'))+'</label>'+
      (d.owner===false
        ? '<div class="sub" style="margin:0">'+esc(T('account.dev_shared_by_line','这台设备由「{name}」共享给你协作，可共同编辑设置与渲染项，但不能删除设备。',{name:d.shared_by_name||'-'}))+'</div>'
        : '<div class="sub">'+esc(T('account.dev_share_desc','输入对方账号 ID 或账号名共享这台设备，对方即可共同编辑设置与渲染项。'))+'</div>'+
          '<div id="dv-shares"></div>'+
          '<div class="apply-row" style="margin-top:10px">'+
          '<input class="input" id="dv-share" placeholder="'+esc(T('account.dev_share_ph','对方账号 ID 或账号名'))+'" autocomplete="off">'+
          '<button class="btn btn-sm btn-primary" data-dvact="share-add">'+esc(T('account.dev_share_add','共享'))+'</button></div>')+
      '</div>'+
      /* 2) 刷新策略（间隔 / 每日时刻 / cron 三选一；权威校验在服务端） */
      '<div class="dev-sec"><label>'+esc(T('account.dev_schedule_title','刷新策略'))+'</label>'+
      '<div class="dev-radios">'+
        dvRadio('dv-sched','interval',d.schedule_type,T('account.dev_sched_interval','按间隔'))+
        dvRadio('dv-sched','daily',d.schedule_type,T('account.dev_sched_daily','每日时刻'))+
        dvRadio('dv-sched','cron',d.schedule_type,T('account.dev_sched_cron','Cron 表达式'))+
      '</div>'+
      '<div id="dv-sched-interval"><label>'+esc(T('account.dev_interval_sec','间隔（秒）'))+'</label>'+
      '<input class="input" id="dv-interval" type="number" min="'+lo+'" max="'+hi+'" value="'+(d.interval_seconds||lo)+'">'+
      '<div class="sub">'+esc(T('account.dev_interval_hint','可填 {min}–{max} 秒',{min:lo,max:hi}))+'</div></div>'+
      '<div id="dv-sched-daily"><label>'+esc(T('account.dev_sched_daily','每日时刻'))+'</label>'+
      '<input class="input" id="dv-daily" placeholder="'+esc(T('account.dev_daily_ph','如 08:00 12:00'))+'" value="'+esc(d.daily_times||'')+'"></div>'+
      '<div id="dv-sched-cron"><label>'+esc(T('account.dev_cron_expr','Cron 表达式（5 段）'))+'</label>'+
      '<input class="input" id="dv-cron" placeholder="'+esc(T('account.dev_cron_ph','如 0 8 * * *'))+'" value="'+esc(d.cron_expr||'')+'"></div>'+
      '<label>'+esc(T('account.dev_tz','时区'))+'</label>'+
      '<input class="input" id="dv-tz" placeholder="'+esc(T('account.dev_tz_ph','留空用站点默认'))+'" value="'+esc(d.timezone||'')+'"></div>'+
      /* 3) 渲染项 */
      '<div class="dev-sec"><label>'+esc(T('account.dev_tasks_title','渲染项'))+'</label>'+
      '<div class="sub">'+esc(T('account.dev_tasks_desc','设备按排序取第一条可用项渲染'))+'</div>'+
      '<div id="dv-tasks"></div>'+
      '<div style="margin-top:12px"><button class="btn btn-sm" data-dvact="task-add">'+esc(T('account.dev_task_add','添加渲染项'))+'</button></div></div>'+
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
      if(!list.length){wrap.innerHTML='<div class="sub" style="margin:0">'+esc(T('account.dev_share_none','尚未共享给任何人'))+'</div>';return}
      wrap.innerHTML=list.map(function(s){
        return '<div class="dev-share-row"><span class="grow">'+esc(s.account_name||('#'+s.account_id))+'</span>'+
          '<button class="btn btn-sm btn-danger" data-dvact="share-del" data-uid="'+s.account_id+'">'+esc(T('account.dev_share_remove','解除'))+'</button></div>';
      }).join('');
    }
    if(d.owner!==false)renderShares(d.shares||[]);
    /* 弹窗内的按钮一律在 ov 上局部绑定，不走全局 data-act 委托：用户控制台页没有面板那套
       委托（showSecret 的注释就是踩过这个坑），靠委托的话那边点了没反应 */
    function syncSched(){
      var pick=box.querySelector('input[name="dv-sched"]:checked');
      var kind=pick?pick.value:'interval';
      box.querySelector('#dv-sched-interval').style.display=kind==='interval'?'':'none';
      box.querySelector('#dv-sched-daily').style.display=kind==='daily'?'':'none';
      box.querySelector('#dv-sched-cron').style.display=kind==='cron'?'':'none';
    }
    ov.addEventListener('change',function(e){
      var t=e.target;
      if(t.name==='dv-sched'){syncSched();return}
      var field=t.dataset.dvf,row=t.closest?t.closest('.dev-task'):null;
      if(!field||!row)return;
      /* 换插件等于换一整套路由与参数，换路由等于换尺寸：都得先落盘再重绘这一行 */
      if(field!=='plugin'&&field!=='route')return;
      var idx=parseInt(row.dataset.idx,10);
      dvReadRow(state,idx,row);
      var task=state.tasks[idx];
      if(!task)return;
      if(field==='plugin'){task.route_path='';task.size='';task.params={}}
      else task.size='';
      dvTasksRender(box,state);
    });
    ov.addEventListener('click',function(e){
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
        state.tasks.push({plugin_name:'',route_path:'',size:'',params:{},enabled:true,name:''});
        dvTasksRender(box,state);return;
      }
      var row=el.closest('.dev-task');
      if(!row)return;
      var idx=parseInt(row.dataset.idx,10);
      dvReadRow(state,idx,row);
      if(act==='task-del'){
        var gone=state.tasks.splice(idx,1)[0];
        if(gone&&gone.id)state.removed.push(gone.id);
      }else{
        var to=act==='task-up'?idx-1:idx+1;
        if(to<0||to>=state.tasks.length)return;
        var tmp=state.tasks[idx];state.tasks[idx]=state.tasks[to];state.tasks[to]=tmp;
      }
      dvTasksRender(box,state);
    });
    syncSched();
    dvTasksRender(box,state);
  }).catch(function(){toast(T('account.dev_load_failed','加载设备列表失败'),'error')});
}
'''

