"""插件配置、业务资源与任务教程的统一声明入口。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

from .actions import (
    ActionDefinition,
    ActionError,
    ActionInvocation,
    ActionPermission,
    make_action,
    validate_id,
    validate_model,
)
from .guides import guide_command_errors, guide_form_errors
from .schema import export_model_schema, schema_field_paths

if TYPE_CHECKING:
    from neobot_modloader.plugin import Plugin


class SurfaceContractError(ValueError):
    """契约中的引用或声明无效，供检查工具定位作者需要修正的地方。"""


@dataclass(frozen=True)
class ResourceColumn:
    key: str
    title: str


@dataclass(frozen=True)
class ResourceDefinition:
    id: str
    title: str
    list_action: str
    columns: tuple[ResourceColumn, ...]
    create_action: str | None = None
    delete_action: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "list_action": self.list_action,
            "columns": [{"key": column.key, "title": column.title} for column in self.columns],
            "create_action": self.create_action,
            "delete_action": self.delete_action,
        }


@dataclass(frozen=True)
class GuideStep:
    target: str
    text: str
    chapter: str | None = None
    example: dict[str, Any] | None = None
    command: dict[str, str] | None = None
    form: str | None = None

    def describe(self) -> dict[str, Any]:
        result = {"target": self.target, "text": self.text}
        if self.chapter is not None:
            result["chapter"] = self.chapter
        if self.example is not None:
            result["example"] = _json_copy(self.example)
        if self.command is not None:
            result["command"] = _json_copy(self.command)
        if self.form is not None:
            result["form"] = self.form
        return result


@dataclass(frozen=True)
class GuideDefinition:
    id: str
    title: str
    steps: tuple[GuideStep, ...]
    completion_action: str | None = None
    demo: dict[str, Any] | None = None

    def describe(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "title": self.title,
            "steps": [step.describe() for step in self.steps],
            "completion_action": self.completion_action,
        }
        if self.demo is not None:
            result["demo"] = _json_copy(self.demo)
        return result


@dataclass(frozen=True)
class ViewDefinition:
    id: str
    title: str
    entry: str
    anchors: tuple[str, ...]

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "entry": self.entry, "anchors": list(self.anchors)}


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def validate_view_entry(entry: Any) -> str:
    """页面是包内 HTML，文件系统边界由宿主读取时再次检查。"""
    if not isinstance(entry, str) or not entry or "\\" in entry or "\0" in entry:
        raise ValueError("页面入口必须是包内相对 HTML 路径")
    path = PurePosixPath(entry)
    if path.is_absolute() or PureWindowsPath(entry).drive or ".." in path.parts or path.suffix.lower() != ".html":
        raise ValueError("页面入口必须是包内相对 HTML 路径")
    return entry


def _segment(value: str, kind: str) -> str:
    validate_id(value, kind=kind)
    if "." in value:
        raise ValueError(f"{kind} ID 不能包含点号")
    return value


def _demo(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"actions", "config"}:
        raise ValueError("演示只支持 actions 和 config 合成数据")
    if not all(isinstance(value.get(key, {}), dict) for key in ("actions", "config")):
        raise ValueError("演示 actions 和 config 必须是对象")
    return _json_copy(value)


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value


def _guide_step(step: Mapping[str, Any], location: str) -> GuideStep:
    if (
        not isinstance(step, Mapping)
        or not {"target", "text"} <= set(step)
        or set(step) - {"target", "text", "chapter", "example", "command", "form"}
    ):
        raise ValueError("教程步骤必须包含 target 和 text")
    errors = guide_form_errors(step, location)
    if errors:
        raise ValueError("；".join(errors))
    chapter = _text(step["chapter"], field="教程章节") if "chapter" in step else None
    example = step.get("example")
    if example is not None and not isinstance(example, dict):
        raise ValueError("教程示例必须是对象")
    command = step.get("command")
    if "command" in step:
        errors = guide_command_errors(command, "教程命令")
        if errors:
            raise ValueError("；".join(errors))
    return GuideStep(
        _text(step["target"], field="教程目标"),
        _text(step["text"], field="教程文字"),
        chapter,
        _json_copy(example),
        _json_copy(command),
        step.get("form"),
    )


def _columns(columns: Sequence[str | Mapping[str, Any]]) -> tuple[ResourceColumn, ...]:
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)) or not columns:
        raise ValueError("资源必须声明列列表")
    result = []
    keys = set()
    for column in columns:
        if isinstance(column, str):
            key = title = column
        elif isinstance(column, Mapping) and set(column) <= {"key", "title"}:
            key = _text(column.get("key"), field="列 key")
            title = column.get("title", key)
        else:
            raise ValueError("资源列必须是字段名或包含 key/title 的对象")
        _text(key, field="列 key")
        _text(title, field="列 title")
        if key in keys:
            raise ValueError(f"资源列重复: {key}")
        keys.add(key)
        result.append(ResourceColumn(key, title))
    return tuple(result)


class PluginSurface:
    """每个 Plugin 独立持有的契约；检查声明无需绑定运行时或页面。"""

    def __init__(self) -> None:
        self._actions: dict[str, ActionDefinition] = {}
        self._resources: dict[str, ResourceDefinition] = {}
        self._guides: dict[str, GuideDefinition] = {}
        self._views: dict[str, ViewDefinition] = {}

    def view(self, id: str, *, title: str, entry: str, anchors: Sequence[str] = ()) -> ViewDefinition:
        _segment(id, "页面")
        if id in self._views:
            raise ValueError(f"页面 ID 重复: {id}")
        if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence):
            raise ValueError("页面锚点必须是列表")
        names = tuple(_segment(anchor, "页面锚点") for anchor in anchors)
        if len(set(names)) != len(names):
            raise ValueError("页面锚点不能重复")
        view = ViewDefinition(id, _text(title, field="页面标题"), validate_view_entry(entry), names)
        self._views[id] = view
        return view

    def action(
        self,
        id: str,
        *,
        input_model: Any = None,
        output_model: Any = None,
        title: str = "",
        description: str = "",
        permission: ActionPermission = "manage",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        validate_id(id, kind="动作")
        if not isinstance(permission, str) or permission not in {"read", "operate", "manage"}:
            raise ValueError("动作权限必须是 read、operate 或 manage")
        validate_model(input_model)
        validate_model(output_model)

        def register(handler: Callable[..., Any]) -> Callable[..., Any]:
            if id in self._actions:
                raise ValueError(f"动作 ID 重复: {id}")
            self._actions[id] = make_action(
                id,
                handler,
                input_model=input_model,
                output_model=output_model,
                title=title,
                description=description,
                permission=permission,
            )
            return handler

        return register

    def resource(
        self,
        id: str,
        *,
        title: str,
        list_action: str,
        columns: Sequence[str | Mapping[str, Any]],
        create_action: str | None = None,
        delete_action: str | None = None,
    ) -> ResourceDefinition:
        validate_id(id, kind="资源")
        if id in self._resources:
            raise ValueError(f"资源 ID 重复: {id}")
        for action in (list_action, create_action, delete_action):
            if action is not None:
                validate_id(action, kind="资源动作")
        resource = ResourceDefinition(
            id, _text(title, field="资源标题"), list_action, _columns(columns), create_action, delete_action
        )
        self._resources[id] = resource
        return resource

    def guide(
        self,
        id: str,
        *,
        title: str,
        steps: Sequence[Mapping[str, Any]],
        completion_action: str | None = None,
        demo: dict[str, Any] | None = None,
    ) -> GuideDefinition:
        validate_id(id, kind="教程")
        if id in self._guides:
            raise ValueError(f"教程 ID 重复: {id}")
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)) or not steps:
            raise ValueError("教程必须至少声明一个步骤")
        copied = tuple(_guide_step(step, f"guides.{id}.steps[{index}]") for index, step in enumerate(steps))
        if completion_action is not None:
            validate_id(completion_action, kind="教程完成检查")
        guide = GuideDefinition(id, _text(title, field="教程标题"), copied, completion_action, _demo(demo))
        self._guides[id] = guide
        return guide

    def _require_action(self, action_id: str, *, owner: str, read_only: bool = False) -> ActionDefinition:
        action = self._actions.get(action_id)
        if action is None:
            raise SurfaceContractError(f"{owner} 引用了未知动作: {action_id}")
        if read_only and action.permission != "read":
            raise SurfaceContractError(f"{owner} 必须引用 read 动作: {action_id}")
        return action

    def _validate_resource(self, resource: ResourceDefinition) -> None:
        self._require_action(resource.list_action, owner=f"资源 {resource.id} 的列表", read_only=True)
        for action_id in (resource.create_action, resource.delete_action):
            if action_id is None:
                continue
            action = self._require_action(action_id, owner=f"资源 {resource.id}")
            if action.permission == "read":
                raise SurfaceContractError(f"资源 {resource.id} 的修改必须引用 operate 或 manage 动作: {action_id}")

    def _guide_target_exists(self, reference: str, fields: set[str], has_config: bool) -> bool:
        if reference == "config":
            return has_config
        kind, separator, target = reference.partition(".")
        if not separator:
            return False
        if kind == "config":
            return target in fields
        if kind == "action":
            return target in self._actions
        if kind == "resource":
            return target in self._resources
        if kind != "view":
            return False
        view_id, _, anchor = target.partition(".")
        view = self._views.get(view_id)
        return view is not None and anchor in view.anchors

    def _validate_guide(self, guide: GuideDefinition, fields: set[str], has_config: bool) -> None:
        if guide.completion_action is not None:
            self._require_action(guide.completion_action, owner=f"教程 {guide.id} 的完成检查", read_only=True)
        if guide.demo is not None:
            for action in guide.demo.get("actions", {}):
                self._require_action(action, owner=f"教程 {guide.id} 的演示")
        for index, step in enumerate(guide.steps):
            if not self._guide_target_exists(step.target, fields, has_config):
                if step.form is not None or step.target == "config":
                    raise SurfaceContractError(f"guides.{guide.id}.steps[{index}].target 无效")
                raise SurfaceContractError(f"教程 {guide.id} 引用了未知目标: {step.target}")

    def _validate(self, plugin: Plugin) -> dict[str, Any] | None:
        if getattr(plugin, "surface", None) is not self:
            raise SurfaceContractError("契约不属于当前插件")
        # 配置持久化使用模型字段名；动作输入输出继续遵守各自的别名协议。
        schema = export_model_schema(plugin.config_model, by_alias=False)
        fields = schema_field_paths(schema)
        for resource in self._resources.values():
            self._validate_resource(resource)
        for guide in self._guides.values():
            self._validate_guide(guide, fields, schema is not None)
        return schema

    def describe(self, plugin: Plugin) -> dict[str, Any]:
        schema = self._validate(plugin)
        result = {
            "schema_version": 1,
            "plugin": {"name": plugin.name, "version": plugin.version, "description": str(plugin.description or "")},
            "config": schema,
            "actions": [action.describe() for action in self._actions.values()],
            "resources": [resource.describe() for resource in self._resources.values()],
            "guides": [guide.describe() for guide in self._guides.values()],
        }
        if self._views:
            result["views"] = [view.describe() for view in self._views.values()]
        return result

    async def invoke(self, plugin: Plugin, action_id: str, payload: Any, invocation: ActionInvocation) -> Any:
        if not isinstance(action_id, str):
            raise ActionError("action_not_found", "插件动作不存在")
        action = self._actions.get(action_id)
        if action is None:
            raise ActionError("action_not_found", "插件动作不存在")
        try:
            self._validate(plugin)
        except Exception:
            raise ActionError("contract_invalid", "插件契约无效") from None
        return await action.invoke(payload, invocation)
