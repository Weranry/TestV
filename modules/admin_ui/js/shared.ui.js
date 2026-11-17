
/* ============ i18n：服务端按当前语言把整份注册表注入 #i18n-data ============ */
var I18N={};
(function(){
  var el=document.getElementById('i18n-data');
  if(!el)return;
  try{I18N=JSON.parse(el.textContent)||{}}catch(e){I18N={}}
})();
/* 取词：缺键回落第二参数，再缺就把键名原样返回——界面上露出键名，好过一片空白。
   骨架（HTML 标记）里的取词由服务端按 T: 前缀标记替换完成，这里只管脚本动态拼出来的
   文案，两边读的是同一份注册表，不会各写一套 */
function T(k,fb,fmt){
  var v=I18N[k];
  if(v===undefined||v===null||v==='')v=(fb===undefined?k:fb);
  if(fmt)v=String(v).replace(/\{(\w+)\}/g,function(m,g){return fmt[g]===undefined?m:fmt[g]});
  return v;
}
/* 弹窗打开期间给 body 加锁（CSS：body.modal-open{overflow:hidden}）。
   遮罩是 fixed 层，页面本身仍可滚：弹窗内容滚到边界后滚动链会传给 document，
   表现为「弹窗不滚、背景在滚」。用观察器统一维护，覆盖 X / 遮罩 / Esc /
   各页直接 remove 的所有关闭路径；观察直接子节点即可（弹窗都挂在 body 下） */
(function(){
  function sync(){
    var any=document.querySelector('.modal-overlay');
    document.body.classList.toggle('modal-open',!!any);
  }
  if(window.MutationObserver){
    new MutationObserver(sync).observe(document.body,{childList:true});
  }
  sync();
})();
/* ============ 共享 UI：请求工具 / 通知 / 弹窗 ============ */
/* 统一请求包装：先解析响应体，再决定要不要兜底，解析失败一律归一为 {success:false}
   后 resolve（否则 r.json() 抛错会让调用方的 Promise 被拒，只读刷新就永久停在「加载中」）。
   注意不能先按 r.ok 拦：后端统一错误出口对 4xx/5xx 也返回 {success:false,message,code}，
   先拦会把「已存在同名用户组」这类具体原因一起吞掉，只剩一句「会话已失效」。
   真正需要兜底的是响应体不是 JSON 的情况——会话过期被重定向到登录页拿到的是 HTML。 */
function _reqJson(u,opt){
  return fetch(u,opt).then(function(r){
    return r.json().then(function(d){
      if(d&&typeof d==='object')return d;
      return {success:false,message:T('msg.session_expired','请求失败或会话已失效，请重新登录'),code:r.status};
    },function(){
      return {success:false,message:T('msg.session_expired','请求失败或会话已失效，请重新登录'),code:r.status};
    });
  });
}
var R={
  get:function(u){return _reqJson(u)},
  post:function(u,d){return _reqJson(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})})},
  put:function(u,d){return _reqJson(u,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})})},
  del:function(u){return _reqJson(u,{method:'DELETE'})}
};
/* ============ 时间格式化 / 登录态（管理端与用户控制台两份外壳共用，只此一份） ============ */
/* 库里存的一律是 UTC（ISO 带 Z 或 SQLite 的 'YYYY-MM-DD HH:MM:SS'），展示时换算到配置时区。
   TZ_OFFSET 是各页面外壳声明的全局量，本函数在调用时才读它，与声明顺序无关 */
