"""i18n 注册表：键 → 文案，按语言取表。

只做「取词」这一件事：不引入第三方库、不拆 `.po`/`.mo`、不做复数与性别规则。
语言解析优先级：面板配置 `LANG` → 请求头 `Accept-Language` → `DEFAULT_LANG`。

面板配置走的是 `config.LANG`：`config_store.apply_overrides()` 会把库里存的值
`setattr` 回 `config`，所以这里读到的就是面板上选的那一项，改完即热生效、不必重启。
"""
import json
import re

from modules.i18n.catalog_en import CATALOG as _EN
from modules.i18n.catalog_zh import CATALOG as _ZH

DEFAULT_LANG = 'zh-CN'
SUPPORTED_LANGS = ('zh-CN', 'en')
_CATALOGS = {'zh-CN': _ZH, 'en': _EN}

# 骨架里的取词标记：`{{T:nav.overview}}`。只认键名字符，避免误吞页面里别的 `{{...}}` 占位符
_T_RE = re.compile(r'\{\{T:([A-Za-z0-9_.]+)\}\}')


def normalize_lang(value):
    """把语言标识收敛成受支持的两种之一；识别不了返回 None。

    `auto` / 空值也返回 None：面板上的「跟随浏览器」不是一个语言，而是要落到
    Accept-Language 上，调用方据此继续往下找。
    """
    if value is None:
        return None
    v = str(value).strip().lower().replace('_', '-')
    if not v or v == 'auto':
        return None
    if v == 'zh' or v.startswith('zh-'):
        return 'zh-CN'
    if v == 'en' or v.startswith('en-'):
        return 'en'
    return None


def from_accept_language(header):
    """从 `Accept-Language` 里挑 q 值最高的受支持语言；没有则返回 None。

    不做 RFC 4647 的完整匹配（lookup/filtering）：只有两种语言，按前缀归类足够。
    q 缺失按 1.0 处理，解析失败的整体按 0（排到最后），这样畸形头不会顶掉正常项。
    """
    if not header:
        return None
    items = []
    for idx, part in enumerate(str(header).split(',')):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(';')
        q = 1.0
        for p in params.split(';'):
            k, _, val = p.strip().partition('=')
            if k.strip().lower() == 'q':
                try:
                    q = float(val)
                except ValueError:
                    q = 0.0
        items.append((-q, idx, normalize_lang(tag)))
    for _, _, lang in sorted(items):
        if lang:
            return lang
    return None


def current_lang(accept_language=None):
    """当前请求该用哪种语言。"""
    configured = None
    try:
        import config
        configured = getattr(config, 'LANG', None)
    except Exception:
        configured = None
    return normalize_lang(configured) or from_accept_language(accept_language) or DEFAULT_LANG


def lang_of(request):
    """一次请求该用哪种语言。接口层用（页面层在 `page_routes` 里另有同口径的取法）。

    面板配置优先、其次请求头——与 `current_lang` 同一套优先级，这里只是把
    「从 request 里取请求头」这一步收成一处，免得每个端点各写一遍。
    """
    try:
        header = request.headers.get('accept-language')
    except Exception:
        header = None
    return current_lang(header)


def t_req(request, key, **fmt):
    """接口里取词：按当前请求的语言翻。没有 request 可用时（后台线程、定时任务）
    直接用 `t(key, lang)`，不要把 request 传成 None 假装能翻。"""
    return t(key, lang_of(request), **fmt)


def t(key, lang=None, **fmt):
    """取词。缺键回落中文，再缺就把键名原样返回（宁可露出键名，也不显示空白）。

    `fmt` 里的 `{name}` 占位符做简单替换：只支持具名参数，不做格式化语法
    （文案里出现 `{}` 或 `{0}` 时不该让整页渲染炸掉）。
    """
    cat = _CATALOGS.get(lang) or _ZH
    text = cat.get(key)
    if text is None:
        text = _ZH.get(key, key)
    if fmt:
        text = re.sub(r'\{(\w+)\}', lambda m: str(fmt.get(m.group(1), m.group(0))), text)
    return text


def translate_html(html, lang):
    """把骨架里的 `{{T:键}}` 标记替换成对应语言的文案。"""
    if '{{T:' not in html:
        return html
    return _T_RE.sub(lambda m: t(m.group(1), lang), html)


def json_catalog(lang, keys=None):
    """把注册表序列化给前端，注入 `<script type="application/json">`。

    前端 JS 侧的通用文案（提示 / 分页条 / 确认框）在同一份表里取词，两边不会各写一套。
    `keys` 给定时只序列化这几个键：面板页在注入前会扫出该页真正用到的键，一页用不到整份
    表时就只带该页的子集（管理面板要大半、登录/注册/控制台只要一小半）。缺的键不写进结果，
    取词时照旧回落到 `T()` 的第二参数。
    `<` 转成 `\\u003c`：JSON 里是合法转义，但能保证数据里万一出现 `</script>`
    也不会把宿主脚本标签提前闭合。
    """
    cat = _CATALOGS.get(lang) or _ZH
    if keys is not None:
        cat = {k: v for k, v in cat.items() if k in keys}
    return json.dumps(cat, ensure_ascii=False, sort_keys=True).replace('<', '\\u003c')