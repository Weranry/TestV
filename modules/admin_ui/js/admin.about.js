/* ================= 关于 ================= */
/* 数据源是 /admin/api/runtime：一次读取，不轮询（检查更新会走 git fetch，不该反复跑）。
   三个维护动作（更新 / 恢复默认 / 重启）都不可逆，一律走 uiConfirm 的 danger 二次确认 */
function aboutBytes(n){
  n=parseInt(n)||0;
  if(n<=0)return '0 B';
  var u=['B','KB','MB','GB','TB'],i=0;
  while(n>=1024&&i<u.length-1){n/=1024;i++}
  return (i?n.toFixed(1):n)+' '+u[i];
}
function aboutMode(m){
  var k={dev:'about.mode_dev',prod:'about.mode_prod',vercel:'about.mode_vercel'}[String(m||'')];
  return T(k||'about.mode_unknown',String(m||'-'));
}
function aboutUpdateMode(m){
  var k={off:'about.umode_off',download:'about.umode_download',auto:'about.umode_auto'}[String(m||'off')];
  return T(k||'about.umode_off','off');
}
function aboutSchema(s){
  if(!s)return T('about.db_off','未启用');
  var t='v'+(s.version===null||s.version===undefined?'-':s.version)+' / '+T('about.schema_latest','最新')+' v'+s.latest;
  return s.up_to_date?t:T('about.schema_behind','{v}（需重启服务）',{v:t});
}
/* 检查结果按后端返回的 reason 稳定码取词；detail 只在失败时附上，排障用，长文本截断 */
function aboutReason(chk){
  chk=chk||{};
  var m={not_git:'about.reason_not_git',git_missing:'about.reason_git_missing',no_branch:'about.reason_no_branch',
    fetch_failed:'about.reason_fetch_failed',up_to_date:'about.reason_up_to_date',
    update_available:'about.reason_update_available',error:'about.reason_error',
    invalid_target:'about.reason_invalid_target',
    downloaded:'about.reason_downloaded',updated:'about.reason_updated'};
  var txt=T(m[chk.reason]||'about.reason_unknown','—');
  if(chk.reason==='update_available'&&chk.remote_subject)txt+='：'+chk.remote_subject;
  if((chk.reason==='fetch_failed'||chk.reason==='error'||chk.reason==='invalid_target')&&chk.detail)txt+='（'+String(chk.detail).slice(0,200)+'）';
  return txt;
}
function aboutUpdateUsable(chk){return ['not_git','git_missing','no_branch','invalid_target'].indexOf((chk||{}).reason)<0}
function _aboutRow(k,v){
  return '<div class="info-item"><span class="ik">'+esc(k)+'</span><span class="iv">'+esc(v)+'</span></div>';
}
function aboutHtml(d){
  var db=d.db||{},up=d.update||{},st=up.settings||{},chk=up.check||{};
  var usable=aboutUpdateUsable(chk),dis=usable?'':' disabled';
  var h='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2></div>';
  h+='<div class="card"><div class="card-header"><div class="card-title"><h2>'+esc(T('about.version_title','版本信息'))+
    '</h2></div></div><div class="card-body"><div class="info-grid">'+
    _aboutRow(T('about.version','框架版本'),d.version||'-')+
    _aboutRow(T('about.python','Python 版本'),d.python||'-')+
    _aboutRow(T('about.mode','运行模式'),aboutMode(d.mode))+
    _aboutRow(T('about.uptime','已运行'),d.uptime_display||'-')+
    _aboutRow(T('about.plugins','插件数量'),String(d.plugin_count===null||d.plugin_count===undefined?0:d.plugin_count))+
    _aboutRow(T('about.db','数据库'),db.available?aboutBytes(db.size_bytes):T('about.db_off','未启用'))+
    _aboutRow(T('about.schema','数据库结构'),aboutSchema(db.schema))+
    '</div></div></div>';
  h+='<div class="card"><div class="card-header"><div class="card-title"><h2>'+esc(T('about.update','更新'))+
    '</h2></div></div><div class="card-body"><div class="info-grid">'+
    _aboutRow(T('about.update_mode','更新模式'),aboutUpdateMode(st.mode))+
    _aboutRow(T('about.update_source','更新来源'),(st.remote||'origin')+' / '+(st.branch||T('about.branch_current','当前分支')))+
    '</div>'+
    '<div class="about-actions" style="margin-top:16px">'+
    '<button class="btn" id="about-check"'+dis+' onclick="aboutCheckUpdate(this)">'+esc(T('about.check_update','检查更新'))+'</button>'+
    '<button class="btn btn-primary" id="about-apply"'+dis+' onclick="aboutApplyUpdate(this)">'+esc(T('about.update_restart','更新并重启'))+'</button>'+
    '</div>'+
    /* 原先独立成菜单项的「更新」分类并进这张卡：更新参数（UPDATE_*）与上面的更新模式/来源
       本来就是同一件事，拆成两个入口反而要多点一次。表在 cfgTableHtml 里生成，
       容器 id 以 cfg- 开头，编辑/还原走的仍是共享的 cfg-edit / cfg-reset 那条链 */
    '<div class="about-sub" aria-hidden="true"></div>'+
    '<div id="cfg-update">'+cfgTableHtml(_setKeysOf(_cfg||{},SET_UPDATE_CAT))+'</div>'+
    '</div></div></div>';
  h+='<div class="card"><div class="card-header"><div class="card-title"><h2>'+esc(T('about.actions_title','维护操作'))+
    '</h2></div></div><div class="card-body"><div class="about-actions">'+
    '<button class="btn btn-danger" onclick="aboutResetConfig(this)">'+esc(T('about.reset','恢复默认设置'))+'</button>'+
    '<button class="btn btn-danger" onclick="aboutRestart(this)">'+esc(T('about.restart','重启服务'))+'</button>'+
    '</div>'+
    /* 高级模式：低调地挂在「维护操作」卡片底部一行——它是解除隐藏分类的开关，不该自己占一张卡 */
    advRowHtml()+
    '</div></div>';
  /* 恢复出厂设置只在系统主管理员这里出现：与重启/恢复默认同属维护动作，入口集中在「关于」；
     普通管理员连卡片都不渲染（接口侧另有 403 兜底） */
  if(isSuper()){
    h+='<div class="card"><div class="card-header"><div class="card-title"><h2>'+esc(T('factory.title','恢复出厂设置'))+
      '</h2></div></div><div class="card-body"><div class="about-actions">'+
      '<button class="btn btn-danger" onclick="factoryReset(\'plugins\')">'+esc(T('factory.plugins_btn','清理所有插件'))+'</button>'+
      '<button class="btn btn-danger" onclick="factoryReset(\'records\')">'+esc(T('factory.records_btn','清理日志与记录'))+'</button>'+
      '<button class="btn btn-danger-solid" onclick="factoryReset(\'full\')">'+esc(T('factory.full_btn','完整恢复出厂'))+'</button>'+
      '</div></div></div>';
  }
  return h;
}
/* 高级模式低调行：未解锁 = 口令框 + 解锁；已解锁 = 「已解锁」+ 重新上锁。
   被锁的项（设备高级项 / 口令）不单独成类：未解锁时在各自分类里隐藏，解锁后就在原位出现
   （见 admin.config.js 的 ADV_HIDDEN_KEYS / _cfgKeyVisible） */
