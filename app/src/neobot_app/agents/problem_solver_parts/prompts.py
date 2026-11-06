"""解题 Agent 的系统提示词组装与内置兜底文案。"""

from __future__ import annotations

from typing import Any


from neobot_app.prompt.render import render_template
from neobot_app.prompt.store import get_template_value, packaged_template

from .models import (
    ProblemSolverAgentConfig,
    _MAX_AGENT_ITERATIONS,
    _MODE_NOTE_NATIVE,
    _MODE_NOTE_PTC,
)


def prompt_text(prompt_store: Any, key: str) -> str:
    """读取 [problem_solver] 的文本键(自定义文件优先,缺失时用内置模板)。"""
    return get_template_value(prompt_store, "problem_solver", key) or packaged_template(
        "problem_solver", key
    )


def load_mode_note(prompt_store: Any, mode: str) -> str:
    """按工具运行时模式读取 [problem_solver.runtime] 的任务模式说明。"""
    key = "mode_note_ptc" if mode == "ptc" else "mode_note_native"
    if prompt_store is not None:
        value = prompt_store.sub_section("problem_solver", "runtime").get(key)
        if isinstance(value, str) and value.strip():
            return value
    return _MODE_NOTE_PTC if mode == "ptc" else _MODE_NOTE_NATIVE


def _runtime_template(prompt_store: Any) -> str:
    """读取 [problem_solver.runtime] 子表模板,缺失时用内置兜底。"""
    if prompt_store is not None:
        section = prompt_store.sub_section("problem_solver", "runtime")
        value = section.get("template")
        if isinstance(value, str) and value.strip():
            return value
    return _FALLBACK_RUNTIME_TEMPLATE


def _build_system_prompt(
    config: ProblemSolverAgentConfig | None,
    *,
    peer_descriptions: str = "",
    prompt_store: Any = None,
    max_iterations: int = _MAX_AGENT_ITERATIONS,
    mode_note: str = "",
) -> str:
    """组装解题 Agent 的系统提示词。

    正文来自 [problem_solver].system_prompt,运行时动态信息(同级 Agent 描述、
    超时、最大轮次、当前任务模式)来自 [problem_solver.runtime],两者都支持
    用户在 data/prompts/custom/prompts.toml 中覆盖。
    """
    cfg = config or ProblemSolverAgentConfig()
    base = get_template_value(
        prompt_store,
        "problem_solver",
        "system_prompt",
        default=_FALLBACK_SYSTEM_PROMPT,
    )
    try:
        timeout_value = int(float(getattr(cfg, "timeout_seconds", 600.0) or 600.0))
    except (TypeError, ValueError):
        timeout_value = 600
    values = {
        "timeout_seconds": timeout_value,
        "max_iterations": max_iterations,
        "peer_descriptions": peer_descriptions,
        "mode_note": mode_note,
        "bot_name": "",
    }
    body = render_template(base, values)
    appendix = render_template(_runtime_template(prompt_store), values)
    return f"{body}\n\n{appendix}" if appendix else body


#: 兼容旧导出名：内容来自 prompts.toml 的 [problem_solver]，代码不再维护副本。
_FALLBACK_SYSTEM_PROMPT = packaged_template("problem_solver", "system_prompt")


_FALLBACK_RUNTIME_TEMPLATE = packaged_template(
    "problem_solver", "runtime.template"
)

