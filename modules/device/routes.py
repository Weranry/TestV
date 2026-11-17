"""设备面 HTTP 契约：注册 / 配对 / 状态 / 取图。

与全站其它路由有两处根本不同，写在这里免得后来者踩坑：

1. `/device/**` 在 `config.AUTH_WHITELIST` 里整体放行——设备自带 `X-Device-Token`，
   不属于任何账号的 evkey，走全站鉴权中间件会被当成未登录访客直接 401。
   **放行不等于不设防**：本文件内每条路由都自己复核令牌、插件/路由启用状态与用户组
   权限（口径对照 [app_core.plugin_disable_middleware](file:///d:/Desktop/einkViewsEvo/modules/app_core.py#L295-L334)）。
2. **计时器跑在设备上**。这里只回答「睡多少秒」和「下次请求哪个 URL」，服务端不存排期
   任务、不起 worker、不主动推送；间隔由 `modules/device/schedule.py` 的纯函数现算。

因此响应里的 `sleep_seconds` 是**相对秒数**，`next_url` 是拼好的**绝对地址**。不下发
`ETag` / `304` / `Cache-Control`：项目政策明确不接受设备端缓存。
"""
import asyncio
import datetime
import importlib
import inspect
import json
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from modules.errors.errors import (
    AccessDeniedError, AuthError, NotFoundError, ParamError, RenderError, error_response,
)
from modules.utils import plog
from modules.utils.client_ip import client_ip
from modules.utils.timezone import utc_now_iso

router = APIRouter(prefix='/device')

# hw_uid 是设备自报的硬件指纹（芯片 MAC 派生后哈希）。限制字符集不是为了安全，
# 而是防止把任意长文本塞进唯一索引与日志。
_HW_UID_RE = re.compile(r'[A-Za-z0-9:_\-]{4,128}')
_GROUP_PARAM_KEYS = ('rotate', 'invert', 'cmode')


# ======================== 请求解析 ========================

async def _body(request):
    """安全解析 JSON 请求体；非 dict（含解析失败）一律当空字典"""
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _text(body, key, limit=128):
    value = body.get(key)
    return '' if value is None else str(value).strip()[:limit]


def _int_field(body, key, default=0):
    value = body.get(key)
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dimension(body, key):
    """屏幕宽/高：非负且给一个上限，脏值不该让渲染端算出天文数字的图"""
    return max(0, min(_int_field(body, key, 0), 4096))


def _firmware(request):
    return (request.headers.get('X-Device-Firmware') or '').strip()[:64]


def _hw_uid(body):
    """取设备硬件指纹：**按原样校验，不先截断**。

    若先 `[:128]` 再匹配，一个 200 字符的脏输入会被悄悄截成合法值落库；长度约束
    本就写在正则里（4-128），先校验就不必再截。
    """
    raw = body.get('hw_uid')
    value = '' if raw is None else str(raw).strip()
    if not _HW_UID_RE.fullmatch(value):
        raise ParamError('hw_uid 不合法（4-128 位字母 / 数字 / 冒号 / 连字符 / 下划线）')
    return value


def _loads(raw):
    """JSON 列 → dict；坏值当空字典，一条脏数据不该把取图链路打挂"""
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


async def _rate(scope):
    """按作用域记一次限流；被拒时返回统一 429 响应，否则 None。

    已鉴权的取图按 `device:<id>` 计数，register / pair 这类未鉴权入口按来源 IP 计数：
    既不占属主账号的 evkey 配额，也不与同 NAT 下的其它设备共用额度。
    """
    from modules.utils.rate_limiter import check_scoped
    limit = int(getattr(config, 'DEVICE_RATE_PER_MINUTE', 20) or 0)
    allowed, _ = await check_scoped(f'device:{scope}', limit, 60)
    if not allowed:
        return error_response('设备请求过于频繁，请稍后再试', 429)
    return None


# ======================== 鉴权与权限 ========================

