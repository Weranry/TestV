# JS 统计页
ADMIN_JS_STATS = r'''/* ================= 统计 ================= */
/* 固定列宽 + <colgroup>：展开子表复用同一套列宽，数值列才能与父表上下对齐 */
var COLS4='<colgroup><col><col style="width:96px"><col style="width:96px"><col style="width:120px"></colgroup>';
/* 路由明细是 6 列（多了 p50/p95），单独一套 colgroup，不与父表复用 */
var COLS6='<colgroup><col><col style="width:80px"><col style="width:80px"><col style="width:96px"><col style="width:96px"><col style="width:96px"></colgroup>';
var _expandedPlugin='';
var _statsData=null;
var _statView='plugin';
/* 排行 / 累计 / 启动历史都是「会越来越长」的列表：整表列出 + 前端分页，
   不再截断（截断会让人以为长尾数据不存在），翻页看全量 */
var _STAT_PER=5;
function refreshStats(){
  var days=document.getElementById('stats-days').value||7;
  R.get('/admin/api/statistics?days='+days).then(renderStatistics).catch(function(){
    var el=document.getElementById('stats-kpis');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
  R.get('/admin/api/stats').then(function(d){renderSessions(d,'st-sessions');renderLifetime(d)}).catch(function(){
    var el=document.getElementById('st-sessions');
    if(el)el.innerHTML='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
  });
  refreshSlowestRoutes(days);
}
/* ---- 最慢路由榜：按 p95 降序，样本不足的路由后端已过滤掉 ----
   一次取回后端允许的上限（50 条），榜单由前端分页铺开；仍带 limit 是为了避免无谓地
   把整张统计表搬到面板上（排序本身就取全量，多取也只是多传几十行 JSON） */
var _slowRoutes=[];
function refreshSlowestRoutes(days){
  R.get('/admin/api/statistics/slowest-routes?days='+days+'&limit=50').then(function(d){
    _slowRoutes=d.routes||[];
    _pgRender['slow']=renderSlowestRoutes;
    renderSlowestRoutes();
  }).catch(function(){});
}
function renderSlowestRoutes(){
  var el=document.getElementById('stats-slow');if(!el)return;
  if(!_slowRoutes.length){el.innerHTML='<div class="empty">'+T('stats.slow_empty','样本不足：单个路由至少 5 次渲染才会进入统计')+'</div>';return}
  var pg=pgSlice(_slowRoutes,'slow',_STAT_PER);
  var h='<table><thead><tr><th>'+T('stats.col_route','路由')+'</th><th class="num">'+T('stats.col_samples','样本')+'</th><th class="num">p50</th><th class="num">p95</th><th class="num">'+T('stats.col_slowest','最慢')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(r){
    h+='<tr><td class="mono ellip" title="'+esc(r.path)+'">'+esc(r.path)+
      ' <span class="dim">'+esc(r.plugin_name||'')+'</span></td>'+
      '<td class="dim num">'+num(r.samples)+'</td>'+
      '<td class="mono dim num">'+r.p50_ms+'ms</td>'+
      '<td class="mono strong num" style="color:var(--orange-deep)">'+r.p95_ms+'ms</td>'+
      '<td class="mono dim num">'+r.max_ms+'ms</td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+pg.bar;
}
function renderStatistics(d){
  _statsData=d;
  var gt=d.grand_total||{};
  var total=gt.total||0,errors=gt.errors||0;
  var rate=total>0?(errors/total*100).toFixed(1)+'%':'0%';
  var daily=d.daily||[];
  var peak=0;daily.forEach(function(r){if(r.total>peak)peak=r.total});
  document.getElementById('stats-kpis').innerHTML=
    kpi(T('stats.kpi_total','总请求'),num(total))+
    kpi(T('stats.col_errors','错误'),num(errors),'red')+
    kpi(T('stats.kpi_error_rate','错误率'),rate)+
    kpi(T('stats.col_avg','平均耗时'),(gt.avg_ms!=null?gt.avg_ms:'-')+'ms')+
    kpi(T('stats.kpi_peak','单日峰值'),num(peak));
  /* ---- 每日图表 ---- */
  var ch='';
  if(daily.length){
    var maxT=peak||1;
    var step=Math.max(1,Math.ceil(daily.length/10));
    ch+='<div class="chart">';
    daily.forEach(function(r){
      var hp=Math.max(2,Math.round(r.total/maxT*100));
      var ep=r.total>0?Math.round(r.errors/r.total*100):0;
      ch+='<div class="bar-col" title="'+T('stats.bar_title','{dt}：{total} 请求 / {errors} 错误',{dt:esc(r.dt),total:r.total,errors:r.errors})+'"><div class="bar" style="height:'+hp+'%">'+(r.errors>0?'<div class="bar-err" style="height:'+ep+'%"></div>':'')+'</div></div>';
    });
    ch+='</div><div class="chart-x">';
    daily.forEach(function(r,i){
      var lbl=(i%step===0)?r.dt.substring(5):'';
      ch+='<span>'+lbl+'</span>';
    });
    ch+='</div>';
  }else ch='<div class="empty">'+T('stats.empty','暂无数据')+'</div>';
  document.getElementById('stats-chart').innerHTML=ch;
  /* ---- 状态码分布 ---- */
  var dist=d.status_dist||[];var map={};
  dist.forEach(function(x){map[x.cls]=x.cnt});
  var cls2=map['2xx']||0,cls3=map['3xx']||0,cls4=map['4xx']||0,cls5=map['5xx']||0;
  var st=cls2+cls3+cls4+cls5;
  if(st>0){
    var colors={'2xx':'#171717','3xx':'var(--fg3)','4xx':'var(--orange-deep)','5xx':'var(--red-deep)'};
    var bar='<div class="stackbar">';
    ['2xx','3xx','4xx','5xx'].forEach(function(k){
      var c=map[k]||0;if(!c)return;
      bar+='<div style="width:'+(c/st*100)+'%;background:'+colors[k]+'" title="'+k+'：'+c+'"></div>';
    });
    bar+='</div><div class="legend">';
    ['2xx','3xx','4xx','5xx'].forEach(function(k){
      var c=map[k]||0;
      bar+='<span><i style="background:'+colors[k]+'"></i>'+k+' · '+num(c)+'</span>';
    });
    bar+='</div>';
    document.getElementById('stats-status').innerHTML=bar;
  }else document.getElementById('stats-status').innerHTML='<div class="empty">'+T('stats.empty','暂无数据')+'</div>';
  renderStatsRank();
}
/* ---- 请求排行：按插件 / 按账号共用一个列表，按钮切换 ---- */
function switchStatView(v){
  if(_statView===v)return;
  _statView=v;
  _expandedPlugin='';
  _pg['rank']=1;
  document.querySelectorAll('#page-stats .stab').forEach(function(t){t.classList.toggle('on',t.dataset.sv===v)});
  renderStatsRank();
}
function renderStatsRank(){
  var el=document.getElementById('stats-rank');if(!el)return;
  var d=_statsData||{};
  var isPlugin=_statView==='plugin';
  var rows=((isPlugin?d.by_plugin:d.by_account)||[]);
  /* 占比条按整表最大值算：同一条数据的长度不该因为翻页而变化 */
  var max=0;rows.forEach(function(r){if(r.total>max)max=r.total});
  var pg=pgSlice(rows,'rank',_STAT_PER);
  var h='<table class="stat-table">'+COLS4+'<thead><tr><th>'+(isPlugin?T('stats.col_plugin','插件'):T('stats.col_account','账号'))+'</th><th class="num">'+T('stats.col_requests','请求')+'</th><th class="num">'+T('stats.col_errors','错误')+'</th><th class="num">'+T('stats.col_avg','平均耗时')+'</th></tr></thead><tbody>';
  if(!pg.rows.length)h+='<tr><td colspan="4" class="empty">'+T('stats.empty','暂无数据')+'</td></tr>';
  pg.rows.forEach(function(r){
    var name;
    if(isPlugin){
      name='<span class="expander" data-act="plugin-expand" data-name="'+esc(r.plugin_name)+'">▸</span> <span class="strong">'+esc(r.plugin_name)+'</span>';
    }else{
      // 无账号身份（环境变量 EVKEY 鉴权）的请求归入「未登录」
      name='<span class="strong">'+esc(r.account_name||T('stats.unknown_account','(未知)'))+'</span>'+(r.account_id?' <span class="dim mono">#'+r.account_id+'</span>':' <span class="dim">'+T('stats.not_logged_in','未登录')+'</span>');
    }
    h+='<tr><td>'+name+'<div class="share"><div style="width:'+(max?Math.round(r.total/max*100):0)+'%"></div></div></td>'+
      '<td class="num">'+num(r.total)+'</td>'+
      '<td class="num'+(r.errors>0?' err-text':'')+'">'+num(r.errors)+'</td>'+
      '<td class="mono dim num">'+(r.avg_ms!=null?r.avg_ms+'ms':'-')+'</td></tr>';
  });
  h+='</tbody></table>'+pg.bar;
  el.innerHTML=h;
  _pgRender['rank']=renderStatsRank;
  if(isPlugin&&_expandedPlugin)restoreExpandedPlugin();
}
/* 自动刷新会重建排行表，这里把之前展开的插件重新展开，避免明细消失 */
function restoreExpandedPlugin(){
  var els=document.querySelectorAll('#stats-rank .expander');
  for(var i=0;i<els.length;i++){
    if(els[i].dataset.name===_expandedPlugin){togglePluginRoutes(els[i]);return}
  }
  _expandedPlugin='';
}
function togglePluginRoutes(btn){
  var name=btn.dataset.name;
  var days=document.getElementById('stats-days').value||7;
  var tr=btn.closest('tr');
  var next=tr.nextElementSibling;
  if(next&&next.classList.contains('detail-row')){next.remove();btn.textContent='▸';_expandedPlugin='';return}
  btn.textContent='▾';
  _expandedPlugin=name;
  R.get('/admin/api/statistics/plugin-routes?days='+days+'&plugin='+encodeURIComponent(name)).then(function(d){
    var routes=d.routes||[];
    // colspan 必须等于父表实际列数：写多会让整张表被撑出多余空列，table-layout:fixed
    // 下空列照样平分剩余宽度，首列（插件名）就被压窄、上半部分跟着错位。
    // 这里按父行格子数现算，父表改列数时不会再出现写死的数字过期。
    var cols=tr.children.length||4;
    var h='<td colspan="'+cols+'">';
    if(!routes.length)h+='<div class="empty" style="padding:12px 0">'+T('stats.plugin_no_routes','该插件暂无请求记录')+'</div>';
    else{
      h+='<table class="stat-table">'+COLS6+'<thead><tr><th>'+T('stats.col_path','路径')+'</th><th class="num">'+T('stats.col_requests','请求')+'</th><th class="num">'+T('stats.col_errors','错误')+'</th><th class="num">'+T('stats.col_avg','平均耗时')+'</th><th class="num">p50</th><th class="num">p95</th></tr></thead><tbody>';
      routes.forEach(function(r){
        h+='<tr><td class="mono ellip" title="'+esc(r.path)+'">'+esc(r.path)+'</td>'+
          '<td class="num">'+num(r.total)+'</td>'+
          '<td class="num'+(r.errors>0?' err-text':'')+'">'+num(r.errors)+'</td>'+
          '<td class="mono dim num">'+(r.avg_ms!=null?r.avg_ms+'ms':'-')+'</td>'+
          '<td class="mono dim num">'+(r.p50_ms!=null?r.p50_ms+'ms':'-')+'</td>'+
          '<td class="mono dim num">'+(r.p95_ms!=null?r.p95_ms+'ms':'-')+'</td></tr>';
      });
      h+='</tbody></table>';
    }
    h+='</td>';
    var detail=document.createElement('tr');detail.className='detail-row';detail.innerHTML=h;
    tr.after(detail);
  }).catch(function(){btn.textContent='▸'});
}
var _lifetimeStats=[];
function renderLifetime(d){
  if(d)_lifetimeStats=d.plugin_stats||[];
  var el=document.getElementById('stats-lifetime');if(!el)return;
  var pg=pgSlice(_lifetimeStats,'lifetime',_STAT_PER);
  var h='<table><thead><tr><th>'+T('stats.col_plugin','插件')+'</th><th class="num">'+T('stats.col_total_req','累计请求')+'</th><th>'+T('stats.col_first_req','首次请求')+'</th><th>'+T('stats.col_last_req','最近请求')+'</th></tr></thead><tbody>';
  if(!pg.rows.length)h+='<tr><td colspan="4" class="empty">'+T('stats.empty','暂无数据')+'</td></tr>';
  pg.rows.forEach(function(s){
    h+='<tr><td class="strong">'+esc(s.plugin_name)+'</td><td class="num">'+num(s.request_count)+'</td><td class="dim">'+fmtDT(s.first_request)+'</td><td class="dim">'+fmtDT(s.last_request)+'</td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender['lifetime']=renderLifetime;
}
'''