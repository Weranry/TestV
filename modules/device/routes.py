"""设备面 HTTP 契约：注册 / 配对 / 状态 / 取图。

与全站其它路由有两处根本不同，写在这里免得后来者踩坑：

1. `/device/**` 在 `config.AUTH_WHITELIST` 里整体放行——设备自带 `X-Device-Token`，
   不属于任何账号的 evkey，走全站鉴权中间件会被当成未登录访客直接 401。
   **放行不等于不设防**：本文件内每条路由都自己复核令牌、插件/路由启用状态与用户组
   权限（口径对照 [app_core.plugin_disable_middleware](file:///d:/Desktop/einkViewsEvo/modules/app_core.py#L295-L334)）。
2. **计时器跑在设备上**。这里只回答「睡多少秒」和「下次请求哪个 URL」，服务端不存排期
   任务、不起 worker、不主动推送；间隔由 `modules/device/schedule.py` 的纯函数现算。

因此响应里的 `sleep_seconds` 是**相对秒数**，`next_url` 是拼好的**绝对地址**。
取图支持 `ETag` / `If-None-Match` / `304`：图片字节没变时不传 body，只回睡眠指令；
渲染失败时回退设备上一张成功图，避免墨水屏停在错误页或空白。
"""
import asyncio
import datetime
import hashlib
import importlib
import inspect
import json
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

import config
from modules.errors.errors import (
    AccessDeniedError, AuthError, NotFoundError, ParamError, RenderError, error_response,
)
from modules.i18n.registry import t_req
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
        raise ParamError('api.err_hw_uid')
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


async def _rate(request, scope):
    """按作用域记一次频次限流；被拒时返回统一 429 响应，否则 None。

    已鉴权的取图按 `device:<id>` 计数，register / pair 这类未鉴权入口按来源 IP 计数：
    分钟级速率不与同 NAT 下的其它设备或属主账号共用。注意这里只负责**频次**；
    属主账号的「计次额度」由取图链路单独调用 `consume_account_quota` 消耗。
    """
    from modules.utils.rate_limiter import check_scoped
    limit = int(getattr(config, 'DEVICE_RATE_PER_MINUTE', 20) or 0)
    allowed, _ = await check_scoped(f'device:{scope}', limit, 60)
    if not allowed:
        return error_response(t_req(request, 'device.err_rate_limited'), 429)
    return None


# ======================== 协议辅助 ========================

_IDEMPOTENCY_RE = re.compile(r'[A-Za-z0-9._:\-]{8,128}')
_IMAGE_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
}


def _time_fields():
    """设备校时字段：ISO 时间给面板/日志看，epoch 给固件直接算偏移。"""
    return {'server_time': utc_now_iso(), 'server_epoch': int(time.time())}


def _idempotency_key(request):
    """可选的幂等键；格式不对直接 400，避免把任意长文本写进主键。"""
    raw = (request.headers.get('Idempotency-Key') or '').strip()
    if not raw:
        return ''
    if not _IDEMPOTENCY_RE.fullmatch(raw):
        raise ParamError('device.err_idem_key')
    return raw


def _etag_for(body):
    return '"' + hashlib.sha256(body or b'').hexdigest() + '"'


def _etag_matches(request, etag):
    """支持逗号分隔的多个 ETag、弱校验前缀与 `*`。"""
    header = (request.headers.get('If-None-Match') or '').strip()
    if not header or not etag:
        return False
    if header == '*':
        return True
    for item in header.split(','):
        candidate = item.strip()
        if candidate.startswith('W/'):
            candidate = candidate[2:].strip()
        if candidate == etag:
            return True
    return False


def _image_headers(sleep_seconds, next_url, etag='', fallback=False):
    headers = {
        'X-Device-Sleep': str(int(sleep_seconds)),
        'X-Device-Next-Url': next_url,
        'X-Device-Now': utc_now_iso(),
        'X-Device-Epoch': str(int(time.time())),
        'Cache-Control': 'no-cache',
    }
    if etag:
        headers['ETag'] = etag
    if fallback:
        headers['X-Device-Fallback'] = '1'
    return headers


