# JS 缓存页
ADMIN_JS_CACHE = r'''/* ================= 缓存 ================= */
function refreshCache(){
  R.get('/admin/api/cache').then(function(d){
    var h='<div class="metrics">'
      +kpi(T('cache.kpi_font','字体缓存条目'),num(d.size)+' <span class="sub">/ '+num(d.maxsize)+'</span>')
      +kpi(T('cache.kpi_hit_rate','命中率'),(d.hit_rate||0)+'%')
      +kpi(T('cache.kpi_hits_misses','命中 / 未命中'),num(d.hits)+' / '+num(d.misses))
      +'</div>';
    document.getElementById('cache-metrics').innerHTML=h;
  });
}
function clearCache(){
  uiConfirm({
    title:T('cache.clear_title','清除缓存'),
    message:T('cache.clear_confirm','将清空字体内存缓存，下次请求会重新加载字体。'),
    confirmText:T('cache.clear_btn','清除')
  }).then(function(ok){
    if(!ok)return;
    R.post('/admin/api/cache/clear',{}).then(function(d){
      if(d.success){toast(T('cache.cleared','缓存已清除'),'success');refreshCache()}
      else toast(d.message||T('cache.clear_failed','清除失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}
'''
