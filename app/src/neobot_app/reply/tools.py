"""Reply-related tools exposed to the main reply agent."""

from __future__ import annotations

import json
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolAccessPolicy, ToolAccessRule, ToolDefinition, ToolGuardContext
from neobot_chat.tools import AgentRegistry
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.reply.postprocess import ReplyPostProcessResult, process_reply_text


def _default_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _tool_def(name: str, description: str, parameters: dict) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


class ReplyToolExecutor(ToolExecutor):
    """Executor for reply-mode tools."""

    def __init__(
        self,
        *,
        send_reply_handler: Any = None,
        willing_service: Any = None,
        numbering: Any = None,
        send_emoji_handler: Any = None,
        emoji_service: Any = None,
        agent_registry: AgentRegistry | None = None,
        wait_handler: Any = None,
        react_emoji_handler: Any = None,
        search_emoji_handler: Any = None,
        cancel_handler: Any = None,
        tts_service: Any = None,
        speak_handler: Any = None,
        chat_context: str | None = None,
        conv_kind: str = "",
        conv_id: str = "",
        wait_cooldown_seconds: int = 60,
        ai_reply_check: bool = False,
        bot_name: str = "Bot",
        long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
        long_reply_max_length: int = 300,
        long_reply_max_sentence_count: int = 12,
        enable_ai_reply_regenerate: bool = True,
        logger: Logger | None = None,
    ) -> None:
        self._send_reply = send_reply_handler
        self._willing = willing_service
        self._numbering = numbering
        self._send_emoji = send_emoji_handler
        self._emoji = emoji_service
        self._agent_registry = agent_registry
        self._wait = wait_handler
        self._react_emoji = react_emoji_handler
        self._search_emoji = search_emoji_handler
        self._cancel = cancel_handler
        self._tts_service = tts_service
        self._speak_handler = speak_handler
        self._chat_context = chat_context
        self._conv_kind = conv_kind
        self._conv_id = conv_id
        self._ai_reply_check = ai_reply_check
        self._bot_name = bot_name
        self._long_reply_fallback_template = long_reply_fallback_template
        self._long_reply_max_length = long_reply_max_length
        self._long_reply_max_sentence_count = long_reply_max_sentence_count
        self._enable_ai_reply_regenerate = enable_ai_reply_regenerate
        self._wait_cooldown_seconds = wait_cooldown_seconds
        self._last_wait_time = 0.0
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = []
        if self._cancel is not None:
            tools.append(
                _tool_def(
                    "cancel",
                    "主动结束本轮回复事件。当认为自己不适合参与当前话题、不需要回复、"
                    "或已通过其他方式完成互动时调用。调用后本轮回复立即结束，不再发送任何消息。",
                    {
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "可选，取消回复的简要原因。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        tools.append(
            _tool_def(
                "split_reply",
                "只切分回复文本，不发送。用于在发送前查看分条结果；send_reply 实际发送时也会自动切分。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "需要切分的回复内容。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        tools.append(
            _tool_def(
                "send_reply",
                "向当前会话发送回复，可自由组合消息段（@、引用回复、文本）。调用后本轮回复视为完成。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "回复内容，尽量自然简洁。",
                        },
                        "reply_to": {
                            "type": "integer",
                            "description": "可选，要引用回复的消息编号。由 agent 根据上下文自行决定是否需要引用。",
                        },
                        "mention": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效，由 agent 自行决定是否 @ 以及 @ 谁。仅在需要提醒通知某人时使用。",
                        },
                        "segments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，已经确认过的分条回复内容；每个元素会作为一条消息发送。",
                        },
                        "ai_check_approved": {
                            "type": "boolean",
                            "description": "AI回复检查开启时，确认切分结果没有严重问题或歧义后设为 true。",
                        },
                        "send_original": {
                            "type": "boolean",
                            "description": "AI回复检查开启且切分结果有问题但仍要发送时设为 true；会发送原文，不再切分。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        if self._wait is not None:
            tools.append(
                _tool_def(
                    "wait",
                    "等待一段时间让其他人发言。当认为当前话题未结束或聊天还可继续时调用。"
                    "等待期间的新消息会被收集并在返回结果中呈现。默认等待20秒。",
                    {
                        "properties": {
                            "seconds": {
                                "type": "integer",
                                "description": "等待秒数，默认20秒，最大值受配置限制。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        if self._willing is not None:
            tools.extend(
                [
                    _tool_def(
                        "adjust_reply_willingness",
                        "调整运行时回复意愿设置。",
                        {
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "set_global",
                                        "set_conversation",
                                        "remove_conversation",
                                        "add_blacklist",
                                        "remove_blacklist",
                                    ],
                                    "description": "调整动作。",
                                },
                                "conv_id": {
                                    "type": "string",
                                    "description": "会话级操作对应的会话 ID。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "数值系数。",
                                },
                            },
                            "required": ["action"],
                        },
                    ),
                    _tool_def(
                        "get_willingness_config",
                        "查看当前运行时回复意愿设置。",
                        {"properties": {}, "required": []},
                    ),
                ]
            )
        if self._send_emoji is not None or self._emoji is not None:
            tools.append(
                _tool_def(
                    "send_emoji",
                    "向当前会话发送一个表情包图片。提示词中的表情包按使用次数从少到多排列（使用次数均衡器），"
                    "优先展示不常用的。当表情包数量过多时提示词中只显示配置值指定的数量，可使用 search_custom_emoji 搜索。",
                    {
                        "properties": {
                            "number": {
                                "type": "integer",
                                "description": "提示词列表中的表情包编号。",
                            },
                            "text": {
                                "type": "string",
                                "description": "可选，随表情包一起发送的文字。",
                            },
                        },
                        "required": ["number"],
                    },
                )
            )
            tools.append(
                _tool_def(
                    "search_custom_emoji",
                    "按关键词搜索自定义表情包（非QQ表情）。在表情包描述和文件名中匹配关键词，"
                    "结果按使用次数从少到多排列。当图库/表情包数量过多（如200以上）时建议使用搜索，"
                    "正常情况下直接看提示词中的列表即可。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词，如\"狗\"、\"贴纸\"、\"猫\"等。",
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
        if self._react_emoji is not None:
            tools.append(
                _tool_def(
                    "react_emoji",
                    "对指定消息做出QQ表情回应（emoji like）。调用前如果不确定表情ID，"
                    "可先用 search_qq_emoji 工具搜索表情关键词获取表情ID。",
                    {
                        "properties": {
                            "message_number": {
                                "type": "integer",
                                "description": "要回应的消息编号。",
                            },
                            "emoji_id": {
                                "type": "integer",
                                "description": "QQ表情的数字ID。常用表情如：76(赞)、66(爱心)、46(猪头)、182(笑哭)、128(猪)。",
                            },
                        },
                        "required": ["message_number", "emoji_id"],
                    },
                ),
            )
        if self._search_emoji is not None:
            tools.append(
                _tool_def(
                    "search_qq_emoji",
                    "搜索QQ内置表情。按关键词搜索表情名称，返回匹配的表情ID和名称列表。"
                    "找到合适的表情后，可使用 react_emoji 工具发送表情回应。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词，如“猪”、“赞”、“笑哭”等。",
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
        if self._tts_service is not None and getattr(self._tts_service, "enabled", False):
            tools.append(
                _tool_def(
                    "speak",
                    "将文本转为语音消息并发送到当前会话。适合用于需要语音回复、朗读内容等场景。",
                    {
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "需要转为语音的文本内容。",
                            },
                        },
                        "required": ["text"],
                    },
                ),
            )
        if self._agent_registry:
            tools.extend(
                [
                    _tool_def(
                        "list_agents",
                        "列出可用的子代理，或查看某个子代理的简介。",
                        {
                            "properties": {
                                "agent": {
                                    "type": "string",
                                    "enum": self._agent_registry.names,
                                    "description": "可选，子代理名称。",
                                },
                            },
                            "required": [],
                        },
                    ),
                    _tool_def(
                        "delegate",
                        "把任务委托给子代理；当子代理的上次回复有疑问或需要更多信息时，"
                        "在 previous_response 中传入其上次回复，并在 task 中给出答复；"
                        "需要同一个子代理持续处理时传同一个 session_id。"
                        "子代理可按需通过自己的工具读取当前聊天上下文。"
                        "涉及聊天图片导入、保存图片、图库管理、表情包增删时必须委托 creator，"
                        "即使用户只说“这张图/刚才那张图/加到表情包”也直接委托 creator，不要先委托 image_parse。"
                        "image_parse 只用于纯图片内容解析，且必须有明确图片参数。"
                        "涉及长期记忆、档案记忆、用户资料记忆时委托 memory。",
                        {
                            "properties": {
                                "agent": {
                                    "type": "string",
                                    "enum": self._agent_registry.names,
                                    "description": "子代理名称。",
                                },
                                "task": {
                                    "type": "string",
                                    "description": "传给子代理的自然语言任务或结构化任务。",
                                },
                                "previous_response": {
                                    "type": "string",
                                    "description": "可选，子代理上次回复的内容。当子代理提问或索要信息时填写。",
                                },
                                "session_id": {
                                    "type": "string",
                                    "description": "可选，持续会话 ID。继续同一个子代理任务时保持相同值。",
                                },
                                "tasks": {
                                    "type": "array",
                                    "description": "可选，批量委托任务列表。",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "agent": {
                                                "type": "string",
                                                "enum": self._agent_registry.names,
                                            },
                                            "task": {"type": "string"},
                                            "previous_response": {
                                                "type": "string",
                                                "description": "可选，该子代理的上次回复。",
                                            },
                                            "session_id": {
                                                "type": "string",
                                                "description": "可选，持续会话 ID。",
                                            },
                                        },
                                        "required": ["agent", "task"],
                                    },
                                },
                            },
                            "required": [],
                        },
                    ),
                ]
            )
        return tools

    async def execute(self, name: str, args: dict) -> str:
        if name == "cancel":
            return await self._execute_cancel(args)
        if name == "split_reply":
            return self._execute_split_reply(args)
        if name == "send_reply":
            return await self._execute_send_reply(args)
        if name == "wait":
            return await self._execute_wait(args)
        if name == "adjust_reply_willingness":
            return self._execute_adjust_willingness(args)
        if name == "get_willingness_config":
            return self._execute_get_willingness_config()
        if name == "send_emoji":
            return await self._execute_send_emoji(args)
        if name == "search_custom_emoji":
            return self._execute_search_custom_emoji(args)
        if name == "react_emoji":
            return await self._execute_react_emoji(args)
        if name == "search_qq_emoji":
            return self._execute_search_qq_emoji(args)
        if name == "speak":
            return await self._execute_speak(args)
        if name == "list_agents":
            return self._execute_list_agents(args)
        if name == "delegate":
            return await self._execute_delegate(args)
        raise ToolError(f"Unknown reply tool: {name}")

    async def _execute_cancel(self, args: dict) -> str:
        if self._cancel is None:
            return "错误：cancel 处理器未配置"
        reason = str(args.get("reason") or "").strip()
        await self._cancel(reason=reason if reason else None)
        return "回复已取消" if not reason else f"回复已取消：{reason}"

    def _execute_split_reply(self, args: dict) -> str:
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        result = self._preview_split(text)
        payload = {
            "ok": True,
            "original_text": result.original_text,
            "messages": result.messages,
            "fallback_used": result.fallback_used,
            "reason": result.reason,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _execute_send_reply(self, args: dict) -> str:
        if self._send_reply is None:
            return "错误：send_reply 处理器未配置"
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        segments = self._normalize_segments(args.get("segments"))
        send_original = bool(args.get("send_original") is True)
        ai_check_approved = bool(args.get("ai_check_approved") is True)
        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return f"错误：reply_to 必须为整数，收到 {reply_to}"
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return f"错误：mention 必须为整数列表，收到 {raw_mention}"

        if self._ai_reply_check and not (send_original or ai_check_approved or segments):
            result = self._preview_split(text)
            return self._build_ai_check_prompt(result)

        if self._enable_ai_reply_regenerate and not send_original and not segments:
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    f"（字符上限 {self._long_reply_max_length}，"
                    f"分句上限 {self._long_reply_max_sentence_count}）。"
                    f"请精简为更短的版本后重新调用 send_reply。"
                )

        await self._send_reply(
            text=text,
            reply_to=reply_to,
            mention=mention,
            segments=segments,
            send_original=send_original,
        )
        if segments:
            return f"回复已发送，共 {len(segments)} 条"
        if send_original:
            return "回复原文已发送"
        return "回复已发送"

    async def _execute_wait(self, args: dict) -> str:
        import time
        if self._wait is None:
            return "错误：wait 处理器未配置"
        now = time.monotonic()
        elapsed = now - self._last_wait_time
        if self._last_wait_time > 0 and elapsed < self._wait_cooldown_seconds:
            remaining = int(self._wait_cooldown_seconds - elapsed)
            return f"wait 处于冷却中，还需等待 {remaining} 秒后才可再次调用。"
        seconds = args.get("seconds", 20)
        if seconds is not None:
            try:
                seconds = int(seconds)
            except (ValueError, TypeError):
                return f"错误：seconds 必须为整数，收到 {seconds}"
        else:
            seconds = 20
        self._last_wait_time = now
        return await self._wait(seconds=seconds)

    def _execute_adjust_willingness(self, args: dict) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        action = str(args.get("action") or "")
        if action == "set_global":
            value = args.get("value")
            if value is None:
                return "错误：set_global 需要提供 value 参数"
            return self._willing.set_runtime_global_coefficient(float(value))
        if action == "set_conversation":
            conv_id = str(args.get("conv_id") or "")
            value = args.get("value")
            if not conv_id:
                return "错误：set_conversation 需要提供 conv_id 参数"
            if value is None:
                return "错误：set_conversation 需要提供 value 参数"
            return self._willing.set_runtime_conversation_coefficient(conv_id, float(value))
        if action == "remove_conversation":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：remove_conversation 需要提供 conv_id 参数"
            return self._willing.remove_runtime_conversation_coefficient(conv_id)
        if action == "add_blacklist":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：add_blacklist 需要提供 conv_id 参数"
            return self._willing.add_runtime_blacklist(conv_id)
        if action == "remove_blacklist":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：remove_blacklist 需要提供 conv_id 参数"
            return self._willing.remove_runtime_blacklist(conv_id)
        return f"错误：未知操作 {action}"

    def _execute_get_willingness_config(self) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        return self._willing.get_runtime_config_summary()

    async def _execute_send_emoji(self, args: dict) -> str:
        handler = self._send_emoji
        if handler is None:
            return "错误：send_emoji 处理器未配置"
        try:
            number = int(args.get("number", -1))
        except (ValueError, TypeError):
            return "错误：number 必须为整数"
        if self._emoji is not None:
            entry = self._emoji.get_entry(number)
            if entry is None:
                total = self._emoji.emoji_count
                return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"
        text = str(args.get("text") or "")
        await handler(number=number, text=text)
        return f"表情包 #{number} 已发送"

    def _execute_search_custom_emoji(self, args: dict) -> str:
        if self._emoji is None:
            return "错误：表情包服务未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        results = self._emoji.search_entries(keyword)
        if not results:
            return f"未找到与\"{keyword}\"相关的自定义表情包"
        lines = [f"搜索\"{keyword}\"的结果（按使用次数从少到多排列）："]
        for number, entry in results:
            usage_info = f" [已用{entry.use_count}次]" if entry.use_count > 0 else ""
            lines.append(f"  #{number}: {entry.analysis_text}{usage_info} ({entry.file_name})")
        return "\n".join(lines)

    async def _execute_react_emoji(self, args: dict) -> str:
        if self._react_emoji is None:
            return "错误：react_emoji 处理器未配置"
        try:
            message_number = int(args.get("message_number", -1))
        except (ValueError, TypeError):
            return "错误：message_number 必须为整数"
        try:
            emoji_id = int(args.get("emoji_id", -1))
        except (ValueError, TypeError):
            return "错误：emoji_id 必须为整数"
        if message_number <= 0:
            return f"错误：message_number 无效，收到 {message_number}"
        if emoji_id < 0:
            return f"错误：emoji_id 无效，收到 {emoji_id}"
        return await self._react_emoji(message_number=message_number, emoji_id=emoji_id)

    def _execute_search_qq_emoji(self, args: dict) -> str:
        if self._search_emoji is None:
            return "错误：search_qq_emoji 处理器未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        return self._search_emoji(keyword=keyword)

    async def _execute_speak(self, args: dict) -> str:
        if self._tts_service is None:
            return "错误：TTS 服务未配置"
        if not getattr(self._tts_service, "enabled", False):
            return "错误：TTS 服务当前不可用"
        if self._speak_handler is None:
            return "错误：speak 处理器未配置"
        text = str(args.get("text") or "").strip()
        if not text:
            return "错误：text 不能为空"
        try:
            return await self._speak_handler(text=text)
        except Exception as exc:
            return f"语音生成失败：{exc}"

    def _execute_list_agents(self, args: dict) -> str:
        if self._agent_registry is None:
            return "No agents available"
        agent = args.get("agent")
        if agent is None:
            return self._agent_registry.list_agents()
        return self._agent_registry.list_agents(str(agent))

    async def _execute_delegate(self, args: dict) -> str:
        if self._agent_registry is None:
            return "No agents available"
        agent = args.get("agent")
        task = args.get("task")
        tasks = args.get("tasks")
        previous_response = args.get("previous_response")
        session_id = args.get("session_id")
        normalized_tasks = tasks if isinstance(tasks, list) else None
        target_agent = str(agent) if agent is not None else "unknown"
        task_str = str(task) if task is not None else None
        task_summary = (task_str or str(normalized_tasks))[:200]
        self._logger.info(
            f"委托子Agent: {target_agent}",
            agent=target_agent,
            task=task_summary,
        )
        return await self._agent_registry.delegate(
            agent=target_agent,
            task=task_str,
            tasks=normalized_tasks,
            previous_response=str(previous_response) if previous_response else None,
            session_id=str(session_id) if session_id else None,
            context=self._build_delegate_context(),
        )

    def _build_delegate_context(self) -> str:
        parts: list[str] = []
        if self._conv_kind and self._conv_id:
            parts.append(f"[当前会话]\nkind={self._conv_kind}\nid={self._conv_id}")
        if self._chat_context:
            parts.append("[主Agent当前提示词]\n" + self._chat_context)

        mapping_text = self._build_message_id_context()
        if mapping_text:
            parts.append(mapping_text)
        return "\n\n".join(parts)

    def _build_message_id_context(self) -> str:
        if self._numbering is None:
            return ""
        mapping = getattr(self._numbering, "mapping", None)
        if not isinstance(mapping, dict) or not mapping:
            return ""
        lines = [
            "[聊天消息编号映射]",
            "这些编号来自主Agent当前提示词。导入、解析、撤回、引用聊天消息时，如果工具需要 message_id，必须使用右侧真实 message_id，不要把左侧聊天编号当作 message_id。",
        ]
        for number, message_id in sorted(mapping.items()):
            lines.append(f"消息编号 {number} -> message_id {message_id}")
        return "\n".join(lines)

    def _preview_split(self, text: str) -> ReplyPostProcessResult:
        return process_reply_text(
            text,
            bot_name=self._bot_name,
            fallback_template=self._long_reply_fallback_template,
            max_length=self._long_reply_max_length,
            max_sentence_count=self._long_reply_max_sentence_count,
        )

    @staticmethod
    def _normalize_segments(value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        segments = [str(item).strip() for item in value if str(item).strip()]
        return segments or None

    @staticmethod
    def _build_ai_check_prompt(result: ReplyPostProcessResult) -> str:
        lines = [
            "AI回复检查已开启，暂未发送。",
            "请检查切分后的分条回复是否存在严重问题或明显歧义。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(f"注意：已触发默认回复，原因：{result.reason or '未知'}")
        lines.append(
            "如果没有严重问题或歧义，请再次调用 send_reply，传入原 text、segments 为上述切分结果、ai_check_approved=true。"
        )
        lines.append(
            "如果切分有问题但仍要发送原文，请调用 send_reply 并设置 send_original=true；如果不应发送，请调用 cancel。"
        )
        return "\n".join(lines)

    async def close(self) -> None:
        return None


def build_reply_toolset(
    *,
    send_reply_handler: Any = None,
    willing_service: Any = None,
    numbering: Any = None,
    send_emoji_handler: Any = None,
    emoji_service: Any = None,
    agent_registry: AgentRegistry | None = None,
    wait_handler: Any = None,
    react_emoji_handler: Any = None,
    search_emoji_handler: Any = None,
    cancel_handler: Any = None,
    tts_service: Any = None,
    speak_handler: Any = None,
    chat_context: str | None = None,
    conv_kind: str = "",
    conv_id: str = "",
    wait_cooldown_seconds: int = 60,
    ai_reply_check: bool = False,
    bot_name: str = "Bot",
    long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
    long_reply_max_length: int = 300,
    long_reply_max_sentence_count: int = 12,
    enable_ai_reply_regenerate: bool = True,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = ReplyToolExecutor(
        send_reply_handler=send_reply_handler,
        willing_service=willing_service,
        numbering=numbering,
        send_emoji_handler=send_emoji_handler,
        emoji_service=emoji_service,
        agent_registry=agent_registry,
        wait_handler=wait_handler,
        react_emoji_handler=react_emoji_handler,
        search_emoji_handler=search_emoji_handler,
        cancel_handler=cancel_handler,
        tts_service=tts_service,
        speak_handler=speak_handler,
        chat_context=chat_context,
        conv_kind=conv_kind,
        conv_id=conv_id,
        wait_cooldown_seconds=wait_cooldown_seconds,
        ai_reply_check=ai_reply_check,
        bot_name=bot_name,
        long_reply_fallback_template=long_reply_fallback_template,
        long_reply_max_length=long_reply_max_length,
        long_reply_max_sentence_count=long_reply_max_sentence_count,
        enable_ai_reply_regenerate=enable_ai_reply_regenerate,
        logger=logger,
    )
    definitions = executor.definitions()
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in definitions
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())
