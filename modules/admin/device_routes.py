"""账号面「我的设备」接口：认领 / 列表 / 详情 / 更新 / 删除 / 渲染项管理。

与设备面契约（`modules/device/routes.py`，给 ESP 用、靠 `X-Device-Token` 鉴权）分开：
这里走登录态（`request.state.user`），两者共用 `modules/device/store.py` 这一份数据层
——名额、令牌、渲染项的口径只写一处，不会出现「设备端放行、账号端拒绝」的双份判定。

**本文件任何端点都不签发也不回传设备令牌**：明文令牌只在设备轮询 `/device/pair`
时出现一次，库里只存哈希（见 `store.hash_device_token`）。
"""
import asyncio
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from modules.admin.common import _body, _int_field
from modules.device import store
from modules.errors.errors import ParamError, error_response
from modules.i18n.registry import t_req

router = APIRouter()

# 屏幕尺寸上限：与设备面 `_dimension` 同一口径（脏值不该让渲染端算出天文数字的图）
_MAX_DIMENSION = 4096
# 由路由层单独解析的保留参数，与 `modules/prerender/params.py` 的 _RESERVED 一致
_RESERVED_ARGS = ('size', 'rotate', 'invert', 'cmode', 'format')


# ======================== 通用 ========================

def _truthy(value):
    """宽松真值：前端发 JSON 布尔，也兼容 '0' / 'false' / 'no' 这类字符串写法"""
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false', 'no')
    return bool(value)


def _json_obj(raw):
    """JSON 列 → dict；坏值当空字典（与 `store` 内同一口径，一条脏数据不该把接口打挂）"""
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_id(raw):
    """路径参数 → 整数 id；非数字返回 None（调用方一律回 404，不泄露存在性）"""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _not_found(request):
    return error_response(t_req(request, 'account.dev_not_found'), 404)


def _plugin_dir(name):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(root, 'plugins', name)


def _limits():
    """前端表单要用的取值区间与候选：间隔上下限、可选输出格式、可选调色板。

    全部从权威处现取（config / image_output / canvas_factory），不在前端另抄一份字面量
    ——注册表加一种格式而那边还在拒绝，是这类候选列表最典型的走偏方式。
    """
    from modules.generate_views.canvas_factory import PALETTES
    from modules.generate_views.array_formats import array_formats, format_for_palette
    palettes = sorted(PALETTES)
    return {
        'min_interval': int(getattr(config, 'DEVICE_MIN_SLEEP_SECONDS', 60)),
        'max_interval': int(getattr(config, 'DEVICE_MAX_SLEEP_SECONDS', 21600)),
        # 设备只走数组格式族（省设备端内存），且格式恒由调色板推导、不由用户手选：
        # `formats` 仍是数组族的全部名字，`palette_formats` 是「调色板 → 唯一格式」对照表。
        'formats': array_formats(),
        'palettes': palettes,
        'palette_formats': {p: format_for_palette(p) for p in palettes},
    }


def _scan_plugin_routes(plugin_name):
    """扫一个插件的可选路由与尺寸。规则与面板的插件页（`modules/admin/plugin_routes.py`）
    同一套：`view` / `json_module` / `page` 三类，跳过 `_` / `.` 开头的条目；
    `view` 下用 `available_view_sizes` 取真正实现了 `generate_image` 的尺寸。
    """
    from modules.register.auto_view_routes import available_view_sizes
    plugin_dir = _plugin_dir(plugin_name)
    routes = []
    for sub in ('view', 'json_module', 'page'):
        sub_dir = os.path.join(plugin_dir, sub)
        if not os.path.isdir(sub_dir):
            continue
        suffix = sub.replace('_module', '')
        for entry in sorted(os.listdir(sub_dir)):
            if entry.startswith('_') or entry.startswith('.'):
                continue
            entry_path = os.path.join(sub_dir, entry)
            sizes = []
            if os.path.isdir(entry_path):
                route_path = f'/{plugin_name}/{suffix}/{entry}'
                if sub == 'view':
                    sizes = available_view_sizes(plugin_name, sub_dir, entry)
            elif entry.endswith('.py'):
                route_path = f'/{plugin_name}/{suffix}/{entry[:-3]}'
            else:
                continue
            routes.append({'path': route_path, 'name': entry, 'kind': suffix, 'sizes': sizes})
    return routes


