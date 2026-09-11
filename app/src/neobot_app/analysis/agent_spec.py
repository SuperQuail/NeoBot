"""Agent 提示词规范：实现 agent_prompt_parts() 即被分析页自动收集。

新增 Agent 不需要再改分析代码或装配代码：

1. Agent（或持有它的 manager/服务）实现一个方法::

       def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
           # [(部分标签, 类型, 文本), ...]；允许 async
           ...

   可选属性：agent_name（展示名，缺省用类名）、agent_kind、agent_note、agent_model。

2. 装配层只做一件事：把它注册进宿主服务注册表（插件也一样），
   分析器启动时会扫描注册表，自动把实现该协议的组件收进来。

因此「以后新增 Agent」= 实现一个方法 + 注册服务，分析页自动出现，
不需要动 bootstrap 的分析来源列表，也不需要动前端。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

#: 规范化方法名（唯一契约）
AGENT_PROMPT_METHOD = "agent_prompt_parts"

#: 展示用可选属性
_NAME_ATTR = "agent_name"
_KIND_ATTR = "agent_kind"
_NOTE_ATTR = "agent_note"
_MODEL_ATTR = "agent_model"


def agent_prompt_parts_of(obj: Any) -> Callable[[], Any] | None:
    """返回对象上的提示词装配方法；未实现规范时返回 None。"""
    method = getattr(obj, AGENT_PROMPT_METHOD, None)
    return method if callable(method) else None


@dataclass(slots=True)
class AgentSpec:
    """一个符合规范的 Agent 来源。"""

    name: str
    loader: Callable[[], Any]
    kind: str = "agent"
    note: str = ""
    model: str = ""


@dataclass(slots=True)
class AgentCatalog:
    """Agent 目录：显式注册 + 从宿主服务注册表自动发现。"""

    logger: Logger | None = None
    _specs: list[AgentSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.logger = self.logger or NullLogger()

    @property
    def specs(self) -> tuple[AgentSpec, ...]:
        return tuple(self._specs)

    def register(
        self,
        obj: Any,
        *,
        name: str | None = None,
        kind: str = "agent",
        note: str = "",
        model: str = "",
    ) -> bool:
        """注册一个符合规范的对象；未实现 agent_prompt_parts() 时忽略（返回 False）。"""
        loader = agent_prompt_parts_of(obj)
        if loader is None:
            return False
        display = str(
            name
            or getattr(obj, _NAME_ATTR, "")
            or type(obj).__name__
        ).strip()
        if not display:
            return False
        self._specs = [item for item in self._specs if item.name != display]
        self._specs.append(
            AgentSpec(
                name=display,
                loader=loader,
                kind=str(getattr(obj, _KIND_ATTR, "") or kind),
                note=str(note or getattr(obj, _NOTE_ATTR, "") or ""),
                model=str(model or getattr(obj, _MODEL_ATTR, "") or ""),
            )
        )
        return True

    def discover(self, service_registry: Any) -> int:
        """扫描宿主服务注册表，自动收集所有实现规范的组件。

        这是「以后新增 Agent 不用适配」的关键：Agent 只要把自己的对象注册成宿主服务
        （官方插件、第三方插件、本体组件一视同仁），就会出现在分析页。
        """
        found = 0
        try:
            described = service_registry.describe() or []
        except Exception as exc:
            self.logger.warning(f"扫描宿主服务失败: {exc}")
            return 0
        for item in described:
            name = str(
                (item.get("name") if isinstance(item, dict) else getattr(item, "name", "")) or ""
            )
            if not name:
                continue
            try:
                obj = service_registry.get(name)
            except Exception:
                continue
            if obj is None or agent_prompt_parts_of(obj) is None:
                continue
            if self.register(obj, name=getattr(obj, _NAME_ATTR, "") or name):
                found += 1
        return found

@dataclass(slots=True)
class PromptPartsProvider:
    """把「装配出来的提示词来源」也纳入同一规范。

    主对话提示词、沙箱维护工具集、委派指令、编号路由这类来源不是 Agent 对象，
    而是装配阶段拼出来的；用本类包一层后，它们与真正的 Agent 走**同一条**收集路径
    （AgentCatalog），分析器不再需要区分「对象」与「散落来源」。
    """

    agent_name: str
    loader: Callable[[], Any]
    agent_kind: str = "agent"
    agent_note: str = ""
    agent_model: str = ""

    def agent_prompt_parts(self) -> Any:
        return self.loader()