async def _authenticate(request):
    """按 `X-Device-Token` 取设备档案；失败抛 401 / 403。

    令牌在库里只存 sha256（无盐，见 store.hash_device_token），因此可以直接按哈希查设备；
    命中后再用 `hmac.compare_digest` 复核一次，与账号密码同一套定长比较口径。
    """
    from modules.device import store
    token = (request.headers.get('X-Device-Token')
             or request.query_params.get('device_token') or '').strip()
    if not token:
        raise AuthError('缺少设备令牌 X-Device-Token')
    row = await asyncio.to_thread(store.get_device_by_token_hash, store.hash_device_token(token))
    if row is None or not store.verify_device_token(row, token):
        raise AuthError('设备令牌无效')
    if not int(row.get('enabled') or 0):
        raise AccessDeniedError('设备已被禁用')
    return row


async def _account_context(device_row):
    """设备所属账号与用户组；未配对（account_id 为空）→ `(None, None)`。

    `get_account_by_id` 自带 `enabled = 1` 过滤：账号被禁用后设备随之停摆，
    不必再单独判一次。
    """
    account_id = device_row.get('account_id')
    if not account_id:
        return None, None
    from modules.database.accounts import get_account_by_id
    account = await asyncio.to_thread(get_account_by_id, account_id)
    if not account:
        raise AccessDeniedError('设备所属账号已被禁用或删除')
    return int(account_id), account.get('group_id')


def _check_render_access(request, plugin_name, route_path, group_id, img_format=None,
                         explicit_params=()):
    """路由内自校验：中间件对 `/device/**` 整体绕过，这里逐项补齐同口径判断。

    与 `plugin_disable_middleware` 保持一致的几点：插件未启用 / 路由被禁用 / 用户组
    无权访问一律拒绝；判定异常必须 fail-closed（宁可误拒也不放行）。
    """
    states = getattr(request.app.state, 'plugin_states', {}) or {}
    if states.get(plugin_name) is not True:
        raise AccessDeniedError(f'插件 {plugin_name} 当前不可用')
    disabled_routes = getattr(request.app.state, 'disabled_routes', set()) or set()
    if route_path in disabled_routes:
        raise AccessDeniedError(f'路由 {route_path} 已禁用')
    if group_id is not None:
        from modules.database.access import (
            check_group_param_access, check_user_plugin_access, check_user_route_access)
        if not check_user_plugin_access(group_id, plugin_name):
            raise AccessDeniedError(f'用户组无权访问插件 {plugin_name}')
        if not check_user_route_access(group_id, route_path):
            raise AccessDeniedError(f'用户组无权访问路由 {route_path}')
        for key in explicit_params:
            if not check_group_param_access(group_id, key):
                raise AccessDeniedError(f'用户组禁止使用{key}参数')
    if img_format:
        from modules.generate_views.image_output import check_format_allowed
        check_format_allowed(img_format, group_id)


# ======================== 渲染项 ========================

def _task_query(task_row, device_row):
    """渲染项 → `resolve_view_params` 用的查询字典。

    设备只 GET `next_url`、不带任何查询参数：参数一律由渲染项（后台配置）决定，
    否则同一台设备两次请求会拿到不同的图，预渲染缓存键也永远不稳定。
    """
    from modules.device.store import load_task_params
    query = load_task_params(task_row)
    query['size'] = str(task_row.get('size') or '')
    fmt = str(device_row.get('format') or '')
    if fmt:
        query['format'] = fmt
    return query


def _explicit_group_params(query):
    """渲染项里显式写了的 rotate / invert / cmode（要按用户组参数开关复核）"""
    return [k for k in _GROUP_PARAM_KEYS if query.get(k) not in (None, '')]


