"""把面板页里的内联 CSS/JS 抽成同源静态资源。

页面 HTML 仍然是 `no-store`（骨架与这一版代码一一对应，缓存旧副本会出现「后端已改、
前端还按老字段渲染」），但样式与脚本的**内容**只随代码版本变化，可以长缓存：

- 启动期就把各模板经 `apply_shared_ui` 展开后抽一遍，按内容 sha256 前 16 位命名
  `/admin/assets/app.<digest>.css|js`。多实例部署下每个实例都算得出同一份 digest，
  不会出现「页面指向了 A 实例有、B 实例没有的资源」。
- 渲染期只做「取内容 → 算 digest → 命中就换成一个标签」，命中不了就保持内联：
  宁可这一页大一点，也不让用户拿到 404 的空样式 / 空脚本。
- 随请求变化的值（时区、可用分页、刷新间隔）由模板里的 `<script data-inline>` 同步声明，
  不参与抽取，否则 digest 会随每次导航变化、缓存等于没开。

`<head>` 里的脚本（主题初始化）与 `type="application/json"` 数据块（语言包）不抽取：
前者必须同步执行以免闪白，后者本来就是给同页脚本读的内联数据。
"""
import hashlib
import re

# 样式块可能带属性（media 等），整块抽走，换成等价的 <link>
_STYLE_RE = re.compile(r'<style\b[^>]*>(.*?)</style>', re.S | re.I)
# 脚本块统一在这里匹配，是否需要抽取由 _should_extract 判定
_SCRIPT_RE = re.compile(r'<script\b([^>]*)>(.*?)</script>', re.S | re.I)
# 资源名白名单：拒绝任意路径穿越，也拒绝 .map / .json 之类没注册过的后缀
_ASSET_NAME_RE = re.compile(r'^app\.[0-9a-f]{16}\.(?:css|js)$')

_ASSET_PREFIX = '/admin/assets/'
_CSS_TYPE = 'text/css; charset=utf-8'
_JS_TYPE = 'application/javascript; charset=utf-8'

# name -> (content_type, text)
_bundles = {}


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _asset_name(text, kind):
    return 'app.%s.%s' % (_digest(text), kind)


def _register(text, kind):
    name = _asset_name(text, kind)
    _bundles[name] = (_CSS_TYPE if kind == 'css' else _JS_TYPE, text)
    return name


def get_bundle(name):
    """按资源名取 (content_type, text)；不存在返回 None（路由据此回 404）。"""
    return _bundles.get(name)


def is_asset_name(name):
    return bool(_ASSET_NAME_RE.match(name or ''))


def _script_is_extractable(attrs, body):
    low = attrs.lower()
    if 'src=' in low or 'type=' in low or 'data-inline' in low:
        return False
    return bool(body.strip())


def _register_from_html(html):
    """把一份展开后的模板里所有可抽取内容登记进 _bundles（启动期预计算用）。"""
    for match in _STYLE_RE.finditer(html):
        _register(match.group(1), 'css')
    head_end = html.lower().find('</head>')
    for match in _SCRIPT_RE.finditer(html):
        if match.start() < head_end:
            continue
        if not _script_is_extractable(match.group(1), match.group(2)):
            continue
        _register(match.group(2), 'js')


def externalize(html):
    """把命中的样式 / 脚本换成长缓存的外链，未命中的保持内联。"""
    def style_sub(match):
        text = match.group(1)
        name = _asset_name(text, 'css')
        if name not in _bundles:
            return match.group(0)
        return '<link rel="stylesheet" href="%s%s">' % (_ASSET_PREFIX, name)

    def script_sub(match):
        body = match.group(2)
        if not _script_is_extractable(match.group(1), body):
            return match.group(0)
        name = _asset_name(body, 'js')
        if name not in _bundles:
            return match.group(0)
        return '<script src="%s%s"></script>' % (_ASSET_PREFIX, name)

    # 顺序很重要：先把样式换成很短的 <link>，再按**替换后**的位置切 </head>。
    # 用替换前的下标切会把正文前段（正好是样式块那三十多 KB）误判成 head，整段脚本留在内联。
    out = _STYLE_RE.sub(style_sub, html)
    cut = out.lower().find('</head>')
    if cut < 0:
        return _SCRIPT_RE.sub(script_sub, out)
    cut += len('</head>')
    # head 里的主题初始化必须同步执行，只有 body 段参与脚本外链
    return out[:cut] + _SCRIPT_RE.sub(script_sub, out[cut:])


def _precompute():
    """启动期把每个页面的资源算好：渲染期只查表，多实例之间也不会各自算出不同的名字。"""
    from modules.admin_ui.assemble import ADMIN_HTML
    from modules.admin_ui.shared_ui import apply_shared_ui
    from modules.admin_ui.templates import (
        CHPASS_HTML, EXPLORE_HTML, LOGIN_HTML, REGISTER_HTML, RESET_HTML, USER_HTML)

    for template in (ADMIN_HTML, USER_HTML, LOGIN_HTML, CHPASS_HTML,
                     REGISTER_HTML, RESET_HTML, EXPLORE_HTML):
        _register_from_html(apply_shared_ui(template))


_precompute()


__all__ = ['externalize', 'get_bundle', 'is_asset_name']