function fmtDT(d){
  if(!d)return '-';
  var s=String(d).trim();if(!s)return '-';
  /* 毫秒以下精度各浏览器解析不一致，展示只到秒，直接抹掉小数部分 */
  var iso=s.replace(' ','T').replace(/\.\d+/,'');
  if(!/[Zz]$|[+-]\d{2}:?\d{2}$/.test(iso))iso+='Z';
  var t=Date.parse(iso);
  if(isNaN(t))return s.replace('T',' ').substring(0,19);
  var off=(TZ_OFFSET===null)?(-new Date().getTimezoneOffset()/60):TZ_OFFSET;
  return new Date(t+off*3600000).toISOString().replace('T',' ').substring(0,19);
}
function doLogout(){
  R.post('/admin/api/auth/logout').then(function(){window.location.href='/login'});
}
function esc(s){return String(s===null||s===undefined?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function num(n){return (parseInt(n)||0).toLocaleString('en-US')}
/* ============ 状态圆点 ============ */
/* 表格状态列只有一个色点：hover 说明放 title（鼠标侧），语义文本放紧随其后的 .sr-only
   （读屏侧），圆点本体 aria-hidden 以免两边被念两遍。
   新增状态列一律用它，不要再直写 <i class="dot ...">——漏一个 .sr-only，那一列对读屏就是空的 */
function dotHtml(cls,text){
  var t=esc(text);
  return '<i class="dot '+cls+'" title="'+t+'" aria-hidden="true"></i><span class="sr-only">'+t+'</span>';
}
/* ============ 分页（各列表共用） ============ */
/* 一份状态表 + 每张列表注册一个「按当前页重绘」的回调：翻页只重绘那张表，
   不动同一页面上的其它内容（弹窗里的列表翻页也不会把表单里填了一半的内容清掉） */
var _pg={},_pgRender={};
function pgPage(key){return _pg[key]||1}
function pgBar(key,total,per){
  var tp=Math.max(1,Math.ceil(total/per)),cp=Math.min(pgPage(key),tp);
  _pg[key]=cp;
  function b(label,p,disabled){
    return '<button class="btn btn-sm btn-ghost" data-act="pg-go" data-key="'+key+'" data-p="'+p+'"'+(disabled?' disabled':'')+'>'+label+'</button>';
  }
  return '<div class="flex pager">'+b(T('pager.first','首页'),1,cp<=1)+b(T('pager.prev','上一页'),cp-1,cp<=1)+
    '<span class="dim small pg-info">'+T('pager.info','第 {cur} 页 / 共 {total} 页',{cur:cp,total:tp})+'</span>'+
    b(T('pager.next','下一页'),cp+1,cp>=tp)+b(T('pager.last','末页'),tp,cp>=tp)+'</div>';
}
/** 前端分页：返回当前页数据与分页条 HTML */
function pgSlice(items,key,per){
  var total=items.length,tp=Math.max(1,Math.ceil(total/per)),cp=Math.min(pgPage(key),tp);
  _pg[key]=cp;
  return {rows:items.slice((cp-1)*per,cp*per),bar:pgBar(key,total,per)};
}
/* 翻页事件：用户控制台与登录页没有面板那套事件委托，这里自带一份 */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act="pg-go"]'):null;
  if(!el)return;
  _pg[el.dataset.key]=Math.max(1,parseInt(el.dataset.p)||1);
  var rf=_pgRender[el.dataset.key];if(rf)rf();
});
/* ============ 浮层通知：固定右上角，不占用页面布局，不挤压其它元素 */
function toast(msg,type,title){
  var wrap=document.getElementById('toasts');
  if(!wrap){
    wrap=document.createElement('div');wrap.id='toasts';wrap.className='toasts';
    // 浮层通知不入焦点流，读屏用户只能靠 live region 知道「刚才那步成功了没」
    wrap.setAttribute('role','status');wrap.setAttribute('aria-live','polite');
    document.body.appendChild(wrap);
  }
  var t=type||'info';
  var glyph={success:'✓',error:'!',warn:'!',info:'i'}[t]||'i';
  var el=document.createElement('div');el.className='toast '+t;
  // 失败是「出了事」，单独用 alert 让读屏打断当前播报；其余按 polite 排队念
  if(t==='error'){el.setAttribute('role','alert');el.setAttribute('aria-live','assertive')}
  el.innerHTML='<span class="ic">'+glyph+'</span><div class="tx">'+(title?'<b>'+esc(title)+'</b>':'')+esc(msg)+'</div><span class="x">×</span>';
  wrap.appendChild(el);
  var timer=setTimeout(close,t==='error'?5000:2800);
  function close(){clearTimeout(timer);if(!el.parentNode)return;el.classList.add('out');setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el)},170)}
  el.querySelector('.x').addEventListener('click',close);
  return el;
}
/* 复制文本：优先 Clipboard API；自托管 prod 常以 http://ip:5000 直连，非安全上下文下
   navigator.clipboard 为 undefined，调用即抛 TypeError，故回退 execCommand('copy')，
   仍失败给明确提示，而不是静默失败、让用户以为已复制 */
function _legacyCopy(text){
  try{
    var ta=document.createElement('textarea');
    ta.value=text;ta.setAttribute('readonly','');
    ta.style.position='fixed';ta.style.top='-1000px';ta.style.opacity='0';
    document.body.appendChild(ta);
    ta.select();ta.setSelectionRange(0,ta.value.length);
    var ok=document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  }catch(e){return false}
}
function copyText(text,okMsg){
  var t=String(text==null?'':text);
  function ok(){toast(okMsg||T('msg.copied','已复制到剪贴板'),'success')}
  function fail(){toast(T('msg.copy_failed','复制失败，请手动选择'),'error')}
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).then(ok,function(){if(_legacyCopy(t))ok();else fail()});
  }else if(_legacyCopy(t))ok();else fail();
}
/* 焦点陷阱：Tab 在弹窗内循环（背后页面此时被遮住，Tab 过去等于焦点凭空消失）。
   关闭时把焦点还给打开弹窗前的那个元素——否则焦点掉回 <body>，键盘用户得从头 Tab 一遍 */
