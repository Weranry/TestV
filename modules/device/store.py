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
import random
import secrets

from modules.database.core import _exec, _exec_many, _delete_batched
from modules.utils.timezone import utc_now_iso

# 设备档案里允许被写回的列。白名单而不是黑名单：以后加列时不必回头审查每个写入点，
# 而 `token_hash` / `account_id` 这类身份字段只能走专门的函数改，不许顺手 UPDATE。
# `format` 不在其中：输出格式恒由「颜色降级值或设备上报的 palette」推导（见 `_derived_format`），
# 不接受外部直写。`palette` 是设备上报值，`palette_override` 才是用户可改的降级选项。
_DEVICE_UPDATABLE = {
    'name', 'model', 'width', 'height', 'palette', 'palette_override', 'firmware', 'enabled',
    'timezone', 'schedule_type', 'interval_seconds', 'daily_times', 'cron_expr',
    'next_run_at', 'last_seen_at', 'last_status', 'last_error', 'last_ip', 'token_hash',
    'account_id', 'carousel_index', 'carousel_mode', 'battery_mv', 'rssi', 'wake_ms',
    'refresh_count', 'offline_alerted',
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


def default_device_name(hw_uid):
    """设备默认名 = 硬件指纹去掉分隔符（MAC `A0:B1:...` → `A0B1...`）。

    设备侧一律用 MAC 当指纹，用户不填名字时直接拿它当名字：界面上不会出现一串
    空白或「未命名设备」，而 MAC 本身又是排障时最常要的那条信息。
    """
    return ''.join(ch for ch in str(hw_uid or '') if ch.isalnum())[:64]


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
        (account_id, name or default_device_name(hw_uid), model, hw_uid,
         int(width or 0), int(height or 0),
         palette, _derived_format(palette, format), firmware or ''),
        commit=True,
    )