def _read_file(path):
    """同步读文件（放到线程池里跑）；用 with 保证句柄关闭，避免测试里的资源告警。"""
    with open(path, 'rb') as fh:
        return fh.read()


def _last_image_dir():
    """最近图片与数据库同目录，备份/迁移时跟着一起走；内存库退到用户目录。"""
    from modules.database.core import db_path
    path = db_path()
    if not path or path == ':memory:':
        base = os.path.join(os.path.expanduser('~'), '.einkviews')
    else:
        base = os.path.dirname(os.path.abspath(path))
    return os.path.join(base, 'device_last')


async def _persist_last_image(device, response, etag):
    """把本张成功图落到磁盘；内容没变就不重写，减少磁盘/闪存磨损。"""
    body = getattr(response, 'body', b'') or b''
    if not body:
        return
    old_path = str(device.get('last_image_path') or '')
    if etag == str(device.get('last_image_etag') or '') and old_path and os.path.isfile(old_path):
        return
    mime = (response.headers.get('content-type') or 'application/octet-stream').split(';')[0].strip()
    ext = _IMAGE_EXT.get(mime, 'bin')
    name = f'device-{device["id"]}.{ext}'
    path = os.path.join(_last_image_dir(), name)

    def write():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as fh:
            fh.write(body)
        os.replace(tmp, path)
        from modules.device import store
        store.set_device_last_image(device['id'], path, etag, mime, name)

    try:
        await asyncio.to_thread(write)
    except Exception as exc:
        # 回退图只是增强项，写失败不能影响本次取图
        plog.exception(f'设备最近图片落盘失败: {exc}')


async def _serve_last_image(request, device, error_text):
    """渲染失败时回退上一张成功图；没有可回退文件返回 None。"""
    path = str(device.get('last_image_path') or '')
    if not path or not os.path.isfile(path):
        return None
    try:
        body = await asyncio.to_thread(_read_file, path)
    except OSError as exc:
        plog.exception(f'设备回退图读取失败: {exc}')
        return None
    from modules.device import store
    from modules.device.schedule import build_next_url, compute_sleep_seconds, jitter_sleep_seconds
    await asyncio.to_thread(store.touch_device, device['id'], 'fallback',
                            str(error_text)[:200], client_ip(request), _firmware(request))
    sleep_seconds = jitter_sleep_seconds(
        compute_sleep_seconds(dict(device, last_seen_at=utc_now_iso())))
    etag = str(device.get('last_image_etag') or '') or _etag_for(body)
    headers = _image_headers(sleep_seconds, build_next_url(request, device), etag, fallback=True)
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=str(device.get('last_image_mime') or 'application/octet-stream'),
                    headers=headers)


# ======================== 鉴权与权限 ========================

async def _authenticate(request):
    """按 `X-Device-Token` 取设备档案；失败抛 401 / 403。

    令牌在库里只存 sha256（无盐，见 store.hash_device_token），因此可以直接按哈希查设备；
    命中后再用 `hmac.compare_digest` 复核一次，与账号密码同一套定长比较口径。
    """
    from modules.device import store
    # 令牌**只认请求头**：query 里的令牌会进代理日志、Referer 与浏览器历史，
    # 设备侧没有理由再走 URL 传凭据。老固件若仍拼 ?device_token= 会被当成未鉴权。
    token = (request.headers.get('X-Device-Token') or '').strip()
    if not token:
        raise AuthError('device.err_token_missing')
    row = await asyncio.to_thread(store.get_device_by_token_hash, store.hash_device_token(token))
    if row is None or not store.verify_device_token(row, token):
        raise AuthError('device.err_token_invalid')
    if not int(row.get('enabled') or 0):
        raise AccessDeniedError('device.err_disabled')
    return row


