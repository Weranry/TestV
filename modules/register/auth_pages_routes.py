"""登录 / 注册 / 找回密码三个页面的路由（挂在站点根下，不带 /admin 前缀）。

这三个页面原先落在 `/admin` 前缀内（`/admin/login` 等），但它们本就不是「后台的一部分」：
注册与找回密码是给**未登录用户**用的，把入口藏进后台路径既不符合直觉，也让登录页地址
多出一段无意义的层级。迁到 `/login` / `/register` / `/reset-password` 之后：

- `/admin` 只表示「后台面板」本身，与用户的登录入口分开；
- 接口路径（`POST /admin/api/auth/login` 等）保持不动，前端仍调原来的接口；
- 旧地址在 `modules/admin/page_routes.py` 里做了 302 兼容，书签与旧文档不会变成死链。

注册开关（`EVKEY_REGISTRATION_ENABLED=False`）的两处表现与迁移前逐字一致：登录页剔除
「注册」链接，直接访问注册页则跳回登录页。
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from modules.admin.common import _REGISTER_LINK_RE
from modules.admin_ui.other_pages import LOGIN_HTML, REGISTER_HTML, RESET_HTML
from modules.admin_ui.panel_render import panel_html, req_lang

router = APIRouter(tags=['auth-pages'])


@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    import config
    html = LOGIN_HTML
    if not getattr(config, 'EVKEY_REGISTRATION_ENABLED', True):
        html = _REGISTER_LINK_RE.sub('', html)
    return panel_html(html, req_lang(request))


@router.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    import config
    if not getattr(config, 'EVKEY_REGISTRATION_ENABLED', True):
        return RedirectResponse(url='/login', status_code=302)
    return panel_html(REGISTER_HTML, req_lang(request))


# 忘记密码：与注册开关无关——注册关了，已有账号照样要能找回自己的密码
@router.get('/reset-password', response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return panel_html(RESET_HTML, req_lang(request))