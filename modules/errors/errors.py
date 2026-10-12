from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from modules.utils import plog


class NotFoundError(Exception):
    pass


class AuthError(Exception):
    pass


class AccessDeniedError(Exception):
    pass


class ParamError(Exception):
    pass


class RenderError(Exception):
    """视图渲染失败：插件抛异常、上游取数失败、编码失败等。

    与 `ParamError` 的分界在责任方——参数写错是调用方的问题（400，属正常流量），
    渲染失败是服务端自己的问题。日志与统计里只有 5xx（含本类）才算「错误」，
    因此这里必须是 500，不能沿用历史上「兜底包成 ParamError」的写法。
    """



def error_response(message, status_code, code=None, headers=None, extra=None):
    """统一错误响应体 `{success: False, message, code}`。

    全站唯一错误出口：异常处理器、中间件与管理 API 全部从这里构造。
    历史遗留的 `{'error': ...}` 已清除，前端只认这一套字段。

    extra 用于附加诊断字段（目前只有 dev 模式的 500 会带 request_id）；
    保持单一出口，避免另起一份 JSONResponse 让字段与转义规则走样。
    """
    content = {
        'success': False,
        'message': str(message),
        'code': status_code if code is None else code,
    }
    if extra:
        content.update(extra)
    return JSONResponse(status_code=status_code, content=content, headers=headers)


async def not_found_error_handler(request: Request, exc: NotFoundError):
    return error_response(exc, 404)


async def param_error_handler(request: Request, exc: ParamError):
    plog.exception(f'参数错误: {exc}')
    return error_response(exc, 400)


async def render_error_handler(request: Request, exc: RenderError):
    # 消息照常回给调用方：渲染失败的原因（上游超时 / 密钥失效）对排障是有效信息，
    # 而这条路径本身已在鉴权之后，不构成对未授权访客的信息泄露
    plog.exception(f'图片渲染失败: {exc}')
    return error_response(exc, 500)


async def auth_error_handler(request: Request, exc: AuthError):
    return error_response(exc, 401)


async def access_denied_error_handler(request: Request, exc: AccessDeniedError):
    return error_response(exc, 403)


async def http_exception_handler(request: Request, exc: HTTPException):
    return error_response(exc.detail, exc.status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response('请求参数校验失败', 422)


async def general_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, 'request_id', '')
    plog.exception(f'未处理异常 [req={rid}]' if rid else '未处理异常')
    if getattr(request.app.state, 'mode', '') == 'dev':
        # 开发模式暴露异常类型与消息便于调试；request_id 只在 dev 附带，生产不外泄内部标识
        return error_response(f'{type(exc).__name__}: {exc}', 500,
                              extra={'request_id': rid} if rid else None)
    return error_response('服务器内部错误', 500)


def register_error_handlers(app):
    app.add_exception_handler(NotFoundError, not_found_error_handler)
    app.add_exception_handler(ParamError, param_error_handler)
    app.add_exception_handler(RenderError, render_error_handler)
    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(AccessDeniedError, access_denied_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)