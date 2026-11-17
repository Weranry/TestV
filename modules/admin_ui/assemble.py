"""把 modules/admin_ui 下拆分的片段按原顺序拼回完整面板页 HTML。

切分是纯粹按行分区、不改动任何字符，因此拼回结果与拆分前的 ADMIN_HTML 逐字节相同。
"""
from modules.admin_ui.admin_shell import ADMIN_HEAD, ADMIN_CSS, ADMIN_BODY, ADMIN_TAIL
from modules.admin_ui.admin_js_core import ADMIN_JS_CORE
from modules.admin_ui.admin_js_overview import ADMIN_JS_OVERVIEW
from modules.admin_ui.admin_js_plugins import ADMIN_JS_PLUGINS
from modules.admin_ui.admin_js_users import ADMIN_JS_USERS
from modules.admin_ui.admin_js_logs import ADMIN_JS_LOGS
from modules.admin_ui.admin_js_cache import ADMIN_JS_CACHE
from modules.admin_ui.admin_js_stats import ADMIN_JS_STATS
from modules.admin_ui.admin_js_prerender import ADMIN_JS_PRERENDER
from modules.admin_ui.admin_js_config import ADMIN_JS_CONFIG
from modules.admin_ui.admin_js_about import ADMIN_JS_ABOUT
from modules.admin_ui.account_page import ACCOUNT_JS
from modules.admin_ui.admin_js_backup import ADMIN_JS_BACKUP
from modules.admin_ui.admin_js_boot import ADMIN_JS_BOOT

_ADMIN_JS = "\n".join([
    ADMIN_JS_CORE, ADMIN_JS_OVERVIEW, ADMIN_JS_PLUGINS, ADMIN_JS_USERS,
    ADMIN_JS_LOGS, ADMIN_JS_CACHE, ADMIN_JS_STATS, ADMIN_JS_PRERENDER,
    ADMIN_JS_CONFIG, ADMIN_JS_ABOUT, ACCOUNT_JS, ADMIN_JS_BACKUP, ADMIN_JS_BOOT,
])

ADMIN_HTML = "\n".join([ADMIN_HEAD, ADMIN_CSS, ADMIN_BODY, _ADMIN_JS, ADMIN_TAIL])