def _task_info(task_row, device_row):
    from modules.device.store import load_task_params
    return {
        'name': str(task_row.get('name') or ''),
        'plugin': str(task_row.get('plugin_name') or ''),
        'route_path': str(task_row.get('route_path') or ''),
        'kind': str(task_row.get('route_kind') or 'view'),
        'size': str(task_row.get('size') or ''),
        'format': str(device_row.get('format') or ''),
        'params': load_task_params(task_row),
    }


async def _render(request, plugin_name, kind, size, params, img_format, group_id, account_id):
    """实时渲染：与 `auto_view_routes.make_view_endpoint` 同一套流程（同一份 `save_image`）。

    不共用那个函数是因为它的入参是 HTTP 查询参数，而设备侧的参数来自渲染项；但「取模
    块 → 并发信号量 → generate_image → save_image」的顺序必须一致，否则设备拿到的图
    与网页端同参数的图会不一致。
    """
    params = dict(params)
    mod_path = f'plugins.{plugin_name}.view.{kind}.{size}'
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        plog.exception(f'视图 {mod_path} 不存在')
        raise ParamError(f'视图 {mod_path} 不存在: {exc}')
    if not hasattr(mod, 'generate_image'):
        raise ParamError(f'视图 {mod_path} 未实现 generate_image')

    rotate = params.pop('rotate')
    invert = params.pop('invert')
    cmode = params.pop('cmode')
    params.pop('size')
    params.pop('fmt')

    from modules.app_core import get_render_semaphore
    from modules.generate_views import render_metrics
    from modules.generate_views.image_output import save_image
    # 并发额度记在属主账号上：同一账号下网页端与多台设备共用一份上限，
    # 设备刷图不会绕过账号自己的并发保护。
    sem = await get_render_semaphore(request.app, group_id, account_id)
    try:
        async with sem:
            render_metrics.mark_start()
            started = time.perf_counter()
            try:
                if inspect.iscoroutinefunction(mod.generate_image):
                    img = await mod.generate_image(
                        rotate=rotate, invert=invert, cmode=cmode, **params)
                else:
                    # 同步 generate_image 是纯 CPU 的 Pillow 绘制，直接调用会独占事件循环
                    img = await asyncio.to_thread(
                        mod.generate_image, rotate=rotate, invert=invert, cmode=cmode, **params)
            finally:
                render_metrics.mark_end((time.perf_counter() - started) * 1000)
    except (ParamError, AccessDeniedError):
        raise
    except Exception as exc:
        plog.exception(f'设备取图渲染失败: {exc}')
        raise RenderError(f'图片生成失败: {exc}')
    return await asyncio.to_thread(
        save_image, img, img_format, [plugin_name, kind, size], group_id=group_id)


# ======================== 端点 ========================

@router.post('/register')
async def device_register(request: Request):
    """设备首次上电自报身份与屏幕参数，换取「是否需要配对」。

    幂等：同一个 hw_uid 反复注册只是更新屏幕参数与固件版本，不产生新档案。
    """
    limited = await _rate('ip:' + client_ip(request))
    if limited is not None:
        return limited
    body = await _body(request)
    hw_uid = _hw_uid(body)

    from modules.device import store
    fields = {
        'model': _text(body, 'model', 64),
        'width': _dimension(body, 'width'),
        'height': _dimension(body, 'height'),
        'palette': _text(body, 'palette', 16) or 'bw',
        'firmware': _text(body, 'firmware', 64),
    }
    device = await asyncio.to_thread(store.get_device_by_hw_uid, hw_uid)
    if device is None:
        await asyncio.to_thread(store.create_device, None, hw_uid, **fields)
        device = await asyncio.to_thread(store.get_device_by_hw_uid, hw_uid)
    else:
        # 屏幕参数以设备自报为准：固件换了屏 / 改了分辨率，这里跟着更新
        await asyncio.to_thread(store.update_device, device['id'], **fields)

    bound = bool(device.get('account_id')) and bool(device.get('token_hash'))
    return {
        'success': True,
        'device_uid': str(device['id']),
        'pair_required': not bound,
        'server_time': utc_now_iso(),
    }