function _trapFocus(ov){
  var prev=document.activeElement,box=ov.querySelector('.modal');
  // 先把焦点移进弹窗：焦点留在触发按钮上时，Tab 的起点在弹窗外，陷阱拦不住第一步
  if(box){box.setAttribute('tabindex','-1');try{box.focus({preventScroll:true})}catch(e){box.focus()}}
  ov.addEventListener('keydown',function(e){
    if(e.key!=='Tab')return;
    var f=ov.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])');
    if(!f.length)return;
    var first=f[0],last=f[f.length-1],cur=document.activeElement;
    // 焦点还在容器上（刚打开）或已经跑到弹窗外：按方向补到另一端
    var edge=(!ov.contains(cur))||cur===box;
    if(e.shiftKey){if(cur===first||edge){e.preventDefault();last.focus()}}
    else if(cur===last||edge){e.preventDefault();first.focus()}
  });
  var raw=ov.remove.bind(ov);
  ov.remove=function(){raw();if(prev&&prev.focus)prev.focus()};
}
/* 「取消」的统一入口：Esc、点遮罩、底部取消按钮都走这里——放弃改动并把弹窗关掉。
   先派发 modal-esc 让确认类弹窗 resolve(false)，再移除遮罩 */
function _closeOverlay(ov){
  ov.dispatchEvent(new Event('modal-esc'));
  ov.remove();
}
/* 打开弹窗。
   右上角 X 的语义是「取消并关闭」：放弃本窗改动，与点遮罩、按 Esc 同走 _closeOverlay。
   要保存必须显式点底部操作条里的「保存」，各页自己绑定的保存逻辑照旧（成功才关、
   失败留在弹窗报错、按钮 disabled 时不提交）。
   DOM 结构固定为 头部（标题 + X）/ 正文（唯一滚动区）/ 底部操作条，X 与操作条都不滚动。 */
