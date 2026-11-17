"""把 `css/` / `js/` / `html/` 下的面板片段按固定顺序拼回完整面板页 HTML。

片段本身在 `modules/admin_ui/`（见 `templates.py`），这里只负责顺序：
外壳四段 → 各分页脚本。顺序有意义（脚本之间靠后定义的函数被前面的调用），
新增分页脚本要在这里登记，且放在依赖它的那一段之后、`ADMIN_JS_BOOT` 之前。
"""
from modules.admin_ui.templates import (
    ACCOUNT_JS, ADMIN_BODY, ADMIN_CSS, ADMIN_HEAD, ADMIN_JS_ABOUT, ADMIN_JS_BACKUP,
    ADMIN_JS_BOOT, ADMIN_JS_CACHE, ADMIN_JS_CONFIG, ADMIN_JS_CORE, ADMIN_JS_DEVICES,
    ADMIN_JS_LOGS, ADMIN_JS_OVERVIEW, ADMIN_JS_PLUGINS, ADMIN_JS_PRERENDER,
    ADMIN_JS_STATS, ADMIN_JS_USERS, ADMIN_TAIL)

_ADMIN_JS = "\n".join([
    ADMIN_JS_CORE, ADMIN_JS_OVERVIEW, ADMIN_JS_PLUGINS, ADMIN_JS_USERS, ADMIN_JS_DEVICES,
    ADMIN_JS_LOGS, ADMIN_JS_CACHE, ADMIN_JS_STATS, ADMIN_JS_PRERENDER,
    ADMIN_JS_CONFIG, ADMIN_JS_ABOUT, ACCOUNT_JS, ADMIN_JS_BACKUP, ADMIN_JS_BOOT,
])

# 管理面板的样式拼法：各 CSS 文件保持纯 CSS（编辑器能正常高亮 / 校验），
# `<style>` 外壳与两个共享占位符在装配时补齐。顺序仍是
# 共享层 → 面板样式 → 「我的」页样式，共享层在前是为了让分页样式能覆盖它。
_ADMIN_STYLE = "\n".join([
    '<style>', '{{SHARED_UI_CSS}}', ADMIN_CSS, '{{ACCOUNT_CSS}}', '</style>',
])

ADMIN_HTML = "\n".join([ADMIN_HEAD, _ADMIN_STYLE, ADMIN_BODY, _ADMIN_JS, ADMIN_TAIL])
