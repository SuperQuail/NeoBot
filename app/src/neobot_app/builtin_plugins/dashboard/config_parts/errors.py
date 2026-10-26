"""配置管理的异常类型。"""

from __future__ import annotations


class ConfigConflictError(RuntimeError):
    """revision 不匹配：文件已被其它会话修改。"""


class ConfigValidationError(RuntimeError):
    """配置内容校验失败。"""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        message = "；".join(
            f"{item.get('path') or '?'}: {item.get('message')}" for item in errors[:8]
        )
        super().__init__(message or "配置校验失败")
