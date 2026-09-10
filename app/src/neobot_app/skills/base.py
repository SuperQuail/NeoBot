"""Skill 核心 — SkillModule 协议与 SkillManager。"""

from __future__ import annotations

import copy
import inspect
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any


_SEPARATOR = "__"
_RESERVED_FINAL_TOOL_NAMES = frozenset(
    {"skills__read_manifest", "skills__read_resource"}
)
_FINAL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCAL_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_MAX_SCHEMA_BYTES = 64 * 1024
_STALE_TOOL_ERROR = "工具不可用或已更新"
_MISSING = object()


@dataclass(frozen=True, slots=True)
class SkillExecutionToken:
    module: Any
    local_name: str
    final_name: str


@dataclass(slots=True)
class _RegisteredSkill:
    module: Any
    name: str
    prefix: str
    exposed: bool
    description: str
    instructions: str
    tools: tuple[dict[str, Any], ...]
    tokens: dict[str, SkillExecutionToken]
    session_tools: frozenset[str]


class SkillModule(ABC):
    """Skill 模块基类。

    子类需实现：
      name, description, get_tools(), execute()
    可选：
      instructions  — 注入到系统提示词的说明文本
      reset()       — 跨会话状态复位
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 唯一标识符，用作工具名前缀。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """简短描述，用于索引和日志。"""

    @property
    def instructions(self) -> str:
        """可选：注入到系统提示词的操作说明。"""
        return ""

    @property
    def session_tools(self) -> set[str]:
        """返回需要以 Session 模式（提交后立即返回，后台执行完成后通知）执行的无前缀工具名集合。"""
        return set()

    @property
    def tool_prefix(self) -> str:
        """工具名前缀；默认与技能名相同。

        允许多个技能共享同一前缀（例如把一组工具拆成若干按需子包），
        此时路由按最终工具名精确匹配，而不是按技能名反查。
        """
        return ""

    @property
    def exposed_to_main_agent(self) -> bool:
        """是否参与主回复管线的常驻/按需加载。

        返回 False 表示该技能的工具仅供任务型 Agent 或内部组件使用：
        既不常驻注入，也不会出现在 skills__load_tools 的候选列表里。
        """
        return True

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """返回 OpenAI function-calling 格式的工具定义列表。

        工具名建议简短（如 search、navigate），
        SkillManager 会按 ``{skill_name}__{tool_name}`` 自动加前缀。
        """

    @abstractmethod
    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        """执行工具并返回结果字符串。

        Args:
            tool_name: 去前缀后的原始工具名（不含 ``{skill_name}__``）
            args: 工具参数字典
        """

    @staticmethod
    def _tool_def(name: str, description: str, parameters: dict | None = None) -> dict:
        """统一工具定义格式（OpenAI function-calling）。"""
        params: dict = {"type": "object", "properties": {}, "required": []}
        if parameters:
            params["properties"] = parameters.get("properties", {})
            params["required"] = parameters.get("required", [])
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": params,
            },
        }

    def reset(self) -> None:
        """复位内部状态（新会话时调用）。"""


class SkillManager:
    """Skill 管理器 — 注册、聚合、路由。

    用法::

        mgr = SkillManager()
        mgr.register(browser_skill)
        mgr.register(web_search_skill)

        # 聚合所有工具定义（自动加名前缀）
        tools = mgr.get_tools()

        # 聚合所有说明文本
        instructions = mgr.get_instructions()

        # 路由执行
        result = await mgr.execute("browser__navigate", {"url": "..."})
    """

    def __init__(self, *, eager_tool_skills: Collection[str] | None = None) -> None:
        self._skills: dict[str, _RegisteredSkill] = {}
        self._session_tools: set[str] = set()
        # 最终工具名 → 技能名；前缀可以被多个技能共享，因此路由必须按最终名精确匹配。
        self._final_owners: dict[str, str] = {}
        # None = 所有技能的工具定义常驻提示词（保持历史行为）。
        # 给定时，只有列表内的技能常驻，其余技能的工具定义改为
        # skills__load_tools 按需加载：工具 schema 会随每次模型调用一起发送，
        # 全部常驻时实测在 2 万 token 以上。
        self._eager_tool_skills: set[str] | None = (
            set(eager_tool_skills) if eager_tool_skills is not None else None
        )

    def register(self, skill: SkillModule) -> None:
        """注册一个 Skill 模块。"""
        name = getattr(skill, "name", None)
        if not isinstance(name, str) or not _SKILL_NAME_RE.fullmatch(name):
            raise ValueError(f"Skill 名称无效: {name!r}")
        if _SEPARATOR in name or name.endswith("_"):
            raise ValueError(f"Skill 名称与分隔符 {_SEPARATOR!r} 冲突: {name!r}")
        if name in self._skills:
            raise ValueError(f"Skill '{name}' 已注册")
        description = getattr(skill, "description", None)
        instructions = getattr(skill, "instructions", "")
        execute = getattr(skill, "execute", None)
        reset = getattr(skill, "reset", None)
        get_tools = getattr(skill, "get_tools", None)
        if not isinstance(description, str) or not isinstance(instructions, str):
            raise ValueError(f"Skill {name!r} description/instructions must be strings")
        if (
            not callable(get_tools)
            or not callable(execute)
            or not inspect.iscoroutinefunction(execute)
        ):
            raise ValueError(
                f"Skill {name!r} must define get_tools() and async execute()"
            )
        if reset is not None and not callable(reset):
            raise ValueError(f"Skill {name!r} reset must be callable")
        raw_prefix = getattr(skill, "tool_prefix", "") or name
        if not isinstance(raw_prefix, str) or not _SKILL_NAME_RE.fullmatch(raw_prefix):
            raise ValueError(f"Skill {name!r} 工具前缀无效: {raw_prefix!r}")
        if _SEPARATOR in raw_prefix or raw_prefix.endswith("_"):
            raise ValueError(f"Skill {name!r} 工具前缀与分隔符冲突: {raw_prefix!r}")
        exposed = getattr(skill, "exposed_to_main_agent", True)
        if not isinstance(exposed, bool):
            raise ValueError(f"Skill {name!r} exposed_to_main_agent must be a bool")
        try:
            raw_tools = get_tools()
        except Exception as exc:
            raise ValueError(
                f"Skill {name!r} tool definitions could not be read"
            ) from exc
        if not isinstance(raw_tools, list):
            raise ValueError(f"Skill {name!r} get_tools() must return a list")
        tools: list[dict[str, Any]] = []
        tokens: dict[str, SkillExecutionToken] = {}
        local_names: set[str] = set()
        for index, tool_def in enumerate(raw_tools):
            original_name, validated = _validate_tool_definition(tool_def, name, index)
            final_name = f"{raw_prefix}{_SEPARATOR}{original_name}"
            if not _FINAL_NAME_RE.fullmatch(final_name):
                raise ValueError(f"无效的最终工具名: {final_name!r}")
            if final_name in _RESERVED_FINAL_TOOL_NAMES:
                raise ValueError(f"保留的最终工具名: {final_name}")
            if original_name in local_names or final_name in self._final_owners:
                owner = self._final_owners.get(final_name)
                raise ValueError(
                    f"重复的最终工具定义: {final_name}"
                    + (f"（已被技能 {owner!r} 注册）" if owner else "")
                )
            local_names.add(original_name)
            validated["function"]["name"] = final_name
            tools.append(validated)
            tokens[final_name] = SkillExecutionToken(skill, original_name, final_name)
        raw_session_tools = getattr(skill, "session_tools", set())
        if not isinstance(raw_session_tools, (set, frozenset)) or not all(
            isinstance(item, str) for item in raw_session_tools
        ):
            raise ValueError(f"Skill {name!r} session_tools must be a set of names")
        if not raw_session_tools <= local_names:
            unknown = sorted(raw_session_tools - local_names)
            raise ValueError(
                f"Skill {name!r} session_tools contain undeclared tools: {unknown}"
            )
        registered = _RegisteredSkill(
            module=skill,
            name=name,
            prefix=raw_prefix,
            exposed=exposed,
            description=description,
            instructions=instructions,
            tools=tuple(tools),
            tokens=tokens,
            session_tools=frozenset(raw_session_tools),
        )
        self._skills[name] = registered
        for final_name in tokens:
            self._final_owners[final_name] = name
        self._session_tools.update(
            f"{raw_prefix}{_SEPARATOR}{tool_name}"
            for tool_name in registered.session_tools
        )

    def unregister(self, name: str) -> None:
        """注销指定 Skill。"""
        registration = self._skills.pop(name, None)
        if registration is None:
            return
        for final_name in registration.tokens:
            if self._final_owners.get(final_name) == name:
                self._final_owners.pop(final_name, None)
        for tool_name in registration.session_tools:
            self._session_tools.discard(f"{registration.prefix}{_SEPARATOR}{tool_name}")

    def get(self, name: str) -> SkillModule | None:
        registration = self._skills.get(name)
        return registration.module if registration else None

    @property
    def all_skills(self) -> list[SkillModule]:
        return [registration.module for registration in self._skills.values()]

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def is_tool_deferred(self, name: str) -> bool:
        """该技能的工具定义是否默认不注入提示词(需 skills__load_tools 加载)。"""
        if self._eager_tool_skills is None:
            return False
        return name not in self._eager_tool_skills

    @property
    def deferred_skill_names(self) -> list[str]:
        """全部被延后加载的技能名(仍会以一行摘要出现在提示词索引里)。

        不参与主回复管线的技能(exposed_to_main_agent=False)不会出现在这里：
        它们既不能常驻，也不能被 skills__load_tools 加载。
        """
        return [
            name
            for name, registration in self._skills.items()
            if registration.exposed and self.is_tool_deferred(name)
        ]

    def skill_tool_names(self, name: str) -> list[str]:
        """指定技能的最终工具名列表(已加前缀)。"""
        registration = self._skills.get(name)
        if registration is None:
            return []
        return [tool["function"]["name"] for tool in registration.tools]

    def get_tools(self, activated: Iterable[str] | None = None) -> list[dict]:
        """聚合 Skill 的工具定义，自动加 ``{name}__`` 前缀。

        activated 中列出的技能会连同常驻技能一起返回；被延后加载的技能
        只有被显式激活后才会出现在提示词里(见 skills__load_tools)。
        """
        active = set(activated or ())
        tools: list[dict] = []
        for name, registration in self._skills.items():
            if not registration.exposed:
                continue
            if self.is_tool_deferred(name) and name not in active:
                continue
            tools.extend(_deep_copy(tool) for tool in registration.tools)
        return tools

    def get_all_tools(self) -> list[dict]:
        """返回全部技能的工具定义（忽略按需加载策略）。

        仅用于自建工具集的独立 Agent（沙箱维护等）：它们不经过主回复管线的
        按需加载流程，必须一次拿到全部工具。
        """
        tools: list[dict] = []
        for registration in self._skills.values():
            tools.extend(_deep_copy(tool) for tool in registration.tools)
        return tools

    def get_skill_tools(self, name: str) -> list[dict]:
        """返回指定 Skill 的工具定义（已加 ``{name}__`` 前缀）。

        子 agent / 专用 agent 只挂载部分 Skill 时必须用本方法取定义，
        否则工具名缺少前缀，SkillManager.execute 无法路由。
        """
        registration = self._skills.get(name)
        if registration is None:
            return []
        return [_deep_copy(tool) for tool in registration.tools]

    def capture_execution_token(self, prefixed_name: str) -> SkillExecutionToken | None:
        registration = self._owner_of(prefixed_name)
        return registration.tokens.get(prefixed_name) if registration else None

    def _owner_of(self, prefixed_name: str) -> _RegisteredSkill | None:
        """按最终工具名精确定位注册项(前缀可被多个技能共享)。"""
        owner = self._final_owners.get(prefixed_name)
        return self._skills.get(owner) if owner else None

    def get_instructions(self) -> str:
        """聚合所有 Skill 的一行摘要(默认注入提示词,节省 token)。

        完整操作说明不再全量注入,由 `skills__view_instructions` 按需查看
        (与 Markdown 技能「默认元数据 + 按需读取正文」的模式一致)。
        """
        lines: list[str] = []
        for registration in self._skills.values():
            if not registration.exposed:
                continue
            summary = self._instructions_summary(registration)
            if summary:
                lines.append(summary)
        return "\n".join(lines)

    def get_skill_instructions(self, name: str) -> str:
        """返回单个 Skill 的完整操作说明(供 skills__view_instructions 使用)。"""
        registration = self._skills.get(name)
        if registration is None:
            return f"技能不存在: {name}"
        instructions = (registration.instructions or "").strip()
        if not instructions:
            tool_names = [
                tool.get("function", {}).get("name", "")
                for tool in registration.tools
            ]
            return (
                f"{name} 没有额外的操作说明。\n"
                f"可用工具: {', '.join(tool_names) or '(无)'}"
            )
        return f"## {name}\n{instructions}"

    @staticmethod
    def _instructions_summary(registration: _RegisteredSkill) -> str:
        """一行摘要:description 优先,否则取 instructions 首行。"""
        description = (registration.description or "").strip()
        if description:
            return f"- {registration.name}: {description}"
        instructions = (registration.instructions or "").strip()
        if instructions:
            first_line = instructions.splitlines()[0].strip()
            return f"- {registration.name}: {first_line}"
        return ""

    async def execute(
        self,
        prefixed_name: str,
        args: dict[str, Any],
        token: SkillExecutionToken | None = None,
    ) -> str:
        """路由执行：按最终工具名 ``{prefix}__{tool}`` 分派到对应的 Skill。"""
        registration = self._owner_of(prefixed_name)
        if registration is None:
            if token is not None:
                # 调用方持有令牌但注册项已注销/重建
                return f"{_STALE_TOOL_ERROR} [{prefixed_name}]"
            prefixes = sorted({r.prefix for r in self._skills.values()})
            parsed = self._split_name(prefixed_name)
            if parsed is not None and parsed[0] in prefixes:
                return f"未知工具: {prefixed_name}"
            available = ", ".join(prefixes)
            return (
                f"未知工具: {prefixed_name}\n"
                f"可用工具名前缀: {available}\n"
                f"格式: {{prefix}}{_SEPARATOR}{{tool_name}}"
            )
        if token is None:
            token = registration.tokens.get(prefixed_name)
        elif registration.tokens.get(prefixed_name) is not token:
            return f"{_STALE_TOOL_ERROR} [{prefixed_name}]"
        if token is None or token.final_name != prefixed_name:
            return f"未知工具: {prefixed_name}"

        try:
            return await token.module.execute(token.local_name, args)
        except Exception:
            return f"工具执行失败 [{prefixed_name}]"

    def reset_all(self) -> None:
        """复位所有 Skill 的状态。"""
        for registration in self._skills.values():
            registration.module.reset()

    def is_session_tool(self, prefixed_name: str) -> bool:
        """检查指定前缀工具名是否已声明为 Session 模式执行。"""
        return prefixed_name in self._session_tools

    def _parse_name(self, prefixed_name: str) -> tuple[str, str] | None:
        parsed = self._split_name(prefixed_name)
        if parsed is not None and parsed[0] in self._skills:
            return parsed
        return None

    @staticmethod
    def _split_name(prefixed_name: str) -> tuple[str, str] | None:
        if _SEPARATOR not in prefixed_name:
            return None
        skill_name, tool_name = prefixed_name.split(_SEPARATOR, 1)
        return (skill_name, tool_name) if skill_name and tool_name else None


def _deep_copy(d: dict) -> dict:
    return copy.deepcopy(d)


def _validate_tool_definition(
    tool_def: Any, skill_name: str, index: int
) -> tuple[str, dict]:
    label = f"Skill {skill_name!r} tool #{index}"
    if not isinstance(tool_def, dict) or tool_def.get("type") != "function":
        raise ValueError(f"{label} must be a function definition")
    function = tool_def.get("function")
    if not isinstance(function, dict):
        raise ValueError(f"{label} function must be an object")
    local_name = function.get("name")
    if (
        not isinstance(local_name, str)
        or not _LOCAL_NAME_RE.fullmatch(local_name)
        or _SEPARATOR in local_name
    ):
        raise ValueError(f"{label} has invalid local name: {local_name!r}")
    if not isinstance(function.get("description"), str):
        raise ValueError(f"{label} description must be a string")
    schema = function.get("parameters")
    if schema is None:
        schema = {"type": "object", "properties": {}, "required": []}
    elif not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError(f"{label} parameters must have an object root")
    try:
        encoded = json.dumps(tool_def, ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} must be JSON-serializable") from exc
    if len(encoded) > _MAX_SCHEMA_BYTES:
        raise ValueError(f"{label} exceeds {_MAX_SCHEMA_BYTES} bytes")
    _validate_schema(schema, label, schema)
    validated = copy.deepcopy(tool_def)
    validated["function"].setdefault("parameters", dict(schema))
    return local_name, validated


def _validate_schema(node: Any, label: str, root: dict) -> None:
    if not isinstance(node, dict):
        raise ValueError(f"{label} contains a non-object schema")
    ref = node.get("$ref")
    if "$ref" in node:
        if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/")):
            raise ValueError(f"{label} contains an invalid or external ref")
        target = _resolve_pointer(root, ref[1:])
        if target is _MISSING:
            raise ValueError(f"{label} contains dangling local ref {ref!r}")
        if not isinstance(target, dict):
            raise ValueError(f"{label} contains a ref to a non-object schema")
    value = node.get("type")
    valid_types = {"object", "array", "string", "number", "integer", "boolean", "null"}
    if value is not None and not (
        isinstance(value, str)
        and value in valid_types
        or isinstance(value, list)
        and value
        and all(isinstance(v, str) and v in valid_types for v in value)
    ):
        raise ValueError(f"{label} contains malformed type")
    for keyword in ("properties", "$defs", "patternProperties"):
        children = node.get(keyword)
        if children is not None:
            if not isinstance(children, dict) or not all(
                isinstance(k, str) for k in children
            ):
                raise ValueError(f"{label} contains malformed {keyword}")
            for key, child in children.items():
                if keyword == "patternProperties":
                    try:
                        re.compile(key)
                    except re.error as exc:
                        raise ValueError(
                            f"{label} contains malformed patternProperties regex"
                        ) from exc
                _validate_schema(child, label, root)
    required = node.get("required")
    if required is not None and (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
    ):
        raise ValueError(f"{label} contains malformed required")
    properties = node.get("properties")
    if (
        required is not None
        and isinstance(required, list)
        and isinstance(properties, dict)
    ):
        missing = [item for item in required if item not in properties]
        if missing:
            raise ValueError(
                f"{label} required references missing property: {missing[0]!r}"
            )
    if "prefixItems" in node:
        raise ValueError(
            f"{label} contains unsupported tuple schema keyword prefixItems"
        )
    if "items" in node:
        items = node["items"]
        if isinstance(items, list):
            raise ValueError(
                f"{label} contains unsupported tuple schema in array-valued items"
            )
        if not isinstance(items, bool):
            _validate_schema(items, label, root)
    additional = node.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        _validate_schema(additional, label, root)
    for keyword in ("allOf", "anyOf", "oneOf"):
        values = node.get(keyword)
        if values is not None:
            if not isinstance(values, list) or not values:
                raise ValueError(f"{label} contains malformed {keyword}")
            for child in values:
                _validate_schema(child, label, root)
    if "not" in node:
        _validate_schema(node["not"], label, root)
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        raise ValueError(f"{label} contains malformed enum")
    for keyword in (
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    ):
        number = node.get(keyword)
        if number is not None and (
            not isinstance(number, (int, float)) or isinstance(number, bool)
        ):
            raise ValueError(f"{label} contains malformed {keyword}")
    for keyword in (
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    ):
        count = node.get(keyword)
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            raise ValueError(f"{label} contains malformed {keyword}")
    if "pattern" in node:
        pattern = node.get("pattern")
        if not isinstance(pattern, str):
            raise ValueError(f"{label} contains malformed pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{label} contains malformed pattern") from exc
    if "uniqueItems" in node and not isinstance(node["uniqueItems"], bool):
        raise ValueError(f"{label} contains malformed uniqueItems")

    if node is root:
        _reject_recursive_refs(root, label)


def _reject_recursive_refs(root: dict, label: str) -> None:
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: dict) -> None:
        node_id = id(node)
        if node_id in visiting:
            raise ValueError(f"{label} contains an unsupported recursive ref")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in _schema_children(node, root):
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(root)


def _schema_children(node: dict, root: dict) -> list[dict]:
    children: list[dict] = []
    for keyword in ("properties", "$defs", "patternProperties"):
        value = node.get(keyword)
        if isinstance(value, dict):
            children.extend(
                child for child in value.values() if isinstance(child, dict)
            )
    for keyword in ("items", "additionalProperties", "not"):
        value = node.get(keyword)
        if isinstance(value, dict):
            children.append(value)
    for keyword in ("allOf", "anyOf", "oneOf"):
        value = node.get(keyword)
        if isinstance(value, list):
            children.extend(child for child in value if isinstance(child, dict))
    ref = node.get("$ref")
    if isinstance(ref, str):
        target = _resolve_pointer(root, ref[1:])
        if isinstance(target, dict):
            children.append(target)
    return children


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        return _MISSING
    current = document
    for raw in pointer[1:].split("/"):
        if "~" in raw and any(
            index + 1 >= len(raw) or raw[index + 1] not in "01"
            for index, char in enumerate(raw)
            if char == "~"
        ):
            return _MISSING
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current
