"""Archive memory agent and tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import AgentMemoryArchive


# 暴露给回复流主 Agent 的描述。
# 次级 Agent 文件都应在文件顶部集中声明这部分内容。
EXPOSED_TO_MAIN_AGENT_NAME = "archive_memory"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "可以读写好友或群聊的记忆档案。需要提供目标 QQ 号或群号，以及如何读取或修改。"
    "例如：修改群号123的群描述，追加该群是2024年创建的。"
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


@dataclass(frozen=True)
class ArchiveMemoryAgentConfig:
    allow_delete: bool = False
    allowed_tables: tuple[str, ...] = ()

    @classmethod
    def from_schema(cls, config: "AgentMemoryArchive | None") -> "ArchiveMemoryAgentConfig":
        if config is None:
            return cls()
        return cls(
            allow_delete=bool(config.allow_delete),
            allowed_tables=tuple(str(item) for item in config.allowed_tables if str(item).strip()),
        )


class ArchiveMemoryToolExecutor(ToolExecutor):
    """Tool executor for archive memory CRUD."""

    def __init__(
        self,
        archive_memory_service: ArchiveMemoryService,
        *,
        config: ArchiveMemoryAgentConfig | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._service = archive_memory_service
        self._config = config or ArchiveMemoryAgentConfig()
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        read_item_schema = {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "档案表名"},
                "key": {"type": "string", "description": "条目键"},
            },
            "required": ["table_name", "key"],
        }
        return [
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
        if name == "save_archive":
            return await self._save_archive(args)
        if name == "read_archive":
            return await self._read_archive(args)
        if name == "list_archive":
            return await self._list_archive(args)
        if name == "delete_archive":
            return await self._delete_archive(args)
        return _json({"ok": False, "error": f"unknown archive tool: {name}"})

    async def close(self) -> None:
        return None

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

        item = await self._service.set(table_name, key, value, tags)
        self._logger.debug("archive memory agent saved entry", table_name=table_name, key=key)
        return _json(
            {
                "ok": True,
                "item": {
                    "table_name": item.table_name,
                    "key": item.key,
                    "value": item.value,
                    "tags": item.tags,
                    "version": item.version,
                },
            }
        )

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
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    normalized = (
        config if isinstance(config, ArchiveMemoryAgentConfig) else ArchiveMemoryAgentConfig.from_schema(config)
    )
    executor = ArchiveMemoryToolExecutor(
        archive_memory_service,
        config=normalized,
        logger=logger,
    )
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


def _build_system_prompt(config: ArchiveMemoryAgentConfig) -> str:
    allowed_tables = "、".join(config.allowed_tables) if config.allowed_tables else "全部表"
    delete_state = "允许" if config.allow_delete else "禁用"
    return (
        "你是档案记忆代理。\n"
        "只处理档案读写任务，优先调用工具，不要空谈。\n"
        "禁止使用Markdown。\n"
        "输出尽可能精简，只返回必要结果。\n"
        "遇到修改、追加、补充、整合类请求时，先读旧档案，再写回整合后的完整新档案，不要只写增量。\n"
        "read_archive 支持批量读取；需要一次查看多条时，优先使用 items 批量传入。\n"
        "list_archive 默认一次只看10条；如果还要继续看，使用 next_offset 作为新的 offset，并传入这次还想多看几条 limit。\n"
        "常用表约定：user_profile 表示用户档案，key 通常是 QQ 号；group_profile 表示群档案，key 通常是群号；group_summary 表示群摘要，key 通常是群号。\n"
        "示例1：修改QQ号为12345的用户的档案，增加他今天早饭吃了个包子。\n"
        "示例2：读取QQ号为12345和QQ号为67890的两个用户档案。\n"
        f"可访问的表：{allowed_tables}。\n"
        f"delete_archive：{delete_state}。\n"
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
        logger: Logger | None = None,
    ) -> None:
        normalized = (
            config if isinstance(config, ArchiveMemoryAgentConfig) else ArchiveMemoryAgentConfig.from_schema(config)
        )
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_archive_memory_toolset(
            archive_memory_service,
            config=normalized,
            logger=logger,
        )
        self.tool_definitions = self._toolset.definitions()
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(normalized),
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        return await self._agent.invoke(state)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        async for chunk in self._agent.stream_invoke(state):
            yield chunk

    async def close(self) -> None:
        await self._agent.close()


def build_archive_memory_agent(
    provider: Provider,
    archive_memory_service: ArchiveMemoryService,
    *,
    config: ArchiveMemoryAgentConfig | AgentMemoryArchive | None = None,
    logger: Logger | None = None,
) -> ArchiveMemoryAgent:
    return ArchiveMemoryAgent(
        provider,
        archive_memory_service,
        config=config,
        logger=logger,
    )
