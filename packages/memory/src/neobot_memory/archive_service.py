"""归档记忆服务。

本模块同时是「档案容量治理」的唯一收口点：save_archive、patch_archive 与自动总结
计数器三条写入路径最终都走 ArchiveMemoryService.set()，超限判定放在这里才能保证
绕过 skill 的写入同样受保护（D1-B）。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Optional

from neobot_contracts.errors import NeoBotError
from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory

#: 超限动作默认值：写库成功后异步压缩。
DEFAULT_OVERFLOW_ACTION = "summarize"
#: 同一 (table_name, key) 两次自动压缩之间的默认最小间隔（秒）。
DEFAULT_OVERFLOW_COOLDOWN_SECONDS = 600.0
#: 超限清单一次最多返回多少条（防止把大表整块塞进面板响应体）。
_MAX_OVER_LIMIT_PAGE_SIZE = 500
#: 超限清单里的内容预览字符数。
_OVER_LIMIT_PREVIEW_CHARS = 200

#: 不参与容量治理的内部表（默认豁免名单）。
#: ⚠️ 与 agent.memory.archive.allowed_tables 语义完全不同：那个是「限制模型能访问
#: 哪些表」，这里是「哪些表不做长度上限拦截」，两者绝不可复用。
#: memory_counter 存的是「待总结消息 JSON」，group_interval=500 时天然超过任何上限：
#:   - 若对它 reject：自动总结连计数都写不进去，整条管线直接断掉；
#:   - 若对它 summarize：压缩器会去「压缩」待总结消息队列，把尚未总结的消息吃掉。
#: 因此它必须无条件豁免；一旦误伤，表现是「档案自动总结整体失效」，比长度超限严重得多。
DEFAULT_EXEMPT_TABLES: frozenset[str] = frozenset({"memory_counter"})

#: 超限压缩的调度回调签名：(table_name, key) -> 是否已调度。
#: 必须立即返回（同步）：写路径要求「先落库、再异步压缩」，不能等一次完整的 AI 调用。
OverflowSummaryTrigger = Callable[[str, str], bool]


class ArchiveOverflowRejected(NeoBotError, ValueError):
    """overflow_action="reject" 时拒绝写入（交由模型自行压缩后重试）。"""

    def __init__(
        self,
        message: str,
        *,
        table_name: str = "",
        key: str = "",
        chars: int = 0,
        max_total_chars: int = 0,
        hint: str = "",
    ) -> None:
        super().__init__(message)
        self.table_name = table_name
        self.key = key
        self.chars = chars
        self.max_total_chars = max_total_chars
        self.hint = hint


class ArchiveVersionConflictError(NeoBotError, ValueError):
    """档案乐观锁版本冲突（服务层公开异常，面板据此返回 409）。

    仓库层（neobot_storage）在版本不一致时抛出它自己的同名异常，
    服务层统一翻译成本类，面板只需要依赖 neobot_memory。
    """

    def __init__(
        self,
        message: str,
        *,
        table_name: str = "",
        key: str = "",
        expected_version: int = 0,
        actual_version: int = 0,
    ) -> None:
        super().__init__(message)
        self.table_name = table_name
        self.key = key
        self.expected_version = expected_version
        self.actual_version = actual_version


@dataclass(frozen=True)
class ArchiveWriteOutcome:
    """一次档案写入的结果，附带容量治理信息。

    item 为 None 表示写入被拒绝（只在 overflow_action="reject" 时出现）。
    """

    item: Optional[ArchiveMemory] = None
    over_limit: bool = False
    action: str = "none"  # none | summarize | reject
    scheduled: bool = False  # 是否已把后台压缩交给触发方
    chars: int = 0
    max_total_chars: int = 0
    hint: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        """写入是否真的落库。"""
        return self.item is not None


def _normalize_max_total_chars(value: Any) -> int:
    """把配置读成非负整数上限；None/非法值/负数一律视为 0（禁用）。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _normalize_overflow_action(value: Any) -> str:
    """把配置读成 summarize / reject；未知值回落到 summarize。"""
    action = str(value or "").strip().lower()
    return action if action in {"summarize", "reject"} else DEFAULT_OVERFLOW_ACTION


