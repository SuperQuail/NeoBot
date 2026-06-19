"""Live DeepSeek test for main-agent archive-memory delegation.

Usage:
  .\\.venv\\Scripts\\python.exe -B test\\run_archive_memory_deepseek.py --request "修改QQ号为12345的用户档案，增加他今天早饭吃了个包子"

Without ``--request``, the script starts an interactive loop.
Archive data is persisted in ``test/db/archive_memory_chat_loop_verify.sqlite3``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neobot_chat import Agent
from neobot_chat.providers import DeepSeekOfficialProvider
from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.logging import NullLogger

from neobot_app.assembly.agents import build_agent_registry
from neobot_app.config.loader.env import load_env
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.config.schemas.env import EnvConfig
from neobot_app.reply.tools import build_reply_toolset

# Manual overrides for quick local testing.
# Priority: values filled here > values loaded from app/.env.
MANUAL_DEEPSEEK_API_KEY = ""
MANUAL_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MANUAL_USER_REQUEST = ""
MANUAL_SEED_TABLE = "user_profile"
MANUAL_SEED_KEY = ""
MANUAL_SEED_VALUE = ""
MANUAL_SEED_TAGS: list[str] = ["profile"]
MANUAL_DB_PATH = "test/db/archive_memory_chat_loop_verify.sqlite3"
MANUAL_MAIN_MODEL = "deepseek-chat"
MANUAL_ARCHIVE_MODEL = ""


@dataclass
class ReplyCapture:
    text: str = ""

    async def send(self, *, text: str, reply_to: int | None = None) -> None:
        self.text = text


class PersistentSqliteArchiveService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def get(self, table_name: str, key: str) -> ArchiveMemory | None:
        return self._get_sync(table_name, key)

    async def exists(self, table_name: str, key: str) -> bool:
        item = await self.get(table_name, key)
        return item is not None

    async def list(
        self,
        table_name: str,
        *,
        tags: list[str] | None = None,
        key_query: str | None = None,
        value_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]:
        return self._list_sync(
            table_name,
            tags,
            key_query,
            value_query,
            limit,
            offset,
        )

    async def set(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        return self._set_sync(table_name, key, value, tags)

    async def delete(self, table_name: str, key: str) -> bool:
        return self._delete_sync(table_name, key)

    def close(self) -> None:
        return None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS archive_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(table_name, key)
                )
                """
            )
            conn.commit()

    def _get_sync(self, table_name: str, key: str) -> ArchiveMemory | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, table_name, key, value, tags, created_at, updated_at, version
                FROM archive_memory
                WHERE table_name = ? AND key = ?
                """,
                (table_name, key),
            ).fetchone()
        return self._row_to_model(row) if row else None

    def _list_sync(
        self,
        table_name: str,
        tags: list[str] | None,
        key_query: str | None,
        value_query: str | None,
        limit: int,
        offset: int,
    ) -> list[ArchiveMemory]:
        sql = """
            SELECT id, table_name, key, value, tags, created_at, updated_at, version
            FROM archive_memory
            WHERE table_name = ?
        """
        params: list[Any] = [table_name]
        if key_query:
            sql += " AND key LIKE ?"
            params.append(f"%{key_query}%")
        if value_query:
            sql += " AND value LIKE ?"
            params.append(f"%{value_query}%")
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([max(0, limit), max(0, offset)])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        items = [self._row_to_model(row) for row in rows]
        if tags:
            items = [item for item in items if all(tag in item.tags for tag in tags)]
        return items

    def _set_sync(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        now = self._now_iso()
        serialized_tags = json.dumps(tags, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, created_at, version FROM archive_memory WHERE table_name = ? AND key = ?",
                (table_name, key),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE archive_memory
                    SET value = ?, tags = ?, updated_at = ?, version = ?
                    WHERE table_name = ? AND key = ?
                    """,
                    (
                        value,
                        serialized_tags,
                        now,
                        int(existing["version"]) + 1,
                        table_name,
                        key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO archive_memory (table_name, key, value, tags, created_at, updated_at, version)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (table_name, key, value, serialized_tags, now, now),
                )

            conn.commit()
            row = conn.execute(
                """
                SELECT id, table_name, key, value, tags, created_at, updated_at, version
                FROM archive_memory
                WHERE table_name = ? AND key = ?
                """,
                (table_name, key),
            ).fetchone()

        if row is None:
            raise RuntimeError(f"archive entry not found after save: {table_name}:{key}")
        return self._row_to_model(row)

    def _delete_sync(self, table_name: str, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM archive_memory WHERE table_name = ? AND key = ?",
                (table_name, key),
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_model(self, row: sqlite3.Row) -> ArchiveMemory:
        return ArchiveMemory(
            id=int(row["id"]),
            table_name=str(row["table_name"]),
            key=str(row["key"]),
            value=str(row["value"]),
            tags=self._parse_tags(row["tags"]),
            created_at=self._parse_dt(row["created_at"]),
            updated_at=self._parse_dt(row["updated_at"]),
            version=int(row["version"]),
        )

    @staticmethod
    def _parse_tags(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
        return []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_dt(raw: str) -> datetime:
        value = datetime.fromisoformat(raw)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use DeepSeek to test main-agent archive-memory delegation.")
    parser.add_argument("--request", default="", help="Natural-language archive request for the main agent")
    parser.add_argument("--seed-table", default="", help="Optional archive table to seed before running requests")
    parser.add_argument("--seed-key", default="", help="Optional archive key to seed before running requests")
    parser.add_argument("--seed-value", default="", help="Optional archive value to seed before running requests")
    parser.add_argument("--seed-tag", action="append", default=[], help="Optional seed tag, can be repeated")
    parser.add_argument("--db-path", default=MANUAL_DB_PATH, help="SQLite database path for persisted archive data")
    parser.add_argument("--model", default=MANUAL_MAIN_MODEL, help="DeepSeek model for main agent")
    parser.add_argument("--archive-model", default=None, help="DeepSeek model for archive agent; defaults to --model")
    return parser.parse_args()


def _prompt_if_empty(value: str, prompt_text: str) -> str:
    if value.strip():
        return value.strip()
    return input(prompt_text).strip()


def resolve_runtime_args(args: argparse.Namespace) -> argparse.Namespace:
    request = args.request.strip() or MANUAL_USER_REQUEST.strip()
    seed_table = args.seed_table.strip() or MANUAL_SEED_TABLE.strip()
    seed_key = args.seed_key.strip() or MANUAL_SEED_KEY.strip()
    seed_value = args.seed_value if args.seed_value.strip() else MANUAL_SEED_VALUE
    seed_tags = args.seed_tag or list(MANUAL_SEED_TAGS)
    archive_model = (
        args.archive_model.strip()
        if isinstance(args.archive_model, str) and args.archive_model.strip()
        else MANUAL_ARCHIVE_MODEL.strip() or None
    )

    args.request = request
    args.seed_table = seed_table
    args.seed_key = seed_key
    args.seed_value = seed_value
    args.seed_tag = seed_tags
    args.db_path = str(Path(args.db_path).expanduser())
    args.archive_model = archive_model
    return args


def build_deepseek_provider(model: str) -> DeepSeekOfficialProvider:
    config = EnvConfig.get_api_platform_config("DeepSeek")
    api_key = MANUAL_DEEPSEEK_API_KEY.strip() or (config.api_key or "").strip()
    base_url = MANUAL_DEEPSEEK_BASE_URL.strip() or (config.url or "https://api.deepseek.com").strip()
    if not api_key or api_key == "test-placeholder-key":
        raise RuntimeError(
            "请配置真实的 DeepSeek API Key："
            "可以在脚本顶部填写 MANUAL_DEEPSEEK_API_KEY，"
            "或在 app/.env 中填写 DeepSeek_APIKey"
        )
    return DeepSeekOfficialProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


async def run_once(agent: Agent, prompt: str, capture: ReplyCapture) -> dict:
    capture.text = ""
    return await agent.invoke({"messages": [{"role": "user", "content": prompt}]})


def extract_delegate_result(state: dict) -> str | None:
    messages = state.get("messages", [])
    for message in reversed(messages):
        if message.get("role") == "tool":
            content = message.get("content")
            if isinstance(content, str):
                return content
    return None


async def run_request(agent: Agent, capture: ReplyCapture, request: str) -> None:
    state = await run_once(agent, request, capture)
    delegate_result = extract_delegate_result(state)
    print("=== Result ===")
    print(f"request={request}")
    print(f"delegate_result={delegate_result}")
    print(f"reply={capture.text}")
    print()


async def interactive_loop(agent: Agent, capture: ReplyCapture) -> None:
    print("Interactive mode started.")
    print("输入自然语言档案请求，输入 exit / quit / q 结束。")
    print()
    while True:
        request = _prompt_if_empty("", "Request> ")
        if not request:
            continue
        if request.lower() in {"exit", "quit", "q"}:
            break
        await run_request(agent, capture, request)


async def main() -> None:
    args = parse_args()
    load_env()
    args = resolve_runtime_args(args)
    using_manual_key = bool(MANUAL_DEEPSEEK_API_KEY.strip())

    archive_service = PersistentSqliteArchiveService(args.db_path)
    config = BotConfig()
    config.agent.memory.archive.allow_delete = True

    archive_model = args.archive_model or args.model
    agent_registry = None
    main_agent = None
    try:
        agent_registry = build_agent_registry(
            config=config,
            archive_memory_service=archive_service,
            provider_factory=lambda: build_deepseek_provider(archive_model),
            logger=NullLogger(),
        )

        seeded = False
        if args.seed_table and args.seed_key and args.seed_value.strip():
            await archive_service.set(
                args.seed_table,
                args.seed_key,
                args.seed_value,
                args.seed_tag or ["profile"],
            )
            seeded = True

        capture = ReplyCapture()
        toolset = build_reply_toolset(
            send_reply_handler=capture.send,
            agent_registry=agent_registry,
        )
        main_agent = Agent(
            build_deepseek_provider(args.model),
            toolset=toolset,
            system_prompt=(
                "你是主代理。\n"
                "只要用户请求涉及档案读写，就必须调用 delegate，agent 固定为 memory。\n"
                "把用户原始自然语言请求直接传给子代理，不要改写成 JSON，不要改成自定义协议。\n"
                "禁止使用 Markdown。\n"
                "输出尽量精简。\n"
                "委托完成后，调用 send_reply，使用简体中文给出简短结果。"
            ),
            logger=NullLogger(),
        )

        print(f"credential_source={'manual' if using_manual_key else 'env'}")
        print(f"db_path={archive_service.db_path}")
        print(f"seeded={seeded}")
        if seeded:
            print(f"seed_table={args.seed_table}")
            print(f"seed_key={args.seed_key}")
            print(f"seed_value={args.seed_value}")
            print(f"seed_tags={args.seed_tag}")
        print()

        if args.request.strip():
            await run_request(main_agent, capture, args.request)
        else:
            await interactive_loop(main_agent, capture)
    finally:
        if main_agent is not None:
            await main_agent.close()
        if agent_registry is not None:
            await agent_registry.close()
        archive_service.close()


if __name__ == "__main__":
    asyncio.run(main())
