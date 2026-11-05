"""有类型的插件业务动作及调用身份，不依赖面板或 HTTP 框架。"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .schema import export_model_schema, schema_field_paths

ActionPermission = Literal["read", "operate", "manage"]
_PERMISSION_LEVELS = {"read": 1, "operate": 2, "manage": 3}
_ID_RE = re.compile(r"[a-z][a-z0-9_.-]*")


def validate_id(value: str, *, kind: str) -> str:
    """公共 ID 只表示插件内的名称，不能混入路径或空点段。"""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or any(not part for part in value.split(".")):
        raise ValueError(f"{kind} ID 无效: {value!r}")
    return value


def validate_model(model: Any) -> None:
    """允许提供模型协议的类型，避免 SDK 绑定具体模型库的内部类。"""
    if model is None:
        return
    methods = ("model_json_schema", "model_validate", "model_dump")
    if not isinstance(model, type) or not all(callable(getattr(model, name, None)) for name in methods):
        raise ValueError("动作模型必须提供 model_json_schema、model_validate 和 model_dump")


@dataclass(frozen=True)
class ActionInvocation:
    """由可信调用入口构造的身份和权限；请求体不能替代此上下文。"""

    identity: str
    permissions: frozenset[str]
    context: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise ValueError("动作调用身份不能为空")
        if isinstance(self.permissions, str):
            raise ValueError("动作权限必须是字符串集合")
        permissions = frozenset(self.permissions)
        if not all(isinstance(permission, str) for permission in permissions):
            raise ValueError("动作权限必须是字符串集合")
        object.__setattr__(self, "permissions", permissions)


class ActionError(Exception):
    """作者明确声明可公开的业务失败；未知处理器异常仍由调用边界隐藏。"""

    def __init__(self, code: str, message: str, *, fields: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "fields": json.loads(json.dumps(self.fields))}


def _declared_location(location: Any, paths: set[str]) -> list[str | int]:
    """截断模型字段之外的位置，避免错误路径带出用户字典的键名。"""
    path: list[str | int] = []
    names: list[str] = []
    for part in location:
        if isinstance(part, int) and not isinstance(part, bool):
            path.append(part)
            continue
        if not isinstance(part, str) or ".".join([*names, part]) not in paths:
            break
        names.append(part)
        path.append(part)
    return path


def validation_error_fields(error: Exception, model: Any) -> list[dict[str, Any]]:
    """只保留声明过的字段位置，字典中用户提供的键名也不进入错误响应。"""
    details = getattr(error, "errors", None)
    if not callable(details):
        return []
    try:
        errors = details(include_input=False, include_context=False, include_url=False)
        paths = schema_field_paths(export_model_schema(model))
    except Exception:
        return []
    result = []
    for issue in errors:
        kind = str(issue.get("type", "invalid"))
        if not re.fullmatch(r"[a-z_]+", kind):
            kind = "invalid"
        result.append({"path": _declared_location(issue.get("loc", ()), paths), "type": kind})
    return result


def _json_value(value: Any) -> Any:
    if callable(getattr(value, "model_dump", None)):
        value = value.model_dump(mode="json", by_alias=True)
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


@dataclass(frozen=True)
class ActionDefinition:
    """动作的公开描述与处理器保存在一起，界面不另行维护校验规则。"""

    id: str
    title: str
    description: str
    permission: ActionPermission
    input_model: Any
    output_model: Any
    handler: Callable[[Any, ActionInvocation], Any]

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "permission": self.permission,
            "input_schema": export_model_schema(self.input_model),
            "output_schema": export_model_schema(self.output_model, mode="serialization"),
        }

    async def invoke(self, payload: Any, invocation: ActionInvocation) -> Any:
        if not isinstance(invocation, ActionInvocation):
            raise ActionError("invalid_invocation", "动作调用缺少可信身份上下文")
        required = _PERMISSION_LEVELS[self.permission]
        if not any(_PERMISSION_LEVELS.get(permission, 0) >= required for permission in invocation.permissions):
            raise ActionError("permission_denied", "没有执行此动作的权限")
        try:
            value = _json_value({} if payload is None and self.input_model is None else payload)
            if self.input_model is not None:
                value = self.input_model.model_validate(value)
            elif not isinstance(value, dict):
                raise ValueError("未声明模型的动作输入必须是 JSON 对象")
        except Exception as exc:
            raise ActionError(
                "invalid_input", "动作输入不符合声明", fields=validation_error_fields(exc, self.input_model)
            ) from None
        try:
            result = self.handler(value, invocation)
            if inspect.isawaitable(result):
                result = await result
        except ActionError:
            raise
        except Exception:
            raise ActionError("action_failed", "动作执行失败") from None
        try:
            if self.output_model is not None:
                result = self.output_model.model_validate(result)
            return _json_value(result)
        except Exception as exc:
            raise ActionError(
                "invalid_output", "动作结果不符合声明", fields=validation_error_fields(exc, self.output_model)
            ) from None


def make_action(
    id: str,
    handler: Callable[[Any, ActionInvocation], Any],
    *,
    input_model: Any = None,
    output_model: Any = None,
    title: str = "",
    description: str = "",
    permission: ActionPermission = "manage",
) -> ActionDefinition:
    validate_id(id, kind="动作")
    if not isinstance(permission, str) or permission not in _PERMISSION_LEVELS:
        raise ValueError("动作权限必须是 read、operate 或 manage")
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError("动作标题和说明必须是字符串")
    if not callable(handler):
        raise ValueError("动作处理器必须可调用")
    validate_model(input_model)
    validate_model(output_model)
    return ActionDefinition(id, title or id, description, permission, input_model, output_model, handler)
