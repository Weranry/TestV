from modules.database.core import _exec

# ---- 站内信 ----

def _pack_group_ids(group_ids):
    """可见用户组统一存成 '1,3' 形式的字符串，空串表示全体可见。

    没有用关联表：一条站内信最多几个组，取值永远是"整条读出来"，拆表只会
    多一次 join，不会带来任何查询上的好处。
    """
    if not group_ids:
        return ''
    return ','.join(str(int(g)) for g in group_ids)


def get_announcements(limit=5, offset=0):
    return _exec('SELECT * FROM announcements ORDER BY id DESC LIMIT ? OFFSET ?',
                 (limit, offset), fetch_all=True)


def count_announcements():
    return _exec('SELECT COUNT(*) AS cnt FROM announcements', fetch_one=True)['cnt']


def get_announcements_for_group(group_id):
    """某个用户组能看到的站内信：全体可见 + 显式点名该组的"""
    gid = int(group_id or 0)
    return _exec(
        "SELECT * FROM announcements WHERE group_ids = ''"
        " OR (',' || group_ids || ',') LIKE ?"
        ' ORDER BY id DESC',
        ('%,' + str(gid) + ',%',), fetch_all=True,
    )


def create_announcement(title, content='', group_ids=None, admin_name=''):
    return _exec('INSERT INTO announcements (title, content, group_ids, admin_name) VALUES (?, ?, ?, ?)',
                 (title, content, _pack_group_ids(group_ids), admin_name or ''), commit=True)


def delete_announcement(ann_id):
    return _exec('DELETE FROM announcements WHERE id = ?', (ann_id,), commit=True)