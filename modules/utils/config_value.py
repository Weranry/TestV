"""配置值解析。

配置项在数据库里统一以字符串存放，读回时要尽量还原成原始类型。
面板存进来的值可能是前端 JSON.stringify 的结果（含 null / true / false），
也可能是手写的 Python 字面量（True / False / None），两种都要认。
只认其中一种会把值原样留成字符串，进而引发类型错误。
"""
import ast
import json


def parse_config_value(value):
    """字符串 -> 原始类型；解析不出来时原样返回字符串"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return value
