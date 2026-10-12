"""插件清单（`plugins/<名字>/plugin.json`）的读取与加载顺序解析。

清单是插件元信息的**唯一来源**：版本、作者、描述、最低框架版本、依赖都从这里读，
面板与启动摘要不再靠 `PLUGIN_DESCRIPTION` 猜。

三条既定取向：
- 没有 `plugin.json` 的插件照旧加载，只标记 `manifest_missing`（不把第三方插件一刀切拒之门外）；
- 清单存在但格式非法 = 加载失败（宁可报出来，也不静默按默认值跑）；
- `dependencies.python` 只记录不强制（Vercel 只能装 requirements.txt 的最小集），
  面板以「建议依赖」呈现。
"""

import json
import os

from modules.utils.version import compare_versions, parse_version

MANIFEST_FILE = 'plugin.json'

# 字段全部可选，缺失按这里的默认值处理；清单里出现的未知字段原样保留（向后兼容新字段）
DEFAULT_DEPENDENCIES = {'plugins': [], 'python': []}


class ManifestError(ValueError):
    """清单存在但不合法：JSON 解析失败、字段类型错误、版本号格式非法、名字与目录不一致"""


def manifest_path(plugin_dir):
    return os.path.join(plugin_dir, MANIFEST_FILE)


def load_manifest(plugin_dir, expected_name=None):
    """读 `<plugin_dir>/plugin.json`。

    文件不存在返回 None（插件可以没有清单）；存在但不合法抛 ManifestError。
    传 `expected_name` 时校验清单里的 name 与目录名一致——不一致说明清单是从别处拷来的，
    这时按清单走会加载到错的插件。
    """
    path = manifest_path(plugin_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ManifestError(f'plugin.json 无法解析: {exc}')
    if not isinstance(raw, dict):
        raise ManifestError('plugin.json 顶层必须是对象')
    return _normalize(raw, expected_name)


def _normalize(raw, expected_name):
    manifest = dict(raw)
    for key in ('name', 'version', 'description', 'author', 'min_framework_version'):
        value = manifest.get(key, '')
        if value is None:
            value = ''
        if not isinstance(value, str):
            raise ManifestError(f'{key} 必须是字符串')
        manifest[key] = value.strip()

    if expected_name and manifest['name'] and manifest['name'] != expected_name:
        raise ManifestError(f"清单里的 name「{manifest['name']}」与目录名「{expected_name}」不一致")
    if expected_name and not manifest['name']:
        manifest['name'] = expected_name

    for key in ('version', 'min_framework_version'):
        if manifest[key] and parse_version(manifest[key]) is None:
            raise ManifestError(f'{key}「{manifest[key]}」不是合法的点分版本号（如 1.0.0）')

    manifest['dependencies'] = _normalize_dependencies(manifest.get('dependencies'))
    return manifest


def _normalize_dependencies(raw):
    deps = dict(DEFAULT_DEPENDENCIES)
    if raw is None:
        return deps
    if not isinstance(raw, dict):
        raise ManifestError('dependencies 必须是对象')
    for key in DEFAULT_DEPENDENCIES:
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ManifestError(f'dependencies.{key} 必须是字符串数组')
        deps[key] = [item.strip() for item in value if item.strip()]
    return deps


def plugin_dependencies(manifest):
    """取一个插件声明的插件级依赖（清单为 None 时返回空列表）"""
    if not manifest:
        return []
    return list(manifest.get('dependencies', {}).get('plugins') or [])


def resolve_load_order(names, manifests, framework_version):
    """按依赖拓扑排序，返回 `(order, skipped)`。

    - `order`：本次要真正加载的插件名，被依赖者排在前面；
    - `skipped`：`{名字: 原因}`，含框架版本过低、依赖缺失、依赖链上有失败、循环依赖。

    跳过而不是静默丢弃：名字与原因会随 `failures` 回传面板，否则管理员只能看到
    「插件凭空少了一个」。
    """
    skipped = {}
    candidates = []
    for name in names:
        manifest = manifests.get(name)
        minimum = (manifest or {}).get('min_framework_version') or ''
        if minimum and compare_framework(framework_version, minimum) < 0:
            skipped[name] = f'需要框架版本 {minimum} 以上（当前 {framework_version}）'
            continue
        candidates.append(name)

    # 依赖不满足会传染：A 依赖 B、B 被跳过时 A 也加载不了，逐轮收敛直到稳定
    changed = True
    while changed:
        changed = False
        for name in list(candidates):
            for dep in plugin_dependencies(manifests.get(name)):
                if dep in skipped:
                    reason = f'依赖的插件 {dep} 未加载'
                elif dep not in candidates:
                    reason = f'依赖的插件 {dep} 不存在'
                else:
                    continue
                skipped[name] = reason
                candidates.remove(name)
                changed = True
                break

    order, resolved, pending = [], set(), list(candidates)
    while pending:
        progressed = False
        for name in list(pending):
            if all(dep in resolved for dep in plugin_dependencies(manifests.get(name))):
                order.append(name)
                resolved.add(name)
                pending.remove(name)
                progressed = True
        if not progressed:
            for name in pending:
                blocked = [d for d in plugin_dependencies(manifests.get(name)) if d in pending]
                skipped[name] = '循环依赖: ' + ' ↔ '.join([name] + blocked)
            break
    return order, skipped


def compare_framework(current, minimum):
    """当前框架版本与插件要求的最小版本比较；无法判定时按「满足」处理（放行加载）"""
    result = compare_versions(current, minimum)
    return 0 if result is None else result