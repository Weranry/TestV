from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from modules.admin_ui.assemble import ADMIN_HTML
from modules.admin_ui.other_pages import CHPASS_HTML
from modules.admin_ui.panel_render import panel_html as _panel_html, req_lang as _req_lang
from modules.auth.auth import decode_session_token

router = APIRouter()

# ---- 旧地址兼容 ----
# 登录 / 注册 / 找回密码已迁到站点根下（见 modules/register/auth_pages_routes.py）。
# 这里为旧地址留一条 302：书签、旧文档、别人部署里写死的 `/admin/login` 都不会变成死链。
# 只做跳转、不再渲染页面，避免同一份页面有两个入口、两处判定各改一遍。


@router.get('/login')
async def legacy_login_page():
    return RedirectResponse(url='/login', status_code=302)


@router.get('/register')
async def legacy_register_page():
    return RedirectResponse(url='/register', status_code=302)


@router.get('/reset-password')
async def legacy_reset_password_page():
    return RedirectResponse(url='/reset-password', status_code=302)


# ---- Pages ----

@router.get('/', response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    session_token = request.cookies.get('ink_session')
    valid_session = False
    if session_token:
        uid = decode_session_token(session_token)
        if uid is not None:
            valid_session = True

    user = getattr(request.state, 'user', None)
    if user and user.get('must_change_password'):
        return _panel_html(CHPASS_HTML, _req_lang(request))

    if not valid_session:
        try:
            from modules.database.accounts import has_accounts
            if has_accounts():
                return RedirectResponse(url='/login', status_code=302)
        except Exception:
            pass

    from modules.database.groups import allowed_admin_tabs, get_group, is_admin_user
    is_admin = is_admin_user(user)
    from config import (ADMIN_STATUS_REFRESH, ADMIN_PLUGINS_REFRESH, ADMIN_STATS_REFRESH, ADMIN_LOGS_REFRESH, ADMIN_APPS_REFRESH)
    from modules.admin_ui.other_pages import USER_HTML
    if is_admin:
        html = ADMIN_HTML
        # 管理组只能在勾选过的分页里操作：把清单注入页面，前端据此隐藏标签页、
        # 跳过无权分页的初始化请求（后端 app_core._check_admin_api_access 另有同样的判定）
        import json
        group = get_group(user.get('group_id'))
        html = html.replace(
            '{{ALLOWED_TABS}}', json.dumps(sorted(allowed_admin_tabs(group))))
        # 概览页的站内信卡片可由管理组单独关闭（与后端 announce_routes._announcement_hidden 同口径：
        # 内置兜底管理组恒为显示）。前端隐藏只防误触，接口侧另有 403
        show_announcement = 1
        if group and not group.get('builtin') and not group.get('show_announcement', 1):
            show_announcement = 0
        html = html.replace('{{SHOW_ANNOUNCEMENT}}', str(show_announcement))
    else:
        html = USER_HTML
    for t in [('ADMIN_STATUS_REFRESH', ADMIN_STATUS_REFRESH),
              ('ADMIN_PLUGINS_REFRESH', ADMIN_PLUGINS_REFRESH), ('ADMIN_STATS_REFRESH', ADMIN_STATS_REFRESH),
              ('ADMIN_LOGS_REFRESH', ADMIN_LOGS_REFRESH), ('ADMIN_APPS_REFRESH', ADMIN_APPS_REFRESH)]:
        html = html.replace('{{'+t[0]+'}}', str(t[1]))
    # 时间为 UTC 存储，前端按配置时区换算展示；无配置时返回 null，交给浏览器本地时区
    from modules.utils.timezone import get_timezone_offset
    try:
        tz_offset = get_timezone_offset()
    except Exception:
        tz_offset = None
    html = html.replace('{{TZ_OFFSET}}', 'null' if tz_offset is None else repr(float(tz_offset)))
    return _panel_html(html, _req_lang(request))