# ======================== 守卫 ========================

async def _ctx(request):
    """取当前登录账号；未登录返回 `(None, 401 响应)`"""
    user = getattr(request.state, 'user', None)
    if not user:
        return None, error_response(t_req(request, 'msg.need_login'), 401)
    return user, None


async def _owned_device(request, device_id):
    """取当前账号**自有**的设备；不存在或不属于本人**一律 404**（不泄露存在性）。

    「自有」与「可编辑」是两条不同口径：共享进来的设备可以编辑，但只有属主能删除设备、
    解除共享，因此两个守卫分开（见 `_editable_device`）。
    """
    user, err = await _ctx(request)
    if err:
        return None, None, err
    did = _parse_id(device_id)
    device = await asyncio.to_thread(store.get_device, did) if did else None
    if not device or device.get('account_id') != user['id']:
        return None, None, _not_found(request)
    row = dict(device)
    row['owner'] = 1
    return user, row, None


async def _editable_device(request, device_id):
    """取当前账号**可编辑**的设备：本人所有，或被共享给本人；两者都不是一律 404。

    共享进来的行补上 `owner=0` 与 `shared_by_id` / `shared_by_name`，详情据此显示
    「由 XX 共享」——共享关系只在设备详情里出现，卡片上不展示。
    """
    user, err = await _ctx(request)
    if err:
        return None, None, err
    did = _parse_id(device_id)
    device = await asyncio.to_thread(store.get_device, did) if did else None
    if not device:
        return None, None, _not_found(request)
    row = dict(device)
    if device.get('account_id') == user['id']:
        row['owner'] = 1
        return user, row, None
    if await asyncio.to_thread(store.is_device_shared_with, device['id'], user['id']):
        row['owner'] = 0
        row['shared_by_id'] = device.get('account_id')
        row['shared_by_name'] = await asyncio.to_thread(
            store.get_device_owner_name, device['id'])
        return user, row, None
    return None, None, _not_found(request)


async def _editable_task(request, task_id):
    """取当前账号**可编辑**的渲染项，返回 `(user, task, device, err)`（口径同 `_editable_device`）"""
    user, err = await _ctx(request)
    if err:
        return None, None, None, err
    tid = _parse_id(task_id)
    task = await asyncio.to_thread(store.get_device_task, tid) if tid else None
    device = await asyncio.to_thread(store.get_device, task.get('device_id')) if task else None
    if not device:
        return None, None, None, _not_found(request)
    if device.get('account_id') != user['id']:
        if not await asyncio.to_thread(store.is_device_shared_with, device['id'], user['id']):
            return None, None, None, _not_found(request)
    return user, task, device, None


# ======================== 序列化 ========================

def _device_summary(device, task_count=0):
    return {
        'id': device['id'],
        'name': device.get('name') or '',
        'model': device.get('model') or '',
        'hw_uid': device.get('hw_uid') or '',
        'width': int(device.get('width') or 0),
        'height': int(device.get('height') or 0),
        'palette': device.get('palette') or 'bw',
        'format': device.get('format') or 'array',
        'enabled': bool(device.get('enabled')),
        'schedule_type': device.get('schedule_type') or 'interval',
        'interval_seconds': int(device.get('interval_seconds') or 0),
        'daily_times': device.get('daily_times') or '',
        'cron_expr': device.get('cron_expr') or '',
        'timezone': device.get('timezone') or '',
        'last_seen_at': device.get('last_seen_at'),
        'last_status': device.get('last_status') or '',
        'last_error': device.get('last_error') or '',
        # 已认领但设备还没来换过令牌：面板据此显示「等待设备上线」
        'paired': bool(device.get('token_hash')),
        'task_count': int(task_count or 0),
        # 共享：owner=False 表示这台是别人共享进来的，shared_by_name 即共享者名。
        # 只在设备详情里展示，卡片上不显示（列表接口照样带出来，由前端决定用不用）。
        'owner': True if device.get('owner') is None else bool(device.get('owner')),
        'shared_by_id': device.get('shared_by_id'),
        'shared_by_name': device.get('shared_by_name') or '',
    }


