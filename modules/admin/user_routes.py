import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body, _drop_account_semaphores, _drop_group_semaphores, _int_field
from modules.errors.errors import error_response
from modules.i18n.registry import t_req

router = APIRouter()


def _evkey_limit_msg(request, max_evkeys, held):
    """evkey 上限的拒绝文案。上限 0 = 该组禁止创建；负数 = 不限，不会走到这里"""
    if max_evkeys == 0:
        return t_req(request, 'user.evkey_forbidden')
    return t_req(request, 'user.evkey_limit_reached', max=max_evkeys, held=held)


def _actor_name(request):
    """当前登录管理员的名字，用于额度 / 权限变动记录的「操作人」列"""
    me = getattr(request.state, 'user', None)
    return (me.get('name') or '') if isinstance(me, dict) else ''


def _builtin_admin_guard(group_id, message):
    """内置兜底管理组的写入口守卫，命中返回错误响应、否则返回 None。

    它拥有全部权限（access.preload_access_cache 会跳过它的规则），改它的名字或限额、
    给它配插件 / 路由 / 参数限制，都会把自己锁在后台外面，而且没有任何界面能改回来。
    注意判定必须 builtin + category 一起看：内置普通用户组（Free）仍然可以编辑。
    """
    from modules.database.groups import get_group, is_admin_category
    group = get_group(group_id)
    if group and group.get('builtin') and is_admin_category(group.get('category')):
        return error_response(message, 400)
    return None


# 会员属性的三个字段：任一变化才算一次「权限变动」
_MEMBERSHIP_KEYS = ('group_id', 'expires_on', 'fallback_group_id')


def _log_membership_if_changed(account_id, old, new, action, reason='', admin_name=''):
    """会员属性真的变了才记一条：无变化也写只是噪音，会把记录刷满"""
    from modules.database.membership import log_change
    if not old or not new:
        return
    if all(str(old.get(k)) == str(new.get(k)) for k in _MEMBERSHIP_KEYS):
        return
    log_change(account_id, action, old, new, reason, admin_name)

# ---- Account CRUD ----

@router.get('/api/accounts')
async def admin_accounts():
    try:
        from modules.database.accounts import get_all_accounts, default_admin_account_id
        def _load_accounts():
            accounts = get_all_accounts()
            # 内置管理账号由前端置灰删除按钮，这里一并标出来，省得两边各判一套
            default_id = default_admin_account_id()
            for a in accounts:
                a['is_default_admin'] = a['id'] == default_id
            return accounts
        accounts = await asyncio.to_thread(_load_accounts)
    except: accounts = []
    return JSONResponse({'accounts': accounts})