function openModal(inner,id){
  var ov=document.createElement('div');ov.className='modal-overlay';if(id)ov.id=id;
  // role/aria-modal：让读屏把这里当独立的一层，不再去念背后被遮住的页面
  ov.setAttribute('role','dialog');ov.setAttribute('aria-modal','true');
  ov.innerHTML='<div class="modal">'+inner+'</div>';
  var box=ov.querySelector('.modal');
  var head=document.createElement('div');head.className='modal-head';
  var x=document.createElement('button');
  x.type='button';x.className='modal-x';x.innerHTML='&times;';
  var xlab=esc(T('btn.close','关闭'));x.title=xlab;x.setAttribute('aria-label',xlab);
  head.appendChild(x);
  var body=document.createElement('div');body.className='modal-body';
  var acts=null;
  while(box.firstChild){
    var n=box.removeChild(box.firstChild);
    // 标题与确认框图标一起进头部：图标靠 CSS 独占一行（压住标题），标题与 X 同处第二行。
    // 各自最多收一个，页面重复写了也不挤进头部
    var isH3=n.nodeType===1&&n.tagName==='H3';
    var isIc=n.nodeType===1&&n.classList.contains('confirm-ic');
    if((isH3&&!head.querySelector('h3'))||(isIc&&!head.querySelector('.confirm-ic')))head.insertBefore(n,x);
    else if(n.nodeType===1&&n.classList.contains('modal-actions'))acts=n;
    else body.appendChild(n);
  }
  box.appendChild(head);box.appendChild(body);if(acts)box.appendChild(acts);
  // X = 取消并关闭：与底部「取消」完全等价，放弃改动后关掉；保存走底部操作条的保存按钮
  x.addEventListener('click',function(){_closeOverlay(ov)});
  ov.addEventListener('mousedown',function(e){ov._down=(e.target===ov)});
  ov.addEventListener('click',function(e){if(e.target===ov&&ov._down)_closeOverlay(ov)});
  document.body.appendChild(ov);
  _trapFocus(ov);
  return ov;
}
/* 确认弹窗：替代原生 confirm，返回 Promise<boolean>；requireText 用于不可逆操作 */
function uiConfirm(o){
  o=o||{};
  return new Promise(function(resolve){
    var danger=!!o.danger,need=o.requireText||'';
    var h='<div class="confirm-ic">'+(danger?'!':'?')+'</div><h3>'+esc(o.title||T('confirm.title','确认操作'))+'</h3>'+
      '<div class="cd">'+esc(o.message||'')+'</div>'+
      (need?'<label>'+esc(T('confirm.type_before','输入'))+' <span class="mono">'+esc(need)+'</span> '+esc(T('confirm.type_after','以确认'))+'</label><input class="input" id="cf-text" autocomplete="off" style="width:100%">':'')+
      '<div class="modal-actions"><button class="btn" data-act="cf-no">'+esc(o.cancelText||T('btn.cancel','取消'))+'</button>'+
      '<button class="btn '+(danger?'btn-danger-solid':'btn-primary')+'" data-act="cf-yes"'+(need?' disabled':'')+'>'+esc(o.confirmText||T('btn.confirm','确认'))+'</button></div>';
    var ov=openModal(h,'cf-modal');
    var box=ov.querySelector('.modal');box.classList.add('confirm');if(danger)box.classList.add('danger');
    var yes=ov.querySelector('[data-act="cf-yes"]');
    var done=function(v){if(ov.parentNode)ov.remove();resolve(v)};
    ov.querySelector('[data-act="cf-no"]').addEventListener('click',function(){done(false)});
    ov.querySelector('[data-act="cf-yes"]').addEventListener('click',function(){done(true)});
    ov.addEventListener('click',function(e){if(e.target===ov)setTimeout(function(){if(!ov.parentNode)resolve(false)},0)});
    ov.addEventListener('modal-esc',function(){done(false)});
    if(need){
      var inp=ov.querySelector('#cf-text');inp.focus();
      inp.addEventListener('input',function(){yes.disabled=inp.value.trim()!==need});
      inp.addEventListener('keydown',function(e){if(e.key==='Enter'&&!yes.disabled)done(true)});
    }
  });
}
/* 纯告知弹窗：只有「知道了」。自带关闭绑定，不依赖各页面自己的事件委托 */
function alertModal(title,message){
  var ov=openModal('<div class="confirm-ic">!</div><h3>'+esc(title)+'</h3>'+
    '<div class="cd">'+esc(message||'')+'</div>'+
    '<div class="modal-actions"><button class="btn btn-primary" id="alert-ok">'+esc(T('alert.ok','知道了'))+'</button></div>');
  ov.querySelector('.modal').classList.add('confirm');
  ov.querySelector('#alert-ok').addEventListener('click',function(){ov.remove()});
  return ov;
}
/* 弹窗内回车提交 / 自动聚焦首个输入框 */
function modalForm(ov,submit){
  var f=ov.querySelector('input:not([type=hidden]),select,textarea');if(f)f.focus();
  ov.addEventListener('keydown',function(e){
    if(e.key!=='Enter')return;
    var t=e.target;
    if(t&&(t.tagName==='TEXTAREA'||t.tagName==='BUTTON'||t.disabled))return;
    submit();
  });
}
/* 按钮忙碌态：防重复提交 */
function btnBusy(btn,on,label){
  if(!btn)return;
  if(btn.tagName==='BUTTON'){
    if(on){if(btn.dataset._t===undefined)btn.dataset._t=btn.innerHTML;btn.disabled=true;btn.textContent=label||T('msg.processing','处理中…')}
    else{btn.disabled=false;if(btn.dataset._t!==undefined){btn.innerHTML=btn.dataset._t;delete btn.dataset._t}}
  }else{
    btn.style.pointerEvents=on?'none':'';
    btn.style.opacity=on?'.55':'';
  }
}
/* 展示完整凭证（新建 evkey 等一次性结果） */
function showSecret(title,secret,note){
  var h='<h3>'+esc(title)+'</h3>'+(note?'<p class="dim small modal-sub">'+esc(note)+'</p>':'')+
    '<div class="panel mono" id="secret-val" style="word-break:break-all">'+esc(secret)+'</div>'+
    '<div class="modal-actions"><button class="btn btn-primary" data-act="copy-secret">'+esc(T('btn.copy','复制'))+'</button></div>';
  var ov=openModal(h,'secret-modal');
  ov.querySelector('[data-act="copy-secret"]').addEventListener('click',function(){
    copyText(secret);
  });
}
/* Esc 关闭最上层弹窗 */
document.addEventListener('keydown',function(e){
  if(e.key!=='Escape')return;
  var ovs=document.querySelectorAll('.modal-overlay');
  if(!ovs.length)return;
  var top=ovs[ovs.length-1];
  _closeOverlay(top);
});
/* ============ 权限记录（会员变动） ============ */
/* 管理面板的「我的」页与用户控制台共用同一张表与同一个渲染器：同一份数据两处展示，
   表体必须逐字一致，否则两边的解读会莫名其妙地不同。
   「类型」列只给圆点，含义由两处卡片头各自的图例承担（两处都必须列出同一份图例）。 */