def _task_summary(task, device=None):
    return {
        'id': task['id'],
        'name': task.get('name') or '',
        'plugin_name': task.get('plugin_name') or '',
        'route_path': task.get('route_path') or '',
        'route_kind': task.get('route_kind') or 'view',
        'size': task.get('size') or '',
        'params': store.load_task_params(task),
        'enabled': bool(task.get('enabled')),
        'sort_order': int(task.get('sort_order') or 0),
    }


async def _detail_payload(device):
    """设备详情的统一回包：摘要 + 渲染项 + 表单区间；属主再附上「共享给了谁」。

    `shares` 只对属主出现——被共享方不需要（也无权）知道这台还共享给了哪些人。
    """
    tasks = await asyncio.to_thread(store.list_device_tasks, device['id'])
    detail = _device_summary(device, len(tasks))
    detail['tasks'] = [_task_summary(task, device) for task in tasks]
    detail['limits'] = _limits()
    if detail['owner']:
        detail['shares'] = await asyncio.to_thread(store.list_shares_for_device, device['id'])
    return detail


# ======================== 渲染项校验 ========================

async def _validate_task(request, user, plugin_name, route_path, size, params):
    """渲染项写入前的三重校验：插件可达 → 路由与尺寸可用 → 参数符合插件 schema。

    偏「让用户当场改对」：取图路径（`/device/image`）每次都会再复核一遍插件与路由权限，
    所以这里漏了也不会越权，但会让用户在设备上看到一张模糊的 404 而不是一条明确的 400。
    """
    if not plugin_name or not route_path or not size:
        return error_response(t_req(request, 'account.dev_task_incomplete'), 400)
    from modules.database.access import check_user_plugin_access, check_user_route_access
    group_id = user.get('group_id')
    if not check_user_plugin_access(group_id, plugin_name):
        return error_response(t_req(request, 'account.dev_task_no_perm'), 403)
    routes = await asyncio.to_thread(_scan_plugin_routes, plugin_name)
    route = next((r for r in routes if r['path'] == route_path), None)
    if route is None or route['kind'] != 'view' or size not in route['sizes']:
        return error_response(t_req(request, 'account.dev_task_bad_route'), 400)
    if not check_user_route_access(group_id, route_path):
        return error_response(t_req(request, 'account.dev_task_no_perm'), 403)
    from modules.plugins.plugin_loader import get_view_args_schema
    from modules.plugins.view_args import validate_view_args
    schema = await asyncio.to_thread(get_view_args_schema, plugin_name, _plugin_dir(plugin_name))
    try:
        validate_view_args(schema, params or {}, _RESERVED_ARGS)
    except ParamError as exc:
        return error_response(str(exc), 400)
    return None


# ======================== 端点 ========================

