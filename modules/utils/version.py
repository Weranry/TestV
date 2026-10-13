"""点分十进制版本号比较（如 `1.0.18`）。

用途只有一处判断：插件的 `min_framework_version` 是否高于当前框架版本。
不引入 `packaging`——它不在依赖清单里（Vercel 只装 requirements.txt 的最小集），
而这里需要的语义只是「谁更新」，标准库足够。
"""

import re

_VERSION_RE = re.compile(r'^\d+(?:\.\d+)*$')


def parse_version(text):
    """把 `'1.0.18'` 解析成 `(1, 0, 18)`；非法输入返回 None。

    `'1.0'` 与 `'1.0.0'` 视为同一版本：在 compare_versions 里补齐到等长再比。
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not _VERSION_RE.match(text):
        return None
    return tuple(int(part) for part in text.split('.'))


def compare_versions(left, right):
    """left 更新返回 1，相同返回 0，更旧返回 -1；任一侧格式非法返回 None。

    None 表示「无法判定」，由调用方决定是放行还是拒绝：插件清单里的版本号在
    加载期已校验过格式，所以走到这里基本不会拿到 None。
    """
    a, b = parse_version(left), parse_version(right)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return (a > b) - (a < b)