function memberActionBadge(a){
  var hit={set:['dot-violet',T('member.action_set','管理员调整')],
    activate:['dot-on',T('member.action_activate','激活码开通')],
    expire:['dot-off',T('member.action_expire','到期归位')]}[a];
  if(!hit)hit=['dot-off',a||T('member.action_other','变动')];
  return dotHtml(hit[0],hit[1]);
}
/* 到期日 '' = 永久有效；回落组 0 = 不转移；组 id 0 = 变动前还没有会员身份（激活开通） */
function _mlExp(v){return v?String(v):T('member.forever','永久')}
function _mlGroup(name,gid){return name||(gid>0?T('member.group_n','用户组 #{n}',{n:gid}):'—')}
function _mlFallback(name,gid){
  var hit=name||(gid>0?T('member.group_n','用户组 #{n}',{n:gid}):'');
  return hit||T('member.no_transfer','不转移');
}
function memberChanges(l){
  var out=[];
  if(String(l.old_group_name||l.old_group_id)!==String(l.new_group_name||l.new_group_id))
    out.push(T('member.chg_group','用户组 {name}',{name:_mlGroup(l.old_group_name,l.old_group_id)})
      +' → '+_mlGroup(l.new_group_name,l.new_group_id));
  if(String(l.old_expires_on||'')!==String(l.new_expires_on||''))
    out.push(T('member.chg_exp','到期日 {v}',{v:_mlExp(l.old_expires_on)})
      +' → '+_mlExp(l.new_expires_on));
  if(String(l.old_fallback_name||l.old_fallback_group_id)!==String(l.new_fallback_name||l.new_fallback_group_id))
    out.push(T('member.chg_fallback','到期回落 {v}',{v:_mlFallback(l.old_fallback_name,l.old_fallback_group_id)})
      +' → '+_mlFallback(l.new_fallback_name,l.new_fallback_group_id));
  return out;
}
function memberLogRows(items){
  if(!items||!items.length)return '<div class="empty">'+esc(T('empty.member_logs','暂无权限变动记录'))+'</div>';
  var h='<table><thead><tr><th>'+T('member.col_time','时间')+'</th><th class="col-dot">'+T('member.col_type','类型')+
    '</th><th>'+T('member.col_change','变动内容')+'</th><th>'+T('member.col_reason','原因')+
    '</th><th>'+T('member.col_admin','操作人')+'</th></tr></thead><tbody>';
  items.forEach(function(l){
    var ch=memberChanges(l);
    h+='<tr><td class="dim">'+esc(fmtDT(l.created_at))+'</td>'+
      '<td class="col-dot">'+memberActionBadge(l.action)+'</td>'+
      '<td>'+esc(ch.length?ch.join(T('member.join_sep','；')):'—')+'</td>'+
      '<td class="dim">'+esc(l.reason||'—')+'</td>'+
      '<td class="dim">'+esc(l.admin_name||T('member.system','系统'))+'</td></tr>';
  });
  return h+'</tbody></table>';
}
/* ============ 密码可见 ============ */
/* 只切换 input 的 type，字段名、提交逻辑与自动完成属性一概不动 */
/* 图标用内联 SVG，不用文字：按钮压在输入框右边缘，写「显示/隐藏」会把密码挤掉一截，
   而且中文两字按钮的宽度随字体变化，几个页面的按钮宽度还对不齐 */
var _PW_EYE='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.8 12S5.9 5.8 12 5.8 22.2 12 22.2 12 18.1 18.2 12 18.2 1.8 12 1.8 12Z"/><circle cx="12" cy="12" r="3.1"/></svg>';
var _PW_EYE_OFF='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.8 12S5.9 5.8 12 5.8c1.9 0 3.5.5 4.9 1.2M22.2 12s-4.1 6.2-10.2 6.2c-1.9 0-3.5-.5-4.9-1.2"/><path d="M9.8 9.8a3.1 3.1 0 0 0 4.4 4.4"/><path d="M3.2 3.2 20.8 20.8"/></svg>';
/* 按钮文字由脚本填：初始态是「闭眼」（密码当前不可见），点击后换「睁眼」 */
function pwPaint(btn){
  var on=btn.getAttribute('aria-pressed')==='true';
  btn.innerHTML=on?_PW_EYE:_PW_EYE_OFF;
  btn.title=on?T('pw.hide','隐藏密码'):T('pw.show','显示密码');
  btn.setAttribute('aria-label',btn.title);
}
function pwToggle(btn){
  var box=btn.closest('.pw');if(!box)return;
  var inp=box.querySelector('input');if(!inp)return;
  var show=inp.type==='password';
  inp.type=show?'text':'password';
  btn.setAttribute('aria-pressed',show?'true':'false');
  pwPaint(btn);
}
/* 自带绑定：面板页有全局 data-act 委托，用户控制台与登录页没有，靠委托会点不动 */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act="pw-toggle"]'):null;
  if(el)pwToggle(el);
});
/* 初始图标：脚本在按钮之前解析，元素还不存在，等 DOM 就绪再统一刷一遍 */
document.addEventListener('DOMContentLoaded',function(){
  var bs=document.querySelectorAll('[data-act="pw-toggle"]');
  for(var i=0;i<bs.length;i++)pwPaint(bs[i]);
});
/* ============ 深色主题切换 ============ */
/* 口径与 <head> 里那段防闪白脚本完全一致：选过就以 localStorage 为准，没选过跟随系统。
   按钮自带绑定（同上：用户控制台与登录页没有面板的全局 data-act 委托），并顺带刷图标与悬停说明 */
