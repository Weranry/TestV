from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body
from modules.cache.cache import stats as cache_stats, clear as cache_clear
from modules.errors.errors import error_response
from modules.i18n.registry import lang_of, t, t_req
from modules.utils.timezone import utc_now_iso

router = APIRouter()

# 配置项清单（键 / 中文标签 / 说明 / 分类）的唯一来源在 config_schema.py：
# import / export / 面板渲染 / i18n 中文文案全部从那里派生，此处只做引用，
# 避免「加了一项配置却漏改某个副本」。
from modules.admin.config_schema import CONFIG_LABELS, CATEGORY_SLUGS as _CATEGORY_SLUGS

def _labels_with_options(lang=None):
    """CONFIG_LABELS + 那些「取值集合固定」项的候选值（面板据此渲染下拉 / 复选）。

    候选一律从代码里现取：输出格式来自 `image_output` 的注册表，不能在面板侧另抄一份
    字面量（注册表加了新格式，抄来的那份会照旧不认）。放在函数里而不是模块级常量，
    是因为它会拉起 PIL，而这份标签只在打开配置页时才需要。

    返回前把 label / desc 覆盖成当前语言的词条；`category` 保持中文原值不动——前端
    拿它分组 / 排序 / 跳过，翻了会把英文界面下的分组逻辑打散，另给 category_label 供显示。
    """
    from modules.generate_views.image_output import supported_formats
    out = {k: dict(v) for k, v in CONFIG_LABELS.items()}
    fmt = supported_formats()
    out['DEFAULT_IMAGE_FORMAT']['options'] = fmt
    out['IMAGE_FORMAT_BLACKLIST']['options'] = fmt
    out['DEFAULT_ROTATE']['options'] = [0, 90, 180, 270]
    out['DEFAULT_TIFF_COMPRESSION']['options'] = ['tiff_lzw', 'tiff_zlib', 'raw']
    # 界面语言：候选来自 i18n 注册表自己（加了语言这里自动多一项，不在面板侧另抄字面量）
    from modules.i18n.registry import SUPPORTED_LANGS
    out['LANG']['options'] = ['auto'] + list(SUPPORTED_LANGS)
    # 更新模式：候选固定三个，与 modules/updater.update_mode 的判定逐字对齐
    out['UPDATE_MODE']['options'] = ['off', 'download', 'auto']
    for key, item in out.items():
        item['label'] = t('config.lbl.' + key, lang)
        item['desc'] = t('config.desc.' + key, lang)
        slug = _CATEGORY_SLUGS.get(item['category'])
        item['category_label'] = t('config.cat.' + slug, lang) if slug else item['category']
    return out


@router.get('/api/config')
async def admin_config(request: Request):
    from modules.database.states import get_config_overrides
    overrides = get_config_overrides()
    defaults = {}
    try:
        import config as cfg
        for k, v in vars(cfg).items():
            if k.isupper() and not k.startswith('_'):
                if isinstance(v, (str, int, float, bool, list)):
                    defaults[k] = v
    except: pass
    return JSONResponse({'overrides': overrides, 'defaults': defaults,
                         'labels': _labels_with_options(lang_of(request))})

def _validate_config_value(key, value, lang=None):
    """配置项取值的服务端校验。返回 (错误文案, 状态码)，None 表示放行。

    面板是唯一入口，但校验必须落在服务端：前端只管渲染，绕过前端直接 POST 一样能写库。
    返回文案而不是现成的响应对象：单条保存要把它包成错误响应，导入要把它并进逐项报告，
    两条路径共用同一份判定（导入侧不该另写一套「哪些键不许写」的规则）。
    """
    from modules import config_store
    if key == 'AUTH_ENABLE' and config_store.get_mode() != 'dev':
        # 非本地模式（prod / vercel）的 AUTH_ENABLE 归环境变量独占，写库不会生效
        # （config_store.enforce_mode_constraints 会覆盖回来）。放任保存等于给管理员
        # 一个「点了没反应」的假开关，所以直接拒绝并说明真正的入口。
        return (t('config.err_auth_env', lang), 400)
    if key == 'REGISTER_DEFAULT_GROUP_ID':
        from modules.database.groups import get_group, is_admin_category
        try:
            gid = int(value or 0)
        except (TypeError, ValueError):
            return (t('config.err_group_id', lang), 400)
        if gid:
            g = get_group(gid)
            if g is None:
                return (t('config.err_group_missing', lang), 404)
            # 默认注册组指向管理组：任何人不带激活码注册一次就成管理员。激活码的三条路径
            # 与组编辑都已堵死管理组，这第四条路径同样要堵（groups.ensure_register_group 有兜底）。
            # 判定看 category 而不是 id：管理组可以被改名，也可以新建。
            if is_admin_category(g.get('category')):
                return (t('config.err_group_admin', lang), 400)
    return None