@router.post('/pair/request')
async def device_pair_request(request: Request):
    """申请一个配对会话，返回 `pair_id` + `pair_code`。

    配对码是 8 位短码，画在墨水屏上、由用户敲进网页。evkey **可选**：

    - 不带 evkey → 会话 `account_id` 为空：设备只拿到码，要等用户在网页「我的设备」
      输入该码完成认领，归属才定下来（见 `/admin/api/my/devices/claim`）；
    - 带 evkey → 保留原有的「设备侧一次走完」行为，逐字不变（老固件不受影响）。

    两条路径共用同一张会话表与同一个 `/device/pair` 换令牌流程，差别只在
    `account_id` 是否为空。
    """
    limited = await _rate('ip:' + client_ip(request))
    if limited is not None:
        return limited
    evkey = (request.headers.get('evkey') or request.query_params.get('evkey') or '').strip()
    account_id = None
    if evkey:
        from modules.database.accounts import get_account_by_evkey
        account = await asyncio.to_thread(get_account_by_evkey, evkey)
        if not account:
            raise AuthError('无效的 evkey，用户不存在或已禁用')
        account_id = account['id']

    body = await _body(request)
    hw_uid = _hw_uid(body)

    from modules.device import store
    ttl = int(getattr(config, 'DEVICE_PAIR_TTL_SECONDS', 600) or 0)
    payload = {
        'model': _text(body, 'model', 64),
        'width': _dimension(body, 'width'),
        'height': _dimension(body, 'height'),
        'palette': _text(body, 'palette', 16) or 'bw',
        'firmware': _text(body, 'firmware', 64),
    }
    pair_id, pair_code = await asyncio.to_thread(
        store.create_pairing, hw_uid, payload, account_id, ttl)
    expires_at = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(seconds=ttl)).isoformat().replace('+00:00', 'Z')
    return {
        'success': True,
        'pair_id': pair_id,
        'pair_code': store.format_pair_code(pair_code),
        'expires_at': expires_at,
    }


