# JS 关于页（版本信息 + 更新 / 重置 / 重启）
ADMIN_JS_ABOUT = r'''/* ================= 关于 ================= */
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
    downloaded:'about.reason_downloaded',updated:'about.reason_updated'};
  var txt=T(m[chk.reason]||'about.reason_unknown','—');
  if(chk.reason==='update_available'&&chk.remote_subject)txt+='：'+chk.remote_subject;
  if((chk.reason==='fetch_failed'||chk.reason==='error')&&chk.detail)txt+='（'+String(chk.detail).slice(0,200)+'）';
  return txt;
}
function aboutUpdateUsable(chk){return ['not_git','git_missing','no_branch'].indexOf((chk||{}).reason)<0}
function _aboutRow(k,v){
  return '<div class="info-item"><span class="ik">'+esc(k)+'</span><span class="iv">'+esc(v)+'</span></div>';
}
function aboutHtml(d){
  var db=d.db||{},up=d.update||{},st=up.settings||{},chk=up.check||{};
  var usable=aboutUpdateUsable(chk),dis=usable?'':' disabled';
  var h='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2><span class="dim small">'+esc(T('about.subtitle','版本信息与维护操作'))+'</span></div>';
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
    '</h2><div class="card-desc">'+esc(T('about.update_desc','更新版本'))+
    '</div></div></div><div class="card-body"><div class="info-grid">'+
    _aboutRow(T('about.update_mode','更新模式'),aboutUpdateMode(st.mode))+
    _aboutRow(T('about.update_source','更新来源'),(st.remote||'origin')+' / '+(st.branch||T('about.branch_current','当前分支')))+
    '</div><div class="panel about-note" id="about-update-note">'+esc(aboutReason(chk))+'</div>'+
    '<div class="about-actions" style="margin-top:16px">'+
    '<button class="btn" id="about-check"'+dis+' onclick="aboutCheckUpdate(this)">'+esc(T('about.check_update','检查更新'))+'</button>'+
    '<button class="btn btn-primary" id="about-apply"'+dis+' onclick="aboutApplyUpdate(this)">'+esc(T('about.update_restart','更新并重启'))+'</button>'+
    '</div></div></div>';
  h+='<div class="card"><div class="card-header"><div class="card-title"><h2>'+esc(T('about.actions_title','维护操作'))+
    '</h2></div></div><div class="card-body"><div class="about-actions">'+
    '<button class="btn btn-danger" onclick="aboutResetConfig(this)">'+esc(T('about.reset','恢复默认设置'))+'</button>'+
    '<button class="btn btn-danger" onclick="aboutRestart(this)">'+esc(T('about.restart','重启服务'))+'</button>'+
    '</div><p class="dim small about-note">'+esc(T('about.actions_note','更新与重启会短暂中断服务。'))+
    '</p></div></div>';
  return h;
}
function loadAbout(){
  var box=document.getElementById('set-about');
  if(!box)return;
  if(!box.querySelector('.set-head'))box.innerHTML='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2></div><div class="empty">'+esc(T('msg.loading','加载中...'))+'</div>';
  R.get('/admin/api/runtime').then(function(d){
    box.innerHTML=aboutHtml(d||{});
  }).catch(function(){
    box.innerHTML='<div class="set-head"><h2>'+esc(T('set.about','关于'))+'</h2></div><div class="empty">'+
      esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function _aboutNote(txt,err){
  var el=document.getElementById('about-update-note');
  if(!el)return;
  el.textContent=txt;
  el.classList.toggle('err',!!err);
}
function aboutCheckUpdate(btn){
  btnBusy(btn,true);
  R.get('/admin/api/update/check').then(function(d){
    btnBusy(btn,false);
    d=d||{};
    _aboutNote(aboutReason(d),!d.available&&d.reason!=='up_to_date');
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
        _aboutNote(T('about.update_failed','更新失败：{msg}',{msg:d.detail||d.reason||''}),true);
        toast(T('about.update_failed','更新失败：{msg}',{msg:d.detail||d.reason||''}),'error');
        return;
      }
      if(d.reason==='up_to_date'){btnBusy(btn,false);_aboutNote(aboutReason(d));toast(T('about.reason_up_to_date','已是最新版本'),'success');return}
      _aboutNote(T('about.update_done','更新完成，正在重启服务…'));
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
'''