def update_device(device_id, **fields):
    """按白名单更新设备档案；没有可写的键就直接返回（未知键静默丢弃）

    传了 `palette`（设备上报）或 `palette_override`（用户降级）就顺带把 `format`
    重算回去：格式恒由「降级值优先，否则上报值」推导，不接受外部直写。只传其一时
    从库里补另一项，避免把用户的降级选择冲掉。
    """
    sets = {k: v for k, v in fields.items() if k in _DEVICE_UPDATABLE}
    if 'palette' in sets or 'palette_override' in sets:
        palette = sets.get('palette')
        override = sets.get('palette_override')
        if palette is None or override is None:
            row = get_device(device_id) or {}
            if palette is None:
                palette = row.get('palette') or 'bw'
            if override is None:
                override = row.get('palette_override') or ''
        sets['format'] = _derived_format(override or palette)
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

    回连同时把 `offline_alerted` 清零：离线告警只对「一次连续离线」发一次，
    设备回来后再次掉线要能重新触发。
    """
    fields = {'last_seen_at': utc_now_iso(), 'last_status': status or '',
              'last_error': error or '', 'last_ip': ip or '', 'offline_alerted': 0}
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


def list_account_devices_overview():
    """设备总列表（管理端「设备 → 设备总列表」）的数据源：每个账号一行。

    设备数只算**自有**（共享进来的不占名额，与 `count_devices_for_account` 同口径）；
    上限取自所属用户组，并在读取侧折算成 `-1 = 不限 / 0 = 禁止 / N = 最多 N 台`
    （管理组恒为 -1，组不存在按 0），与 `group_max_devices` 同一套语义。
    """
    from modules.database.groups import is_admin_category
    rows = _exec(
        'SELECT a.id AS account_id, a.uid AS account_uid, a.name AS account_name, a.group_id AS group_id,'
        ' g.name AS group_name, g.category AS group_category, g.max_devices AS group_max_devices,'
        ' (SELECT COUNT(*) FROM devices d WHERE d.account_id = a.id) AS device_count'
        ' FROM accounts a LEFT JOIN user_groups g ON g.id = a.group_id'
        ' ORDER BY a.id',
        fetch_all=True)
    out = []
    for row in rows:
        item = dict(row)
        if is_admin_category(row.get('group_category')):
            item['max_devices'] = -1
        elif row.get('group_id') is None:
            item['max_devices'] = 0
        else:
            item['max_devices'] = int(row.get('group_max_devices') or 0)
        out.append(item)
    return out


def delete_device(device_id):
    """解除配对：连带删掉渲染项与配对会话（遥测历史由外键级联清理）"""
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
    update_fields = dict(account_id=account_id, model=payload.get('model', ''),
                         width=payload.get('width', 0), height=payload.get('height', 0),
                         palette=payload.get('palette') or 'bw',
                         firmware=payload.get('firmware', ''))
    # 老档案（默认名为空）在认领时补齐成 MAC，与新建设备的口径一致
    if not str(device.get('name') or '').strip():
        update_fields['name'] = default_device_name(hw_uid)
    update_device(device['id'], **update_fields)
    return device['id']


def device_quota_error(account_id, hw_uid):
    """用户组设备名额校验：放行返回 None，超额返回 `(取词键, 格式化参数)`；
    账号不存在抛 `AccessDeniedError`。

    与 `group_max_evkeys` 同一套口径：-1 = 不限、0 = 禁止绑定、N = 最多 N 台（管理组
    折算成 -1，见 `group_max_devices`）。**已经属于本账号**的设备不重复占名额——
    否则改一次设置就会把自己挡在门外。

    判定写在 store 里而不是路由里：`/device/pair` 与账号面「输入配对码认领」都要用它，
    两处各写一遍必然走偏，而且是「一边拒一边放」的那种走偏。

    超额时回的是取词键而不是成品文案：中英切换归请求侧管，store 层不认语言。键跟着判定
    一起放在这儿，三条调用路径的口径与措辞才不会有别的走法（0 上限得说「不允许绑定」，
    不能念成「上限 0 台」）。
    """
    existing = get_device_by_hw_uid(hw_uid)
    if existing and existing.get('account_id') == account_id:
        return None
    from modules.database.accounts import get_account_by_id
    from modules.errors.errors import AccessDeniedError
    account = get_account_by_id(account_id)
    if not account:
        raise AccessDeniedError('device.err_owner_gone')
    limit = group_max_devices(account.get('group_id'))
    if limit == -1:
        return None
    used = count_devices_for_account(account_id)
    if used >= limit:
        if limit <= 0:
            return ('account.dev_no_bind', {})
        return ('account.dev_limit_detail', {'cur': used, 'max': limit})
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


def create_pairing(hw_uid, payload, account_id=None, ttl_seconds=600, idempotency_key=''):
    """建一条配对会话，返回 `(pair_id, pair_code)`。

    顺带清掉早就过期的历史会话：本项目没有设备排期 worker（计时器在设备上），
    这类垃圾没有别的地方会清，靠每次新建时顺带删一次，量级恒定。
    `idempotency_key` 由设备重试时带上，配合 `get_pairing_by_idempotency` 复用同一组码。
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(seconds=int(ttl_seconds or 0))
    purge_expired_pairings(now)
    pair_id = secrets.token_urlsafe(16)
    pair_code = new_pair_code()
    _exec(
        'INSERT INTO device_pairings (id, hw_uid, pair_code, secret_hash, payload_json,'
        ' account_id, status, idempotency_key, created_at, expires_at)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (pair_id, hw_uid, pair_code, hash_device_token(pair_code), _dumps(payload),
         account_id, 'pending', idempotency_key or '', utc_now_iso(),
         expires.isoformat().replace('+00:00', 'Z')),
        commit=True,
    )
    return pair_id, pair_code


