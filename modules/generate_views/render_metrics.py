"""渲染打点：把「渲染本身」的实时状态暴露给健康检查与面板。

只存内存、单进程内共享（项目强制单进程单 worker），不落库：
面板是轮询展示，重启归零可以接受；落库则会让渲染热路径每次多一次写库。
"""
import threading

_lock = threading.Lock()
_state = {
    'active': 0,        # 当前正在渲染的请求数
    'total': 0,         # 本次进程累计渲染次数（不含缓存命中）
    'hits': 0,          # 本次进程累计成品图缓存命中次数
    'last_ms': None,    # 最近一次渲染耗时
    'slowest_ms': 0.0,  # 本次进程最慢一次渲染
    '_sum_ms': 0.0,
}


def mark_start():
    """渲染开始打点。必须与 mark_end 成对，异常路径也要走到 mark_end"""
    with _lock:
        _state['active'] += 1


def mark_end(duration_ms):
    """渲染结束打点（成功与失败都要调）"""
    with _lock:
        _state['active'] = max(0, _state['active'] - 1)
        _state['total'] += 1
        _state['last_ms'] = round(duration_ms, 2)
        _state['_sum_ms'] += duration_ms
        if duration_ms > _state['slowest_ms']:
            _state['slowest_ms'] = round(duration_ms, 2)


def mark_hit():
    """缓存命中打点。命中不是一次渲染，不进 total / last_ms"""
    with _lock:
        _state['hits'] += 1


def snapshot():
    """当前快照（只读）"""
    with _lock:
        total = _state['total']
        return {
            'active': _state['active'],
            'total': total,
            'hits': _state['hits'],
            'last_ms': _state['last_ms'],
            'avg_ms': round(_state['_sum_ms'] / total, 2) if total else None,
            'slowest_ms': _state['slowest_ms'] or None,
        }