var THEME_KEY='ink_theme';
var _MOON='<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 9.6A5.8 5.8 0 0 1 6.4 2.5a5.8 5.8 0 1 0 7.1 7.1z"/></svg>';
var _SUN='<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="3.1"/><path d="M8 1.6v1.5M8 12.9v1.5M1.6 8h1.5M12.9 8h1.5M3.5 3.5l1.1 1.1M11.4 11.4l1.1 1.1M12.5 3.5l-1.1 1.1M4.6 11.4l-1.1 1.1"/></svg>';
function currentTheme(){
  var t=null;
  try{t=localStorage.getItem(THEME_KEY)}catch(e){}
  if(t==='dark'||t==='light')return t;
  return (window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)?'dark':'light';
}
function themePaint(){
  var dark=document.documentElement.classList.contains('dark');
  var tip=dark?T('theme.to_light','切换到浅色'):T('theme.to_dark','切换到深色');
  var bs=document.querySelectorAll('[data-act="theme-toggle"]');
  for(var i=0;i<bs.length;i++){
    bs[i].innerHTML=dark?_SUN:_MOON;
    bs[i].title=tip;bs[i].setAttribute('aria-label',tip);
  }
}
function setTheme(t){
  var root=document.documentElement;
  if(t==='dark')root.classList.add('dark');else root.classList.remove('dark');
  try{localStorage.setItem(THEME_KEY,t)}catch(e){}
  themePaint();
}
function toggleTheme(){setTheme(document.documentElement.classList.contains('dark')?'light':'dark')}
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act="theme-toggle"]'):null;
  if(el)toggleTheme();
});
document.addEventListener('DOMContentLoaded',function(){
  /* 未选择主题时系统偏好可能在页面打开后才变（macOS 按日落自动切换），跟着走 */
  if(window.matchMedia){
    var mq=window.matchMedia('(prefers-color-scheme:dark)');
    var onSys=function(){var t=null;try{t=localStorage.getItem(THEME_KEY)}catch(e){}if(t!=='dark'&&t!=='light')setTheme(mq.matches?'dark':'light')};
    if(mq.addEventListener)mq.addEventListener('change',onSys);else if(mq.addListener)mq.addListener(onSys);
  }
  themePaint();
});
/* ============ 限额与配额的取值口径（面板、用户控制台共用） ============ */
/* 0 与 -1 都是合法上限，取默认值不能写 `|| 默认`（`0||-1` 会把「禁止」变成「不限」） */
function _intVal(v,d){var n=parseInt(v,10);return isNaN(n)?d:n}
/* EVkey 持有上限三态：-1 = 不限，0 = 该组禁止创建，N = 最多 N 个 */
function evkeyLimitText(v){
  var n=_intVal(v,null);
  if(n===null)return '-';
  if(n<0)return T('user.unlimited','不限');
  if(n===0)return T('user.forbidden','禁止');
  return T('user.evkey_limit_n','{n}',{n:n});
}
/* 设备上限三态同 evkey：-1 = 不限，0 = 该组禁止绑定，N = 最多 N 台
   （上限 0 不能念成「0 台」，那会被读成不限）。面板与用户控制台共用这一份口径 */
function devLimitText(v){
  var n=_intVal(v,null);
  if(n===null)return '-';
  if(n<0)return T('device.unlimited','不限');
  if(n===0)return T('device.forbidden','禁止');
  return num(n);
}
/* 配额两种模式共用一个字段 quota_period：day/week/month/year = 按时间周期（到点归零），
   trial = 按次总量（用完即止、永不重置）。
   下拉框用完整说法（每日），表格列拼「N次/月」用单字标签（日），两套标签分开取词。 */
var _QUOTA_UNITS=[['day','user.period_day','每日'],['week','user.period_week','每周'],
  ['month','user.period_month','每月'],['year','user.period_year','每年']];
var _QUOTA_PERIODS=[['day','user.period_short_day','日'],['week','user.period_short_week','周'],
  ['month','user.period_short_month','月'],['year','user.period_short_year','年'],
  ['trial','user.period_trial_short','总量']];
