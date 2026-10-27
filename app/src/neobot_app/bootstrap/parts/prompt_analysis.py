"""装配提示词分析目录与各 Agent 的 prompt parts provider。"""

from __future__ import annotations

from .maintenance_schedule import MAINTENANCE_RESIDENT_SKILLS
from .state import _BuildState


def _build_prompt_analysis(state: _BuildState) -> None:
    """装配提示词分析目录与各 Agent 的 prompt parts provider。"""
    agent_registry = state.agent_registry
    archive_summary_service = state.archive_summary_service
    config = state.config
    group_queue = state.group_queue
    logger_factory = state.logger_factory
    memory_svcs = state.memory_svcs
    problem_solver_manager = state.problem_solver_manager
    prompt_store = state.prompt_store
    sandbox = state.sandbox
    self_heal_manager = state.self_heal_manager
    skill_manager = state.skill_manager
    vision_provider = state.vision_provider

    # ── 提示词分析（面板「分析」页）：只做本地装配统计，不调用模型 ──
    from neobot_app.analysis.agent_spec import PromptPartsProvider
    from neobot_app.analysis.prompt_analysis import PromptAnalyzer, tools_to_text

    prompt_analyzer = PromptAnalyzer(logger=logger_factory.get_logger("app.analysis"))

    async def _main_agent_parts() -> list:
        try:
            empty_queue = type(group_queue)()
        except Exception:
            empty_queue = group_queue
        system_prompt = await memory_svcs["prompt_builder"].build_group_chat_prompt(
            0, empty_queue
        )
        from neobot_app.skills.agent_toolset import LiveToolset, SkillToolsetExecutor

        definitions = LiveToolset(executor=SkillToolsetExecutor(skill_manager)).definitions()
        return [
            ("系统提示词（群聊 · 空聊天）", "system", system_prompt),
            (f"工具定义（{len(definitions)} 个 · 全部 skill 包）", "tools", tools_to_text(definitions)),
        ]

    async def _maintenance_agent_parts() -> list:
        from neobot_app.prompt.store import get_template_value

        prompt = get_template_value(prompt_store, "maintenance", "system_prompt")
        from neobot_app.skills.agent_toolset import LiveToolset, SkillToolsetExecutor

        definitions = LiveToolset(
            executor=SkillToolsetExecutor(skill_manager, resident=MAINTENANCE_RESIDENT_SKILLS)
        ).definitions()
        return [
            ("系统提示词", "system", prompt),
            (f"工具定义（{len(definitions)} 个 · 常驻精简集）", "tools", tools_to_text(definitions)),
        ]

    prompt_analyzer.catalog.register(
        PromptPartsProvider(
            "主 Agent（对话）",
            _main_agent_parts,
            agent_kind="agent",
            agent_note="空聊天（不含历史与记忆）；工具按全部 skill 包统计，实际请求还会按 agent 模式裁剪",
        )
    )
    prompt_analyzer.catalog.register(
        PromptPartsProvider(
            "沙箱维护 Agent",
            _maintenance_agent_parts,
            agent_kind="agent",
            agent_note="独立 AI 循环：常驻精简工具集 + 按需加载",
        )
    )

    def _archive_summary_parts() -> list:
        service = archive_summary_service
        prompt = service._build_summary_prompt(
            conversation_kind="group", conversation_id="0", messages=[]
        )
        definitions = list(getattr(service, "_tool_definitions", []) or [])
        parts = [("总结指令（群聊 · 空会话）", "system", prompt)]
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

    def _problem_solver_parts() -> list:
        from neobot_app.agents.problem_solver import _build_system_prompt

        cfg = getattr(getattr(config, "agent", None), "problem_solver", None)
        return [("系统提示词", "system", _build_system_prompt(cfg, prompt_store=prompt_store))]

    def _self_heal_parts() -> list:
        from neobot_app.agents.self_heal import SelfHealAgentConfig, _build_system_prompt

        cfg = getattr(getattr(config, "agent", None), "self_heal", None) or SelfHealAgentConfig()
        return [("系统提示词", "system", _build_system_prompt(cfg, prompt_store=prompt_store))]

    def _delegation_parts() -> list:
        instructions = ""
        description = ""
        if skill_manager is not None:
            for key in ("agents", "agent_delegation"):
                skill = skill_manager.get(key)
                if skill is None:
                    continue
                value = getattr(skill, "instructions", "") or ""
                if isinstance(value, str) and value.strip():
                    instructions = value
                description = str(getattr(skill, "description", "") or "")
                if instructions:
                    break
        parts = []
        if instructions:
            parts.append(("工具使用指令", "instructions", instructions))
        if description:
            parts.append(("技能描述（注入给模型的工具说明）", "instructions", description))
        if not parts:
            parts.append(("工具使用指令", "instructions", ""))
        return parts

    prompt_analyzer.catalog.register(
        PromptPartsProvider(
            "子 Agent 委派（agents__*）",
            _delegation_parts,
            agent_kind="instructions",
            agent_note="委派工具的使用指令；可用子 Agent 列表由 agents__list 在运行时给出",
        )
    )

    # 解题/自修复 Agent 的工具定义：优先取运行时 agent 实例上真正会发出去的清单，
    # 取不到再回退模块级构造器（避免分析页只显示提示词、漏掉工具这一大块）。
    def _problem_solver_parts() -> list:
        from neobot_app.agents.problem_solver import (
            ProblemSolverAgentConfig,
            _build_system_prompt,
            build_problem_solver_toolset,
        )

        schema_cfg = getattr(getattr(config, "agent", None), "problem_solver", None)
        parts = [
            ("系统提示词", "system", _build_system_prompt(schema_cfg, prompt_store=prompt_store))
        ]
        definitions: list = []
        agent = getattr(problem_solver_manager, "_agent", None)
        if agent is not None:
            definitions = list(getattr(agent, "tool_definitions", []) or [])
        if not definitions:
            try:
                definitions = list(
                    build_problem_solver_toolset(
                        config=ProblemSolverAgentConfig.from_schema(schema_cfg),
                        logger=logger_factory.get_logger("app.problem_solver"),
                        sandbox_service=sandbox["sandbox_service"],
                        vision_provider=vision_provider,
                    ).definitions()
                )
            except Exception:
                definitions = []
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

    def _self_heal_parts() -> list:
        from neobot_app.agents.self_heal import SelfHealAgentConfig, _build_system_prompt

        schema_cfg = getattr(getattr(config, "agent", None), "self_heal", None)
        # 该构造器需要真实配置对象（读 timeout_seconds）：缺失时用 schema 默认值兜底
        agent_cfg = (
            SelfHealAgentConfig.from_schema(schema_cfg)
            if schema_cfg is not None
            else SelfHealAgentConfig()
        )
        parts = [
            ("系统提示词", "system", _build_system_prompt(agent_cfg, prompt_store=prompt_store))
        ]
        agent = getattr(self_heal_manager, "_agent", None)
        definitions = (
            list(getattr(agent, "tool_definitions", []) or []) if agent is not None else []
        )
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts


    # 已注册的子 Agent（AgentRegistry）：每个 specialist 一条，便于对照 agents__list
    try:
        for item in agent_registry.snapshot():
            sub_name = str(item.get("name") or "")
            sub_description = str(item.get("description") or "")
            if not sub_name:
                continue
            prompt_analyzer.add_source(
                f"子 Agent · {sub_name}",
                (lambda text_value=sub_description: [
                    ("描述（模型看到的 specialist 说明）", "instructions", text_value)
                ]),
                kind="subagent",
                note="由 agents__delegate 调用；提示词在委派时按任务拼装",
            )
    except Exception:
        pass

    # 编号 Agent（agent_model_N）：只做模型路由，提示词复用委派指令 + 任务文本
    def _numbered_agent_parts() -> list:
        import dataclasses

        routing = getattr(config, "agent_model", None)
        if routing is None or not dataclasses.is_dataclass(routing):
            return []
        lines: list = []
        for field_info in dataclasses.fields(routing):
            value = getattr(routing, field_info.name, None)
            if value in (None, "", 0):
                continue
            description = str((field_info.metadata or {}).get("description") or "")
            suffix = f"  # {description}" if description else ""
            lines.append(f"{field_info.name} = {value}{suffix}")
        if not lines:
            return []
        return [("模型路由", "instructions", chr(10).join(lines))]

    prompt_analyzer.catalog.register(
        PromptPartsProvider(
            "编号 Agent（agent_model_1-3）",
            _numbered_agent_parts,
            agent_kind="routing",
            agent_note="编号只决定用哪个模型；提示词 = 委派指令 + 具体任务文本",
        )
    )

    state.prompt_analyzer = prompt_analyzer
