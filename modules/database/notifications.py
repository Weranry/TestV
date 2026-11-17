"""用户端通知：面向单个账号的事件流（设备被删除、权限变更、系统消息）。

与「站内信（announcements）」的区别：站内信是面向用户组的广播、由管理员发布、不可删除；
通知是发给某个账号的个人事件，用户可以逐条删除。两者在控制台弹窗里分栏展示。

**文案不存成品文本**：只存 kind（类别）+ payload（渲染所需的快照，如设备名/组名/到期日），
由前端按 kind 取 i18n 文案渲染。否则英文界面会在通知里露出中文（i18n 是硬约束）。代价是
新增一种 kind 必须同步补中英文案。read_at 为空即未读。
"""
import json

from modules.database.core import _exec, _exec_many


def _pack_payload(payload):
    if not payload:
        return '{}'
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'


def _decode(row):
    """把库里的 payload_json 解出来，对外的字段名统一叫 payload"""
    item = dict(row)
    try:
        item['payload'] = json.loads(item.pop('payload_json') or '{}')
    except (TypeError, ValueError):
        item['payload'] = {}
    return item


def create_notification(account_id, kind, payload=None, title='', body=''):
    """投一条通知给某账号，返回新行 id"""
    return _exec(
        'INSERT INTO notifications (account_id, kind, title, body, payload_json)'
        ' VALUES (?, ?, ?, ?, ?)',
        (int(account_id), kind or '', title or '', body or '', _pack_payload(payload)),
        commit=True,
    )


def create_notifications(account_ids, kind, payload=None, title='', body=''):
    """同一内容批量投递给多个账号（账号自动去重），返回投递条数。

    title/body 留空是常态：前端拿 kind + payload 渲染文案。批量写走 _exec_many 单事务提交。
    """
    ids = []
    for aid in account_ids or []:
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        if aid and aid not in ids:
            ids.append(aid)
    if not ids:
        return 0
    pj = _pack_payload(payload)
    _exec_many([
        ('INSERT INTO notifications (account_id, kind, title, body, payload_json)'
         ' VALUES (?, ?, ?, ?, ?)', (aid, kind or '', title or '', body or '', pj))
        for aid in ids
    ])
    return len(ids)


def list_notifications(account_id, limit=20, offset=0):
    rows = _exec(
        'SELECT * FROM notifications WHERE account_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
        (int(account_id), max(1, int(limit)), max(0, int(offset))), fetch_all=True,
    )
    return [_decode(r) for r in (rows or [])]


def count_notifications(account_id):
    row = _exec('SELECT COUNT(*) AS cnt FROM notifications WHERE account_id = ?',
                (int(account_id),), fetch_one=True)
    return row['cnt'] if row else 0


def count_unread(account_id):
    row = _exec(
        'SELECT COUNT(*) AS cnt FROM notifications WHERE account_id = ? AND read_at IS NULL',
        (int(account_id),), fetch_one=True,
    )
    return row['cnt'] if row else 0


def mark_read(account_id, ids=None, all=False):
    """把该账号的通知标为已读，返回受影响行数。

    ids 为空且 all 不为真时直接返回 0——否则空 ids 会退化成"整表更新"，误清掉不想清的未读。
    """
    if not all and not ids:
        return 0
    sql = ("UPDATE notifications SET read_at = datetime('now')"
           ' WHERE account_id = ? AND read_at IS NULL')
    params = [int(account_id)]
    if not all:
        clean = [int(i) for i in ids]
        sql += ' AND id IN (%s)' % ','.join('?' * len(clean))
        params.extend(clean)
    return _exec(sql, tuple(params), commit=True, rowcount=True)


def delete_notification(account_id, notif_id):
    """删一条自己的通知，返回删除行数。

    account_id 条件不能省：否则拿到别人的 id 就能删掉别人的通知（越权时 rowcount=0）。
    """
    return _exec('DELETE FROM notifications WHERE id = ? AND account_id = ?',
                 (int(notif_id), int(account_id)), commit=True, rowcount=True)


def clear_notifications(account_id):
    """清空某账号的全部通知，返回删除行数"""
    return _exec('DELETE FROM notifications WHERE account_id = ?', (int(account_id),),
                 commit=True, rowcount=True)
