"""设备面的数据库读写：设备档案 / 令牌 / 配对会话 / 渲染项。

三张 `device*` 表的 SQL 只写在这一处：`/device/**` 路由、以后的后台「我的设备」、
模拟设备脚本都从这里取数。两处各写一份最容易出的错是「后台配的间隔」与「设备实际
拿到的间隔」对不上，而且不报任何错。

与 [ESP设备集成计划书](file:///d:/Desktop/einkViewsEvo/.trae/documents/ESP设备集成计划书.md)
的一处偏差：本版**没有 device_secret**（计划书里设备轮询 `pair/status` 用的那串）。
地基版把「设备拿配对码」这一步做成需要 evkey，配对在设备侧一次走完，不需要账号面
UI 参与；`secret_hash` 因此存的是配对码的哈希，`pair_code` 明文列留给以后账号面
按码认领时检索（`idx_pair_code` 也是为它建的）。
"""
import datetime
import hashlib
import hmac
import json
import secrets

from modules.database.core import _exec, _exec_many
from modules.utils.timezone import utc_now_iso

# 设备档案里允许被写回的列。白名单而不是黑名单：以后加列时不必回头审查每个写入点，
# 而 `token_hash` / `account_id` 这类身份字段只能走专门的函数改，不许顺手 UPDATE。
# `format` 不在其中：输出格式恒由 `palette` 推导（见 `_derived_format`），不接受外部直写。
_DEVICE_UPDATABLE = {
    'name', 'model', 'width', 'height', 'palette', 'firmware', 'enabled',
    'timezone', 'schedule_type', 'interval_seconds', 'daily_times', 'cron_expr',
    'next_run_at', 'last_seen_at', 'last_status', 'last_error', 'last_ip', 'token_hash',
    'account_id',
}


def _derived_format(palette, fallback='array'):
    """调色板 → 唯一对应的 array 格式。设备只上报支持颜色，格式由它推导。

    映射的唯一来源是 `array_formats.format_for_palette`（从 `PALETTES` 现取），
    未知调色板退回 `fallback`。
    """
    from modules.generate_views.array_formats import format_for_palette
    return format_for_palette(palette) or fallback or 'array'


# 渲染项里允许被写回的列，同一套白名单思路：`device_id` 不许顺手改（搬走渲染项等于
# 越权），归属只能靠外键跟着设备走。
_TASK_UPDATABLE = {'name', 'plugin_name', 'route_path', 'route_kind', 'size',
                   'params_json', 'cache_key', 'sort_order', 'enabled'}


def _dumps(value):
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'


def _parse_iso(text):
    """库里的时间戳 → 带时区的 datetime；读不出来返回 None"""
    value = str(text or '').strip().replace(' ', 'T')
    if not value:
        return None
    if value[-1] in ('Z', 'z'):
        value = value[:-1] + '+00:00'
    try:
        dt = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


# ======================== 设备档案 ========================

def get_device(device_id):
    if not device_id:
        return None
    return _exec('SELECT * FROM devices WHERE id = ?', (device_id,), fetch_one=True)


def get_device_by_hw_uid(hw_uid):
    if not hw_uid:
        return None
    return _exec('SELECT * FROM devices WHERE hw_uid = ?', (hw_uid,), fetch_one=True)


def get_device_by_token_hash(token_hash):
    """按令牌哈希直接查设备（这也是令牌用无盐 sha256 的原因，见 hash_device_token）"""
    if not token_hash:
        return None
    return _exec('SELECT * FROM devices WHERE token_hash = ?', (token_hash,), fetch_one=True)


def create_device(account_id, hw_uid, model='', width=0, height=0, palette='bw',
                  format='', firmware='', name=''):
    """新建设备档案。`account_id` 为 None 表示还没归属账号（配对完成前）。

    输出格式不接受调用方直接给定：设备只上报支持颜色（palette），格式由它推导
    （`_derived_format`）。`format` 参数仅在调色板未知时当兜底值用。
    """
    palette = palette or 'bw'
    return _exec(
        'INSERT INTO devices (account_id, name, model, hw_uid, width, height, palette,'
        ' format, firmware) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (account_id, name, model, hw_uid, int(width or 0), int(height or 0),
         palette, _derived_format(palette, format), firmware or ''),
        commit=True,
    )