def get_pairing_by_idempotency(hw_uid, idempotency_key):
    """同一台设备 + 同一个幂等键的待认领会话；找不到或已过期返回 None。"""
    if not hw_uid or not idempotency_key:
        return None
    row = _exec(
        "SELECT * FROM device_pairings WHERE hw_uid = ? AND idempotency_key = ?"
        " AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (hw_uid, idempotency_key), fetch_one=True)
    if not row or is_pairing_expired(row):
        return None
    return row


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


# ======================== 设备签入审批 ========================
# 关闭「自动加入」后，用户在网页输入配对码认领设备不再当场绑定，而是落一条待审批记录，
# 管理员在「设备 → 设备签入审批」里批准（或拒绝）才生效。审批通过后仍走认领那套绑定
# 动作（bind_device_to_account + attach_pairing_account + cancel_other_pairings，在路由层）。

_SIGNIN_STATUSES = ('pending', 'approved', 'rejected')


def create_signin(account_id, hw_uid, pair_id='', payload=None):
    """创建一条待审批的签入记录，返回 signin_id。

    同一账号 + 同一 hw_uid 已有 pending 时直接复用（幂等）：用户反复输码不该堆出一串重复
    申请，管理员也不该面对同台设备的多条待办。
    """
    if not account_id or not hw_uid:
        return 0
    existing = _exec(
        "SELECT id FROM device_signins WHERE account_id = ? AND hw_uid = ? AND status = 'pending'",
        (account_id, hw_uid), fetch_one=True)
    if existing:
        return int(existing['id'])
    return _exec(
        'INSERT INTO device_signins (account_id, hw_uid, pair_id, payload_json)'
        ' VALUES (?, ?, ?, ?)',
        (account_id, hw_uid, pair_id or '', _dumps(payload or {})), commit=True)


def get_signin(signin_id):
    if not signin_id:
        return None
    return _exec('SELECT * FROM device_signins WHERE id = ?', (signin_id,), fetch_one=True)


def list_pending_signins():
    """待审批签入列表（按账号聚合所需字段）：新到排前头，并带账号名与设备示意名。"""
    return _exec(
        'SELECT s.*, a.uid AS account_uid, a.name AS account_name, g.name AS group_name,'
        ' (SELECT COALESCE(NULLIF(d.name, ""), d.model) FROM devices d WHERE d.hw_uid = s.hw_uid)'
        ' AS device_name'
        ' FROM device_signins s'
        ' LEFT JOIN accounts a ON a.id = s.account_id'
        ' LEFT JOIN user_groups g ON g.id = a.group_id'
        " WHERE s.status = 'pending' ORDER BY s.id DESC",
        fetch_all=True)


def count_pending_signins():
    row = _exec("SELECT COUNT(*) AS cnt FROM device_signins WHERE status = 'pending'",
                fetch_one=True)
    return int(row['cnt']) if row else 0


def set_signin_status(signin_id, status, note='', admin_name=''):
    """置审批结果（仅 pending 可改，条件写避免两次审批互相覆盖）；返回是否写中。"""
    if status not in _SIGNIN_STATUSES or not signin_id:
        return False
    rows = _exec(
        "UPDATE device_signins SET status = ?, note = ?, admin_name = ?"
        " WHERE id = ? AND status = 'pending'",
        (status, note or '', admin_name or '', signin_id), commit=True, rowcount=True)
    return bool(rows)


def reject_pending_signins_for_device(hw_uid, note='', admin_name=''):
    """把某台设备（按 hw_uid）所有待审批签入置为 rejected，返回条数。

    删设备时必须调用：`device_signins` 没有 devices 外键，删设备后这些 pending 会按
    hw_uid 残留，下一次批准又会按同一个 hw_uid 把设备「复活」出来。批量置 rejected
    而不是逐条 `set_signin_status`（后者只改一条，需要先查 id 列表反而更绕）。
    """
    if not hw_uid:
        return 0
    rows = _exec(
        "UPDATE device_signins SET status = 'rejected', note = ?, admin_name = ?"
        " WHERE hw_uid = ? AND status = 'pending'",
        (note or '', admin_name or '', hw_uid), commit=True, rowcount=True)
    return int(rows or 0)


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
    """当前该显示的那一项：按 `sort_order` 轮播，游标存在 `devices.carousel_index`。

    游标是「第几项」而不是任务 id：渲染项被删 / 重排后 id 会失效，按下标取模则永远落在
    现有列表内。只有一项时恒取它（不推进游标，见 `advance_device_carousel`）。
    随机轮播不读游标：每次取图都从启用项里随机挑一条。
    """
    rows = list_device_tasks(device_id, only_enabled=True)
    if not rows:
        return None
    device = get_device(device_id)
    if str((device or {}).get('carousel_mode') or 'sequence') == 'random':
        return random.choice(rows)
    try:
        index = int((device or {}).get('carousel_index') or 0)
    except (TypeError, ValueError):
        index = 0
    return rows[index % len(rows)]


def advance_device_carousel(device_id):
    """轮播推进一格（取图成功后调用）；返回下一项的序号。

    取模写回而不是无限累加：库里的游标始终落在 `0..n-1`，重排 / 增删渲染项后
    不需要额外校正，也不会把整数撑爆。只有一项时归零。
    """
    if not device_id:
        return 0
    device = get_device(device_id)
    if str((device or {}).get('carousel_mode') or 'sequence') == 'random':
        return int((device or {}).get('carousel_index') or 0)
    rows = list_device_tasks(device_id, only_enabled=True)
    if not rows:
        update_device(device_id, carousel_index=0)
        return 0
    try:
        current = int((device or {}).get('carousel_index') or 0)
    except (TypeError, ValueError):
        current = 0
    nxt = (current + 1) % len(rows)
    update_device(device_id, carousel_index=nxt)
    return nxt


def save_device_telemetry(device_id, battery_mv=0, rssi=0, wake_ms=0,
                          refresh_count=0, firmware=''):
    """落一条遥测：历史追加 + 设备档案上的快照列更新 + 记一次心跳。

    快照列只为列表/详情直接读，不 join 历史表；历史表供以后画曲线与排查。
    数值全部由路由层钳过范围，这里不再二次校验。
    """
    if not device_id:
        return 0
    row_id = _exec(
        'INSERT INTO device_telemetry (device_id, battery_mv, rssi, wake_ms,'
        ' refresh_count, firmware) VALUES (?, ?, ?, ?, ?, ?)',
        (device_id, int(battery_mv or 0), int(rssi or 0), int(wake_ms or 0),
         int(refresh_count or 0), firmware or ''),
        commit=True,
    )
    fields = {'battery_mv': int(battery_mv or 0), 'rssi': int(rssi or 0),
              'wake_ms': int(wake_ms or 0), 'refresh_count': int(refresh_count or 0)}
    if firmware:
        fields['firmware'] = firmware
    update_device(device_id, **fields)
    # 上报本身就是一次存活证据：没走 status/image 的设备也能把 last_seen 刷新、
    # 把离线告警标记清掉。
    touch_device(device_id, 'telemetry', '', '', firmware or '')
    return row_id


def list_device_telemetry(device_id, limit=20):
    """某设备最近的遥测（新的在前），供详情弹窗展示历史。"""
    if not device_id:
        return []
    try:
        limit = max(1, min(int(limit or 20), 200))
    except (TypeError, ValueError):
        limit = 20
    return _exec(
        'SELECT * FROM device_telemetry WHERE device_id = ? ORDER BY id DESC LIMIT ?',
        (device_id, limit), fetch_all=True)


def trim_device_telemetry(device_id, keep=200):
    """只保留某设备最近 N 条遥测，避免历史表无限膨胀（删除用子查询，一次一条语句）。"""
    if not device_id:
        return
    try:
        keep = max(1, int(keep or 200))
    except (TypeError, ValueError):
        keep = 200
    _exec(
        'DELETE FROM device_telemetry WHERE device_id = ? AND id NOT IN'
        ' (SELECT id FROM device_telemetry WHERE device_id = ? ORDER BY id DESC LIMIT ?)',
        (device_id, device_id, keep), commit=True)


def prune_device_telemetry(days):
    """删除超过保留期的遥测记录（0 = 不清理），返回删除条数。

    与请求日志的保留期清理同一套分批语义：单条大 DELETE 会长时间占住全局锁。
    """
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        return 0
    if days <= 0:
        return 0
    return _delete_batched(
        'DELETE FROM device_telemetry WHERE id IN ('
        "SELECT id FROM device_telemetry WHERE created_at < datetime('now', ?) LIMIT ?)",
        (f'-{days} days',),
    )


def set_device_last_image(device_id, path, etag, mime, name):
    """记录最近一张成功图片的位置与 ETag，供渲染失败回退 / 304 复用。

    这是一组派生字段，不放进 `_DEVICE_UPDATABLE`：面板/接口的普通「改设备」
    不应该能改写它，否则回退会指向任意路径。
    """
    if not device_id:
        return
    _exec(
        'UPDATE devices SET last_image_path = ?, last_image_etag = ?,'
        ' last_image_mime = ?, last_image_name = ? WHERE id = ?',
        (path or '', etag or '', mime or '', name or '', device_id), commit=True)


def get_idempotent_response(idem_key, scope, ttl_seconds=86400):
    """取一条未过期的幂等响应；没有/过期返回 None。

    只缓存 register / pair-request 这类**不含令牌**的响应，所以可以直接存 JSON。
    """
    if not idem_key or not scope:
        return None
    row = _exec(
        'SELECT response_json, created_at FROM device_idempotency'
        ' WHERE idem_key = ? AND scope = ?', (idem_key, scope), fetch_one=True)
    if not row:
        return None
    created = _parse_iso(row.get('created_at'))
    if created is None:
        return None
    ttl = max(0, int(ttl_seconds or 0))
    if ttl and (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() > ttl:
        _exec('DELETE FROM device_idempotency WHERE idem_key = ?', (idem_key,), commit=True)
        return None
    try:
        value = json.loads(row.get('response_json') or '{}')
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def save_idempotent_response(idem_key, scope, payload, ttl_seconds=86400):
    """写入/覆盖幂等响应，并顺手清掉过期行（没有定时任务，借写入点做清理）。"""
    if not idem_key or not scope:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    ttl = max(0, int(ttl_seconds or 0))
    if ttl:
        cutoff = (now - datetime.timedelta(seconds=ttl)).isoformat().replace('+00:00', 'Z')
        _exec('DELETE FROM device_idempotency WHERE created_at < ?', (cutoff,), commit=True)
    _exec(
        'INSERT OR REPLACE INTO device_idempotency (idem_key, scope, response_json, created_at)'
        ' VALUES (?, ?, ?, ?)',
        (idem_key, scope, _dumps(payload), utc_now_iso()), commit=True)


def list_offline_devices(threshold_iso):
    """判为离线、且本轮还没告过警的设备。

    只算已配对（有令牌、有账号）、启用且**曾经上线过**的设备：从未上线的设备
    `last_seen_at` 为空，算进离线会让刚创建的档案立刻报「掉线」。
    """
    if not threshold_iso:
        return []
    return _exec(
        'SELECT d.*, a.name AS account_name FROM devices d'
        ' LEFT JOIN accounts a ON a.id = d.account_id'
        ' WHERE d.enabled = 1 AND d.account_id IS NOT NULL'
        " AND d.token_hash <> '' AND d.last_seen_at IS NOT NULL"
        ' AND d.last_seen_at < ? AND d.offline_alerted = 0 ORDER BY d.id',
        (threshold_iso,), fetch_all=True)


def mark_device_offline_alerted(device_id):
    """标记本轮离线已告警；返回是否写中（并发下只有一个扫描者能拿到 True）。"""
    if not device_id:
        return False
    rows = _exec(
        'UPDATE devices SET offline_alerted = 1 WHERE id = ? AND offline_alerted = 0',
        (device_id,), commit=True, rowcount=True)
    return bool(rows)


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