@router.post('/pair')
async def device_pair(request: Request):
    """凭 `pair_id` + `pair_code` 换设备令牌（明文令牌只在这里出现一次）。

    三种结果，固件按 `state` 字段判定，**不去解析文案**：

    - `202` + `state='pending_confirmation'` → 会话还没被账号认领，睡 `retry_after`
      秒后带同样的 `pair_id` / `pair_code` 重投；
    - `200` + `state='paired'` + `token` → 拿到令牌，落库转去取图；
    - `4xx`（码错 / 过期 / 作废）→ 重新 `/device/pair/request` 出一次新码。
    """
    limited = await _rate('ip:' + client_ip(request))
    if limited is not None:
        return limited
    body = await _body(request)
    pair_id = _text(body, 'pair_id', 128)
    pair_code = _text(body, 'pair_code', 32)
    if not pair_id or not pair_code:
        raise ParamError('缺少 pair_id 或 pair_code')

    from modules.device import store
    pairing = await asyncio.to_thread(store.get_pairing, pair_id)
    if pairing is None:
        raise NotFoundError('配对会话不存在')
    if pairing.get('status') != 'pending':
        raise AccessDeniedError('该配对会话已使用或已失效')
    if store.is_pairing_expired(pairing):
        await asyncio.to_thread(store.set_pairing_status, pair_id, 'expired')
        raise AccessDeniedError('配对码已过期，请重新发起配对')
    if not store.verify_pairing_code(pairing, pair_code):
        attempts = await asyncio.to_thread(store.record_pairing_attempt, pair_id)
        max_attempts = int(getattr(config, 'DEVICE_PAIR_MAX_ATTEMPTS', 5) or 0)
        if max_attempts > 0 and attempts >= max_attempts:
            await asyncio.to_thread(store.set_pairing_status, pair_id, 'rejected')
            raise AccessDeniedError('配对码错误次数过多，该会话已作废')
        raise AccessDeniedError('配对码不正确')

    # 会话还没归属账号（设备侧出码、等用户在网页输入配对码）：不绑定、不签发令牌。
    # 用 202 表示「已受理、稍后再来」——既不是拿到令牌，也不是请求有错。码校验已经过了，
    # 所以这里**不消耗 attempts**：等认领不该把设备的重投次数耗光。
    if not pairing.get('account_id'):
        return JSONResponse({
            'success': False,
            'state': 'pending_confirmation',
            'message': '等待用户在网页输入配对码完成认领',
            'retry_after': 5,
            'pair_id': pair_id,
            'server_time': utc_now_iso(),
        }, status_code=202)

    account_id = pairing.get('account_id')
    hw_uid = str(pairing.get('hw_uid') or '')
    payload = _loads(pairing.get('payload_json'))
    # 认领时已经按 hw_uid 预绑过设备行，优先用它；没有（带 evkey 的一次性配对、或设备
    # 换过码但档案已存在）再按 hw_uid 找，最后才新建。
    device = None
    if pairing.get('device_id'):
        device = await asyncio.to_thread(store.get_device, pairing['device_id'])
    if device is None:
        device = await asyncio.to_thread(store.get_device_by_hw_uid, hw_uid)
    if device is None:
        device_id = await asyncio.to_thread(
            store.create_device, account_id, hw_uid,
            payload.get('model', ''), payload.get('width', 0), payload.get('height', 0),
            payload.get('palette') or 'bw', '', payload.get('firmware', ''))
        device = await asyncio.to_thread(store.get_device, device_id)
    else:
        # 重新配对 / 设备恢复出厂后重来：覆盖屏幕参数与归属账号
        await asyncio.to_thread(
            store.update_device, device['id'], account_id=account_id,
            model=payload.get('model', ''), width=payload.get('width', 0),
            height=payload.get('height', 0), palette=payload.get('palette') or 'bw',
            firmware=payload.get('firmware', ''))
        device = await asyncio.to_thread(store.get_device, device['id'])

    # 名额在**真正绑定**的这一刻校验：放在 pair/request 会让「配额已满」多绕一轮，
    # 放在这里则是权威判定点，且 re-pair 自身设备不会被自己的名额挡住。
    if account_id:
        denied = await _enforce_device_quota(account_id, hw_uid)
        if denied is not None:
            raise AccessDeniedError(denied)

    token = store.new_device_token()
    await asyncio.to_thread(store.set_device_token, device['id'], token)
    await asyncio.to_thread(store.set_pairing_status, pair_id, 'paired', device['id'])

    from modules.device.schedule import build_next_url
    # 配对完成后 last_seen_at 仍为空 → 间隔算出 0，设备立刻取第一张图（见 schedule 模块）
    return {
        'success': True,
        'state': 'paired',
        'token': token,
        'device_id': device['id'],
        'size': str((await asyncio.to_thread(store.current_device_task, device['id'])
                     or {}).get('size') or ''),
        'sleep_seconds': 0,
        'next_url': build_next_url(request, device),
        'server_time': utc_now_iso(),
    }


async def _enforce_device_quota(account_id, hw_uid):
    """用户组设备名额校验；超额时返回提示文案，否则 None。

    判定已下沉到 `store.device_quota_error`：账号面「输入配对码认领」要用同一份口径，
    两处各写一遍必然走偏。这里只保留事件循环里的异步包装。
    """
    from modules.device import store
    return await asyncio.to_thread(store.device_quota_error, account_id, hw_uid)