def update_device(device_id, **fields):
    """按白名单更新设备档案；没有可写的键就直接返回（未知键静默丢弃）

    传了 `palette` 就顺带把 `format` 重算回去——格式恒由调色板推导，不接受外部直写。
    """
    sets = {k: v for k, v in fields.items() if k in _DEVICE_UPDATABLE}
    if 'palette' in sets:
        sets['format'] = _derived_format(sets['palette'])
    if not device_id or not sets:
        return
    clauses = ', '.join(f'{k} = ?' for k in sets)
    _exec(f'UPDATE devices SET {clauses} WHERE id = ?',
          tuple(sets.values()) + (device_id,), commit=True)


def set_device_token(device_id, token):
    """写入新令牌的哈希（更换 / 重置令牌都走这里，明文只在响应里出现一次）"""
    if not device_id or not token:
        return
    update_device(device_id, token_hash=hash_device_token(token))


def touch_device(device_id, status='', error='', ip='', firmware=''):
    """记一次设备回连：心跳时间、状态、错误、来源 IP、固件版本。

    全是**诊断字段**：不驱动任何服务端任务，也不参与排期计算（间隔由纯函数现算后下发，
    计时器在设备上）。心跳时间只用来告诉面板「这台设备最后什么时候来过」。
    """
    fields = {'last_seen_at': utc_now_iso(), 'last_status': status or '',
              'last_error': error or '', 'last_ip': ip or ''}
    if firmware:
        fields['firmware'] = firmware
    update_device(device_id, **fields)


def list_devices_for_account(account_id):
    if not account_id:
        return []
    return _exec('SELECT * FROM devices WHERE account_id = ? ORDER BY id',
                 (account_id,), fetch_all=True)


def count_devices_for_account(account_id):
    row = _exec('SELECT COUNT(*) AS cnt FROM devices WHERE account_id = ?',
                (account_id,), fetch_one=True)
    return int(row['cnt']) if row else 0


def delete_device(device_id):
    """解除配对：连带删掉渲染项与配对会话（devices 上只有 tasks 有外键）"""
    if not device_id:
        return
    _exec('DELETE FROM device_tasks WHERE device_id = ?', (device_id,), commit=True)
    _exec('DELETE FROM device_pairings WHERE device_id = ?', (device_id,), commit=True)
    _exec('DELETE FROM devices WHERE id = ?', (device_id,), commit=True)


# ======================== 设备共享 ========================
# 属主把设备共享给其他账号协作：被共享者可共同编辑设备的设置与渲染项，但不能删除设备或
# 改变归属（那条判定在账号面路由层）。共享**不改变 devices.account_id**，只在本表记
# 「谁共享给了谁」，所以共享进来的设备不会占接收方名额（名额只算自有的，见
# count_devices_for_account）。

def share_device(device_id, account_id):
    """把设备共享给某个账号；返回受影响行数（0 = 之前已共享过）。"""
    if not device_id or not account_id:
        return 0
    return _exec('INSERT OR IGNORE INTO device_shares (device_id, account_id) VALUES (?, ?)',
                 (device_id, account_id), commit=True, rowcount=True)


def unshare_device(device_id, account_id):
    """解除一条共享；返回受影响行数（0 = 本来就没有这条共享）。"""
    if not device_id or not account_id:
        return 0
    return _exec('DELETE FROM device_shares WHERE device_id = ? AND account_id = ?',
                 (device_id, account_id), commit=True, rowcount=True)


def is_device_shared_with(device_id, account_id):
    """该设备是否被共享给了这个账号（**不含**属主判断）。"""
    if not device_id or not account_id:
        return False
    row = _exec('SELECT 1 FROM device_shares WHERE device_id = ? AND account_id = ?',
                (device_id, account_id), fetch_one=True)
    return row is not None


def is_device_editable_by(device_id, account_id):
    """设备是否可被该账号编辑：属主本人，或被共享给了该账号。"""
    device = get_device(device_id)
    if not device:
        return False
    if device.get('account_id') == account_id:
        return True
    return is_device_shared_with(device_id, account_id)


