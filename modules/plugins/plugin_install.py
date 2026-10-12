"""插件 zip 包的上传安装与卸载。

原先把插件装进实例只有「手工拷目录 + 面板点热重载」一条路，而 `plugins/` 不在任何版本控制下、
也没有任何校验：拷错目录、清单里的 `name` 与目录名不一致、`min_framework_version` 高于当前框架，
都要等到「面板上凭空少了一个插件」才被发现。这里补上「先解压校验、再原子落盘」的通道。

**信任边界（改本文件前先读）**：安装插件 = 让服务以自身进程权限执行包内的 Python 代码
（`routes.py` / `plugin_config.py` 都在 import 期执行）。所以本模块做的是**完整性校验**
（zip 结构、路径穿越、体积、清单合法性），**不是安全沙箱**；`plugin.json` 只是元信息，
不是准入门槛。准入靠「后台登录态 + 插件分页权限 + 二次确认 + 文档声明」。

staging 必须放在 `plugins/` 下的**点目录**里（`.staging/`）：`register_plugins` 只扫 `plugins/`
的第一层、且要求目录下有 `routes.py` 才认作插件。点目录不会被扫到；而 `plugins/<uuid>` 那种
名字会——根形式的插件其 `routes.py` 就在插件根下，一次并发热重载就能把半成品当成真插件加载。

覆盖安装与卸载都**不留备份**：同名目录直接删除。这也是为什么这里只认 `.staging` 一个点目录。
"""
import hashlib
import io
import os
import posixpath
import re
import shutil
import threading
import uuid
import zipfile
import zlib

from modules.plugins.manifest import (
    MANIFEST_FILE,
    ManifestError,
    compare_framework,
    load_manifest,
)
from modules.utils import body_limit, plog

# 安装与卸载共用一把锁：两个上传同时搬目录 + 重建路由表，磁盘状态与内存态会对不上
_LOCK = threading.Lock()

# 插件名白名单：三方（清单 name / zip 顶层目录名 / 落盘目录名）都必须匹配
NAME_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_-]*$')

# zip 内文件名带盘符（C:\...）的判据
_DRIVE_RE = re.compile(r'^[A-Za-z]:')

STAGING_DIR = '.staging'

# zip bomb 的静态上限：条目数、单文件、压缩比。总量上限走配置 PLUGIN_UNPACK_MAX_MB
MAX_ENTRIES = 2000
MAX_FILE_BYTES = 8 * body_limit.MB
MAX_RATIO = 200

# 允许进插件的扩展名。`.pyc/.pyo/.so/.dll` 之类自然被挡在白名单之外
ALLOWED_EXTS = frozenset((
    '.py', '.json', '.md', '.txt', '.html', '.css', '.js', '.svg',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
    '.ttf', '.woff', '.woff2', '.csv', '.yaml', '.yml', '.toml',
))
# 压缩包不再递归解压：套一层 zip 就能绕过上面全部体积与类型判据
NESTED_EXTS = frozenset((
    '.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.whl', '.7z', '.rar',
))
# 打包工具顺带带上来的噪声：直接剪掉，不当成内容也不因此拒绝整个包
_NOISE_NAMES = frozenset(('.DS_Store', 'Thumbs.db', 'desktop.ini'))
_NOISE_SEGMENTS = frozenset(('__MACOSX', '__pycache__'))


class InstallError(Exception):
    """带 i18n key 与占位参数的安装失败：raise InstallError('plugin.zip_bad_path')。

    只带 key 不带成品文案：本模块是纯函数、拿不到 request，取词统一在 HTTP 层做。
    """

    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def _is_noise(raw_name):
    """打包时顺手带进来的 macOS / Windows / 缓存残留"""
    name = raw_name.replace('\\', '/')
    if posixpath.basename(name.rstrip('/')) in _NOISE_NAMES:
        return True
    if posixpath.splitext(name)[1].lower() in ('.pyc', '.pyo'):
        return True
    return any(seg in _NOISE_SEGMENTS for seg in name.split('/'))


