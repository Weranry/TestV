"""面板页的统一渲染出口（取词 + 共享 UI 注入 + 语言包注入 + no-store）。

原先这两个函数长在 `modules/admin/page_routes.py` 里。登录/注册/找回密码三个页面迁到
`/login` / `/register` / `/reset-password`（不再走 `/admin` 前缀）之后，新旧两处都要用同一份
渲染逻辑，故提到这里由双方共用：渲染口径只有一处，不会出现「某个出口漏了取词、页面留着
未替换的 `{{T:...}}`」。
"""
import re

from fastapi.responses import HTMLResponse

from modules.admin_ui.shared_ui import apply_shared_ui

# 一页要用到哪些键，从三处扫：骨架里的 `{{T:…}}` 标记、脚本里的 `T('…')` 调用，
# 以及 JS 侧以字符串字面量存放的键表（CRUMBS / USER_SUB_CRUMBS / TEST_MODES / _QUOTA_* 等
# ——这些键写成 `['day','user.period_day','每天']` 由 `T(表[code],兜底)` 动态取，只看 `T(`
# 调用会整批漏掉，正是「英文界面混进中文兜底」的高发处）。三样合起来才是该页完整的键集，
# 只把这份子集注入 `#i18n-data` 即可；万一扫漏，取词仍会回落到 `T()` 的第二参数。
_MARKER_RE = re.compile(r'\{\{T:([A-Za-z0-9_.]+)\}\}')
_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])T\('([A-Za-z0-9_.]+)'")
_LITERAL_RE = re.compile(r"['\"]([a-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+)['\"]")

# 页面是启动时装配好的常量字符串，键集按内容哈希缓存，免得每次导航重扫三百多 KB
_page_keys_cache = {}


def _page_keys(html):
    h = hash(html)
    keys = _page_keys_cache.get(h)
    if keys is None:
        keys = frozenset(
            set(_MARKER_RE.findall(html)) | set(_CALL_RE.findall(html))
            | set(_LITERAL_RE.findall(html)))
        _page_keys_cache[h] = keys
    return keys


# 面板页面一律 no-store：HTML 是**进程启动时装配**的（内联 CSS/JS 与这一版代码一一对应），
# 浏览器缓存住旧副本时，服务端升级完看到的还是旧界面，而且前后端会错位（接口已改、页面
# 还按老字段渲染，表现为「改了没生效 / 一片空白」）。页面不大，每次导航重取一次即可。
_NO_STORE = {'Cache-Control': 'no-store'}


def panel_html(html, lang=None):
    """所有面板页（含登录/注册/找回密码/首次改密/用户控制台）的统一出口。

    取词、共享 UI 注入与语言包的注入都在这里做一次：这几件事都按同一份「当前语言」
    计算，分散到各端点里写会漏掉某个出口（漏掉的那个页面会留着未替换的 `{{T:...}}`）。
    """
    from modules.i18n.registry import current_lang, json_catalog, translate_html
    lang = lang or current_lang()
    # 先注入共享 UI 再取词：ACCOUNT_CARDS 等片段是在 apply_shared_ui 里填进来的，
    # 若先取词，这些片段里的 `{{T:...}}` 就赶不上这一趟，会原样吐给浏览器
    html = apply_shared_ui(html)
    # 键集要在 translate_html 之前扫：它会把 `{{T:…}}` 标记就地替换掉，之后就扫不到了
    keys = _page_keys(html)
    html = translate_html(html, lang)
    html = html.replace('{{LANG}}', lang).replace('{{I18N}}', json_catalog(lang, keys))
    return HTMLResponse(content=html, headers=_NO_STORE)


def req_lang(request):
    """未登录页也要按浏览器语言给文案，此时只看请求头（面板配置优先级在 current_lang 内）"""
    from modules.i18n.registry import current_lang
    return current_lang(request.headers.get('accept-language'))


__all__ = ['panel_html', 'req_lang']