"""框架热更新：从 git 远端拉取新代码 → 只覆盖框架文件 → 按需装依赖。

范围是刻意划死的：**只动框架与 requirements，不碰 `plugins/` 与 `data/`**。
插件目录是使用方自己写/自己装的，`data/` 是运行数据（数据库、备份、上传），
被一次自动更新覆盖掉就是事故。更新完框架代码必须重启进程才生效（插件热重载只覆盖
`plugins/**`），因此本模块只负责「把文件换好」，重启由调用方决定（见 `restart_process`）。

所有函数都是同步阻塞的（git / pip 都是外部进程），调用方负责放进 worker 线程。
"""
import os
import subprocess
import sys
import tempfile

from modules.utils import plog

# 允许被更新覆盖的路径（相对仓库根）。显式白名单而不是「排除 plugins/data」：
# 仓库里将来多出一个目录时，白名单的失效方式是「更新不到它」，黑名单的失效方式是
# 「把使用方的私有文件覆盖掉」——两者的代价不对等。
FRAMEWORK_PATHS = (
    'modules',
    'run.py',
    'app.py',
    'config.py',
    'requirements.txt',
    'requirements-local.txt',
    'public',
    'deploy',
    '.trae/wiki',
)

# 依赖清单：requirements-local.txt 里有一行 `-r requirements.txt`，装上它就同时覆盖两者。
# 它缺失（老版本仓库）时退回 requirements.txt。
_REQUIREMENTS_CANDIDATES = ('requirements-local.txt', 'requirements.txt')

# git 命令超时（秒）：fetch 走网络，给宽一点；其余都是本地操作
_FETCH_TIMEOUT = 120
_GIT_TIMEOUT = 30
_PIP_TIMEOUT = 900


