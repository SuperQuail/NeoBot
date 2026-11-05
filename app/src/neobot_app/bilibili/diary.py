"""B站动态日记 — 把今天群聊摘要写成一条 B站动态并发布。

默认关闭（config.bilibili.dynamic_diary_enabled=false）。日记前 5 分钟刷新摘要，
只读 group_summary（不读私聊），按上次快照做行级 diff；agent 用 read_diary_material
分页查看，用 send_dynamic/cancel 决定发布。素材快照只在**发布成功**后更新，
preview/发布失败都不消费当天的 diff。
发布只调用 BilibiliClient/BilibiliService.publish_dynamic，不碰 QQ 空间、不回复消息。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_app.bilibili._compat import bilibili_config, call_client, get_field
from neobot_app.bilibili.prompts import build_diary_prompt
from neobot_app.bilibili.diary_tools import run_diary_agent
from neobot_app.skills.base import SkillModule
from neobot_app.time_context import get_current_time_values, today_local, to_local
from neobot_app.utils.atomic import atomic_write_text
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.diary")

DEFAULT_MATERIAL_TABLES = ("group_summary",)
#: 每张档案表最多取多少条当日条目做素材。
_MAX_ARCHIVE_ITEMS = 20
#: 单条档案素材最多截取多少字符。
_ARCHIVE_ITEM_CHARS = 500


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BilibiliDiaryService:
    """每日摘要 -> B站动态。"""

    def __init__(
        self,
        provider: Any = None,
        client: Any = None,
        *,
        archive_service: Any = None,
        material_provider: Any = None,
        data_dir: Path | None = None,
        bot_name: str = "",
        bot_data: str = "",
        enabled: bool = False,
        max_chars: int = 600,
        max_material_chars: int = 6000,
        requirement: str = "",
        timeout_seconds: float = 60.0,
    ) -> None:
        # client 可以是 BilibiliClient（同步 publish_dynamic）或 BilibiliService（异步门面）。
        self._provider = provider
        self._client = client
        self._archive = archive_service
        self._material_provider = material_provider
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._bot_name = bot_name
        self._bot_data = bot_data
        self._enabled = bool(enabled)
        self._max_chars = max(1, int(max_chars or 600))
        self._max_material_chars = max(0, int(max_material_chars or 0))
        self._requirement = str(requirement or "").strip()
        self._timeout_seconds = float(timeout_seconds)
        #: 定时任务与工具预览/发布互斥，避免两份生成共用同一份旧快照。
        self._lock = asyncio.Lock()
        #: 本轮素材快照，只在发布成功后落盘（预览/失败不消费今天的 diff）。
        self._pending_snapshot: list[str] | None = None

    @classmethod
    def from_config(
        cls,
        provider: Any,
        client: Any,
        config: Any,
        *,
        archive_service: Any = None,
        material_provider: Any = None,
        data_dir: Path | None = None,
        bot_name: str = "",
        bot_data: str = "",
        **overrides: Any,
    ) -> "BilibiliDiaryService":
        cfg = bilibili_config(config)
        values: dict[str, Any] = {
            "archive_service": archive_service,
            "material_provider": material_provider,
            "data_dir": data_dir,
            "bot_name": bot_name,
            "bot_data": bot_data,
            "enabled": bool(getattr(cfg, "dynamic_diary_enabled", False)),
        }
        values["requirement"] = str(getattr(cfg, "dynamic_diary_requirement", "") or "")
        values.update(overrides)
        return cls(provider, client, **values)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        return self._provider is not None and self._enabled

    # ── 素材 ──

    async def collect_material(self) -> str:
        """只收集群聊摘要，并按上次快照做行级 diff；+ 前缀表示今天新增/变化。"""
        return await self._archive_material()

    def _snapshot_path(self) -> Path | None:
        if self._data_dir is None:
            return None
        return self._data_dir / "bilibili" / "diary_material.json"

    def _load_snapshot(self) -> list[str] | None:
        path = self._snapshot_path()
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return [str(item) for item in data] if isinstance(data, list) else None

    def _save_snapshot(self, lines: list[str]) -> None:
        path = self._snapshot_path()
        if path is None:
            return
        try:
            atomic_write_text(path, json.dumps(lines, ensure_ascii=False))
        except Exception as exc:
            logger.warning(f"B站日记素材快照写入失败，下次可能重复采用素材：{path}（{type(exc).__name__}: {exc}）")

    def _commit_snapshot(self) -> None:
        """发布成功后落盘本次快照；预览/发布失败都不落盘，避免吃掉 diff。"""
        lines = self._pending_snapshot
        if lines is None:
            return
        self._save_snapshot(lines)
        self._pending_snapshot = None

    async def _archive_material(self) -> str:
        if self._archive is None:
            return ""
        today = today_local()
        current: list[str] = []
        for table in DEFAULT_MATERIAL_TABLES:
            try:
                items = await call_client(
                    self._archive.list, table, limit=_MAX_ARCHIVE_ITEMS
                )
            except Exception as exc:
                logger.warning(f"读取日记档案失败，本次日记将缺少该表素材（{table}）：{type(exc).__name__}: {exc}")
                continue
            for item in items or []:
                updated = get_field(item, "updated_at", None)
                if isinstance(updated, datetime):
                    try:
                        if to_local(updated).date() != today:
                            continue
                    except Exception:
                        pass
                key = str(get_field(item, "key", "") or "")
                value = str(get_field(item, "value", "") or "").strip()
                if not value:
                    continue
                for line in value.splitlines():
                    text = line.strip()
                    if text:
                        current.append(f"[群:{key}] {text[:_ARCHIVE_ITEM_CHARS]}")
        previous = self._load_snapshot()
        if previous is None:
            added = current
        else:
            seen = set(previous)
            added = [line for line in current if line not in seen]
        # 这里只记下候选快照；真正落盘等 publish() 成功后 _commit_snapshot()。
        self._pending_snapshot = current
        return "\n".join(f"+ {line}" for line in added)

    # ── 生成与发布 ──

    async def generate(self) -> str:
        """生成动态正文；返回空字符串表示生成失败或 agent 决定不写。"""
        if self._provider is None:
            return ""
        material = await self.collect_material()
        date_text = get_current_time_values()["current_date"]
        system, user = build_diary_prompt(
            "",
            date_text=date_text,
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            max_chars=self._max_chars,
            max_material_chars=self._max_material_chars,
            requirement=self._requirement,
        )
        try:
            result = await run_diary_agent(
                self._provider,
                system,
                user,
                [line for line in material.splitlines() if line],
                max_chars=self._max_chars,
                timeout=self._timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"B站日记生成失败：{type(exc).__name__}: {exc}")
            return ""
        return result.text or ""

    async def publish(self, text: str) -> dict:
        """发布一条文本动态，返回 {ok, dynamic_id, error}。"""
        target = self._client
        publisher = getattr(target, "publish_dynamic", None) if target is not None else None
        if not callable(publisher):
            return {"ok": False, "error": "B站客户端未配置或不支持发布动态"}
        try:
            dynamic_id = await call_client(publisher, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"B站动态发布失败：{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        logger.info(f"B站动态已发布（dynamic_id={dynamic_id}，{len(text)} 字）")
        self._commit_snapshot()
        return {"ok": True, "dynamic_id": dynamic_id}

    async def run(self, *, preview: bool = False) -> dict:
        """生成并（非 preview 时）发布；返回结构化结果。"""
        if not self._enabled:
            return {"ok": False, "error": "B站动态日记未启用"}
        # 定时发布与工具调用互斥：素材快照/生成/发布是一整段，不能被另一个 run 插队。
        async with self._lock:
            text = await self.generate()
            if not text:
                return {"ok": False, "error": "生成失败或模型没有产出"}
            if preview:
                return {"ok": True, "preview": True, "text": text}
            result = await self.publish(text)
            result["text"] = text
            return result


class BilibiliDiarySkill(SkillModule):
    """Agent 工具：生成/发布 B站动态日记。"""

    def __init__(self, service: BilibiliDiaryService | None = None) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "bilibili_diary"

    @property
    def description(self) -> str:
        return "B站动态日记：把今天的聊天/档案写成一条B站动态并发布（默认关闭，可先 preview）"

    @property
    def instructions(self) -> str:
        return (
            "B站动态日记 Skill 提供以下能力：\n\n"
            "  publish_bilibili_diary — 生成今天的B站动态并发布；preview=true 时只生成不发布。\n\n"
            "使用前提：B站已登录且已开启动态日记（默认关闭）。"
            "动态内容只来自群聊摘要（不读私聊），按今天新增/变化做 diff；不会修改QQ空间。"
        )

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._service is None:
            return []
        return [
            self._tool_def(
                "publish_bilibili_diary",
                "生成今天的B站动态并发布。preview=true 时只返回草稿、不发布。",
                {
                    "properties": {
                        "preview": {
                            "type": "boolean",
                            "description": "只生成不发布，默认 false",
                            "default": False,
                        }
                    },
                    "required": [],
                },
            )
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "publish_bilibili_diary" or self._service is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        try:
            result = await self._service.run(preview=bool(args.get("preview", False)))
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})
        return _json(result)
