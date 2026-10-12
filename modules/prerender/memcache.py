"""预渲染命中路径的内存成品缓存：缓存**已编码好的响应体字节**。

命中一次原本要走：读整块 BLOB → Pillow 解索引 PNG → 旋转 / 反色 → 重新编码成目标格式。
实测约 2ms，其中编码占大头（默认 jpg q100 单张 36KB），而产物本身是「与后处理无关」的
索引图，同一份产物会被不同格式、不同旋转反复请求。这里把最终字节缓存下来，
命中路径就只剩一次内存查表。

为什么不让 store 直接缓存 PIL 对象：`Image` / `ImageDraw` 不是线程安全的，共享出去
迟早被某个调用方原地改坏；响应体是不可变字节，跨线程共享没有这个问题。

键必须带上 fmt / rotate / invert / cmode —— 预渲染缓存键是「与后处理无关」的，
编码结果却是后处理的函数：不带就会把 90° 的图当成 0° 的返回。字节预算按 LRU 淘汰
（读路径在 worker 线程，故用一个 threading.Lock 保护），0 = 关闭。
"""
import threading
from collections import OrderedDict

# 键 → (content, mime, filename, raw_len)
_entries = OrderedDict()
_bytes = 0
_budget = 0
_hits = 0
_misses = 0
_lock = threading.Lock()

_DEFAULT_MB = 32


def _budget_bytes():
    """预算每次现取：面板改完要立刻生效（禁止在导入期捕获配置值）"""
    import config
    try:
        mb = float(getattr(config, 'PRERENDER_MEMORY_CACHE_MB', _DEFAULT_MB) or 0)
    except (TypeError, ValueError):
        mb = 0.0
    # 按 float 解析再换算：写成 int(mb) 会把 0.5 这类值悄悄截断成 0，
    # 而 0 在本项目等于「关闭缓存」——配置看起来生效了，实际全关。
    return int(max(0.0, mb) * 1024 * 1024)


def _sync_budget_locked(budget):
    """预算变了（含被关成 0）就整体清空：老条目是按旧预算装的，留着没有意义"""
    global _budget
    if budget == _budget:
        return
    _entries.clear()
    _bytes = 0
    _budget = budget


def get(key):
    """命中返回 (content, mime, filename, raw_len)；未命中返回 None"""
    global _hits, _misses
    budget = _budget_bytes()
    with _lock:
        _sync_budget_locked(budget)
        entry = _entries.get(key)
        if entry is None:
            _misses += 1
            return None
        _entries.move_to_end(key)
        _hits += 1
        return entry


def put(key, value):
    """写入 / 覆盖一份已编码响应体；超预算时从最久未用的条目开始淘汰"""
    global _bytes
    budget = _budget_bytes()
    content = value[0] or b''
    with _lock:
        _sync_budget_locked(budget)
        size = len(content)
        # 关掉缓存，或单条就顶满预算：不缓存（否则刚放进去就被自己挤掉，白算一轮）
        if budget <= 0 or size > budget:
            return
        old = _entries.pop(key, None)
        if old is not None:
            _bytes -= len(old[0] or b'')
        _entries[key] = value
        _bytes += size
        while _bytes > budget and _entries:
            _evicted = _entries.popitem(last=False)[1]
            _bytes -= len(_evicted[0] or b'')


def delete_identity(cache_key):
    """摘掉某个预渲染键派生出的全部编码结果（产物被覆盖 / 删除时调用）。

    内存键是 (cache_key, fmt, rotate, invert, cmode)：同一份产物按不同后处理会存成多条，
    按键首段精确摘除即可，不必整体清空——整体清空会把其它任务的热点产物一起打掉。
    """
    global _bytes
    budget = _budget_bytes()
    with _lock:
        _sync_budget_locked(budget)
        for key in [k for k in _entries if k[0] == cache_key]:
            entry = _entries.pop(key, None)
            if entry is not None:
                _bytes -= len(entry[0] or b'')


def clear():
    """整体清空（清表、裁剪、批量删除这类一次动很多键的场景用）。

    store.py 里凡是「删掉一批产物行」的入口之后都要调用：漏掉任何一条路径的后果都是
    「库里已经删了、内存里还在返回旧图」。只动单个键时用 delete_identity()。
    """
    global _bytes, _budget
    with _lock:
        _entries.clear()
        _bytes = 0
        _budget = _budget_bytes()


def stats():
    """条目数 / 占用字节 / 命中情况（面板与 /metrics 用）"""
    budget = _budget_bytes()
    with _lock:
        return {
            'enabled': budget > 0,
            'entries': len(_entries),
            'bytes': _bytes,
            'max_bytes': budget,
            'hits': _hits,
            'misses': _misses,
        }