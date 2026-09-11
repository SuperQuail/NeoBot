"""技能工具按需加载的共享实现（主回复管线与独立 Agent 共用）。

工具 schema 会随每次模型调用一起发送，全部常驻时代价极高；因此在模型
明确需要某个技能时才通过 `skills__load_tools` 加载，加载后该技能的工具
立即出现在后续模型调用里。
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from typing import Any

LOADER_TOOL_NAME = "skills__load_tools"


def _tool_def(name: str, description: str, parameters: dict | None = None) -> dict:
    params: dict = {"type": "object", "properties": {}, "required": []}
    if parameters:
        params["properties"] = parameters.get("properties", {})
        params["required"] = parameters.get("required", [])
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": params},
    }


class SkillToolActivation:
    """一份「已加载技能」的状态，绑定到某个 Agent 会话/管线。

    Args:
        skill_manager: 提供 get_tools / skill_names / skill_tool_names 的管理器。
        resident: 覆盖常驻技能名单；None 表示沿用 SkillManager 自己的策略。
        authorize: 可选的单工具授权判定（如技能 allowed-tools 白名单）。
    """

    def __init__(
        self,
        skill_manager: Any,
        *,
        resident: Collection[str] | None = None,
        authorize: Callable[[str], bool] | None = None,
    ) -> None:
        self._manager = skill_manager
        self._resident = None if resident is None else frozenset(resident)
        self._authorize = authorize
        self._activated: set[str] = set()
        self._dirty = False

    # ── 状态 ──

    @property
    def manager(self) -> Any:
        return self._manager

    @property
    def activated(self) -> frozenset[str]:
        return frozenset(self._activated)

    def activated_names(self) -> list[str]:
        return sorted(self._activated)

    def consume_dirty(self) -> bool:
        """取出并清除「工具列表已变化」标记。"""
        dirty = self._dirty
        self._dirty = False
        return dirty

    # ── 工具定义 ──

    def tools(self) -> list[dict]:
        """当前应注入模型的动作工具（常驻 + 已加载）。"""
        manager = self._manager
        getter = getattr(manager, "get_tools", None)
        if not callable(getter):
            return []
        try:
            return list(getter(self._activated, resident=self._resident))
        except TypeError:
            # 兼容只接受 activated 的实现
            return list(getter(self._activated))

    def _is_visible(self, name: str) -> bool:
        if self._authorize is None:
            return True
        try:
            return bool(self._authorize(name))
        except Exception:
            return False

    def is_resident(self, name: str) -> bool:
        """该技能是否已经常驻本次会话（常驻覆盖优先于管理器策略）。"""
        if self._resident is not None:
            return name in self._resident
        deferred = getattr(self._manager, "is_tool_deferred", None)
        return not (callable(deferred) and deferred(name))

    def candidates(self) -> list[str]:
        """仍可加载的技能名（已常驻/已加载/不可用的都不列出）。"""
        manager = self._manager
        names = getattr(manager, "deferred_skill_names", None)
        if not names:
            return []
        pending = []
        for name in names:
            if name in self._activated or self.is_resident(name):
                continue
            tool_names = getattr(manager, "skill_tool_names", None)
            available = list(tool_names(name)) if callable(tool_names) else []
            if available and not any(self._is_visible(item) for item in available):
                continue
            pending.append(name)
        return sorted(pending)

    def loader_definition(self) -> dict | None:
        """`skills__load_tools` 的定义；没有可加载技能时返回 None。"""
        pending = self.candidates()
        if not pending:
            return None
        return _tool_def(
            LOADER_TOOL_NAME,
            "按需加载技能的调用工具（工具定义默认不随提示词下发，以节省每次调用的 token）。"
            "需要用到某个技能时，先用本工具加载它，加载后该技能的工具即可在本轮直接调用。"
            "一次可加载多个技能；已经加载过的技能无需重复加载。",
            {
                "properties": {
                    "skills": {
                        "type": "array",
                        "items": {"type": "string", "enum": pending},
                        "description": "要加载的技能名列表，取自提示词的技能索引。",
                    },
                },
                "required": ["skills"],
            },
        )

    # ── 加载 ──

    def load(self, args: dict) -> str:
        """执行一次按需加载，返回给模型的可读结果。"""
        manager = self._manager
        raw = args.get("skills")
        if isinstance(raw, str):
            requested = [raw]
        elif isinstance(raw, (list, tuple)):
            requested = [str(item) for item in raw]
        else:
            return "Error: 缺少 skills 参数（字符串数组）"
        requested = [item.strip() for item in requested if str(item).strip()]
        if not requested:
            return "Error: skills 参数为空"

        known = set(getattr(manager, "skill_names", None) or [])
        deferred = set(getattr(manager, "deferred_skill_names", None) or [])
        added: list[str] = []
        already: list[str] = []
        unknown: list[str] = []
        hidden: list[str] = []
        for name in requested:
            if name not in known:
                unknown.append(name)
                continue
            if name in self._activated or self.is_resident(name) or name not in deferred:
                already.append(name)
                continue
            tool_names = list(getattr(manager, "skill_tool_names", lambda _n: [])(name))
            visible = [item for item in tool_names if self._is_visible(item)]
            if not visible:
                hidden.append(name)
                continue
            self._activated.add(name)
            added.append(f"{name}: {', '.join(visible)}")

        if added:
            self._dirty = True

        lines: list[str] = []
        if added:
            lines.append("已加载技能工具（本轮即可直接调用）：")
            lines.extend(f"  - {item}" for item in added)
        if already:
            lines.append(f"已经可用，无需重复加载：{', '.join(sorted(set(already)))}")
        if unknown:
            lines.append(f"未知技能名：{', '.join(sorted(set(unknown)))}")
        if hidden:
            lines.append(
                f"当前会话无法使用（能力或白名单限制）：{', '.join(sorted(set(hidden)))}"
            )
        if not lines:
            return "没有可加载的技能"
        remaining = self.candidates()
        if remaining:
            lines.append(f"尚未加载的技能：{', '.join(remaining)}")
        return "\n".join(lines)

    def load_many(self, names: Iterable[str]) -> str:
        return self.load({"skills": list(names)})
