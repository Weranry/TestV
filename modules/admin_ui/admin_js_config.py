# JS 设置页（主从布局：左分类菜单 + 右配置项）
ADMIN_JS_CONFIG = r'''/* ================= 设置页 ================= */
/* 分类的展示顺序。值是 CONFIG_LABELS 里的 category 中文原名（前端拿它分组/排序，不翻），
   别的语言由后端下发的 category_label 显示。
   与旧版「按类别平铺」的关键差别：**不再有跳过项**——原先散在各分页的配置卡片
   （鉴权/日志/缓存/统计/定时/备份）全部并进这里，配置项只此一处入口 */
var CFG_PAGE_ORDER=['图像参数','时区','鉴权','缓存','限流','并发','统计','定时','更新','管理面板','共享存储','备份','其他'];
/* 关于：不属于任何分类，固定在菜单最底部 */
var SET_ABOUT='about';
var _setCat='';
function _setCatSort(a,b){
  var ia=CFG_PAGE_ORDER.indexOf(a),ib=CFG_PAGE_ORDER.indexOf(b);
  if(ia<0)ia=99;if(ib<0)ib=99;
  return ia-ib||a.localeCompare(b);
}
/* 分类名 → 展示文本：category 本身是中文 id，只有展示走 category_label */
function _setCatName(c,d){
  var labels=(d&&d.labels)||{};
  var ks=Object.keys(labels).filter(function(k){return (labels[k].category||'其他')===c});
  var lb=ks.length?labels[ks[0]]:{};
  return lb.category_label||(c==='其他'?T('config.cat.other','其他'):c);
}
function _setKeysOf(d,cat){
  var out=[];
  Object.keys(d.defaults||{}).forEach(function(k){
    if((((d.labels||{})[k]||{}).category||'其他')===cat)out.push(k);
  });
  return out.sort();
}
/* 分类图标（16×16，与侧栏主菜单同一套画法：fill:none;stroke:currentColor）。
   侧栏折叠成图标条后分类名会被隐藏，只剩图标能把 13 个分类彼此区分开 */
var SET_ICONS={
  '图像参数':['<rect x="2.5" y="3.5" width="11" height="9" rx="1.5"/>','<circle cx="6" cy="7" r="1.1"/>','<path d="M3.2 11.6l2.8-2.8 2.4 2.4 2.2-2.2 2.4 2.4"/>'],
  '时区':['<circle cx="8" cy="8" r="5.5"/>','<path d="M8 4.8V8l2.2 1.3"/>'],
  '鉴权':['<path d="M8 2.2l4.5 1.7v4.3c0 2.6-1.9 4.4-4.5 5.6-2.6-1.2-4.5-3-4.5-5.6V3.9z"/>','<path d="M6.2 8l1.3 1.3 2.3-2.4"/>'],
  '缓存':['<ellipse cx="8" cy="4.2" rx="4.5" ry="1.7"/>','<path d="M3.5 4.2v3.8c0 .9 2 1.7 4.5 1.7s4.5-.8 4.5-1.7V4.2"/>','<path d="M3.5 8v3.8c0 .9 2 1.7 4.5 1.7s4.5-.8 4.5-1.7V8"/>'],
  '限流':['<path d="M2.5 5h11M2.5 8h11M2.5 11h11"/>','<circle cx="10.6" cy="8" r="1.7"/>'],
  '并发':['<rect x="2.8" y="3.2" width="4.2" height="4.2" rx="1"/>','<rect x="9" y="3.2" width="4.2" height="4.2" rx="1"/>','<rect x="2.8" y="8.6" width="4.2" height="4.2" rx="1"/>','<rect x="9" y="8.6" width="4.2" height="4.2" rx="1"/>'],
  '统计':['<path d="M2.5 13.5h11"/>','<path d="M4.8 13.5V9M8 13.5V5M11.2 13.5V7"/>'],
  '定时':['<rect x="3" y="3.6" width="10" height="9.4" rx="1.5"/>','<path d="M3 6.6h10M6 2.4v2.2M10 2.4v2.2"/>'],
  '更新':['<path d="M12.8 8a4.8 4.8 0 1 1-1.5-3.5"/>','<path d="M13 2.8V6H9.8"/>'],
  '管理面板':['<rect x="2.5" y="3" width="11" height="10" rx="1.5"/>','<path d="M6.6 3v10"/>'],
  '共享存储':['<rect x="2.5" y="2.8" width="11" height="3" rx="1"/>','<rect x="3.5" y="5.8" width="9" height="7.4" rx="1.5"/>','<path d="M6.6 9h2.8"/>'],
  '备份':['<path d="M8 2.4v7.2"/><path d="M5.2 7L8 9.6 10.8 7"/><path d="M3 12.6h10"/>'],
  '其他':['<circle cx="8" cy="8" r="5.5"/>','<path d="M5.7 6.5a2.4 2.4 0 1 1 2.9 2.3V10"/>','<path d="M8 12.2h.01"/>'],
  'about':['<circle cx="8" cy="8" r="5.5"/>','<path d="M8 7.4v3.2M8 5.1h.01"/>']
};
/* 兜底图标：以后新增分类忘了配图标，菜单里也不会出现一个空位 */
var SET_ICON_OTHER=['<circle cx="8" cy="8" r="5.5"/>','<path d="M8 7.6v3.2M8 5.1h.01"/>'];
function _setIcon(cat){
  var ps=SET_ICONS[cat]||SET_ICON_OTHER;
  return '<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ps.join('')+'</svg>';
}
function renderSetMenu(d){
  var byCat={};
  Object.keys(d.defaults||{}).forEach(function(k){
    var c=(((d.labels||{})[k]||{}).category)||'其他';
    (byCat[c]=byCat[c]||[]).push(k);
  });
  var h='';
  Object.keys(byCat).sort(_setCatSort).forEach(function(c){
    h+='<div class="set-item" data-act="set-cat" data-cat="'+esc(c)+'">'+_setIcon(c)+'<span class="lbl">'+esc(_setCatName(c,d))+
      '</span><span class="cnt">'+byCat[c].length+'</span></div>';
  });
  h+='<div class="set-sep"></div>';
  h+='<div class="set-item" data-act="set-cat" data-cat="'+SET_ABOUT+'">'+_setIcon(SET_ABOUT)+'<span class="lbl">'+esc(T('set.about','关于'))+'</span></div>';
  var el=document.getElementById('set-menu');
  if(el)el.innerHTML=h;
  /* 菜单是整段重建的，折叠态下的悬停提示要重新挂一遍 */
  syncNavTitles();
}
function refreshConfig(){
  fetchCfg().then(function(d){
    _cfg=d;
    renderSetMenu(d);
    /* 首次进入选第一个分类；之后保持用户选的那个（刷新/保存后不跳走） */
    var cats=Object.keys(d.defaults||{}).map(function(k){
      return (((d.labels||{})[k]||{}).category)||'其他';
    });
    var hit=(_setCat&&(cats.indexOf(_setCat)>=0||_setCat===SET_ABOUT))?_setCat:cats.sort(_setCatSort)[0];
    setSelect(hit||SET_ABOUT);
  }).catch(function(){
    var el=document.getElementById('cfg-body');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
}
function setSelect(cat){
  _setCat=cat;
  /* 分类名要等配置数据回来才拿得到，面包屑的「设置 / 分类」在这里补第二段 */
  paintCrumbs('config');
  var items=document.querySelectorAll('#set-menu .set-item');
  for(var i=0;i<items.length;i++)items[i].classList.toggle('on',items[i].dataset.cat===cat);
  var cfgBox=document.getElementById('set-cfg'),aboutBox=document.getElementById('set-about');
  if(cat===SET_ABOUT){
    cfgBox.hidden=true;aboutBox.hidden=false;
    loadAbout();
    return;
  }
  cfgBox.hidden=false;aboutBox.hidden=true;
  var keys=_setKeysOf(_cfg||{},cat);
  document.getElementById('set-title').textContent=_setCatName(cat,_cfg);
  document.getElementById('set-count').textContent=T('config.group_count','{n} 项',{n:keys.length});
  var el=document.getElementById('cfg-body');
  el.innerHTML=cfgTableHtml(keys);
  /* 保存 / 还原后按容器 id 重载自身（与旧版各分页的做法一致），重载即重绘当前分类 */
  _cfgReloadMap['cfg-body']=refreshConfig;
  bindCfgInput();
}
/* 导出 / 导入：配置迁移走「一个 JSON 文件」，比在面板上逐项抄写可靠。
   导出用 fetch + Blob 落地成带文件名的文件（响应体是普通 JSON，不必像备份那样走页面导航的流式下载） */
function cfgExport(){
  R.get('/admin/api/config/export').then(function(d){
    if(!d||!d.schema){toast((d&&d.message)||T('config.export_failed','导出失败'),'error');return}
    var stamp=String(d.exported_at||'').replace(/[^0-9]/g,'').substring(0,14);
    var name='einkviews-config'+(stamp?'-'+stamp:'')+'.json';
    var url=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));
    var a=document.createElement('a');
    a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
    /* 撤销要延后：同步 revoke 会在部分浏览器上把刚开始的下载一并取消 */
    setTimeout(function(){URL.revokeObjectURL(url)},10000);
    toast(T('config.exported','已导出 {name}',{name:name}),'success');
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
/* 选中文件即导入（不再多一次「上传」点击）。导入是覆盖写，必须先确认——
   确认框里说清覆盖范围：只覆盖包里有的项，其余保持原样 */
function cfgImport(){
  var inp=document.getElementById('cfg-import-file');
  var f=(inp&&inp.files&&inp.files[0])?inp.files[0]:null;
  if(!f)return;
  /* 立刻清空 input：同名文件再次选中不会触发 change，第二次就再也导不进来 */
  inp.value='';
  var fr=new FileReader();
  fr.onerror=function(){toast(T('config.read_failed','无法读取该文件'),'error')};
  fr.onload=function(){
    var data=null;
    try{data=JSON.parse(String(fr.result||''))}catch(e){toast(T('config.bad_package_json','配置包不是合法 JSON'),'error');return}
    uiConfirm({
      title:T('config.import','导入配置'),danger:true,confirmText:T('config.import_confirm','导入'),
      message:T('config.import_confirm_msg','将用「{name}」覆盖当前的全局配置、插件配置与各用户组限额，导入后立即生效；包里没有的项保持原样。',{name:f.name})
    }).then(function(ok){
      if(!ok)return;
      R.post('/admin/api/config/import',data).then(function(d){
        if(!d||d.success===false){toast((d&&d.message)||T('config.import_failed','导入失败'),'error');return}
        toast(d.message||T('config.import_done','导入完成'),'success');
        /* 覆盖项整批换过，缓存必须作废：渲染前重新取一次 */
        _cfgCacheTime=0;
        refreshConfig();
      }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
    });
  };
  fr.readAsText(f);
}
'''