LOGIN_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>eInkViews</title>
<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;color:var(--fg)}
.login-card{background:var(--ds-background-100);border-radius:var(--r-md);padding:40px 32px;width:360px;max-width:100%;box-shadow:var(--sh-2)}
.login-card h1{font-size:24px;font-weight:600;letter-spacing:-.6px;margin-bottom:24px}
input,button{font-family:inherit;font-size:inherit}
.input{width:100%;height:40px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;transition:box-shadow var(--motion-fast);margin-bottom:16px;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);background:var(--ds-background-100);color:var(--fg)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.btn{display:block;width:100%;height:40px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;transition:all var(--motion-fast)}
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100)}
.btn-primary:hover{background:var(--ds-gray-900)}
.link{font-size:12px;margin-top:16px;color:var(--fg2);text-align:center}
.link a{color:var(--fg);text-decoration:underline;text-underline-offset:2px;text-decoration-color:var(--fg3)}
.link a:hover{text-decoration-color:var(--fg)}
.link .link-sep{margin:0 8px;color:var(--faint)}
</style>
{{THEME_INIT}}
</head>
<body>
<div class="login-card">
  <h1>eInkViews</h1>
  <input class="input" type="text" id="username-input" placeholder="{{T:auth.username}}" autocomplete="off">
  <div class="pw pw-block"><input class="input" type="password" id="password-input" placeholder="{{T:auth.password}}" autocomplete="current-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <button class="btn btn-primary" id="submit-btn" data-act="login">{{T:login.submit}}</button>
  <div class="link">
    <!-- register-link:start -->
    <a href="/register">{{T:login.register}}</a><span class="link-sep">·</span>
    <!-- register-link:end -->
    <a href="/reset-password">{{T:login.forgot}}</a>
  </div>