@router.get('/api/my/devices')
async def my_devices(request: Request):
    """我的设备列表 = 自有的 ∪ 别人共享给我的（含每台的渲染项数量与「已认领待上线」计数）。

    `current`（已用名额）与 `pending_claim` **只统计自有的**：共享进来的设备不占接收方
    名额，也不该让接收方看到属主那台的「等待上线」提示。
    """
    user, err = await _ctx(request)
    if err:
        return err
    devices = await asyncio.to_thread(store.list_devices_owned_and_shared, user['id'])
    items = []
    current = 0
    pending_claim = 0
    for device in devices:
        tasks = await asyncio.to_thread(store.list_device_tasks, device['id'])
        summary = _device_summary(device, len(tasks))
        if summary['owner']:
            current += 1
            if not summary['paired']:
                pending_claim += 1
        items.append(summary)
    max_devices = await asyncio.to_thread(store.group_max_devices, user.get('group_id'))
    return JSONResponse({
        'devices': items,
        'current': current,
        'max': max_devices,
        'pending_claim': pending_claim,
    })


@router.post('/api/my/devices/claim')
async def claim_device(request: Request):
    """输入设备屏上的 8 位配对码完成认领。

    **只绑定归属，不签发令牌**：设备下次轮询 `/device/pair` 时才拿到明文令牌（只出现一次）。
    因此认领成功后设备仍显示「等待设备上线」，直到它回来换令牌。
    """
    user, err = await _ctx(request)
    if err:
        return err
    from modules.utils.rate_limiter import check_scoped
    # 8 位码的空间不算小，但接口未鉴权就能探测账号归属，限流不能省
    allowed, _ = await check_scoped(f'claim:{user["id"]}', 10, 60)
    if not allowed:
        return error_response(t_req(request, 'account.dev_claim_rate_limited'), 429)

    body = await _body(request)
    code = str((body or {}).get('pair_code') or '') if isinstance(body, dict) else ''
    bad = t_req(request, 'account.dev_claim_bad')
    pairing = await asyncio.to_thread(store.get_pending_pairing_by_code, code)
    if not pairing:
        return error_response(bad, 400)
    if store.is_pairing_expired(pairing):
        await asyncio.to_thread(store.set_pairing_status, pairing['id'], 'expired')
        # 与「码不存在」同一句：不泄露「码存在但过期」
        return error_response(bad, 400)

    owner = pairing.get('account_id')
    if owner:
        if owner != user['id']:
            return error_response(t_req(request, 'account.dev_claim_taken'), 409)
        # 同一账号重复提交同一码：幂等返回成功，不重复占用名额
        return JSONResponse({'success': True, 'device_id': pairing.get('device_id'),
                             'message': t_req(request, 'account.dev_claim_ok')})

    hw_uid = str(pairing.get('hw_uid') or '')
    denied = await asyncio.to_thread(store.device_quota_error, user['id'], hw_uid)
    if denied:
        return error_response(denied, 400)

    payload = _json_obj(pairing.get('payload_json'))
    device_id = await asyncio.to_thread(store.bind_device_to_account, hw_uid, user['id'], payload)
    written = await asyncio.to_thread(
        store.attach_pairing_account, pairing['id'], user['id'], device_id)
    # 写后回读复核归属：两次认领撞在一起时条件写会落空，落空就得回报冲突而不是假装成功
    fresh = await asyncio.to_thread(store.get_device, device_id)
    if not written or not fresh or fresh.get('account_id') != user['id']:
        return error_response(t_req(request, 'account.dev_claim_taken'), 409)
    # 同一台设备的旧码一并作废：否则旧码还能被别的账号认领，把归属改走
    await asyncio.to_thread(store.cancel_other_pairings, hw_uid, pairing['id'])
    return JSONResponse({'success': True, 'device_id': device_id,
                         'message': t_req(request, 'account.dev_claim_ok')})