async def _account_context(request, device_row):
    """设备所属账号与用户组；未配对（account_id 为空）→ `(None, None)`。

    `get_account_by_id` 自带 `enabled = 1` 过滤：账号被禁用后设备随之停摆，
    不必再单独判一次。顺手把属主写进 `request.state`，请求日志据此把设备取图/状态
    归到所属账号下（设备请求没有登录态，auth 中间件拿不到 user）。
    """
    account_id = device_row.get('account_id')
    if not account_id:
        return None, None
    from modules.database.accounts import get_account_by_id
    account = await asyncio.to_thread(get_account_by_id, account_id)
    if not account:
        raise AccessDeniedError('device.err_owner_gone')
    request.state.device_account_id = int(account_id)
    return int(account_id), account.get('group_id')


def _check_render_access(request, plugin_name, route_path, group_id, img_format=None,
                         explicit_params=()):
    """路由内自校验：中间件对 `/device/**` 整体绕过，这里逐项补齐同口径判断。

    与 `plugin_disable_middleware` 保持一致的几点：插件未启用 / 路由被禁用 / 用户组
    无权访问一律拒绝；判定异常必须 fail-closed（宁可误拒也不放行）。
    """
    states = getattr(request.app.state, 'plugin_states', {}) or {}
    if states.get(plugin_name) is not True:
        raise AccessDeniedError('device.err_plugin_off', plugin=plugin_name)
    disabled_routes = getattr(request.app.state, 'disabled_routes', set()) or set()
    if route_path in disabled_routes:
        raise AccessDeniedError('device.err_route_off', route=route_path)
    if group_id is not None:
        from modules.database.access import (
            check_group_param_access, check_user_plugin_access, check_user_route_access)
        if not check_user_plugin_access(group_id, plugin_name):
            raise AccessDeniedError('api.err_no_plugin', plugin=plugin_name)
        if not check_user_route_access(group_id, route_path):
            raise AccessDeniedError('api.err_no_route', route=route_path)
        for key in explicit_params:
            if not check_group_param_access(group_id, key):
                raise AccessDeniedError('api.err_group_param', key=key)
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
        raise ParamError('api.err_view_missing', view=mod_path, msg=exc)
    if not hasattr(mod, 'generate_image'):
        raise ParamError('api.err_view_no_gen', view=mod_path)

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
        raise RenderError('api.err_render_failed', msg=exc)
    return await asyncio.to_thread(
        save_image, img, img_format, [plugin_name, kind, size], group_id=group_id)


# ======================== 端点 ========================

@router.post('/register')
async def device_register(request: Request):
    """设备首次上电自报身份与屏幕参数，换取「是否需要配对」。

    幂等：同一个 hw_uid 反复注册只是更新屏幕参数与固件版本，不产生新档案。
    带 `Idempotency-Key` 时连响应一起复用：固件超时重投拿到的是同一份结果
    （尤其是 `device_uid`），不会在两侧产生两个「自认为注册成功」的分支。
    """
    limited = await _rate(request, 'ip:' + client_ip(request))
    if limited is not None:
        return limited
    body = await _body(request)
    hw_uid = _hw_uid(body)

    from modules.device import store
    idem_key = _idempotency_key(request)
    ttl = int(getattr(config, 'DEVICE_IDEMPOTENCY_TTL_SECONDS', 86400) or 0)
    # scope 带上 hw_uid：同一把幂等键被不同设备复用时应各自算数，不能互相顶掉
    scope = f'register:{hw_uid}'
    if idem_key:
        cached = await asyncio.to_thread(store.get_idempotent_response, idem_key, scope, ttl)
        if cached is not None:
            return cached

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
        # 屏幕参数以设备自报为准：固件换了屏 / 改了分辨率，这里跟着更新。
        # 老档案没有名字时补上 MAC（新档案在 create_device 里已经默认写入）
        if not str(device.get('name') or '').strip():
            fields['name'] = store.default_device_name(hw_uid)
        await asyncio.to_thread(store.update_device, device['id'], **fields)

    bound = bool(device.get('account_id')) and bool(device.get('token_hash'))
    payload = {
        'success': True,
        'device_uid': str(device['id']),
        'pair_required': not bound,
        **_time_fields(),
    }
    if idem_key:
        # 只缓存这份不含令牌的结果；重投时原样返回，设备侧的 device_uid 不会漂
        await asyncio.to_thread(store.save_idempotent_response, idem_key, scope, payload, ttl)
    return payload


