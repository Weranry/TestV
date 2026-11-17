import threading
from PIL import Image, ImageFont
import config

_cache = None
_lock = threading.Lock()
_hits = 0
_misses = 0
_enabled = True


def _cfg_int(name, default):
    """配置项转 int。面板存的是字符串，写错值（如 abc）不能把渲染路径直接炸掉"""
    try:
        return int(getattr(config, name, default))
    except (TypeError, ValueError):
        return default


def _ensure_cache():
    """按当前 config 重建字体 LRU 池。

    只缓存字体：字体文件运行期不变、FreeType 解析成本高，用**不过期**的 LRU 最合适——
    带上 TTL 反而有害，ESP32 每 5~15 分钟轮询一次正好踩在过期边界上，每个视图的
    3~5 个字号会反复走磁盘 + 解析。

    CACHE_MAXSIZE 是管理面板可改的配置项，若在导入期就把值烙进 LRUCache，面板改完
    不会生效（必须重启），缓存页显示的 maxsize 也是旧值。这里每次调用比对一次，
    仅在值真的变化时重建。
    """
    # LRUCache 延迟导入：缓存被 set_enabled(False) 停用后（Vercel Serverless）
    # 本函数根本不会被调到（get_font 直接实时加载），所以 Serverless 侧
    # 不装 cachetools 也跑得起来。
    from cachetools import LRUCache
    global _cache
    maxsize = _cfg_int('CACHE_MAXSIZE', 64)
    if _cache is None or _cache.maxsize != maxsize:
        with _lock:
            if _cache is None or _cache.maxsize != maxsize:
                _cache = LRUCache(maxsize=maxsize)
    return _cache


def set_enabled(enabled):
    """停用后不再读写内存缓存，改为每次实时加载（Vercel Serverless 无复用进程）"""
    global _enabled
    _enabled = bool(enabled)
    if not _enabled:
        with _lock:
            if _cache is not None:
                _cache.clear()


def is_enabled():
    return _enabled


def _record_hit():
    global _hits
    _hits += 1


def _record_miss():
    global _misses
    _misses += 1


def get_font(font_path, size):
    if not _enabled:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            return ImageFont.load_default()
    key = f'font:{font_path}:{size}'
    cache = _ensure_cache()
    with _lock:
        cached = cache.get(key)
        if cached is not None:
            _record_hit()
            return cached
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        # 计数与 stats() 读的是同一对变量，统一在锁内自增，否则命中率会漂移
        with _lock:
            _record_miss()
        return ImageFont.load_default()
    with _lock:
        cache[key] = font
        _record_miss()
    return font


def get_image(image_path):
    """实时加载为 RGBA 图片，**不进缓存**。

    图片曾与字体共用同一个缓存池，但 RGBA 位图是内存大头，条目一多就会把字体挤出去
    （与「只缓存字体」的意图正好相反）。渲染结果本身就不缓存，图片同理：直接实时加载。
    """
    try:
        return Image.open(image_path).convert('RGBA')
    except Exception:
        return None


def get_indexed_image(image_path):
    """实时加载**保留原始模式**（通常是 'P'）的已解码图片，**不进缓存**。

    get_image() 会统一转成 RGBA，调色板索引语义随之丢失；weather 的 sprite 需要
    pix[x, y] 直接与 0/1/2 比较来决定画黑白红，只能走这条不转换模式的通道。
    """
    try:
        return _load_indexed(image_path)
    except Exception:
        return None


def _load_indexed(image_path):
    img = Image.open(image_path)
    img.load()
    return img


def clear():
    global _hits, _misses
    with _lock:
        if _cache is not None:
            _cache.clear()
        _hits = 0
        _misses = 0


def stats(with_items=True):
    """缓存统计。with_items=False 时跳过条目列表的构造。

    `items` 只有缓存页会用；/admin/api/status 这类被轮询的接口只取计数，
    让它把整池 key 也拼一遍纯属白干（CACHE_MAXSIZE 调大后开销还会跟着涨）。
    """
    cache = _ensure_cache()
    with _lock:
        total = _hits + _misses
        hit_rate = (_hits / total * 100) if total > 0 else 0.0
        result = {
            'size': len(cache),
            'maxsize': cache.maxsize,
            'hits': _hits,
            'misses': _misses,
            'hit_rate': round(hit_rate, 1),
        }
        if with_items:
            result['items'] = [
                {'key': key, 'kind': key.split(':', 1)[0] if ':' in key else 'other'}
                for key in cache
            ]
        return result