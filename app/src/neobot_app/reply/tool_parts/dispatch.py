"""工具授权、执行分发与技能调用（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _SKILL_GUARD_BASE_TOOLS, _SKILL_INTERNAL_KEYS


class _DispatchMixin:
    def _shared_agent_tools(self) -> Any:
        from neobot_app.skills.agent_tools_skill import AgentToolsSkill
        lookup = getattr(self._skill_manager, "get", None)
        shared = lookup("agent_tools") if callable(lookup) else None
        return shared if isinstance(shared, AgentToolsSkill) else None

    def agent_tool_capabilities(self) -> frozenset[str]:
        """Authorize program bindings independently of their wire presentation."""
        shared = self._shared_agent_tools()
        if shared is None:
            return frozenset()
        names = set(shared.runtime.capability_names())
        if shared.runtime.config.ptc_enabled:
            names.add("run_code")
        return frozenset(name for name in names if self._policy_authorized(f"agent_tools__{name}"))

    def is_tool_authorized(self, name: str) -> bool:
        """主 Agent 的授权判定:能力存在 + 去重,与任务工具模式(native/PTC)无关。

        任务工具模式只决定「任务型 Agent(解题/子 Agent)如何编排」;
        主回复管线始终直接调用业务工具,不因切到 PTC 而把工具换成单个 run_code。
        """
        if not self._policy_authorized(name):
            return False
        shared = self._shared_agent_tools()
        if shared is not None:
            from neobot_app.agent_tools.modes import LEGACY_FILE_ALIASES
            if name.startswith("agent_tools__"):
                return name.removeprefix("agent_tools__") in shared.runtime.capability_names()
            if name in LEGACY_FILE_ALIASES and LEGACY_FILE_ALIASES[name] in shared.runtime.capability_names():
                return False
        return True

    def _policy_authorized(self, name: str) -> bool:
        """Apply the skill allowlist and live model capability policy, not mode filtering."""
        native_vision = getattr(self._native_vision_provider, "native_vision", False) is True
        if name.startswith("image_context__") and not native_vision:
            return False
        if native_vision and name in {
            "image_parse__parse_image",
            "drawing__inspect_image",
            "user_profile__analyze_user_avatar",
        }:
            return False
        return not self._allowed_tools or name in (
            _SKILL_GUARD_BASE_TOOLS | self._allowed_tools
        )

    def authorization_error(self, name: str) -> str:
        if self._allowed_tools and name not in (_SKILL_GUARD_BASE_TOOLS | self._allowed_tools):
            return f"Error: 工具 {name} 不在当前技能允许的工具列表内"
        shared = self._shared_agent_tools()
        if shared is not None:
            from neobot_app.agent_tools.modes import LEGACY_FILE_ALIASES
            if name in LEGACY_FILE_ALIASES:
                return f"Error: 工具 {name} 已去重，请使用 agent_tools__{LEGACY_FILE_ALIASES[name]}（PTC时在run_code内调用）"
            if name.startswith("agent_tools__") and name.removeprefix("agent_tools__") not in shared.runtime.capability_names():
                return f"Error: 工具 {name} 不存在或当前部署未启用"
        return f"Error: 工具 {name} 与当前模型视觉能力不匹配，请使用当前提供的图片工具"

    async def execute(self, name: str, args: dict) -> str:
        # allowed-tools 白名单拦截（须在 skills__read_* 等所有路由之前）
        if not self.is_tool_authorized(name):
            return self.authorization_error(name)
        if not name.startswith("agent_tools__") and self._skill_manager is not None:
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            from neobot_app.agent_tools.contracts import ToolContext
            lookup = getattr(self._skill_manager, "get", None)
            shared = lookup("agent_tools") if callable(lookup) else None
            if isinstance(shared, AgentToolsSkill) and self._conv_kind in {"group", "private"} and str(self._conv_id).isdigit():
                flow = f"{self._conv_kind}:{self._conv_id}"
                context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow)
                safe = {"cancel", "send_reply", "split_reply", "wait", "send_long_reply",
                        "credential__request", "credential__check", "skills__read_manifest",
                        "skills__read_resource", "skills__view_instructions", "check_background_tasks",
                        "cancel_task", "agents__list", "image_context__add_image", "image_parse__parse_image",
                        "sandbox_manager__read_file", "sandbox_manager__list_files",
                        "sandbox_manager__glob_files", "sandbox_manager__grep_files"}
                if shared.runtime.state.is_planning(context) and name not in safe:
                    return json.dumps({"ok": False, "code": "PLAN_MODE", "error": "计划待审批，不能通过旧工具绕过执行限制"}, ensure_ascii=False)
        if name == "cancel":
            return await self._execute_cancel(args)
        if name == "split_reply":
            return self._execute_split_reply(args)
        if name == "send_reply":
            return await self._execute_send_reply(args)
        if name == "wait":
            return await self._execute_wait(args)
        if name == "adjust_reply_willingness":
            return await self._execute_adjust_willingness(args)
        if name == "get_willingness_config":
            return self._execute_get_willingness_config()
        if name == "manage_willing_config":
            return await self._execute_manage_willing_config(args)
        if name == "send_emoji":
            return await self._execute_send_emoji(args)
        if name == "list_emojis":
            return self._execute_list_emojis(args)
        if name == "search_custom_emoji":
            return self._execute_search_custom_emoji(args)
        if name == "react_emoji":
            return await self._execute_react_emoji(args)
        if name == "search_qq_emoji":
            return self._execute_search_qq_emoji(args)
        if name == "speak":
            return await self._execute_speak(args)
        if name == "poke_user":
            return await self._execute_poke_user(args)
        if name == "check_background_tasks":
            return await self._execute_check_background_tasks(args)
        if name == "cancel_task":
            return await self._execute_cancel_task(args)
        if name == "check_last_drawing":
            return await self._execute_check_last_drawing(args)
        if name == "mark_scheduled_task_complete":
            return await self._execute_mark_scheduled_task_complete(args)
        if name == "send_long_reply":
            return await self._execute_send_long_reply(args)
        # Markdown 技能读取（优先于 SkillManager 的 __ 路由）
        if name == "skills__read_manifest":
            return self._read_skill_manifest(args)
        if name == "skills__read_resource":
            return self._read_skill_resource(args)
        # 内置技能操作说明查看（按需读取,默认只注入一行摘要）
        if name == "skills__view_instructions":
            return self._view_skill_instructions(args)
        if name == "skills__load_tools":
            return self._load_skill_tools(args)
        # Skill 系统路由（优先于 ToolError）
        if self._skill_manager is not None and "__" in name:
            token = self._skill_tokens.get(name)
            capture = getattr(self._skill_manager, "capture_execution_token", None)
            if token is None and callable(capture):
                # Direct executor users may execute before asking for definitions.
                token = capture(name)
                if token is None:
                    return f"未知工具: {name}"
            # 自动注入当前对话上下文，skill 工具不需要也不应自行指定。
            # 模型伪造的内部键（pipeline_key/_numbering_mapping/_delegate_context）
            # 一律剥离，由会话状态覆盖。
            enriched = {
                key: value
                for key, value in dict(args).items()
                if key not in _SKILL_INTERNAL_KEYS
            }
            if self._conv_kind and self._conv_id:
                enriched["pipeline_key"] = f"{self._conv_kind}:{self._conv_id}"
            if self._current_user_id is not None:
                # 当前会话用户 QQ(凭据申请等需要记录请求者)
                enriched["_requester_id"] = self._current_user_id
            if self._numbering is not None:
                mapping = getattr(self._numbering, "mapping", None)
                if isinstance(mapping, dict):
                    enriched["_numbering_mapping"] = mapping
            if self._chat_context and name.startswith("agents__"):
                # 仅子 Agent 委派需要当前对话上下文，避免污染其他 skill 工具参数
                enriched["_delegate_context"] = self._chat_context
            if self._skill_manager.is_session_tool(name):
                return await self._execute_session_tool(name, enriched, token)
            return await self._execute_skill(name, enriched, token)
        raise ToolError(f"Unknown reply tool: {name}")

    async def _execute_skill(self, name: str, args: dict, token: Any) -> str:
        if not name.startswith(("agent_tools__", "agents__", "background_trigger__", "sandbox_manager__")):
            if token is None:
                return await self._skill_manager.execute(name, args)
            return await self._skill_manager.execute(name, args, token=token)
        from neobot_app.agent_tools.contracts import ToolContext
        from neobot_app.agent_tools.invocation import CURRENT_INVOCATION, ToolInvocation

        if self._conv_kind not in {"group", "private"} or not str(self._conv_id).isdigit():
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            lookup = getattr(self._skill_manager, "get", None)
            shared = lookup("agent_tools") if callable(lookup) else None
            if name.startswith("agent_tools__") or isinstance(shared, AgentToolsSkill):
                return json.dumps({"ok": False, "code": "CONTEXT_REQUIRED", "error": "缺少可信聊天身份"})
            # Preserve host-only legacy callers when the shared runtime is absent.
            if token is None:
                return await self._skill_manager.execute(name, args)
            return await self._skill_manager.execute(name, args, token=token)
        flow = f"{self._conv_kind}:{self._conv_id}"
        definitions = self.definitions()
        allowed = self.agent_tool_capabilities()
        context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow, user_id=self._current_user_id,
                              human_request=self._human_request, allowed_tools=allowed)
        external = [d for d in definitions if not d["function"]["name"].startswith("agent_tools__")]
        image_parts: list[dict] = []
        async def dispatch(external_name: str, external_args: dict) -> Any:
            result = await self.execute(external_name, external_args)
            image_parts.extend(getattr(result, "image_parts", []))
            return result
        invocation = ToolInvocation(context, dispatch, external, self._agent_history)
        marker = CURRENT_INVOCATION.set(invocation)
        try:
            if token is None:
                result = await self._skill_manager.execute(name, args)
            else:
                result = await self._skill_manager.execute(name, args, token=token)
            if image_parts:
                from neobot_app.skills.image_context_skill import ImageContextResult
                return ImageContextResult(str(result), image_parts)
            return result
        finally:
            CURRENT_INVOCATION.reset(marker)

    def _filter_tool_defs(self, tools: list[ToolDefinition]) -> list[ToolDefinition]:
        # allowed-tools 白名单：非空时过滤掉「不在白名单且不在 allowed_tools 中」的工具
        if self._allowed_tools:
            allowed = _SKILL_GUARD_BASE_TOOLS | self._allowed_tools
            tools = [t for t in tools if t["function"]["name"] in allowed]
        tools = [t for t in tools if self.is_tool_authorized(t["function"]["name"])]
        names: set[str] = set()
        for tool in tools:
            name = tool["function"]["name"]
            if name in names:
                raise ValueError(f"重复的最终工具定义: {name}")
            names.add(name)
        return tools
