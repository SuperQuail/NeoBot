"""总结触发前半段：消息计数、计数器读写与缓存、失败退避与清账。"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from neobot_app.time_context import epoch_seconds

from .constants import (
    COUNTER_TABLE,
    MAX_STORED_MESSAGE_CHARS,
    _COUNTER_CACHE_TTL_SECONDS,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_MAX_DOUBLINGS,
    RETRY_BACKOFF_MAX_SECONDS,
)
from .helpers import _normalize_counter_message, _normalize_message_text, _tunable


class SummaryCounterMixin:
    """消息记录与计数器状态机（自动总结的唯一数据源）。"""

    async def record_message(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        """记录一条实时消息，并在达到配置间隔时触发摘要。"""
        if conversation_kind not in {"group", "private"}:
            return
        if self.is_standby():
            self._logger.debug(
                "Bot 已进入待机，跳过档案自动总结记录",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return
        interval = self._interval_for(conversation_kind)
        if interval <= 0:
            return
        if self._provider is None:
            self._logger.debug(
                "档案自动总结跳过：provider 不可用",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        clean_text = _normalize_message_text(message_text)
        if not clean_text:
            return

        counter_key = self._counter_key(conversation_kind, conversation_id)
        entry = {
            "sender_id": str(sender_id or ""),
            "sender_name": str(sender_name or ""),
            "text": clean_text[:MAX_STORED_MESSAGE_CHARS],
        }
        async with self._counter_lock(counter_key):
            state = await self._cached_counter(counter_key)
            if int(state.get("count", 0)) + 1 >= interval:
                # 将要触发总结：以库里的最新状态为准。计数器读路径带 30 秒缓存，
                # 若直接写回缓存内容，会把外部对计数器（清零、改冷却）的修改覆盖掉。
                state = await self._load_counter(counter_key)
            messages = list(state.get("messages", []))
            messages.append(entry)
            count = int(state.get("count", 0)) + 1

            state = self._counter_state(
                count=count,
                messages=messages[-max(interval, 1) :],
                failures=state.get("failures"),
                retry_after=state.get("retry_after"),
            )
            await self._save_counter(counter_key, state)

        if count < interval:
            return

        # 同一会话只允许一次总结在跑：消息在总结期间继续累计，
        # 但不会为每条消息都排一个「必然超时」的任务。占位由
        # _summarize_and_reset 内部统一持有（flush_all 路径共用），这里只预检。
        if counter_key in self._active_summaries:
            self._logger.debug(
                "档案自动总结已在执行，跳过本次调度",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        if not self._retry_ready(state):
            self._logger.debug(
                "档案自动总结处于失败冷却中，保留待总结消息",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                retry_after=state.get("retry_after"),
                failures=state.get("failures"),
            )
            return
        await self._summarize_and_reset(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            counter_key=counter_key,
            messages=list(state.get("messages", [])),
            snapshot_count=count,
        )

    @asynccontextmanager
    async def _counter_lock(self, counter_key: str) -> AsyncIterator[asyncio.Lock]:
        """按 counter_key 分片的计数锁：get-or-create，释放后从注册表回收 key。

        回收时检查注册表中仍是本锁才删除，防止等待者与新建锁并发持有。
        """
        while True:
            lock = self._locks.get(counter_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[counter_key] = lock
            await lock.acquire()
            if self._locks.get(counter_key) is lock:
                break
            lock.release()
        try:
            yield lock
        finally:
            if self._locks.get(counter_key) is lock:
                del self._locks[counter_key]
            lock.release()

    async def _cached_counter(self, key: str) -> dict[str, Any]:
        """读取计数器状态（带进程内解析缓存，缓存有 TTL）。

        record_message 每条消息都要读一次计数器，而它是一整个 JSON blob
        （间隔 500 条 × 800 字符 ≈ 400KB）：在事件循环上每条消息做一次 DB 读 +
        json.loads 是实实在在的开销。缓存解析结果后，读路径只在缓存过期（或首次）
        时落到 DB；写路径仍然每条都落库，因此崩溃丢失窗口与原来一致。

        缓存必须过期：计数器行的外部修改（模型通过 archive_crud 写
        memory_counter、另一个进程、人工改库）在旧实现里是可见的——永不重读会
        让本进程把陈旧 blob 整块写回，撤消外部的删除/清零。
        """
        now = time.monotonic()
        cached = self._counter_cache.get(key)
        ttl = _tunable("_COUNTER_CACHE_TTL_SECONDS", _COUNTER_CACHE_TTL_SECONDS)
        if cached is not None and now - cached[1] < ttl:
            return cached[0]
        fresh = await self._load_counter(key)
        self._counter_cache[key] = (fresh, now)
        return fresh

    async def _load_counter(self, key: str) -> dict[str, Any]:
        item = await self._archive.get(COUNTER_TABLE, key)
        if item is None or not item.value:
            return {"count": 0, "messages": []}
        try:
            data = json.loads(item.value)
        except json.JSONDecodeError:
            return {"count": 0, "messages": []}
        raw_count = data.get("count", 0)
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            messages = []
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        state: dict[str, Any] = {
            "count": count,
            "messages": [_normalize_counter_message(message) for message in messages],
        }
        # 失败冷却信息随计数器一起保存，缺省不写（保持存量数据的原有形态）。
        failures = data.get("failures")
        retry_after = data.get("retry_after")
        if failures:
            state["failures"] = failures
        if retry_after:
            state["retry_after"] = retry_after
        return state

    async def _save_counter(self, key: str, state: dict[str, Any]) -> None:
        await self._archive.set(
            COUNTER_TABLE,
            key,
            json.dumps(state, ensure_ascii=False),
            ["auto_summary_counter"],
        )
        # 同步缓存，避免下次读到过期内容（尤其是总结成功后的清零）
        self._counter_cache[key] = (state, time.monotonic())

    @staticmethod
    def _counter_state(
        *,
        count: int,
        messages: list[Any],
        failures: Any = None,
        retry_after: Any = None,
    ) -> dict[str, Any]:
        """构造计数器状态；默认值不落盘，保持存量数据的原有形态。"""
        state: dict[str, Any] = {"count": int(count), "messages": list(messages)}
        try:
            failure_count = int(failures)
        except (TypeError, ValueError):
            failure_count = 0
        if failure_count > 0:
            state["failures"] = failure_count
        try:
            retry_at = float(retry_after)
        except (TypeError, ValueError):
            retry_at = 0.0
        if retry_at > 0:
            state["retry_after"] = retry_at
        return state

    @staticmethod
    def _retry_ready(state: dict[str, Any]) -> bool:
        """冷却窗口是否已过；无冷却信息时随时可重试。"""
        try:
            retry_after = float(state.get("retry_after") or 0.0)
        except (TypeError, ValueError):
            return True
        return retry_after <= 0 or epoch_seconds() >= retry_after

    def _begin_summary(self, counter_key: str) -> bool:
        """占位：同一会话同时只允许一次总结(无 await，检查与占位是原子的)。"""
        if counter_key in self._active_summaries:
            return False
        self._active_summaries.add(counter_key)
        return True

    def _end_summary(self, counter_key: str) -> None:
        self._active_summaries.discard(counter_key)

    @staticmethod
    def _backoff_seconds(failures: int) -> float:
        """连续失败次数 → 冷却秒数(指数退避,带上限)。"""
        doublings = min(max(int(failures) - 1, 0), RETRY_BACKOFF_MAX_DOUBLINGS)
        return min(
            RETRY_BACKOFF_BASE_SECONDS * (2**doublings), RETRY_BACKOFF_MAX_SECONDS
        )

    async def _commit_success(self, counter_key: str, *, snapshot_count: int) -> None:
        """总结成功后清账：只移除已总结的消息，保留总结期间新到的消息。

        计数器读路径带 30 秒缓存，这里必须回库读最新状态。用 count 差值而不是
        消息下标计算新到条数：总结期间消息会因 interval 截断把最早的挤掉，
        下标会错位；count 每条消息恰好 +1，差值就是新到条数（截断只影响队列）。
        """
        async with self._counter_lock(counter_key):
            state = await self._load_counter(counter_key)
            messages = list(state.get("messages", []))
            count = int(state.get("count", 0) or 0)
            arrivals = max(0, count - int(snapshot_count))
            kept = messages[-arrivals:] if arrivals else []
            # count 语义 = 缓冲中尚未总结的消息条数：下一次攒满 interval 才总结，
            # 总量与旧行为一致，但不再丢掉总结期间到的那几条。
            await self._save_counter(
                counter_key, {"count": len(kept), "messages": kept}
            )

    async def _defer_after_failure(self, counter_key: str) -> int:
        """总结失败后保留待总结消息,并写入指数退避冷却。

        没有冷却时，计数器一旦越过阈值且总结持续失败，每条新消息都会重跑
        一整轮工具调用循环，把「失败重试」放大成按消息计费的 token 风暴。
        整个读-改-写必须在计数器锁内完成：否则会把总结期间新到消息的追加
        用旧快照覆盖掉（失败路径只允许合并冷却字段，不得改写 count/messages）。
        """
        try:
            async with self._counter_lock(counter_key):
                state = await self._load_counter(counter_key)
                failures = int(state.get("failures", 0) or 0) + 1
                await self._save_counter(
                    counter_key,
                    self._counter_state(
                        count=int(state.get("count", 0) or 0),
                        messages=list(state.get("messages", [])),
                        failures=failures,
                        retry_after=epoch_seconds() + self._backoff_seconds(failures),
                    ),
                )
                return failures
        except Exception:
            return 0

    def _interval_for(self, conversation_kind: str) -> int:
        trigger = getattr(getattr(self._config, "agent", None), "memory", None)
        trigger = getattr(trigger, "trigger", None)
        value = (
            getattr(trigger, "group_interval", 0)
            if conversation_kind == "group"
            else getattr(trigger, "private_interval", 0)
        )
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _counter_key(conversation_kind: str, conversation_id: str) -> str:
        return f"{conversation_kind}:{conversation_id}"
