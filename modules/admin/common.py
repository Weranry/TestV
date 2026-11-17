import re

# 登录页「注册新账号」入口的标记块：EVKEY_REGISTRATION_ENABLED=False 时整段剔除，
# 避免出现指向已关闭注册页的死链（与首页 admin-entry 同一套做法）
_REGISTER_LINK_RE = re.compile(r'\s*<!--\s*register-link:start\s*-->.*?<!--\s*register-link:end\s*-->', re.S)

def _app_state(r): return r.app.state


def is_super_admin(request):
    """是否「系统主管理员」：内置管理组里最早创建的兜底管理账号。

    它是唯一允许做整库级操作（恢复备份、恢复出厂）与管理员账号/管理组管理的账号；
    其他管理组账号即便拿到后台分页权限也只是普通管理员。主管理员在
    user_routes 里被禁止改组/删除，因此这个判定不会随日常操作漂移。

    直接调用（单元测试的最小请求桩没有 state）时返回 True——这些测试本来就是
    在无鉴权环境里跑整个流程；真实请求一定带 state。
    """
    state = getattr(request, 'state', None)
    if state is None:
        return True
    user = getattr(state, 'user', None)
    if not isinstance(user, dict):
        return False
    from modules.database.groups import is_admin_category
    if not is_admin_category(user.get('group_category')):
        return False
    try:
        from modules.database.accounts import default_admin_account_id
        return user.get('id') == default_admin_account_id()
    except Exception:
        return False


def super_admin_only(request):
    """系统主管理员专属操作的统一拒绝出口（None = 放行）"""
    if is_super_admin(request):
        return None
    from modules.errors.errors import error_response
    from modules.i18n.registry import t_req
    return error_response(t_req(request, 'msg.super_admin_only'), 403)


async def _body(request):
    """安全解析 JSON 请求体：解析失败返回 None，避免每处都写一遍裸 except"""
    try:
        return await request.json()
    except Exception:
        return None

def _client_ip(request):
    """来源 IP，供登录防撞库计数。取法见 modules/utils/client_ip.py：
    默认只认直连地址（伪造 X-Forwarded-For 无效），配了 TRUST_PROXY_HEADERS 才信代理"""
    from modules.utils.client_ip import client_ip
    return client_ip(request)

def _int_field(body, key, default):
    """取整数字段；缺失或非法时用 default（注意 0 是合法值，不能被 or 吞掉）"""
    v = body.get(key)
    if v is None or v == '':
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

def _fmt_bytes(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{int(n)} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'

def _drop_group_semaphores(state, *group_ids):
    """丢弃这些用户组下所有账号的渲染并发信号量。

    并发上限按组配置、按用户缓存，改组/转移账号后不丢弃就会沿用旧组的信号量，
    要重启进程才生效。
    """
    sems = getattr(state, 'render_semaphores', None)
    if not sems:
        return
    for uid in [u for u, e in sems.items() if e[0] in group_ids]:
        sems.pop(uid, None)


def _drop_account_semaphores(state, *account_ids):
    """丢弃这些账号的渲染并发信号量。

    账号被删除后信号量再没有任何请求会用到，留着就是纯内存泄漏（缓存本身也有
    容量上限兜底，但删除是明确的回收时机，不该等它挤出去）。
    """
    sems = getattr(state, 'render_semaphores', None)
    if not sems:
        return
    for uid in account_ids:
        sems.pop(uid, None)