function _periodLabel(p){
  var hit=_QUOTA_PERIODS.find(function(x){return x[0]===p});
  return hit?T(hit[1],hit[2]):T('user.period_short_day','日');
}
function quotaText(g){
  var lim=_intVal(g.quota_limit,0);
  if(lim<=0)return T('user.unlimited','不限');
  if(String(g.quota_period)==='trial')return T('user.quota_trial','{n}次/总量',{n:lim});
  return T('user.quota_period','{n}次/{period}',{n:lim,period:_periodLabel(g.quota_period)});
}
/* ============ 通知中心（顶栏铃铛 + 弹窗）：管理端与用户控制台共用 ============ */
/* 两栏：公告（站内信，全站广播，不可删除）与通知（个人事件：设备被删、权限变更、系统）。
   数据源 /admin/api/my/announcements 与 /admin/api/my/notifications。文案不存服务端 ——
   只存 kind + payload 快照，这里现场渲染，中英切换不会露出另一种语言 */
var _annItems=[],_notifItems=[],_NOTIF_PER_PAGE=5;
/* 不同类别不同图标（16 viewBox / stroke=currentColor / 1.5），kind 与后端一一对应；
   未知 kind 落到 system，宁可图标泛一点，也不给空位 */
var _NOTIF_ICON={
  device_deleted:'<rect x="3.5" y="2.5" width="9" height="11" rx="1.5"/><path d="M2 14 14 2"/>',
  membership:'<path d="M8 2l5 1.5v4c0 3-2.2 5.2-5 6.5-2.8-1.3-5-3.5-5-6.5v-4z"/>',
  system:'<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 5.4h.01"/>'
};
function _notifIcon(kind){
  var p=_NOTIF_ICON[kind]||_NOTIF_ICON.system;
  return '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';
}
function _notifKindLabel(kind){
  if(kind==='device_deleted')return T('notif.kind_device_deleted','设备已被删除');
  if(kind==='membership')return T('notif.kind_membership','权限变更');
  return T('notif.kind_system','系统消息');
}
/* kind + payload → 可读文案。membership 一事一议：到期归位报「转入的组」，
   组名变了报新组名，只有到期日动了才报日期——三种都报同一句会答非所问 */
function _notifText(n){
  var p=n.payload||{};
  if(n.kind==='device_deleted')return T('notif.body_device_deleted','设备「{name}」已被管理员删除。',{name:p.name||''});
  if(n.kind==='membership'){
    if(p.action==='expire')return T('notif.body_membership_group','用户组已调整为 {group}',{group:p.group_name||p.fallback_group_name||''});
    if((p.new_group_name||'')!==(p.old_group_name||''))return T('notif.body_membership_group','用户组已调整为 {group}',{group:p.new_group_name||''});
    return T('notif.body_membership_expires','到期日已调整为 {date}',{date:p.expires_on||''});
  }
  return n.body||n.title||_notifKindLabel(n.kind);
}
function notifRender(){
  var box=document.getElementById('notif-list');if(!box)return;
  var pg=pgSlice(_notifItems,'notif-event',_NOTIF_PER_PAGE);
  if(!_notifItems.length){
    box.innerHTML='<div class="empty">'+esc(T('notif.empty','暂无通知'))+'</div>';
  }else{
    box.innerHTML='<div class="notif-list">'+pg.rows.map(function(n){
      var label=_notifKindLabel(n.kind);
      return '<div class="notif-item"><span class="ic" title="'+esc(label)+'">'+_notifIcon(n.kind)+'</span>'+
        '<div class="tx">'+esc(_notifText(n))+'</div>'+
        '<span class="meta">'+esc(fmtDT(n.created_at))+'</span>'+
        '<button class="del" type="button" data-act="notif-del" data-id="'+n.id+'" title="'+esc(T('notif.del_title','删除通知'))+'" aria-label="'+esc(T('notif.del_title','删除通知'))+'">'+
        '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button></div>';
    }).join('')+'</div>';
  }
  notifFoot();
}
_pgRender['notif-event']=notifRender;
function annRender(){
  var box=document.getElementById('notif-ann');if(!box)return;
  var pg=pgSlice(_annItems,'notif-ann',_NOTIF_PER_PAGE);
  if(!_annItems.length){
    box.innerHTML='<div class="empty">'+esc(T('notif.ann_empty','暂无公告'))+'</div>';
  }else{
    box.innerHTML='<div class="ann-list">'+pg.rows.map(function(a){
      return '<div class="ann-item"><div class="h"><b>'+esc(a.title)+'</b><span class="meta">'+esc(fmtDT(a.created_at))+'</span></div>'+
        (a.content?'<div class="body">'+esc(a.content)+'</div>':'')+'</div>';
    }).join('')+'</div>';
  }
  notifFoot();
}
_pgRender['notif-ann']=annRender;
/* 底部固定栏只渲染「当前页签」的翻页条：公告与通知都有分页，口径一致，且都不跟着条目滚动。
   两个页签的数据可能先后异步到达，按显示状态取当前页签，避免晚到的数据把另一页的翻页条覆盖掉 */
