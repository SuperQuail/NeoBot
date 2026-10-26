"""解题 Agent 本体与构造器。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.types import (
    ChatChunk,
    State,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)
from neobot_app.agent_tools.contracts import ToolContext

from .models import (
    EXPOSED_TO_MAIN_AGENT_DESCRIPTION,
    ProblemSolverAgentConfig,
    _CHAT_FLOW_ID,
    _MAX_AGENT_ITERATIONS,
    _MODE_NOTE_NATIVE,
    _MODE_NOTE_PTC,
    _SOLVER_CHAT_CONTEXT,
    _TOOL_CONTEXT,
    _default_resolver,
)

from .prompts import _build_system_prompt
from .toolset_builder import build_problem_solver_toolset

if TYPE_CHECKING:
    from .manager import ProblemSolverManager


class ProblemSolverAgent:
    """LLM-backed agent dedicated to complex problem solving.

    invoke() → 提交后台解题任务，立即返回
    _invoke_direct() → 直接执行解题（供后台任务使用）
    """

    def __init__(
        self,
        provider: Provider,
        *,
        config: ProblemSolverAgentConfig | None = None,
        logger: Logger | None = None,
        web_search_config: dict | None = None,
        manager: ProblemSolverManager | None = None,
        peer_descriptions: str = "",
        sandbox_service: Any = None,
        vision_provider: Any = None,
        prompt_store: Any = None,
    ) -> None:
        cfg = config or ProblemSolverAgentConfig()
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        if prompt_store is not None:
            desc = prompt_store.get("problem_solver", "description", default="")
            if desc:
                self.description = desc
        self._manager = manager
        self._toolset = build_problem_solver_toolset(
            config=cfg,
            logger=logger,
            web_search_config=web_search_config,
            sandbox_service=sandbox_service,
            vision_provider=vision_provider,
        )
        self.tool_definitions = self._toolset.definitions()

        async def _record_usage(model_name, input_tokens, output_tokens):
            await get_usage_tracker().record(
                module=CURRENT_USAGE_MODULE.get(""),
                model_name=model_name,
                registered_key=getattr(provider, "registered_key", ""),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                conversation_kind=CURRENT_CONVERSATION_KIND.get(""),
                conversation_id=CURRENT_CONVERSATION_ID.get(""),
            )

        # 提示词上下文:绑定工具运行时后需要用同一组取值重建系统提示词
        self._cfg = cfg
        self._peer_descriptions = peer_descriptions
        self._prompt_store = prompt_store
        self._mode_note = ""
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=self._render_system_prompt(),
            on_model_usage=_record_usage,
            max_iterations=_MAX_AGENT_ITERATIONS,
            command_timeout=int(cfg.timeout_seconds),
            logger=logger or NullLogger(),
        )

    def _render_system_prompt(self) -> str:
        """按当前提示词取值渲染系统提示词(模式说明随工具运行时变化)。"""
        return _build_system_prompt(
            self._cfg,
            peer_descriptions=self._peer_descriptions,
            prompt_store=self._prompt_store,
            max_iterations=_MAX_AGENT_ITERATIONS,
            mode_note=self._mode_note,
        )

    def set_tool_runtime(self, runtime: Any) -> None:
        """Bind once during application assembly, before accepting solve tasks."""
        executor = self._toolset.executor
        executor._runtime = runtime
        specs = [ToolSpec(d, _default_resolver) for d in executor.definitions()]
        self._toolset = Toolset(executor=executor, specs=specs)
        previous = self._agent
        self._mode_note = _MODE_NOTE_PTC if runtime.mode == "ptc" else _MODE_NOTE_NATIVE
        self._agent = Agent(
            previous.provider, toolset=self._toolset, include_builtin_tools=False,
            description=self.description,
            system_prompt=self._render_system_prompt(),
            on_model_usage=previous._on_model_usage, max_iterations=previous.max_iterations,
            command_timeout=previous.command_timeout, logger=previous._logger,
        )
        self.tool_definitions = self._toolset.definitions()

    async def invoke(self, state: State) -> State:
        """主 Agent 委托入口：提交后台解题任务并立即返回。"""
        if self._manager is None:
            return {
                "messages": [
                    {"role": "assistant", "content": "错误：解题后台管理器未配置"}
                ],
            }

        messages = state.get("messages", [])
        question = messages[-1]["content"] if messages else ""
        question_str = str(question) if question else ""

        delegate_context = str(state.get("_delegate_context") or "")

        # Authorization never comes from user-editable prompt prose.
        trusted = state.get("_agent_tool_context")
        if isinstance(trusted, ToolContext):
            conv_kind, conv_id = trusted.chat_flow_id.split(":", 1)
        else:
            conv_kind, conv_id = None, None
        if not conv_kind or not conv_id:
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "错误：无法确定当前会话信息，请重试",
                    }
                ],
            }

        pipeline_key = f"{conv_kind}:{conv_id}"
        result_json = await self._manager.submit(
            pipeline_key=pipeline_key,
            conversation_kind=conv_kind,
            conversation_id=conv_id,
            question=question_str,
            delegate_context=delegate_context,
            execution_context=trusted,
        )
        return {
            "messages": [{"role": "assistant", "content": result_json}],
        }

    @staticmethod
    def _parse_conv_from_context(context: str) -> tuple[str, str]:
        """从委托上下文解析当前会话 kind 和 id。"""
        import re

        m = re.search(r"\[当前会话\]\s*\nkind=(\w+)\s*\nid=(\S+)", context)
        if m:
            return m.group(1), m.group(2)
        m = re.search(r"kind=(\w+)\s*\nid=(\S+)", context)
        if m:
            return m.group(1), m.group(2)
        return "", ""

    async def _invoke_direct(self, state: State) -> State:
        """内部直接执行解题（供 ProblemSolverManager 后台任务使用）。"""
        self._toolset.executor.reset_search()
        token = _SOLVER_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        token_cf = _CHAT_FLOW_ID.set(str(state.get("_chat_flow_id") or ""))
        trusted = state.get("_agent_tool_context")
        token_tc = _TOOL_CONTEXT.set(trusted if isinstance(trusted, ToolContext) else None)
        token_m = CURRENT_USAGE_MODULE.set("agent:problem_solver")
        try:
            return await self._agent.invoke(state)
        finally:
            _SOLVER_CHAT_CONTEXT.reset(token)
            _CHAT_FLOW_ID.reset(token_cf)
            _TOOL_CONTEXT.reset(token_tc)
            CURRENT_USAGE_MODULE.reset(token_m)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _SOLVER_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        token_cf = _CHAT_FLOW_ID.set(str(state.get("_chat_flow_id") or ""))
        trusted = state.get("_agent_tool_context")
        token_tc = _TOOL_CONTEXT.set(trusted if isinstance(trusted, ToolContext) else None)
        token_m = CURRENT_USAGE_MODULE.set("agent:problem_solver")
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _SOLVER_CHAT_CONTEXT.reset(token)
            _CHAT_FLOW_ID.reset(token_cf)
            _TOOL_CONTEXT.reset(token_tc)
            CURRENT_USAGE_MODULE.reset(token_m)

    async def close(self) -> None:
        await self._agent.close()


def build_problem_solver_agent(
    provider: Provider | None,
    *,
    config: ProblemSolverAgentConfig | Any = None,
    logger: Logger | None = None,
    manager: ProblemSolverManager | None = None,
    web_search_config: dict | None = None,
    peer_descriptions: str = "",
    sandbox_service: Any = None,
    vision_provider: Any = None,
    prompt_store: Any = None,
) -> ProblemSolverAgent | None:
    """构建解题 Agent 并关联到 Manager。

    Args:
        provider: LLM provider
        config: 解题 Agent 配置
        logger: 日志记录器
        manager: 后台任务管理器
        web_search_config: 联网搜索配置字典，包含 engines, max_rounds, preview_pages_limit
        peer_descriptions: 同级 sub agent 描述
        sandbox_service: 沙箱文件服务，提供 run_python/write_file/read_file/list_files 工具
        vision_provider: 视觉模型 provider，提供 parse_image 工具
        prompt_store: 提示词存储(提示词文件来源;None 时使用内置兜底)
    """
    cfg = (
        config
        if isinstance(config, ProblemSolverAgentConfig)
        else ProblemSolverAgentConfig.from_schema(config)
    )
    if provider is None:
        (logger or NullLogger()).warning(
            "problem solver agent 未启用：provider 不可用，请检查模型配置"
        )
        return None
    # 解题 agent 的 max_tokens 覆盖 agent 模型的默认值，
    # 否则 agent 模型的 max_output_tokens 会限制解题输出长度。
    # provider 为只读/共享实例时（原生视觉包装器）不能让装配崩溃：降级为沿用其自身预算。
    try:
        provider.max_tokens = cfg.max_tokens
    except AttributeError:
        (logger or NullLogger()).warning(
            "provider.max_tokens 只读，已跳过解题 Agent 的输出预算覆盖",
            requested_max_tokens=cfg.max_tokens,
        )
    agent = ProblemSolverAgent(
        provider=provider,
        config=cfg,
        logger=logger,
        web_search_config=web_search_config,
        manager=manager,
        peer_descriptions=peer_descriptions,
        sandbox_service=sandbox_service,
        vision_provider=vision_provider,
        prompt_store=prompt_store,
    )
    if manager is not None:
        manager.set_agent(agent)
        manager.set_prompt_store(prompt_store)
    return agent
