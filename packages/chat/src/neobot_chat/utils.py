"""公共工具函数"""

import json


def parse_tool_args(raw: str | dict) -> dict:
    """解析工具参数：如果是字符串则解析 JSON，否则直接返回"""
    return json.loads(raw) if isinstance(raw, str) else raw