@router.get('/api/my/device-options')
async def my_device_options(request: Request):
    """渲染项表单的可选项：插件 → 视图路由 → 尺寸 → 参数 schema，外加取值区间。"""
    user, err = await _ctx(request)
    if err:
        return err
    group_id = user.get('group_id')
    from modules.database.access import check_user_plugin_access, check_user_route_access
    from modules.plugins.plugin_loader import get_view_args_schema
    # 插件清单取自启动时的扫描结果（与面板插件页同一个数据源），再按用户组权限过滤
    plugins = (getattr(request.app.state, 'plugin_result', {}) or {}).get('plugins', [])
    items = []
    for plugin in plugins:
        name = plugin.get('name')
        if not name or not check_user_plugin_access(group_id, name):
            continue
        routes = []
        for route in await asyncio.to_thread(_scan_plugin_routes, name):
            # 设备渲染项只支持视图（`/device/image` 明确拒绝非 view 类型），
            # 这里就把 json / page 路由滤掉，免得前端列出一堆选了必然 400 的选项
            if route['kind'] != 'view' or not route['sizes']:
                continue
            if not check_user_route_access(group_id, route['path']):
                continue
            routes.append(route)
        if not routes:
            continue
        schema = await asyncio.to_thread(get_view_args_schema, name, _plugin_dir(name))
        items.append({
            'name': name,
            'description': plugin.get('description', '') or '',
            'schema': schema,
            'routes': routes,
        })
    return JSONResponse({'plugins': items, 'limits': _limits()})


@router.get('/api/my/devices/{device_id}')
async def get_my_device(device_id: str, request: Request):
    """设备详情（含全部渲染项与表单取值区间）；被共享的设备同样能看"""
    user, device, err = await _editable_device(request, device_id)
    if err:
        return err
    return JSONResponse(await _detail_payload(device))


def _apply_schedule(request, body, fields):
    """排期字段写入：三种模式各按既有解析器校验，非法返回错误响应，合法返回 None。

    间隔钳到 `DEVICE_MIN/MAX_SLEEP_SECONDS`，每日时刻走 `normalize_daily_times`，
    cron 走 `normalize_cron`——三个解析器就是取图链路用的同一份，落库的写法必然一致。
    """
    if 'schedule_type' not in body:
        return None
    kind = str(body.get('schedule_type') or '').lower()
    invalid = error_response(t_req(request, 'account.dev_sched_invalid'), 400)
    if kind == 'interval':
        seconds = _int_field(body, 'interval_seconds', 0)
        low = int(getattr(config, 'DEVICE_MIN_SLEEP_SECONDS', 60))
        high = int(getattr(config, 'DEVICE_MAX_SLEEP_SECONDS', 21600))
        if seconds < low or seconds > high:
            return invalid
        fields.update(schedule_type='interval', interval_seconds=seconds)
        return None
    if kind == 'daily':
        from modules.prerender.scheduler import normalize_daily_times
        value = normalize_daily_times(body.get('daily_times'))
        if not value:
            return invalid
        fields.update(schedule_type='daily', daily_times=value)
        return None
    if kind == 'cron':
        from modules.prerender.scheduler import normalize_cron
        value = normalize_cron(body.get('cron_expr'))
        if not value:
            return invalid
        fields.update(schedule_type='cron', cron_expr=value)
        return None
    return invalid


@router.put('/api/my/devices/{device_id}')
async def update_my_device(device_id: str, request: Request):
    """更新设备：基础信息 + 刷新策略（排期三分支）；共享进来的设备也能改，但不改归属"""
    user, device, err = await _editable_device(request, device_id)
    if err:
        return err
    body = await _body(request)
    if not isinstance(body, dict):
        return error_response(t_req(request, 'msg.bad_json'), 400)

    fields = {}
    for key in ('name', 'model'):
        if key in body:
            fields[key] = str(body.get(key) or '')[:64]
    if 'timezone' in body:
        fields['timezone'] = str(body.get('timezone') or '')[:64]
    if 'width' in body:
        fields['width'] = max(0, min(_int_field(body, 'width', 0), _MAX_DIMENSION))
    if 'height' in body:
        fields['height'] = max(0, min(_int_field(body, 'height', 0), _MAX_DIMENSION))
    if 'enabled' in body:
        fields['enabled'] = 1 if _truthy(body.get('enabled')) else 0
    if 'palette' in body:
        value = str(body.get('palette') or '')
        if value not in _limits()['palettes']:
            return error_response(t_req(request, 'account.dev_bad_value', name=value), 400)
        # 格式不在这里接收：`store.update_device` 会按新调色板推导出唯一对应的 array 格式
        fields['palette'] = value

    invalid = _apply_schedule(request, body, fields)
    if invalid is not None:
        return invalid

    if fields:
        await asyncio.to_thread(store.update_device, device['id'], **fields)
    fresh = await asyncio.to_thread(store.get_device, device['id'])
    dirty = dict(fresh)
    dirty['owner'] = device.get('owner')
    dirty['shared_by_id'] = device.get('shared_by_id')
    dirty['shared_by_name'] = device.get('shared_by_name')
    return JSONResponse({'success': True, 'device': await _detail_payload(dirty)})