</div>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
async function doLogin(btn){
  var u=document.getElementById('username-input').value.trim(),p=document.getElementById('password-input').value.trim();
  if(!u){toast(T('login.need_username','请输入用户名'),'error');document.getElementById('username-input').focus();return}
  if(!p){toast(T('login.need_password','请输入密码'),'error');document.getElementById('password-input').focus();return}
  btnBusy(btn,true,T('login.busy','登录中…'));
  try{
    var r=await fetch('/admin/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    var d=await r.json();
    if(r.ok){toast(T('login.success','登录成功，正在跳转…'),'success');setTimeout(function(){window.location.href='/admin'},500)}
    else{btnBusy(btn,false);toast(d.message||T('login.failed','登录失败'),'error')}
  }catch(e){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')}
}
document.addEventListener('click',function(e){
  var el=e.target.closest('[data-act="login"]');
  if(el)doLogin(el);
});
document.getElementById('password-input').addEventListener('keydown',function(e){if(e.key==='Enter')doLogin(document.getElementById('submit-btn'))});
</script>
</body>
</html>'''

CHPASS_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:chpass.page_title}}</title>
<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;color:var(--fg)}
.card{background:var(--ds-background-100);border-radius:var(--r-md);padding:40px 32px;width:380px;max-width:100%;box-shadow:var(--sh-2)}
.card h1{font-size:24px;font-weight:600;letter-spacing:-.4px;margin-bottom:4px}
.card p{font-size:14px;color:var(--fg2);margin-bottom:24px}
input{font-family:inherit;font-size:inherit}
.input{width:100%;height:40px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;margin-bottom:16px;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);background:var(--ds-background-100);color:var(--fg)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.btn{display:block;width:100%;height:40px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;transition:all var(--motion-fast)}
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100)}
.btn-primary:hover{background:var(--ds-gray-900)}
</style>
{{THEME_INIT}}
</head>
<body>
<div class="card">
  <h1>{{T:chpass.title}}</h1>
  <p>{{T:chpass.desc}}</p>
  <div class="pw pw-block"><input class="input" type="password" id="pw1" placeholder="{{T:reset.new_password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <div class="pw pw-block"><input class="input" type="password" id="pw2" placeholder="{{T:reset.confirm_password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <button class="btn btn-primary" id="submit-btn" data-act="change-pw">{{T:chpass.submit}}</button>
</div>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
async function doChange(btn){
  var p1=document.getElementById('pw1').value,p2=document.getElementById('pw2').value;
  if(!p1||p1.length<6){toast(T('auth.pw_short','密码至少 6 位'),'error');return}
  if(p1!==p2){toast(T('auth.pw_mismatch','两次输入的密码不一致'),'error');return}
  btnBusy(btn,true,T('auth.submitting','提交中…'));
  try{
    var r=await fetch('/admin/api/auth/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p1})});
    var d=await r.json();
    if(r.ok){toast(T('chpass.success','密码已修改，正在跳转…'),'success');setTimeout(function(){window.location.href='/admin'},900)}
    else{btnBusy(btn,false);toast(d.message||T('chpass.failed','修改失败'),'error')}
  }catch(e){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')}
}
document.addEventListener('click',function(e){
  var el=e.target.closest('[data-act="change-pw"]');
  if(el)doChange(el);
});
document.getElementById('pw2').addEventListener('keydown',function(e){if(e.key==='Enter')doChange(document.getElementById('submit-btn'))});
</script>
</body>
</html>'''

REGISTER_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:register.page_title}}</title>
<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;color:var(--fg)}
.card{background:var(--ds-background-100);border-radius:var(--r-md);padding:40px 32px;width:400px;max-width:100%;box-shadow:var(--sh-2)}
.card h1{font-size:24px;font-weight:600;letter-spacing:-.6px;margin-bottom:4px}
.card p{font-size:14px;color:var(--fg2);margin-bottom:24px}
input,button{font-family:inherit;font-size:inherit}
.input{width:100%;height:40px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;margin-bottom:16px;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);background:var(--ds-background-100);color:var(--fg)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.btn{display:block;width:100%;height:40px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;transition:all var(--motion-fast)}
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100)}
.btn-primary:hover{background:var(--ds-gray-900)}
.footer{margin-top:16px;font-size:12px;color:var(--fg2)}
.footer a{color:var(--fg);text-decoration:underline;text-underline-offset:2px;text-decoration-color:var(--fg3)}
.footer a:hover{text-decoration-color:var(--fg)}
</style>
{{THEME_INIT}}
</head>
<body>
<div class="card">
  <h1>{{T:register.title}}</h1>
  <input class="input" id="name-input" placeholder="{{T:auth.username}}" autocomplete="off">
  <input class="input" id="email-input" type="email" placeholder="{{T:register.email}}" autocomplete="off">
  <div class="pw pw-block"><input class="input" type="password" id="password-input" placeholder="{{T:auth.password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <div class="pw pw-block"><input class="input" type="password" id="password2-input" placeholder="{{T:register.password2}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <input class="input" id="code-input" placeholder="{{T:register.code}}" autocomplete="off">
  <button class="btn btn-primary" id="submit-btn" data-act="register">{{T:register.submit}}</button>
  <div class="footer"><a href="/login">{{T:auth.back_login}}</a></div>
</div>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
async function doRegister(btn){
  var name=document.getElementById('name-input').value.trim();
  var email=document.getElementById('email-input').value.trim();
  var pwd=document.getElementById('password-input').value;
  var pwd2=document.getElementById('password2-input').value;
  var code=document.getElementById('code-input').value.trim();
  if(!name){toast(T('register.need_name','请填写用户名'),'error');document.getElementById('name-input').focus();return}
  if(!email){toast(T('register.need_email','请填写邮箱'),'error');document.getElementById('email-input').focus();return}
  if(email.indexOf('@')<0){toast(T('register.bad_email','邮箱格式不正确'),'error');document.getElementById('email-input').focus();return}
  if(!pwd){toast(T('register.need_password','请填写密码'),'error');document.getElementById('password-input').focus();return}
  if(pwd.length<6){toast(T('auth.pw_short','密码至少 6 位'),'error');return}
  if(pwd!==pwd2){toast(T('auth.pw_mismatch','两次输入的密码不一致'),'error');return}
  btnBusy(btn,true,T('register.busy','注册中…'));
  try{
    var r=await fetch('/admin/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,email:email,password:pwd,code:code})});
    var d=await r.json();
    if(d.success){toast(T('register.success','注册成功，即将跳转登录…'),'success');setTimeout(function(){window.location.href='/login'},1200)}
    else{btnBusy(btn,false);toast(d.message||T('register.failed','注册失败'),'error')}
  }catch(e){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')}
}
document.addEventListener('click',function(e){
  var el=e.target.closest('[data-act="register"]');
  if(el)doRegister(el);
});
document.getElementById('code-input').addEventListener('keydown',function(e){if(e.key==='Enter')doRegister(document.getElementById('submit-btn'))});
</script>
</body>
</html>'''

RESET_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:reset.page_title}}</title>
<style>
{{SHARED_UI_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;color:var(--fg)}
.card{background:var(--ds-background-100);border-radius:var(--r-md);padding:40px 32px;width:400px;max-width:100%;box-shadow:var(--sh-2)}
.card h1{font-size:24px;font-weight:600;letter-spacing:-.6px;margin-bottom:4px}
.card p{font-size:14px;color:var(--fg2);margin-bottom:24px}
input,button{font-family:inherit;font-size:inherit}
.input{width:100%;height:40px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;margin-bottom:16px;box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);background:var(--ds-background-100);color:var(--fg)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.btn{display:block;width:100%;height:40px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;transition:all var(--motion-fast)}
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100)}
.btn-primary:hover{background:var(--ds-gray-900)}
.footer{margin-top:16px;font-size:12px;color:var(--fg2)}
.footer a{color:var(--fg);text-decoration:underline;text-underline-offset:2px;text-decoration-color:var(--fg3)}
.footer a:hover{text-decoration-color:var(--fg)}
</style>
{{THEME_INIT}}
</head>
<body>
<div class="card">
  <h1>{{T:reset.title}}</h1>
  <p>{{T:reset.desc}}</p>
  <input class="input" id="name-input" placeholder="{{T:auth.username}}" autocomplete="off">
  <input class="input" id="email-input" type="email" placeholder="{{T:reset.email}}" autocomplete="off">
  <div class="pw pw-block"><input class="input" type="password" id="password-input" placeholder="{{T:reset.new_password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <div class="pw pw-block"><input class="input" type="password" id="password2-input" placeholder="{{T:reset.confirm_password}}" autocomplete="new-password"><button type="button" class="pw-eye" data-act="pw-toggle" aria-pressed="false"></button></div>
  <button class="btn btn-primary" id="submit-btn" data-act="reset">{{T:reset.submit}}</button>
  <div class="footer"><a href="/login">{{T:auth.back_login}}</a></div>
</div>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
async function doReset(btn){
  var name=document.getElementById('name-input').value.trim();
  var email=document.getElementById('email-input').value.trim();
  var pwd=document.getElementById('password-input').value;
  var pwd2=document.getElementById('password2-input').value;
  if(!name){toast(T('login.need_username','请输入用户名'),'error');document.getElementById('name-input').focus();return}
  if(!email){toast(T('reset.need_email','请填写注册邮箱'),'error');document.getElementById('email-input').focus();return}
  if(!pwd||pwd.length<6){toast(T('auth.pw_short','密码至少 6 位'),'error');document.getElementById('password-input').focus();return}
  if(pwd!==pwd2){toast(T('auth.pw_mismatch','两次输入的密码不一致'),'error');return}
  btnBusy(btn,true,T('auth.submitting','提交中…'));
  try{
    var r=await fetch('/admin/api/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,email:email,password:pwd})});
    var d=await r.json();
    if(d.success){toast(T('reset.success','密码已重置，即将跳转登录…'),'success');setTimeout(function(){window.location.href='/login'},1200)}
    else{btnBusy(btn,false);toast(d.message||T('reset.failed','重置失败'),'error')}
  }catch(e){btnBusy(btn,false);toast(T('msg.network_error','网络错误'),'error')}
}
document.addEventListener('click',function(e){
  var el=e.target.closest('[data-act="reset"]');
  if(el)doReset(el);
});
document.getElementById('password2-input').addEventListener('keydown',function(e){if(e.key==='Enter')doReset(document.getElementById('submit-btn'))});
</script>
</body>
</html>'''

USER_HTML = r'''<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{T:console.page_title}}</title>
<style>
{{SHARED_UI_CSS}}
{{ACCOUNT_CSS}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);background:var(--bg);color:var(--fg);font-size:14px;min-height:100vh;-webkit-font-smoothing:antialiased}
/* 浏览器默认把 <b>/<strong> 设成 700，面板页统一用 600；这里不跟着重置，同一段文案的字重会跳变 */
b,strong{font-weight:600}
nav{position:sticky;top:0;z-index:100;background:var(--topbar);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);height:56px;display:flex;align-items:center;padding:0 24px}
.logo{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:16px;letter-spacing:-.4px}
/* 用户名与图标按钮组贴到顶栏右缘；主题切换按钮排在用户名左边，所以自动边距落在用户名上 */
nav .user{margin-left:auto;font-size:14px;color:var(--fg2);display:flex;align-items:center;gap:8px}
/* 退出登录 / 主题切换都是图标按钮（与后台面板栏底那份同一个画法）：文字收进 title / aria-label，
   鼠标悬停给提示，不再在顶栏里占一段汉字 */
nav .user .icon-btn{width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:var(--r-sm);background:none;color:var(--fg2);cursor:pointer;padding:0}
nav .user .icon-btn:hover{color:var(--fg);background:var(--soft)}
nav .user .icon-btn svg{width:18px;height:18px}
/* 与后台面板的 main 用同一组内边距与同一个最大宽度：同一块屏幕换一边看，卡片宽窄与留白才一致 */
main{padding:24px 24px 64px;max-width:1400px;margin:0 auto}
.card{background:var(--ds-background-100);border-radius:var(--r-md);box-shadow:var(--card-shadow);margin-bottom:16px;overflow:hidden}
.card-header{padding:16px 24px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
/* .card-title / .card-desc 与后台面板同一套写法：标题与说明用 flex gap 排版，
   说明行不再靠自身 margin，否则带圆点图例的那几行间距和面板里差 3px */
.card-title{display:flex;flex-direction:column;gap:4px;min-width:0}
.card-title h2{font-size:16px;font-weight:600;letter-spacing:-.4px}
.card-desc{font-size:12px;color:var(--fg2);font-weight:400}
/* 卡片头右上角的计数小字（「已使用 N 个 / M」这类）：中文的 min-content 只有一个字宽，
   被挤压时会逐字竖排、看上去像被旁边的元素盖住。禁止收缩，保持整行 */
.card-header small,.card-header .acts .dim{white-space:nowrap;flex-shrink:0}
.card-header .acts>.dim+.btn{margin-left:8px}
/* 表格放卡片里：列宽不足时整卡横向滚动，而不是把最后一列挤成竖排 */
.card-body{padding:24px;overflow-x:auto}
.card.cfg .card-header{background:var(--soft);border-bottom-color:var(--line)}
.panel{background:var(--soft);border-radius:var(--r-sm);padding:16px;font-size:12px;box-shadow:var(--ring)}
/* .acts / .sep / 表格内边距与后台面板保持同一套数值，两边按钮间距与内容左边缘才对得上 */
.acts{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.acts .sep{width:1px;height:18px;background:var(--line);margin:0 4px;flex-shrink:0}
/* 表格里的操作按钮强制单行：宁可撑宽卡片横向滚动，也不让按钮折到下一行 */
td .acts{flex-wrap:nowrap}
input,button{font-family:inherit;font-size:inherit}
.input{width:100%;height:32px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;outline:none;background:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);color:var(--fg);transition:box-shadow var(--motion-fast)}
.input:hover{box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-600)}
.input:focus{box-shadow:inset 0 0 0 1px var(--ds-focus-color),var(--ds-focus-ring)}
.input::placeholder{color:var(--faint)}
.btn{display:inline-flex;align-items:center;justify-content:center;height:32px;padding:0 16px;border:none;border-radius:var(--r-sm);font-size:14px;font-weight:500;cursor:pointer;background:var(--ds-background-100);color:var(--fg);box-shadow:inset 0 0 0 1px var(--ds-gray-alpha-500);transition:all var(--motion-fast);white-space:nowrap;flex-shrink:0}
.btn:hover{background:var(--ds-gray-100)}
.btn-primary{background:var(--ds-gray-1000);color:var(--ds-background-100);box-shadow:inset 0 0 0 1px var(--ds-gray-1000)}
.btn-primary:hover{background:var(--ds-gray-900)}
.btn-danger{color:var(--red)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;padding:8px 16px;font-size:12px;font-weight:500;color:var(--fg2);border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 16px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
/* 首末列补足到 24px：表格内容与 .card-body 的左内边距对齐，否则左边比卡片标题缩进少一截 */
table th:first-child,table td:first-child{padding-left:24px}
table th:last-child,table td:last-child{padding-right:24px}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--soft)}
/* 操作列按内容收窄：按钮个数与文字宽度都由内容决定，写死宽度必然溢出 */
.col-act{width:1%;white-space:nowrap}
/* 只放圆点的列（额度记录「操作」、EVkey「状态」）：整列居中，表头同样带上这个类 */
.col-dot{width:1%;white-space:nowrap;text-align:center}
.mono{font-family:var(--mono);font-size:12px;word-break:break-all}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.badge{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:400;line-height:16px;white-space:nowrap;flex-shrink:0;color:var(--fg2)}
.badge::before{content:'';width:8px;height:8px;border-radius:50%;background:var(--fg3);flex-shrink:0}
.badge-on::before{background:var(--blue)}
.badge-off::before{background:var(--fg3)}
.badge-warn::before{background:var(--orange)}
.badge-error::before{background:var(--red)}
.badge-custom::before{background:var(--violet)}
/* 状态圆点：8px 圆点 + 中性灰文字，颜色语义只由圆点表达 */
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;flex-shrink:0;vertical-align:middle;background:var(--fg3)}
.dot-on{background:var(--blue)}
.dot-off{background:var(--fg3)}
.dot-warn{background:var(--orange)}
.dot-error{background:var(--red)}
.dot-violet{background:var(--violet)}
/* 状态圆点图例：表格状态列只有圆点、不带文字，含义统一挪到卡片头说明。
   不同类别的图例各占一行，所以外层用纵向 flex */
.dot-legend{display:flex;flex-direction:column;gap:4px;margin-top:8px;font-size:12px;color:var(--fg2)}
.dot-legend .lg-row{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px}
.dot-legend .lg-row>em{font-style:normal;color:var(--fg3)}
.dot-legend .lg-item{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.dot-legend .dot{cursor:default}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.empty{text-align:center;padding:40px 0;color:var(--fg3);font-size:14px}
.strong{font-weight:600}
.btn-sm{height:26px;padding:0 8px;font-size:12px}
.dim{color:var(--fg2)}
.small{font-size:12px}
/* 页头（大标题 + 说明 + ACCOUNT 英文小标）已整块移除：这一页只有一张「我的」面板，
   标题层级由顶栏与卡片自身承担，不再重复一遍 */
/* .grid / .stat / .chips / .chip / .sub / .apply-row 全部由 ACCOUNT_CSS 提供（它在上面
   已注入，管理端 #page-account 引用的是同一份），这里不再重复定义——两份定义一旦分头
   改动，同名组件在两端就会走样 */
/* 站内信：浅底条目，正文保留换行。管理端概览页与用户控制台渲染的是同一种条目，
   底色/圆角/正文字号必须同源，否则同一条消息在两个界面里长得不一样 */
.ann-list{display:flex;flex-direction:column;gap:16px}
.ann-item{padding:16px;border-radius:var(--r-sm);background:var(--soft);box-shadow:var(--ring)}
.ann-item .h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ann-item .h b{font-size:14px;font-weight:600}
.ann-item .h .sp{flex:1}
.ann-item .body{font-size:14px;color:var(--fg2);margin-top:8px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.ann-item .meta{font-size:12px;color:var(--fg3);white-space:nowrap}
/* meta 的两种落位：概览页把它放在正文下方独立一行，控制台把它塞进标题行右侧。
   用子选择器区分，避免同一个 .meta 在两种结构里互相带上对方的边距 */
.ann-item>.meta{margin-top:8px;display:flex;gap:16px;flex-wrap:wrap}
.ann-item .h .meta{margin-left:auto}
@media (max-width:640px){
  main{padding:16px 16px 40px}
  nav{padding:0 16px}
  .card-header{padding:16px}
  .card-body{padding:16px}
  th,td{padding-left:8px;padding-right:8px}
}
</style>
{{THEME_INIT}}
</head>
<body>
<nav>
  <span class="logo">{{LOGO}}eInkViews</span>
  <span class="user"><button class="icon-btn" type="button" data-act="theme-toggle" title="{{T:theme.to_dark}}" aria-label="{{T:theme.to_dark}}"></button><span id="nav-user-name"></span><button class="icon-btn" type="button" data-act="logout" title="{{T:nav.logout}}" aria-label="{{T:nav.logout}}"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 2.5h-3v11h3"/><path d="M10 5.5L12.5 8 10 10.5M12.6 8H6.5"/></svg></button></span>
</nav>
<main>
<!-- 这一页只有一张「我的」面板：账号名/用户组/UID 由第一张「账号信息」卡片承载，
     页头的大标题与说明已删除，不再重复 -->
<div class="card" id="ann-card" style="display:none">
  <div class="card-header">
    <div class="card-title"><h2>{{T:announce.title}}</h2></div>
  </div>
  <div class="card-body">
    <div class="ann-list" id="ann-list"></div>
    <div class="flex" id="ann-bar" style="justify-content:flex-end;margin-top:16px;display:none"></div>
  </div>
</div>

{{ACCOUNT_CARDS}}
</main>
<script type="application/json" id="i18n-data">{{I18N}}</script>
<script>{{SHARED_UI_JS}}</script>
<script>
var TZ_OFFSET={{TZ_OFFSET}};
/* fmtDT / doLogout 都是两份外壳共用的通用件，只有一份，在共享层里 */
/* 站内信：5 条一页，超出才显示翻页条；无内容时整张卡片隐藏，不占版面。
   这是用户控制台比管理端「我的」分页多的唯一一张卡片 */
var _annItems=[],_annPage=1,_ANN_PER=5;
function annRender(){
  var box=document.getElementById('ann-list'),bar=document.getElementById('ann-bar');
  var tp=Math.max(1,Math.ceil(_annItems.length/_ANN_PER));
  if(_annPage>tp)_annPage=tp;
  box.innerHTML=_annItems.slice((_annPage-1)*_ANN_PER,_annPage*_ANN_PER).map(function(a){
    return '<div class="ann-item"><div class="h"><b>'+esc(a.title)+'</b><span class="meta">'+esc(fmtDT(a.created_at))+'</span></div>'+
      (a.content?'<div class="body">'+esc(a.content)+'</div>':'')+'</div>';
  }).join('');
  if(_annItems.length>_ANN_PER){
    bar.style.display='flex';
    bar.innerHTML='<button class="btn btn-sm" data-act="ann-prev"'+(_annPage<=1?' disabled':'')+'>'+T('pager.prev','上一页')+'</button>'+
      '<span class="dim small">'+T('account.page_of','{cur} / {total} 页',{cur:_annPage,total:tp})+'</span>'+
      '<button class="btn btn-sm" data-act="ann-next"'+(_annPage>=tp?' disabled':'')+'>'+T('pager.next','下一页')+'</button>';
  }else bar.style.display='none';
}
function loadAnnouncements(){
  R.get('/admin/api/my/announcements').then(function(d){
    if(!d||d.success===false)return;
    _annItems=d.items||[];
    if(!_annItems.length)return;
    document.getElementById('ann-card').style.display='';
    annRender();
  }).catch(function(){});
}
/* 本页只接管「退出登录」与站内信翻页：其余 data-act（Key / 改密 / 记录翻页）
   由 account_page.ACCOUNT_JS 的委托处理，两边不重复绑定 */
document.addEventListener('click',function(e){
  var el=e.target.closest('[data-act]');
  if(!el)return;
  if(el.dataset.act==='logout')doLogout();
  else if(el.dataset.act==='ann-prev'){if(_annPage>1){_annPage--;annRender()}}
  else if(el.dataset.act==='ann-next'){
    var tp=Math.max(1,Math.ceil(_annItems.length/_ANN_PER));
    if(_annPage<tp){_annPage++;annRender()}
  }
});
loadAnnouncements();
</script>
<script>{{ACCOUNT_JS}}</script>
</body>
</html>'''