def project_root():
    """仓库根：本文件位于 <root>/modules/updater.py"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_git(root, args, timeout=_GIT_TIMEOUT):
    """执行一条 git 命令，返回 (returncode, stdout, stderr)。git 不存在时返回 (-1, '', 原因)。

    环境里显式关掉交互式凭据提示：更新是后台/一键触发的，弹出凭据输入会一直挂到超时。
    """
    env = dict(os.environ)
    env['GIT_TERMINAL_PROMPT'] = '0'
    env.setdefault('GIT_ASKPASS', 'echo')
    try:
        proc = subprocess.run(
            ['git'] + list(args), cwd=root, env=env, timeout=timeout,
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
    except FileNotFoundError:
        return -1, '', 'git 不可用'
    except subprocess.TimeoutExpired:
        return -2, '', 'git 命令超时'
    except Exception as exc:
        return -3, '', str(exc)
    return proc.returncode, (proc.stdout or '').strip(), (proc.stderr or '').strip()


def is_git_repo(root=None):
    """当前部署是不是一个 git 检出。打包分发（zip / Docker 镜像）里没有 .git，更新不可用"""
    code, out, _ = _run_git(root or project_root(), ['rev-parse', '--is-inside-work-tree'])
    return code == 0 and out.strip() == 'true'


def current_branch(root=None):
    """当前分支名；处于游离 HEAD 或取不到时返回空串"""
    code, out, _ = _run_git(root or project_root(), ['rev-parse', '--abbrev-ref', 'HEAD'])
    if code != 0:
        return ''
    name = out.strip()
    return '' if name in ('', 'HEAD') else name


def _ref(remote, branch):
    return f'{remote}/{branch}'


def check_update(root=None, remote='origin', branch=''):
    """检查是否有更新。返回结构：

    {available, reason, detail, branch, remote, local, remote_rev, local_subject, remote_subject, changed}

    `reason` 是给前端做映射的稳定串（not_git / git_missing / no_branch / fetch_failed /
    up_to_date / update_available），`detail` 是原始报错文本（排障用，不做取词）。
    """
    root = root or project_root()
    if not os.path.isdir(os.path.join(root, '.git')):
        return _result(reason='not_git')
    if not is_git_repo(root):
        return _result(reason='not_git')

    branch = branch or current_branch(root)
    if not branch:
        return _result(reason='no_branch')

    code, _out, err = _run_git(root, ['fetch', '--prune', remote, branch], timeout=_FETCH_TIMEOUT)
    if code == -1:
        return _result(reason='git_missing', branch=branch, remote=remote)
    if code != 0:
        return _result(reason='fetch_failed', detail=err, branch=branch, remote=remote)

    ref = _ref(remote, branch)
    local = _git_rev(root, 'HEAD')
    remote_rev = _git_rev(root, ref)
    if not local or not remote_rev:
        return _result(reason='fetch_failed', detail=err, branch=branch, remote=remote)

    changed = _changed_files(root, ref)
    return {
        'available': local != remote_rev,
        'reason': 'update_available' if local != remote_rev else 'up_to_date',
        'detail': '',
        'branch': branch,
        'remote': remote,
        'local': local,
        'remote_rev': remote_rev,
        'local_subject': _git_subject(root, 'HEAD'),
        'remote_subject': _git_subject(root, ref),
        'changed': changed,
    }


def _git_rev(root, ref):
    code, out, _ = _run_git(root, ['rev-parse', ref])
    return out if code == 0 else ''


def _git_subject(root, ref):
    code, out, _ = _run_git(root, ['log', '-1', '--pretty=%s', ref])
    return out if code == 0 else ''


def _changed_files(root, ref):
    """相对 HEAD，远端在这批框架路径上改了哪些文件（用于展示与判断 requirements 是否变化）"""
    code, out, _ = _run_git(root, ['diff', '--name-only', 'HEAD', ref, '--'] + list(FRAMEWORK_PATHS))
    if code != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _requirements_changed(changed):
    return [name for name in _REQUIREMENTS_CANDIDATES if name in changed]


def _install_requirements(root, ref, names):
    """按**远端版本**的依赖清单装依赖，语义是「先保证依赖装得上，再换代码」。

    清单从 `git show <ref>:<file>` 取，不动工作区：这样 pip 失败时工作区代码还是旧的、
    依赖也还是旧的，两边一致（若先覆盖代码再装依赖，中途失败会留下「新代码 + 旧依赖」
    这种半截状态）。
    """
    errors = []
    for name in names:
        code, content, err = _run_git(root, ['show', f'{ref}:{name}'])
        if code != 0 or not content:
            errors.append(err or f'{name} 读取失败')
            continue
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix='einkviews-req-', suffix='.txt')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content + '\n')
            proc = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', tmp],
                cwd=root, timeout=_PIP_TIMEOUT,
                capture_output=True, text=True, encoding='utf-8', errors='replace',
            )
            if proc.returncode == 0:
                # 成功一份即可：requirements-local.txt 内含 `-r requirements.txt`，两者都覆盖
                return ''
            errors.append((proc.stderr or proc.stdout or '').strip()[-500:])
        except Exception as exc:
            errors.append(str(exc))
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return '；'.join(e for e in errors if e)[-500:]


def apply_update(root=None, remote='origin', branch='', download_only=False):
    """拉取更新并（可选）覆盖框架文件。

    download_only=True 时只做 fetch——把远端对象取回本地备用，工作区一行不改。
    返回 {success, reason, detail, changed, requirements, branch, remote}。
    """
    root = root or project_root()
    info = check_update(root, remote=remote, branch=branch)
    if info['reason'] in ('not_git', 'git_missing', 'no_branch'):
        return _apply_result(info, success=False)
    if info['reason'] == 'fetch_failed':
        return _apply_result(info, success=False)
    if download_only:
        # fetch 已在 check_update 里完成，「仅下载」到这一步就是成功
        return _apply_result(info, success=True, reason='downloaded' if info['available'] else 'up_to_date')

    if not info['available']:
        return _apply_result(info, success=True, reason='up_to_date')

    ref = _ref(info['remote'], info['branch'])
    req_files = _requirements_changed(info['changed'])
    if req_files:
        err = _install_requirements(root, ref, req_files)
        if err:
            return _apply_result(info, success=False, reason='pip_failed', detail=err)

    # 只覆盖白名单路径：`git checkout <ref> -- <paths>` 把远端那棵树里这些路径的内容
    # 写进工作区，其余文件（plugins/、data/、使用方自己的改动）原样不动
    code, _out, err = _run_git(
        root, ['checkout', ref, '--'] + list(FRAMEWORK_PATHS), timeout=_FETCH_TIMEOUT)
    if code != 0:
        return _apply_result(info, success=False, reason='checkout_failed', detail=err)

    plog.info(f'[更新] 已更新到 {ref} · {len(info["changed"])} 个文件'
              + (f' · 依赖已安装 {req_files}' if req_files else ''))
    return _apply_result(info, success=True, reason='updated', requirements=req_files)


def _result(reason, detail='', branch='', remote='', **extra):
    out = {
        'available': False, 'reason': reason, 'detail': detail, 'branch': branch,
        'remote': remote, 'local': '', 'remote_rev': '', 'local_subject': '',
        'remote_subject': '', 'changed': [],
    }
    out.update(extra)
    return out


def _apply_result(info, success, reason=None, detail=None, requirements=None):
    return {
        'success': bool(success),
        'reason': reason or info.get('reason', ''),
        'detail': info.get('detail', '') if detail is None else detail,
        'branch': info.get('branch', ''),
        'remote': info.get('remote', ''),
        'available': info.get('available', False),
        'changed': info.get('changed', []),
        'requirements': requirements or [],
        'remote_rev': info.get('remote_rev', ''),
        'remote_subject': info.get('remote_subject', ''),
    }


# ---- 自动更新（由调度循环驱动，只有 leader 实例执行） ----

def update_mode():
    """当前更新模式：off / download / auto（非法值一律当 off）"""
    import config
    value = str(getattr(config, 'UPDATE_MODE', 'off') or '').strip().lower()
    if value in ('download', 'auto'):
        return value
    return 'off'


def update_settings():
    """面板「关于」页要回显的更新设置（不含检查结果）"""
    import config
    return {
        'mode': update_mode(),
        'remote': str(getattr(config, 'UPDATE_REMOTE', 'origin') or 'origin').strip() or 'origin',
        'branch': str(getattr(config, 'UPDATE_BRANCH', '') or '').strip(),
        'auto_times': str(getattr(config, 'UPDATE_AUTO_TIMES', '') or '').strip(),
    }


def _auto_step(app):
    """自动更新的一轮（同步，跑在 worker 线程）：到点了就按模式拉取/更新，更新成功则重启"""
    mode = update_mode()
    if mode == 'off':
        return None
    from modules.database.core import is_db_available
    if not is_db_available():
        return None
    from modules.database.stats import get_server_info, set_server_info
    from modules.prerender.scheduler import last_daily_occurrence

    settings = update_settings()
    occurrence = last_daily_occurrence(settings['auto_times'])
    if not occurrence:
        return None
    if occurrence <= (get_server_info('update_auto_last') or ''):
        return None

    error = ''
    restarted = False
    try:
        result = apply_update(
            remote=settings['remote'], branch=settings['branch'],
            download_only=(mode == 'download'),
        )
        if not result['success']:
            error = result['detail'] or result['reason']
        elif mode == 'auto' and result['reason'] == 'updated':
            restarted = True
    except Exception as exc:
        error = str(exc)
        plog.exception('自动更新失败')
    # 无论成败都记已处理：不记的话调度循环每 10 秒重试一次，网络不通会变成高频失败风暴
    set_server_info('update_auto_last', occurrence)
    set_server_info('update_auto_error', error or '')
    if error:
        plog.error(f'[更新] {error}')
    if restarted:
        # 放在最后：重启是终态动作，先记完「上次执行」再重启，否则重启后这条记录丢了会重复更新
        from modules.utils.restart import restart_process
        restart_process(app)
    return occurrence


async def maybe_run_scheduled_update(app):
    """调度循环每轮调用一次；由 leader 实例执行（与自动备份共用同一个循环）"""
    import asyncio
    await asyncio.to_thread(_auto_step, app)


__all__ = [
    'FRAMEWORK_PATHS', 'project_root', 'is_git_repo', 'current_branch',
    'check_update', 'apply_update', 'update_mode', 'update_settings',
    'maybe_run_scheduled_update',
]