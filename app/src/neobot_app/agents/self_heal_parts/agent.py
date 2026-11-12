"""自修复 Agent：系统提示词、LLM Agent 与构造器。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.types import (
    State,
    ToolAccessPolicy,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.prompt.assets import raw_text
from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)

from .models import (
    EXPOSED_TO_MAIN_AGENT_DESCRIPTION,
    SelfHealAgentConfig,
    _default_resolver,
)

from .tool_executor import SelfHealToolExecutor

if TYPE_CHECKING:
    from .manager import SelfHealManager

#: 兼容旧导出名：内容来自 ``prompts.toml`` 的 ``[self_heal].system_prompt``，
#: 代码里不再维护第二份文案（旧调用方/测试仍可 import）。
_FALLBACK_SYSTEM_PROMPT = raw_text("self_heal", "system_prompt")

#: 自修复上下文超过该字符数时触发 compact（复用 runtime/compact 的结构化 checkpoint）。
_COMPACT_TRIGGER_CHARS = 120_000
#: 单次 compact 调用的超时（秒）；相对 2 小时总预算很短，失败不影响主流程。
_COMPACT_TIMEOUT_SECONDS = 120.0


def _build_system_prompt(
    config: SelfHealAgentConfig,
    *,
    peer_descriptions: str = "",
    prompt_store: Any = None,
) -> str:
    from neobot_app.prompt.render import render_template

    base = raw_text("self_heal", "system_prompt", store=prompt_store)
    runtime = raw_text("self_heal", "runtime", store=prompt_store)
    detail = render_template(
        runtime,
        {"timeout_seconds": config.timeout_seconds, "peer_descriptions": peer_descriptions},
    )
    return base + "\n\n" + detail + "\n"


class SelfHealAgent:
    """由 LLM 驱动的自修复 Agent，结构上镜像 ProblemSolverAgent。"""

    def __init__(
        self,
        provider: Provider,
        *,
        config: SelfHealAgentConfig | None = None,
        logger: Logger | None = None,
        manager: SelfHealManager | None = None,
        sandbox_service: Any = None,
        data_dir: Path | None = None,
        source_roots: list[Path] | None = None,
        log_file: Path | None = None,
        repair_hooks: dict[str, Any] | None = None,
        web_search_config: dict | None = None,
        vision_provider: Any = None,
        peer_descriptions: str = "",
        prompt_store: Any = None,
    ) -> None:
        cfg = config or SelfHealAgentConfig()
        log = logger or NullLogger()
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        if prompt_store is not None:
            desc = raw_text("self_heal", "description", store=prompt_store)
            if desc:
                self.description = desc
        self._manager = manager
        executor = SelfHealToolExecutor(
            logger=log,
            sandbox_service=sandbox_service,
            source_roots=source_roots,
            log_file=log_file,
            sandbox_debug_dir=cfg.sandbox_debug_dir,
            repair_hooks=repair_hooks or {},
            web_search_config=web_search_config,
            vision_provider=vision_provider,
        )
        self._toolset = Toolset(
            executor=executor,
            specs=[
                ToolSpec(definition=d, access_resolver=_default_resolver)
                for d in executor.definitions()
            ],
            policy=ToolAccessPolicy(),
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

        async def _compact_self_heal_context(messages: list[dict]) -> list[dict] | None:
            """上下文过长时用紧凑检查点替换较早消息；失败返回 None（不影响任务）。"""
            total_chars = sum(
                len(str(message.get("content") or ""))
                + len(str(message.get("tool_calls") or ""))
                for message in messages
            )
            if total_chars < _COMPACT_TRIGGER_CHARS:
                return None
            from neobot_app.runtime.compact import compact_messages

            result = await compact_messages(
                provider, messages, retain=8, timeout=_COMPACT_TIMEOUT_SECONDS
            )
            if not result:
                log.warning(
                    "self_heal 上下文压缩失败，继续使用原上下文",
                    chars=total_chars,
                    messages=len(messages),
                )
                return None
            log.info(
                "self_heal 上下文已压缩",
                chars_before=total_chars,
                messages_before=len(messages),
                messages_after=len(result["messages"]),
            )
            return result["messages"]

        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(
                cfg, peer_descriptions=peer_descriptions, prompt_store=prompt_store
            ),
            on_model_usage=_record_usage,
            max_iterations=None,
            command_timeout=int(cfg.timeout_seconds),
            message_compactor=_compact_self_heal_context,
            logger=log,
        )

    def _build_toolset(self, executor: SelfHealToolExecutor) -> Toolset:
        specs = [
            ToolSpec(definition=d, access_resolver=_default_resolver)
            for d in executor.definitions()
        ]
        return Toolset(executor=executor, specs=specs, policy=ToolAccessPolicy())

    async def _invoke_direct(self, state: State) -> State:
        """直接调用入口（由 SelfHealManager 在后台任务中调用）。"""
        self._toolset.executor.reset_search()
        token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
        try:
            return await self._agent.invoke(state)
        finally:
            CURRENT_USAGE_MODULE.reset(token_m)

    async def stream_invoke(self, state: State):
        token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            CURRENT_USAGE_MODULE.reset(token_m)

    async def close(self) -> None:
        await self._agent.close()


# ── Builder ─────────────────────────────────────────────────────────────────


def build_self_heal_agent(
    provider: Provider | None,
    *,
    config: SelfHealAgentConfig | Any = None,
    logger: Logger | None = None,
    manager: SelfHealManager | None = None,
    sandbox_service: Any = None,
    data_dir: Path | None = None,
    source_roots: list[Path] | None = None,
    log_file: Path | None = None,
    repair_hooks: dict[str, Any] | None = None,
    web_search_config: dict | None = None,
    vision_provider: Any = None,
    peer_descriptions: str = "",
    prompt_store: Any = None,
) -> SelfHealAgent | None:
    """构建 SelfHealAgent；provider 不可用时返回 None（自修复功能降级，不影响主流程）。"""
    cfg = (
        config
        if isinstance(config, SelfHealAgentConfig)
        else SelfHealAgentConfig.from_schema(config)
    )
    if provider is None:
        (logger or NullLogger()).warning(
            "self-heal agent 未启用：provider 不可用，请检查模型配置"
        )
        return None
    # provider 可能是只读/共享实例（原生视觉包装器的 max_tokens 是只读属性）。
    # 这里失败不能让 Bot 启动崩溃：自修复是可选能力，降级为「沿用 provider 自身预算」即可。
    try:
        provider.max_tokens = cfg.max_tokens
    except AttributeError:
        (logger or NullLogger()).warning(
            "provider.max_tokens 只读，已跳过自修复 Agent 的输出预算覆盖",
            requested_max_tokens=cfg.max_tokens,
        )
    agent = SelfHealAgent(
        provider=provider,
        config=cfg,
        logger=logger,
        manager=manager,
        sandbox_service=sandbox_service,
        data_dir=data_dir,
        source_roots=source_roots,
        log_file=log_file,
        repair_hooks=repair_hooks or {},
        web_search_config=web_search_config,
        vision_provider=vision_provider,
        peer_descriptions=peer_descriptions,
        prompt_store=prompt_store,
    )
    if manager is not None:
        manager.set_agent(agent)
        manager.set_prompt_store(prompt_store)
    return agent
