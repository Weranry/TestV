"""文本响应的 gzip 压缩。

面板是单页 SSR（内联 CSS + JS 合计约 300KB 一个响应），/admin/api/* 的列表与统计
响应也不小。不压缩的话这些字节每次都在链路上原样走一遍。

**为什么不用 starlette 自带的 GZipMiddleware**：它按 minimum_size 一视同仁地压所有
够大的响应，包括设备端取回的 JPEG / PNG —— 这些格式本身已是压缩数据，再 gzip 一次
几乎没有体积收益，却要实打实付一遍 CPU（预渲染命中的价值正在于"不再付编码成本"），
在 Orange Pi 这类设备上尤其不划算。所以这里只压文本类响应，其余一律原样放行。

只在本地模式注册（与 BodyLimitMiddleware 一致）：Vercel 侧的内容压缩由平台负责，
那条链路不新增功能代码。
"""
import zlib

from starlette.datastructures import Headers, MutableHeaders

# 值得压缩的内容类型。图片 / 字体 / 音视频都是已压缩格式，不在其中。
_COMPRESSIBLE_TYPES = (
    'text/',
    'application/json',
    'application/javascript',
    'application/xml',
    'application/manifest+json',
    'image/svg+xml',
)

# 小于这个字节数不压：gzip 头尾加尾部校验本身就有几十字节，小响应压完可能更大
DEFAULT_MIN_SIZE = 1024


def accepts_gzip(headers):
    """请求是否接受 gzip。

    `q=0` 表示显式拒绝，必须排除；`q=0.5` 之类是"可接受但优先级低"，仍然算接受。
    """
    raw = (headers.get('accept-encoding') if headers else '') or ''
    for part in raw.split(','):
        token, _, params = part.strip().partition(';')
        if token.strip().lower() != 'gzip':
            continue
        quality = 1.0
        for item in params.split(';'):
            key, _, value = item.strip().partition('=')
            if key.strip().lower() == 'q':
                try:
                    quality = float(value)
                except (TypeError, ValueError):
                    quality = 1.0
        return quality > 0
    return False


def is_compressible(content_type):
    """内容类型是否属于"压了有意义"的文本族"""
    if not content_type:
        return False
    base = content_type.split(';', 1)[0].strip().lower()
    return any(base.startswith(prefix) for prefix in _COMPRESSIBLE_TYPES)


class GZipMiddleware:
    """纯 ASGI 的文本压缩中间件。

    在 ASGI 层做而不是 `@app.middleware('http')`：后者拿到的是封装好的响应对象，
    要压就得先把整个 body 读进内存（流式响应随之被破坏）；这里能按 message 增量压，
    只在最后一条 flush。

    minimum_size 与是否压缩每请求现算，不在装配期定死（与其它中间件一致）。
    """

    def __init__(self, app, minimum_size=DEFAULT_MIN_SIZE):
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or not accepts_gzip(Headers(scope=scope)):
            return await self.app(scope, receive, send)

        compress = False
        compressor = None

        async def send_wrapper(message):
            nonlocal compress, compressor
            kind = message.get('type')
            if kind == 'http.response.start':
                headers = MutableHeaders(scope=message)
                declared = headers.get('content-length')
                try:
                    declared = int(declared) if declared is not None else None
                except (TypeError, ValueError):
                    declared = None
                compress = (
                    # 已经被下游压过一次的不能再套一层
                    not headers.get('content-encoding')
                    and is_compressible(headers.get('content-type'))
                    and (declared is None or declared >= self.minimum_size)
                )
                if compress:
                    headers['content-encoding'] = 'gzip'
                    # 压缩后长度事先不可知：留着这个头，客户端会按原始长度截断响应
                    del headers['content-length']
                    # 同一个 URL 对"能压/不能压"的两类客户端响应不同，缓存必须分开
                    headers.add_vary_header('accept-encoding')
                    # wbits=31 = gzip 容器（不是裸 deflate）
                    compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
                await send(message)
                return
            if kind == 'http.response.body' and compress:
                body = message.get('body') or b''
                more = bool(message.get('more_body'))
                out = compressor.compress(body)
                if not more:
                    out += compressor.flush()
                elif not out:
                    # 这一段还没被压缩器吐出东西，发空包只会让客户端以为提前结束
                    return
                message = {'type': 'http.response.body', 'body': out, 'more_body': more}
            await send(message)

        await self.app(scope, receive, send_wrapper)