@router.delete('/api/my/devices/{device_id}')
async def delete_my_device(device_id: str, request: Request):
    """解绑并删除设备（渲染项随外键级联清掉，旧令牌立即失效）。

    只有**属主**能删：被共享者可以改设置与渲染项，但删设备等于动别人的资产。
    """
    user, device, err = await _owned_device(request, device_id)
    if err:
        return err
    await asyncio.to_thread(store.delete_device, device['id'])
    return JSONResponse({'success': True, 'message': t_req(request, 'account.dev_unbound')})


@router.post('/api/my/devices/{device_id}/shares')
async def share_my_device(device_id: str, request: Request):
    """把设备共享给对方账号（**仅属主**）：body 传 `account_id` 或 `account_name`。

    只能共享给已存在且启用的账号；不能共享给自己（自己是属主时根本没意义）。
    共享后对方即可在「我的设备」里看到这台、共同编辑设置与渲染项，但不能删除。
    """
    user, device, err = await _owned_device(request, device_id)
    if err:
        return err
    body = await _body(request)
    if not isinstance(body, dict):
        return error_response(t_req(request, 'msg.bad_json'), 400)
    from modules.database.accounts import get_account_by_name, get_account_row
    target = None
    raw_id = body.get('account_id')
    if raw_id not in (None, ''):
        tid = _parse_id(raw_id)
        target = await asyncio.to_thread(get_account_row, tid) if tid else None
    else:
        name = str(body.get('account_name') or '').strip()
        target = await asyncio.to_thread(get_account_by_name, name) if name else None
    if not target:
        return error_response(t_req(request, 'account.dev_share_not_found'), 404)
    if target['id'] == user['id']:
        return error_response(t_req(request, 'account.dev_share_self'), 400)
    added = await asyncio.to_thread(store.share_device, device['id'], target['id'])
    if not added:
        return error_response(t_req(request, 'account.dev_share_exists',
                                   name=target.get('name') or ''), 400)
    shares = await asyncio.to_thread(store.list_shares_for_device, device['id'])
    return JSONResponse({'success': True, 'shares': shares,
                         'message': t_req(request, 'account.dev_share_ok',
                                          name=target.get('name') or '')})


@router.delete('/api/my/devices/{device_id}/shares/{account_id}')
async def unshare_my_device(device_id: str, account_id: str, request: Request):
    """解除一台设备对某账号的共享（**仅属主**）"""
    user, device, err = await _owned_device(request, device_id)
    if err:
        return err
    removed = await asyncio.to_thread(store.unshare_device, device['id'], _parse_id(account_id))
    if not removed:
        return _not_found(request)
    shares = await asyncio.to_thread(store.list_shares_for_device, device['id'])
    return JSONResponse({'success': True, 'shares': shares,
                         'message': t_req(request, 'account.dev_share_removed')})


