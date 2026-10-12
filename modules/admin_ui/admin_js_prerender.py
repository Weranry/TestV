# JS 定时预渲染页
ADMIN_JS_PRERENDER = r'''/* ================= 定时预渲染 ================= */
/* 后处理参数：由每个请求现场套用，不进缓存键、也不回填到查询参数文本框。
   size 不在此列——它是业务参数，要跟着路径一起填。 */
var PR_POST=['rotate','invert','cmode','format','fmt'];
var _prTasks=[],_prMeta={};

/* 上次执行结果只留圆点，含义见「定时任务」卡片头「上次执行」图例那一行；
   失败原因仍在 title 里，鼠标悬停可看 */
function prBadge(status,err){
  var m={rendered:['dot-on',T('prerender.status_ok','成功')],skipped:['dot-warn',T('prerender.status_skip','已跳过')],
    invalid:['dot-warn',T('prerender.status_stale','路由失效')],error:['dot-error',T('prerender.status_fail','失败')]}[status];
  if(!m)return '<span class="dim small">'+T('prerender.status_none','未执行')+'</span>';
  return dotHtml(m[0],m[1]+(err?('：'+err):''));
}
/* 每日时刻在库里是规范化的 'HH:MM,HH:MM'，展示换成更易读的分隔符 */
function prDailyText(v){
  return String(v||'').split(',').map(function(s){return s.trim()})
    .filter(function(s){return s}).join('、');
}
function prSchedType(t){
  var v=String(t?t.schedule_type:'interval');
  return (v==='daily'||v==='cron')?v:'interval';
}
function prScheduleText(t){
  var v=String(t.schedule_type);
  if(v==='daily')return T('prerender.sched_daily','每日 {time}',{time:esc(prDailyText(t.daily_time)||'-')});
  if(v==='cron')return 'Cron '+esc(String(t.cron_expr||'')||'-');
  return T('prerender.sched_interval','每 {n} 秒',{n:num(t.interval_seconds)});
}
function prParams(t){
  try{return JSON.parse(t.params_json||'{}')}catch(e){return {}}
}
/* 任务参数里属于「查询参数」的部分（去掉后处理项），回填文本框 / 展示用 */
function prQueryParams(t){
  var p=prParams(t),out={};
  Object.keys(p).forEach(function(k){if(PR_POST.indexOf(k)<0)out[k]=p[k]});
  return out;
}
function prParamsText(t){
  var p=prQueryParams(t),ks=Object.keys(p);
  if(!ks.length)return '';
  return ks.sort().map(function(k){return esc(k)+'='+esc(p[k])}).join('&');
}
function prQueryString(t){
  var p=prQueryParams(t),ks=Object.keys(p);
  return ks.sort().map(function(k){return k+'='+p[k]}).join('&');
}
function prRateText(){
  var m=_prMeta||{};
  if(m.hit_rate===null||m.hit_rate===undefined)return '-';
  return (m.hit_rate*100).toFixed(1)+'%';
}
function refreshPrerender(){
  var list=document.getElementById('pr-list');
  if(list&&!list.querySelector('table'))list.innerHTML='<span class="dim small">'+T('msg.loading','加载中...')+'</span>';
  R.get('/admin/api/prerender/tasks').then(function(d){
    if(d.success===false){if(list)list.innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    _prTasks=d.tasks||[];_prMeta=d;
    prRenderInfo();prRenderMetrics();prRenderCacheMetrics();prRenderList();
  });
}
function prRenderInfo(){
  var el=document.getElementById('pr-info');if(!el)return;
  var m=_prMeta||{};
  var state=m.enabled?'<b>'+T('prerender.state_on','已启用')+'</b>':'<b>'+T('prerender.state_off','已停用')+'</b>';
  var running=(m.running&&m.running.length)?T('prerender.info_running',' · <b>执行中 {n}</b>',{n:m.running.length}):'';
  el.innerHTML=T('prerender.info','调度 {state} · 轮询 {tick} 秒{running}',{state:state,tick:num(m.tick_seconds),running:running});
}
/* 两张 KPI 行都放 4 项：栅格按项目数均分宽度，项目数不同会让两行卡片宽度对不上 */
function prRenderMetrics(){
  var el=document.getElementById('pr-metrics');if(!el)return;
  var m=_prMeta||{},tasks=_prTasks||[],enabled=0;
  tasks.forEach(function(t){if(t.enabled)enabled++});
  // 「执行中」不在此重复：page-head 的调度信息里已经带了「执行中 N」
  el.innerHTML=kpi(T('prerender.kpi_tasks','任务数'),num(tasks.length))+
    kpi(T('prerender.kpi_enabled','启用中'),num(enabled))+
    kpi(T('prerender.kpi_hits','命中次数'),num(m.total_hits))+
    kpi(T('prerender.kpi_hit_rate','命中率'),prRateText());
}
function prRenderCacheMetrics(){
  var el=document.getElementById('pr-cache-metrics');if(!el)return;
  var m=_prMeta||{},c=m.cache||{};
  function cap(text){return ' <span class="sub">/ '+text+'</span>'}
  // 命中率是任务视角（命中 / 请求），只在「定时任务」卡片出现，同一数值不重复展示
  el.innerHTML=kpi(T('prerender.kpi_cache_rows','缓存条数'),num(c.rows)+cap(T('prerender.cache_max_rows','{n} 条',{n:num(m.cache_max_rows)})))+
    kpi(T('prerender.kpi_cache_bytes','占用空间'),fmtBytes(c.bytes)+cap(num(m.cache_max_mb)+' MB'))+
    kpi(T('prerender.kpi_cache_avg','平均单张'),c.rows?fmtBytes(c.bytes/c.rows):'-')+
    kpi(T('prerender.kpi_cache_expired','待回收条数'),num(m.expired_rows));
}
/* 定时任务列表：任务只会越加越多，5 条一页 */
function prRenderList(){
  var list=document.getElementById('pr-list');if(!list)return;
  var running=(_prMeta.running||[]);
  if(!_prTasks.length){
    list.innerHTML='<div class="empty">'+T('prerender.empty','暂无定时任务，点右上角「新建任务」把变化慢的视图提前渲染好')+'</div>';
    return;
  }
  // 列表只留一眼能扫的关键值；路由明细、参数、耗时、错误原因等一律进「详情」弹窗
  // 操作列不写死宽度：5 个按钮的实际宽度由文字决定，固定 200px 一定放不下，
  // 会被 .acts 的 nowrap 撑成横向滚动。.col-act 让浏览器按内容收窄该列。
  var pg=pgSlice(_prTasks,'pr-tasks',5);
  var h='<table><thead><tr><th>'+T('prerender.col_task','任务')+'</th><th>'+T('prerender.col_sched','排期')+'</th><th class="num">'+T('prerender.col_hit_run','命中 / 执行')+'</th>'+
    '<th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(t){
    var isRunning=running.indexOf(t.id)>=0;
    // 停用只标 .off（压淡内容列），操作按钮保持常态，否则像被禁用却还能点
    h+='<tr'+(t.enabled?'':' class="off"')+'>';
    // 详情入口挂在整格上：整格可点比只有任务名可点更好找，.lnk 给 hover 反馈
    h+='<td class="lnk" data-act="pr-detail" data-id="'+t.id+'">'+
       '<div class="strong">'+esc(t.name)+' '+prBadge(t.last_status,t.last_error)+'</div>'+
       '<div class="dim small">'+esc(t.route_path)+(t.size?' ['+esc(t.size)+']':'')+
       (t.enabled?'':T('prerender.row_disabled',' · 已停用'))+(parseInt(t.cache_ttl_hours)>0?T('prerender.row_ttl',' · 寿命 {n} 小时',{n:num(t.cache_ttl_hours)}):'')+'</div></td>';
    h+='<td>'+prScheduleText(t)+'</td>';
    h+='<td class="mono num">'+num(t.hit_count)+' / '+num(t.run_count)+'</td>';
    h+='<td><div class="flex"><button class="btn btn-sm btn-ghost" data-act="pr-run" data-id="'+t.id+'"'+
       (isRunning?' disabled':'')+'>'+(isRunning?T('prerender.btn_running','执行中…'):T('prerender.btn_run','立即执行'))+'</button>'+
       '<button class="btn btn-sm btn-ghost" data-act="pr-preview" data-id="'+t.id+'">'+T('prerender.btn_preview','预览')+'</button>'+
       '<button class="btn btn-sm btn-ghost" data-act="pr-edit" data-id="'+t.id+'">'+T('core.edit','编辑')+'</button>'+
       '<button class="btn btn-sm btn-ghost" data-act="pr-toggle" data-id="'+t.id+'" data-en="'+(t.enabled?1:0)+'">'+
       (t.enabled?T('prerender.btn_disable','停用'):T('prerender.btn_enable','启用'))+'</button>'+
       '<button class="btn btn-sm btn-ghost" data-act="pr-del" data-id="'+t.id+'">'+T('btn.delete','删除')+'</button></div></td>';
    h+='</tr>';
  });
  list.innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender['pr-tasks']=prRenderList;
}
function prTaskById(id){
  for(var i=0;i<_prTasks.length;i++)if(_prTasks[i].id===id)return _prTasks[i];
  return null;
}
/* ---------- 新建 / 编辑弹窗 ---------- */
/* 表单只有「路径 + 查询参数 + 排期」：与「测试」页同款，旋转/反色/cmode/格式由每个请求自己带 */
function showPrerenderModal(id){
  var t=id?prTaskById(id):null;
  if(id&&!t){toast(T('prerender.not_found','任务不存在'),'error');return}
  var h='<h3>'+(t?T('prerender.modal_edit_title','编辑任务'):T('prerender.modal_new_title','新建定时任务'))+'</h3>';
  h+='<div class="cd">'+T('prerender.modal_desc','到点自动渲染一次并存入成品缓存；之后同路径、同业务参数的请求直接命中，旋转、反色、cmode 与输出格式由每个请求自己带，不再重新渲染。')+'</div>';
  h+='<label>'+T('prerender.label_name','任务名称')+'</label><input class="input" id="pr-name" placeholder="'+T('prerender.ph_name','留空则自动命名')+'" value="'+esc(t?t.name:'')+'" style="width:100%">';
  h+='<label>'+T('prerender.label_path','请求路径')+'</label><input class="input mono" id="pr-path" placeholder="'+T('prerender.ph_path','/插件/view/视图名 或 /插件/json/名称')+'" value="'+
     esc(t?t.route_path:'')+'" style="width:100%">';
  h+='<label>'+T('prerender.label_params','查询参数（视图必须带 size，用 &amp; 分隔）')+'</label>'+
     '<input class="input mono" id="pr-params" placeholder="size=hxl&amp;city=beijing" value="'+esc(t?prQueryString(t):'')+'" style="width:100%">';
  h+='<label>'+T('prerender.label_ttl','缓存寿命（小时，填 0 或留空 = 不过期）')+'</label><input class="input mono" id="pr-ttl" value="'+
     esc(t?(parseInt(t.cache_ttl_hours)||0):0)+'" style="width:100%">';
  var st=prSchedType(t);
  h+='<label>'+T('prerender.label_sched_type','排期方式')+'</label><select class="input" id="pr-stype" style="width:100%">'+
     '<option value="interval"'+(st==='interval'?' selected':'')+'>'+T('prerender.opt_interval','固定间隔')+'</option>'+
     '<option value="daily"'+(st==='daily'?' selected':'')+'>'+T('prerender.opt_daily','每日时刻')+'</option>'+
     '<option value="cron"'+(st==='cron'?' selected':'')+'>'+T('prerender.opt_cron','Cron 表达式')+'</option></select>';
  h+='<div id="pr-int-row"><label>'+T('prerender.label_interval','间隔秒数（最小 10）')+'</label><input class="input mono" id="pr-interval" value="'+
     esc(t?t.interval_seconds:600)+'" style="width:100%"></div>';
  h+='<div id="pr-daily-row"><label>'+T('prerender.label_daily','每日时刻 HH:MM（可填多个，用空格或逗号分隔，按配置时区）')+'</label>'+
     '<input class="input mono" id="pr-daily" placeholder="10:00 12:00 15:00" value="'+
     esc(t?String(t.daily_time||'').replace(/,/g,' '):'')+'" style="width:100%"></div>';
  h+='<div id="pr-cron-row"><label>'+T('prerender.label_cron','Cron 表达式（分 时 日 月 周，按配置时区）')+'</label>'+
     '<input class="input mono" id="pr-cron" placeholder="0 8 * * 1-5" value="'+
     esc(t?String(t.cron_expr||''):'')+'" style="width:100%">'+
     '<div class="dim small">'+T('prerender.cron_hint','支持 *、n、a-b、*/n、a-b/n 与逗号列表；如 */15 * * * * 每 15 分钟、0 8 * * 1-5 工作日 8:00。日与星期同时限定时按标准 cron 取「或」。')+'</div></div>';
  h+='<div class="ck-list"><label><input type="checkbox" id="pr-enabled"'+
     (!t||t.enabled?' checked':'')+'>'+T('prerender.btn_enable','启用')+'</label></div>';
  h+='<div class="modal-actions"><button class="btn btn-primary" data-act="pr-save" data-id="'+(t?t.id:0)+'">'+T('btn.save','保存')+'</button></div>';
  var ov=openModal(h,'pr-modal');
  function fillSchedule(){
    var v=ov.querySelector('#pr-stype').value;
    ov.querySelector('#pr-int-row').style.display=v==='interval'?'':'none';
    ov.querySelector('#pr-daily-row').style.display=v==='daily'?'':'none';
    ov.querySelector('#pr-cron-row').style.display=v==='cron'?'':'none';
  }
  ov.querySelector('#pr-stype').addEventListener('change',fillSchedule);
  fillSchedule();
  modalForm(ov,function(){prSave(ov.querySelector('[data-act="pr-save"]'))});
}
/* 路径 → (插件名, 规范化路由)；插件名必须是路径第一段，否则后端会拒 */
function prSplitPath(text){
  var seg=String(text||'').trim().replace(/^\/+|\/+$/g,'').split('/').filter(function(s){return s});
  return {plugin:seg[0]||'',path:'/'+seg.join('/')};
}
function prSave(btn){
  var ov=btn.closest('.modal-overlay');if(!ov)return;
  var id=parseInt(btn.dataset.id)||0;
  var target=prSplitPath(ov.querySelector('#pr-path').value);
  if(!target.plugin){toast(T('prerender.need_path','请填写请求路径，如 /weather/view/summary'),'error');return}
  var body={
    name:ov.querySelector('#pr-name').value.trim(),
    plugin_name:target.plugin,
    route_path:target.path,
    params:parseParamString(ov.querySelector('#pr-params').value),
    cache_ttl_hours:parseInt(ov.querySelector('#pr-ttl').value)||0,
    schedule_type:ov.querySelector('#pr-stype').value,
    interval_seconds:parseInt(ov.querySelector('#pr-interval').value)||0,
    daily_time:ov.querySelector('#pr-daily').value.trim(),
    cron_expr:ov.querySelector('#pr-cron').value.trim(),
    enabled:ov.querySelector('#pr-enabled').checked,
  };
  btnBusy(btn,true);
  var p=id?R.put('/admin/api/prerender/tasks/'+id,body):R.post('/admin/api/prerender/tasks',body);
  p.then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    ov.remove();toast(id?T('prerender.updated','任务已更新'):T('prerender.created','任务已创建'),'success');refreshPrerender();
  });
}
function prRun(id,btn){
  btnBusy(btn,true,T('prerender.btn_running','执行中…'));
  R.post('/admin/api/prerender/tasks/'+id+'/run').then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    var t=d.task||{};
    if(t.last_status==='rendered')toast(T('prerender.run_done','渲染完成，耗时 {n}ms',{n:parseInt(t.last_ms)||0}),'success');
    else toast(t.last_error||T('prerender.run_failed','任务未成功执行'),'warn');
    refreshPrerender();
  });
}
/* 启停只是改一个字段，但接口是整体覆盖：用任务自身现存的字段拼回一份完整请求体 */
function prTaskBody(t,enabled){
  return {name:t.name,plugin_name:t.plugin_name,route_path:t.route_path,
    params:prQueryParams(t),cache_ttl_hours:parseInt(t.cache_ttl_hours)||0,
    schedule_type:t.schedule_type,interval_seconds:t.interval_seconds,
    daily_time:t.daily_time,cron_expr:t.cron_expr||'',enabled:enabled};
}
function prToggle(id,enable){
  var t=prTaskById(id);if(!t)return;
  R.put('/admin/api/prerender/tasks/'+id,prTaskBody(t,enable)).then(function(d){
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    toast(enable?T('prerender.enabled_done','任务已启用'):T('prerender.disabled_done','任务已停用'),'success');refreshPrerender();
  });
}
function prDel(id){
  var t=prTaskById(id);if(!t)return;
  uiConfirm({title:T('prerender.del_title','删除定时任务'),message:T('prerender.del_msg','将同时删除该任务的成品缓存：{name}',{name:t.name}),
    confirmText:T('btn.delete','删除'),danger:true}).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/prerender/tasks/'+id).then(function(d){
      if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      toast(T('prerender.del_done','任务已删除'),'success');refreshPrerender();
    });
  });
}
function prClearCache(){
  uiConfirm({title:T('prerender.clear_cache_title','清空成品缓存'),message:T('prerender.clear_cache_msg','所有任务的成品产物都会被删除（任务保留，下个周期会重新生成）'),
    confirmText:T('prerender.clear_confirm','清空'),danger:true}).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/prerender/tasks/clear-cache').then(function(d){
      if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      toast(T('prerender.cleared','已清空 {n} 条缓存',{n:num(d.deleted)}),'success');refreshPrerender();
    });
  });
}
/* ---------- 详情弹窗：列表里省略的信息都放这里 ---------- */
function prDetail(id){
  var t=prTaskById(id);if(!t)return;
  var isView=String(t.route_kind)!=='json';
  function row(k,v){return '<div class="info-item"><span class="ik">'+esc(k)+'</span><span class="iv">'+v+'</span></div>'}
  var h='<h3>'+esc(t.name)+'</h3>';
  h+='<div class="info-grid">';
  h+='<div class="info-item"><span class="ik">'+T('prerender.detail_target','目标')+'</span><span class="iv mono">'+esc(t.route_path)+'</span></div>';
  h+=row(T('prerender.detail_kind','类型'),isView?T('prerender.kind_view','视图')+(t.size?' ['+esc(t.size)+']':''):'JSON');
  h+=row(T('prerender.col_sched','排期'),prScheduleText(t));
  h+=row(T('prerender.detail_state','状态'),t.enabled?T('prerender.state_on','已启用'):T('prerender.state_off','已停用'));
  h+=row(T('prerender.detail_ttl','缓存寿命'),parseInt(t.cache_ttl_hours)>0?T('prerender.hours','{n} 小时',{n:num(t.cache_ttl_hours)}):T('prerender.no_expire','不过期'));
  h+='<div class="info-item"><span class="ik">'+T('prerender.detail_next','下次执行')+'</span><span class="iv mono">'+esc(fmtDT(t.next_run_at))+'</span></div>';
  h+='<div class="info-item"><span class="ik">'+T('prerender.legend_last','上次执行')+'</span><span class="iv mono">'+esc(fmtDT(t.last_run_at))+'</span></div>';
  h+='<div class="info-item"><span class="ik">'+T('prerender.detail_result','执行结果')+'</span><span class="iv">'+prBadge(t.last_status,t.last_error)+'</span></div>';
  h+=row(T('prerender.detail_render_ms','渲染耗时'),t.last_ms?(parseInt(t.last_ms)||0)+' ms':'-');
  h+='<div class="info-item"><span class="ik">'+T('prerender.col_hit_run','命中 / 执行')+'</span><span class="iv mono">'+num(t.hit_count)+' / '+num(t.run_count)+'</span></div>';
  h+='<div class="info-item"><span class="ik">'+T('prerender.detail_created','创建时间')+'</span><span class="iv mono">'+esc(fmtDT(t.created_at))+'</span></div>';
  h+='</div>';
  // 失败原因要有标签：与下面「查询参数 / 成品缓存」两节保持同样的小标题，别只丢一段红字
  if(t.last_error)h+='<label>'+T('prerender.detail_error','失败原因')+'</label><div class="panel err">'+esc(t.last_error)+'</div>';
  h+='<label>'+T('prerender.detail_params','查询参数')+'</label><div class="panel mono" style="word-break:break-all">'+
     (prParamsText(t)||'<span class="dim">'+T('prerender.none','无')+'</span>')+'</div>';
  h+='<label>'+T('prerender.cache_title','成品缓存')+'</label><div class="panel mono" id="pr-detail-cache"><span class="dim">'+T('prerender.loading_detail','读取中…')+'</span></div>';
  h+='<div class="modal-actions">'+
     '<button class="btn btn-primary" data-act="pr-preview" data-id="'+t.id+'">'+T('prerender.btn_preview_art','预览成品')+'</button></div>';
  var ov=openModal(h,'pr-detail');
  // 成品信息要查缓存行，单独取一次；没有成品是正常状态，不当错误弹
  R.get('/admin/api/prerender/tasks/'+id+'/preview?meta=1').then(function(d){
    var el=ov.querySelector('#pr-detail-cache');if(!el)return;
    if(d.success===false){el.innerHTML='<span class="dim">'+T('prerender.no_art','尚无成品，先执行一次任务')+'</span>';return}
    var kind=d.art_kind==='json'?'JSON':(d.art_kind==='rgb'?T('prerender.art_rgb','RGB 图'):T('prerender.art_index','索引图'));
    el.innerHTML=T('prerender.meta_line','{kind} · {w}×{h} · {bytes} · 渲染 {ms}ms · 生成 {rendered} · 最近命中 {hit}',{kind:esc(kind),w:num(d.width),h:num(d.height),bytes:esc(fmtBytes(d.bytes)),ms:parseInt(d.render_ms)||0,rendered:esc(fmtDT(d.rendered_at)),hit:esc(fmtDT(d.last_hit_at))});
  });
}
/* 预览：先用 meta=1 问清成品是图还是 JSON，图片再交给 <img> 直出 */
function prPreview(id){
  var t=prTaskById(id);if(!t)return;
  R.get('/admin/api/prerender/tasks/'+id+'/preview?meta=1').then(function(d){
    if(d.success===false){toast(d.message||T('core.op_failed','操作失败'),'error');return}
    var kind=d.art_kind==='json'?'JSON':(d.art_kind==='rgb'?T('prerender.art_rgb','RGB 图'):T('prerender.art_index','索引图'));
    var h='<h3>'+T('prerender.preview_title','成品预览')+'</h3><div class="cd">'+
      T('prerender.preview_line','{name} · {kind} · {bytes} · 渲染 {ms}ms · {rendered}',{name:esc(t.name),kind:esc(kind),bytes:esc(fmtBytes(d.bytes)),ms:parseInt(d.render_ms)||0,rendered:esc(fmtDT(d.rendered_at))})+'</div>';
    if(d.art_kind==='json'){
      h+='<textarea class="input mono" rows="16" readonly style="width:100%">'+esc(d.text)+'</textarea>';
    }else{
      // 预览的是缓存里的索引图本身：它是内部存储编码，与「png 输出格式是否被禁用」无关。
      // 加时间戳绕过浏览器缓存，否则改了参数看到的还是旧图
      h+='<div class="panel pv"><img alt="'+T('prerender.alt_art','成品图')+'" src="/admin/api/prerender/tasks/'+id+
        '/preview?t='+Date.now()+'"></div>';
    }
    openModal(h,'pr-preview');
  });
}
'''