@router.post('/api/config')
async def admin_save_config(request: Request):
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    key, value = body.get('key'), body.get('value')
    if not key: return error_response(t_req(request, 'msg.missing_field', name='key'), 400)
    # 白名单与导入导出同源（CONFIG_LABELS）。不校验的话这里就成了「任意 setattr(config)」
    # 的写入口：受限管理组能改写 REDIS_URL / AUTH_WHITELIST 等任意配置项。
    if key not in CONFIG_LABELS:
        return error_response(t_req(request, 'config.err_unknown_key', name=key), 400)
    if value is not None:
        err = _validate_config_value(key, value, lang_of(request))
        if err is not None:
            return error_response(err[0], err[1])
    from modules.database.states import save_config_override, delete_config_override
    from modules import config_store
    if value is None:
        delete_config_override(key)
        config_store.reload_and_apply()
    else:
        save_config_override(key, value)
        config_store.apply_one(key, value)
    return JSONResponse({'success': True})


@router.post('/api/config/reset-all')
async def admin_reset_config(request: Request):
    """清空全部全局配置覆盖，回到 config.py 的默认值。

    只动 config_overrides 这张表：插件配置覆盖、用户组限额、账号数据都不在「恢复默认
    设置」的语义里，它们各自有独立的入口（插件页 / 用户组页）。删完统一热应用一次，
    避免出现「A 已还原、B 还是旧值」的中间态。
    """
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)

    def _clear():
        from modules.database.states import get_config_overrides, delete_config_override
        keys = list(get_config_overrides().keys())
        for key in keys:
            delete_config_override(key)
        return len(keys)

    removed = await asyncio.to_thread(_clear)
    from modules import config_store
    config_store.reload_and_apply()
    return JSONResponse({'success': True, 'removed': removed})


# ---- 配置导入 / 导出 ----

# 载荷标识与格式版本。导入先认这两个字段，避免把随手一个 JSON（插件自带的配置文件、
# 别家的导出清单）当成配置包灌进库。版本号只在「导入方比导出方新」时拒收：
# 老版本服务读不了新版本多出来的结构，反过来（新服务读老包）是安全的。
CONFIG_SCHEMA = 'einkviews-config'
CONFIG_SCHEMA_VERSION = 1

# 导入允许写回的组字段：只留限额 / 配额这类可重算的运行参数。组名、类别、builtin、
# admin_tabs 一律不进导入——一次误导入就能把某个管理组的分页清空，或把内置组改名，
# 而这几项在面板上本该逐个确认。
_GROUP_IMPORT_FIELDS = ('max_evkeys', 'max_devices', 'max_concurrent_renders',
                        'rate_limit_per_minute', 'quota_limit', 'quota_period')
_GROUP_INT_FIELDS = ('max_evkeys', 'max_devices', 'max_concurrent_renders',
                     'rate_limit_per_minute', 'quota_limit')


def _as_int(value):
    """导入值转 int；bool 与非法值返回 None（True 会被 int() 当成 1，不能放进来）"""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _export_config():
    """配置导出的载荷（同步查库，调用方负责放线程）

    config_overrides 里可能残留已经改名的历史键，导出按 CONFIG_LABELS 过滤：
    导出文件只应包含当前版本真的认识、也真的能导入回来的项。
    """
    from modules.database.states import get_config_overrides, get_all_plugin_config_overrides
    from modules.database.groups import get_all_groups

    version = ''
    try:
        from modules.app_core import FRAMEWORK_VERSION
        version = FRAMEWORK_VERSION
    except Exception:
        pass

    groups = []
    for g in get_all_groups():
        item = {'id': g.get('id'), 'name': g.get('name')}
        for field in _GROUP_IMPORT_FIELDS:
            item[field] = g.get(field)
        groups.append(item)

    overrides = get_config_overrides()
    return {
        'schema': CONFIG_SCHEMA,
        'version': CONFIG_SCHEMA_VERSION,
        'framework_version': version,
        'exported_at': utc_now_iso(),
        'config': {k: v for k, v in overrides.items() if k in CONFIG_LABELS},
        'plugins': get_all_plugin_config_overrides(),
        'groups': groups,
    }


