# JS 日志页
ADMIN_JS_LOGS = r'''/* ================= 日志 ================= */
var _logOffset=0,_logPageSize=100,_logTotal=0;
/* 末页允许的最大 offset：总页数至少为 1，避免 offset 永远夹不到上界 */
function _logMaxOff(lim,total){return (Math.max(1,Math.ceil(total/lim))-1)*lim}
/* 翻页按钮按 cp/tp 置灰：越界的「下一页」点了只会看到空表，分不清「没数据」和「翻过头」 */
function _setLogBtns(prevId,nextId,cp,tp){
  var p=document.getElementById(prevId),n=document.getElementById(nextId);
  if(p)p.disabled=cp<=1;
  if(n)n.disabled=cp>=tp;
}
/* 筛选条件变化时重置 offset，否则会拿旧 offset 去查新结果集 */
function logResetAndRefresh(){_logOffset=0;refreshRequestLogs()}
function refreshRequestLogs(pageDir){
  if(typeof pageDir==='number'){
    var page=Math.floor(_logOffset/_logPageSize);
    // 夹在 [0, 末页偏移]：只夹下界会让「下一页」越过后 offset 越界
    _logOffset=Math.min(Math.max(0,(page+pageDir)*_logPageSize),_logMaxOff(_logPageSize,_logTotal));
  }
  var plugin=document.getElementById('log-plugin').value;
  var ms=document.getElementById('log-status').value;
  var acctEl=document.getElementById('log-account');
  var acct=acctEl?acctEl.value:'';
  var lim=_logPageSize;
  var url='/admin/api/request-logs?limit='+lim+'&offset='+_logOffset;
  if(plugin)url+='&plugin='+encodeURIComponent(plugin);
  if(ms)url+='&min_status='+ms;
  if(acct)url+='&account='+encodeURIComponent(acct);
  R.get(url).then(function(d){
    if(d.success===false){document.getElementById('logs-area').innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _logTotal=d.total||0;
    var tp=Math.max(1,Math.ceil(d.total/lim)),cp=Math.floor(_logOffset/lim)+1;
    // 数据变动（清空、筛选）导致当前 offset 越界时，夹回末页重取一次
    if(cp>tp){_logOffset=(tp-1)*lim;refreshRequestLogs();return}
    _setLogBtns('log-prev','log-next',cp,tp);
    var lq=d.log_queue||{};
    // 保留天数与队列积压从概览页移到这里，和日志正文放在一起看更直观
    var ret=(d.retention_days!=null?T('log.retention_days','{n} 天',{n:d.retention_days}):'-');
    var drop=(lq.dropped?T('log.dropped_n',' · 已丢弃 {n} 条',{n:num(lq.dropped)}):'');
    document.getElementById('log-page-info').textContent=
      T('log.page_info','{cur} / {total} 页 · 共 {n} 条 · 保留 {retention} · 队列 {size} / {max}{dropped}',{cur:cp,total:tp,n:num(d.total),retention:ret,size:num(lq.size),max:num(lq.maxsize),dropped:drop});
    var sc={'5':'var(--red-deep)','4':'var(--orange-deep)','3':'var(--blue-deep)','2':'inherit'};
    var logs=d.logs||[];
    var h='<table><thead><tr><th>'+T('log.col_time','时间')+'</th><th>'+T('log.col_method','方式')+'</th><th>'+T('log.col_path','路径')+'</th><th>'+T('log.col_plugin','插件')+'</th><th>'+T('log.col_account','账号')+'</th><th class="col-state">'+T('log.col_state','状态')+'</th><th class="num">'+T('log.col_duration','耗时')+'</th><th>'+T('log.col_request_id','请求 ID')+'</th><th>'+T('log.col_error','响应')+'</th></tr></thead><tbody>';
    if(!logs.length)h+='<tr><td colspan="9" class="empty">'+T('log.empty','暂无日志')+'</td></tr>';
    logs.forEach(function(l){
      var s=String(l.status_code||'');
      var color=sc[s.charAt(0)]||'inherit';
      h+='<tr><td class="mono dim">'+fmtDT(l.timestamp).substring(5)+'</td><td>'+esc(l.method)+'</td>'+
        '<td class="mono ellip" title="'+esc(l.path)+'">'+esc(l.path)+'</td>'+
        '<td class="dim">'+esc(l.plugin_name||'-')+'</td>'+
        '<td class="dim ellip" title="'+esc(_logAcctName(l.account_id))+'">'+esc(_logAcctName(l.account_id))+'</td>'+
        '<td class="mono num" style="color:'+color+';font-weight:500">'+l.status_code+'</td>'+
        '<td class="mono dim num">'+(l.duration_ms!=null?l.duration_ms+'ms':'-')+'</td>'+
        '<td class="mono dim">'+esc(l.request_id||'-')+'</td>'+
        '<td class="res-err" title="'+esc(l.error||'')+'">'+esc(l.error||'')+'</td></tr>';
    });
    h+='</tbody></table>';
    document.getElementById('logs-area').innerHTML=h;
  }).catch(function(){
    var el=document.getElementById('logs-area');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function exportLogs(fmt){
  var p=document.getElementById('log-plugin').value,ms=document.getElementById('log-status').value;
  var acctEl=document.getElementById('log-account'),acct=acctEl?acctEl.value:'';
  var u='/admin/api/request-logs/export?format='+fmt;
  if(p)u+='&plugin='+encodeURIComponent(p);
  if(ms)u+='&min_status='+ms;
  if(acct)u+='&account='+encodeURIComponent(acct);
  window.open(u,'_blank');
}
function clearLogs(){
  uiConfirm({
    title:T('log.clear_title','清空全部日志'),
    message:T('log.clear_confirm','将删除所有请求日志记录，此操作不可恢复。'),
    confirmText:T('log.clear_forever','永久清空'),danger:true,requireText:T('log.clear','清空')
  }).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/request-logs/clear',{}).then(function(d){
      if(d.success){toast(T('log.cleared','已清空 {n} 条日志',{n:num(d.deleted)}),'success');refreshRequestLogs()}
      else toast(d.message||T('log.clear_failed','清空失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
function loadPluginOptions(){
  R.get('/admin/api/plugins').then(function(d){
    var sel=document.getElementById('log-plugin');
    (d.plugins||[]).forEach(function(p){
      var o=document.createElement('option');o.value=p.name;o.textContent=p.name;sel.appendChild(o);
    });
  });
}
/* 账号下拉与「账号」列共用同一份账号表：日志里存的是 account_id，直接显示数字读不出是谁。
   EVKEY 环境变量鉴权的请求没有账号（account_id 为 NULL），显示 '-'。 */
var _logAccts={},_logAcctLoaded=false;
function _logAcctName(id){
  if(id===null||id===undefined||id==='')return '-';
  return _logAccts[id]||('#'+id);
}
function loadLogAccountOptions(){
  if(_logAcctLoaded)return;
  _logAcctLoaded=true;
  R.get('/admin/api/accounts').then(function(d){
    var sel=document.getElementById('log-account');
    (d.accounts||[]).forEach(function(a){
      _logAccts[a.id]=a.name;
      if(!sel)return;
      var o=document.createElement('option');o.value=a.id;o.textContent=a.name;sel.appendChild(o);
    });
    // 名字是懒加载的：拉回来之前已渲染的行只有 '#id'，补一次重绘把名字填上。
    // 不能反过来在拿到名字前先渲染，那样筛选框也会空着
    var area=document.getElementById('logs-area');
    if(area&&area.querySelector('table'))refreshRequestLogs();
  }).catch(function(){_logAcctLoaded=false});
}
/* ---- 二级子标签：请求日志 / 配置审计（谁改了哪个管理接口） ---- */
var _logView='request';
function switchLogSubTab(v){
  _logView=v;
  /* 页内那行子标签已删（入口统一在侧栏）；
     侧边栏二级项同步点亮：页内切换与侧边栏入口是同一份视图状态，不能各亮各的 */
  document.querySelectorAll('.snav-sub .tab').forEach(function(t){
    if(t.dataset.page==='logs')t.classList.toggle('on',t.dataset.sub===v);
  });
  var req=document.getElementById('log-view-request'),aud=document.getElementById('log-view-audit');
  if(req)req.style.display=(v==='request')?'':'none';
  if(aud)aud.style.display=(v==='audit')?'':'none';
  refreshLogView();
}
function refreshLogView(){
  if(_logView==='audit')refreshAuditLogs();
  else{loadLogAccountOptions();refreshRequestLogs()}
}
var _auditOffset=0,_auditPageSize=100,_auditTotal=0;
function refreshAuditLogs(pageDir){
  if(typeof pageDir==='number'){
    var page=Math.floor(_auditOffset/_auditPageSize);
    _auditOffset=Math.min(Math.max(0,(page+pageDir)*_auditPageSize),_logMaxOff(_auditPageSize,_auditTotal));
  }
  R.get('/admin/api/audit-logs?limit='+_auditPageSize+'&offset='+_auditOffset).then(function(d){
    var el=document.getElementById('audit-area');if(!el)return;
    if(d.success===false){el.innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _auditTotal=d.total||0;
    var tp=Math.max(1,Math.ceil(d.total/_auditPageSize)),cp=Math.floor(_auditOffset/_auditPageSize)+1;
    if(cp>tp){_auditOffset=(tp-1)*_auditPageSize;refreshAuditLogs();return}
    _setLogBtns('audit-prev','audit-next',cp,tp);
    document.getElementById('audit-page-info').textContent=
      T('log.audit_page_info','{cur} / {total} 页 · 共 {n} 条 · 记录管理接口的写操作',{cur:cp,total:tp,n:num(d.total)});
    var logs=d.logs||[];
    var h='<table><thead><tr><th>'+T('log.col_time','时间')+'</th><th>'+T('log.col_account','账号')+'</th><th>'+T('log.col_ip','来源 IP')+'</th><th>'+T('core.col_action','操作')+'</th><th>'+T('log.col_path','路径')+'</th><th class="col-state">'+T('log.col_state','状态')+'</th><th>'+T('log.col_detail','详情')+'</th></tr></thead><tbody>';
    if(!logs.length)h+='<tr><td colspan="7" class="empty">'+T('log.audit_empty','暂无审计记录')+'</td></tr>';
    logs.forEach(function(l){
      h+='<tr><td class="mono dim">'+fmtDT(l.timestamp).substring(5)+'</td>'+
        '<td>'+esc(l.actor||T('log.unknown_actor','(未知)'))+' <span class="dim mono">'+(l.account_id?'#'+l.account_id:'')+'</span></td>'+
        '<td class="mono dim">'+esc(l.ip||'-')+'</td>'+
        '<td class="mono strong">'+esc(l.method||'')+'</td>'+
        '<td class="mono ellip" title="'+esc(l.path||'')+'">'+esc(l.path||'')+'</td>'+
        '<td class="mono dim num">'+(l.status_code!=null?l.status_code:'-')+'</td>'+
        '<td class="mono dim ellip" title="'+esc(l.summary||'')+'">'+esc(l.summary||'')+'</td></tr>';
    });
    h+='</tbody></table>';
    el.innerHTML=h;
  }).catch(function(){
    var el=document.getElementById('audit-area');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function clearAuditLogs(){
  uiConfirm({
    title:T('log.audit_clear_title','清空审计记录'),
    message:T('log.audit_clear_confirm','将删除全部配置变更审计记录，此操作不可恢复。'),
    confirmText:T('log.clear_forever','永久清空'),danger:true,requireText:T('log.clear','清空')
  }).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/audit-logs/clear',{}).then(function(d){
      if(d.success){toast(T('log.audit_cleared','已清空 {n} 条审计记录',{n:num(d.deleted)}),'success');refreshAuditLogs()}
      else toast(d.message||T('log.clear_failed','清空失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
'''
