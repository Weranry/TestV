# JS 备份/恢复页
ADMIN_JS_BACKUP = r'''/* ================= 备份与恢复 ================= */
var _BK_PER=10,_bkFiles=[];
/* 最近一次备份时间写在「操作」卡片头右侧：备份是否还在正常产出，看这一行最快。
   自动备份的开关在「设置 → 备份」里改，这里只回显它的状态与上一次的执行结果——
   失败也记了时间（防重试风暴），所以失败提示必须显式露出来，不能只看「最近一次」。 */
function bkLast(list,info){
  var el=document.getElementById('bk-last');
  if(!el)return;
  var h=T('backup.last_backup','最近备份：{time}',{time:((list&&list.length)?fmtDT(list[0].created_at):T('backup.none','暂无'))});
  if(info){
    var times=esc(info.auto_times||'');
    if(info.auto_enabled){
      h+='<span class="sep"></span>'+T('backup.auto_on','自动备份：已开启')+(times?'（'+times+'）':'');
      h+=' · '+(info.auto_last?T('backup.auto_last','最近一次：{time}',{time:fmtDT(info.auto_last)}):T('backup.auto_never','尚未执行'));
    }else{
      h+='<span class="sep"></span>'+T('backup.auto_off','自动备份：未开启');
    }
    if(info.auto_error)h+='<span class="sep"></span>'+T('backup.auto_failed','上次自动备份失败：{error}',{error:esc(info.auto_error)});
  }
  el.innerHTML=h;
}
/* data/backups/ 里的自动快照列表。这些文件只进不出（每次恢复前写一份），所以要有
   逐份删除 + 按保留策略清理两个入口，光看 KPI 的占用数字没法动手 */
function renderBackupFiles(list){
  if(list)_bkFiles=list||[];
  var el=document.getElementById('bk-files');
  if(!el)return;
  if(!_bkFiles.length){
    el.innerHTML='<div class="empty">'+T('backup.files_empty','暂无自动快照。恢复备份前，当前库会先在这里留一份。')+'</div>';
    return;
  }
  var r=pgSlice(_bkFiles,'bk-files',_BK_PER);
  var h='<table><thead><tr><th>'+T('backup.col_name','文件名')+'</th><th class="num">'+T('test.col_size','大小')+'</th><th>'+T('log.col_time','时间')+'</th>'+
    '<th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  r.rows.forEach(function(b){
    h+='<tr><td class="mono ellip" title="'+esc(b.name)+'">'+esc(b.name)+'</td>'+
      '<td class="mono num">'+esc(b.size_text||fmtBytes(b.size))+'</td>'+
      '<td>'+fmtDT(b.created_at)+'</td>'+
      '<td><div class="acts">'+
        '<button class="btn btn-sm" data-act="bk-file-dl" data-name="'+esc(b.name)+'">'+T('backup.file_download','下载')+'</button>'+
        '<button class="btn btn-sm" data-act="bk-file-restore" data-name="'+esc(b.name)+'">'+T('backup.file_restore','恢复')+'</button>'+
        '<span class="sep"></span>'+
        '<button class="btn btn-sm btn-danger" data-act="bk-file-del" data-name="'+esc(b.name)+'">'+T('btn.delete','删除')+'</button>'+
      '</div></td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+r.bar;
  _pgRender['bk-files']=renderBackupFiles;
}
function bkDeleteFile(name){
  uiConfirm({title:T('backup.del_title','删除备份'),danger:true,confirmText:T('btn.delete','删除'),
    message:T('backup.del_confirm','将删除快照「{name}」，删除后无法再用于恢复。',{name:name})
  }).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/backup/files/'+encodeURIComponent(name)).then(function(d){
      if(d.success===false){toast(d.message||T('announce.del_failed','删除失败'),'error');return}
      toast(d.message||T('backup.deleted','已删除该备份'),'success');refreshBackup();
    });
  });
}
/* 快照下载走页面导航：FileResponse 是流式响应，用 fetch 还得在内存里把整个文件拼一遍再落盘 */
function bkFileDownload(name){
  window.location.href='/admin/api/backup/files/'+encodeURIComponent(name)+'/download';
}
/* 直接用目录里的快照恢复，省掉「先下载再上传」这一步 */
function bkFileRestore(name){
  uiConfirm({
    title:T('backup.snapshot_restore_title','用这份快照恢复'),danger:true,confirmText:T('backup.replace_confirm','替换并恢复'),
    message:T('backup.snapshot_restore_confirm','将用快照「{name}」覆盖当前数据库，当前数据会先自动备份。恢复后所有账号、权限与配置以这份快照为准，当前登录态会失效。',{name:name})
  }).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/backup/files/'+encodeURIComponent(name)+'/restore').then(function(d){
      if(d.success===false){toast(d.message||T('backup.restore_failed','恢复失败'),'error');return}
      toast(d.message||T('backup.restored','恢复完成，需重新登录'),'success');
      setTimeout(function(){window.location.href='/login'},1200);
    });
  });
}
function bkCleanup(){
  uiConfirm({title:T('backup.cleanup','按保留策略清理'),danger:true,confirmText:T('backup.cleanup_confirm','清理'),
    message:T('backup.cleanup_msg','按「备份保留份数 / 保留天数」删掉超出的自动快照（策略在下方「备份配置」里改，0 = 不限）。')
  }).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/backup/cleanup').then(function(d){
      if(d.success===false){toast(d.message||T('backup.cleanup_failed','清理失败'),'error');return}
      toast(d.message||T('backup.cleaned','清理完成'),'success');refreshBackup();
    });
  });
}
function refreshBackup(){
  R.get('/admin/api/backup/info').then(function(d){
    if(!d||d.success===false){
      var el=document.getElementById('bk-metrics');
      if(el)el.innerHTML='<div class="empty">'+esc((d&&d.message)||T('backup.db_disabled','当前模式未启用数据库'))+'</div>';
      bkLast(null);renderBackupFiles([]);
      return;
    }
    var el=document.getElementById('bk-metrics');
    if(el)el.innerHTML=
      /* 与概览页共用 kpi()：.metric 里的主数值必须用 .k，用 .v 会掉回 14px 正文样式 */
      kpi(T('backup.kpi_db_size','库大小'),esc(d.db_size_text||fmtBytes(d.db_size)))+
      kpi(T('backup.kpi_backups','已有备份'),T('backup.count_n','{n} 份',{n:(d.backups||[]).length}))+
      kpi(T('backup.kpi_size','备份占用'),esc(d.backups_size_text||fmtBytes(d.backups_size)))+
      kpi(T('backup.kpi_upload_max','上传上限'),d.upload_max_mb>0?d.upload_max_mb+' MB':T('user.unlimited','不限'));
    bkLast(d.backups,d);renderBackupFiles(d.backups);
  }).catch(function(){
    var el=document.getElementById('bk-metrics');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
    bkLast(null);renderBackupFiles([]);
  });
}
function bkFile(){var el=document.getElementById('bk-file');return (el&&el.files&&el.files[0])?el.files[0]:null}
/* 选中文件后才能真正点「恢复」：按钮常驻但禁用，各按钮宽度才一致 */
function bkPick(){
  var f=bkFile(),btn=document.getElementById('bk-restore'),note=document.getElementById('bk-file-note');
  if(btn)btn.disabled=!f;
  if(note)note.textContent=f?(f.name+' · '+fmtBytes(f.size)):T('backup.no_file','未选择文件');
}
/* 走页面导航下载：导出是流式响应，用 fetch 还得在内存里把整个文件拼一遍再落盘 */
function bkDownload(el){
  var b=el||document.querySelector('[data-act="bk-download"]');
  if(b){b.disabled=true;b.textContent=T('backup.exporting','导出中...')}
  window.location.href='/admin/api/backup/download';
  setTimeout(function(){if(b){b.disabled=false;b.textContent=T('backup.download','下载当前备份')}},1500);
}
function bkRestore(){
  var f=bkFile();
  if(!f){toast(T('backup.pick_first','请先选择备份文件'),'error');return}
  uiConfirm({
    title:T('backup.restore_title','恢复备份'),danger:true,confirmText:T('backup.replace_confirm','替换并恢复'),
    message:T('backup.restore_confirm','将用备份「{name}」覆盖当前数据库，当前数据会先自动备份。恢复后所有账号、权限与配置以这份备份为准，当前登录态会失效。',{name:f.name})
  }).then(function(ok){
    if(!ok)return;
    var btn=document.getElementById('bk-restore');
    if(btn){btn.disabled=true;btn.textContent=T('backup.restoring','恢复中...')}
    var done=function(){if(btn){btn.disabled=false;btn.textContent=T('backup.restore','上传并恢复')}};
    /* 传原始二进制 body（不是 multipart）：与后端约定一致，服务端也不需要 python-multipart */
    fetch('/admin/api/backup/restore',{
      method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f
    }).then(function(r){return r.json()}).then(function(d){
      if(!d||d.success===false){toast((d&&d.message)||T('backup.restore_failed','恢复失败'),'error');done();return}
      toast(d.message||T('backup.restored','恢复完成，需重新登录'),'success');
      setTimeout(function(){window.location.href='/login'},1200);
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error');done()});
  });
}
'''