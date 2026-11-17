"""共享 UI 的注入点。

设计令牌、共享样式与脚本、通知铃铛、导航 logo、「我的」页卡片本身都在
`static/` 下（见 `templates.py`），这里只负责把它们填进各页面的占位符。
"""
from modules.admin_ui import templates
from modules.admin_ui.templates import (
    ACCOUNT_CARDS, ACCOUNT_CSS, ACCOUNT_JS, LOGO_SVG, NOTIF_BELL)

# 私有别名保留原名字：共享层的这几份历史上是模块私有常量，内部与本文件按下划线名引用
_THEME_TOKENS_CSS = templates.THEME_TOKENS_CSS
_SHARED_UI_CSS = templates.SHARED_UI_CSS
_SHARED_UI_JS = templates.SHARED_UI_JS
_THEME_INIT_JS = templates.THEME_INIT_JS


def apply_shared_ui(html):
    """把共享 UI（设计令牌 / 浮层通知 / 弹窗样式与脚本 / 导航 logo / 「我的」页卡片）注入到占位符处"""
    return (html
            # 令牌层直接拼在共享样式前面：每个页面的 <style> 里都有 {{SHARED_UI_CSS}}，
            # 拼在这里就不必再往六个页面里各插一个令牌占位符（少一处会漏的定义）
            .replace('{{SHARED_UI_CSS}}', _THEME_TOKENS_CSS + _SHARED_UI_CSS)
            .replace('{{SHARED_UI_JS}}', _SHARED_UI_JS)
            .replace('{{THEME_INIT}}', _THEME_INIT_JS)
            .replace('{{ACCOUNT_CSS}}', ACCOUNT_CSS)
            .replace('{{ACCOUNT_CARDS}}', ACCOUNT_CARDS)
            .replace('{{ACCOUNT_JS}}', ACCOUNT_JS)
            .replace('{{NOTIF_BELL}}', NOTIF_BELL)
            .replace('{{LOGO}}', LOGO_SVG))
