"""管理端「设备」分页接口：设备总列表（按账号聚合）与设备签入审批。

与账号面（`modules/admin/device_routes.py`，登录态用户自己管设备）分开：这里走管理权限，
数据层同样只走 `modules/device/store.py` 一份——名额、令牌、绑定口径不会出现双份判定。

- 设备总列表：每个账号一行（账号 / 用户名 / 用户组 / 设备数 / 上限），详情弹窗列出该账号设备；
- 设备签入审批：关闭 `DEVICE_APPROVAL_REQUIRED` 后，用户在网页认领配对码不再当场绑定，
  而是落一条待审批记录（见 `store.create_signin`）。管理员批准时**复用认领那套绑定动作**。
"""
import asyncio
import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body
from modules.device import store
from modules.errors.errors import error_response
from modules.i18n.registry import t_req

router = APIRouter()


def _parse_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _admin_name(request):
    user = getattr(request.state, 'user', None) or {}
    return str(user.get('name') or '')


def _signin_item(row):
    return {
        'id': row['id'],
        'account_id': row['account_id'],
        'uid': int(row.get('account_uid') or 0),
        'account_name': row.get('account_name') or '',
        'group_name': row.get('group_name') or '',
        'hw_uid': row.get('hw_uid') or '',
        'device_name': row.get('device_name') or '',
        'pair_id': row.get('pair_id') or '',
        'created_at': row.get('created_at'),
    }


async def _approve_one(request, signin_id, note=''):
    """审批通过一条签入：复核名额与归属后执行绑定。返回 (错误响应 or None)。

    名额判定放在**真正绑定这一刻**（而不是提交申请时）：期间用户组上限可能被调小，
    以绑定时的权威值为准，与 `device_quota_error` 同一套口径。
    """
    signin = await asyncio.to_thread(store.get_signin, signin_id)
    if not signin or signin.get('status') != 'pending':
        return error_response(t_req(request, 'device.signin_not_found'), 404)
    account_id = signin['account_id']
    hw_uid = signin['hw_uid']
    # 期间可能已被别的账号认领走（同台设备两条待审）：不抢别家的设备，直接判这条失效
    existing = await asyncio.to_thread(store.get_device_by_hw_uid, hw_uid)
    if existing and existing.get('account_id') not in (None, account_id):
        return error_response(t_req(request, 'device.signin_taken'), 409)
    denied = await asyncio.to_thread(store.device_quota_error, account_id, hw_uid)
    if denied:
        # 名额已满：store 回的是取词键，文案按请求语言在这儿拼（与 /device/pair、账号面认领同一组键）
        return error_response(t_req(request, denied[0], **denied[1]), 400)
    try:
        payload = json.loads(signin.get('payload_json') or '{}')
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    device_id = await asyncio.to_thread(store.bind_device_to_account, hw_uid, account_id, payload)
    pair_id = signin.get('pair_id') or ''
    if pair_id:
        await asyncio.to_thread(store.attach_pairing_account, pair_id, account_id, device_id)
        await asyncio.to_thread(store.cancel_other_pairings, hw_uid, pair_id)
    await asyncio.to_thread(store.set_signin_status, signin_id, 'approved', note, _admin_name(request))
    return None


# ======================== 设备总列表 ========================

@router.get('/api/devices')
async def admin_device_overview():
    """设备总列表：每个账号一行（账号 / 用户名 / 用户组 / 设备数 / 上限）。"""
    rows = await asyncio.to_thread(store.list_account_devices_overview)
    items = [{
        'account_id': r['account_id'],
        'uid': int(r.get('account_uid') or 0),
        'account_name': r.get('account_name') or '',
        'group_name': r.get('group_name') or '',
        'device_count': int(r.get('device_count') or 0),
        'max_devices': int(r.get('max_devices') or 0),
    } for r in rows]
    return JSONResponse({
        'accounts': items,
        'total': len(items),
        'device_total': sum(i['device_count'] for i in items),
    })


@router.get('/api/devices/{account_id}')
async def admin_device_account(account_id: str, request: Request):
    """某账号的设备目录（详情弹窗）：复用账号面那份序列化，口径只有一处。"""
    aid = _parse_id(account_id)
    if not aid:
        return error_response(t_req(request, 'user.account_not_found'), 404)
    from modules.admin.user_routes import admin_account_devices
    return await admin_account_devices(aid, request)


# ======================== 设备签入审批 ========================

@router.get('/api/device-signins')
async def admin_device_signins():
    """待审批的签入列表（按提交时间倒序）与待审条数（红点用）。"""
    try:
        rows = await asyncio.to_thread(store.list_pending_signins)
        items = [_signin_item(r) for r in rows]
        return JSONResponse({'items': items, 'total': len(items), 'pending_count': len(items)})
    except Exception as e:  # noqa: BLE001 —— 与申请列表同一处理：坏数据不该把接口打挂
        return error_response(str(e), 500)


