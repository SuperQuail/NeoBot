"""Reply-related tools exposed to the main reply agent."""

from __future__ import annotations

import json
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolAccessPolicy, ToolAccessRule, ToolDefinition, ToolGuardContext
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.reply.postprocess import ReplyPostProcessResult, process_reply_text
from neobot_app.time_context import monotonic_seconds


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
        wait_handler: Any = None,
        react_emoji_handler: Any = None,
        search_emoji_handler: Any = None,
        cancel_handler: Any = None,
        tts_service: Any = None,
        speak_handler: Any = None,
        poke_user_handler: Any = None,
        drawing_manager: Any = None,
        scheduled_task_manager: Any = None,
        problem_solver_manager: Any = None,
        notification_hub: Any = None,
        markdown_image_converter: Any = None,
        send_long_reply_handler: Any = None,
        skill_manager: Any = None,
        chat_context: str | None = None,
        conv_kind: str = "",
        conv_id: str = "",
        wait_cooldown_seconds: int = 60,
        ai_reply_check: bool = False,
        ai_reply_check_lightweight: bool = True,
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
        self._wait = wait_handler
        self._react_emoji = react_emoji_handler
        self._search_emoji = search_emoji_handler
        self._cancel = cancel_handler
        self._tts_service = tts_service
        self._speak_handler = speak_handler
        self._poke_user = poke_user_handler
        self._drawing_manager = drawing_manager
        self._scheduled_task_manager = scheduled_task_manager
        self._problem_solver_manager = problem_solver_manager
        self._notification_hub = notification_hub
        self._markdown_image_converter = markdown_image_converter
        self._send_long_reply = send_long_reply_handler
        self._skill_manager = skill_manager
        self._chat_context = chat_context
        self._conv_kind = conv_kind
        self._conv_id = conv_id
        self._ai_reply_check = ai_reply_check
        self._ai_reply_check_lightweight = ai_reply_check_lightweight
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
                "向当前会话发送回复，可附带表情包图片。发送图片时先逐一发送图片再发送切分后的文字；"
                "若设置 merge_text_with_image=true 则文字与第一张图片合并且不切分。"
                "调用后本轮回复视为完成。",
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
                        "images": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要发送的表情包编号列表。发送时先逐一发送图片（每条消息一张图片），再发送切分后的文字。若同时设置 merge_text_with_image=true，文字会与第一张图片合并为一条消息且文字不再切分。",
                        },
                        "merge_text_with_image": {
                            "type": "boolean",
                            "description": "可选，是否将文字与第一张图片合并发送，此时文字不切分。默认为 false。仅在提供了 images 参数时生效。",
                        },
                        "ai_check_approved": {
                            "type": "boolean",
                            "description": "AI回复检查开启时，确认切分结果没有严重问题或歧义后设为 true。",
                        },
                        "send_original": {
                            "type": "boolean",
                            "description": "AI回复检查开启且切分结果有问题但仍要发送时设为 true；会发送原文，不再切分。对于 @ 和引用消息也适用，设置为 true 后不会切分文字。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        if self._markdown_image_converter is not None:
            tools.append(
                _tool_def(
                    "send_long_reply",
                    "发送 Markdown 格式的长回复。这是唯一允许使用 Markdown 格式的发送方式。"
                    "提供 markdown 内容时，系统自动将其转为图片发送。"
                    "如果已有预渲染的图片文件，可提供 image_path 直接发送，"
                    "此时 markdown 仅用于日志记录（仍建议提供以便追溯）。"
                    "适用于包含代码块、表格、数学公式等复杂格式的长文本回复。"
                    "也用于发送解题结果、跨聊天通信结果等需要格式化的内容。"
                    "注意：普通聊天回复请使用 send_reply 发送纯文本（不使用 Markdown）。"
                    "调用后本轮回复视为完成。",
                    {
                        "properties": {
                            "markdown": {
                                "type": "string",
                                "description": "Markdown 格式的回复内容（image_path 为空时必填）。支持标题、列表、代码块、表格等标准 Markdown 语法。",
                            },
                            "image_path": {
                                "type": "string",
                                "description": "可选，预渲染的图片文件路径。提供后直接发送该图片，不再重新渲染。解题任务完成通知中会包含此路径。",
                            },
                            "reply_to": {
                                "type": "integer",
                                "description": "可选，要引用回复的消息编号。",
                            },
                            "mention": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效。",
                            },
                            "caption": {
                                "type": "string",
                                "description": "可选，随图片一起发送的简短说明文字。",
                            },
                        },
                        "required": [],
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
                                        "set_conversation",
                                        "remove_conversation",
                                        "add_blacklist",
                                        "remove_blacklist",
                                    ],
                                    "description": "调整动作。仅允许作用于当前会话。",
                                },
                                "conv_id": {
                                    "type": "string",
                                    "description": "可选，会话 ID；不填时使用当前会话。若提供，必须等于当前会话 ID。",
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
                    "向当前会话发送一个表情包图片（可附带可选文字）。"
                    "仅用于只发送表情包而不发送独立文字回复的场景。"
                    "若需要同时发送文字回复和表情包，请使用 send_reply 工具并通过 images 参数指定表情包编号。"
                    "提示词中的表情包按使用次数从少到多排列（使用次数均衡器），优先展示不常用的。",
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
                                "description": "搜索关键词，如「猪」、「赞」、「笑哭」等。",
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
        if self._poke_user is not None:
            tools.append(
                _tool_def(
                    "poke_user",
                    "戳一戳指定的QQ用户。在群聊中自动使用群戳一戳，在私聊中自动使用好友戳一戳。"
                    "只需提供目标QQ号，Bot会自动判断会话类型。",
                    {
                        "properties": {
                            "user_id": {
                                "type": "integer",
                                "description": "要戳一戳的目标QQ号。",
                            },
                        },
                        "required": ["user_id"],
                    },
                ),
            )
        if (
            self._drawing_manager is not None
            or self._scheduled_task_manager is not None
            or self._notification_hub is not None
        ):
            tools.append(
                _tool_def(
                    "check_background_tasks",
                    "查询当前聊天流的后台任务状态（可扩展，当前支持绘图任务）。"
                    "返回：后台任务列表及各任务的状态、进行中/冷却/最近完成/失败等信息。"
                    "在决定是否调用 generate_image 之前，必须优先调用此工具检查是否有正在进行的后台任务，避免重复提交。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        if self._drawing_manager is not None:
            tools.append(
                _tool_def(
                    "check_last_drawing",
                    "查看当前聊天流上一次绘图任务的详细记录。"
                    "包括：任务ID、状态（完成/失败/超时）、图片ID、提示词、错误信息等。"
                    "用于确认上一次绘图是否成功、查看生成的图片ID或失败原因。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        if self._scheduled_task_manager is not None:
            tools.append(
                _tool_def(
                    "mark_scheduled_task_complete",
                    "标记指定 UUID 的定时任务已完成。定时任务提醒会提供任务 UUID；"
                    "当你已经完成该提醒对应的事项，或用户明确表示该事项已完成时调用。"
                    "如果提醒内容注明任务配置为一次性通知且系统已自动完成当前触发窗口，发送提醒后不要再调用本工具。"
                    "对于持续通知的提醒任务和生日祝福任务，只要已经发送提醒或祝福消息，就应调用本工具标记完成；"
                    "对于持续提醒类任务，如果已经提醒三到五次仍然没有用户反馈，发送最后一次自然提醒后也应调用本工具结束本次任务。",
                    {
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "定时任务提醒中提供的 UUID。",
                            },
                        },
                        "required": ["task_id"],
                    },
                )
            )
        # 合并 Skill 系统的工具定义
        if self._skill_manager is not None:
            tools.extend(self._skill_manager.get_tools())
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
        if name == "poke_user":
            return await self._execute_poke_user(args)
        if name == "check_background_tasks":
            return await self._execute_check_background_tasks(args)
        if name == "check_last_drawing":
            return await self._execute_check_last_drawing(args)
        if name == "mark_scheduled_task_complete":
            return await self._execute_mark_scheduled_task_complete(args)
        if name == "send_long_reply":
            return await self._execute_send_long_reply(args)
        # Skill 系统路由（优先于 ToolError）
        if self._skill_manager is not None and "__" in name:
            # 自动注入当前对话上下文，skill 工具不需要也不应自行指定
            enriched = dict(args)
            if self._conv_kind and self._conv_id:
                enriched["pipeline_key"] = f"{self._conv_kind}_{self._conv_id}"
            return await self._skill_manager.execute(name, enriched)
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
        merge_text_with_image = bool(args.get("merge_text_with_image") is True)
        raw_images = args.get("images")
        images: list[int] | None = None
        if raw_images is not None:
            if not isinstance(raw_images, list):
                return f"错误：images 必须为列表，收到 {type(raw_images).__name__}"
            try:
                images = [int(n) for n in raw_images]
            except (ValueError, TypeError):
                return f"错误：images 必须为整数列表，收到 {raw_images}"
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

        if (
            self._ai_reply_check_lightweight
            and not self._ai_reply_check
            and not (send_original or ai_check_approved or segments)
        ):
            result = self._preview_split(text)
            if result.fallback_used:
                return self._build_ai_check_prompt(result)

        if self._enable_ai_reply_regenerate and not (send_original or merge_text_with_image) and not segments:
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    f"（字符上限 {self._long_reply_max_length}，"
                    f"分句上限 {self._long_reply_max_sentence_count}）。"
                    f"请精简为更短的版本后重新调用 send_reply。"
                )

        if self._enable_ai_reply_regenerate and not (send_original or merge_text_with_image) and ai_check_approved:
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    f"（字符上限 {self._long_reply_max_length}，"
                    f"分句上限 {self._long_reply_max_sentence_count}）。"
                    f"当前切分结果为默认回复，并非你的原意，请精简为更短的版本后重新调用 send_reply。"
                )

        await self._send_reply(
            text=text,
            reply_to=reply_to,
            mention=mention,
            segments=segments,
            send_original=send_original,
            images=images,
            merge_text_with_image=merge_text_with_image,
        )
        if segments:
            seg_text = "\n---\n".join(segments)
            return f"已发送 {len(segments)} 条消息：\n{seg_text}"
        if send_original:
            display = text.strip()
            return f"已发送原文：{display[:300]}{'...' if len(display) > 300 else ''}"
        preview = self._preview_split(text)
        preview_text = "\n---\n".join(preview.messages)
        if images:
            return f"已发送（{len(images)} 张图片 + {len(preview.messages)} 条文字）：\n{preview_text}"
        return f"已发送 {len(preview.messages)} 条消息：\n{preview_text}"

    async def _execute_wait(self, args: dict) -> str:
        if self._wait is None:
            return "错误：wait 处理器未配置"
        now = monotonic_seconds()
        elapsed = now - self._last_wait_time
        if self._last_wait_time > 0 and elapsed < self._wait_cooldown_seconds:
            remaining = int(self._wait_cooldown_seconds - elapsed)
            return (
                f"wait 处于冷却中，还需等待 {remaining} 秒后才可再次调用。"
                "【提示】如果是在等待后台任务完成，请结束本轮回复，系统会在完成后通知你。"
            )
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
            return "错误：主回复工具不允许修改全局回复意愿；请仅调整当前会话"
        current_conv_id = str(self._conv_id or "").strip()
        requested_conv_id = str(args.get("conv_id") or current_conv_id).strip()
        if action in {
            "set_conversation",
            "remove_conversation",
            "add_blacklist",
            "remove_blacklist",
        }:
            if not current_conv_id:
                return "错误：无法确定当前会话 ID"
            if requested_conv_id != current_conv_id:
                return "错误：只能调整当前会话的回复意愿"
        if action == "set_conversation":
            value = args.get("value")
            if value is None:
                return "错误：set_conversation 需要提供 value 参数"
            return self._willing.set_runtime_conversation_coefficient(current_conv_id, float(value))
        if action == "remove_conversation":
            return self._willing.remove_runtime_conversation_coefficient(current_conv_id)
        if action == "add_blacklist":
            return self._willing.add_runtime_blacklist(current_conv_id)
        if action == "remove_blacklist":
            return self._willing.remove_runtime_blacklist(current_conv_id)
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
        emoji_entry = None
        if self._emoji is not None:
            emoji_entry = self._emoji.get_entry(number)
            if emoji_entry is None:
                total = self._emoji.emoji_count
                return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"
        text = str(args.get("text") or "")
        await handler(number=number, text=text)
        entry_name = emoji_entry.file_name if emoji_entry else f"#{number}"
        return f"已发送表情包 {entry_name}"

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

    async def _execute_poke_user(self, args: dict) -> str:
        if self._poke_user is None:
            return "错误：poke_user 处理器未配置"
        try:
            user_id = int(args.get("user_id", -1))
        except (ValueError, TypeError):
            return "错误：user_id 必须为整数"
        if user_id <= 0:
            return f"错误：user_id 无效，收到 {args.get('user_id')}"
        return await self._poke_user(user_id=user_id)

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

    async def _execute_check_background_tasks(self, args: dict) -> str:
        """查询当前聊天流的后台任务状态（可扩展，当前返回绘图任务）。"""
        if (
            self._drawing_manager is None
            and self._scheduled_task_manager is None
            and self._problem_solver_manager is None
            and self._notification_hub is None
        ):
            return json.dumps({"ok": False, "error": "后台任务未配置"}, ensure_ascii=False)
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps({"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False)
        status: dict[str, Any] = {}
        if self._drawing_manager is not None:
            status.update(self._drawing_manager.get_pipeline_status(pipeline_key))
        if self._scheduled_task_manager is not None:
            status.update(self._scheduled_task_manager.get_pipeline_status(pipeline_key))
        if self._problem_solver_manager is not None:
            status.update(self._problem_solver_manager.get_pipeline_status(pipeline_key))
        if self._notification_hub is not None:
            status.update(self._notification_hub.get_pipeline_status(pipeline_key))
        self._logger.info(
            "主Agent查询后台任务状态",
            pipeline_key=pipeline_key,
            has_active=status.get("has_active_task"),
            cooldown=status.get("cooldown_remaining_seconds"),
        )
        return json.dumps({"ok": True, "pipeline_key": pipeline_key, **status}, ensure_ascii=False)

    async def _execute_mark_scheduled_task_complete(self, args: dict) -> str:
        if self._scheduled_task_manager is None:
            return json.dumps({"ok": False, "error": "定时任务系统未配置"}, ensure_ascii=False)
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return json.dumps({"ok": False, "error": "task_id 不能为空"}, ensure_ascii=False)
        result = await self._scheduled_task_manager.mark_completed(task_id)
        self._logger.info(
            "主Agent标记定时任务完成",
            task_id=task_id,
            ok=result.get("ok"),
        )
        return json.dumps(result, ensure_ascii=False)

    async def _execute_send_long_reply(self, args: dict) -> str:
        if self._markdown_image_converter is None:
            return json.dumps({"ok": False, "error": "Markdown 转图片功能未配置"}, ensure_ascii=False)

        markdown = str(args.get("markdown") or "").strip()
        pre_rendered = str(args.get("image_path") or "").strip()

        if not markdown and not pre_rendered:
            return json.dumps(
                {"ok": False, "error": "markdown 和 image_path 至少需要提供一个"},
                ensure_ascii=False,
            )

        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return json.dumps({"ok": False, "error": f"reply_to 必须为整数，收到 {reply_to}"}, ensure_ascii=False)
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return json.dumps({"ok": False, "error": "mention 必须为整数列表"}, ensure_ascii=False)
        caption = str(args.get("caption") or "").strip()

        if pre_rendered:
            image_path = pre_rendered
        else:
            try:
                image_path = str(await self._markdown_image_converter.convert(markdown))
            except Exception as exc:
                self._logger.error(f"Markdown 转图片失败: {exc}")
                return json.dumps({"ok": False, "error": f"Markdown 转图片失败：{exc}"}, ensure_ascii=False)

        # 调用 orchestrator 提供的 handler 实际发送图片
        if self._send_long_reply is not None:
            await self._send_long_reply(
                image_path=image_path,
                caption=caption,
                reply_to=reply_to,
                mention=mention,
                markdown=markdown,
            )
        return json.dumps({
            "ok": True,
            "status": "sent",
            "image_path": image_path,
            "caption": caption or None,
            "message": f"已发送Markdown图片{'(预渲染)' if pre_rendered else ''}，路径：{image_path}",
        }, ensure_ascii=False)

    async def _execute_check_last_drawing(self, args: dict) -> str:
        """查询当前聊天流上一次绘图任务的详细记录。"""
        if self._drawing_manager is None:
            return json.dumps({"ok": False, "error": "后台任务未配置"}, ensure_ascii=False)
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps({"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False)
        info = self._drawing_manager.get_last_draw_info(pipeline_key)
        if info.get("found"):
            self._logger.info(
                "主Agent查询上一次绘图记录",
                pipeline_key=pipeline_key,
                task_id=info.get("task_id"),
                status=info.get("status"),
            )
        return json.dumps({"ok": True, "pipeline_key": pipeline_key, **info}, ensure_ascii=False)

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

    def _build_ai_check_prompt(self, result: ReplyPostProcessResult) -> str:
        lines = [
            "AI回复检查已开启，暂未发送。",
            "请检查切分后的分条回复是否存在严重问题或明显歧义。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(f"注意：因 {result.reason or '未知原因'}，已触发默认回复替换，当前切分结果为默认回复文本。")
            if self._enable_ai_reply_regenerate:
                lines.append(
                    "默认回复不是你的原意，请重新生成一个更简短的版本（不超过"
                    f"{self._long_reply_max_length}字符、不超过"
                    f"{self._long_reply_max_sentence_count}条），"
                    "然后直接调用 send_reply 发送新文本，无需设置 ai_check_approved。"
                )
            else:
                lines.append(
                    "如确认使用当前默认回复，请再次调用 send_reply，传入原 text、"
                    "segments 为上述切分结果、ai_check_approved=true。"
                    "如不应发送任何回复，请调用 cancel。"
                )
        else:
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
    wait_handler: Any = None,
    react_emoji_handler: Any = None,
    search_emoji_handler: Any = None,
    cancel_handler: Any = None,
    tts_service: Any = None,
    speak_handler: Any = None,
    poke_user_handler: Any = None,
    drawing_manager: Any = None,
    scheduled_task_manager: Any = None,
    problem_solver_manager: Any = None,
    notification_hub: Any = None,
    markdown_image_converter: Any = None,
    send_long_reply_handler: Any = None,
    skill_manager: Any = None,
    chat_context: str | None = None,
    conv_kind: str = "",
    conv_id: str = "",
    wait_cooldown_seconds: int = 60,
    ai_reply_check: bool = False,
    ai_reply_check_lightweight: bool = True,
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
        wait_handler=wait_handler,
        react_emoji_handler=react_emoji_handler,
        search_emoji_handler=search_emoji_handler,
        cancel_handler=cancel_handler,
        tts_service=tts_service,
        speak_handler=speak_handler,
        poke_user_handler=poke_user_handler,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        send_long_reply_handler=send_long_reply_handler,
        skill_manager=skill_manager,
        chat_context=chat_context,
        conv_kind=conv_kind,
        conv_id=conv_id,
        wait_cooldown_seconds=wait_cooldown_seconds,
        ai_reply_check=ai_reply_check,
        ai_reply_check_lightweight=ai_reply_check_lightweight,
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