@router.post('/pair/request')
async def device_pair_request(request: Request):
    """申请一个配对会话，返回 `pair_id` + `pair_code`。

    配对码是 8 位短码，画在墨水屏上、由用户敲进网页。evkey **可选**：

    - 不带 evkey → 会话 `account_id` 为空：设备只拿到码，要等用户在网页「我的设备」
      输入该码完成认领，归属才定下来（见 `/admin/api/my/devices/claim`）；
    - 带 evkey → 保留原有的「设备侧一次走完」行为，逐字不变（老固件不受影响）。

    两条路径共用同一张会话表与同一个 `/device/pair` 换令牌流程，差别只在
    `account_id` 是否为空。

    带 `Idempotency-Key` 时：同一台设备用同一把键重投，直接返回原来那条仍在有效期内的
    会话（`pair_id` / 码 / 过期时间都不变），不会因为固件超时重试堆出一串孤儿会话。
    """
    limited = await _rate(request, 'ip:' + client_ip(request))
    if limited is not None:
        return limited
    # evkey 只从请求头取：配对请求也走同一条规则，避免凭据出现在 URL 与访问日志里。
    # 旧固件仍拼 ?evkey=... 时只会退化成「无归属」的正常配对码，再走网页认领。
    evkey = (request.headers.get('evkey') or '').strip()
    account_id = None
    if evkey:
        from modules.database.accounts import get_account_by_evkey
        account = await asyncio.to_thread(get_account_by_evkey, evkey)
        if not account:
            raise AuthError('api.err_evkey_invalid')
        account_id = account['id']

    body = await _body(request)
    hw_uid = _hw_uid(body)
    idem_key = _idempotency_key(request)

    from modules.device import store
    if idem_key:
        existing = await asyncio.to_thread(store.get_pairing_by_idempotency, hw_uid, idem_key)
        if existing is not None:
            return {
                'success': True,
                'pair_id': existing['id'],
                'pair_code': store.format_pair_code(existing.get('pair_code')),
                'expires_at': existing.get('expires_at') or '',
                'reused': True,
                **_time_fields(),
            }

    ttl = int(getattr(config, 'DEVICE_PAIR_TTL_SECONDS', 600) or 0)
    payload = {
        'model': _text(body, 'model', 64),
        'width': _dimension(body, 'width'),
        'height': _dimension(body, 'height'),
        'palette': _text(body, 'palette', 16) or 'bw',
        'firmware': _text(body, 'firmware', 64),
    }
    pair_id, pair_code = await asyncio.to_thread(
        store.create_pairing, hw_uid, payload, account_id, ttl, idem_key)
    expires_at = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(seconds=ttl)).isoformat().replace('+00:00', 'Z')
    return {
        'success': True,
        'pair_id': pair_id,
        'pair_code': store.format_pair_code(pair_code),
        'expires_at': expires_at,
        **_time_fields(),
    }