def _safe_member_name(raw_name):
    """把 zip 里的条目名收敛成安全的相对路径；不安全一律抛 InstallError。

    防的是 Zip Slip：`../`、绝对路径、Windows 盘符与反斜杠分隔符。反斜杠直接拒绝而不是
    归一化——zip 规范只认 `/`，带反斜杠的包不是我们支持的打包方式，而 `..\\` 这类写法
    在按 `/` 切段时会被整段漏过。
    """
    name = (raw_name or '').strip()
    if not name or '\\' in name:
        raise InstallError('plugin.zip_bad_path', name=raw_name)
    if posixpath.isabs(name) or _DRIVE_RE.match(name):
        raise InstallError('plugin.zip_bad_path', name=raw_name)
    trimmed = name.rstrip('/')
    if not trimmed:
        raise InstallError('plugin.zip_bad_path', name=raw_name)
    for seg in trimmed.split('/'):
        # 点开头的段一并拒：`.git/`、`.env` 这类内容不属于插件包
        if not seg or seg in ('.', '..') or seg.startswith('.'):
            raise InstallError('plugin.zip_bad_path', name=raw_name)
    return trimmed


def _check_ext(name):
    ext = posixpath.splitext(name)[1].lower()
    if ext in NESTED_EXTS:
        raise InstallError('plugin.zip_nested', name=name)
    if ext not in ALLOWED_EXTS:
        raise InstallError('plugin.zip_bad_type', name=name)


def _read_entries(zf, total_limit):
    """剪枝噪声 + 逐条安全判据 + 体积统计，返回 `[(info, 相对路径, 是否目录)]`。

    `total_limit` 为解压后总字节上限（0 = 不限）。压缩比与单文件上限在这里静态判一次，
    真实字节数在 `_safe_extract` 里解压时再核一次——zip 头里的 `file_size` 是攻击者写的。
    """
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise InstallError('plugin.zip_too_many', limit=MAX_ENTRIES)
    entries, total = [], 0
    for info in infos:
        raw_name = info.filename
        if _is_noise(raw_name):
            continue
        mode = (info.external_attr >> 16) & 0o170000
        name = _safe_member_name(raw_name)
        if info.is_dir() or mode == 0o040000:
            entries.append((info, name, True))
            continue
        # 0 是「打包工具没写权限位」，等价于普通文件；其余只允许普通文件
        if mode not in (0, 0o100000):
            raise InstallError('plugin.zip_bad_path', name=raw_name)
        _check_ext(name)
        if info.file_size > MAX_FILE_BYTES:
            raise InstallError('plugin.zip_too_big', name=name)
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_RATIO:
            raise InstallError('plugin.zip_too_big', name=name)
        total += info.file_size
        if total_limit > 0 and total > total_limit:
            raise InstallError('plugin.zip_too_big', name=name)
        entries.append((info, name, False))
    return entries


def _safe_extract(zf, entries, dest, total_limit):
    """把通过判据的条目解压到 `dest`。

    目录不依赖 zip 里的目录条目，一律由文件的父路径 `makedirs` 生成；每个目标再过一次
    `commonpath`，作为路径穿越的第二道确认。
    """
    dest_real = os.path.realpath(dest)
    total = 0
    for info, name, is_dir in entries:
        target = os.path.join(dest_real, *name.split('/'))
        target_real = os.path.realpath(target)
        if os.path.commonpath([dest_real, target_real]) != dest_real:
            raise InstallError('plugin.zip_bad_path', name=info.filename)
        if is_dir:
            os.makedirs(target_real, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target_real), exist_ok=True)
        got = 0
        with zf.open(info) as src, open(target_real, 'wb') as out:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                total += len(chunk)
                if got > MAX_FILE_BYTES or (total_limit > 0 and total > total_limit):
                    raise InstallError('plugin.zip_too_big', name=name)
                out.write(chunk)
        # 实读字节与 zip 头声明不符 = 头是伪造的，按坏包处理
        if got != info.file_size:
            raise InstallError('plugin.zip_bad', err=name)
    return total


