# JS 概览页
ADMIN_JS_OVERVIEW = r'''/* ================= 概览 ================= */
function kpi(l,v,cls){return '<div class="metric"><div class="l">'+l+'</div><div class="k '+(cls||'')+'">'+v+'</div></div>'}
/* 概览页的「定义条目」：小号灰标签在上、值在下。与 .metric 小卡的区别是不带卡片外壳，
   可以直接铺进大卡的栅格里 —— 概览页因此不再出现「卡片里套小卡」 */
function defItem(k,v,cls){return '<div class="def"><div class="def-k">'+k+'</div><div class="def-v'+(cls?' '+cls:'')+'">'+v+'</div></div>'}
function fmtBytes(n){
  n=Number(n)||0;
  if(n<1024)return n+' B';
  var u=['KB','MB','GB','TB'],i=-1;
  while(n>=1024&&i<u.length-1){n/=1024;i++}
  return n.toFixed(1)+' '+u[i];
}
/* 健康度评分：以 100 分为基准，告警扣 15、异常扣 35，取整到 0~100 */
function renderOverviewHealth(h){
  var checks=h.checks||[];
  var score=100,bad=[];
  checks.forEach(function(c){
    if(c.status==='error'){score-=35;bad.push(c.name)}
    else if(c.status==='warn'){score-=15;bad.push(c.name)}
  });
  score=Math.max(0,Math.min(100,score));
  // 只给文字等级，不加 A/B/C/D：分数已经很直观，字母是多余的一层映射
  var g=score>=90?[T('overview.grade_excellent','优秀'),'']:score>=75?[T('overview.grade_good','良好'),'']:score>=60?[T('overview.grade_fair','一般'),'warn']:[T('overview.grade_bad','异常'),'error'];
  var note;
  if(!checks.length)note=T('overview.no_checks','暂无检查项');
  else if(!bad.length)note=T('overview.all_checks_ok','全部检查项正常（共 {n} 项）',{n:checks.length});
  else note=(g[1]==='error'?T('overview.err_prefix','异常：'):T('overview.warn_prefix','告警：'))+bad.join('、');
  document.getElementById('ov-health').innerHTML=
    '<div class="hs-num '+g[1]+'">'+score+'</div>'+
    '<div><div class="hs-grade">'+g[0]+'</div><div class="hs-note">'+esc(note)+'</div></div>';
}
/* 运行信息拆成两处：版本 / 本次启动落在上卡的右侧栅格，其余落在下卡右半。
   取值口径与文案键与改造前逐字一致，只是渲染目标从一张 #ov-info 换成两个容器 */
function renderOverviewInfo(d){
  var r=d.runtime||{},db=d.db||{},disk=d.disk||{};
  document.getElementById('ov-info-top').innerHTML=
    defItem(T('overview.info_version','服务版本'),esc(d.version||'-')+' · Python '+esc(d.python||'-'))+
    defItem(T('overview.info_start','本次启动'),esc(fmtDT(r.last_startup)));
  document.getElementById('ov-info-bottom').innerHTML=
    defItem(T('overview.info_uptime','累计运行'),fmtUptime(r.total_uptime_seconds)+T('overview.info_uptime_suffix',' · 共 {n} 次启动',{n:num(r.session_count)}))+
    defItem(T('overview.info_first_start','首次启动'),esc(fmtDT(r.first_startup)))+
    defItem(T('overview.info_db','数据库文件'),(db.available?fmtBytes(db.size_bytes):'<span class="dim">'+T('overview.db_disabled','当前模式已停用')+'</span>'))+
    defItem(T('overview.info_disk','磁盘剩余'),(disk.total?fmtBytes(disk.free)+' / '+fmtBytes(disk.total):'<span class="dim">'+T('overview.disk_unreadable','无法读取')+'</span>'));
}
function refreshOverview(){
  R.get('/admin/api/status').then(function(d){
    var rc=d.request_counts||{};var total=0;Object.keys(rc).forEach(function(k){total+=rc[k]});
    document.getElementById('ov-uptime').textContent=d.uptime_display||'-';
    // 状态 = 绿点「运行中」+ 模式徽章：Python / 插件数 / 账号数 在下方的定义栅格里已有，避免重复
    document.getElementById('ov-status').innerHTML=
      '<span class="badge badge-on">'+T('stats.session_running','运行中')+'</span>'+
      ' <span class="badge '+(d.mode==='dev'?'badge-off':'badge-on')+'">'+esc(d.mode||'')+'</span>';
    var t=d.today||{},c=d.cache||{};
    var rate=t.total>0?(t.errors/t.total*100).toFixed(1)+'%':'0%';
    document.getElementById('ov-kpi-top').innerHTML=
      defItem(T('overview.kpi_total','总请求'),num(total))+
      defItem(T('overview.kpi_today','今日请求'),num(t.total))+
      defItem(T('overview.kpi_error_rate','今日错误率'),rate,(t.errors>0?'red':''))+
      defItem(T('overview.kpi_avg_ms','今日平均耗时'),(t.avg_ms!=null?t.avg_ms:'-')+'ms');
    document.getElementById('ov-kpi-bottom').innerHTML=
      defItem(T('overview.kpi_plugins','插件数'),d.plugin_count)+
      defItem(T('overview.kpi_accounts','账号数'),d.user_count)+
      defItem(T('overview.kpi_evkey','EVkey 数'),num(d.evkey_count))+
      defItem(T('overview.kpi_hit_rate','缓存命中率'),(c.enabled?c.hit_rate+'%':T('overview.cache_off','已停用')));
    renderOverviewInfo(d);
    renderOverviewHealth(d.health||{});
  }).catch(function(){
    var msg='<div class="empty">'+esc(T('msg.session_expired','请求失败或会话已失效，请重新登录'))+'</div>';
    ['ov-kpi-top','ov-kpi-bottom','ov-info-top','ov-info-bottom'].forEach(function(id){
      var el=document.getElementById(id);if(el)el.innerHTML=msg;
    });
  });
}
/* 启动历史：每次重启长一行，越用越长，5 条一页 */
var _sessionsData=null,_SESSION_PER=5;
function renderSessions(d,cid){
  if(d)_sessionsData=d;
  var data=_sessionsData||{},ss=data.sessions||[];
  var el=document.getElementById(cid);if(!el)return;
  if(!ss.length){el.innerHTML='<div class="empty">'+T('stats.no_sessions','暂无启动记录')+'</div>';return}
  // 分页 key 必须与下面 _pgRender 注册的 key 一致：这张表在概览页与控制台各有一份 DOM
  // （cid 不同），用 cid 当 key 才能各自独立翻页，也不会与数据字段名 sessions 撞车
  var pg=pgSlice(ss,cid,_SESSION_PER);
  var h='<div class="stat-line dim">'+T('stats.sessions_summary','首次启动 {first} · 最近启动 {last} · 累计运行 {uptime} · 共 {n} 次启动',{first:fmtDT(data.first_startup),last:fmtDT(data.last_startup),uptime:fmtUptime(data.total_uptime_seconds),n:ss.length})+'</div>';
  h+='<table><thead><tr><th>'+T('stats.col_start','开始时间')+'</th><th>'+T('stats.col_duration','持续时间')+'</th><th>'+T('stats.col_mode','模式')+'</th><th>'+T('stats.col_version','版本')+'</th><th class="num">'+T('stats.col_requests','请求')+'</th><th class="num">'+T('stats.col_errors','错误')+'</th></tr></thead><tbody>';
  pg.rows.forEach(function(s){
    var running=!s.end_time;
    h+='<tr><td>'+fmtDT(s.start_time)+(running?' <span class="badge badge-on" style="margin-left:8px">'+T('stats.session_running','运行中')+'</span>':'')+'</td>'+
      '<td>'+fmtUptime(s.uptime_seconds)+'</td>'+
      '<td>'+esc(s.mode||'-')+'</td>'+
      '<td class="mono">'+esc(s.version||'-')+'</td>'+
      '<td class="num">'+num(s.requests)+'</td>'+
      '<td class="num'+(s.errors>0?' err-text':'')+'">'+num(s.errors)+'</td></tr>';
  });
  el.innerHTML=h+'</tbody></table>'+pg.bar;
  _pgRender[cid]=function(){renderSessions(null,cid)};
}

/* ================= 站内信 ================= */
var _ANN_PER=5,_annGroups=null;
/* 用户组名缓存：渲染可见范围、渲染历史列表时复用，避免每次都重拉；
   用户组增删改后置空失效（每次开弹窗渲染可见范围前各失效一次） */
function loadAnnGroups(cb){
  if(_annGroups){cb(_annGroups);return}
  R.get('/admin/api/groups').then(function(d){_annGroups=d.groups||[];cb(_annGroups)})
    .catch(function(){_annGroups=[];cb(_annGroups)});
}
/* group_ids 为空 = 全体可见；非空逐个翻成组名，组被删了就退回显示 id */
function annScopeHtml(a,groups){
  var ids=String(a.group_ids||'').split(',').filter(function(x){return x});
  if(!ids.length)return '<span class="ann-scope">'+T('announce.all_users','全体可见')+'</span>';
  return ids.map(function(id){
    var hit=groups.filter(function(x){return String(x.id)===String(id)})[0];
    return '<span class="ann-scope">'+esc(hit?hit.name:T('announce.group_tag','组 #{id}',{id:id}))+'</span>';
  }).join(' ');
}
/* 可见范围勾选框：每次开弹窗先置空缓存再拉，避免用户组被增删后选项过期。
   渲染进弹窗里的 #ann-scope —— 页面上只有一个弹窗，拿 id 取就是那一份 */
function annRenderScope(){
  _annGroups=null;
  loadAnnGroups(function(groups){
    var el=document.getElementById('ann-scope');if(!el)return;
    var h='<label><input type="checkbox" id="ann-all" data-act="ann-all"> '+T('announce.all_users','全体可见')+'</label>';
    h+=groups.map(function(g){
      return '<label><input type="checkbox" class="ann-g" value="'+g.id+'"> '+esc(g.name)+'</label>';
    }).join('');
    if(!groups.length)h+='<span class="dim small">'+T('announce.no_groups','还没有用户组，将按全体可见发布')+'</span>';
    el.innerHTML=h;
  });
}
/* 主页那张卡只有「输入框 + 新建」两个触发点，真正的填写在弹窗里：
   点输入框或点按钮都走这里。弹窗已开着就不再叠一个（连点两下会盖出两层） */
function showAnnounceModal(){
  if(document.getElementById('ann-modal'))return;
  var h='<h3>'+T('announce.new_title','发送站内信')+'</h3>'+
    '<label>'+T('announce.title_label','标题')+'</label>'+
    '<input class="input" id="ann-title" autocomplete="off">'+
    '<label>'+T('announce.content_label','内容（选填）')+'</label>'+
    '<textarea class="input" id="ann-content" rows="4" style="height:auto;min-height:96px;padding:8px 16px;line-height:1.6;resize:vertical"></textarea>'+
    '<label>'+T('announce.scope_label','可见范围')+'</label>'+
    '<div class="ck-row" id="ann-scope">'+T('msg.loading','加载中...')+'</div>'+
    '<div class="modal-actions">'+
    '<button class="btn" data-act="modal-close">'+T('btn.cancel','取消')+'</button>'+
    '<button class="btn btn-primary" data-act="ann-create">'+T('announce.publish','发布')+'</button>'+
    '</div>';
  openModal(h,'ann-modal');
  annRenderScope();
}
/* 站内信被该管理组关掉时连数据都不拉：接口会 403，拉只会在控制台刷一屏错误。
   历史列表：标题 / 缩略 / 时间 / 发送人 / 对象，5 条一页（服务端 limit + offset） */
function refreshAnnouncements(){
  var el=document.getElementById('ann-area');if(!el)return;
  if(!SHOW_ANNOUNCEMENT)return;
  var page=pgPage('ann');
  R.get('/admin/api/announcements?limit='+_ANN_PER+'&offset='+((page-1)*_ANN_PER)).then(function(d){
    if(d.success===false){el.innerHTML='<div class="empty">'+esc(d.message||T('msg.load_failed','加载失败'))+'</div>';return}
    var items=d.items||[],total=d.total||0;
    loadAnnGroups(function(groups){
      if(!items.length){el.innerHTML='<div class="empty">'+T('announce.empty','还没有站内信，点上方「新建」发布一条。')+'</div>';return}
      var h='<table><thead><tr><th>'+T('announce.col_title','标题')+'</th><th>'+T('announce.col_excerpt','缩略')+'</th>'+
        '<th>'+T('announce.col_time','时间')+'</th><th>'+T('announce.col_sender','发送人')+'</th>'+
        '<th>'+T('announce.col_scope','对象')+'</th><th></th></tr></thead><tbody>';
      items.forEach(function(a){
        // 缩略：正文压成一行、40 字截断，换行会让行高参差
        var ex=String(a.content||'').replace(/\s+/g,' ').trim();
        if(ex.length>40)ex=ex.slice(0,40)+'…';
        h+='<tr><td>'+esc(a.title)+'</td>'+
          '<td class="ann-excerpt">'+(ex?esc(ex):'—')+'</td>'+
          '<td>'+fmtDT(a.created_at)+'</td>'+
          '<td>'+(a.admin_name?esc(a.admin_name):'—')+'</td>'+
          '<td>'+annScopeHtml(a,groups)+'</td>'+
          '<td class="num"><button class="btn btn-sm btn-danger" data-act="ann-del" data-id="'+a.id+'" data-title="'+esc(a.title)+'">'+T('btn.delete','删除')+'</button></td></tr>';
      });
      el.innerHTML=h+'</tbody></table>'+pgBar('ann',total,_ANN_PER);
      _pgRender['ann']=refreshAnnouncements;
    });
  }).catch(function(){el.innerHTML='<div class="empty">'+T('msg.load_failed','加载失败')+'</div>'});
}
/* 「全体可见」勾上即等于全选：勾选框只是把组勾满并禁用，让范围一眼可读 */
function annToggleAll(el){
  var on=el.checked;
  document.querySelectorAll('#ann-scope .ann-g').forEach(function(c){c.checked=on;c.disabled=on});
}
/* 发布走弹窗：成功后关掉弹窗、回到第一页并刷新列表（弹窗里的输入随 DOM 一起消失，
   不用手工清空；失败则保留弹窗，让用户改完重发） */
function createAnnouncement(btn){
  var title=document.getElementById('ann-title').value.trim();
  if(!title){toast(T('announce.need_title','请填写标题'),'error');return}
  var content=document.getElementById('ann-content').value;
  var ids=[];
  if(!document.getElementById('ann-all').checked){
    document.querySelectorAll('#ann-scope .ann-g').forEach(function(c){if(c.checked)ids.push(parseInt(c.value))});
  }
  btnBusy(btn,true,T('announce.publishing','发布中…'));
  R.post('/admin/api/announcements',{title:title,content:content,group_ids:ids}).then(function(d){
    btnBusy(btn,false);
    if(d.success===false){toast(d.message||T('announce.publish_failed','发布失败'),'error');return}
    var ov=document.getElementById('ann-modal');if(ov)ov.remove();
    toast(T('announce.published','站内信已发布'),'success');
    _pg.ann=1;
    refreshAnnouncements();
  }).catch(function(){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')});
}
function delAnnouncement(id,title){
  uiConfirm({title:T('announce.del_title','删除站内信'),message:T('announce.del_confirm','删除后「{title}」将立即对所有用户不可见。',{title:title}),confirmText:T('btn.delete','删除'),danger:true}).then(function(ok){
    if(!ok)return;
    R.del('/admin/api/announcements/'+id).then(function(d){
      if(d.success){toast(T('announce.deleted','已删除'),'success');refreshAnnouncements()}
      else toast(d.message||T('announce.del_failed','删除失败'),'error');
    }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
  });
}

/* ================= 主页缩略图 ================= */
/* 概览左上角那张图不是 iframe（首页响应带 X-Frame-Options: DENY，嵌不进来），
   而是照 Vercel 部署页的做法：固定 640/400 比例的圆角框里放一块 <canvas>，
   按首页真实结构等比绘制一张微缩图 —— 背景光斑、logo 白卡、站名 + EVO 徽章、
   副标题、两枚按钮、页脚。画布内部分辨率取 2 倍，缩到框宽后边缘不发虚。
   颜色全部现取当前主题的 CSS 变量，切主题后由 MutationObserver 重绘同一张图。 */
var SHOT_W=640,SHOT_H=400,SHOT_DPR=2;
var SHOT_FONT='"Inter","Segoe UI",system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif';
var SHOT_MONO='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace';
/* 首页 logo 的四个紫色多边形 + 一个深紫圆点（与 shared_ui.LOGO_SVG、index.html 同源），
   viewBox 为 `7 -3 128 161.62`。Path2D 只建一次，重绘时直接复用 */
var SHOT_VB={x:7,y:-3,w:128,h:161.6217803955078};
var SHOT_LOGO=[
  ['M61 86.1962L26.5 106.115C22.5 108.424 17.5 105.537 17.5 100.919L17.5 61.0814C17.5 56.4626 22.5 53.5759 26.5 55.8853L61 75.8038C65 78.1133 65 83.8867 61 86.1962Z','#8A6DB1'],
  ['M119 53.1962L84.5 73.1147C80.5 75.4241 75.5 72.5374 75.5 67.9186L75.5 28.0814C75.5 23.4626 80.5 20.5759 84.5 22.8853L119 42.8038C123 45.1132 123 50.8868 119 53.1962Z','#8A6DB1'],
  ['M72.3109 27.8923L72.3109 67.7295C72.3109 72.3483 67.3109 75.235 63.3109 72.9256L28.8109 53.007C24.8109 50.6976 24.8109 44.9241 28.8109 42.6147L63.3109 22.6962C67.3109 20.3867 72.3109 23.2735 72.3109 27.8923Z','#6E5494'],
  ['M72.3109 93.8923L72.3109 133.729C72.3109 138.348 67.3109 141.235 63.3109 138.926L28.8109 119.007C24.8109 116.698 24.8109 110.924 28.8109 108.615L63.3109 88.6962C67.3109 86.3867 72.3109 89.2735 72.3109 93.8923Z','#6E5494'],
  ['M101 84a12 12 0 1 0 0 24a12 12 0 1 0 0-24Z','#5A4378']
].map(function(p){return [new Path2D(p[0]),p[1]]});
function _shotColor(name,fb){
  var v=getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v||fb;
}
/* 圆角矩形：老浏览器没有 ctx.roundRect，退回手画四角弧 */
function _shotRound(ctx,x,y,w,h,r){
  ctx.beginPath();
  if(ctx.roundRect){ctx.roundRect(x,y,w,h,r);return}
  ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();
}
/* logo 按 viewBox 等比缩放、居中到 (cx,cy)，最长边为 size */
function _shotLogo(ctx,cx,cy,size){
  var s=size/Math.max(SHOT_VB.w,SHOT_VB.h);
  ctx.save();
  ctx.translate(cx-(SHOT_VB.x+SHOT_VB.w/2)*s,cy-(SHOT_VB.y+SHOT_VB.h/2)*s);
  ctx.scale(s,s);
  SHOT_LOGO.forEach(function(p){ctx.fillStyle=p[1];ctx.fill(p[0])});
  ctx.restore();
}
function drawOverviewShot(){
  var c=document.getElementById('ov-shot');if(!c)return;
  var ctx=c.getContext('2d');if(!ctx)return;
  if(c.width!==SHOT_W*SHOT_DPR){c.width=SHOT_W*SHOT_DPR;c.height=SHOT_H*SHOT_DPR}
  ctx.setTransform(SHOT_DPR,0,0,SHOT_DPR,0,0);
  var dk=document.documentElement.classList.contains('dark');
  var bg=_shotColor('--ds-background-200','#fafafa');
  var card=dk?_shotColor('--ds-gray-100','#1a1a1a'):'#ffffff';
  var ink=_shotColor('--ds-gray-1000','#171717');
  var sub=_shotColor('--ds-gray-900','#4d4d4d');
  var faint=_shotColor('--ds-gray-700','#8f8f8f');
  var line=_shotColor('--ds-gray-alpha-400','rgba(0,0,0,.08)');
  var soft=_shotColor('--ds-gray-100','#f2f2f2');
  var cx=SHOT_W/2;

  ctx.clearRect(0,0,SHOT_W,SHOT_H);
  ctx.fillStyle=bg;ctx.fillRect(0,0,SHOT_W,SHOT_H);
  /* 首页 body::before 的三层光斑：等比换算成三个极淡的径向渐变 */
  [[.18,.12,'138,109,177',.16],[.84,.22,'0,112,243',.10],[.50,1.02,'121,40,202',.10]].forEach(function(g){
    var x=g[0]*SHOT_W,y=g[1]*SHOT_H,rg=ctx.createRadialGradient(x,y,0,x,y,SHOT_W*.34);
    rg.addColorStop(0,'rgba('+g[2]+','+g[3]+')');rg.addColorStop(1,'rgba('+g[2]+',0)');
    ctx.fillStyle=rg;ctx.fillRect(0,0,SHOT_W,SHOT_H);
  });

  /* logo 白卡：首页 .logo-bg 在两种主题下都是白底，这里保持同一观感 */
  var ls=88,lx=cx-ls/2,ly=62;
  ctx.save();
  ctx.shadowColor='rgba(0,0,0,.16)';ctx.shadowBlur=16;ctx.shadowOffsetY=5;
  _shotRound(ctx,lx,ly,ls,ls,18);ctx.fillStyle='#fff';ctx.fill();
  ctx.restore();
  _shotLogo(ctx,cx,ly+ls/2,58);

  /* 站名 + EVO 徽章：与首页 `.title-row` 同构 —— 居中的只有站名，徽章绝对定位贴它的
     右上角（首页是 `.title{position:relative}` + `.title-badge{top:0;left:100%}`）。
     不要把两者当成一个整体去凑宽度：那样站名会被徽章顶得偏左，与真实首页对不上 */
  ctx.textBaseline='alphabetic';
  ctx.font='700 30px '+SHOT_FONT;
  var name='eInkViews',nw=ctx.measureText(name).width,ty=206;
  ctx.font='500 9px '+SHOT_MONO;
  var bw=ctx.measureText('EVO').width+18;
  var x0=cx-nw/2;
  ctx.font='700 30px '+SHOT_FONT;ctx.fillStyle=ink;ctx.textAlign='left';
  ctx.fillText(name,x0,ty);
  _shotRound(ctx,x0+nw,ty-26,bw,17,8.5);ctx.fillStyle=soft;ctx.fill();
  ctx.font='500 9px '+SHOT_MONO;ctx.fillStyle=sub;ctx.textAlign='center';
  ctx.fillText('EVO',x0+nw+bw/2,ty-14);

  /* 两枚按钮：深底 GitHub + 描边 Wiki（与首页 .buttons 同布局）。
     首页那行副标题（`is working on …`）不画进来，站名与按钮之间留 38px 呼吸位 */
  var bw2=112,bh=30,bgap=12,bx=cx-(bw2*2+bgap)/2,by=244;
  _shotRound(ctx,bx,by,bw2,bh,7);ctx.fillStyle=ink;ctx.fill();
  ctx.font='500 12.5px '+SHOT_FONT;ctx.fillStyle=bg;ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText('GitHub',bx+bw2/2,by+bh/2+1);
  _shotRound(ctx,bx+bw2+bgap,by,bw2,bh,7);ctx.fillStyle=card;ctx.fill();
  ctx.strokeStyle=line;ctx.lineWidth=1;ctx.stroke();
  ctx.fillStyle=ink;
  ctx.fillText('Wiki',bx+bw2+bgap+bw2/2,by+bh/2+1);

  /* 页脚：一行小灰字，位置照首页 .footer */
  ctx.font='400 10.5px '+SHOT_FONT;ctx.fillStyle=faint;ctx.textAlign='center';ctx.textBaseline='alphabetic';
  ctx.fillText('built for Open ePaperLink · AGPL-3.0 © 2024-2026 · Weranry',cx,378);
}
/* 主题切换后重绘：<html> 的 class 是主题的唯一开关，变了就重画同一张图。
   字体加载完再补一次，免得首次用回退字体把标题宽度量错、徽章贴不上 */
(function initOverviewShot(){
  drawOverviewShot();
  new MutationObserver(drawOverviewShot).observe(document.documentElement,{attributes:true,attributeFilter:['class']});
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(drawOverviewShot);
})();
'''