@router.post('/api/device-signins/batch')
async def admin_batch_device_signins(request: Request):
    """批量批准 / 拒绝签入：只处理仍为 pending 的条目，已处理的自动跳过。"""
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
        return error_response(t_req(request, 'device.need_pick_signin'), 400)

    note = body.get('note', '')
    done = 0
    skipped = []
    for signin_id in ids:
        if action == 'approve':
            err = await _approve_one(request, signin_id, note)
            if err is not None:
                skipped.append(signin_id)
                continue
            done += 1
        else:
            ok = await asyncio.to_thread(
                store.set_signin_status, signin_id, 'rejected', note, _admin_name(request))
            if ok:
                done += 1
            else:
                skipped.append(signin_id)
    if not done:
        return error_response(t_req(request, 'device.signin_not_found'), 404)
    return JSONResponse({'success': True, 'processed': done, 'skipped': skipped})


@router.post('/api/device-signins/{signin_id}/approve')
async def admin_approve_signin(signin_id: str, request: Request):
    sid = _parse_id(signin_id)
    if not sid:
        return error_response(t_req(request, 'device.signin_not_found'), 404)
    body = await _body(request) or {}
    err = await _approve_one(request, sid, body.get('note', ''))
    if err is not None:
        return err
    return JSONResponse({'success': True})


@router.post('/api/device-signins/{signin_id}/reject')
async def admin_reject_signin(signin_id: str, request: Request):
    sid = _parse_id(signin_id)
    if not sid:
        return error_response(t_req(request, 'device.signin_not_found'), 404)
    body = await _body(request) or {}
    ok = await asyncio.to_thread(
        store.set_signin_status, sid, 'rejected', body.get('note', ''), _admin_name(request))
    if not ok:
        return error_response(t_req(request, 'device.signin_not_found'), 404)
    return JSONResponse({'success': True})


# ======================== 设备治理（启用/停用 / 删除） ========================
# 管理端对设备的能力刻意**少于**用户侧：只做「启用/停用」与「删除」，不做改名、转移归属、
# 解绑、撤销共享——那些是设备属主自己的事（用户面的设备接口）。

@router.put('/api/devices/{device_id}')
async def admin_update_device(device_id: str, request: Request):
    """启用 / 停用某台设备（请求体只认 `enabled` 一个键）。"""
    did = _parse_id(device_id)
    if not did:
        return error_response(t_req(request, 'device.not_found'), 404)
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    if 'enabled' not in body:
        return error_response(t_req(request, 'user.unknown_action'), 400)
    device = await asyncio.to_thread(store.get_device, did)
    if not device:
        return error_response(t_req(request, 'device.not_found'), 404)
    enabled = 1 if body.get('enabled') else 0
    await asyncio.to_thread(store.update_device, did, enabled=enabled)
    return JSONResponse({'success': True, 'device': {'id': did, 'enabled': bool(enabled)}})


@router.delete('/api/devices/{device_id}')
async def admin_delete_device(device_id: str, request: Request):
    """删除某台设备，并通知其属主。

    副作用顺序有讲究：先删设备（连带渲染项/配对会话），再按 hw_uid 把残留的待审签入
    置 rejected——否则那些 pending 会在下一次批准时按同一个 hw_uid 把设备「复活」。
    属主为空（尚未归属）时不发通知，直接删掉了事。
    """
    did = _parse_id(device_id)
    if not did:
        return error_response(t_req(request, 'device.not_found'), 404)
    device = await asyncio.to_thread(store.get_device, did)
    if not device:
        return error_response(t_req(request, 'device.not_found'), 404)
    hw_uid = device.get('hw_uid') or ''
    owner_id = device.get('account_id')
    await asyncio.to_thread(store.delete_device, did)
    if hw_uid:
        await asyncio.to_thread(store.reject_pending_signins_for_device, hw_uid)
    if owner_id:
        from modules.database import notifications
        await asyncio.to_thread(
            notifications.create_notification, owner_id, 'device_deleted',
            {'name': device.get('name') or device.get('model') or '', 'device_id': did})
    return JSONResponse({'success': True})


# ======================== 高级模式 ========================

@router.post('/api/advanced/unlock')
async def admin_advanced_unlock(request: Request):
    """校验高级模式口令（与配置项 `ADVANCED_MODE_KEY` 比对），成功即视为解锁。

    **知情门槛，不是安全边界**：真正的高危操作仍受管理组分页权限管控，这里只是让
    不熟的管理员不误触隐藏项。定长比较，避免逐字符短路泄露口令长度信息。
    """
    body = await _body(request)
    if body is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    key = str(body.get('key') or '')
    import config as cfg
    expected = str(getattr(cfg, 'ADVANCED_MODE_KEY', '') or '')
    if not expected or not key or not hmac.compare_digest(key, expected):
        return error_response(t_req(request, 'adv.wrong_key'), 403)
    return JSONResponse({'success': True})