function notifFoot(){
  var foot=document.getElementById('notif-foot');if(!foot)return;
  var ann=document.getElementById('notif-ann');
  var onAnn=!ann||ann.style.display!=='none';
  var pg=onAnn?pgSlice(_annItems,'notif-ann',_NOTIF_PER_PAGE)
               :pgSlice(_notifItems,'notif-event',_NOTIF_PER_PAGE);
  foot.innerHTML=pg.bar;
  foot.style.display='';
}
function notifTab(tab){
  var ann=document.getElementById('notif-ann'),ev=document.getElementById('notif-list');
  if(!ann||!ev)return;
  ann.style.display=(tab==='ann')?'':'none';
  ev.style.display=(tab==='ann')?'none':'';
  notifFoot();
  var tabs=document.querySelectorAll('[data-act="notif-tab"]');
  for(var i=0;i<tabs.length;i++)tabs[i].classList.toggle('on',tabs[i].dataset.tab===tab);
}
function setNotifDot(n){
  /* 管理端同一时刻可能有两只铃铛在 DOM 里（侧栏底部 + 顶栏），逐个开关 */
  var els=document.querySelectorAll('.notif-dot');
  for(var i=0;i<els.length;i++)els[i].style.display=(n>0)?'block':'none';
}
function loadAnnouncements(){
  R.get('/admin/api/my/announcements').then(function(d){
    if(!d||d.success===false)return;
    _annItems=d.items||[];
    if(document.getElementById('notif-ann'))annRender();
  }).catch(function(){});
}
function loadNotifications(){
  R.get('/admin/api/my/notifications?limit=100').then(function(d){
    if(!d||d.success===false)return;
    _notifItems=d.items||[];
    setNotifDot(d.unread||0);
    if(document.getElementById('notif-list'))notifRender();
  }).catch(function(){});
}
function openNotifications(){
  var h='<h3>'+esc(T('notif.title','通知中心'))+'</h3>'+
    '<div class="acc-tabs">'+
      '<span class="acc-tab on" data-act="notif-tab" data-tab="ann">'+esc(T('notif.tab_ann','公告'))+'</span>'+
      '<span class="acc-tab" data-act="notif-tab" data-tab="event">'+esc(T('notif.tab_event','通知'))+'</span></div>'+
    '<div class="notif-body"><div id="notif-ann"></div><div id="notif-list" style="display:none"></div></div>'+
    '<div class="notif-foot" id="notif-foot" style="display:none"></div>';
  openModal(h,'notif-modal');
  annRender();notifRender();
  notifTab('ann');
  /* 打开即全部标为已读（公告不参与未读），红点清零：同一条不会二次打扰。
     定时刷新只回读未读数，新事件才会把红点点亮 */
  R.post('/admin/api/my/notifications/read',{all:true}).then(function(d){
    if(d&&d.success!==false)setNotifDot(d.unread||0);
  }).catch(function(){});
}
/* 单条删除静默生效（与启用/停用、单条审批同一套体验）：条目当场消失就是反馈，
   再弹一句「已删除」只是噪音；只有失败才出声 */
function deleteNotification(id){
  R.del('/admin/api/my/notifications/'+id).then(function(d){
    if(!d||d.success===false){toast((d&&d.message)||T('msg.network_error','网络错误'),'error');return}
    _notifItems=_notifItems.filter(function(n){return n.id!==id});
    setNotifDot(d.unread||0);
    notifRender();
  }).catch(function(){toast(T('msg.network_error','网络错误'),'error')});
}
/* 铃铛 / 页签 / 删除三个动作的委托（管理面板另有自己的 data-act 委托，两边互不认识对方的键名） */
document.addEventListener('click',function(e){
  var el=e.target.closest?e.target.closest('[data-act]'):null;
  if(!el)return;
  var act=el.dataset.act;
  if(act==='notif-open')openNotifications();
  else if(act==='notif-tab')notifTab(el.dataset.tab);
  else if(act==='notif-del')deleteNotification(parseInt(el.dataset.id,10));
});
/* 没有铃铛的页面（登录 / 注册 / 访客页）不发这两个请求，也不起定时器 */
if(document.querySelector('[data-act="notif-open"]')){
  loadAnnouncements();loadNotifications();
  /* 未读数定时刷新；页面被隐藏时跳过（切回来那次 tick 会立刻补上） */
  setInterval(function(){if(!document.hidden)loadNotifications()},60000);
}
