# JS 插件页（含接口测试）
ADMIN_JS_PLUGINS = r'''/* ================= 插件 ================= */
var _pluginRoutes={};
/* 清单字段的悬停说明：最低框架版本 + 依赖（python 依赖只是「建议」，不强制安装） */
function manifestTip(p){
  var d=p.dependencies||{};var lines=[];
  if(p.author)lines.push(T('plugin.tip_author','作者: {name}',{name:p.author}));
  if(p.min_framework_version)lines.push(T('plugin.tip_min_fw','最低框架版本: {ver}',{ver:p.min_framework_version}));
  if((d.plugins||[]).length)lines.push(T('plugin.tip_dep_plugins','依赖插件: {list}',{list:d.plugins.join(', ')}));
  if((d.python||[]).length)lines.push(T('plugin.tip_sug_python','建议依赖: {list}',{list:d.python.join(', ')}));
  return lines.join('\n')||T('plugin.tip_none','未声明额外信息');
}
function refreshPlugins(){
  R.get('/admin/api/plugins').then(function(d){
    _pluginRoutes=d.routes||{};
    var ps=d.plugins||[];var disabledCount=0;
    ps.forEach(function(p){if(!p.enabled)disabledCount++});
    var dot=document.getElementById('plugins-dot');
    dot.style.display=disabledCount>0?'inline-block':'none';
    dot.title=T('plugin.disabled_count','{n} 个已禁用',{n:disabledCount});
    var h='<table><thead><tr><th>'+T('nav.plugins','插件')+'</th><th>'+T('stats.col_version','版本')+'</th><th>'+T('plugin.col_desc','描述')+'</th><th class="num">'+T('plugin.col_routes','路由')+'</th><th class="col-state">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
    ps.forEach(function(p){
      h+='<tr><td class="strong">'+esc(p.name)+'</td>';
      // 版本与依赖来自 plugin.json；没写清单的插件不能装作有版本，直接说明未声明
      if(p.manifest_missing)h+='<td class="dim" title="'+T('plugin.no_manifest_tip','该插件没有 plugin.json')+'">'+T('plugin.no_manifest','未声明清单')+'</td>';
      else h+='<td class="mono" title="'+esc(manifestTip(p))+'">'+esc(p.version||'—')+'</td>';
      h+='<td class="dim">'+esc(p.description||'')+'</td><td class="dim num">'+T('plugin.route_count','{n} 条',{n:p.route_count})+'</td>';
      h+='<td><span class="sw'+(p.enabled?' on':'')+'" data-act="plugin-toggle" data-name="'+esc(p.name)+'"><span class="sw-track"></span>'+(p.enabled?T('user.enabled','启用'):T('user.disabled','禁用'))+'</span></td>';
      h+='<td><div class="acts"><button class="btn btn-sm" data-act="plugin-routes" data-name="'+esc(p.name)+'">'+T('plugin.col_routes','路由')+'</button>'+
        '<button class="btn btn-sm" data-act="plugin-config" data-name="'+esc(p.name)+'">'+T('nav.config','设置')+'</button>'+
        '<span class="sep"></span>'+
        '<button class="btn btn-sm btn-danger" data-act="plugin-uninstall" data-name="'+esc(p.name)+'">'+T('plugin.uninstall','卸载')+'</button></div></td></tr>';
    });
    h+='</tbody></table>';
    var fs=d.failures||[];
    if(fs.length){
      h+='<div class="card-desc err-text" style="margin:14px 0 6px">'+T('plugin.failures_intro','以下插件加载失败：')+'</div>'+
        '<table><thead><tr><th class="col-state">'+T('nav.plugins','插件')+'</th><th>'+T('stats.col_errors','错误')+'</th></tr></thead><tbody>';
      fs.forEach(function(f){
        h+='<tr><td class="strong">'+esc(f.name)+'</td><td class="dim mono">'+esc(f.error||'')+'</td></tr>';
      });
      h+='</tbody></table>';
    }
    document.getElementById('plugins-area').innerHTML=h;
  });
}
/* 热重载：重扫插件目录 + 重建路由 + 清插件代码缓存，改完插件代码不必重启服务 */
function reloadPlugins(btn){
  uiConfirm({title:T('plugin.reload_title','热重载插件'),message:T('plugin.reload_confirm','将重扫插件目录并重建路由，确定继续？'),confirmText:T('plugin.reload_btn','重载')}).then(function(ok){
    if(!ok)return;
    btnBusy(btn,true);
    R.post('/admin/api/plugins/reload',{}).then(function(d){
      btnBusy(btn,false);
      refreshPlugins();
      if(d&&d.success===false){toast(d.message||T('plugin.reload_failed','重载失败'),'error');return}
      if(d.failed>0)toast(T('plugin.reload_partial','已加载 {loaded}/{total}，{failed} 个失败',{loaded:d.loaded,total:d.total,failed:d.failed}),'error');
      else toast(T('plugin.reload_done','已重载 {n} 个插件',{n:d.loaded}),'success');
    }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
/* 添加插件：先把文件取到局部变量再清空 input，同一个文件连选两次也能再次触发 change。
   body 走裸二进制，不能走 R.post（它会做 JSON 序列化） */
function addPlugin(input){
  var f=input.files&&input.files[0];input.value='';
  if(!f){toast(T('plugin.install_pick','请选择 zip 文件'),'error');return}
  uiConfirm({
    title:T('plugin.install_title','添加插件'),danger:true,confirmText:T('plugin.install','添加'),
    message:T('plugin.install_confirm','包内代码将以服务进程权限执行，确定添加？')
  }).then(function(ok){if(ok)uploadPluginZip(f,false)});
}
function uploadPluginZip(f,replace){
  fetch('/admin/api/plugins/install'+(replace?'?replace=1':''),{
    method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f
  }).then(function(r){
    return r.json().then(function(d){return {status:r.status,data:d||{}}},function(){
      return {status:r.status,data:{success:false,message:T('msg.session_expired','请求失败或会话已失效，请重新登录')}}
    });
  }).then(function(res){
    var d=res.data;
    if(d.success===false){
      // 409 = 同名插件已存在，转成二次确认的「覆盖」
      if(res.status===409)confirmReplacePlugin(f,d.name);
      else toast(d.message||T('core.op_failed','操作失败'),'error');
      return;
    }
    refreshPlugins();
    var rl=d.reload||{};
    if(rl.failed>0){
      toast(T('plugin.install_loaded_but_failed','{name} 加载失败',{name:d.name}),'error');
      showAddFailures(d.name,rl.failures||[]);
    }else toast(T('plugin.install_done','{name} 已添加',{name:d.name}),'success');
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
function confirmReplacePlugin(f,name){
  uiConfirm({
    title:T('plugin.install_exists_title','插件已存在'),danger:true,confirmText:T('plugin.install_overwrite','覆盖'),
    message:T('plugin.install_exists_confirm','将替换插件 {name}，旧版本会被删除。确定继续？',{name:name})
  }).then(function(ok){if(ok)uploadPluginZip(f,true)});
}
/* 已落盘但导入失败：列出具体导入错误 */
function showAddFailures(name,failures){
  var h='<h3>'+esc(T('plugin.install_failures_title','{name} · 加载失败',{name:name}))+'</h3>';
  h+='<table style="margin-top:12px"><thead><tr><th>'+T('nav.plugins','插件')+'</th><th>'+T('stats.col_errors','错误')+'</th></tr></thead><tbody>';
  failures.forEach(function(f){
    h+='<tr><td class="strong">'+esc(f.name||'')+'</td><td class="dim mono">'+esc(f.error||'')+'</td></tr>';
  });
  h+='</tbody></table>';
  openModal(h,'install-fail-modal');
}
/* 卸载：直接删除插件目录，不留备份 */
function uninstallPlugin(name,btn){
  uiConfirm({
    title:T('plugin.uninstall_title','卸载插件'),danger:true,confirmText:T('plugin.uninstall','卸载'),
    message:T('plugin.uninstall_confirm','确定卸载 {name}？',{name:name})
  }).then(function(ok){
    if(!ok)return;
    btnBusy(btn,true);
    R.post('/admin/api/plugins/'+encodeURIComponent(name)+'/uninstall',{}).then(function(d){
      btnBusy(btn,false);
      if(!d.success){toast(d.message||T('core.op_failed','操作失败'),'error');return}
      refreshPlugins();
      toast(T('plugin.uninstall_done','{name} 已卸载',{name:name}),'success');
    }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
  });
}
function togglePlugin(name,el){
  btnBusy(el,true);
  R.post('/admin/api/plugins/'+encodeURIComponent(name)+'/toggle',{}).then(function(d){
    btnBusy(el,false);
    if(d.success){refreshPlugins();toast(d.enabled?T('plugin.enabled_done','{name} 已启用',{name:name}):T('plugin.disabled_done','{name} 已禁用',{name:name}),'success')}
    else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(el,false);toast(T('msg.network_error','网络错误'),'error')});
}
function showPluginRoutes(pname){
  var routes=_pluginRoutes[pname]||[];
  var h='<h3>'+esc(T('plugin.routes_title','{name} · 路由管理',{name:pname}))+'</h3><p class="dim small modal-sub">'+T('plugin.routes_sub','关闭后该路由立即返回不可用')+'</p>';
  // 状态列只有圆点，含义在这里说明（与页面卡片、其它表格同一套图例写法）
  h+='<div class="dot-legend"><div class="lg-row"><em>'+T('user.legend_status','状态')+'</em>'+
    '<span class="lg-item"><i class="dot dot-on"></i>'+T('user.enabled','启用')+'</span>'+
    '<span class="lg-item"><i class="dot dot-off"></i>'+T('user.disabled','禁用')+'</span></div></div>';
  if(!routes.length){h+='<div class="empty">'+T('plugin.no_routes','该插件暂无路由')+'</div>'}
  else{
    h+='<table style="margin-top:12px"><thead><tr><th>'+T('test.col_path','路径')+'</th><th class="col-dot">'+T('user.legend_status','状态')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
    routes.forEach(function(r){
      h+='<tr><td class="mono ellip" title="'+esc(r.path)+'">'+esc(r.path)+'</td>';
      h+='<td class="col-dot">'+dotHtml(r.disabled?'dot-off':'dot-on',r.disabled?T('user.disabled','禁用'):T('user.enabled','启用'))+'</td>';
      h+='<td><span class="sw sm'+(r.disabled?'':' on')+'" data-act="route-toggle" data-path="'+esc(r.path)+'" data-en="'+(r.disabled?'0':'1')+'"><span class="sw-track"></span></span></td></tr>';
    });
    h+='</tbody></table>';
  }
  openModal(h,'route-modal');
}
function toggleRoute(path,enabled,btn){
  btnBusy(btn,true);
  R.post('/admin/api/routes/toggle',{path:path,enabled:enabled}).then(function(d){
    btnBusy(btn,false);
    if(d.success){
      var tr=btn.closest('tr');if(tr){
        // 状态列已改成只有圆点：这里只换颜色类名，不再写文字（写文字会把图例约定破坏掉）
        var badge=tr.querySelector('.dot');
        if(badge)badge.className='dot '+(enabled?'dot-on':'dot-off');
      }
      btn.classList.toggle('on',enabled);
      btn.dataset.en=enabled?'1':'0';
      toast(enabled?T('plugin.enabled_done','{name} 已启用',{name:path.substring(0,40)}):T('plugin.disabled_done','{name} 已禁用',{name:path.substring(0,40)}),'success');
    }else toast(d.message||T('core.op_failed','操作失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
/* 配置项的可读名：插件在 plugin_config.py 的 CONFIG_LABELS 里自报，未登记才回落键名 */
var _pcfgLabels={};
/* 当前生效的配置值：字典 / 数组项的编辑弹窗要靠它取初值，不必再发一次请求 */
var _pcfgConfig={};
function _pcfgLabel(key){var m=_pcfgLabels[key];return (m&&m.label)||key}
function showPluginConfig(pname){
  R.get('/admin/api/plugins/'+encodeURIComponent(pname)+'/config').then(function(d){
    var cfg=d.config||{},overrides=d.overrides||{},labels=d.labels||{};
    _pcfgLabels=labels;_pcfgConfig=cfg;
    var keys=Object.keys(cfg);
    var h='<h3>'+esc(T('plugin.config_title','{name} · 插件配置',{name:pname}))+'</h3>';
    if(!keys.length){h+='<div class="empty">'+T('plugin.no_config','该插件无 plugin_config.py 或配置为空')+'</div>'}
    else{
      keys.forEach(function(k){
        var v=cfg[k];var isOv=overrides[k]!==undefined;var meta=labels[k]||{};
        var badge=isOv?' <span class="badge badge-custom" style="margin-left:4px">'+T('plugin.override_badge','已修改')+'</span>':'';
        var rst=isOv?'<button class="btn btn-sm btn-danger" data-act="pcfg-reset" data-plugin="'+esc(pname)+'" data-key="'+esc(k)+'">'+T('core.reset','还原')+'</button>':'';
        // 面板显示插件自报的中文名，键名只留在悬停提示里（不是给人读的展示文本）
        h+='<label title="'+esc(k)+'">'+esc(meta.label||k)+badge+
          (meta.desc?'<span class="pcfg-desc">'+esc(meta.desc)+'</span>':'')+'</label>';
        // 布尔项用开关，不让用户手打 True/False。这里不做即时保存：本弹窗是表单语义，
        // 由底部「保存全部」或行内「保存」统一提交，混进即时保存会让按钮行为不可预期
        if(typeof v==='boolean'){
          h+='<div class="flex"><span class="sw'+(v?' on':'')+'" data-act="pcfg-sw" data-key="'+esc(k)+'" data-val="'+(v?'1':'0')+'">'+
            '<span class="sw-track"></span><span class="sw-tx">'+(v?T('core.on','开启'):T('core.off','关闭'))+'</span></span>'+rst+
            '<button class="btn btn-sm" data-act="pcfg-save" data-plugin="'+esc(pname)+'" data-key="'+esc(k)+'">'+T('btn.save','保存')+'</button></div>';
        }else if(v&&typeof v==='object'){
          // 字典 / 数组值不在行内编辑：JSON 挤进单行输入框既看不全也改不动。
          // 行里只放一段只读预览，真正的编辑交给弹窗里的等宽文本框
          var disp=JSON.stringify(v);
          h+='<div class="flex"><span class="pcfg-json mono" title="'+esc(disp)+'">'+esc(disp)+'</span>'+rst+
            '<button class="btn btn-sm" data-act="pcfg-json" data-plugin="'+esc(pname)+'" data-key="'+esc(k)+'">'+T('core.edit','编辑')+'</button></div>';
        }else{
          var disp=String(v);
          h+='<div class="flex"><input class="input" id="pcfg-'+esc(k)+'" value="'+esc(disp)+'" style="flex:1">'+rst+
            '<button class="btn btn-sm" data-act="pcfg-save" data-plugin="'+esc(pname)+'" data-key="'+esc(k)+'">'+T('btn.save','保存')+'</button></div>';
        }
      });
      h+='<div class="modal-actions"><button class="btn btn-primary" data-act="pcfg-save-all" data-plugin="'+esc(pname)+'">'+T('plugin.save_all','保存全部')+'</button></div>';
    }
    openModal(h,'pcfg-modal');
  });
}
/* 开关翻转只是改本地待提交值，不落库；data-val 就是提交时要写的值 */
function pcfgFlip(el){
  var on=el.dataset.val!=='1';
  el.dataset.val=on?'1':'0';
  el.classList.toggle('on',on);
  var tx=el.querySelector('.sw-tx');if(tx)tx.textContent=on?T('core.on','开启'):T('core.off','关闭');
}
function _pcfgSw(key){
  var m=document.getElementById('pcfg-modal');if(!m)return null;
  var sws=m.querySelectorAll('[data-act="pcfg-sw"]');
  for(var i=0;i<sws.length;i++)if(sws[i].dataset.key===key)return sws[i];
  return null;
}
/* 弹窗里全部待提交字段：文本输入框 + 布尔开关 */
function _pcfgItems(m){
  var out=[];
  m.querySelectorAll('input[id^="pcfg-"]').forEach(function(el){out.push({key:el.id.substring(5),value:el.value})});
  m.querySelectorAll('[data-act="pcfg-sw"]').forEach(function(el){out.push({key:el.dataset.key,value:el.dataset.val==='1'})});
  return out;
}
function savePluginCfg(pname,key,btn){
  var el=document.getElementById('pcfg-'+key);
  var val=el?el.value:null;
  if(!el){
    var sw=_pcfgSw(key);if(!sw)return;
    val=sw.dataset.val==='1';
  }
  btnBusy(btn,true);
  R.post('/admin/api/plugins/'+encodeURIComponent(pname)+'/config',{key:key,value:val}).then(function(d){
    btnBusy(btn,false);
    if(d.success)toast(T('core.saved','{key} 已保存',{key:_pcfgLabel(key)}),'success');else toast(d.message||T('core.save_failed','保存失败'),'error');
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function resetPluginCfg(pname,key){
  uiConfirm({title:T('plugin.reset_title','还原插件配置'),message:T('core.reset_confirm','确定将 {key} 还原为默认值吗？',{key:_pcfgLabel(key)}),confirmText:T('core.reset','还原')}).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/plugins/'+encodeURIComponent(pname)+'/config?key='+encodeURIComponent(key)).then(function(d){
      if(d.success){toast(T('plugin.cfg_reset_done','{key} 已还原',{key:_pcfgLabel(key)}),'success');var m=document.getElementById('pcfg-modal');if(m)m.remove();showPluginConfig(pname)}
      else toast(d.message||T('core.reset_failed','还原失败'),'error');
    });
  });
}
/* 字典 / 数组配置项的编辑弹窗：点「编辑」打开，改完点「保存」当场生效。
   提交的是文本框原样的 JSON 文本，服务端 parse_config_value 会还原成 dict / list；
   行内那个只读预览不参与提交，所以「保存全部」管不到它（它有自己的保存按钮） */
function pcfgEditJson(pname,key){
  var v=_pcfgConfig[key];
  var meta=_pcfgLabels[key]||{};
  var isArr=Object.prototype.toString.call(v)==='[object Array]';
  var hint=isArr?T('plugin.json_hint_arr','JSON 数组；保存后立即生效'):T('plugin.json_hint_obj','JSON 对象；保存后立即生效');
  var h='<h3>'+esc(pname)+' · '+esc(meta.label||key)+'</h3>'+
    (meta.desc?'<p class="dim small modal-sub">'+esc(meta.desc)+'</p>':'')+
    '<label class="mono">'+esc(key)+'</label>'+
    '<textarea class="input mono json-edit" id="pcfg-json-text" rows="10" autocomplete="off" spellcheck="false">'+esc(JSON.stringify(v,null,2))+'</textarea>'+
    '<p class="dim small json-edit-hint" id="pcfg-json-hint">'+esc(hint)+'</p>'+
    '<div class="modal-actions"><button class="btn btn-primary" id="pcfg-json-save">'+T('btn.save','保存')+'</button></div>';
  var m=openModal(h,'pcfg-json-modal');
  var ta=m.querySelector('#pcfg-json-text'),tip=m.querySelector('#pcfg-json-hint');
  var save=m.querySelector('#pcfg-json-save');
  ta.focus();
  function fail(msg){tip.textContent=msg;tip.style.color='var(--red)';tip.style.fontWeight='500'}
  ta.addEventListener('input',function(){tip.textContent=hint;tip.style.color='';tip.style.fontWeight=''});
  save.addEventListener('click',function(){
    var raw=ta.value.trim();
    if(!raw){fail(T('plugin.json_required','不能为空；想恢复默认值请用「还原」'));return}
    // 前端先挡一次格式错误，省得为一个手滑发一趟请求；服务端仍会再校验一遍
    try{JSON.parse(raw)}catch(e){fail(T('core.json_invalid','JSON 格式有误：{msg}',{msg:e.message}));return}
    btnBusy(save,true);
    R.post('/admin/api/plugins/'+encodeURIComponent(pname)+'/config',{key:key,value:raw}).then(function(d){
      btnBusy(save,false);
      if(!d.success){fail(d.message||T('core.save_failed','保存失败'));return}
      toast(T('core.saved','{key} 已保存',{key:_pcfgLabel(key)}),'success');
      m.remove();
      var base=document.getElementById('pcfg-modal');if(base)base.remove();
      showPluginConfig(pname);
    }).catch(function(){btnBusy(save,false);fail(T('msg.network_error','网络错误'))});
  });
}
function saveAllPluginCfg(pname,btn){
  var m=document.getElementById('pcfg-modal');if(!m)return;
  var items=_pcfgItems(m);
  var total=items.length,done=0,ok=0;
  if(!total){m.remove();return}
  btnBusy(btn,true,T('plugin.saving','保存中…'));
  items.forEach(function(it){
    R.post('/admin/api/plugins/'+encodeURIComponent(pname)+'/config',{key:it.key,value:it.value}).then(function(d){
      done++;if(d.success)ok++;
      if(done===total){btnBusy(btn,false);toast(T('plugin.saved_items','已保存 {ok}/{total} 项',{ok:ok,total:total}),ok===total?'success':'warn');m.remove();showPluginConfig(pname)}
    }).catch(function(){done++;if(done===total){btnBusy(btn,false);toast(T('plugin.saved_items','已保存 {ok}/{total} 项',{ok:ok,total:total}),'warn');m.remove();showPluginConfig(pname)}});
  });
}
/* ================= 接口测试 ================= */
var TEST_MODES={single:'test.mode_single',sequence:'test.mode_sequence',concurrent:'test.mode_concurrent'};
function syncTestMode(){
  var m=document.getElementById('t-mode').value;
  var cnt=document.getElementById('t-count'),conc=document.getElementById('t-conc');
  cnt.disabled=(m==='single');
  if(m==='single')cnt.value=1;
  else if((parseInt(cnt.value)||0)<2)cnt.value=2;
  conc.disabled=(m!=='concurrent');
}
function parseParamString(str){
  var params={};
  str.split('&').forEach(function(kv){
    if(!kv)return;var i=kv.indexOf('=');
    if(i<0)params[decodeURIComponent(kv)]='';
    else params[decodeURIComponent(kv.slice(0,i))]=decodeURIComponent(kv.slice(i+1));
  });
  return params;
}
function clearTestResults(){
  document.getElementById('t-summary').innerHTML='';
  document.getElementById('t-summary-note').textContent=T('test.waiting','等待测试');
  document.getElementById('t-results').innerHTML='<div class="empty">'+T('test.no_result','暂无结果')+'</div>';
  document.getElementById('t-payload').textContent=T('test.no_request','尚未发起请求');
  document.getElementById('t-payload-note').textContent=T('test.payload_note','开始测试后展示实际发出的请求');
}
function runTest(btn){
  var path=document.getElementById('t-path').value.trim();
  if(!path){toast(T('test.need_path','请输入请求路径'),'error');return}
  var mode=document.getElementById('t-mode').value;
  var count=Math.max(1,parseInt(document.getElementById('t-count').value)||1);
  var concurrency=Math.max(1,parseInt(document.getElementById('t-conc').value)||4);
  if(mode==='single')count=1;
  document.getElementById('t-summary-note').textContent=T('test.running','测试进行中…');
  document.getElementById('t-results').innerHTML='<div class="empty">'+T('test.running','测试进行中…')+'</div>';
  btnBusy(btn,true,T('test.running_btn','测试中…'));
  R.post('/admin/api/test-route',{
    path:path,params:parseParamString(document.getElementById('t-params').value.trim()),
    mode:mode,count:count,concurrency:concurrency
  }).then(function(d){
    btnBusy(btn,false);
    if(!d.success){document.getElementById('t-summary-note').textContent=T('test.failed','测试失败');document.getElementById('t-results').innerHTML='<div class="empty">'+esc(d.message||T('test.failed','测试失败'))+'</div>';return}
    renderTestPayload(d);renderTestSummary(d);renderTestResults(d);
  }).catch(function(){btnBusy(btn,false);document.getElementById('t-summary-note').textContent=T('test.failed','测试失败');toast(T('msg.network_error','网络错误'),'error')});
}
function renderTestPayload(d){
  var p=d.payload||{},params=p.params||{};
  var qs=Object.keys(params).map(function(k){return k+'='+params[k]}).join('&');
  var lines=['GET '+(p.url||''),
    T('test.payload_params','查询参数: {v}',{v:qs||T('test.payload_none','（无）')}),
    T('test.payload_evkey','evkey: {v}',{v:(p.headers&&p.headers.evkey)||T('test.payload_none','（无）')}),
    T('test.payload_mode','模式: {mode} · 共 {count} 次 · 并发 {conc}',{mode:T(TEST_MODES[d.mode]||d.mode),count:d.count,conc:d.concurrency})];
  document.getElementById('t-payload').textContent=lines.join('\n');
  document.getElementById('t-payload-note').textContent=T('test.payload_target','目标 {url}',{url:p.url||''});
}
function renderTestSummary(d){
  var s=d.summary||{},failed=(s.count||0)-(s.ok||0);
  document.getElementById('t-summary-note').textContent=T('test.summary_note','完成 {count} 次请求，总用时 {ms}ms',{count:s.count,ms:s.total_ms});
  document.getElementById('t-summary').innerHTML=
    kpi(T('test.kpi_count','请求数'),num(s.count))+
    kpi(T('test.kpi_ok_fail','成功 / 失败'),num(s.ok)+' / '+num(failed),failed>0?'red':'')+
    kpi(T('test.kpi_avg','平均耗时'),s.avg_ms+'ms')+
    kpi(T('test.kpi_p95','P95 耗时'),s.p95_ms+'ms')+
    kpi(T('test.kpi_min_max','最快 / 最慢'),s.min_ms+' / '+s.max_ms+'ms')+
    kpi(T('test.kpi_avg_size','平均大小'),fmtSize(s.avg_size));
}
function fmtSize(v){
  if(v==null)return '-';
  if(v>=1048576)return (v/1048576).toFixed(1)+' MB';
  if(v>=1024)return (v/1024).toFixed(1)+' KB';
  return v+' B';
}
/* 测试结果：逐条列出，请求数一多就很长，5 条一页 */
var _testResults=[];
function renderTestResults(d){
  if(d)_testResults=d.results||[];
  var el=document.getElementById('t-results');if(!el)return;
  if(!_testResults.length){el.innerHTML='<div class="empty">'+T('test.no_result','暂无结果')+'</div>';return}
  var pg=pgSlice(_testResults,'t-results',5);
  var h='<table><thead><tr><th class="num">#</th><th class="col-state">'+T('user.legend_status','状态')+'</th><th class="num">'+T('test.col_duration','耗时')+'</th><th class="num">'+T('test.col_size','大小')+'</th><th>'+T('test.col_time','请求时间')+'</th><th>'+T('test.col_type_err','类型 / 错误')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(r){
    var t=fmtDT(r.started_at);
    h+='<tr><td class="dim num">'+r.index+'</td>'+
      '<td class="mono num'+(r.ok?'':' err-text')+'">'+(r.status||'-')+'</td>'+
      '<td class="mono num">'+r.duration_ms+'ms</td>'+
      '<td class="mono dim num">'+fmtSize(r.size)+'</td>'+
      '<td class="mono dim">'+(r.started_at?t.substring(11):'-')+'</td>'+
      '<td>'+(r.error?'<span class="res-err" title="'+esc(r.error)+'">'+esc(r.error)+'</span>':'<span class="dim">'+esc(r.content_type||'-')+'</span>')+'</td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender['t-results']=renderTestResults;
}
/* ================= 接口清单 ================= */
/* 数据由服务端从 app.router.routes 现算（插件热重载、路由开关后刷新一次即可），
   这里只做搜索过滤 + 客户端分页，不再另外维护一份接口表 */
var _adRoutes=[];
function refreshApiDocs(){
  var box=document.getElementById('ad-list');if(!box)return;
  if(!box.querySelector('table'))box.innerHTML='<span class="dim small">'+T('msg.loading','加载中...')+'</span>';
  R.get('/admin/api/api-docs').then(function(d){
    _adRoutes=d.routes||[];
    var note=document.getElementById('ad-note');
    if(note)note.textContent=T('test.api_count','共 {n} 个业务接口',{n:num(_adRoutes.length)});
    adRender();
  }).catch(function(){
    box.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function adSearch(){_pg['api-docs']=1;adRender()}
function adRender(){
  var box=document.getElementById('ad-list');if(!box)return;
  var input=document.getElementById('ad-search');
  var q=(input?input.value:'').trim().toLowerCase();
  var rows=_adRoutes;
  if(q)rows=_adRoutes.filter(function(r){
    return (r.path||'').toLowerCase().indexOf(q)>=0
      ||(r.plugin||'').toLowerCase().indexOf(q)>=0
      ||(r.method||'').toLowerCase().indexOf(q)>=0;
  });
  if(!rows.length){box.innerHTML='<div class="empty">'+(q?T('test.api_no_match','没有匹配的接口'):T('test.api_empty','暂无接口'))+'</div>';return}
  var sl=pgSlice(rows,'api-docs',20);
  var h='<table><thead><tr><th class="col-state">'+T('test.col_method','方法')+'</th><th>'+T('test.col_path','路径')+'</th><th>'+T('nav.plugins','插件')+'</th><th class="col-dot">'+T('test.auth_legend','鉴权')+'</th><th class="col-act">'+T('core.col_action','操作')+'</th></tr></thead><tbody>';
  sl.rows.forEach(function(r){
    var kind=r.kind?esc(r.kind)+(r.name?'/'+esc(r.name):''):'';
    // 路径带 {参数} 的不能直接填进测试框（原样发出去只会 404/422），按钮置灰但保留
    var fill=r.param_path
      ?'<button class="btn btn-sm" disabled title="'+T('test.fill_disabled_tip','路径含 {param}，需替换成实际值后再测')+'">'+T('test.fill_btn','填入测试')+'</button>'
      :'<button class="btn btn-sm" data-act="ad-fill" data-path="'+esc(r.path)+'" title="'+T('test.fill_tip','把该路径填入上方请求配置')+'">'+T('test.fill_btn','填入测试')+'</button>';
    h+='<tr><td class="mono">'+esc(r.method)+'</td>'+
      '<td class="mono ellip" title="'+esc(r.path)+'">'+esc(r.path)+'</td>'+
      '<td'+(r.description?' title="'+esc(r.description)+'"':'')+'>'+
        (r.plugin?'<span class="strong">'+esc(r.plugin)+'</span>':'<span class="dim">—</span>')+
        (kind?' <span class="dim small">'+kind+'</span>':'')+'</td>'+
      '<td class="col-dot">'+(r.need_evkey
        ?dotHtml('dot-on',T('test.evkey_needed_tip','请求头或查询参数需带 evkey'))
        :dotHtml('dot-off',T('test.free_auth_tip','白名单路径，无需 evkey')))+'</td>'+
      '<td><div class="acts">'+fill+
        '<button class="btn btn-sm" data-act="copy-text" data-copy="'+esc(r.path)+'">'+T('btn.copy','复制')+'</button>'+
      '</div></td></tr>';
  });
  box.innerHTML=h+'</tbody></table>'+sl.bar;
  _pgRender['api-docs']=adRender;
}
function adFill(path){
  var inp=document.getElementById('t-path');if(!inp)return;
  inp.value=path;
  var pg=document.getElementById('page-test');
  if(pg)pg.scrollIntoView({behavior:'smooth',block:'start'});
  toast(T('test.filled','已填入请求路径'),'success');
}
'''