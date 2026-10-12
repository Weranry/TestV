"""预渲染缓存键：只有「最终参数完全一致」才算命中。

键的输入必须已经是 merge 之后的最终参数（含插件默认值与全局默认值），
因此「没传 city 但默认 city=beijing」与「显式传 city=beijing」同键；
默认值改了 → 键跟着变 → 老图自然 miss，不需要额外的失效逻辑。

缓存产物是「与格式无关的索引图」，所以视图路由的 rotate/invert/cmode/format
不进键——它们命中时按当次请求现场套用，一份产物服务所有旋转角度与输出格式。
"""
import hashlib
import json

# 凭证类参数不参与身份判定：evkey 是每个客户端的凭证，算进去会导致按 key 全 miss
_EXCLUDED = ('evkey',)

# 可后处理的参数：对其「现场套用」就能得到与当时渲染等价的结果，因此不必各存一份
_POSTPROCESS = ('rotate', 'invert', 'cmode', 'format', 'fmt')


def normalize_params(params):
    """归一化成可比较的字典：剔除凭证、丢 None、值统一 str、格式小写"""
    out = {}
    for k, v in (params or {}).items():
        if k in _EXCLUDED or v is None:
            continue
        out[k] = str(v)
    # format / fmt 是同一个东西的两种写法，统一成 fmt，避免同一次请求算出两个键
    if 'format' in out and 'fmt' not in out:
        out['fmt'] = out.pop('format')
    else:
        out.pop('format', None)
    if 'fmt' in out:
        out['fmt'] = out['fmt'].lower()
    return out


def dump_params(params):
    """落库用：保留原始类型（runner 直接回传给 generate_image / to_json）

    键是按归一化后的字符串算的，因此这里存原始类型不会让键漂移。
    """
    return json.dumps(params or {}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def load_params(text):
    """读回任务参数；脏数据按空字典处理，避免一个坏任务拖垮调度循环"""
    try:
        data = json.loads(text or '{}')
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def build_identity(plugin_name, route_path, params, route_kind='view'):
    """最终参数 → 稳定的缓存键

    `route_kind='view'` 时剔除可后处理参数（旋转/反色/cmode/格式）。
    `route_kind='json'` 保持原样：JSON 路由的参数是直接透传给 to_json 的业务参数，
    不能替调用方认定哪个 key 是"后处理"，误剔会让不同请求撞同一个键。
    """
    norm = normalize_params(params)
    if route_kind != 'json':
        for key in _POSTPROCESS:
            norm.pop(key, None)
    blob = json.dumps(
        {
            'plugin': plugin_name,
            'route': route_path,
            'kind': route_kind,
            'params': norm,
        },
        sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    )
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()