@router.post('/pair')
async def device_pair(request: Request):
    """凭 `pair_id` + `pair_code` 换设备令牌（明文令牌只在这里出现一次）。

    三种结果，固件按 `state` 字段判定，**不去解析文案**：

    - `202` + `state='pending_confirmation'` → 会话还没被账号认领，睡 `retry_after`
      秒后带同样的 `pair_id` / `pair_code` 重投；
    - `200` + `state='paired'` + `token` → 拿到令牌，落库转去取图；
    - `4xx`（码错 / 过期 / 作废）→ 重新 `/device/pair/request` 出一次新码。

    幂等重试：带 `Idempotency-Key` 且与会话上记录的一致时，「已经 paired、但固件没收到
    令牌就超时重投」不会落到 `err_pair_used`，而是复核配对码后重新签发一枚令牌
    （`reissued=True`）。旧令牌同时作废——令牌只在响应里出现一次，丢了只能重发。
    """
    limited = await _rate(request, 'ip:' + client_ip(request))
    if limited is not None:
        return limited
    body = await _body(request)
    pair_id = _text(body, 'pair_id', 128)
    pair_code = _text(body, 'pair_code', 32)
    if not pair_id or not pair_code:
        raise ParamError('device.err_pair_params')
    idem_key = _idempotency_key(request)

    from modules.device import store
    pairing = await asyncio.to_thread(store.get_pairing, pair_id)
    if pairing is None:
        raise NotFoundError('device.err_pair_missing')
    if pairing.get('status') == 'paired':
        # 只有「同一把幂等键」的重投才允许补发，且必须仍过码校验：
        # 否则拿到过 pair_id 的人都能在配对完成后无限重签令牌。
        if not idem_key or idem_key != str(pairing.get('idempotency_key') or ''):
            raise AccessDeniedError('device.err_pair_used')
        if not store.verify_pairing_code(pairing, pair_code):
            raise AccessDeniedError('device.err_pair_bad')
        device = await asyncio.to_thread(store.get_device, pairing.get('device_id'))
        if device is None:
            raise NotFoundError('device.err_pair_missing')
        token = store.new_device_token()
        await asyncio.to_thread(store.set_device_token, device['id'], token)
        from modules.device.schedule import build_next_url
        return {
            'success': True,
            'state': 'paired',
            'token': token,
            'device_id': device['id'],
            'size': str((await asyncio.to_thread(store.current_device_task, device['id'])
                         or {}).get('size') or ''),
            'sleep_seconds': 0,
            'next_url': build_next_url(request, device),
            'reissued': True,
            **_time_fields(),
        }
    if pairing.get('status') != 'pending':
        raise AccessDeniedError('device.err_pair_used')
    if store.is_pairing_expired(pairing):
        await asyncio.to_thread(store.set_pairing_status, pair_id, 'expired')
        raise AccessDeniedError('device.err_pair_expired')
    if not store.verify_pairing_code(pairing, pair_code):
        attempts = await asyncio.to_thread(store.record_pairing_attempt, pair_id)
        max_attempts = int(getattr(config, 'DEVICE_PAIR_MAX_ATTEMPTS', 5) or 0)
        if max_attempts > 0 and attempts >= max_attempts:
            await asyncio.to_thread(store.set_pairing_status, pair_id, 'rejected')
            raise AccessDeniedError('device.err_pair_locked')
        raise AccessDeniedError('device.err_pair_bad')

    # 会话还没归属账号（设备侧出码、等用户在网页输入配对码）：不绑定、不签发令牌。
    # 用 202 表示「已受理、稍后再来」——既不是拿到令牌，也不是请求有错。码校验已经过了，
    # 所以这里**不消耗 attempts**：等认领不该把设备的重投次数耗光。
    if not pairing.get('account_id'):
        return JSONResponse({
            'success': False,
            'state': 'pending_confirmation',
            'message': t_req(request, 'device.pair_wait_claim'),
            'retry_after': 5,
            'pair_id': pair_id,
            **_time_fields(),
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
            raise AccessDeniedError(denied[0], **denied[1])

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
        **_time_fields(),
    }


async def _enforce_device_quota(account_id, hw_uid):
    """用户组设备名额校验；超额时返回 `(取词键, 格式化参数)`，否则 None。

    判定已下沉到 `store.device_quota_error`：账号面「输入配对码认领」要用同一份口径，
    两处各写一遍必然走偏。这里只做事件循环里的异步包装——取词交给异常处理器，
    `AccessDeniedError` 认键与参数，不必在这儿先翻一遍再让处理器翻第二遍。
    """
    from modules.device import store
    return await asyncio.to_thread(store.device_quota_error, account_id, hw_uid)


@router.get('/status')
async def device_status(request: Request):
    """设备问「现在显示什么、下次什么时候回来」——纯查询，不产生图"""
    device = await _authenticate(request)
    limited = await _rate(request, f'd{device["id"]}')
    if limited is not None:
        return limited
    account_id, group_id = await _account_context(request, device)

    from modules.device import store
    from modules.device.schedule import build_next_url, compute_sleep_seconds, jitter_sleep_seconds
    # 先算间隔再打心跳：首次回连 last_seen_at 为空 → 0，设备立刻去取第一张图；
    # 若反过来先打心跳，首次就会拿到一整段间隔、白等一轮才拿到首图。
    # 抖动的目的只是打散「大量设备整点同时醒」，不改变平均间隔。
    sleep_seconds = jitter_sleep_seconds(compute_sleep_seconds(device))
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
        **_time_fields(),
    }


