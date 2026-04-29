"""Archive memory agent and tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
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
from neobot_memory import ArchiveMemoryService

from neobot_app.agents.image_parse import ImageParseAgent
from neobot_app.favorability import clamp_favorability, favorability_to_text

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.config.schemas.bot import AgentMemoryArchive, AgentMemoryFavorability
    from neobot_app.user_profiles import UserProfileService


# 暴露给回复流主 Agent 的描述。
# 次级 Agent 文件都应在文件顶部集中声明这部分内容。
EXPOSED_TO_MAIN_AGENT_NAME = "memory"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "长期记忆与用户档案。可读写群聊/好友的长期记忆档案（增/查/列）、"
    "查询用户资料与好友备注、解析用户头像并写入用户档案、"
    "拉取历史聊天记录辅助记忆决策、根据互动质量调整用户好感度。"
    "涉及记忆/档案/用户资料/头像解析/好感度的任务均委托它。"
)

_MEMORY_CONTEXT: ContextVar[str] = ContextVar("memory_context", default="")

# 同级 sub agent 描述，用于识别任务是否应委托给其他 agent
PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片。\n"
    "- chat_interaction: 聊天互动、群管理（设管理员/禁言/踢人/群名片/头衔等）、好友管理（备注/分组/删除/点赞等）、发送表情包。\n"
    "- image_parse: 仅按需求解析图片内容，不保存、不导入、不管理图库/表情包。\n"
    "如果收到的任务明显属于其他 agent 的职责，直接告知主Agent该委托给对应的 agent，不要越权处理。"
)

DEFAULT_LIST_LIMIT = 10
MAX_LIST_LIMIT = 200


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _coerce_nonnegative_int(value: Any, *, default: int) -> int:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ArchiveMemoryAgentConfig:
    allow_delete: bool = False
    allowed_tables: tuple[str, ...] = ()
    auto_compact_chars: int = 500
    max_chars: int = 600
    favorability_max_change: int = 5
    favorability_min: int = -1000
    favorability_max: int = 1000

    @classmethod
    def from_schema(
        cls,
        config: "AgentMemoryArchive | None" = None,
        favorability_config: "AgentMemoryFavorability | None" = None,
    ) -> "ArchiveMemoryAgentConfig":
        base = cls()
        if config is not None:
            base = cls(
                allow_delete=bool(config.allow_delete),
                allowed_tables=tuple(str(item) for item in config.allowed_tables if str(item).strip()),
                auto_compact_chars=_coerce_nonnegative_int(
                    getattr(config, "auto_compact_chars", 500),
                    default=500,
                ),
                max_chars=_coerce_nonnegative_int(getattr(config, "max_chars", 600), default=600),
                favorability_max_change=base.favorability_max_change,
                favorability_min=base.favorability_min,
                favorability_max=base.favorability_max,
            )
        if favorability_config is not None:
            base = cls(
                allow_delete=base.allow_delete,
                allowed_tables=base.allowed_tables,
                auto_compact_chars=base.auto_compact_chars,
                max_chars=base.max_chars,
                favorability_max_change=_coerce_nonnegative_int(
                    getattr(favorability_config, "max_change_per_summary", 5),
                    default=5,
                ),
                favorability_min=int(getattr(favorability_config, "min_value", -1000) or -1000),
                favorability_max=int(getattr(favorability_config, "max_value", 1000) or 1000),
            )
        return base


class ArchiveMemoryToolExecutor(ToolExecutor):
    """Tool executor for archive memory CRUD."""

    def __init__(
        self,
        archive_memory_service: ArchiveMemoryService,
        *,
        config: ArchiveMemoryAgentConfig | None = None,
        profile_service: "UserProfileService | None" = None,
        adapter: "OneBotAdapter | None" = None,
        compaction_provider: Provider | None = None,
        image_parse_provider: Provider | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._service = archive_memory_service
        self._config = config or ArchiveMemoryAgentConfig()
        self._profile_service = profile_service
        self._adapter = adapter
        self._compaction_provider = compaction_provider
        self._image_parse_provider = image_parse_provider
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        user_info_item_schema = {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "QQ号"},
            },
            "required": ["user_id"],
        }
        read_item_schema = {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "档案表名"},
                "key": {"type": "string", "description": "条目键"},
            },
            "required": ["table_name", "key"],
        }
        user_info_tools = []
        if self._profile_service is not None:
            user_info_tools.append(
                _tool_def(
                    "read_user_info",
                    "读取数据库用户资料表中的资料，包含好友备注 remark 和头像解析记忆 avatar_analysis。查询某个QQ号的好友备注或头像记忆时优先使用此工具。",
                    {
                        "properties": {
                            "user_id": {"type": "string", "description": "单条读取时的QQ号"},
                            "items": {
                                "type": "array",
                                "items": user_info_item_schema,
                                "description": "批量读取时的QQ号列表",
                            },
                        },
                    },
                )
            )
        avatar_tools = []
        if self._profile_service is not None and self._adapter is not None and self._image_parse_provider is not None:
            avatar_tools.append(
                _tool_def(
                    "analyze_user_avatar",
                    "获取并解析指定用户QQ头像,将解析结果写入用户资料表 avatar_analysis。",
                    {
                        "properties": {
                            "user_id": {"type": "string", "description": "目标QQ号"},
                            "group_id": {"type": "string", "description": "可选，群号"},
                            "requirement": {
                                "type": "string",
                                "description": "可选，头像解析要求；默认提取稳定外观特征和可作为记忆的头像信息。",
                            },
                        },
                        "required": ["user_id"],
                    },
                )
            )
        history_tools = []
        if self._adapter is not None:
            history_tools.append(
                _tool_def(
                    "read_earlier_messages",
                    "读取更早的聊天记录。自动记忆触发时,如果近期消息含义不明确,使用它拉取更多上下文后再决定是否写入记忆。",
                    {
                        "properties": {
                            "conversation_kind": {
                                "type": "string",
                                "enum": ["group", "private"],
                                "description": "会话类型",
                            },
                            "conversation_id": {"type": "string", "description": "群号或好友QQ号"},
                            "message_seq": {
                                "type": "integer",
                                "description": "可选，历史起点 message_seq，默认0",
                            },
                            "count": {"type": "integer", "description": "读取条数，默认20，最大50"},
                            "reverse_order": {"type": "boolean", "description": "是否反向排序"},
                        },
                        "required": ["conversation_kind", "conversation_id"],
                    },
                )
            )

        favorability_tools = []
        if self._profile_service is not None and self._config.favorability_max_change > 0:
            favorability_tools.append(
                _tool_def(
                    "update_favorability",
                    f"调整用户好感度。每次变更幅度限制在 ±{self._config.favorability_max_change} 以内，"
                    f"范围 {self._config.favorability_min} 到 {self._config.favorability_max}。"
                    "根据近期聊天中用户表现出的态度、行为、互动质量等综合判断，适当调整好感度。"
                    "正向互动（友好、积极、配合）增加好感度，负向互动（冒犯、恶意、骚扰）减少好感度。",
                    {
                        "properties": {
                            "user_id": {"type": "string", "description": "目标QQ号"},
                            "change": {
                                "type": "integer",
                                "description": f"好感度变更量，范围 [{-self._config.favorability_max_change}, {self._config.favorability_max_change}]",
                            },
                            "reason": {
                                "type": "string",
                                "description": "可选，变更原因简述",
                            },
                        },
                        "required": ["user_id", "change"],
                    },
                )
            )

        return [
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射。仅在任务缺少群号/QQ号、或需要确认聊天上下文中的指代时调用。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "save_archive",
                "创建或更新一条档案记忆。修改已有档案时，必须写回整合后的完整内容，不要只写增量。",
                {
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "档案表名，例如 user_profile 或 group_summary",
                        },
                        "key": {
                            "type": "string",
                            "description": "条目键，例如 QQ 号或群号",
                        },
                        "value": {
                            "type": "string",
                            "description": "整合更新后的完整档案内容",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选标签",
                        },
                    },
                    "required": ["table_name", "key", "value"],
                },
            ),
            _tool_def(
                "read_archive",
                "读取档案记忆。可传单条 table_name 加 key，也可传 items 批量读取多条。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "单条读取时的档案表名"},
                        "key": {"type": "string", "description": "单条读取时的条目键"},
                        "items": {
                            "type": "array",
                            "items": read_item_schema,
                            "description": "批量读取时的条目列表",
                        },
                    },
                },
            ),
            *user_info_tools,
            *avatar_tools,
            *history_tools,
            *favorability_tools,
            _tool_def(
                "list_archive",
                "列出档案记忆条目。默认一次返回10条。如需继续查看，传更大的 offset，并用 limit 指定本次继续查看的条数。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名"},
                        "key_query": {"type": "string", "description": "可选的键筛选条件"},
                        "value_query": {"type": "string", "description": "可选的内容筛选条件"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选的标签筛选条件",
                        },
                        "limit": {"type": "integer", "description": "本次返回条数，默认10"},
                        "offset": {"type": "integer", "description": "分页偏移量，用于继续查看后续条目"},
                    },
                    "required": ["table_name"],
                },
            ),
            _tool_def(
                "delete_archive",
                "按表名和键删除一条档案记忆。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名"},
                        "key": {"type": "string", "description": "条目键"},
                    },
                    "required": ["table_name", "key"],
                },
            ),
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_chat_context":
            return self._get_chat_context()
        if name == "save_archive":
            return await self._save_archive(args)
        if name == "read_archive":
            return await self._read_archive(args)
        if name == "read_user_info":
            return await self._read_user_info(args)
        if name == "analyze_user_avatar":
            return await self._analyze_user_avatar(args)
        if name == "read_earlier_messages":
            return await self._read_earlier_messages(args)
        if name == "list_archive":
            return await self._list_archive(args)
        if name == "delete_archive":
            return await self._delete_archive(args)
        if name == "update_favorability":
            return await self._update_favorability(args)
        return _json({"ok": False, "error": f"unknown archive tool: {name}"})

    async def close(self) -> None:
        return None

    @staticmethod
    def _get_chat_context() -> str:
        context = _MEMORY_CONTEXT.get("").strip()
        if not context:
            return _json({"ok": False, "error": "当前没有可用的聊天上下文"})
        return _json({"ok": True, "context": context})

    async def _save_archive(self, args: dict[str, Any]) -> str:
        table_name, table_error = self._resolve_table_name(args.get("table_name"))
        if table_name is None:
            return _json({"ok": False, "error": table_error})
        key = self._validate_required_text(args.get("key"))
        if key is None:
            return _json({"ok": False, "error": "key is required"})
        value = self._validate_required_text(args.get("value"))
        if value is None:
            return _json({"ok": False, "error": "value is required"})
        tags = self._normalize_tags(args.get("tags"))

        value, value_status = await self._prepare_archive_value(
            table_name=table_name,
            key=key,
            value=value,
        )
        item = await self._service.set(table_name, key, value, tags)
        self._logger.debug("存档记忆代理已保存条目", table_name=table_name, key=key)
        return _json(
            {
                "ok": True,
                **value_status,
                "item": {
                    "table_name": item.table_name,
                    "key": item.key,
                    "value": item.value,
                    "tags": item.tags,
                    "version": item.version,
                },
            }
        )

    async def _prepare_archive_value(
        self,
        *,
        table_name: str,
        key: str,
        value: str,
    ) -> tuple[str, dict[str, Any]]:
        original_length = len(value)
        compacted = False
        truncated = False

        auto_limit = self._config.auto_compact_chars
        max_limit = self._config.max_chars
        if auto_limit > 0 and original_length > auto_limit and self._compaction_provider is not None:
            compacted_value = await self._compact_archive_value(
                table_name=table_name,
                key=key,
                value=value,
                target_chars=auto_limit,
            )
            if compacted_value:
                value = compacted_value
                compacted = True

        if max_limit > 0 and len(value) > max_limit:
            value = value[:max_limit]
            truncated = True

        return value, {
            "compacted": compacted,
            "truncated": truncated,
            "original_length": original_length,
            "written_length": len(value),
            "auto_compact_chars": auto_limit,
            "max_chars": max_limit,
        }

    async def _compact_archive_value(
        self,
        *,
        table_name: str,
        key: str,
        value: str,
        target_chars: int,
    ) -> str:
        prompt = (
            "请精简以下长期记忆档案。要求：\n"
            "1. 尽可能在不删减事实的情况下压缩措辞。\n"
            "2. 如果必须删减，优先删减最不重要、最琐碎、重复或时效性最低的部分。\n"
            "3. 保留稳定的个人信息、群信息、偏好、关系和明确要求记住的内容。\n"
            f"4. 尽量控制在 {target_chars} 个中文字符以内。\n"
            "只输出精简后的档案正文。\n\n"
            f"档案表: {table_name}\n键: {key}\n原档案:\n{value}"
        )
        try:
            response = await self._compaction_provider.chat(
                [
                    {"role": "system", "content": "你负责压缩长期记忆档案，只输出档案正文。"},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as exc:
            self._logger.warning(
                "archive memory compact failed",
                table_name=table_name,
                key=key,
                error=str(exc),
            )
            return ""
        return self._extract_response_text(response).strip()

    async def _read_archive(self, args: dict[str, Any]) -> str:
        requests, error = self._normalize_read_requests(args)
        if error is not None:
            return _json({"ok": False, "error": error})

        results: list[dict[str, Any]] = []
        for table_name, key in requests:
            item = await self._service.get(table_name, key)
            if item is None:
                results.append(
                    {
                        "found": False,
                        "table_name": table_name,
                        "key": key,
                    }
                )
                continue
            results.append(
                {
                    "found": True,
                    "item": {
                        "table_name": item.table_name,
                        "key": item.key,
                        "value": item.value,
                        "tags": item.tags,
                        "version": item.version,
                    },
                }
            )

        if len(results) == 1:
            result = results[0]
            if result["found"]:
                return _json({"ok": True, "found": True, "item": result["item"]})
            return _json(
                {
                    "ok": True,
                    "found": False,
                    "table_name": result["table_name"],
                    "key": result["key"],
                }
            )

        return _json(
            {
                "ok": True,
                "count": len(results),
                "results": results,
            }
        )

    async def _read_user_info(self, args: dict[str, Any]) -> str:
        if self._profile_service is None:
            return _json({"ok": False, "error": "user profile service is not configured"})

        requests, error = self._normalize_user_info_requests(args)
        if error is not None:
            return _json({"ok": False, "error": error})

        results: list[dict[str, Any]] = []
        for user_id in requests:
            profile = await self._profile_service.get_user(user_id)
            if profile is None:
                results.append({"found": False, "user_id": user_id})
                continue
            results.append(
                {
                    "found": True,
                    "user": self._serialize_user_profile(profile, user_id=user_id),
                }
            )

        if len(results) == 1:
            result = results[0]
            if result["found"]:
                return _json({"ok": True, "found": True, "user": result["user"]})
            return _json({"ok": True, "found": False, "user_id": result["user_id"]})

        return _json({"ok": True, "count": len(results), "results": results})

    async def _analyze_user_avatar(self, args: dict[str, Any]) -> str:
        if self._profile_service is None or self._adapter is None or self._image_parse_provider is None:
            return _json({"ok": False, "error": "avatar analysis dependencies are not configured"})

        user_id = self._validate_required_text(args.get("user_id"))
        if user_id is None:
            return _json({"ok": False, "error": "user_id is required"})

        group_id = self._normalize_optional_text(args.get("group_id"))
        requirement = self._normalize_optional_text(args.get("requirement")) or (
            "请简洁描述这个QQ头像中稳定、可作为长期记忆的视觉信息。"
            "只描述头像本身,不要推断真实身份、性格或敏感属性。"
        )

        avatar_url = await self._fetch_avatar_url(user_id=user_id, group_id=group_id)
        if not avatar_url:
            return _json({"ok": False, "error": "avatar url not found", "user_id": user_id})

        parser = ImageParseAgent(
            self._image_parse_provider,
            adapter=self._adapter,
            logger=self._logger,
        )
        state = await parser.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": _json(
                            {
                                "requirement": requirement,
                                "image_url": avatar_url,
                            }
                        ),
                    }
                ]
            }
        )
        messages = state.get("messages", [])
        analysis = ""
        if messages:
            content = messages[-1].get("content")
            analysis = content if isinstance(content, str) else str(content or "")
        analysis = analysis.strip()
        if not analysis:
            return _json({"ok": False, "error": "avatar analysis returned empty text", "user_id": user_id})

        await self._profile_service.update_user_avatar_analysis(user_id, analysis)
        return _json(
            {
                "ok": True,
                "user_id": user_id,
                "avatar_url": avatar_url,
                "avatar_analysis": analysis,
            }
        )

    async def _fetch_avatar_url(self, *, user_id: str, group_id: str | None) -> str | None:
        params = {"user_id": int(user_id), "group_id": int(group_id) if group_id else None}
        result = await self._adapter.call_api("get_qq_avatar", params)
        data = result.get("data") if isinstance(result, dict) else None
        url = data.get("url") if isinstance(data, dict) else None
        return str(url).strip() if url else None

    async def _read_earlier_messages(self, args: dict[str, Any]) -> str:
        if self._adapter is None:
            return _json({"ok": False, "error": "adapter is not configured"})

        conversation_kind = self._normalize_optional_text(args.get("conversation_kind"))
        conversation_id = self._validate_required_text(args.get("conversation_id"))
        if conversation_kind not in {"group", "private"}:
            return _json({"ok": False, "error": "conversation_kind must be group or private"})
        if conversation_id is None:
            return _json({"ok": False, "error": "conversation_id is required"})

        message_seq = max(0, int(args.get("message_seq") or 0))
        count = min(max(1, int(args.get("count") or 20)), 50)
        reverse_order = bool(args.get("reverse_order", False))
        if conversation_kind == "group":
            response = await self._adapter.get_group_msg_history(
                int(conversation_id),
                message_seq=message_seq,
                count=count,
                reverse_order=reverse_order,
            )
        else:
            response = await self._adapter.get_friend_msg_history(
                int(conversation_id),
                message_seq=message_seq,
                count=count,
                reverse_order=reverse_order,
            )

        data = getattr(response, "data", None)
        messages = list(getattr(data, "messages", None) or [])
        return _json(
            {
                "ok": True,
                "conversation_kind": conversation_kind,
                "conversation_id": conversation_id,
                "count": len(messages),
                "messages": [self._serialize_history_message(message) for message in messages],
            }
        )

    async def _list_archive(self, args: dict[str, Any]) -> str:
        table_name, table_error = self._resolve_table_name(args.get("table_name"))
        if table_name is None:
            return _json({"ok": False, "error": table_error})

        limit = self._normalize_limit(args.get("limit"))
        offset = max(0, int(args.get("offset") or 0))
        tags = self._normalize_tags(args.get("tags"))
        key_query = self._normalize_optional_text(args.get("key_query"))
        value_query = self._normalize_optional_text(args.get("value_query"))

        fetched = await self._service.list(
            table_name,
            tags=tags or None,
            key_query=key_query,
            value_query=value_query,
            limit=min(limit + 1, MAX_LIST_LIMIT),
            offset=offset,
        )
        has_more = len(fetched) > limit
        items = fetched[:limit]
        next_offset = offset + len(items)

        return _json(
            {
                "ok": True,
                "count": len(items),
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
                "next_offset": next_offset if has_more else None,
                "items": [
                    {
                        "table_name": item.table_name,
                        "key": item.key,
                        "value": item.value,
                        "tags": item.tags,
                        "version": item.version,
                    }
                    for item in items
                ],
            }
        )

    async def _delete_archive(self, args: dict[str, Any]) -> str:
        if not self._config.allow_delete:
            return _json({"ok": False, "error": "delete_archive is disabled by config"})

        table_name, table_error = self._resolve_table_name(args.get("table_name"))
        if table_name is None:
            return _json({"ok": False, "error": table_error})
        key = self._validate_required_text(args.get("key"))
        if key is None:
            return _json({"ok": False, "error": "key is required"})

        deleted = await self._service.delete(table_name, key)
        return _json({"ok": True, "deleted": deleted, "table_name": table_name, "key": key})

    async def _update_favorability(self, args: dict[str, Any]) -> str:
        if self._profile_service is None:
            return _json({"ok": False, "error": "user profile service is not configured"})

        user_id = self._validate_required_text(args.get("user_id"))
        if user_id is None:
            return _json({"ok": False, "error": "user_id is required"})

        change_raw = args.get("change")
        try:
            change = int(change_raw)
        except (TypeError, ValueError):
            return _json({"ok": False, "error": f"change must be an integer, got {change_raw}"})

        max_change = self._config.favorability_max_change
        if abs(change) > max_change:
            change = max_change if change > 0 else -max_change

        profile = await self._profile_service.get_user(user_id)
        current = int(getattr(profile, "favorability", 0) or 0)
        new_value = clamp_favorability(
            current + change,
            min_val=self._config.favorability_min,
            max_val=self._config.favorability_max,
        )
        actual_change = new_value - current

        reason = self._normalize_optional_text(args.get("reason")) or ""

        if actual_change != 0:
            await self._profile_service.update_user_favorability(user_id, new_value)

        old_label = favorability_to_text(current)
        new_label = favorability_to_text(new_value)
        return _json({
            "ok": True,
            "user_id": user_id,
            "previous": current,
            "change": actual_change,
            "value": new_value,
            "previous_label": old_label,
            "new_label": new_label,
            "reason": reason,
            "clamped": actual_change != change,
        })

    def _normalize_read_requests(self, args: dict[str, Any]) -> tuple[list[tuple[str, str]], str | None]:
        raw_items = args.get("items")
        if raw_items is not None:
            if not isinstance(raw_items, list) or not raw_items:
                return [], "items must be a non-empty array"
            requests: list[tuple[str, str]] = []
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    return [], "each item in items must be an object"
                table_name, table_error = self._resolve_table_name(raw_item.get("table_name"))
                if table_name is None:
                    return [], table_error
                key = self._validate_required_text(raw_item.get("key"))
                if key is None:
                    return [], "key is required"
                requests.append((table_name, key))
            return requests, None

        table_name, table_error = self._resolve_table_name(args.get("table_name"))
        if table_name is None:
            return [], table_error
        key = self._validate_required_text(args.get("key"))
        if key is None:
            return [], "key is required"
        return [(table_name, key)], None

    def _normalize_user_info_requests(self, args: dict[str, Any]) -> tuple[list[str], str | None]:
        raw_items = args.get("items")
        if raw_items is not None:
            if not isinstance(raw_items, list) or not raw_items:
                return [], "items must be a non-empty array"
            requests: list[str] = []
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    return [], "each item in items must be an object"
                user_id = self._validate_required_text(raw_item.get("user_id"))
                if user_id is None:
                    return [], "user_id is required"
                requests.append(user_id)
            return requests, None

        user_id = self._validate_required_text(args.get("user_id"))
        if user_id is None:
            return [], "user_id is required"
        return [user_id], None

    @staticmethod
    def _serialize_user_profile(profile: Any, *, user_id: str) -> dict[str, Any]:
        fetched_at = getattr(profile, "fetched_at", None)
        fav = int(getattr(profile, "favorability", 0) or 0)
        return {
            "user_id": str(getattr(profile, "user_id", None) or user_id),
            "nick_name": getattr(profile, "nick_name", None) or "",
            "remark": getattr(profile, "remark", None) or "",
            "avatar_analysis": getattr(profile, "avatar_analysis", None) or "",
            "profile": getattr(profile, "profile", None) or "",
            "known_gender": getattr(profile, "known_gender", None) or "",
            "sex": getattr(profile, "sex", None) or "",
            "age": getattr(profile, "age", None),
            "city": getattr(profile, "city", None) or "",
            "country": getattr(profile, "country", None) or "",
            "birthday": getattr(profile, "birthday", None) or "",
            "long_nick": getattr(profile, "long_nick", None) or "",
            "labs": getattr(profile, "labs", None) or "",
            "favorability": fav,
            "favorability_label": favorability_to_text(fav),
            "fetched_at": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else None,
        }

    @staticmethod
    def _serialize_history_message(message: Any) -> dict[str, Any]:
        sender = getattr(message, "sender", None)
        sender_name = (
            getattr(sender, "card", None)
            or getattr(sender, "nickname", None)
            or getattr(message, "user_id", None)
            or ""
        )
        return {
            "message_id": getattr(message, "message_id", None),
            "message_seq": getattr(message, "message_seq", None),
            "time": getattr(message, "time", None),
            "sender_id": getattr(message, "user_id", None) or getattr(sender, "user_id", None),
            "sender_name": str(sender_name),
            "raw_message": getattr(message, "raw_message", None) or "",
        }

    @staticmethod
    def _extract_response_text(response: dict[str, Any]) -> str:
        content = response.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text") or item.get("content")
                    if value is not None:
                        parts.append(str(value))
                elif item is not None:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content or "")

    def _resolve_table_name(self, raw: Any) -> tuple[str | None, str]:
        table_name = self._normalize_optional_text(raw)
        if not table_name:
            return None, "table_name is required"
        if self._config.allowed_tables and table_name not in self._config.allowed_tables:
            return None, f"table_name '{table_name}' is not allowed"
        return table_name, ""

    @staticmethod
    def _validate_required_text(raw: Any) -> str | None:
        text = str(raw or "").strip()
        return text or None

    @staticmethod
    def _normalize_optional_text(raw: Any) -> str | None:
        text = str(raw).strip() if raw is not None else ""
        return text or None

    @staticmethod
    def _normalize_tags(raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list):
            values = raw
        else:
            values = [raw]

        normalized: list[str] = []
        for item in values:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized

    @staticmethod
    def _normalize_limit(raw: Any) -> int:
        limit = DEFAULT_LIST_LIMIT if raw is None else int(raw)
        limit = max(1, limit)
        return min(limit, MAX_LIST_LIMIT - 1)


def build_archive_memory_toolset(
    archive_memory_service: ArchiveMemoryService,
    *,
    config: ArchiveMemoryAgentConfig | AgentMemoryArchive | None = None,
    favorability_config: "AgentMemoryFavorability | None" = None,
    profile_service: "UserProfileService | None" = None,
    adapter: "OneBotAdapter | None" = None,
    compaction_provider: Provider | None = None,
    image_parse_provider: Provider | None = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    normalized = (
        config
        if isinstance(config, ArchiveMemoryAgentConfig)
        else ArchiveMemoryAgentConfig.from_schema(config, favorability_config=favorability_config)
    )
    executor = ArchiveMemoryToolExecutor(
        archive_memory_service,
        config=normalized,
        profile_service=profile_service,
        adapter=adapter,
        compaction_provider=compaction_provider,
        image_parse_provider=image_parse_provider,
        logger=logger,
    )
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


def _build_system_prompt(
    config: ArchiveMemoryAgentConfig,
    *,
    has_user_info: bool = False,
    has_avatar_analysis: bool = False,
    has_history: bool = False,
    has_favorability: bool = False,
) -> str:
    allowed_tables = "、".join(config.allowed_tables) if config.allowed_tables else "全部表"
    delete_state = "允许" if config.allow_delete else "禁用"
    user_info_rule = (
        "查询某个QQ号的好友备注或基础用户资料时，优先使用 read_user_info；如果用户资料表查不到，再读取 user_profile 档案。\n"
        if has_user_info
        else ""
    )
    avatar_rule = (
        "需要理解某个用户头像时,使用 analyze_user_avatar 获取并解析头像;解析结果会写入用户资料 avatar_analysis。\n"
        if has_avatar_analysis
        else ""
    )
    history_rule = (
        "自动记忆触发时,如果近期消息含义不完整或指代不清,可以使用 read_earlier_messages 拉取更早聊天记录确认,确认后再决定是否写入。\n"
        if has_history
        else ""
    )
    favorability_rule = (
        f"自动记忆触发且存在好感度工具时，根据近期聊天中参与用户的行为综合调整好感度。\n"
        f"正向互动（友好、配合、积极）适当增加好感度，负向互动（冒犯、骚扰、恶意）适当减少好感度。\n"
        f"每次变更上限 ±{config.favorability_max_change}，范围 {config.favorability_min}~{config.favorability_max}。\n"
        f"调整时使用 update_favorability 工具，无需过度谨慎，少量变化累积才能体现关系趋势。\n"
        if has_favorability
        else ""
    )
    return (
        "你是记忆Agent。\n"
        "只处理长期记忆相关任务，优先调用工具，不要空谈。\n"
        "禁止使用Markdown。\n"
        "输出尽可能精简，只返回必要结果。\n"
        "如果任务缺少群号/QQ号或需要确认聊天上下文中的指代信息，先调用 get_chat_context 查看主Agent上下文和消息编号映射。\n"
        "遇到修改、追加、补充、整合类请求时，先读旧档案，再写回整合后的完整新档案，不要只写增量。\n"
        "自动触发的群聊记忆流程：先依次检查本轮参与聊天的所有群友,只记录了解到的新个人信息,不记录具体聊天事件;如果聊天中明确要求你记住某些事情且档案没有,加入对应档案;没有新信息时允许不写;最后再记录群的新信息,同样不记录具体事件。\n"
        "自动触发的好友聊天记忆流程：只记录该好友新的稳定信息或明确要求记住的内容,不记录具体聊天事件;没有新信息时允许不写。\n"
        f"{favorability_rule}"
        "记录时效性信息时，必须使用\"YY年M月D日\"的简写日期格式标注时间（如\"26年4月25日\"），禁止使用\"最近\"\"前几天\"\"不久前\"等模糊时间表述。\n"
        "记录指向性信息时，必须明确标注所属的群号或QQ号。例如写\"张三(QQ:12345)是群号67890的群群主\"，而不是\"张三是群主\"。\n"
        f"{user_info_rule}"
        f"{avatar_rule}"
        f"{history_rule}"
        "read_archive 支持批量读取；需要一次查看多条时，优先使用 items 批量传入。\n"
        "list_archive 默认一次只看10条；如果还要继续看，使用 next_offset 作为新的 offset，并传入这次还想多看几条 limit。\n"
        "常用表约定：user_profile 表示用户档案，key 通常是 QQ 号；group_profile 表示群档案，key 通常是群号；group_summary 表示群摘要，key 通常是群号。\n"
        f"单条档案超过 {config.auto_compact_chars} 字符会先自动精简,超过 {config.max_chars} 字符会截断写入。\n"
        "示例1：修改QQ号为12345的用户的档案，增加他今天早饭吃了个包子。\n"
        "示例2：读取QQ号为12345和QQ号为67890的两个用户档案。\n"
        f"可访问的表：{allowed_tables}。\n"
        f"delete_archive：{delete_state}。\n"
        f"{PEER_AGENT_DESCRIPTIONS}\n"
        "任务完成后，只返回简短纯文本结果。"
    )


class ArchiveMemoryAgent:
    """LLM-backed agent dedicated to archive memory operations."""

    def __init__(
        self,
        provider: Provider,
        archive_memory_service: ArchiveMemoryService,
        *,
        config: ArchiveMemoryAgentConfig | AgentMemoryArchive | None = None,
        favorability_config: "AgentMemoryFavorability | None" = None,
        profile_service: "UserProfileService | None" = None,
        adapter: "OneBotAdapter | None" = None,
        image_parse_provider: Provider | None = None,
        logger: Logger | None = None,
    ) -> None:
        normalized = (
            config
            if isinstance(config, ArchiveMemoryAgentConfig)
            else ArchiveMemoryAgentConfig.from_schema(config, favorability_config=favorability_config)
        )
        has_favorability = (
            profile_service is not None and normalized.favorability_max_change > 0
        )
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_archive_memory_toolset(
            archive_memory_service,
            config=normalized,
            profile_service=profile_service,
            adapter=adapter,
            compaction_provider=provider,
            image_parse_provider=image_parse_provider,
            logger=logger,
        )
        self.tool_definitions = self._toolset.definitions()
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(
                normalized,
                has_user_info=profile_service is not None,
                has_avatar_analysis=profile_service is not None and adapter is not None and image_parse_provider is not None,
                has_history=adapter is not None,
                has_favorability=has_favorability,
            ),
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        token = _MEMORY_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            return await self._agent.invoke(state)
        finally:
            _MEMORY_CONTEXT.reset(token)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _MEMORY_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _MEMORY_CONTEXT.reset(token)

    async def close(self) -> None:
        await self._agent.close()


def build_archive_memory_agent(
    provider: Provider,
    archive_memory_service: ArchiveMemoryService,
    *,
    config: ArchiveMemoryAgentConfig | AgentMemoryArchive | None = None,
    favorability_config: "AgentMemoryFavorability | None" = None,
    profile_service: "UserProfileService | None" = None,
    adapter: "OneBotAdapter | None" = None,
    image_parse_provider: Provider | None = None,
    logger: Logger | None = None,
) -> ArchiveMemoryAgent:
    return ArchiveMemoryAgent(
        provider,
        archive_memory_service,
        config=config,
        favorability_config=favorability_config,
        profile_service=profile_service,
        adapter=adapter,
        image_parse_provider=image_parse_provider,
        logger=logger,
    )