@router.post('/api/my/devices/{device_id}/tasks')
async def create_my_device_task(device_id: str, request: Request):
    """给设备新增一条渲染项（三重校验见 `_validate_task`）；被共享者同样可加"""
    user, device, err = await _editable_device(request, device_id)
    if err:
        return err
    body = await _body(request)
    if not isinstance(body, dict):
        return error_response(t_req(request, 'msg.bad_json'), 400)
    plugin_name = str(body.get('plugin_name') or '').strip()
    route_path = str(body.get('route_path') or '').strip()
    size = str(body.get('size') or '').strip()
    params = body.get('params')
    if not isinstance(params, dict):
        params = {}
    invalid = await _validate_task(request, user, plugin_name, route_path, size, params)
    if invalid is not None:
        return invalid
    existing = await asyncio.to_thread(store.list_device_tasks, device['id'])
    sort_order = max([int(row.get('sort_order') or 0) for row in existing] or [0]) + 1
    task_id = await asyncio.to_thread(
        store.create_device_task, device['id'], plugin_name, route_path,
        str(body.get('name') or '').strip()[:64], 'view', size, params, '',
        sort_order, 1 if _truthy(body.get('enabled', True)) else 0)
    task = await asyncio.to_thread(store.get_device_task, task_id)
    return JSONResponse({'success': True, 'task': _task_summary(task, device)})


@router.post('/api/my/devices/{device_id}/tasks/reorder')
async def reorder_my_device_tasks(device_id: str, request: Request):
    """按给定 id 顺序重排本设备的渲染项（不做拖拽，前端用上移 / 下移后整体提交）"""
    user, device, err = await _editable_device(request, device_id)
    if err:
        return err
    body = await _body(request)
    ids = (body or {}).get('ids') if isinstance(body, dict) else None
    if not isinstance(ids, list):
        return error_response(t_req(request, 'msg.missing_field', name='ids'), 400)
    await asyncio.to_thread(store.reorder_device_tasks, device['id'], ids)
    tasks = await asyncio.to_thread(store.list_device_tasks, device['id'])
    fresh = await asyncio.to_thread(store.get_device, device['id'])
    return JSONResponse({'success': True,
                         'tasks': [_task_summary(task, fresh) for task in tasks]})


@router.put('/api/my/device-tasks/{task_id}')
async def update_my_device_task(task_id: str, request: Request):
    """更新渲染项（改插件 / 路由 / 尺寸 / 参数 / 名称 / 启用）；被共享者同样可改"""
    user, task, device, err = await _editable_task(request, task_id)
    if err:
        return err
    body = await _body(request)
    if not isinstance(body, dict):
        return error_response(t_req(request, 'msg.bad_json'), 400)
    plugin_name = str(body.get('plugin_name') or task.get('plugin_name') or '').strip()
    route_path = str(body.get('route_path') or task.get('route_path') or '').strip()
    size = str(body.get('size') or task.get('size') or '').strip()
    params = body.get('params')
    if not isinstance(params, dict):
        params = store.load_task_params(task)
    invalid = await _validate_task(request, user, plugin_name, route_path, size, params)
    if invalid is not None:
        return invalid
    fields = {
        'plugin_name': plugin_name, 'route_path': route_path, 'size': size,
        'params_json': json.dumps(params, ensure_ascii=False),
    }
    if 'name' in body:
        fields['name'] = str(body.get('name') or '').strip()[:64]
    if 'enabled' in body:
        fields['enabled'] = 1 if _truthy(body.get('enabled')) else 0
    await asyncio.to_thread(store.update_device_task, task['id'], **fields)
    fresh = await asyncio.to_thread(store.get_device_task, task['id'])
    return JSONResponse({'success': True, 'task': _task_summary(fresh, device)})


@router.delete('/api/my/device-tasks/{task_id}')
async def delete_my_device_task(task_id: str, request: Request):
    """删除渲染项（归属复核在 `_editable_task`）"""
    user, task, device, err = await _editable_task(request, task_id)
    if err:
        return err
    await asyncio.to_thread(store.delete_device_task, task['id'])
    return JSONResponse({'success': True})