function advRowHtml(){
  var row='<div class="flex" style="gap:8px;align-items:center;margin-top:16px;border-top:1px solid var(--line);padding-top:16px">'+
    '<span class="dim">'+esc(T('adv.title','高级模式'))+'</span>';
  if(advUnlocked()){
    return row+'<span class="dim small">'+esc(T('adv.status_on','已解锁'))+'</span>'+
      '<button class="btn btn-sm btn-ghost" data-act="adv-lock" title="'+esc(T('adv.lock','重新上锁'))+'" aria-label="'+esc(T('adv.lock','重新上锁'))+'">'+esc(T('adv.lock','重新上锁'))+'</button></div>';
  }
  return row+'<input class="input mono" type="password" id="adv-key" autocomplete="off" style="flex:1;max-width:220px" placeholder="'+esc(T('adv.key_ph','输入口令'))+'" onkeydown="if(event.key===\'Enter\')unlockAdvanced(document.getElementById(\'adv-unlock\'))">'+
    '<button class="btn btn-sm btn-ghost" id="adv-unlock" data-act="adv-unlock" title="'+esc(T('adv.unlock','解锁'))+'" aria-label="'+esc(T('adv.unlock','解锁'))+'">'+esc(T('adv.unlock','解锁'))+'</button></div>';
}
function unlockAdvanced(btn){
  var inp=document.getElementById('adv-key');
  var key=inp?String(inp.value||''):'';
  if(!key){toast(T('adv.need_key','请输入口令'),'error');return}
  btnBusy(btn,true);
  R.post('/admin/api/advanced/unlock',{key:key}).then(function(d){
    btnBusy(btn,false);
    if(!d||d.success===false){toast((d&&d.message)||T('adv.wrong_key','口令不正确'),'error');return}
    try{sessionStorage.setItem('ADV_UNLOCKED','1')}catch(e){}
    toast(T('adv.unlocked','高级模式已解锁'),'success');
    /* 解锁后：被锁的项立刻在各自分类的原位出现——重绘菜单，并把当前分类的表格重绘一遍 */
    if(_cfg){renderSetMenu(_cfg);setSelect(_setCat||SET_ABOUT)}else{refreshConfig();loadAbout()}
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function lockAdvanced(){
  try{sessionStorage.removeItem('ADV_UNLOCKED')}catch(e){}
  toast(T('adv.locked','已重新上锁'),'success');
  /* 上锁后：被锁的项从各自分类里消失——重绘菜单与当前分类表格；分类本身都还在，不用跳走 */
  if(_cfg){renderSetMenu(_cfg);setSelect(_setCat||SET_ABOUT)}else{refreshConfig();loadAbout()}
}
function loadAbout(){
  var box=document.getElementById('set-about');
  if(!box)return;
  if(!box.querySelector('.set-head'))box.innerHTML='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2></div><div class="empty">'+esc(T('msg.loading','加载中...'))+'</div>';
  R.get('/admin/api/runtime').then(function(d){
    box.innerHTML=aboutHtml(d||{});
    /* 关于页里的「更新参数」表用 cfg-edit 那条链改值：把它的重载回调注册进来（重载=重绘本页），
       并补一次 bindCfgInput——正是在这里渲染，焦点要落到刚展开的输入框上 */
    _cfgReloadMap['cfg-update']=loadAbout;
    bindCfgInput();
  }).catch(function(){
    box.innerHTML='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2></div><div class="empty">'+
      esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function aboutCheckUpdate(btn){
  btnBusy(btn,true);
  R.get('/admin/api/update/check').then(function(d){
    btnBusy(btn,false);
    d=d||{};
    toast(aboutReason(d),d.available?'success':(d.reason==='up_to_date'?'success':'error'));
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function aboutApplyUpdate(btn){
  uiConfirm({
    title:T('about.update_restart','更新并重启'),danger:true,confirmText:T('about.update_restart','更新并重启'),
    message:T('about.update_confirm_msg','将更新到最新版本并重启服务。')
  }).then(function(ok){
    if(!ok)return;
    btnBusy(btn,true);
    R.post('/admin/api/update/apply').then(function(d){
      d=d||{};
      if(d.success===false){
        btnBusy(btn,false);
        toast(T('about.update_failed','更新失败：{msg}',{msg:d.detail||d.reason||''}),'error');
        return;
      }
      if(d.reason==='up_to_date'){btnBusy(btn,false);toast(T('about.reason_up_to_date','已是最新版本'),'success');return}
      toast(T('about.update_done','更新完成，正在重启服务…'),'success');
      R.post('/admin/api/system/restart');
      /* 重启是 execv 原地换镜像：连接会断一下，几秒后刷新页面即回到新版本 */
      setTimeout(function(){window.location.reload()},5000);
    }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
function aboutResetConfig(btn){
  uiConfirm({
    title:T('about.reset','恢复默认设置'),danger:true,confirmText:T('about.reset','恢复默认设置'),
    message:T('about.reset_confirm_msg','将恢复全部配置为默认值，插件与用户组不受影响。')
  }).then(function(ok){
    if(!ok)return;
    btnBusy(btn,true);
    R.post('/admin/api/config/reset-all').then(function(d){
      btnBusy(btn,false);
      if(d&&d.success){
        toast(T('about.reset_done','已恢复默认设置'),'success');
        /* 覆盖项整批清空，缓存作废后重绘（当前停在关于页，重绘后仍在关于页） */
        _cfgCacheTime=0;refreshConfig();
      }else toast((d&&d.message)||T('about.reset_failed','恢复失败'),'error');
    }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
function aboutRestart(btn){
  uiConfirm({
    title:T('about.restart','重启服务'),danger:true,confirmText:T('about.restart','重启服务'),
    message:T('about.restart_confirm_msg','服务将短暂中断后自动恢复。')
  }).then(function(ok){
    if(!ok)return;
    btnBusy(btn,true);
    R.post('/admin/api/system/restart').then(function(d){
      if(d&&d.success){
        toast(T('about.restart_done','服务正在重启…'),'success');
        setTimeout(function(){window.location.reload()},5000);
      }else{btnBusy(btn,false);toast((d&&d.message)||T('about.restart_failed','重启失败'),'error')}
    }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