def list_shares_for_device(device_id):
    """一台设备当前共享给了哪些账号，带账号名（供详情展示「共享给 XX」）。"""
    if not device_id:
        return []
    return _exec(
        'SELECT s.account_id, a.name AS account_name, s.created_at '
        'FROM device_shares s LEFT JOIN accounts a ON a.id = s.account_id '
        'WHERE s.device_id = ? ORDER BY s.id',
        (device_id,), fetch_all=True)


def list_devices_shared_with_account(account_id):
    """共享给某账号的设备（每行即 devices 行，额外带 shared_by_id / shared_by_name）。
    shared_by_* 指的是**共享者**（即设备属主），供列表展示「由 XX 共享」。"""
    if not account_id:
        return []
    return _exec(
        'SELECT d.*, d.account_id AS shared_by_id, a.name AS shared_by_name '
        'FROM device_shares s JOIN devices d ON d.id = s.device_id '
        'LEFT JOIN accounts a ON a.id = d.account_id '
        'WHERE s.account_id = ? ORDER BY d.id',
        (account_id,), fetch_all=True)


def get_device_owner_name(device_id):
    """设备属主的账号名（被共享方在详情里显示「由 XX 共享」用）"""
    if not device_id:
        return ''
    row = _exec('SELECT a.name AS name FROM devices d LEFT JOIN accounts a ON a.id = d.account_id '
                'WHERE d.id = ?', (device_id,), fetch_one=True)
    return (row.get('name') or '') if row else ''


def list_devices_owned_and_shared(account_id):
    """某账号的设备目录 = 自有的 ∪ 共享进来的（管理端「账号详情 → 设备」标签用）。
    每行带 `owner`（1/0）与 `shared_by_id` / `shared_by_name`（仅共享进来的行有值）。"""
    if not account_id:
        return []
    owned = _exec(
        'SELECT d.*, 1 AS owner, NULL AS shared_by_id, NULL AS shared_by_name '
        'FROM devices d WHERE d.account_id = ? ORDER BY d.id',
        (account_id,), fetch_all=True)
    shared = _exec(
        'SELECT d.*, 0 AS owner, d.account_id AS shared_by_id, a.name AS shared_by_name '
        'FROM device_shares s JOIN devices d ON d.id = s.device_id '
        'LEFT JOIN accounts a ON a.id = d.account_id '
        'WHERE s.account_id = ? ORDER BY d.id',
        (account_id,), fetch_all=True)
    return list(owned) + list(shared)


def group_max_devices(group_id):
    """用户组可挂设备数上限：-1 = 不限，0 = 禁止绑定，N = 最多 N 台；组不存在按 0。

    与 `applications.group_max_evkeys` 同一套口径、同一个理由：管理组一律折算成 -1，
    免得管理员在紧急情况下反而绑不上设备。折算发生在读取侧，不把库里的值改掉——
    改库既歧义（0 在限额语义里是「禁止」），又会被后来的人当成可调项再改回去。
    """
    row = _exec('SELECT max_devices, category FROM user_groups WHERE id = ?',
                (group_id,), fetch_one=True)
    if not row:
        return 0
    from modules.database.groups import is_admin_category
    if is_admin_category(row.get('category')):
        return -1
    return int(row['max_devices'] or 0)


def bind_device_to_account(hw_uid, account_id, payload=None):
    """认领时把设备行预绑到账号名下，返回 `device_id`。

    **不签发令牌**：明文令牌只能在设备轮询 `/device/pair` 时出现一次，库里只存哈希
    （见 `set_device_token`）。因此认领只是「先把归属与屏幕参数定下来」，设备下次
    来换令牌时直接拿这条已绑好的档案。

    设备行通常已经存在（`/device/register` 时以匿名身份建过），此时更新而不是新建，
    沿用与 `/device/pair` 一致的口径：屏幕参数以设备自报为准。
    """
    payload = payload or {}
    device = get_device_by_hw_uid(hw_uid)
    if device is None:
        return create_device(account_id, hw_uid, payload.get('model', ''),
                             payload.get('width', 0), payload.get('height', 0),
                             payload.get('palette') or 'bw',
                             firmware=payload.get('firmware', ''))
    update_device(device['id'], account_id=account_id, model=payload.get('model', ''),
                  width=payload.get('width', 0), height=payload.get('height', 0),
                  palette=payload.get('palette') or 'bw', firmware=payload.get('firmware', ''))
    return device['id']