def _import_config(app, payload, lang=None):
    """把导出包写回库（同步，调用方负责放线程）；返回逐项处理结果

    三条判定贯穿始终：**结构对不对**（schema / version）、**这项认不认识**（白名单）、
    **这个值收不收**（复用面板保存时的 _validate_config_value）。认不出的键一律
    落到 skipped 而不是整包拒收——配置包常常是「从新版本的部署导出、导进旧版本」，
    里面混着几项本版本没有的配置是常态，为此整包失败反而更危险（用户会去手改库）。
    """
    result = {
        'config': {'applied': [], 'skipped': [], 'rejected': []},
        'groups': {'applied': 0, 'skipped': [], 'rejected': []},
        'plugins': {'applied': 0, 'skipped': []},
    }

    from modules.database.states import save_config_override, save_plugin_config_override

    # 1) 全局配置项：白名单 = CONFIG_LABELS 登记的键
    incoming = payload.get('config') or {}
    for key, value in incoming.items():
        if key not in CONFIG_LABELS:
            result['config']['skipped'].append(key)
            continue
        err = _validate_config_value(key, value, lang)
        if err is not None:
            result['config']['rejected'].append({'key': key, 'message': err[0]})
            continue
        save_config_override(key, value)
        result['config']['applied'].append(key)

    # 2) 插件配置项：白名单 = 当前真的加载成功的插件 + 该插件 plugin_config.py 里声明过的键
    plugins = payload.get('plugins') or {}
    if plugins:
        import os
        from modules.plugins.plugin_loader import load_plugin_config, clear_plugin_config_cache
        loaded = {p.get('name') for p in
                  getattr(app.state, 'plugin_result', {}).get('plugins', [])}
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        for name, kv in plugins.items():
            if name not in loaded or not isinstance(kv, dict):
                result['plugins']['skipped'].append(name)
                continue
            declared = load_plugin_config(name, os.path.join(project_root, 'plugins', name))
            for key, value in kv.items():
                if key not in declared:
                    result['plugins']['skipped'].append(f'{name}.{key}')
                    continue
                save_plugin_config_override(name, key, value)
                result['plugins']['applied'] += 1
        clear_plugin_config_cache()

    # 3) 用户组的限额 / 配额：按 id 对上号才写，对不上（换了库、组被删过）只报告不改，
    #    绝不新建组——组 id 是关联账号、激活码的外键锚点，凭空造一组比不导入更糟
    from modules.database.groups import get_group, update_group
    from modules.database.quotas import normalize_period
    for item in (payload.get('groups') or []):
        if not isinstance(item, dict):
            result['groups']['rejected'].append({'id': None, 'message': t('config.err_item_not_object', lang)})
            continue
        gid = _as_int(item.get('id'))
        if not gid or get_group(gid) is None:
            result['groups']['skipped'].append(item.get('id'))
            continue
        changes = {}
        bad = None
        for field in _GROUP_IMPORT_FIELDS:
            if field not in item or item[field] is None:
                continue
            if field in _GROUP_INT_FIELDS:
                num = _as_int(item[field])
                if num is None or (field != 'max_evkeys' and num < 0):
                    bad = t('config.err_field_invalid', lang, field=field)
                    break
                changes[field] = num
            else:
                changes[field] = normalize_period(item[field])
        if bad:
            result['groups']['rejected'].append({'id': gid, 'message': bad})
            continue
        if changes:
            update_group(gid, **changes)
            result['groups']['applied'] += 1
    return result


@router.get('/api/config/export')
async def admin_config_export(request: Request):
    """把当前配置导出成可迁移的 JSON（配置覆盖 + 插件配置 + 各组限额）"""
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)
    # 导出要查好几张表，且面板点一次就走一次全量
    payload = await asyncio.to_thread(_export_config)
    return JSONResponse(payload)


@router.post('/api/config/import')
async def admin_config_import(request: Request):
    """导入配置包。结构校验 → 白名单过滤 → 批量写回 → 热应用 → 变更摘要"""
    import asyncio
    from modules.database.core import is_db_available
    if not is_db_available():
        return error_response(t_req(request, 'config.db_unavailable'), 400)
    payload = await _body(request)
    if payload is None:
        return error_response(t_req(request, 'msg.bad_json'), 400)
    if payload.get('schema') != CONFIG_SCHEMA:
        return error_response(t_req(request, 'config.err_pkg_schema', schema=CONFIG_SCHEMA), 400)
    version = _as_int(payload.get('version'))
    if version is None or version > CONFIG_SCHEMA_VERSION:
        return error_response(t_req(request, 'config.err_pkg_version', version=CONFIG_SCHEMA_VERSION), 400)

    lang = lang_of(request)
    result = await asyncio.to_thread(_import_config, request.app, payload, lang)

    # 热应用：全部覆盖项一起重算，比逐项 apply_one 少一次 config 模块重载，
    # 也不会出现「A 已生效、B 还是旧值」的中间态（_validate_config_value 已挡下
    # 被运行模式独占的键，这里不必再逐项裁定）
    from modules import config_store
    config_store.reload_and_apply()

    applied = len(result['config']['applied'])
    skipped = result['config']['skipped'] + result['plugins']['skipped'] + result['groups']['skipped']
    rejected = result['config']['rejected'] + result['groups']['rejected']
    message = t('config.imported_summary', lang, config=applied,
                plugins=result['plugins']['applied'], groups=result['groups']['applied'])
    if skipped:
        message += t('config.imported_skipped', lang, n=len(skipped))
    if rejected:
        message += t('config.imported_rejected', lang, n=len(rejected))
    return JSONResponse({'success': True, 'message': message, 'result': result})


@router.get('/api/cache')
async def admin_cache():
    return JSONResponse(cache_stats())

@router.post('/api/cache/clear')
async def admin_clear_cache():
    cache_clear()
    return JSONResponse({'success': True})