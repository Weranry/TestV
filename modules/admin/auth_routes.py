import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body, _client_ip
from modules.i18n.registry import t_req
from modules.auth.auth import (
    create_session_token, set_session_cookie, clear_session_cookie,
    is_https_request,
)
from modules.errors.errors import error_response

router = APIRouter()

# 自助激活核销失败的原因文案。必须逐条分开：把「你用过了」笼统说成「无效」，
# 用户只会以为码坏了去反复试；更不能再返回成功。
_CODE_ERRORS = {
    'used': 'account.code_used',
    'exhausted': 'account.code_exhausted',
    'expired': 'account.code_expired',
    'disabled': 'account.code_disabled',
    'invalid': 'account.code_invalid',
}

# ---- Auth ----

@router.post('/api/auth/login')
async def auth_login(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    username = body.get('username', '').strip()
    password = body.get('password', '')
    if not username: return error_response(t_req(request, 'login.need_username'), 400)
    if not password: return error_response(t_req(request, 'login.need_password'), 400)

    # 防撞库：账号与来源 IP 两个维度分别计数，校验密码前先看是否还在锁定期。
    # 账号名统一小写后再入键：名字本身不区分大小写，`Admin` 与 `admin` 是同一个账号，
    # 不折叠的话换一下大小写就能把锁定计数清零。
    from modules.utils import login_guard
    guard_keys = [f'user:{username.lower()}', f'ip:{_client_ip(request)}']
    locked = await login_guard.check(guard_keys)
    if locked:
        return error_response(
            t_req(request, 'login.locked', locked=locked), 429, headers={'Retry-After': str(locked)}
        )

    from modules.database.accounts import verify_account_login
    # 密码校验是同步 pbkdf2（10 万轮，本机约 35ms）：直接在协程里跑会把所有并发请求
    # 一起卡住，必须下放 worker 线程（与 auth.py 查库同一条理由）
    acct = await asyncio.to_thread(verify_account_login, username, password)
    if not acct:
        await login_guard.record_failure(guard_keys)
        return error_response(t_req(request, 'login.bad_credentials'), 401)
    await login_guard.record_success(guard_keys)
    token = create_session_token(acct['id'])
    from modules.database.groups import is_admin_user
    is_admin = is_admin_user(acct)
    resp = JSONResponse({'success': True, 'is_admin': is_admin, 'account_name': acct['name'], 'group_name': acct['group_name'], 'must_change_password': bool(acct.get('must_change_password', 0))})
    set_session_cookie(resp, token, secure=is_https_request(request))
    return resp

@router.post('/api/auth/register')
async def auth_register(request: Request):
    import config
    if not getattr(config, 'EVKEY_REGISTRATION_ENABLED', True):
        return error_response(t_req(request, 'register.disabled'), 403)
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    username = body.get('username', '').strip()
    password = body.get('password', '')
    email = (body.get('email') or '').strip()
    note = body.get('note', '').strip()
    code = (body.get('code') or '').strip()
    if not username: return error_response(t_req(request, 'login.need_username'), 400)
    if not email or '@' not in email: return error_response(t_req(request, 'user.need_valid_email'), 400)
    if not password or len(password) < 6: return error_response(t_req(request, 'auth.pw_short'), 400)
    from modules.database.accounts import create_account, get_account_by_name, is_numeric_identifier
    from modules.database.groups import ensure_register_group, group_is_admin_category
    # 纯数字用户名会把「按 uid 登录」的入口堵死，注册时直接拒绝
    if is_numeric_identifier(username):
        return error_response(t_req(request, 'register.name_numeric'), 400)
    if get_account_by_name(username):
        return error_response(t_req(request, 'register.name_taken'), 409)

    from modules.database.activations import redeem, refund, expiry_after, purge_if_exhausted
    expires_on, fallback_group_id, code_id = '', 0, 0
    if code:
        # 有激活码：落组、账号有效期、到期回落组全部以该码为准
        row = redeem(code)
        if row is None:
            return error_response(t_req(request, 'register.bad_code'), 400)
        if group_is_admin_category(int(row['group_id'])):
            # 用管理组的码注册等于当场拿到全部管理权限，与自助激活同一条硬约束
            refund(code)
            return error_response(t_req(request, 'register.code_admin_forbidden'), 400)
        code_id = int(row['id'])
        group_id = row['group_id']
        days = int(row.get('duration_days') or 0)
        if days > 0:
            expires_on = expiry_after(days)
        fallback_group_id = int(row.get('fallback_group_id') or 0)
    else:
        # 落组必须现取现建：用户组可被删除，写死 id/组名缺失时会让注册撞 FOREIGN KEY constraint failed
        group_id = ensure_register_group()
    if not group_id:
        return error_response(t_req(request, 'register.group_create_failed'), 400)
    try:
        # 建号要算一次 pbkdf2，同样下放线程，别让注册把事件循环占住
        aid = await asyncio.to_thread(
            create_account, username, password, group_id, note, expires_on,
            fallback_group_id, email)
    except Exception as e:
        # 建号失败要把激活码名额还回去，否则用户白扣一次
        if code:
            refund(code)
        return error_response(str(e), 400)
    if code_id:
        # 用完即销毁：有限次的码在最后一次核销后立即从面板消失，不留历史
        purge_if_exhausted(code_id)
        # 权限记录：新账号的会员属性完全来自这张码（old 为空快照）
        from modules.database.membership import get_membership, log_change
        log_change(aid, 'activate', None, get_membership(aid), '注册时使用激活码开通', '')
    return JSONResponse({'success': True, 'id': aid, 'message': t_req(request, 'register.done')})

@router.post('/api/auth/reset-password')
async def auth_reset_password(request: Request):
    """忘记密码：账号名 + 注册邮箱都对上，就允许当场设新密码。

    项目没有任何邮件服务，所以不做「发验证码/发链接」那一套；注册邮箱在这里就是
    「你是这个账号主人」的凭据（注册必填、列表不展示、只在账号详情里可见）。
    邮箱并不保证全局唯一，因此必须与账号名一起校验——只比邮箱等于谁都能改别人密码。

    失败同样计入防撞库（独立的 reset 维度），否则邮箱可以拿来慢慢试。
    """
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    username = body.get('username', '').strip()
    email = (body.get('email') or '').strip()
    new_password = body.get('password', '')
    if not username: return error_response(t_req(request, 'login.need_username'), 400)
    if not email: return error_response(t_req(request, 'reset.need_registered_email'), 400)
    if not new_password or len(new_password) < 6:
        return error_response(t_req(request, 'auth.pw_short'), 400)

    from modules.utils import login_guard
    guard_keys = [f'reset:{username.lower()}', f'ip:{_client_ip(request)}']
    locked = await login_guard.check(guard_keys)
    if locked:
        return error_response(
            t_req(request, 'login.locked', locked=locked), 429, headers={'Retry-After': str(locked)}
        )

    from modules.database.accounts import get_account_for_reset, set_account_password
    # 匹配与改密都是同步查库 + pbkdf2，照 login 的做法下放线程
    acct = await asyncio.to_thread(get_account_for_reset, username, email)
    if not acct:
        await login_guard.record_failure(guard_keys)
        return error_response(t_req(request, 'reset.bad_credentials'), 400)
    await login_guard.record_success(guard_keys)
    await asyncio.to_thread(set_account_password, acct['id'], new_password)
    # 顺手解掉登录维度的锁定：能走到这里已经证明是本人在重置，不该再被旧的失败计数挡在门外
    await login_guard.record_success([f'user:{username.lower()}'])
    from modules.auth.auth import invalidate_auth_cache
    invalidate_auth_cache()
    return JSONResponse({'success': True, 'message': t_req(request, 'reset.done')})

@router.post('/api/auth/logout')
async def auth_logout():
    resp = JSONResponse({'success': True})
    clear_session_cookie(resp)
    return resp

@router.post('/api/auth/change-password')
async def auth_change_password(request: Request):
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    new_password = body.get('password', '')
    if not new_password or len(new_password) < 6:
        return error_response(t_req(request, 'auth.pw_short'), 400)
    from modules.database.accounts import set_account_password, is_setup_required
    from modules.auth.auth import invalidate_auth_cache
    # 与新密码的 pbkdf2 同理：下放线程，避免改密请求卡住其它并发请求
    await asyncio.to_thread(set_account_password, user['id'], new_password)
    # 初始化门禁：内置管理账号改掉公开初始口令后当场解除，无需重启（见 app_core 的 setup 门禁）。
    # 重新判定而不是直接置 False——改密的可能是普通用户，此时门禁应当照旧。
    try:
        request.app.state.setup_required = await asyncio.to_thread(is_setup_required)
    except Exception:
        pass
    # 改密后立即失效缓存，否则旧缓存里的账号信息会继续沿用到期
    invalidate_auth_cache()
    return JSONResponse({'success': True, 'message': t_req(request, 'account.pw_updated')})

@router.get('/api/auth/me')
async def admin_me(request: Request):
    user = getattr(request.state, 'user', None)
    if user is None: return JSONResponse({'authenticated': False})

    from modules.database.groups import is_admin_user
    group = {}
    plugins = []
    routes = []
    # 会员信息（激活码开通）：到期日 + 到期后转入的用户组名，个人控制台要展示
    membership = {
        'expires_on': user.get('expires_on') or '',
        'fallback_group_id': int(user.get('fallback_group_id') or 0),
        'fallback_group_name': '',
    }
    try:
        from modules.database.groups import get_group, get_group_permissions, is_admin_category
        g = get_group(user['group_id'])
        if g:
            # 管理组的两项限额在服务端被折算成「不限」（evkey 走 group_max_evkeys、
            # 并发走 app_core 的信号量），这里必须报同一份口径：库里存的值对它已不生效，
            # 照原值显示会让管理员以为自己被卡住了。evkey 用 -1、并发用 0 表示不限
            admin_grp = is_admin_category(g.get('category'))
            group = {
                'name': g['name'],
                'description': g.get('description') or '',
                'max_evkeys': -1 if admin_grp else int(g.get('max_evkeys') or 0),
                'max_concurrent_renders': 0 if admin_grp else int(g.get('max_concurrent_renders') or 0),
                'rate_limit_per_minute': int(g.get('rate_limit_per_minute') or 0),
                'quota_limit': int(g.get('quota_limit') or 0),
                'quota_period': g.get('quota_period') or 'day',
            }
        perms = get_group_permissions(user['group_id'])
        # 未显式配置 = 默认允许；显式配置为 False 才是禁用
        for p in getattr(request.app.state, 'plugin_result', {}).get('plugins', []):
            name = p['name']
            plugins.append({'name': name, 'enabled': perms['plugins'].get(name, True)})
        for path in sorted(perms['routes']):
            routes.append({'path': path, 'enabled': perms['routes'][path]})
        if membership['fallback_group_id']:
            fb = get_group(membership['fallback_group_id'])
            if fb:
                membership['fallback_group_name'] = fb['name']
    except Exception:
        pass

    return JSONResponse({
        'authenticated': True,
        'is_admin': is_admin_user(user),
        'user': {
            'id': user['id'], 'uid': user.get('uid'), 'name': user.get('name', ''),
            'group_id': user['group_id'], 'group_name': user['group_name'],
            'description': user.get('description', ''),
        },
        'group': group,
        'membership': membership,
        'permissions': {'plugins': plugins, 'routes': routes},
    })

# ---- User self-service ----

@router.post('/api/my/activation')
async def my_redeem_activation(request: Request):
    """注册后自助输入激活码（相当于开通/续期会员）。

    与注册时的核销共用同一套语义与原子核销：落组、到期日、到期回落组全部以码为准。
    """
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    code = (body.get('code') or '').strip()
    if not code: return error_response(t_req(request, 'account.need_code'), 400)

    from modules.database.groups import get_group, group_is_admin_category, is_admin_user
    # 管理员账号已经是最高权限，再核销只会把自己踢出管理组
    if is_admin_user(user):
        return error_response(t_req(request, 'account.admin_no_code'), 400)

    from modules.database.activations import (
        redeem_for_account, refund, expiry_after, extend_expiry, purge_if_exhausted,
    )
    # 按账号去重且区分失败原因：同账号重复用同一张码要说「已用过」，
    # 而不是笼统的「无效」——更不能再提示一次激活成功
    row, reason = redeem_for_account(code, user['id'])
    if row is None:
        return error_response(t_req(request, _CODE_ERRORS.get(reason, 'account.code_invalid')), 400)
    group_id = int(row['group_id'])
    if group_is_admin_category(group_id):
        # 自助激活不允许进管理组：那等于把管理权限交给任何拿到码的人
        refund(code, user['id'])
        return error_response(t_req(request, 'account.code_self_forbidden'), 400)
    if not get_group(group_id):
        refund(code, user['id'])
        return error_response(t_req(request, 'account.code_group_missing'), 400)

    days = int(row.get('duration_days') or 0)
    fallback_group_id = int(row.get('fallback_group_id') or 0)
    if int(row.get('allow_repeat') or 0):
        # 允许反复激活的码：续期语义，在现有到期日上叠加，未用完的天数不丢
        expires_on = extend_expiry(user.get('expires_on'), days)
    else:
        expires_on = expiry_after(days) if days > 0 else ''
    old_group_id = user['group_id']
    from modules.database.membership import get_membership, log_change
    before_membership = get_membership(user['id'])
    try:
        from modules.database.accounts import set_account_membership
        set_account_membership(user['id'], group_id, expires_on, fallback_group_id)
    except Exception as e:
        refund(code, user['id'])
        return error_response(str(e), 400)

    # 用完即销毁：有限次的码在最后一次核销后立即从面板消失，不留历史
    purge_if_exhausted(int(row['id']))

    # 权限记录：激活 = 用户自己的权限变动，也要能在他自己的「权限记录」里看到
    log_change(user['id'], 'activate', before_membership, get_membership(user['id']),
               '激活码自助开通', user.get('name', ''))

    # 用户组变了：鉴权缓存与并发信号量都要立即失效，否则 60 秒内仍按旧组放行
    from modules.auth.auth import invalidate_auth_cache
    from modules.admin.common import _drop_group_semaphores
    invalidate_auth_cache()
    _drop_group_semaphores(request.app.state, old_group_id, group_id)

    group_name = get_group(group_id)['name']
    fb = get_group(fallback_group_id) if fallback_group_id else None
    return JSONResponse({
        'success': True,
        'message': t_req(request, 'account.redeem_group_done', group=group_name),
        'group_name': group_name,
        'expires_on': expires_on,
        'fallback_group_name': (fb['name'] if fb else ''),
    })

@router.get('/api/my/evkeys')
async def my_evkeys(request: Request):
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    from modules.database.accounts import get_evkeys_for_account, count_evkeys_for_account
    from modules.database.applications import (
        count_pending_applications, group_max_evkeys, list_applications_for_account,
    )
    evkeys = get_evkeys_for_account(user['id'])
    max_evkeys = group_max_evkeys(user['group_id'])
    current = count_evkeys_for_account(user['id'])
    pending = count_pending_applications(user['id'])
    # pending 一并返回：前端要靠 current + pending 判断还能不能再申请；
    # applications 是审批中申请的明细——只给个数字的话，用户提交完在列表里看不到任何东西，
    # 会以为申请丢了而反复提交（每次提交都占一个名额）
    return JSONResponse({'evkeys': evkeys, 'current': current, 'pending': pending, 'max': max_evkeys,
                         'applications': list_applications_for_account(user['id'])})

@router.get('/api/my/quota')
async def my_quota(request: Request):
    """个人控制台的实时额度用量（只读，不消耗额度）"""
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    try:
        from modules.utils.rate_limiter import quota_usage
        return JSONResponse(await quota_usage(request))
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/my/quota/logs')
async def my_quota_logs(request: Request):
    """我的额度变动记录（管理员发放 / 手动重置）。到期自动重置不记录，只记人为操作"""
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    try:
        from modules.database.quotas import count_logs, list_logs
        limit = min(max(int(request.query_params.get('limit', 50)), 1), 200)
        offset = max(int(request.query_params.get('offset', 0)), 0)
        return {'items': list_logs(user['id'], limit=limit, offset=offset),
                'total': count_logs(user['id'])}
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/my/membership-logs')
async def my_membership_logs(request: Request):
    """我的权限记录（只读）：用户组升降、到期日增减、到期回落，含管理员的操作与原因"""
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    try:
        from modules.database.membership import count_logs, list_logs
        limit = min(max(int(request.query_params.get('limit', 50)), 1), 200)
        offset = max(int(request.query_params.get('offset', 0)), 0)
        return {'items': list_logs(user['id'], limit=limit, offset=offset),
                'total': count_logs(user['id'])}
    except Exception as e:
        return error_response(str(e), 500)

@router.get('/api/my/announcements')
async def my_announcements(request: Request):
    """当前用户可见的站内信：全体可见 + 点名本用户组的"""
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    try:
        from modules.database.announcements import get_announcements_for_group
        return {'items': get_announcements_for_group(user.get('group_id'))}
    except Exception as e:
        return error_response(str(e), 500)

@router.post('/api/my/evkeys/apply')
async def my_apply_evkey(request: Request):
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    body = await _body(request) or {}
    from modules.database.accounts import count_evkeys_for_account, create_evkey, new_evkey
    from modules.database.applications import (
        create_evkey_application, count_pending_applications, group_max_evkeys, evkey_quota,
    )
    max_evkeys = group_max_evkeys(user['group_id'])
    current = count_evkeys_for_account(user['id'])
    pending = count_pending_applications(user['id'])
    # 上限按「已持有 + 审批中」算；-1 = 不限，0 = 该组禁止创建
    if evkey_quota(max_evkeys, current, pending) == 0:
        reason = t_req(request, 'account.evkey_no_create') if max_evkeys == 0 \
            else t_req(request, 'account.evkey_limit_detail', cur=current, pending=pending, max=max_evkeys)
        return error_response(reason, 400)

    import config as cfg
    # 管理员在自己的控制台建 Key 不需要等自己审批，直接发放
    from modules.database.groups import is_admin_user
    is_admin = is_admin_user(user)
    if is_admin or not cfg.EVKEY_APPROVAL_REQUIRED:
        new_key = new_evkey()
        create_evkey(user['id'], new_key, body.get('description', ''))
        return JSONResponse({'success': True, 'message': t_req(request, 'account.evkey_created'), 'evkey': new_key})

    create_evkey_application(user['id'], user['name'], body.get('description', ''), user['group_id'])
    return JSONResponse({'success': True, 'message': t_req(request, 'account.key_pending_msg')})

@router.put('/api/my/evkeys/{evkey_id}')
async def my_toggle_evkey(evkey_id: int, request: Request):
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    body = await _body(request)
    # 原先用 `await _body(request) or {}`：请求体解析失败会被当成空字典，
    # 再走 `body.get('enabled', True)` 缺省值 True，把用户原本禁用的 key 悄悄启用回来。
    # 与本文件的其它写接口一致：解析不出来就报 400。
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.accounts import get_evkeys_for_account, toggle_evkey
    if not any(e['id'] == evkey_id for e in get_evkeys_for_account(user['id'])):
        return error_response(t_req(request, 'msg.forbidden'), 403)
    toggle_evkey(evkey_id, body.get('enabled', True))
    return JSONResponse({'success': True})

@router.delete('/api/my/evkeys/{evkey_id}')
async def my_delete_evkey(evkey_id: int, request: Request):
    user = getattr(request.state, 'user', None)
    if not user: return error_response(t_req(request, 'msg.need_login'), 401)
    from modules.database.accounts import get_evkeys_for_account, delete_evkey
    mine = get_evkeys_for_account(user['id'])
    if not any(e['id'] == evkey_id for e in mine):
        return error_response(t_req(request, 'msg.forbidden'), 403)
    delete_evkey(evkey_id)
    return JSONResponse({'success': True})