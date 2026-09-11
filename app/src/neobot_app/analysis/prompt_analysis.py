"""提示词分析：统计各 Agent 装配出的提示词字符数与估算 token。

估算规则（面板「分析」页展示的口径，仅用于量级参考）：

- 中日韩字符（CJK）× 0.6 token
- 其他字符（英文/数字/标点/空白）× 0.3 token

本模块**只做本地装配与统计**：不联网、不调用模型、不写数据库。
各 Agent 的提示词来源由装配层（bootstrap）以 loader 形式注入，
这样新增一个 Agent 只需注册一个 loader，分析模块不必认识任何具体 Agent。
"""

from __future__ import annotations

import inspect
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.analysis.agent_spec import AgentCatalog

#: 展示口径说明（面板直接展示这行，避免用户误解为真实计费 token）
TOKEN_RULE_TEXT = "估算口径：中文字符 × 0.6 + 其他字符 × 0.3（非真实计费 token）"

#: CJK 及日韩文字范围
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")

#: 单部分返回的文本上限（面板展示用；超出只截断展示，统计仍按全文算）
DEFAULT_TEXT_LIMIT = 40000

#: loader 返回：[(标签, 类型, 文本), ...] 或 [PromptPart, ...]（同步/异步均可）
Loader = Callable[[], Any]


def estimate_tokens(text: str) -> float:
    """按面板口径估算 token：CJK × 0.6 + 其他 × 0.3。"""
    if not text:
        return 0.0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return round(cjk * 0.6 + other * 0.3, 1)


@dataclass(slots=True)
class PromptPart:
    """提示词的一部分（系统提示词 / 工具定义 / 历史 / 指令等）。"""

    label: str
    kind: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def tokens(self) -> float:
        return estimate_tokens(self.text)

    def to_dict(self, *, text_limit: int = DEFAULT_TEXT_LIMIT) -> dict[str, Any]:
        truncated = len(self.text) > text_limit
        return {
            "label": self.label,
            "kind": self.kind,
            "chars": self.chars,
            "tokens": self.tokens,
            "truncated": truncated,
            "text": self.text[:text_limit],
        }


def as_part(item: Any) -> PromptPart:
    """把 loader 的返回值规整成 PromptPart。"""
    if isinstance(item, PromptPart):
        return item
    label, kind, text = item
    return PromptPart(label=str(label), kind=str(kind), text=str(text))


@dataclass(slots=True)
class PromptSource:
    """一个 Agent（或一个提示词装配点）的来源声明。"""

    name: str
    loader: Loader
    kind: str = "agent"
    note: str = ""
    model: str = ""


@dataclass(slots=True)
class PromptAnalyzer:
    """收集各来源的提示词装配结果并统计（不调用模型）。

    两类来源：
    - catalog：**规范化 Agent**（实现 agent_prompt_parts()，由装配层注册或经宿主服务自动发现），
      新增 Agent 不需要改这里；
    - _sources：非 Agent 的补充条目（模型路由、委派指令等）。
    """

    logger: Logger | None = None
    text_limit: int = DEFAULT_TEXT_LIMIT
    catalog: AgentCatalog | None = None
    _sources: list[PromptSource] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.logger = self.logger or NullLogger()
        if self.catalog is None:
            self.catalog = AgentCatalog(logger=self.logger)

    def add_source(
        self,
        name: str,
        loader: Loader,
        *,
        kind: str = "agent",
        note: str = "",
        model: str = "",
    ) -> None:
        """注册一个提示词来源；同名覆盖（软重启重新装配时不重复堆积）。"""
        self._sources = [item for item in self._sources if item.name != name]
        self._sources.append(
            PromptSource(name=name, loader=loader, kind=kind, note=note, model=model)
        )

    @property
    def sources(self) -> tuple[PromptSource, ...]:
        return tuple(self._sources)

    async def collect(self) -> dict[str, Any]:
        """逐个来源装配并统计；单个来源失败不影响其余（错误写进该条目）。"""
        agents: list[dict[str, Any]] = []
        catalog_specs = self.catalog.specs if self.catalog is not None else ()
        sources = list(self._sources) + [
            PromptSource(
                name=spec.name,
                loader=spec.loader,
                kind=spec.kind,
                note=spec.note,
                model=spec.model,
            )
            for spec in catalog_specs
        ]
        for source in sources:
            entry: dict[str, Any] = {
                "name": source.name,
                "kind": source.kind,
                "note": source.note,
                "model": source.model,
            }
            try:
                raw = source.loader()
                if inspect.isawaitable(raw):
                    raw = await raw
                parts = [as_part(item) for item in (raw or [])]
            except Exception as exc:
                self.logger.warning(f"提示词分析失败: {source.name}: {exc}")
                entry.update(
                    {
                        "error": f"{type(exc).__name__}: {exc}",
                        "parts": [],
                        "total_chars": 0,
                        "total_tokens": 0.0,
                    }
                )
                agents.append(entry)
                continue
            entry["parts"] = [part.to_dict(text_limit=self.text_limit) for part in parts]
            entry["total_chars"] = sum(part.chars for part in parts)
            entry["total_tokens"] = round(sum(part.tokens for part in parts), 1)
            agents.append(entry)
        return {
            "available": True,
            "rule": TOKEN_RULE_TEXT,
            "generated_at": int(time.time()),
            "agents": agents,
        }


def tools_to_text(definitions: Iterable[dict[str, Any]]) -> str:
    """把工具定义渲染成 JSON 文本（与实际发给模型的结构一致，便于对账）。"""
    import json

    return json.dumps(list(definitions), ensure_ascii=False, indent=1)