@router.post('/telemetry')
async def device_telemetry(request: Request):
    """设备上报遥测：电量 / 信号 / 唤醒耗时 / 累计刷新次数。

    与取图链路解耦：固件可以在唤醒后先报遥测、再决定是否取图（或只报不进图）。
    数值一律钳在合理区间后落库——脏值只影响展示，不该让详情页出现 99999 mV 这类
    明显不可能是真实读数的数据。
    """
    device = await _authenticate(request)
    limited = await _rate(request, f'd{device["id"]}')
    if limited is not None:
        return limited
    if device.get('account_id'):
        request.state.device_account_id = int(device['account_id'])
    body = await _body(request)

    def clamp(key, low, high):
        return max(low, min(_int_field(body, key, 0), high))

    battery_mv = clamp('battery_mv', 0, 10000)
    rssi = clamp('rssi', -200, 0)
    wake_ms = clamp('wake_ms', 0, 600000)
    refresh_count = clamp('refresh_count', 0, 2000000000)
    firmware = _text(body, 'firmware', 64) or _firmware(request)

    from modules.device import store
    await asyncio.to_thread(
        store.save_device_telemetry, device['id'], battery_mv, rssi, wake_ms,
        refresh_count, firmware)
    # 只留最近 200 条：遥测是高频上报，历史表不能无限长（设备详情只展示最近几条）
    await asyncio.to_thread(store.trim_device_telemetry, device['id'], 200)
    return {
        'success': True,
        'device_id': device['id'],
        **_time_fields(),
    }