def device_quota_error(account_id, hw_uid):
    """用户组设备名额校验：超额时返回提示文案，否则 None；账号不存在抛 `AccessDeniedError`。

    与 `group_max_evkeys` 同一套口径：-1 = 不限、0 = 禁止绑定、N = 最多 N 台（管理组
    折算成 -1，见 `group_max_devices`）。**已经属于本账号**的设备不重复占名额——
    否则改一次设置就会把自己挡在门外。

    判定写在 store 里而不是路由里：`/device/pair` 与账号面「输入配对码认领」都要用它，
    两处各写一遍必然走偏，而且是「一边拒一边放」的那种走偏。
    """
    existing = get_device_by_hw_uid(hw_uid)
    if existing and existing.get('account_id') == account_id:
        return None
    from modules.database.accounts import get_account_by_id
    from modules.errors.errors import AccessDeniedError
    account = get_account_by_id(account_id)
    if not account:
        raise AccessDeniedError('设备所属账号已被禁用或删除')
    limit = group_max_devices(account.get('group_id'))
    if limit == -1:
        return None
    used = count_devices_for_account(account_id)
    if used >= limit:
        return f'当前用户组最多绑定 {limit} 台设备，请先解绑其它设备或联系管理员'
    return None


# ======================== 令牌 ========================

TOKEN_PREFIX = 'dev_'
_TOKEN_BYTES = 32


def new_device_token():
    """设备令牌：`dev_` + 32 字节随机（URL 安全 base64）"""
    return TOKEN_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)


def hash_device_token(token):
    """令牌 → 库里的存储值。

    无盐 sha256：令牌是 32 字节随机串（256 位熵），不存在被字典 / 彩虹表命中的可能，
    因此不需要 pbkdf2 那套加盐慢哈希（账号密码才需要——人选的口令熵很低）。
    反过来，无盐才能给 `token_hash` 建索引按哈希直接查设备；加盐后同一令牌每次哈希都
    不同，只能全表扫。
    """
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def verify_device_token(device_row, token):
    """定长比较：`==` 会在第一个不同字节处短路、逐字节泄露前缀信息"""
    stored = (device_row or {}).get('token_hash') or ''
    if not stored or not token:
        return False
    try:
        return hmac.compare_digest(hash_device_token(token), stored)
    except Exception:
        return False


# ======================== 配对会话 ========================

# 去混淆字母表（Crockford Base32 去掉 I / L / O / U）：这串码要画在墨水屏上、由用户
# 手动敲进网页，`0/O`、`1/I/L` 这类同形字符少一个是一个坑。
_PAIR_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
# 用户把同形字符敲错时做一次归一：O→0、I/L→1、U→V，然后才拿去比对
_PAIR_CONFUSABLE = {'O': '0', 'I': '1', 'L': '1', 'U': 'V'}
PAIR_CODE_LEN = 8


def new_pair_code():
    return ''.join(secrets.choice(_PAIR_ALPHABET) for _ in range(PAIR_CODE_LEN))


def normalize_pair_code(code):
    """用户输入 → 比对用的规范形式：转大写、纠正同形字符、丢掉无关字符"""
    out = []
    for char in str(code or '').upper():
        char = _PAIR_CONFUSABLE.get(char, char)
        if char in _PAIR_ALPHABET:
            out.append(char)
    return ''.join(out)


def format_pair_code(code):
    """展示用 `XXXX-XXXX`；连字符只作视觉分组，不参与比对"""
    text = str(code or '').upper()
    return f'{text[:4]}-{text[4:]}' if len(text) > 4 else text