def _resolve_plugin_dir(root):
    """判定 zip 结构，返回 `(插件根目录, 顶层目录名或 None)`。

    - A 形式：zip 根下就有 `plugin.json`，插件目录即 zip 根，名字稍后从清单里读；
    - B 形式：顶层**恰好一个**含 `plugin.json` 的目录，根下不允许再有其它的顶层条目。
    """
    if os.path.isfile(os.path.join(root, MANIFEST_FILE)):
        return root, None
    top = sorted(os.listdir(root))
    candidates = [
        entry for entry in top
        if os.path.isfile(os.path.join(root, entry, MANIFEST_FILE))
    ]
    if not candidates:
        raise InstallError('plugin.zip_no_manifest')
    if len(candidates) > 1:
        raise InstallError('plugin.zip_multi_plugins', names='、'.join(candidates[:5]))
    name = candidates[0]
    extra = [entry for entry in top if entry != name]
    if extra:
        raise InstallError('plugin.zip_extra_entries', names='、'.join(extra[:5]))
    return os.path.join(root, name), name


def _check_utf8(plugin_dir):
    """`.py` / `.json` 必须能按 UTF-8 解码：解不开的包在 import 期就会炸，不如现在就拒。

    只捕解码错误；`OSError` 放它往上抛（HTTP 层按 500 记日志）——磁盘问题报成「编码不对」
    会把人带去查编码，与 `_install_locked` 里「不把 OSError 当成坏包」是同一条原则。
    """
    for folder, _dirs, files in os.walk(plugin_dir):
        for fname in files:
            if posixpath.splitext(fname)[1].lower() not in ('.py', '.json'):
                continue
            path = os.path.join(folder, fname)
            try:
                with open(path, 'rb') as handle:
                    handle.read().decode('utf-8')
            except UnicodeDecodeError:
                raise InstallError('plugin.install_bad_encoding', name=fname)


def _validate_plugin_dir(plugin_dir, expected_name, framework_version, plugins_dir):
    """校验解压出来的插件目录，返回 `(manifest, warnings)`。

    `expected_name` 为 B 形式的顶层目录名（A 形式传 None，名字从清单读）。清单本身的字段
    类型 / 版本号格式 / 名字与目录名一致由 `load_manifest` 负责，这里只补它管不到的：
    必须有 `routes.py`、框架版本不能过低、代码得是 UTF-8。
    """
    try:
        manifest = load_manifest(plugin_dir, expected_name=expected_name)
    except ManifestError as exc:
        raise InstallError('plugin.install_bad_manifest', err=exc)
    if manifest is None:
        raise InstallError('plugin.zip_no_manifest')
    name = manifest.get('name') or ''
    if not NAME_RE.match(name):
        raise InstallError('plugin.zip_name_mismatch', name=name or '（空）')
    if not os.path.isfile(os.path.join(plugin_dir, 'routes.py')):
        raise InstallError('plugin.install_no_routes')
    minimum = manifest.get('min_framework_version') or ''
    if minimum and compare_framework(framework_version, minimum) < 0:
        # 启动期 resolve_load_order 必然会 skip 它，装了也只是「面板上多一个加载失败的条目」
        raise InstallError('plugin.install_fw_too_low', need=minimum, cur=framework_version)
    _check_utf8(plugin_dir)
    warnings = []
    missing = [
        dep for dep in manifest.get('dependencies', {}).get('plugins') or []
        if not os.path.isdir(os.path.join(plugins_dir, dep))
    ]
    if missing:
        # 只提示不回绝：可能是同批要装的另一个插件，且启动期已有一套明确的 skip 原因
        warnings.append({'key': 'plugin.warn_dep_missing', 'params': {'list': '、'.join(missing)}})
    return manifest, warnings


def _dir_stats(root):
    """`(文件数, 总字节)`：回给面板的是**落盘后**的规模，不是 zip 里的声明"""
    count = size = 0
    for folder, _dirs, files in os.walk(root):
        for fname in files:
            count += 1
            try:
                size += os.path.getsize(os.path.join(folder, fname))
            except OSError:
                pass
    return count, size