@router.get('/status')
async def device_status(request: Request):
    """设备问「现在显示什么、下次什么时候回来」——纯查询，不产生图"""
    device = await _authenticate(request)
    limited = await _rate(f'd{device["id"]}')
    if limited is not None:
        return limited
    account_id, group_id = await _account_context(device)

    from modules.device import store
    from modules.device.schedule import build_next_url, compute_sleep_seconds
    # 先算间隔再打心跳：首次回连 last_seen_at 为空 → 0，设备立刻去取第一张图；
    # 若反过来先打心跳，首次就会拿到一整段间隔、白等一轮才拿到首图。
    sleep_seconds = compute_sleep_seconds(device)
    await asyncio.to_thread(store.touch_device, device['id'], 'status',
                            '', client_ip(request), _firmware(request))

    task = None
    if account_id:
        task = await asyncio.to_thread(store.current_device_task, device['id'])
    return {
        'success': True,
        'device_id': device['id'],
        'task': _task_info(task, device) if task else None,
        'sleep_seconds': sleep_seconds,
        'next_url': build_next_url(request, device),
        'server_time': utc_now_iso(),
    }


@router.get('/image')
async def device_image(request: Request):
    """取图：返回图片字节，间隔与下次地址放在响应头里。

    响应头（而不是 JSON 包体）是刻意的：固件直接用 body 当位图流写屏，不必先解析 JSON
    再取 base64，省一次解码与一份内存。
    """
    device = await _authenticate(request)
    limited = await _rate(f'd{device["id"]}')
    if limited is not None:
        return limited
    account_id, group_id = await _account_context(device)

    from modules.device import store
    from modules.device.schedule import build_next_url, compute_sleep_seconds
    task = await asyncio.to_thread(store.current_device_task, device['id']) if account_id else None
    if task is None:
        # 没有可渲染项：把原因记进档案（面板能看到），用 404 让固件明确区分
        # 「还没配」与「渲染失败」，而不是拿一张空白图当成功。
        await asyncio.to_thread(store.touch_device, device['id'], 'no-task',
                                '该设备还没有配置渲染项', client_ip(request), _firmware(request))
        raise NotFoundError('该设备还没有配置渲染项')

    if str(task.get('route_kind') or 'view') != 'view':
        raise ParamError('该渲染项不是视图类型，无法取图')
    plugin_name = str(task.get('plugin_name') or '')
    route_path = str(task.get('route_path') or '')
    size = str(task.get('size') or '')
    if not plugin_name or not route_path or not size:
        raise ParamError('渲染项配置不完整（缺插件 / 路由 / 尺寸）')
    kind = route_path.rstrip('/').split('/')[-1]

    query = _task_query(task, device)
    plugin_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), f'../../plugins/{plugin_name}'))
    from modules.prerender.params import resolve_view_params
    params = resolve_view_params(plugin_name, plugin_dir, size, query)
    img_format = params['fmt']
    _check_render_access(request, plugin_name, route_path, group_id, img_format,
                         _explicit_group_params(query))

    from modules.prerender import store as prerender_store
    # 定时预渲染命中则直接复用成品图：设备侧与网页端共用同一份缓存键，
    # 不会出现「网页端命中、设备端却实时渲染」的双份开销。
    response = await prerender_store.try_serve(
        request, plugin_name, route_path, params, 'view', group_id)

    try:
        if response is None:
            response = await _render(request, plugin_name, kind, size, params,
                                     img_format, group_id, account_id)
    except Exception as exc:
        await asyncio.to_thread(store.touch_device, device['id'], 'error',
                                str(exc)[:200], client_ip(request), _firmware(request))
        raise

    # 打完心跳再算间隔：这次取图已经完成，下次该等满一个间隔，而不是又立刻来（忙轮询）
    await asyncio.to_thread(store.touch_device, device['id'], 'ok',
                            '', client_ip(request), _firmware(request))
    sleep_seconds = compute_sleep_seconds(dict(device, last_seen_at=utc_now_iso()))

    response.headers['X-Device-Sleep'] = str(sleep_seconds)
    response.headers['X-Device-Next-Url'] = build_next_url(request, device)
    response.headers['X-Device-Now'] = utc_now_iso()
    return response
