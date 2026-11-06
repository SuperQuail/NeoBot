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

from neobot_app.prompt.store import packaged_template as _packaged_template
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
_FALLBACK_SYSTEM_PROMPT = _packaged_template("self_heal", "system_prompt")


def _build_system_prompt(
    config: SelfHealAgentConfig,
    *,
    peer_descriptions: str = "",
    prompt_store: Any = None,
) -> str:
    from neobot_app.prompt.render import render_template
    from neobot_app.prompt.store import packaged_template

    base = ""
    runtime = ""
    if prompt_store is not None:
        base = prompt_store.get("self_heal", "system_prompt", default="")
        runtime = prompt_store.get("self_heal", "runtime", default="")
    if not base:
        base = packaged_template("self_heal", "system_prompt")
    if not runtime:
        runtime = packaged_template("self_heal", "runtime")
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
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        if prompt_store is not None:
            desc = prompt_store.get("self_heal", "description", default="")
            if desc:
                self.description = desc
        self._manager = manager
        executor = SelfHealToolExecutor(
            logger=logger,
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

        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(
                cfg, peer_descriptions=peer_descriptions, prompt_store=prompt_store
            ),
            on_model_usage=_record_usage,
            max_iterations=30,
            command_timeout=int(cfg.timeout_seconds),
            logger=logger or NullLogger(),
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
