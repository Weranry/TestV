import asyncio
import hmac
import os
import re
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

router = APIRouter()

# 存活探针只注册在本地链路（dev / prod）：Vercel 侧首页走边缘静态直出，
# 不需要也不应该再往 Serverless 函数里加端点，故单独一个 router 由 app_core 按模式挂载。
health_router = APIRouter()

PUBLIC_PAGES_DIR = os.path.join(os.path.dirname(__file__), '../../public/pages')
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), '../../public')

# index.html 本身是「Vercel 静态直出版」：那些随环境变化的文案/入口，在文件里存的是
# **Vercel 版本**，并用 `<!-- 名字:start -->…<!-- 名字:end -->` 锚点包起来。这样 Vercel 的
# @vercel/static 把它当静态文件直出也是正确的（不会有指向 /login 的死链）。
# 只有 dev/prod 才改写这些块：整块内容按 _LOCAL_BLOCKS 替换，锚点本身保留。
_BLOCK_RE = re.compile(r'<!--\s*(?P<name>[a-z][a-z0-9-]*):start\s*-->.*?<!--\s*(?P=name):end\s*-->', re.S)
_ADMIN_MODES = ('dev', 'prod')

# 本地（dev/prod）才存在的差异内容：键是锚点名，值是本地模式下要填进该块的内容。
# `admin-entry` / `nav-entry` 是首页唯一跟着语言走的文案（首页正文是英文直出），写成取词
# 标记、由 `render_index` 按当前语言替换；其余正文保持英文，不进文案表。
#
# 两条入口都只挂在本地模式：`/login` 与 `/explore` 这两个页面本身也只由 `app_core` 在
# is_local 分支里注册，Vercel 侧没有对应端点（首页走边缘静态直出）。块留空即「这条入口
# 不存在」，不会在静态版上留下一个点进去 404 的死链。
_LOCAL_BLOCKS = {
    'admin-entry': '&middot; <a href="/login">{{T:index.admin_entry}}</a>',
    'nav-entry': '&middot; <a href="/explore">{{T:index.nav_entry}}</a>',
    'env-note': 'eInkViews is working!',
}

# 「尚未完成初始化」提示：建库时写入的内置管理账号还在用公开的初始口令（admin/admin123）时，
# 大标题下的可变区块换成这条引导文案——那台机器上初始口令就是有效凭据，必须催着改掉。
# 改完密码（must_change_password 归零）后自动恢复常态文案（见 app_core 的 setup 门禁）。
_SETUP_NOTICE = (
    '尚未完成初始化：请用初始账号 <b>admin</b> / <b>admin123</b> '
    '登录 <a href="/login">管理面板</a> 并立即修改密码'
)


def _local_blocks(setup_required=False):
    """本地模式要填进锚点块的内容；setup_required 时把首页提示位换成初始化引导"""
    blocks = dict(_LOCAL_BLOCKS)
    if setup_required:
        blocks['env-note'] = f'<span class="setup-note">{_SETUP_NOTICE}</span>'
    return blocks


def _apply_local_blocks(html, blocks):
    """把本地模式的差异内容填进对应的锚点块；未登记名字的块原样保留"""
    def _repl(match):
        name = match.group('name')
        content = blocks.get(name)
        if content is None:
            return match.group(0)
        return f'<!-- {name}:start -->{content}<!-- {name}:end -->'

    return _BLOCK_RE.sub(_repl, html)


_INDEX_PATH = os.path.join(PUBLIC_PAGES_DIR, 'index.html')

# 首页是纯静态内容，按 mode 缓存改写结果：否则每个请求都要读盘一次再跑一遍正则。
# 用 mtime 做失效判定（只 stat 不读文件），改完 index.html 立刻生效、无需重启。
# 缓存键带上 setup_required：初始化前后的两份 HTML 同时留着，免去改密瞬间失效重读盘。
_index_cache = {}


def _load_index_html(mode, setup_required=False):
    mtime = os.path.getmtime(_INDEX_PATH)
    key = (mode, bool(setup_required))
    cached = _index_cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    with open(_INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()
    if mode in _ADMIN_MODES:
        html = _apply_local_blocks(html, _local_blocks(setup_required))
    _index_cache[key] = (mtime, html)
    return html


async def render_index(request: Request):
    """首页 HTML。初始化未完成（app.state.setup_required）时提示位换成引导文案。

    单独抽出来给 setup 门禁复用：拦在鉴权之前的那一层也要能返回同一份首页。

    取词放在缓存之外：`_index_cache` 里存的是带 `{{T:...}}` 标记的版本（按 mode / 初始化
    状态缓存），语言每次请求现算，免得语言一变就得清缓存。Vercel 侧块内没有标记，
    `translate_html` 会原样返回。
    """
    from modules.i18n.registry import current_lang, translate_html
    mode = getattr(request.app.state, 'mode', 'vercel')
    setup_required = bool(getattr(request.app.state, 'setup_required', False))
    html = await asyncio.to_thread(_load_index_html, mode, setup_required)
    lang = current_lang(request.headers.get('accept-language'))
    return HTMLResponse(content=translate_html(html, lang))


@router.get('/')
async def index(request: Request):
    return await render_index(request)


@health_router.get('/healthz')
async def healthz(request: Request):
    """存活探针：不碰数据库与缓存，只回运行模式与版本，便于外部监控区分部署。"""
    return JSONResponse({
        'success': True,
        'status': 'ok',
        'mode': getattr(request.app.state, 'mode', 'unknown'),
        'version': request.app.version,
    })


def _metrics_token_ok(request, token):
    """METRICS_TOKEN 非空时的校验：`?token=` 或 `Authorization: Bearer <token>`。

    定长比较：`!=` 在首个不同字符处短路，逐字节泄露令牌前缀。令牌是调用方可控的输入，
    非 ASCII 会直接抛 TypeError（compare_digest 不支持含非 ASCII 的 str），统一编 bytes。
    """
    provided = request.query_params.get('token') or ''
    if not provided:
        auth = request.headers.get('authorization') or ''
        if auth.lower().startswith('bearer '):
            provided = auth[7:].strip()
    if not provided:
        return False
    return hmac.compare_digest(provided.encode('utf-8'), token.encode('utf-8'))


@health_router.get('/metrics')
async def metrics(request: Request):
    """Prometheus 指标出口。

    与 /healthz 同挂 health_router → 只在本地链路存在，Vercel 侧不受影响；同样免鉴权、
    不吃限流额度、不记请求日志（三处白名单已同步登记），可放心被监控高频轮询。
    """
    try:
        import config
        token = str(getattr(config, 'METRICS_TOKEN', '') or '')
    except Exception:
        token = ''
    if token and not _metrics_token_ok(request, token):
        return Response(content='forbidden\n', status_code=403,
                        media_type='text/plain; charset=utf-8')

    from modules.utils import metrics as _metrics
    # 渲染里含两处读库（库文件大小、预渲染成品缓存条数），下放 worker 线程，
    # 别让一次监控轮询把事件循环占住
    body = await asyncio.to_thread(_metrics.render, request.app)
    return Response(content=body, media_type='text/plain; version=0.0.4; charset=utf-8')


@router.get('/favicon.ico')
async def favicon():
    return FileResponse(os.path.join(PUBLIC_DIR, 'favicon.ico'))