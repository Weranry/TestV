import os
from modules.cache.cache import get_font as _cached_get_font


def get_root_font_path(filename):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    return os.path.join(project_root, 'assets', 'fonts', filename)


def get_plugin_font_path(filename, base_file):
    plugin_root = os.path.abspath(os.path.join(os.path.dirname(base_file), '../..'))
    return os.path.join(plugin_root, 'assets', 'fonts', filename)


def get_font(size, font_path):
    # 是否走缓存由 modules.cache.cache 自己决定（Vercel Serverless 模式下已停用）
    return _cached_get_font(font_path, size)