def _normalize_cooldown(value: Any) -> float:
    """把配置读成非负冷却秒数；None/非法值回落默认值。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_OVERFLOW_COOLDOWN_SECONDS
    return parsed if parsed > 0 else 0.0


class ArchiveMemoryService:
    """归档记忆的增删改查与查询操作服务。"""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        logger: Logger,
        *,
        max_total_chars: Any = 0,
        overflow_action: Any = DEFAULT_OVERFLOW_ACTION,
        overflow_summary_cooldown_seconds: Any = DEFAULT_OVERFLOW_COOLDOWN_SECONDS,
        exempt_tables: Iterable[str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._logger = logger
        # 容量治理默认关闭：只有外部（bootstrap / 自动总结服务）显式配置后才会生效，
        # 从而保证「不接线 = 与现状完全一致」。
        self._max_total_chars = _normalize_max_total_chars(max_total_chars)
        self._overflow_action = _normalize_overflow_action(overflow_action)
        self._overflow_cooldown_seconds = _normalize_cooldown(overflow_summary_cooldown_seconds)
        self._exempt_tables: frozenset[str] = (
            frozenset(str(name) for name in exempt_tables)
            if exempt_tables is not None
            else DEFAULT_EXEMPT_TABLES
        )
        self._overflow_trigger: Optional[OverflowSummaryTrigger] = None
        #: (table_name, key) -> 冷却到期时刻（time.monotonic()）
        self._overflow_cooldown_until: dict[tuple[str, str], float] = {}

    # ── 容量治理配置 ────────────────────────────────────────────────

    def configure_overflow_policy(
        self,
        *,
        max_total_chars: Any = None,
        overflow_action: Any = None,
        cooldown_seconds: Any = None,
        exempt_tables: Iterable[str] | None = None,
    ) -> None:
        """配置单条档案的存储上限与超限动作；参数为 None 表示保持当前值。

        max_total_chars=0 表示禁用容量治理（行为回落到现状）。
        """
        if max_total_chars is not None:
            self._max_total_chars = _normalize_max_total_chars(max_total_chars)
        if overflow_action is not None:
            self._overflow_action = _normalize_overflow_action(overflow_action)
        if cooldown_seconds is not None:
            self._overflow_cooldown_seconds = _normalize_cooldown(cooldown_seconds)
        if exempt_tables is not None:
            self._exempt_tables = frozenset(str(name) for name in exempt_tables)

    def set_overflow_trigger(self, trigger: Optional[OverflowSummaryTrigger]) -> None:
        """注入「档案超限 → 调度一次自动压缩」的回调（None 表示卸载）。"""
        self._overflow_trigger = trigger

    @property
    def max_total_chars(self) -> int:
        """单条档案的存储硬上限；0 表示禁用。"""
        return self._max_total_chars

    @property
    def overflow_action(self) -> str:
        """超限动作：summarize / reject。"""
        return self._overflow_action

    @property
    def exempt_tables(self) -> frozenset[str]:
        """不参与容量治理的内部表集合。"""
        return self._exempt_tables

    def clear_overflow_cooldown(self, table_name: str, key: str) -> None:
        """清除某个条目的压缩冷却。

        压缩失败时由触发方调用：失败不应该被冷却窗口掩盖成 600 秒的静默，
        清掉冷却后「下次写入再试」才成立（是否真的重试仍由触发方的失败退避决定）。
        """
        self._overflow_cooldown_until.pop((table_name, key), None)

    # ── 基本读写（签名语义保持不变，面板直接转调） ──────────────────

    async def get(self, table_name: str, key: str) -> Optional[ArchiveMemory]:
        async with self._uow_factory() as uow:
            item = await uow.archive.get(table_name, key)
        self._logger.debug("存档记忆已获取", table_name=table_name, key=key, found=item is not None)
        return item

    async def exists(self, table_name: str, key: str) -> bool:
        async with self._uow_factory() as uow:
            exists = await uow.archive.exists(table_name, key)
        self._logger.debug("存档记忆存在检查", table_name=table_name, key=key, exists=exists)
        return exists

    async def list(
        self,
        table_name: str,
        *,
        tags: Optional[list[str]] = None,
        key_query: Optional[str] = None,
        value_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArchiveMemory]:
        async with self._uow_factory() as uow:
            items = await uow.archive.list(
                table_name,
                tags=tags,
                key_query=key_query,
                value_query=value_query,
                limit=limit,
                offset=offset,
            )
        self._logger.debug(
            "存档记忆列表已获取",
            table_name=table_name,
            count=len(items),
            limit=limit,
            offset=offset,
        )
        return items

    async def set(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        """创建或更新归档记忆条目（容量治理的唯一收口点）。

        超过 max_total_chars 时：
        - overflow_action="summarize"：先落库（不丢信息），再触发异步压缩，立即返回；
        - overflow_action="reject"：不写库，抛 ArchiveOverflowRejected。
        """
        outcome = await self.set_with_outcome(table_name, key, value, tags)
        if outcome.item is None:
            raise ArchiveOverflowRejected(
                outcome.error or f"档案超过存储上限: {table_name}:{key}",
                table_name=table_name,
                key=key,
                chars=outcome.chars,
                max_total_chars=outcome.max_total_chars,
                hint=outcome.hint,
            )
        return outcome.item

    async def set_with_outcome(
        self, table_name: str, key: str, value: str, tags: list[str]
    ) -> ArchiveWriteOutcome:
        """与 set 相同，但把超限信息（over_limit / 是否已调度压缩 / hint）一并返回。

        工具层（archive_crud）用它给模型回 over_limit=True + hint；面板/内部写路径
        可以直接用 set()。
        """
        limit = self._max_total_chars
        chars = len(value or "")
        governed = table_name not in self._exempt_tables
        over_limit = governed and limit > 0 and chars > limit
        if over_limit and self._overflow_action == "reject":
            hint = (
                f"档案超过存储上限 {limit} 字（当前 {chars} 字），已拒绝写入"
                "（agent.memory.archive.overflow_action=reject）。"
                "请先用 read_archive 的 outline/offset 分页阅读，再用 patch_archive "
                "压缩或删除冗余内容后重试。"
            )
            self._logger.warning(
                "档案超过存储上限，按配置拒绝写入",
                table_name=table_name,
                key=key,
                chars=chars,
                max_total_chars=limit,
            )
            return ArchiveWriteOutcome(
                item=None,
                over_limit=True,
                action="reject",
                chars=chars,
                max_total_chars=limit,
                hint=hint,
                error=f"档案超过存储上限 {limit} 字（当前 {chars} 字），已拒绝写入",
            )

        async with self._uow_factory() as uow:
            item = await uow.archive.set(table_name, key, value, tags)
            await uow.commit()
        self._logger.debug(
            "存档记忆已保存",
            table_name=table_name,
            key=key,
            version=item.version,
        )
        if not over_limit:
            return ArchiveWriteOutcome(item=item, chars=chars, max_total_chars=limit)

        # 先写后压缩：原文已经落库，压缩只是在后台把体积收回来（不丢信息）。
        scheduled = self._schedule_overflow_compression(table_name, key, chars=chars, limit=limit)
        if scheduled:
            hint = (
                f"档案已超过存储上限 {limit} 字（当前 {chars} 字），已触发后台自动压缩。"
                "压缩期间请勿整条重写该档案；稍后用 read_archive 查看压缩结果。"
            )
        else:
            hint = (
                f"档案已超过存储上限 {limit} 字（当前 {chars} 字），后台自动压缩暂未调度"
                "（AI 不可用或处于冷却中）。原文已完整保留，下次写入会自动重试。"
            )
        self._logger.warning(
            "档案超过存储上限，已保留原内容并等待压缩",
            table_name=table_name,
            key=key,
            chars=chars,
            max_total_chars=limit,
            compression_scheduled=scheduled,
        )
        return ArchiveWriteOutcome(
            item=item,
            over_limit=True,
            action="summarize",
            scheduled=scheduled,
            chars=chars,
            max_total_chars=limit,
            hint=hint,
        )

    async def delete(self, table_name: str, key: str) -> bool:
        async with self._uow_factory() as uow:
            deleted = await uow.archive.delete(table_name, key)
            if deleted:
                await uow.commit()
        self._logger.debug("存档记忆已删除", table_name=table_name, key=key, deleted=deleted)
        return deleted

    # ── 乐观锁与观测能力（面板） ────────────────────────────────────

    async def set_if_version(
        self,
        table_name: str,
        key: str,
        value: str,
        tags: list[str],
        expected_version: int,
    ) -> ArchiveMemory:
        """带乐观锁的写入：version 不一致时抛 ArchiveVersionConflictError（面板 409）。

        注意这里不做容量治理判定：面板是运维兜底入口，管理员必须能写入并看到
        超限提示，而不是被上限拦在门外（真正超限的档案应通过压缩回收）。
        """
        limit = self._max_total_chars
        chars = len(value or "")
        if limit > 0 and chars > limit and table_name not in self._exempt_tables:
            # 面板是运维兜底入口：必须能写入并看到超限，而不是被上限拦在门外；
            # 这里只记录 WARNING，让超限档案仍能被 list_over_limit 枚举出来。
            self._logger.warning(
                "面板写入的档案超过存储上限（面板路径不拦截，仅记录）",
                table_name=table_name,
                key=key,
                chars=chars,
                max_total_chars=limit,
            )
        async with self._uow_factory() as uow:
            setter = getattr(uow.archive, "set_if_version", None)
            if setter is None:
                # 默认内存实现（neobot_memory.defaults）没有乐观锁：退化成先查后写。
                # 仅在单进程开发/测试路径上使用，真正的并发保护在 SqlAlchemy 仓库里。
                item = await self._set_if_version_fallback(
                    uow, table_name, key, value, tags, expected_version
                )
            else:
                try:
                    item = await setter(table_name, key, value, tags, expected_version)
                except NeoBotError as exc:
                    # 仓库层的冲突异常带 table/key/expected/actual，翻译时原样保留，
                    # 面板据此能直接渲染「已被他人修改（当前 version=N）」。
                    raise ArchiveVersionConflictError(
                        str(exc),
                        table_name=str(getattr(exc, "table_name", "") or table_name),
                        key=str(getattr(exc, "key", "") or key),
                        expected_version=int(getattr(exc, "expected_version", 0) or 0),
                        actual_version=int(getattr(exc, "actual_version", 0) or 0),
                    ) from exc
            await uow.commit()
        self._logger.debug(
            "存档记忆乐观锁写入",
            table_name=table_name,
            key=key,
            version=item.version,
        )
        return item

    async def _set_if_version_fallback(
        self,
        uow: Any,
        table_name: str,
        key: str,
        value: str,
        tags: list[str],
        expected_version: int,
    ) -> ArchiveMemory:
        """无原生乐观锁的存储实现：先查后写（有 TOCTOU 窗口，仅开发路径）。"""
        current = await uow.archive.get(table_name, key)
        actual = int(getattr(current, "version", 0) or 0) if current is not None else 0
        try:
            expected = int(expected_version)
        except (TypeError, ValueError):
            expected = 0
        if actual != expected:
            raise ArchiveVersionConflictError(
                f"档案已被其他写入修改: {table_name}:{key}",
                table_name=table_name,
                key=key,
                expected_version=expected,
                actual_version=actual,
            )
        return await uow.archive.set(table_name, key, value, tags)

    async def list_table_names(self) -> list[str]:
        """库内实际存在哪些档案表（面板表清单；不依赖静态常量）。"""
        async with self._uow_factory() as uow:
            lister = getattr(uow.archive, "list_table_names", None)
            if lister is None:
                self._logger.warning("当前档案存储实现不支持枚举表名，返回空清单")
                return []
            names = await lister()
        return [str(name) for name in names]

    async def table_stats(self) -> list[dict[str, Any]]:
        """每张档案表的条目数与最大 value 字符数。"""
        async with self._uow_factory() as uow:
            stats = getattr(uow.archive, "table_stats", None)
            if stats is None:
                self._logger.warning("当前档案存储实现不支持表统计，返回空清单")
                return []
            rows = await stats()
        return [dict(row) for row in rows]

    async def count_over_limit(self, table_name: Optional[str] = None) -> int:
        """当前超过存储上限的档案条目数（上限禁用时为 0）。"""
        limit = self._max_total_chars
        if limit <= 0:
            return 0
        async with self._uow_factory() as uow:
            counter = getattr(uow.archive, "count_over_limit", None)
            if counter is None:
                return 0
            total = await counter(
                limit,
                table_name=table_name,
                exclude_tables=tuple(sorted(self._exempt_tables)),
            )
        return int(total or 0)

    async def list_over_limit(
        self,
        table_name: Optional[str] = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """枚举「当前超过存储上限」的档案（A7 可观测，供面板直接返回 JSON）。

        返回字段：table_name / key / chars / version / updated_at（ISO8601）/ preview。
        内部豁免表（memory_counter 等）永远不出现在这里——它们天然超限，列出来只会
        把真正的超标档案淹没。
        """
        max_chars = self._max_total_chars
        if max_chars <= 0:
            return []
        page_size = max(0, min(int(limit), _MAX_OVER_LIMIT_PAGE_SIZE))
        async with self._uow_factory() as uow:
            lister = getattr(uow.archive, "list_over_limit", None)
            if lister is None:
                self._logger.warning("当前档案存储实现不支持超限清单，返回空清单")
                return []
            items = await lister(
                max_chars,
                table_name=table_name,
                exclude_tables=tuple(sorted(self._exempt_tables)),
                limit=page_size,
                offset=max(offset, 0),
            )
        return [self._over_limit_entry(item, max_chars=max_chars) for item in items]

    @staticmethod
    def _over_limit_entry(item: ArchiveMemory, *, max_chars: int) -> dict[str, Any]:
        value = item.value or ""
        updated_at = item.updated_at
        return {
            "table_name": item.table_name,
            "key": item.key,
            "chars": len(value),
            "version": item.version,
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
            "max_total_chars": max_chars,
            "preview": value[:_OVER_LIMIT_PREVIEW_CHARS],
        }

    # ── 超限压缩调度 ────────────────────────────────────────────────

    def _in_overflow_cooldown(self, table_name: str, key: str) -> bool:
        until = self._overflow_cooldown_until.get((table_name, key), 0.0)
        return until > 0.0 and time.monotonic() < until

    def _schedule_overflow_compression(
        self, table_name: str, key: str, *, chars: int, limit: int
    ) -> bool:
        """触发一次异步压缩；返回是否真的调度成功。

        冷却与单飞：冷却在这里判（同一 key 在 overflow_summary_cooldown_seconds
        内不重复触发），单飞由触发方持有（同一 (table, key) 同时只跑一个压缩任务）。
        触发方返回 False（AI 不可用 / 正在压缩 / 处于失败退避）时不写冷却，
        这样「下次写入再试」才不会被一次失败锁死 600 秒。
        """
        if self._in_overflow_cooldown(table_name, key):
            self._logger.debug(
                "档案超过存储上限，但仍在压缩冷却期内，跳过本次触发",
                table_name=table_name,
                key=key,
            )
            return False
        trigger = self._overflow_trigger
        if trigger is None:
            self._logger.warning(
                "档案超过存储上限但没有可用的自动压缩入口，仅保留原内容",
                table_name=table_name,
                key=key,
                chars=chars,
                max_total_chars=limit,
            )
            return False
        try:
            scheduled = bool(trigger(table_name, key))
        except Exception as exc:
            self._logger.warning(
                "档案超过存储上限，触发自动压缩失败",
                table_name=table_name,
                key=key,
                error=str(exc) or type(exc).__name__,
            )
            return False
        if scheduled:
            self._overflow_cooldown_until[(table_name, key)] = (
                time.monotonic() + self._overflow_cooldown_seconds
            )
        return scheduled
