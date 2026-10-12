"""请求体大小上限的统一判定。

原先只有备份上传自己做了「先看 Content-Length、再按实读字节兜底」的双重判定，
其余接口没有任何上限：一个超大 POST 就能把进程内存吃掉。判定收到这一份里，
全局中间件（见 app_core）与备份上传共用，避免同一条规则两处各写一套、改一处漏一处。

口径沿用项目约定：**0 = 不限**。
"""
from starlette.datastructures import Headers

MB = 1024 * 1024


def limit_bytes(mb):
    """配置值（MB）→ 字节上限。0 / 负数 / 非法值一律 0（= 不限）。"""
    try:
        n = int(float(mb))
    except (TypeError, ValueError):
        return 0
    return n * MB if n > 0 else 0


def declared_length(headers):
    """请求头声明的 body 字节数；没有该头或值非法时返回 None。

    分块传输（chunked）没有 Content-Length，只能靠实读字节兜底。
    """
    raw = headers.get('content-length') if headers else None
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def exceeds(limit, declared=None, actual=None):
    """是否超出上限；limit <= 0 恒为 False（不限）。

    declared 用于读体之前提前拒绝，actual 用于读体过程中/之后兜底。
    """
    if limit <= 0:
        return False
    if declared is not None and declared > limit:
        return True
    return actual is not None and actual > limit


def reject_message(limit, label='请求体'):
    """统一的超限文案（limit 需 > 0）"""
    return f'{label}超过 {limit // MB} MB 上限'


class BodyLimitMiddleware:
    """请求体大小上限中间件（纯 ASGI）。

    为什么不用 `@app.middleware('http')`：BaseHTTPMiddleware 下只有 `request.body()`
    能把读到的 body 缓存下来回放给下游，用 `request.stream()` 会让下游拿到空 body
    （见 starlette/middleware/base.py 里 _CachedRequest 的说明），没法「边收边判」。
    在 ASGI 层包一层 receive 才能做到「超限即中断」，同时不影响正常请求。

    上限每请求从 `config.MAX_REQUEST_BODY_MB` 现取：面板改完配置当场生效，
    不在装配期定死（与限流中间件读配置的方式一致）。
    """

    def __init__(self, app, skip_prefixes=(), skip_paths=()):
        self.app = app
        self.skip_prefixes = tuple(skip_prefixes or ())
        self.skip_paths = tuple(skip_paths or ())

    @staticmethod
    def _limit():
        import config
        return limit_bytes(getattr(config, 'MAX_REQUEST_BODY_MB', 0))

    def _skipped(self, scope):
        """放行判定：无 body 的方法与白名单路径不受这项限制"""
        if scope.get('method') in ('GET', 'HEAD', 'OPTIONS'):
            return True
        path = scope.get('path') or ''
        return path in self.skip_paths or path.startswith(self.skip_prefixes)

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or self._skipped(scope):
            return await self.app(scope, receive, send)
        limit = self._limit()
        if limit <= 0:
            return await self.app(scope, receive, send)

        # 第一道：Content-Length 能提前拒的都在读 body 之前拒掉。
        # 等 body 全进内存再判，这个上限就等于没有——大文件上传一定会带这个头。
        if exceeds(limit, declared=declared_length(Headers(scope=scope))):
            return await self._reject(scope, receive, send, limit)

        # 第二道：没有 Content-Length（分块传输）时按累计字节兜底
        total = 0
        rejected = False

        async def counted_receive():
            nonlocal total, rejected
            message = await receive()
            if message.get('type') == 'http.request' and not rejected:
                total += len(message.get('body') or b'')
                if exceeds(limit, actual=total):
                    # 自己回 413，再给下游一个 disconnect：读体方会抛 ClientDisconnect
                    # 并放弃这次请求，超出的部分不会再往里读
                    rejected = True
                    await self._reject(scope, receive, send, limit)
                    return {'type': 'http.disconnect'}
            return message

        async def guarded_send(message):
            # 被中断的下游可能还要吐 500，一律丢弃：响应已经发出去了，
            # 再来一次 http.response.start 会让 ASGI 服务器直接报错
            if not rejected:
                await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except Exception:
            # 被自己中断而抛出的异常（ClientDisconnect / 下游的收尾异常）到此为止
            if not rejected:
                raise

    @staticmethod
    async def _reject(scope, receive, send, limit):
        from modules.errors.errors import error_response
        await error_response(reject_message(limit), 413)(scope, receive, send)