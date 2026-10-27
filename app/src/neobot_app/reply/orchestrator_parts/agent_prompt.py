"""agent 模式首轮上下文：消息队列快照、提示词与初始消息。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.reply.event import ReplyEvent, ReplyState
from .tool_text import _render_tool_package_index

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue


class AgentPromptMixin:

    async def _prepare_agent_messages(
        self, event: ReplyEvent, queue: MessageQueue, queue_key: str
    ) -> tuple[MessageNumbering, MessageQueue, list[dict], str, set[str] | None, bool]:
        """构建本轮 agent 的提示词与初始消息，返回后续步骤共用的上下文。"""
        from neobot_app.message.numbering import MessageNumbering

        # 带上 bot_account：wait/增量注入等文本渲染路径需要判断「这条是不是我自己发的」，
        # 以免把自己的历史发言渲染成「编号: 发送者: 正文」再次示范脏格式。
        numbering = MessageNumbering(
            bot_account=getattr(getattr(self._config, "bot", None), "account", None),
            queue=queue,
            queue_key=queue_key,
        )

        # 1. 克隆消息队列
        queue_copy = queue.clone(queue_key)

        # 2. 构建角色消息(聊天记录拆分为真实 user/assistant 消息,先于 system
        #    构建以填充消息编号映射)与 system 提示词(不含聊天记录)。
        #    每轮会变的上下文(群友信息/对方档案/印象)由 builder 渲染成 user 块,
        #    追加在 system 之后、聊天记录之前,而不是塞进 system。
        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        role_messages = await self._build_role_messages(
            event,
            queue_copy,
            queue_key,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        context_messages: list[dict[str, str]] = []
        prompt = await self._build_prompt(
            event,
            queue_copy,
            queue_key,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            context_blocks=context_messages,
        )
        self._record_flow_prompt(event, queue_key, prompt)
        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 注入匹配的 Markdown 技能（插件 SKILL.md）：先完成匹配与 allowed-tools 判定，
        # 供后续表情包搜索提示引用（限制激活时 search_custom_emoji 已被过滤）
        matched_skills: list[Any] = []
        if self._markdown_skills is not None:
            matched = self._match_markdown_skills(queue_copy, queue_key)
            if matched:
                matched_skills = list(matched)

        # allowed-tools 白名单：仅当本轮所有命中技能都声明了非空 allowed-tools 时才限制
        # 工具集，限制集为这些声明的并集；任一命中技能未声明（或声明为空）则不限制
        # （传 None，避免未声明技能的工具被其他技能的声明误伤）
        allowed_tools: set[str] | None = None
        if matched_skills:
            declared = [
                set(getattr(skill, "allowed_tools", None) or ())
                for skill in matched_skills
            ]
            if all(declared):
                union: set[str] = set()
                for tools in declared:
                    union.update(tools)
                allowed_tools = union

        # 表情包列表不再注入提示词:它按使用次数排序且带"已用N次",每次发出表情包都会
        # 改变 system 前缀,让整段缓存失效。改为按需工具 list_emojis / search_custom_emoji。

        # 注入 Skill 操作说明(一行摘要;完整说明用 skills__view_instructions 按需查看)
        if self._skill_manager is not None:
            skill_instructions = self._skill_manager.get_instructions()
            hidden_skill = (
                "image_parse" if getattr(self._provider, "native_vision", False) is True
                else "image_context"
            )
            skill_instructions = "\n".join(
                line for line in skill_instructions.splitlines()
                if not line.startswith(f"- {hidden_skill}:")
            )
            if skill_instructions:
                prompt += (
                    "\n\n<Skill 操作说明>\n"
                    f"{skill_instructions}\n"
                    "需要某个技能的具体操作说明、参数细节或注意事项时,"
                    "调用 skills__view_instructions 查看完整内容。"
                    "\n未直接列出调用工具的技能,其工具定义尚未加载以节省每次调用的开销;"
                    "需要使用时先调用 skills__load_tools 加载(一次可加载多个),"
                    "加载后本轮即可直接调用。"
                    "\n</Skill 操作说明>"
                )
            package_index = _render_tool_package_index(self._skill_manager)
            if package_index:
                prompt += (
                    "\n\n<可加载工具包>\n"
                    f"{package_index}\n"
                    "清单已直接给出；需要某个包时直接调用 skills__load_tools 加载，无需先查询。"
                    "\n</可加载工具包>"
                )

        # 注入匹配的 Markdown 技能（插件 SKILL.md）
        if matched_skills:
            prompt += (
                "\n\n<可用技能>\n"
                + self._render_skills(matched_skills)
                + "\n</可用技能>"
            )

        # 限制说明（保持与 <可用技能> 相邻追加）
        if allowed_tools is not None:
            prompt += (
                "\n注意：当前激活技能限制了可用工具，仅允许："
                f"{', '.join(sorted(allowed_tools))}"
                "（以及始终可用的基础回复工具与技能读取工具）。"
            )

        # 原生视觉说明属于稳定内容:放进 system 提示词(跨管线逐字节相同、可缓存),
        # 不再作为对话末尾的 user 消息(那个位置随历史长度变化,永远命中不了缓存)
        native_vision_active = getattr(self._provider, "native_vision", False) is True
        if native_vision_active:
            vision_note = self._native_vision_note()
            if vision_note:
                prompt += f"\n\n{vision_note}"

        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 3. 准备消息列表(system + 上下文块 + 角色消息 + 后台通知)
        event.transition(ReplyState.GENERATING)
        messages: list[dict] = [{"role": "system", "content": prompt}]
        messages.extend(context_messages)
        messages.extend(role_messages)
        if context_messages:
            self._record_debug(
                "chat_context_injected",
                event,
                queue_key=queue_key,
                injected_count=len(context_messages),
            )
        if event.background_content:
            messages.append({"role": "user", "content": event.background_content})
            _bg_kind = event.conversation_ref.kind if event.conversation_ref else ""
            _bg_id = event.conversation_ref.id if event.conversation_ref else ""
            self._logger.info(
                "orchestrator 注入后台通知（新管线初始消息）",
                event_id=event.event_id,
                pipeline_key=f"{_bg_kind}:{_bg_id}",
                notification_preview=event.background_content[:120],
            )
            self._record_debug(
                "background_notification_injected_initial",
                event,
                queue_key=queue_key,
                notification=event.background_content[:200],
            )
        return (
            numbering,
            queue_copy,
            messages,
            prompt,
            allowed_tools,
            native_vision_active,
        )

    async def _agent_prepare_loop_state(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
    ) -> tuple[int, bool, bool, int, int, set[str], set[str], dict[str, str], dict[str, int]] | None:
        """首轮循环前的状态准备；返回 None 表示 pre-reply 钩子已直接发送并结束。"""
        # 5. Agent 循环（外层 while 支持私聊连续会话）
        max_iterations = self._get_agent_max_iterations()
        is_private = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "private"
        )
        is_group = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        )
        group_lifespan = self._get_group_chat_reply_lifespan() if is_group else 0
        # 成本管线续用预算:基础寿命(默认5)耗尽后,若缓存命中后的继续成本
        # 低于重启管线的输入成本,可额外续用(默认20次),总寿命不超过 5+20
        cost_pipeline_extension_budget = (
            self._get_cost_pipeline_threshold()
            if is_group and group_lifespan > 0 and self._cost_pipeline_enabled()
            else 0
        )

        # 记录已渲染的群成员用户ID，用于挂起恢复时补充新成员档案
        rendered_user_ids: set[str] = set()
        if is_group:
            from neobot_app.message.queue import QueueEntryType as _QET

            for entry in queue_copy.entries(queue_key):
                if entry.kind == _QET.MESSAGE and entry.message is not None:
                    uid = getattr(entry.message, "user_id", None)
                    if uid is not None:
                        rendered_user_ids.add(str(uid))

        # pre-reply hooks：可短路跳过 Agent 循环，直接用返回文本发送
        pre_hook_text = await self._apply_pre_reply_hooks(event)
        if pre_hook_text is not None:
            event.generated_text = pre_hook_text
            self._record_debug(
                "reply_generated", event, queue_key=queue_key, reply_text=pre_hook_text
            )
            before_message_id = queue.get_last_message_id(queue_key)
            delivered = await self._send_reply(
                event,
                pre_hook_text,
                self_sent=self._self_sent_sink(queue, queue_copy, queue_key),
            )
            if delivered is not False:
                self._record_reply_delivered(
                    event, queue, queue_key, before_message_id=before_message_id
                )
            return None

        # 工具输出压缩状态:已压缩的 tool_call_id 与调用名映射(压缩只改内容,
        # 不动消息顺序,assistant.tool_calls 与结果消息始终配对)
        compressed_tool_call_ids: set[str] = set()
        tool_name_by_call_id: dict[str, str] = {}
        #: 工具失败指纹 -> 连续失败次数；成功一次即清零。
        tool_failure_streak: dict[str, int] = {}
        return (
            max_iterations,
            is_private,
            is_group,
            group_lifespan,
            cost_pipeline_extension_budget,
            rendered_user_ids,
            compressed_tool_call_ids,
            tool_name_by_call_id,
            tool_failure_streak,
        )