def create_pairing(hw_uid, payload, account_id=None, ttl_seconds=600):
    """建一条配对会话，返回 `(pair_id, pair_code)`。

    顺带清掉早就过期的历史会话：本项目没有设备排期 worker（计时器在设备上），
    这类垃圾没有别的地方会清，靠每次新建时顺带删一次，量级恒定。
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(seconds=int(ttl_seconds or 0))
    purge_expired_pairings(now)
    pair_id = secrets.token_urlsafe(16)
    pair_code = new_pair_code()
    _exec(
        'INSERT INTO device_pairings (id, hw_uid, pair_code, secret_hash, payload_json,'
        ' account_id, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (pair_id, hw_uid, pair_code, hash_device_token(pair_code), _dumps(payload),
         account_id, 'pending', utc_now_iso(), expires.isoformat().replace('+00:00', 'Z')),
        commit=True,
    )
    return pair_id, pair_code


def get_pairing(pair_id):
    if not pair_id:
        return None
    return _exec('SELECT * FROM device_pairings WHERE id = ?', (pair_id,), fetch_one=True)


def get_pending_pairing_by_code(pair_code):
    """按配对码找待认领的会话（账号面「输入配对码认领」用；地基版还没有入口调它）"""
    code = normalize_pair_code(pair_code)
    if not code:
        return None
    return _exec("SELECT * FROM device_pairings WHERE pair_code = ? AND status = 'pending'"
                 ' ORDER BY created_at DESC LIMIT 1', (code,), fetch_one=True)


def verify_pairing_code(pairing, pair_code):
    """定长比较配对码；空值一律 False"""
    stored = (pairing or {}).get('secret_hash') or ''
    code = normalize_pair_code(pair_code)
    if not stored or not code:
        return False
    try:
        return hmac.compare_digest(hash_device_token(code), stored)
    except Exception:
        return False


def is_pairing_expired(pairing, now=None):
    """过期判定放在读取侧，不依赖任何定时清理。读不出有效期时按已过期处理（fail-closed）：
    宁可让设备重新出一次码，也不让一条读不出有效期的会话继续换令牌。
    """
    expires = _parse_iso((pairing or {}).get('expires_at'))
    if expires is None:
        return True
    return (now or datetime.datetime.now(datetime.timezone.utc)) >= expires


def record_pairing_attempt(pair_id):
    """配对码错一次：累加 attempts 并返回累加后的值（调用方据此决定是否作废）"""
    if not pair_id:
        return 0
    _exec('UPDATE device_pairings SET attempts = attempts + 1 WHERE id = ?',
          (pair_id,), commit=True)
    row = _exec('SELECT attempts FROM device_pairings WHERE id = ?', (pair_id,), fetch_one=True)
    return int(row['attempts']) if row else 0


def set_pairing_status(pair_id, status, device_id=None):
    if not pair_id:
        return
    if device_id is None:
        _exec('UPDATE device_pairings SET status = ? WHERE id = ?', (status, pair_id), commit=True)
        return
    _exec('UPDATE device_pairings SET status = ?, device_id = ? WHERE id = ?',
          (status, device_id, pair_id), commit=True)


def attach_pairing_account(pair_id, account_id, device_id=None):
    """把归属写进配对会话并绑上设备行；返回是否写中。

    条件写（`status = 'pending'`）是刻意的：两次认领撞在一起时，只有先到的那次能写中，
    后到的拿到 False 去报冲突。若不加条件，后到的会静默改掉归属，先认领的人
    「刚认领完设备就不见了」，而且没有任何地方会报错。
    """
    if not pair_id or not account_id:
        return False
    rows = _exec(
        "UPDATE device_pairings SET account_id = ?, device_id = COALESCE(?, device_id)"
        " WHERE id = ? AND status = 'pending'",
        (account_id, device_id, pair_id), commit=True, rowcount=True)
    return bool(rows)


def cancel_other_pairings(hw_uid, keep_pair_id):
    """同一台设备的其它待认领会话置 `rejected`，返回作废条数。

    不清理的话：设备重新出码后旧码仍然可用（两条 pending 并存），旧码被别的账号认领
    就会把设备归属改走。保留 `keep_pair_id` 是因为认领流程要在同一个事务序列里
    确认最新那条仍然 pending。
    """
    if not hw_uid:
        return 0
    rows = _exec(
        "UPDATE device_pairings SET status = 'rejected'"
        " WHERE hw_uid = ? AND id != ? AND status = 'pending'",
        (hw_uid, keep_pair_id or ''), commit=True, rowcount=True)
    return int(rows or 0)


def purge_expired_pairings(now=None, keep_seconds=86400):
    """删掉「过期已经超过 keep_seconds」的会话。留一天是为了让面板还能看到刚过期的
    那条记录（用户报「配对码填了没用」时，能看到它其实已经超时了），再久就没意义了。
    """
    cutoff = (now or datetime.datetime.now(datetime.timezone.utc)) \
        - datetime.timedelta(seconds=int(keep_seconds or 0))
    _exec('DELETE FROM device_pairings WHERE expires_at < ?',
          (cutoff.isoformat().replace('+00:00', 'Z'),), commit=True)


# ======================== 渲染项 ========================

def list_device_tasks(device_id, only_enabled=False):
    if not device_id:
        return []
    sql = 'SELECT * FROM device_tasks WHERE device_id = ?'
    if only_enabled:
        sql += ' AND enabled = 1'
    return _exec(sql + ' ORDER BY sort_order, id', (device_id,), fetch_all=True)


def get_device_task(task_id):
    if not task_id:
        return None
    return _exec('SELECT * FROM device_tasks WHERE id = ?', (task_id,), fetch_one=True)


def current_device_task(device_id):
    """当前该显示的那一项。地基版只取第一项：多视图轮播（按时段 / 顺序切换）留到下一轮，
    这里先把「一台设备至少有一项可渲染」的链路打通。
    """
    rows = list_device_tasks(device_id, only_enabled=True)
    return rows[0] if rows else None


def create_device_task(device_id, plugin_name, route_path, name='', route_kind='view',
                       size='', params=None, cache_key='', sort_order=0, enabled=1):
    return _exec(
        'INSERT INTO device_tasks (device_id, name, plugin_name, route_path, route_kind,'
        ' size, params_json, cache_key, sort_order, enabled)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (device_id, name, plugin_name, route_path, route_kind, size,
         _dumps(params or {}), cache_key, int(sort_order or 0), 1 if enabled else 0),
        commit=True,
    )


def update_device_task(task_id, **fields):
    """按白名单更新渲染项；未知键静默丢弃（与 `update_device` 同一口径）。

    `params_json` 由调用方自己 `json.dumps`：这里只做白名单过滤，不做序列化，
    免得「传了 dict」和「传了字符串」两种写法在这层被悄悄统一成一种。
    """
    sets = {k: v for k, v in fields.items() if k in _TASK_UPDATABLE}
    if not task_id or not sets:
        return
    clauses = ', '.join(f'{k} = ?' for k in sets)
    _exec(f'UPDATE device_tasks SET {clauses} WHERE id = ?',
          tuple(sets.values()) + (task_id,), commit=True)


def reorder_device_tasks(device_id, ordered_ids):
    """按给定 id 顺序重写 `sort_order`；**只动本设备的行**。

    不认识的 id、别的设备的 id、重复的 id 一律跳过——排序接口是越权改写 `sort_order`
    最顺手的地方，这里拒掉就不会把别人的渲染项排到自己前面。
    """
    if not device_id or not ordered_ids:
        return
    own = {int(row['id']) for row in list_device_tasks(device_id)}
    order = []
    for raw in ordered_ids:
        try:
            task_id = int(raw)
        except (TypeError, ValueError):
            continue
        if task_id in own and task_id not in order:
            order.append(task_id)
    if not order:
        return
    _exec_many([
        ('UPDATE device_tasks SET sort_order = ? WHERE id = ? AND device_id = ?',
         (pos, task_id, device_id)) for pos, task_id in enumerate(order, start=1)
    ])


def delete_device_task(task_id):
    _exec('DELETE FROM device_tasks WHERE id = ?', (task_id,), commit=True)


def load_task_params(task_row):
    """渲染项的 `params_json` → dict。坏值一律当空字典：一条脏数据不该把取图链路打挂"""
    raw = (task_row or {}).get('params_json')
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