@router.post('/api/accounts')
async def admin_create_account(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    name = body.get('name', '').strip()
    group_id = body.get('group_id')
    password = body.get('password', '')
    email = (body.get('email') or '').strip()
    if not name or not group_id: return error_response(t_req(request, 'user.need_name_or_group'), 400)
    if not password or len(password) < 6: return error_response(t_req(request, 'auth.pw_short'), 400)
    # 与注册同一约束：邮箱是「忘记密码」的唯一凭据，建号时就必须有
    if not email or '@' not in email: return error_response(t_req(request, 'user.need_valid_email'), 400)
    try:
        from modules.database.accounts import create_account, get_account_by_name, is_numeric_identifier
        # 与注册同一约束：账号名不能是纯数字，否则「按 uid 登录」没法与账号名消歧
        if is_numeric_identifier(name):
            return error_response(t_req(request, 'user.name_numeric'), 400)
        if await asyncio.to_thread(get_account_by_name, name):
            return error_response(t_req(request, 'user.name_taken'), 409)
        # 建号要算一次 pbkdf2，下放线程，别让管理端的建号把事件循环占住
        aid = await asyncio.to_thread(
            create_account, name, password, int(group_id),
            body.get('description', ''), '', 0, email)
        from modules.auth.auth import invalidate_auth_cache
        invalidate_auth_cache()
        return JSONResponse({'id': aid, 'name': name, 'group_id': group_id})
    except Exception as e:
        return error_response(str(e), 400)

@router.put('/api/accounts/{account_id}')
async def admin_update_account(account_id: int, request: Request):
    """编辑账号：名称 / 用户组 / 备注 / 启用状态 + 会员属性（到期日、到期回落组）。

    会员属性（组、到期日、回落组）有变动时写一条 account_membership_logs，
    面板的「权限记录」里能看到前后值与操作人；reason 由调用方选填。
    """
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.accounts import (
        default_admin_account_id, update_account, get_account_row, is_numeric_identifier)
    from modules.database.membership import get_membership, log_change
    # 内置管理账号是后台的兜底入口（唯一那个必然能进后台的账号），改它的组、启用状态
    # 或密码都等于把这个入口改掉
    if account_id == await asyncio.to_thread(default_admin_account_id):
        return error_response(t_req(request, 'user.builtin_acct_no_edit'), 400)
    # 用 get_account_row 而不是 get_account_by_id：后者会过滤 enabled=1，
    # 编辑一个被禁用的账号时取不到原组，信号量就丢不掉
    before = await asyncio.to_thread(get_account_row, account_id)
    if before is None:
        return error_response(t_req(request, 'user.account_not_found'), 404)
    payload = dict(body)
    if 'name' in payload:
        new_name = str(payload.get('name') or '').strip()
        if not new_name:
            return error_response(t_req(request, 'user.name_empty'), 400)
        # 与注册/建号同一约束：改成纯数字会让该账号只能靠 uid 登录，且名字与编号撞车
        if is_numeric_identifier(new_name):
            return error_response(t_req(request, 'user.name_numeric'), 400)
        payload['name'] = new_name
    # 邮箱只在传了才处理：老账号没有邮箱，编辑其它字段时不该被必填卡住
    if 'email' in payload:
        email = str(payload.get('email') or '').strip()
        if email and '@' not in email:
            return error_response(t_req(request, 'user.need_valid_email'), 400)
        payload['email'] = email
    # 到期日 / 回落组只在传了才处理：账号编辑弹窗不改会员属性，
    # 用 body.get(..., 原值) 会把缺失字段误判成「改成空」
    if 'expires_on' in payload:
        import datetime
        expires_on = (payload.get('expires_on') or '').strip()
        if expires_on:
            try:
                datetime.date.fromisoformat(expires_on)
            except ValueError:
                return error_response(t_req(request, 'user.bad_expires_format'), 400)
        payload['expires_on'] = expires_on
    if 'fallback_group_id' in payload:
        from modules.database.groups import get_group, is_admin_category
        fallback = _int_field(payload, 'fallback_group_id', 0)
        if fallback:
            fb = await asyncio.to_thread(get_group, fallback)
            if fb is None:
                return error_response(t_req(request, 'user.fallback_not_found'), 404)
            if is_admin_category(fb.get('category')):
                # 回落组是管理组时，会员一到期就自动升成管理员，必须堵死
                return error_response(t_req(request, 'user.fallback_admin_forbidden'), 400)
        payload['fallback_group_id'] = fallback
    old_membership = await asyncio.to_thread(get_membership, account_id)
    try:
        # 直接透传 body：组 id 不存在或账号名重复会在库里撞约束，必须兜成可读的 400，
        # 否则异常穿透中间件变成 500，面板拿不到任何有用信息
        await asyncio.to_thread(update_account, account_id, **payload)
    except Exception as e:
        return error_response(t_req(request, 'user.save_failed_reason', msg=str(e)), 400)
    from modules.auth.auth import invalidate_auth_cache
    invalidate_auth_cache()
    def _log_membership():
        new_membership = get_membership(account_id)
        _log_membership_if_changed(
            account_id, old_membership, new_membership, 'set',
            body.get('reason', ''), _actor_name(request))
    await asyncio.to_thread(_log_membership)
    # 并发上限按用户组配置、按账号缓存：换组后不丢弃旧信号量，该账号会一直沿用
    # 原用户组的上限，要重启进程才生效（与批量转移、自助激活同一处理）
    old_gid = before.get('group_id') if before else None
    new_gid = body.get('group_id', old_gid)
    if old_gid is not None and new_gid is not None and int(old_gid) != int(new_gid):
        _drop_group_semaphores(request.app.state, old_gid, new_gid)
    return JSONResponse({'success': True})

@router.delete('/api/accounts/{account_id}')
async def admin_delete_account(account_id: int, request: Request):
    from modules.database.accounts import delete_account, default_admin_account_id
    # 建库时生成的兜底管理账号不能删：删掉它，管理入口就没有可用的兜底账号了
    if account_id == await asyncio.to_thread(default_admin_account_id):
        return error_response(t_req(request, 'user.builtin_acct_no_delete'), 400)
    await asyncio.to_thread(delete_account, account_id)
    from modules.auth.auth import invalidate_auth_cache
    invalidate_auth_cache()
    # 并发信号量按账号缓存，账号没了就该回收，否则字典只增不减
    _drop_account_semaphores(request.app.state, account_id)
    return JSONResponse({'success': True})

@router.post('/api/accounts/batch')
async def admin_batch_accounts(request: Request):
    """账号批量操作：转移用户组 / 启用 / 禁用 / 删除。

    admin 组（id=1）下的账号一律不参与——误操作会把管理入口整个锁死；
    当前登录账号自身也不允许被禁用或删除。
    """
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    action = body.get('action') or ''
    ids = body.get('ids')
    if not isinstance(ids, list):
        return error_response(t_req(request, 'user.ids_not_list'), 400)
    try:
        ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        return error_response(t_req(request, 'user.ids_invalid'), 400)
    if not ids:
        return error_response(t_req(request, 'user.need_pick_account'), 400)
    if action not in ('transfer', 'enable', 'disable', 'delete'):
        return error_response(t_req(request, 'user.unknown_action'), 400)

    from modules.database.accounts import (
        get_all_accounts, update_accounts_group, set_accounts_enabled, delete_accounts,
    )
    rows = {a['id']: a for a in await asyncio.to_thread(get_all_accounts)}
    targets = [i for i in ids if i in rows]
    if not targets:
        return error_response(t_req(request, 'user.selected_not_found'), 404)
    # 管理组（category='admin'）下的账号一律不参与：误操作会把管理入口整个锁死
    if any(rows[i].get('group_category') == 'admin' for i in targets):
        return error_response(t_req(request, 'user.admin_group_acct_forbidden'), 400)
    me = getattr(request.state, 'user', None)
    me_id = me.get('id') if isinstance(me, dict) else None
    if action in ('disable', 'delete') and me_id in targets:
        return error_response(t_req(request, 'user.self_acct_forbidden'), 400)

    if action == 'transfer':
        from modules.database.groups import get_group, group_is_admin_category
        try:
            target_gid = int(body.get('group_id'))
        except (TypeError, ValueError):
            return error_response(t_req(request, 'user.need_target_group'), 400)
        if await asyncio.to_thread(get_group, target_gid) is None:
            return error_response(t_req(request, 'user.target_group_not_found'), 404)
        if await asyncio.to_thread(group_is_admin_category, target_gid):
            # 批量转入管理组等于批量授予管理权限，只能逐个在账号编辑里明确调整
            return error_response(t_req(request, 'user.batch_transfer_admin_forbidden'), 400)
        old_groups = {rows[i]['group_id'] for i in targets}
        from modules.database.membership import get_membership
        def _apply_transfer():
            before_membership = {i: get_membership(i) for i in targets}
            update_accounts_group(targets, target_gid)
            # 批量改组也是权限变动，逐个记一条：否则被批量转移的账号在「权限记录」里一片空白
            for i in targets:
                _log_membership_if_changed(i, before_membership.get(i), get_membership(i),
                                           'set', body.get('reason', ''), _actor_name(request))
        await asyncio.to_thread(_apply_transfer)
        _drop_group_semaphores(request.app.state, *old_groups, target_gid)
    elif action == 'enable':
        await asyncio.to_thread(set_accounts_enabled, targets, True)
    elif action == 'disable':
        await asyncio.to_thread(set_accounts_enabled, targets, False)
    else:
        await asyncio.to_thread(delete_accounts, targets)
        _drop_account_semaphores(request.app.state, *targets)

    from modules.auth.auth import invalidate_auth_cache
    invalidate_auth_cache()
    return JSONResponse({'success': True, 'affected': len(targets)})

@router.get('/api/accounts/{account_id}/usage')
async def admin_account_usage(account_id: int, request: Request):
    """账号用量：按天 / 按插件取 account_stats 长期累计"""
    try:
        days = max(1, min(int(request.query_params.get('days', 30)), 365))
        from modules.database.stats import get_account_usage_daily, get_account_usage_by_plugin
        daily, by_plugin = await asyncio.to_thread(
            lambda: (get_account_usage_daily(account_id, days),
                     get_account_usage_by_plugin(account_id, days)))
        return {
            'account_id': account_id,
            'days': days,
            'daily': daily,
            'by_plugin': by_plugin,
        }
    except Exception as e:
        return error_response(str(e), 500)


@router.get('/api/accounts/{account_id}/devices')
async def admin_account_devices(account_id: int, request: Request):
    """账号的设备目录：自有的 ∪ 别人共享给它的（与用户端「我的设备」同一份口径）。

    **只读目录**：管理端不代账号改设备，编辑仍走用户自己的账号面接口。
    每行带 `owner`，前端「归属」列据此标「自有 / 由 XX 共享」。
    """
    from modules.database.accounts import get_account_row
    from modules.device import store
    acct = await asyncio.to_thread(get_account_row, account_id)
    if not acct:
        return error_response(t_req(request, 'user.account_not_found'), 404)
    rows = await asyncio.to_thread(store.list_devices_owned_and_shared, account_id)
    items = []
    for row in rows:
        tasks = await asyncio.to_thread(store.list_device_tasks, row['id'])
        items.append({
            'id': row['id'],
            'name': row.get('name') or '',
            'model': row.get('model') or '',
            'width': int(row.get('width') or 0),
            'height': int(row.get('height') or 0),
            'owner': bool(row.get('owner')),
            'shared_by_name': row.get('shared_by_name') or '',
            'paired': bool(row.get('token_hash')),
            'enabled': bool(row.get('enabled')),
            'last_seen_at': row.get('last_seen_at'),
            'task_count': len(tasks),
        })
    return JSONResponse({
        'devices': items,
        'owned': len([i for i in items if i['owner']]),
        'shared_in': len([i for i in items if not i['owner']]),
    })


# ---- Evkey management per account ----

@router.get('/api/accounts/{account_id}/evkeys')
async def admin_account_evkeys(account_id: int):
    from modules.database.accounts import get_evkeys_for_account
    evkeys = await asyncio.to_thread(get_evkeys_for_account, account_id)
    return JSONResponse({'evkeys': evkeys})

@router.post('/api/accounts/{account_id}/evkeys')
async def admin_create_evkey(account_id: int, request: Request):
    body = await _body(request) or {}
    from modules.database.accounts import get_account_by_id, count_evkeys_for_account, create_evkey, new_evkey
    from modules.database.applications import evkey_quota, group_max_evkeys
    acct, current = await asyncio.to_thread(
        lambda: (get_account_by_id(account_id), count_evkeys_for_account(account_id)))
    if not acct: return error_response(t_req(request, 'user.account_not_found'), 404)
    # 上限一律从用户组取：管理组会被折算成 -1（不限），不能拿账号行里 join 出来的原始值
    max_evkeys = await asyncio.to_thread(group_max_evkeys, acct['group_id'])
    if evkey_quota(max_evkeys, current) == 0:
        return error_response(_evkey_limit_msg(request, max_evkeys, current), 400)
    evkey = new_evkey()
    eid = await asyncio.to_thread(create_evkey, account_id, evkey, body.get('description', ''))
    return JSONResponse({'id': eid, 'evkey': evkey})

@router.delete('/api/evkeys/{evkey_id}')
async def admin_delete_evkey(evkey_id: int):
    from modules.database.accounts import delete_evkey
    await asyncio.to_thread(delete_evkey, evkey_id)
    return JSONResponse({'success': True})

@router.put('/api/evkeys/{evkey_id}')
async def admin_toggle_evkey(evkey_id: int, request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.accounts import toggle_evkey
    await asyncio.to_thread(toggle_evkey, evkey_id, body.get('enabled', True))
    return JSONResponse({'success': True})

# ---- Evkey bulk generate ----

@router.post('/api/evkey/generate')
async def admin_generate_evkeys(request: Request):
    body = await _body(request) or {}
    # 用 _int_field：count/account_id 传了非数字时 int() 会抛 ValueError 穿透成 500
    count = max(1, min(_int_field(body, 'count', 1), 50))
    account_id = _int_field(body, 'account_id', 0)
    description = body.get('description', '')
    if not account_id: return error_response(t_req(request, 'msg.missing_field', name='account_id'), 400)
    from modules.database.accounts import get_account_by_id, count_evkeys_for_account, create_evkey, new_evkey
    from modules.database.applications import evkey_quota, group_max_evkeys
    acct, current = await asyncio.to_thread(
        lambda: (get_account_by_id(account_id), count_evkeys_for_account(account_id)))
    if not acct: return error_response(t_req(request, 'user.account_not_found'), 404)
    # 同上：管理组折算成不限，批量生成不受组内配置的数值约束
    max_evkeys = await asyncio.to_thread(group_max_evkeys, acct['group_id'])
    quota = evkey_quota(max_evkeys, current)
    # 负数 = 不限：不能直接参与 min，否则会得到一个负额度把生成卡死
    if quota >= 0:
        count = min(count, quota)
    if count == 0: return error_response(_evkey_limit_msg(request, max_evkeys, current), 400)
    def _create_evkeys():
        generated = []
        for _ in range(count):
            evkey = new_evkey()
            eid = create_evkey(account_id, evkey, description)
            generated.append({'id': eid, 'evkey': evkey})
        return generated
    generated = await asyncio.to_thread(_create_evkeys)
    return JSONResponse({'count': len(generated), 'keys': generated})

# ---- Groups ----

@router.get('/api/groups')
async def admin_groups():
    try:
        from modules.database.groups import get_all_groups, current_register_group_id
        # 面板要在列表里标出「默认注册组」，顺带把它和用户组一起返回，省一次请求
        groups, default_id = await asyncio.to_thread(
            lambda: (get_all_groups(), current_register_group_id()))
    except Exception:
        groups, default_id = [], 0
    return JSONResponse({'groups': groups, 'register_default_id': default_id})

@router.post('/api/groups')
async def admin_create_group(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    name = body.get('name', '').strip()
    if not name: return error_response(t_req(request, 'msg.missing_field', name='name'), 400)
    from modules.database.groups import (
        create_group, get_all_groups, normalize_admin_tabs, normalize_category,
    )
    from modules.database.quotas import normalize_period
    if name in {g['name'] for g in await asyncio.to_thread(get_all_groups)}:
        return error_response(t_req(request, 'msg.group_name_taken', name=name), 409)
    category = normalize_category(body.get('category'))
    gid = await asyncio.to_thread(
        create_group,
        name, body.get('description', ''),
        _int_field(body, 'max_concurrent_renders', 5),
        _int_field(body, 'rate_limit_per_minute', 0),
        _int_field(body, 'max_evkeys', 3),
        _int_field(body, 'quota_limit', 0),
        normalize_period(body.get('quota_period')),
        category,
        # 普通用户组只有「我的」，分页清单不保留；管理组按勾选结果存
        normalize_admin_tabs(body.get('admin_tabs')) if category == 'admin' else '',
        _int_field(body, 'show_announcement', 1),
    )
    return JSONResponse({'id': gid, 'name': name})

@router.put('/api/groups/{group_id}')
async def admin_update_group(group_id: int, request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    guard = await asyncio.to_thread(_builtin_admin_guard, group_id, t_req(request, 'user.builtin_admin_no_edit'))
    if guard: return guard
    from modules.database.groups import update_group, get_all_groups, normalize_admin_tabs, normalize_category
    from modules.database.quotas import normalize_period
    new_name = (body.get('name') or '').strip()
    if new_name and new_name in {g['name'] for g in await asyncio.to_thread(get_all_groups) if g['id'] != group_id}:
        return error_response(t_req(request, 'msg.group_name_taken', name=new_name), 409)
    payload = dict(body)
    # 数值字段统一整型化（空值 = 0），周期收敛到合法取值，避免 'false' 这类字符串
    # 被原样写进库，读回来再经 parse_config_value 变成 truthy
    for key in ('max_evkeys', 'max_concurrent_renders', 'rate_limit_per_minute', 'quota_limit'):
        if key in payload:
            payload[key] = _int_field(payload, key, 0)
    if 'quota_period' in payload:
        payload['quota_period'] = normalize_period(payload['quota_period'])
    if 'show_announcement' in payload:
        # 布尔字段整型化：字符串 'false' 直接进 bool() 会变成 True
        payload['show_announcement'] = _int_field(payload, 'show_announcement', 1)
    if 'category' in payload:
        payload['category'] = normalize_category(payload['category'])
    if payload.get('category') == 'user':
        # 改回普通用户组时清掉遗留的分页清单：留着的话下次切回管理组会带出一份过期的旧勾选
        payload['admin_tabs'] = ''
    elif 'admin_tabs' in payload:
        payload['admin_tabs'] = normalize_admin_tabs(payload['admin_tabs'])
    await asyncio.to_thread(update_group, group_id, **payload)
    # 限额按用户组缓存，改完必须显式失效，否则要等重启才生效
    from modules.utils.rate_limiter import invalidate_group_limits
    invalidate_group_limits(group_id)
    # 并发信号量按用户缓存，改完要丢弃该用户组下所有用户的旧信号量才能立刻生效
    _drop_group_semaphores(request.app.state, group_id)
    return JSONResponse({'success': True})

@router.delete('/api/groups/{group_id}')
async def admin_delete_group(group_id: int, request: Request):
    """删除用户组。带 transfer_to 时先把组下账号整体转移到该组，再删组。

    不带 transfer_to 会按 accounts.group_id 的 ON DELETE CASCADE 连带删掉账号与 evkey。

    三条硬约束：
    1) 内置兜底组不可删——它们是删组动作自己的落点（默认注册组、账号转移目标）；
    2) 组内还有「激活码开通且未到期」的账号时不可删，删除等于单方面终止已售出的时长；
       管理员手动提级/手动建号的账号不算，那本就是他自己的操作（判定见 groups 模块）；
    3) 被删的组若正担任默认注册组，标记要跟着这次删除的落点走：转移 → 跟着转到目标组；
       连带删除 → 落到内置兜底用户组。目标组是管理组时不能继承这个标记，否则不带激活码
       注册一次就是管理员。
    """
    from modules.database.groups import (
        builtin_user_group_id, count_unexpired_accounts_in_group, current_register_group_id,
        delete_group, get_group, group_is_admin_category, is_admin_category,
        set_register_default_group, transfer_group_accounts,
    )
    from modules.database.accounts import count_accounts_in_group
    from modules.utils.rate_limiter import invalidate_group_limits
    from modules.auth.auth import invalidate_auth_cache

    group = await asyncio.to_thread(get_group, group_id)
    if group is None:
        return error_response(t_req(request, 'user.group_not_found'), 404)
    if group.get('builtin'):
        return error_response(t_req(request, 'user.builtin_group_undeletable', name=group['name']), 400)

    unexpired = await asyncio.to_thread(count_unexpired_accounts_in_group, group_id)
    if unexpired > 0:
        return error_response(t_req(request, 'user.group_del_has_unexpired', n=unexpired), 400)

    moved = 0
    target_id = 0
    transfer_to = request.query_params.get('transfer_to')
    if transfer_to:
        try:
            target_id = int(transfer_to)
        except (TypeError, ValueError):
            return error_response(t_req(request, 'user.transfer_to_invalid'), 400)
        if target_id == group_id:
            return error_response(t_req(request, 'user.transfer_to_self'), 400)
        target = await asyncio.to_thread(get_group, target_id)
        if target is None:
            return error_response(t_req(request, 'user.target_group_not_found'), 404)
        if is_admin_category(target.get('category')):
            # 删组的转移也是一次批量改组：转进管理组等于批量授予后台权限
            return error_response(t_req(request, 'user.transfer_admin_forbidden'), 400)
        moved = await asyncio.to_thread(count_accounts_in_group, group_id)
        await asyncio.to_thread(transfer_group_accounts, group_id, target_id)
        # 账号换组：并发信号量与鉴权缓存里的组信息都得按新组重建
        _drop_group_semaphores(request.app.state, group_id, target_id)

    if await asyncio.to_thread(current_register_group_id) == group_id:
        fallback = target_id
        if not fallback or await asyncio.to_thread(group_is_admin_category, fallback):
            fallback = await asyncio.to_thread(builtin_user_group_id)
        await asyncio.to_thread(set_register_default_group, fallback)

    await asyncio.to_thread(delete_group, group_id)
    invalidate_group_limits(group_id)
    invalidate_auth_cache()
    return JSONResponse({'success': True, 'transferred': moved})

# ---- Activation codes ----

def _validate_code_inputs(request, body, group_id):
    """激活码入参校验。返回 (expires_on, fallback_group_id, 错误响应)"""
    import datetime
    expires_on = (body.get('expires_on') or '').strip()
    if expires_on:
        # 必须是 YYYY-MM-DD：核销时是字符串比较，格式错了会静默永远通过或永远失败
        try:
            datetime.date.fromisoformat(expires_on)
        except ValueError:
            return None, None, error_response(t_req(request, 'user.bad_code_expires_format'), 400)
    fallback = _int_field(body, 'fallback_group_id', 0)
    if fallback:
        from modules.database.groups import get_group, is_admin_category
        if fallback == group_id:
            return None, None, error_response(t_req(request, 'user.fallback_same_group'), 400)
        fb = get_group(fallback)
        if fb is None:
            return None, None, error_response(t_req(request, 'user.fallback_not_found'), 404)
        if is_admin_category(fb.get('category')):
            # 回落组是管理组时，会员一到期就自动升成管理员——一条没人盯着的提权通道
            return None, None, error_response(t_req(request, 'user.fallback_admin_forbidden'), 400)
    return expires_on, fallback, None


@router.get('/api/activation-codes')
async def admin_codes(request: Request):
    """激活码列表（跨组管理）。?group_id= 按用户组筛选；?status= 按状态筛选。

    用户组行里的「激活码」按钮跳到本接口并预筛该组。用完 / 过期的码一律当场销毁
    （后台扫描周期是分钟级，靠它兜底会让废码在面板上停留几十秒），所以列表读之前
    先清一次，返回的永远只可能是还能用的码。
    """
    from modules.database.activations import (
        list_codes, code_status, today_iso, purge_dead_codes,
    )
    group_id = request.query_params.get('group_id')
    try:
        group_id = int(group_id) if group_id not in (None, '', '0') else 0
    except (TypeError, ValueError):
        return error_response(t_req(request, 'user.group_id_invalid'), 400)
    status = (request.query_params.get('status') or '').strip()
    today = today_iso()
    def _load_codes():
        purge_dead_codes(today)
        return list_codes(group_id)
    rows = await asyncio.to_thread(_load_codes)
    codes = []
    for row in rows:
        row['status'] = code_status(row, today)
        if status and row['status'] != status:
            continue
        codes.append(row)
    return JSONResponse({'codes': codes, 'total': len(codes)})

@router.post('/api/activation-codes')
async def admin_create_code(request: Request):
    """新建激活码（跨组管理）。目标用户组在 body.group_id 里选。

    max_uses（可激活账号数）/ duration_days（账号有效期）都按项目约定 0 = 不限，
    负数一律钳到 0；expires_on 是激活码本身的有效日期，'' = 永不过期。
    allow_repeat = 1 表示允许同一账号反复激活（每次照常占一个名额、到期日在现有基础上叠加）。
    """
    body = await _body(request) or {}
    from modules.database.groups import get_group, is_admin_category
    group_id = _int_field(body, 'group_id', 0)
    target = await asyncio.to_thread(get_group, group_id)
    if target is None:
        return error_response(t_req(request, 'user.group_not_found'), 404)
    if is_admin_category(target.get('category')):
        return error_response(t_req(request, 'user.code_admin_forbidden'), 400)
    expires_on, fallback, err = await asyncio.to_thread(_validate_code_inputs, request, body, group_id)
    if err:
        return err
    from modules.database.activations import create_code
    cid, code = await asyncio.to_thread(
        create_code,
        group_id,
        max(0, _int_field(body, 'max_uses', 0)),
        expires_on,
        max(0, _int_field(body, 'duration_days', 0)),
        fallback,
        body.get('note', ''),
        bool(body.get('allow_repeat')),
    )
    return JSONResponse({'success': True, 'id': cid, 'code': code})

@router.put('/api/activation-codes/{code_id}')
async def admin_toggle_code(code_id: int, request: Request):
    """改激活码开关。两个字段都按「传了才改」处理——只传 allow_repeat 时
    绝不能顺手把 enabled 写成 True，否则会把停用中的码悄悄启用回来。
    """
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.activations import get_code, set_code_enabled, set_code_allow_repeat
    if await asyncio.to_thread(get_code, code_id) is None:
        return error_response(t_req(request, 'user.code_not_found'), 404)
    if 'enabled' in body:
        await asyncio.to_thread(set_code_enabled, code_id, body['enabled'])
    if 'allow_repeat' in body:
        await asyncio.to_thread(set_code_allow_repeat, code_id, body['allow_repeat'])
    return JSONResponse({'success': True})

@router.delete('/api/activation-codes/{code_id}')
async def admin_delete_code(code_id: int, request: Request):
    from modules.database.activations import get_code, delete_code
    if await asyncio.to_thread(get_code, code_id) is None:
        return error_response(t_req(request, 'user.code_not_found'), 404)
    await asyncio.to_thread(delete_code, code_id)
    return JSONResponse({'success': True})


@router.get('/api/groups/{group_id}/permissions')
async def admin_group_perms(group_id: int):
    from modules.database.groups import get_group_permissions
    return JSONResponse(await asyncio.to_thread(get_group_permissions, group_id))

@router.post('/api/groups/{group_id}/permissions')
async def admin_set_group_perms(group_id: int, request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    guard = await asyncio.to_thread(_builtin_admin_guard, group_id, t_req(request, 'user.builtin_admin_no_perm'))
    if guard: return guard
    from modules.database.groups import set_group_plugin, delete_group_plugin, set_group_route, delete_group_route
    # 值必须是显式规则：False 才是"禁用"（缺规则表示默认允许）。
    # 传 null 表示删除规则、恢复默认允许，不能用"删除"来表达禁用，否则永远禁不掉。
    def _apply_group_rules():
        for name, enabled in (body.get('plugins') or {}).items():
            if enabled is None:
                delete_group_plugin(group_id, name)
            else:
                set_group_plugin(group_id, name, bool(enabled))
        for path, enabled in (body.get('routes') or {}).items():
            if enabled is None:
                delete_group_route(group_id, path)
            else:
                set_group_route(group_id, path, bool(enabled))
    await asyncio.to_thread(_apply_group_rules)
    return JSONResponse({'success': True})

@router.get('/api/groups/{group_id}/params')
async def admin_group_params(group_id: int):
    from modules.database.access import get_group_params
    return JSONResponse({'params': await asyncio.to_thread(get_group_params, group_id)})

@router.post('/api/groups/{group_id}/params')
async def admin_set_group_params(group_id: int, request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    guard = await asyncio.to_thread(_builtin_admin_guard, group_id, t_req(request, 'user.builtin_admin_no_perm'))
    if guard: return guard
    from modules.database.access import set_group_param, delete_group_param
    # 与插件/路由权限同一套语义：enabled=False 才是"禁用该参数"，null 表示删除规则恢复默认允许
    if 'param_key' in body:
        pairs = {body['param_key']: body.get('enabled')}
    else:
        pairs = body
    def _apply_group_params():
        for key, enabled in pairs.items():
            if enabled is None:
                delete_group_param(group_id, key)
            else:
                set_group_param(group_id, key, bool(enabled))
    await asyncio.to_thread(_apply_group_params)
    return JSONResponse({'success': True})

# ---- Account quota (grant / reset / logs) ----

def _quota_context(request, account_id):
    """账号 + 其用户组的配额设定，一次查询取齐。返回 (行, None) 或 (None, 错误响应)"""
    from modules.database.accounts import get_account_row
    acct = get_account_row(account_id)
    if not acct:
        return None, error_response(t_req(request, 'user.account_not_found'), 404)
    return acct, None


@router.get('/api/accounts/{account_id}/quota')
async def admin_account_quota(account_id: int, request: Request):
    """账号额度总览：组配额 + 发放额 = 实际额度，以及本周期已用与操作流水"""
    from modules.database.quotas import get_granted, get_status, list_logs, normalize_period
    acct, err = await asyncio.to_thread(_quota_context, request, account_id)
    if err:
        return err
    base = _int_field(acct, 'quota_limit', 0)
    period = normalize_period(acct.get('quota_period'))
    def _load_quota():
        status = get_status(account_id, base, period)
        return status, get_granted(account_id), list_logs(account_id, limit=50)
    (effective, used, period, start), granted, logs = await asyncio.to_thread(_load_quota)
    return JSONResponse({
        'account_id': account_id,
        'account_name': acct.get('name') or '',
        'group_id': acct.get('group_id'),
        'group_name': acct.get('group_name') or '',
        'base_limit': base,
        'granted': granted,
        'limit': effective,
        'used': used,
        # -1 = 不限（组配额 0），前端据此显示「不限」而不是一个负数
        'remaining': (max(0, effective - used) if effective > 0 else -1),
        'period': period,
        'period_start': start,
        'logs': logs,
    })


@router.post('/api/accounts/{account_id}/quota/grant')
async def admin_grant_account_quota(account_id: int, request: Request):
    """发放（正数）或回收（负数）该账号的额外额度"""
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.quotas import grant, normalize_period
    acct, err = await asyncio.to_thread(_quota_context, request, account_id)
    if err:
        return err
    amount = _int_field(body, 'amount', 0)
    if amount == 0:
        return error_response(t_req(request, 'user.grant_amount_zero'), 400)
    ok, msg, total = await asyncio.to_thread(
        grant,
        account_id, amount, _int_field(acct, 'quota_limit', 0),
        normalize_period(acct.get('quota_period')), body.get('reason', ''), _actor_name(request),
    )
    if not ok:
        return error_response(msg, 400)
    return JSONResponse({'success': True, 'limit': total})


@router.post('/api/accounts/{account_id}/quota/reset')
async def admin_reset_account_quota(account_id: int, request: Request):
    """手动重置：本周期已用归零，已发放额度保留"""
    body = await _body(request) or {}
    from modules.database.quotas import normalize_period, reset
    acct, err = await asyncio.to_thread(_quota_context, request, account_id)
    if err:
        return err
    await asyncio.to_thread(
        reset, account_id, normalize_period(acct.get('quota_period')), body.get('reason', ''),
        _actor_name(request))
    return JSONResponse({'success': True})


# ---- Account membership (权限变动记录) ----

@router.get('/api/accounts/{account_id}/membership-logs')
async def admin_account_membership_logs(account_id: int, request: Request):
    """账号的权限变动记录：改组 / 到期日增减 / 到期回落组，最新的在前。

    激活码开通（activate）与到期自动归位（expire）也写进同一张表，
    所以这里是一条完整的时间线，而不只有管理员手动改过什么。
    """
    from modules.database.accounts import get_account_row
    if await asyncio.to_thread(get_account_row, account_id) is None:
        return error_response(t_req(request, 'user.account_not_found'), 404)
    try:
        from modules.database.membership import count_logs, list_logs
        limit = min(max(int(request.query_params.get('limit', 50)), 1), 200)
        offset = max(int(request.query_params.get('offset', 0)), 0)
        items, total = await asyncio.to_thread(
            lambda: (list_logs(account_id, limit=limit, offset=offset), count_logs(account_id)))
        return JSONResponse({
            'items': items,
            'total': total,
        })
    except Exception as e:
        return error_response(str(e), 500)


# ---- Applications ----

@router.get('/api/applications')
async def admin_list_applications(request: Request):
    """待审批申请：按账号折叠返回，一个账号一行。

    只列待审批的——已批准/已拒绝是历史记录，审批时就地做决定即可，翻历史徒增干扰。
    total 是折叠后的账号数（分页按账号走）。
    """
    try:
        # limit/offset 必须双向夹：limit 负值会被 SQLite 当成 LIMIT -1（等于不限量），
        # 一次请求就能把整表拉出来
        limit = max(1, min(int(request.query_params.get('limit', 50)), 200))
        offset = max(0, int(request.query_params.get('offset', 0)))
        from modules.database.applications import (
            get_application_groups, count_application_groups, count_evkey_applications,
        )
        groups, total, pending_count = await asyncio.to_thread(
            lambda: (get_application_groups(status='pending', limit=limit, offset=offset),
                     count_application_groups(status='pending'),
                     # 红点看的是待审批的申请条数，不是账号数
                     count_evkey_applications(status='pending')))
        return {'groups': groups, 'total': total, 'pending_count': pending_count}
    except Exception as e:
        return error_response(str(e), 500)

@router.post('/api/applications/batch')
async def admin_batch_applications(request: Request):
    """批量批准/拒绝申请：一次处理多个账号下的待审批申请。

    只处理仍为 pending 的条目，已处理过的自动跳过（批准返回实际生成的 evkey）。
    """
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    action = body.get('action') or ''
    ids = body.get('ids')
    if action not in ('approve', 'reject'):
        return error_response(t_req(request, 'user.unknown_action'), 400)
    if not isinstance(ids, list):
        return error_response(t_req(request, 'user.ids_not_list'), 400)
    try:
        ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        return error_response(t_req(request, 'user.ids_invalid'), 400)
    if not ids:
        return error_response(t_req(request, 'user.need_pick_application'), 400)

    note = body.get('note', '')
    from modules.database.applications import (
        batch_approve_evkey_applications, batch_reject_evkey_applications,
    )
    if action == 'approve':
        # 不再收 group_id：上限按申请单自带的组判定，见 _application_group_id
        keys, skipped = await asyncio.to_thread(batch_approve_evkey_applications, ids, note)
        if not keys:
            # 全被跳过时把原因带出去，比笼统的「不存在或已处理」有用
            if skipped:
                return error_response(skipped[0], 400)
            return error_response(t_req(request, 'user.application_not_found'), 404)
        from modules.auth.auth import invalidate_auth_cache
        invalidate_auth_cache()
        return JSONResponse({'success': True, 'approved': len(keys), 'keys': keys,
                             'skipped': skipped})

    rejected = await asyncio.to_thread(batch_reject_evkey_applications, ids, note)
    if not rejected:
        return error_response(t_req(request, 'user.application_not_found'), 404)
    return JSONResponse({'success': True, 'rejected': rejected})

@router.post('/api/applications/{app_id}/approve')
async def admin_approve_application(app_id: int, request: Request):
    body = await _body(request) or {}
    admin_note = body.get('note', '')
    from modules.database.applications import approve_evkey_application, EvkeyLimitExceeded
    from modules.auth.auth import invalidate_auth_cache
    try:
        result = await asyncio.to_thread(approve_evkey_application, app_id, admin_note)
    except EvkeyLimitExceeded as e:
        return error_response(str(e), 400)
    if result is None: return error_response(t_req(request, 'user.application_not_found_one'), 404)
    invalidate_auth_cache()
    return JSONResponse({'success': True, 'account_id': result['account_id'], 'evkey': result['evkey']})

@router.post('/api/applications/{app_id}/reject')
async def admin_reject_application(app_id: int, request: Request):
    body = await _body(request) or {}
    from modules.database.applications import reject_evkey_application
    await asyncio.to_thread(reject_evkey_application, app_id, body.get('note', ''))
    return JSONResponse({'success': True})