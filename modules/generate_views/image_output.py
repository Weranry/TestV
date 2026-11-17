import io
from fastapi.responses import Response
import config
import modules.config_store as _config_store
from modules.errors.errors import ParamError, AccessDeniedError
from modules.generate_views.array_formats import (
    array_formats, canonical_format, is_array_format, pack_array)

_FORMAT_REGISTRY = {
    'jpg':  {'pillow': 'JPEG', 'mime': 'image/jpeg',  'ext': '.jpg'},
    'jpeg': {'pillow': 'JPEG', 'mime': 'image/jpeg',  'ext': '.jpg'},
    'png':  {'pillow': 'PNG',  'mime': 'image/png',   'ext': '.png'},
    'bmp':  {'pillow': 'BMP',  'mime': 'image/bmp',   'ext': '.bmp'},
    'webp': {'pillow': 'WEBP', 'mime': 'image/webp',  'ext': '.webp'},
    'tiff': {'pillow': 'TIFF', 'mime': 'image/tiff',  'ext': '.tiff'},
    'gif':  {'pillow': 'GIF',  'mime': 'image/gif',   'ext': '.gif'},
}


def _format_save_kwargs(fmt_key):
    """输出参数每次现从 config 取，保证管理面板改完即时生效"""
    if fmt_key in ('jpg', 'jpeg'):
        return {'quality': config.DEFAULT_JPEG_QUALITY, 'subsampling': 0, 'progressive': False}
    if fmt_key == 'webp':
        return {'quality': config.DEFAULT_WEBP_QUALITY}
    if fmt_key == 'png':
        return {'compress_level': config.DEFAULT_PNG_COMPRESS_LEVEL}
    if fmt_key == 'tiff':
        return {'compression': config.DEFAULT_TIFF_COMPRESSION}
    return {}


def image_to_raw_array(img):
    """黑白原始位流（`array` 格式，等同 `bwarray`）"""
    return pack_array(img, 'array')


def _edge_cache_headers():
    """Vercel CDN 边缘缓存头，仅在 vercel 模式下返回非空。

    用 Vercel 独占的 `Vercel-CDN-Cache-Control`：它优先级最高，且**不会被返回给
    客户端**，所以 ESP32 与浏览器完全看不到，不会触发设备端缓存。

    命中边缘缓存时函数根本不执行，鉴权、限流、日志、统计都不会发生。这是刻意取舍：
    Vercel 侧的 evkey 只用来挡住恶意请求，而命中缓存的请求本就不消耗函数算力。
    """
    if _config_store.get_mode() != 'vercel':
        return {}
    try:
        ttl = int(config.EDGE_CACHE_TTL or 0)
    except (TypeError, ValueError):
        ttl = 0
    if ttl <= 0:
        return {}
    return {'Vercel-CDN-Cache-Control': f'public, max-age={ttl}'}


def check_format_allowed(img_format, group_id=None):
    """格式黑名单 + 用户组 `format_<fmt>` 权限校验。

    命中预渲染缓存时也必须重跑一遍：图是之前生成的，但组权限可能在那之后被改掉。

    别名先归一到正式名（`bwarray` → `array`）再查黑名单与权限键，否则
    「禁了 `format_array` 却能改用 `bwarray` 绕开」。
    """
    img_format = canonical_format(img_format)
    if img_format in config.IMAGE_FORMAT_BLACKLIST:
        raise ParamError(f'{img_format.upper()} 格式已被框架层面禁止生成')
    if group_id is not None:
        from modules.database.access import check_group_param_access
        if not check_group_param_access(group_id, f'format_{img_format}'):
            raise AccessDeniedError(
                f'{img_format.upper()} 格式生成已被用户组禁止，请联系管理员'
            )


def ensure_format_supported(img_format):
    """格式是否在输出注册表内（数组格式族走位流打包，单独判定）"""
    if is_array_format(img_format) or img_format in _FORMAT_REGISTRY:
        return
    raise ParamError(f'不支持的输出格式: {img_format}，支持 ' + ', '.join(supported_formats()))


def supported_formats():
    """合法的输出格式集合（管理面板的下拉/复选候选）。

    `jpeg` 是 `jpg` 的别名，不重复列出；数组格式族不在注册表里，从
    `array_formats()` 现取。候选必须从这里取，别在面板侧另抄一份字面量：
    注册表加一种格式、那边还会照旧拒绝。
    """
    return sorted(k for k in _FORMAT_REGISTRY if k != 'jpeg') + array_formats()


def build_image_bytes(img, img_format, name_parts):
    """渲染结果 → (内容字节, mime, 文件名, 原始位长或 None)

    预渲染把这份产物原样存库，命中时不再经过 Pillow。
    """
    if is_array_format(img_format):
        raw = pack_array(img, img_format)
        return raw, 'application/octet-stream', '_'.join(name_parts) + '.bin', len(raw)
    info = _FORMAT_REGISTRY[img_format]
    buf = io.BytesIO()
    img.save(buf, format=info['pillow'], **_format_save_kwargs(img_format))
    return buf.getvalue(), info['mime'], '_'.join(name_parts) + info['ext'], None


def build_response_from_bytes(content, mime, filename, raw_len=None):
    """由既有的字节产物构造响应（预渲染命中路径与实时渲染共用）

    图像已在内存里生成完毕，整体返回即可。禁止用 StreamingResponse 包 BytesIO：
    迭代 BytesIO 是按行(0x0A)切分而非按块，一张 JPEG 会被切成上百个小 chunk，
    每个 chunk 都要过一次 anyio 线程池，单请求凭空多出几十毫秒。
    """
    headers = {'Content-Disposition': f'inline; filename={filename}'}
    if raw_len is not None:
        headers['X-Raw-Bytes'] = str(raw_len)
    return Response(
        content=content,
        media_type=mime,
        headers={**headers, **_edge_cache_headers()},
    )


def save_image(img, img_format, name_parts, group_id=None):
    img_format = img_format.lower()
    check_format_allowed(img_format, group_id)
    ensure_format_supported(img_format)
    content, mime, filename, raw_len = build_image_bytes(img, img_format, name_parts)
    return build_response_from_bytes(content, mime, filename, raw_len)