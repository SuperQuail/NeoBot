"""Chat interaction agent and tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.emoji.service import EmojiService
    from neobot_app.user_profiles import UserProfileService

from neobot_contracts.models import ConversationRef

EXPOSED_TO_MAIN_AGENT_NAME = "chat_interaction"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "聊天互动与社交管理。可执行群管理（设管理员/禁言/踢人/群名片/群名/头衔/加群请求/精华/撤回）、"
    "好友管理（备注/分组/删除/好友请求/为好友QQ空间主页点赞）、读取合并转发消息、发送表情包。"
    "戳一戳请使用主Agent的 poke_user 工具。"
    "需提供目标群号/QQ号；修改好友备注用 manage_friend(set_remark)，修改群名片用 manage_group(set_card)。"
)

_CHAT_INTERACTION_CONTEXT: ContextVar[str] = ContextVar("chat_interaction_context", default="")

# 同级 sub agent 描述，用于识别任务是否应委托给其他 agent
PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片。\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注/聊天记录、解析用户头像、调整好感度。\n"
    "- image_parse: 仅按需求解析图片内容，不保存、不导入、不管理图库/表情包。\n"
    "如果收到的任务明显属于其他 agent 的职责，直接告知主Agent该委托给对应的 agent，不要越权处理。"
)


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


class ChatInteractionToolExecutor(ToolExecutor):
    """Tool executor for chat interaction operations."""

    def __init__(
        self,
        adapter: "OneBotAdapter",
        emoji_service: "EmojiService | None" = None,
        profile_service: "UserProfileService | None" = None,
        logger: Logger | None = None,
        forward_display_threshold: int = 50,
        forward_max_nesting: int = 10,
    ) -> None:
        self._adapter = adapter
        self._emoji_service = emoji_service
        self._profile_service = profile_service
        self._logger = logger or NullLogger()
        self._forward_display_threshold = forward_display_threshold
        self._forward_max_nesting = forward_max_nesting

    def definitions(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = [
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射。仅在任务缺少群号/QQ号、或需要判断上下文中的指代时调用。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "read_forward_msg",
                "读取合并转发消息的具体内容。传入消息 ID（来自 [合并转发:ID=xxx] 中的 ID），返回转发消息中的节点列表。支持嵌套转发（转发中包含转发）的递归展开。",
                {
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "合并转发消息的 ID，来自聊天记录中 [合并转发:ID=xxx] 的 ID 部分。",
                        },
                    },
                    "required": ["message_id"],
                },
            ),
        ]
        if self._emoji_service is not None:
            tools.append(
                _tool_def(
                    "send_sticker",
                    "从表情包库中选择并发送一个表情包图片到指定会话。",
                    {
                        "properties": {
                            "number": {
                                "type": "integer",
                                "description": "表情包编号，从可用表情包列表中选取。",
                            },
                            "text": {
                                "type": "string",
                                "description": "可选，随表情包一起发送的文字。",
                            },
                            "group_id": {
                                "type": "string",
                                "description": "目标群号，群聊场景使用。",
                            },
                            "user_id": {
                                "type": "string",
                                "description": "目标QQ号，私聊场景使用。",
                            },
                        },
                        "required": ["number"],
                    },
                ),
            )
        tools.append(
            _tool_def(
                "manage_group",
                "群管理：管理员、禁言、踢人、群名/群备注/群名片/头衔、加群请求、精华、撤回。",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "set_admin",
                                "set_ban",
                                "set_whole_ban",
                                "kick",
                                "set_card",
                                "set_group_name",
                                "set_group_remark",
                                "set_special_title",
                                "handle_add_request",
                                "set_essence",
                                "delete_essence",
                                "delete_msg",
                            ],
                            "description": "要执行的群管理动作。",
                        },
                        "group_id": {"type": "integer", "description": "群号"},
                        "user_id": {"type": "integer", "description": "目标 QQ 号"},
                        "enable": {"type": "boolean", "description": "是否启用/设为管理员/全员禁言"},
                        "duration": {"type": "integer", "description": "禁言秒数"},
                        "reject_add_request": {"type": "boolean", "description": "踢人后是否拒绝再次加群"},
                        "text": {"type": "string", "description": "群名、备注、名片或头衔"},
                        "flag": {"type": "string", "description": "加群请求 flag"},
                        "approve": {"type": "boolean", "description": "是否同意请求"},
                        "reason": {"type": "string", "description": "拒绝理由"},
                        "message_id": {"type": "integer", "description": "消息 ID，用于撤回/精华"},
                    },
                    "required": ["action"],
                },
            )
        )
        tools.append(
            _tool_def(
                "manage_friend",
                "好友管理：备注、分组、删除、好友请求、点赞用户主页（QQ资料卡）。戳一戳请使用主Agent的 poke_user 工具。",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "set_remark",
                                "set_category",
                                "delete_friend",
                                "handle_add_request",
                                "send_like",
                            ],
                            "description": "要执行的好友管理动作。send_like=点赞用户QQ主页/资料卡",
                        },
                        "user_id": {"type": "integer", "description": "目标 QQ 号"},
                        "remark": {"type": "string", "description": "好友备注"},
                        "category_id": {"type": "integer", "description": "好友分组 ID"},
                        "flag": {"type": "string", "description": "好友请求 flag"},
                        "approve": {"type": "boolean", "description": "是否同意请求"},
                        "times": {
                            "type": "integer",
                            "description": "点赞次数，非VIP每日最多10次，VIP每日最多20次",
                        },
                    },
                    "required": ["action"],
                },
            )
        )
        return tools

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_chat_context":
            return self._get_chat_context()
        if name == "read_forward_msg":
            return await self._read_forward_msg(args)
        if name == "send_sticker":
            return await self._send_sticker(args)
        if name == "manage_group":
            return await self._manage_group(args)
        if name == "manage_friend":
            return await self._manage_friend(args)
        return f"未知工具: {name}"

    async def close(self) -> None:
        return None

    @staticmethod
    def _get_chat_context() -> str:
        context = _CHAT_INTERACTION_CONTEXT.get("").strip()
        if not context:
            return _json({"ok": False, "error": "当前没有可用的聊天上下文"})
        return _json({"ok": True, "context": context})

    async def _read_forward_msg(self, args: dict[str, Any]) -> str:
        message_id = str(args.get("message_id") or "").strip()
        if not message_id:
            return _json({"ok": False, "error": "缺少 message_id 参数"})

        try:
            result = await self._adapter.get_forward_msg(message_id)
        except Exception as exc:
            return _json({"ok": False, "error": f"获取合并转发消息失败: {exc}"})

        if result is None:
            return _json({"ok": False, "error": f"无法获取合并转发消息 {message_id}，可能已过期"})

        data = result.get("data", result) if isinstance(result, dict) else {}
        messages = data.get("messages", []) if isinstance(data, dict) else []
        if not messages:
            return _json({"ok": True, "message_id": message_id, "node_count": 0, "content": "(空转发消息)"})

        node_count = len(messages)
        threshold = self._forward_display_threshold
        rendered = self._render_forward_nodes(messages, depth=1)

        if node_count < threshold:
            return _json({
                "ok": True,
                "message_id": message_id,
                "node_count": node_count,
                "content": rendered,
            })
        else:
            return _json({
                "ok": True,
                "message_id": message_id,
                "node_count": node_count,
                "display_threshold": threshold,
                "truncated": True,
                "content": rendered[:2000],
                "hint": f"消息过多（{node_count}条），仅显示前2000字符。如需完整内容，可先通过条件筛选后重新请求。",
            })

    def _render_forward_nodes(self, messages: list, depth: int) -> str:
        """递归渲染转发消息节点，处理嵌套转发。"""
        lines: list[str] = []
        for i, node in enumerate(messages):
            if not isinstance(node, dict):
                continue
            sender = node.get("sender", {})
            sender_name = ""
            if isinstance(sender, dict):
                sender_name = sender.get("nickname") or sender.get("card") or f"QQ:{sender.get('user_id', '未知')}"
            elif sender:
                sender_name = str(sender)

            node_msg = node.get("message", [])
            node_content = self._render_node_message(node_msg, depth)
            lines.append(f"  [{i + 1}] {sender_name}: {node_content}")

        return "\n".join(lines)

    def _render_node_message(self, segments: list, depth: int) -> str:
        """渲染单条转发节点内的消息段，递归展开嵌套转发。"""
        parts: list[str] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            seg_type = str(seg.get("type") or "")
            seg_data = seg.get("data", {})
            if not isinstance(seg_data, dict):
                seg_data = {}

            if seg_type == "text":
                parts.append(str(seg_data.get("text") or ""))
            elif seg_type == "image":
                parts.append("[图片]")
            elif seg_type == "face":
                parts.append(f"[表情:{seg_data.get('id', '')}]")
            elif seg_type == "at":
                qq = seg_data.get("qq", "")
                parts.append("@全体成员" if qq == "all" else f"@{seg_data.get('name', qq)}")
            elif seg_type == "forward" and depth < self._forward_max_nesting:
                forward_id = seg_data.get("id", "")
                parts.append(f"[嵌套合并转发:ID={forward_id}，使用 read_forward_msg 查看]")
            elif seg_type == "forward":
                parts.append(f"[嵌套合并转发:ID={seg_data.get('id', '')}，已达最大嵌套层级]")
            elif seg_type == "reply":
                parts.append(f"[回复:{seg_data.get('id', '')}]")
            elif seg_type == "record":
                parts.append("[语音]")
            elif seg_type == "video":
                parts.append("[视频]")
            else:
                parts.append(f"[{seg_type}]")
        return "".join(parts)

    async def _send_sticker(self, args: dict[str, Any]) -> str:
        if self._emoji_service is None:
            return "错误：表情包服务未配置"

        try:
            number = int(args.get("number", -1))
        except (ValueError, TypeError):
            return "错误：number 必须为整数"

        entry = self._emoji_service.get_entry(number)
        if entry is None:
            total = self._emoji_service.emoji_count
            return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"

        text = str(args.get("text") or "")

        segments: list[dict] = []
        if text.strip():
            segments.append({"type": "text", "data": {"text": text.strip()}})
        segments.append({
            "type": "image",
            "data": {"file": f"file:///{entry.file_path.as_posix()}"},
        })

        group_id = str(args.get("group_id") or "")
        user_id = str(args.get("user_id") or "")
        if group_id:
            conversation_ref = ConversationRef(kind="group", id=group_id)
        elif user_id:
            conversation_ref = ConversationRef(kind="private", id=user_id)
        else:
            return "错误：未指定 group_id 或 user_id，无法确定发送目标"

        self._logger.info(
            f"发送表情包 #{number}",
            file=entry.file_name,
            target=f"{conversation_ref.kind}:{conversation_ref.id}",
        )
        await self._adapter.send(conversation_ref, segments)
        return f"表情包 #{number} 已发送（{entry.file_name}）"

    async def _manage_group(self, args: dict[str, Any]) -> str:
        action = str(args.get("action") or "").strip()
        try:
            api_action, params = self._group_action_params(action, args)
            result = await self._adapter.call_api(api_action, params)
            if self._api_succeeded(result):
                return _json({"ok": True, "action": action, "api": api_action, "result": result})
            return _json({"ok": False, "action": action, "api": api_action, "result": result})
        except Exception as exc:
            return _json({"ok": False, "action": action, "error": str(exc)})

    async def _manage_friend(self, args: dict[str, Any]) -> str:
        action = str(args.get("action") or "").strip()
        try:
            api_action, params = self._friend_action_params(action, args)
            result = await self._adapter.call_api(api_action, params)
            succeeded = self._api_succeeded(result)
            if action == "set_remark" and succeeded:
                await self._sync_friend_remark(params)
            return _json({"ok": succeeded, "action": action, "api": api_action, "result": result})
        except Exception as exc:
            return _json({"ok": False, "action": action, "error": str(exc)})

    async def _sync_friend_remark(self, params: dict[str, Any]) -> None:
        if self._profile_service is None:
            return
        user_id = params.get("user_id")
        remark = params.get("remark")
        if user_id in (None, ""):
            return
        try:
            await self._profile_service.update_user_remark(user_id, str(remark or ""))
            self._logger.debug("friend remark synced to user profile", user_id=str(user_id))
        except Exception as exc:
            self._logger.warning(
                "同步好友备注到用户资料失败",
                user_id=str(user_id),
                error=str(exc),
            )

    @staticmethod
    def _api_succeeded(result: Any) -> bool:
        if result is None:
            return False
        if not isinstance(result, dict):
            return True
        status = result.get("status")
        if status is None:
            return True
        return status == "ok"

    def _group_action_params(self, action: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        group_id = self._optional_int(args.get("group_id"))
        user_id = self._optional_int(args.get("user_id"))
        message_id = self._optional_int(args.get("message_id"))
        text = self._optional_str(args.get("text"))

        if action == "set_admin":
            return "set_group_admin", {
                "group_id": self._require(group_id, "group_id"),
                "user_id": self._require(user_id, "user_id"),
                "enable": bool(args.get("enable")),
            }
        if action == "set_ban":
            return "set_group_ban", {
                "group_id": self._require(group_id, "group_id"),
                "user_id": self._require(user_id, "user_id"),
                "duration": self._require(self._optional_int(args.get("duration")), "duration"),
            }
        if action == "set_whole_ban":
            return "set_group_whole_ban", {
                "group_id": self._require(group_id, "group_id"),
                "enable": bool(args.get("enable", True)),
            }
        if action == "kick":
            return "set_group_kick", {
                "group_id": self._require(group_id, "group_id"),
                "user_id": self._require(user_id, "user_id"),
                "reject_add_request": bool(args.get("reject_add_request", False)),
            }
        if action == "set_card":
            return "set_group_card", {
                "group_id": self._require(group_id, "group_id"),
                "user_id": self._require(user_id, "user_id"),
                "card": self._require(text, "text"),
            }
        if action == "set_group_name":
            return "set_group_name", {
                "group_id": self._require(group_id, "group_id"),
                "group_name": self._require(text, "text"),
            }
        if action == "set_group_remark":
            return "set_group_remark", {
                "group_id": self._require(group_id, "group_id"),
                "remark": self._require(text, "text"),
            }
        if action == "set_special_title":
            return "set_group_special_title", {
                "group_id": self._require(group_id, "group_id"),
                "user_id": self._require(user_id, "user_id"),
                "special_title": self._require(text, "text"),
            }
        if action == "handle_add_request":
            return "set_group_add_request", {
                "flag": self._require(self._optional_str(args.get("flag")), "flag"),
                "approve": bool(args.get("approve", True)),
                "reason": self._optional_str(args.get("reason")),
            }
        if action == "set_essence":
            return "set_essence_msg", {"message_id": self._require(message_id, "message_id")}
        if action == "delete_essence":
            return "delete_essence_msg", {"message_id": self._require(message_id, "message_id")}
        if action == "delete_msg":
            return "delete_msg", {"message_id": self._require(message_id, "message_id")}
        raise ValueError(f"未知群管理动作: {action}")

    def _friend_action_params(self, action: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        user_id = self._optional_int(args.get("user_id"))
        if action == "set_remark":
            return "set_friend_remark", {
                "user_id": self._require(user_id, "user_id"),
                "remark": self._require(self._optional_str(args.get("remark")), "remark"),
            }
        if action == "set_category":
            return "set_friend_category", {
                "user_id": self._require(user_id, "user_id"),
                "category_id": self._require(self._optional_int(args.get("category_id")), "category_id"),
            }
        if action == "delete_friend":
            return "delete_friend", {"user_id": self._require(user_id, "user_id")}
        if action == "handle_add_request":
            return "set_friend_add_request", {
                "flag": self._require(self._optional_str(args.get("flag")), "flag"),
                "approve": bool(args.get("approve", True)),
                "remark": self._optional_str(args.get("remark")),
            }
        if action == "send_like":
            return "send_like", {
                "user_id": self._require(user_id, "user_id"),
                "times": int(args.get("times") or 1),
            }
        raise ValueError(f"未知好友管理动作: {action}")

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _require(value: Any, name: str) -> Any:
        if value is None or value == "":
            raise ValueError(f"缺少参数 {name}")
        return value


def build_chat_interaction_toolset(
    adapter: "OneBotAdapter",
    emoji_service: "EmojiService | None" = None,
    profile_service: "UserProfileService | None" = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
    forward_display_threshold: int = 50,
    forward_max_nesting: int = 10,
) -> Toolset:
    executor = ChatInteractionToolExecutor(
        adapter=adapter,
        emoji_service=emoji_service,
        profile_service=profile_service,
        logger=logger,
        forward_display_threshold=forward_display_threshold,
        forward_max_nesting=forward_max_nesting,
    )
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


def _build_system_prompt() -> str:
    return (
        "你是聊天互动代理。\n"
        "负责执行聊天互动、群管理、好友管理。\n"
        "群管理动作包括设管理员、禁言、踢人、群名/备注/名片/头衔、请求处理、精华和撤回。\n"
        "好友管理动作包括备注、分组、删除、请求处理、点赞用户主页（QQ资料卡）。\n"
        "如果任务缺少群号/QQ号或需要确认聊天上下文中的指代信息，先调用 get_chat_context 查看主Agent上下文和消息编号映射。\n"
        "禁止使用Markdown。\n"
        "输出尽可能精简，只返回必要结果。\n"
        "send_like（点赞用户主页）注意事项：非VIP用户每日最多点赞10次，VIP用户每日最多20次。需要确保点赞次数不超出限制。\n"
        f"{PEER_AGENT_DESCRIPTIONS}\n"
        "任务完成后，只返回简短纯文本结果。"
    )


class ChatInteractionAgent:
    """LLM-backed agent dedicated to chat interaction operations."""

    def __init__(
        self,
        provider: Provider,
        adapter: "OneBotAdapter",
        emoji_service: "EmojiService | None" = None,
        profile_service: "UserProfileService | None" = None,
        logger: Logger | None = None,
        forward_display_threshold: int = 50,
        forward_max_nesting: int = 10,
    ) -> None:
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_chat_interaction_toolset(
            adapter=adapter,
            emoji_service=emoji_service,
            profile_service=profile_service,
            logger=logger,
            forward_display_threshold=forward_display_threshold,
            forward_max_nesting=forward_max_nesting,
        )
        self.tool_definitions = self._toolset.definitions()
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(),
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        token = _CHAT_INTERACTION_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            return await self._agent.invoke(state)
        finally:
            _CHAT_INTERACTION_CONTEXT.reset(token)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _CHAT_INTERACTION_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _CHAT_INTERACTION_CONTEXT.reset(token)

    async def close(self) -> None:
        await self._agent.close()


def build_chat_interaction_agent(
    provider: Provider,
    adapter: "OneBotAdapter",
    emoji_service: "EmojiService | None" = None,
    profile_service: "UserProfileService | None" = None,
    logger: Logger | None = None,
    forward_display_threshold: int = 50,
    forward_max_nesting: int = 10,
) -> ChatInteractionAgent:
    return ChatInteractionAgent(
        provider=provider,
        adapter=adapter,
        emoji_service=emoji_service,
        profile_service=profile_service,
        logger=logger,
        forward_display_threshold=forward_display_threshold,
        forward_max_nesting=forward_max_nesting,
    )