@router.get('/image')
async def device_image(request: Request):
    """取图：返回图片字节，间隔与下次地址放在响应头里。

    响应头（而不是 JSON 包体）是刻意的：固件直接用 body 当位图流写屏，不必先解析 JSON
    再取 base64，省一次解码与一份内存。

    - 成功响应对**最终字节**算强 ETag；设备带 `If-None-Match` 命中时回 `304` 且不带 body，
      睡眠 / 下次地址等头照常给——省下的是射频时间与 Flash 写入。
    - 渲染失败（非权限/参数错误）时回退这台设备上一张成功图，并带 `X-Device-Fallback: 1`：
      墨水屏停在旧内容，远好于停在错误页或空白。
    """
    device = await _authenticate(request)
    limited = await _rate(request, f'd{device["id"]}')
    if limited is not None:
        return limited
    account_id, group_id = await _account_context(request, device)

    from modules.device import store
    from modules.device.schedule import (
        build_next_url, compute_sleep_seconds, jitter_sleep_seconds)
    task = await asyncio.to_thread(store.current_device_task, device['id']) if account_id else None
    if task is None:
        # 没有可渲染项：把原因记进档案（面板能看到），用 404 让固件明确区分
        # 「还没配」与「渲染失败」，而不是拿一张空白图当成功。
        await asyncio.to_thread(store.touch_device, device['id'], 'no-task',
                                '该设备还没有配置渲染项', client_ip(request), _firmware(request))
        raise NotFoundError('api.err_no_item')

    if str(task.get('route_kind') or 'view') != 'view':
        raise ParamError('api.err_not_view_item')
    plugin_name = str(task.get('plugin_name') or '')
    route_path = str(task.get('route_path') or '')
    size = str(task.get('size') or '')
    if not plugin_name or not route_path or not size:
        raise ParamError('api.err_item_incomplete')
    kind = route_path.rstrip('/').split('/')[-1]

    # 总日志里要能看出「设备这次请求的是哪个插件的哪条路由」：/device/image 只是入口，
    # 真正渲染的内容由渲染项决定，这里把路由交给请求日志中间件
    request.state.log_route = route_path

    query = _task_query(task, device)
    plugin_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), f'../../plugins/{plugin_name}'))
    from modules.prerender.params import resolve_view_params
    params = resolve_view_params(plugin_name, plugin_dir, size, query)
    img_format = params['fmt']
    _check_render_access(request, plugin_name, route_path, group_id, img_format,
                         _explicit_group_params(query))

    # 设备刷新同样计入属主账号的计次额度：`/device/**` 绕过了全局限流中间件，这里按账号
    # 单独补一次消耗。放在权限校验之后、取图之前——预渲染缓存命中同样算一次刷新，
    # 而配错权限 / 没配渲染项不会白吃额度。
    from modules.utils.rate_limiter import consume_account_quota
    allowed, quota_msg, _limit = await consume_account_quota(group_id, account_id)
    if not allowed:
        # 额度耗尽与渲染失败分开打点：设备侧 429 在后台看得到原因，也方便判断是配置问题
        # 还是额度真的用完了
        from modules.utils import metrics as _metrics
        _metrics.incr('device_quota_rejected')
        await asyncio.to_thread(store.touch_device, device['id'], 'error',
                                quota_msg[:200], client_ip(request), _firmware(request))
        return error_response(quota_msg, 429)

    from modules.prerender import store as prerender_store
    # 定时预渲染命中则直接复用成品图：设备侧与网页端共用同一份缓存键，
    # 不会出现「网页端命中、设备端却实时渲染」的双份开销。
    try:
        response = await prerender_store.try_serve(
            request, plugin_name, route_path, params, 'view', group_id)
        if response is None:
            response = await _render(request, plugin_name, kind, size, params,
                                     img_format, group_id, account_id)
    except (ParamError, AccessDeniedError):
        # 权限 / 参数问题是配置错误，拿旧图顶上等于把问题藏起来：
        # 固件与面板都必须看到这次失败。
        await asyncio.to_thread(store.touch_device, device['id'], 'error',
                                '渲染被拒绝（权限或参数）', client_ip(request), _firmware(request))
        raise
    except Exception as exc:
        # 渲染失败 → 回退上一张成功图；没有可回退的才把错误抛给固件
        fallback = await _serve_last_image(request, device, exc)
        if fallback is not None:
            return fallback
        await asyncio.to_thread(store.touch_device, device['id'], 'error',
                                str(exc)[:200], client_ip(request), _firmware(request))
        raise

    # 打完心跳再算间隔：这次取图已经完成，下次该等满一个间隔，而不是又立刻来（忙轮询）
    await asyncio.to_thread(store.touch_device, device['id'], 'ok',
                            '', client_ip(request), _firmware(request))
    # 多视图轮播：**取图成功后**才推进游标——渲染失败 / 权限拒绝时下次还取同一项，
    # 否则一次坏配置会让设备在几张图之间来回跳过，问题反而看不清。
    await asyncio.to_thread(store.advance_device_carousel, device['id'])
    sleep_seconds = jitter_sleep_seconds(
        compute_sleep_seconds(dict(device, last_seen_at=utc_now_iso())))

    body = getattr(response, 'body', b'') or b''
    if not body:
        # 非内存响应（理论上不会出现在这两条链路）就不参与 ETag/回退，只补睡眠头
        response.headers['X-Device-Sleep'] = str(sleep_seconds)
        response.headers['X-Device-Next-Url'] = build_next_url(request, device)
        response.headers['X-Device-Now'] = utc_now_iso()
        response.headers['X-Device-Epoch'] = str(int(time.time()))
        return response

    etag = _etag_for(body)
    await _persist_last_image(device, response, etag)
    headers = _image_headers(sleep_seconds, build_next_url(request, device), etag)
    if _etag_matches(request, etag):
        # 304：不带 body，但睡眠指令必须照给，否则固件只能猜一个间隔
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return response
