"""面板 / 用户控制台 / 认证页 / 访客导航页的全部前端片段，唯一来源是 `admin_ui/` 下的真实文件。

目录按类型分：`css/`、`js/`、`html/`；不属于这三类的散件（logo、主题初始化片段、
铃铛标记片段）统一放 `misc/`。
Python 侧不再保存任何 HTML/CSS/JS 代码：这里只负责把文件读成字符串，交给
`assemble.py`（面板装配）、`shared_ui.apply_shared_ui()`（共享件注入）与
`panel_render.panel_html()`（取词、外链化）。

改动约定：
  * 改界面 = 直接改对应目录下的文件，不再往 .py 里贴三引号字符串；
  * 新增片段 = 在对应目录加文件 + 这里加一行常量；
  * 文件用 UTF-8、保留原始换行（`newline=''`），装配结果与拆分前逐字节一致。

占位符（`{{T:...}}` / `{{SHARED_UI_CSS}}` / `{{I18N}}` 等）在文件里原样保留，
由渲染期统一替换，不要把运行时值写死进文件。
"""
import os

# admin_ui/ 目录本身：css / js / html / misc 都在它下面
UI_DIR = os.path.dirname(os.path.abspath(__file__))


def read_ui(name):
    """读 `admin_ui/<name>`（含子目录，如 `css/admin.css`）。缺失直接抛错，让问题在启动期暴露。"""
    with open(os.path.join(UI_DIR, name), 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


# ---- 面板外壳与分页脚本 ----
ADMIN_HEAD = read_ui('html/admin.head.html')
ADMIN_CSS = read_ui('css/admin.css')
ADMIN_BODY = read_ui('html/admin.body.html')
ADMIN_TAIL = read_ui('html/admin.tail.html')
ADMIN_JS_CORE = read_ui('js/admin.core.js')
ADMIN_JS_OVERVIEW = read_ui('js/admin.overview.js')
ADMIN_JS_PLUGINS = read_ui('js/admin.plugins.js')
ADMIN_JS_USERS = read_ui('js/admin.users.js')
ADMIN_JS_DEVICES = read_ui('js/admin.devices.js')
ADMIN_JS_LOGS = read_ui('js/admin.logs.js')
ADMIN_JS_CACHE = read_ui('js/admin.cache.js')
ADMIN_JS_STATS = read_ui('js/admin.stats.js')
ADMIN_JS_PRERENDER = read_ui('js/admin.prerender.js')
ADMIN_JS_CONFIG = read_ui('js/admin.config.js')
ADMIN_JS_ABOUT = read_ui('js/admin.about.js')
ADMIN_JS_BACKUP = read_ui('js/admin.backup.js')
ADMIN_JS_BOOT = read_ui('js/admin.boot.js')

# ---- 「我的」页（用户控制台与管理面板共用） ----
ACCOUNT_CSS = read_ui('css/account.css')
ACCOUNT_CARDS = read_ui('html/account.cards.html')
ACCOUNT_JS = read_ui('js/account.js')

# ---- 共享件（设计令牌 / 浮层 / 弹窗 / 铃铛 / logo） ----
THEME_TOKENS_CSS = read_ui('css/shared.tokens.css')
SHARED_UI_CSS = read_ui('css/shared.ui.css')
SHARED_UI_JS = read_ui('js/shared.ui.js')
THEME_INIT_JS = read_ui('misc/theme.init.html')
NOTIF_BELL = read_ui('misc/notif.bell.html')
LOGO_SVG = read_ui('misc/logo.svg')

# ---- 独立页面 ----
LOGIN_HTML = read_ui('html/login.html')
CHPASS_HTML = read_ui('html/chpass.html')
REGISTER_HTML = read_ui('html/register.html')
RESET_HTML = read_ui('html/reset.html')
USER_HTML = read_ui('html/user.html')
EXPLORE_HTML = read_ui('html/explore.html')