def install_from_zip(raw, plugins_dir, framework_version, *, replace=False):
    """把 zip 字节流安装成 `plugins/<名字>/`，返回安装结果字典（失败抛 InstallError）。

    `replace=False` 时目标已存在即拒绝；`replace=True` 时删掉同名旧目录再装入（不留备份）。
    新目录已经解压校验完毕才动旧目录，所以失败时不会留下半成品。
    """
    with _LOCK:
        return _install_locked(raw, plugins_dir, framework_version, replace)


def _install_locked(raw, plugins_dir, framework_version, replace):
    import config

    plugins_dir = os.path.abspath(plugins_dir)
    os.makedirs(plugins_dir, exist_ok=True)
    staging_root = os.path.join(plugins_dir, STAGING_DIR)
    work_dir = os.path.join(staging_root, uuid.uuid4().hex)
    os.makedirs(work_dir, exist_ok=False)
    try:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                total_limit = body_limit.limit_bytes(getattr(config, 'PLUGIN_UNPACK_MAX_MB', 64))
                entries = _read_entries(zf, total_limit)
                if not entries:
                    raise InstallError('plugin.zip_empty')
                unpack_dir = os.path.join(work_dir, 'unpack')
                os.makedirs(unpack_dir)
                _safe_extract(zf, entries, unpack_dir, total_limit)
        except (zipfile.BadZipFile, NotImplementedError, EOFError, zlib.error) as exc:
            # 压缩算法不支持、数据被截断或 deflate 流损坏，都归到「不是有效的 zip 包」。
            # 不把 OSError 收进来：磁盘写满这类错误报成坏包会把人带偏
            raise InstallError('plugin.zip_bad', err=exc)
        plugin_dir, dir_name = _resolve_plugin_dir(unpack_dir)
        manifest, warnings = _validate_plugin_dir(
            plugin_dir, dir_name, framework_version, plugins_dir)
        name = manifest['name']
        if dir_name and dir_name != name:
            raise InstallError('plugin.zip_name_mismatch', name=name)

        dest = os.path.join(plugins_dir, name)
        replaced = os.path.exists(dest)
        if replaced:
            if not replace:
                raise InstallError('plugin.install_exists', name=name)
            # 覆盖安装：旧版本直接删除，不留备份（用户明确要求）
            shutil.rmtree(dest)
        try:
            # 同设备走 rename，跨设备由 shutil.move 自己退化成拷贝（staging 与目标同在
            # plugins/ 下，正常走不到拷贝这条）
            shutil.move(plugin_dir, dest)
        except OSError as exc:
            raise InstallError('plugin.install_move_failed', err=exc)

        files, size = _dir_stats(dest)
        plog.info(f'插件已安装: {name} {manifest.get("version", "")} '
                  f'({files} 个文件, {size} 字节, sha256={hashlib.sha256(raw).hexdigest()[:12]}'
                  f'{"，已覆盖旧版本" if replaced else ""})')
        return {
            'name': name,
            'version': manifest.get('version', ''),
            'description': manifest.get('description', ''),
            'author': manifest.get('author', ''),
            'files': files,
            'size': size,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'warnings': warnings,
            'replaced': replaced,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def uninstall_plugin(name, plugins_dir):
    """把 `plugins/<name>` 整体删除，返回 `{name}`（不留备份）。

    只接受白名单名字且必须是 `plugins/` 的**直接子目录**（realpath 二次确认），
    防的是拿请求参数拼路径穿到别处去。
    """
    with _LOCK:
        if not NAME_RE.match(name or ''):
            raise InstallError('plugin.uninstall_bad_name', name=name or '')
        plugins_dir = os.path.abspath(plugins_dir)
        target = os.path.abspath(os.path.join(plugins_dir, name))
        real = os.path.realpath(target)
        if (os.path.dirname(target) != plugins_dir
                or os.path.dirname(real) != os.path.realpath(plugins_dir)):
            raise InstallError('plugin.uninstall_bad_name', name=name)
        if not os.path.isdir(target):
            raise InstallError('plugin.uninstall_missing', name=name)
        shutil.rmtree(target)
        plog.info(f'插件已卸载: {name}')
        return {'name': name}
