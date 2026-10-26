"""档案超限的后台压缩任务：触发调度、压缩落库、失败退避与单飞占位。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_app.time_context import epoch_seconds

from .constants import AUTO_COMPRESSION_TARGET_CHARS, MAX_OVERFLOW_BACKOFF_ENTRIES
from .helpers import _compression_usage_kind, _positive_int_or_zero


class OverflowJobMixin:
    """写路径超限触发的压缩任务（先写后压缩）。"""

    async def wait_pending_overflow_tasks(self, timeout: float = 30.0) -> None:
        """等待所有在途的「档案超限」压缩任务结束（测试与关闭路径使用）。"""
        pending = [task for task in self._overflow_tasks if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    # ── 档案超限 → 后台压缩（spec(1)）──

    def _schedule_overflow_compression(self, table_name: str, key: str) -> bool:
        """档案超限触发入口：由 ArchiveMemoryService 在写路径同步调用。

        只做「要不要调度」的判定并立刻返回；真正的压缩在后台任务里跑。这是「先写后
        压缩」的关键：写入工具不会被一次完整的模型调用拖住（max_summary_seconds 量级）。
        单飞复用总结的 _active_summaries 占位（同一 (table_name, key) 同时只跑一个）。
        """
        if self._overflow_max_total_chars <= 0:
            return False
        task_key = self._overflow_task_key(table_name, key)
        if self._provider is None:
            # D3 选项一：AI 不可用时保留原内容、不截断，等下次写入再试。
            self._logger.warning(
                "档案超过存储上限但总结模型不可用，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
            )
            return False
        if not self._overflow_retry_ready(task_key):
            self._logger.debug(
                "档案超限压缩处于失败冷却中，跳过本次触发",
                table_name=table_name,
                key=key,
                retry_after=self._overflow_retry_after.get(task_key),
            )
            return False
        if not self._begin_summary(task_key):
            self._logger.debug(
                "档案超限压缩已在执行，跳过本次触发",
                table_name=table_name,
                key=key,
            )
            return False
        # 自动压缩目标 ≤ 存储上限：上限 15000 时压到 10000，留出 5000 字余量。
        target_chars = min(
            self._overflow_max_total_chars, AUTO_COMPRESSION_TARGET_CHARS
        )
        try:
            task = asyncio.create_task(
                self._run_compression_job(
                    table_name,
                    key,
                    task_key,
                    target_chars=target_chars,
                    source="auto",
                )
            )
        except RuntimeError as exc:
            self._end_summary(task_key)
            self._logger.warning(
                "档案超限压缩无法调度（没有运行中的事件循环）",
                table_name=table_name,
                key=key,
                error=str(exc),
            )
            return False
        self._overflow_tasks.add(task)
        task.add_done_callback(self._overflow_tasks.discard)
        self._logger.info(
            "档案超过存储上限，已调度后台压缩",
            table_name=table_name,
            key=key,
        )
        return True

    async def _run_compression_job(
        self,
        table_name: str,
        key: str,
        task_key: str,
        *,
        target_chars: int,
        source: str,
        operator_ip: str | None = None,
        task_state: dict[str, Any] | None = None,
    ) -> bool:
        """后台压缩任务入口：异常一律转成「保留原文 + 失败退避」，绝不影响写入方。

        自动路径（写超限）与手动路径（面板）共用本入口：差别只有 target_chars /
        source，以及手动路径会回填 ``task_state``（面板状态表）。单飞键由调用方
        ``_begin_summary`` 持有，这里只负责 ``_end_summary`` 释放。
        """
        state: dict[str, Any] = {}
        try:
            ok = await self.compress_archive(
                table_name,
                key,
                target_chars=target_chars,
                source=source,
                operator_ip=operator_ip,
                state=state,
            )
        except Exception as exc:
            failures = self._record_overflow_failure(task_key)
            # 异常同样算失败：清掉服务侧冷却，重试节奏交给这里的失败退避，
            # 否则一次异常会把「下次写入再试」压成 600 秒的静默。
            self._clear_overflow_cooldown(table_name, key)
            error = str(exc) or type(exc).__name__
            self._logger.warning(
                "档案超限压缩失败，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
                source=source,
                error=error,
                consecutive_failures=failures,
            )
            self._finalize_manual_task(task_state, status="failed", error=error, state=state)
            return False
        finally:
            self._end_summary(task_key)
        if task_state is not None:
            self._finalize_manual_task(
                task_state,
                status="done" if ok else "failed",
                error="" if ok else str(state.get("error") or "压缩未达到目标"),
                state=state,
            )
        return ok

    async def compress_archive(
        self,
        table_name: str,
        key: str,
        *,
        target_chars: int,
        source: str,
        operator_ip: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> bool:
        """对单条档案跑一轮「压缩」工具循环，并把结果落库。

        ``target_chars`` 是**本次压缩**的目标，不再直接读全局字段（spec(4) §4.10.3）：
        自动路径传 min(max_total_chars, 10000)（source="auto"），手动路径传
        面板输入（source="manual"）。复用总结的预算与保护：max_tool_rounds /
        max_summary_seconds / 单次调用超时 / 用量统计 / 工具连续失败熔断 / 失败指数退避。

        可选的 ``state`` 是调用方的出参字典，回填 chars_before / chars_after /
        snapshot_id / error，供面板状态表使用（保持本方法返回 bool）。
        """
        limit = _positive_int_or_zero(target_chars)
        if limit <= 0:
            return True
        item = await self._archive.get(table_name, key)
        value = (item.value or "") if item is not None else ""
        if not value:
            return False
        chars_before = len(value)
        if state is not None:
            state["chars_before"] = chars_before
        if chars_before <= limit:
            # 已被别的路径压缩过（例如同一批写入共享一次压缩），无需再跑模型。
            if state is not None:
                state["chars_after"] = chars_before
            return True

        # 压缩**开始前**留痕：此刻的原文就是快照内容（D15）。失败 / 未达标时删除。
        snapshot_id = await self._save_compression_snapshot(
            table_name,
            key,
            value=value,
            item=item,
            source=source,
            operator_ip=operator_ip,
        )
        if state is not None:
            state["snapshot_id"] = snapshot_id

        # 自动压缩：hard_limit 用存储硬上限（可能大于本次目标，例如 15000 上限压到
        # 10000），target_chars 才是本次必须达到的目标；手动压缩的 target 本身就是
        # 运维要求的硬目标，hard_limit 与目标一致。
        hard_limit = (
            self._overflow_max_total_chars or limit if source == "auto" else limit
        )
        prompt = self._build_overflow_compression_prompt(
            table_name=table_name,
            key=key,
            value=value,
            limit=hard_limit,
            trigger=source,
            target_chars=limit,
        )
        try:
            tool_successes, tool_failures = await self._run_overflow_tool_loop(
                prompt,
                table_name=table_name,
                key=key,
                usage_kind=_compression_usage_kind(source),
            )
        except Exception:
            # 工具循环异常中止：模型可能已经写了一半，先回滚原文再抛给上层记失败。
            restored = await self._restore_compression_original(table_name, key, value)
            if restored:
                await self._drop_compression_snapshot(snapshot_id)
            if state is not None:
                state["snapshot_id"] = None if restored else snapshot_id
            raise

        after = await self._archive.get(table_name, key)
        remaining = len((after.value if after is not None else "") or "")
        if state is not None:
            state["chars_after"] = remaining
        task_key = self._overflow_task_key(table_name, key)
        if remaining > limit:
            # 工具循环可能只读不写、或 save 被判定失败：给一次不依赖工具的直写兜底。
            if await self._direct_rewrite_without_tools(table_name, key, value, limit):
                after = await self._archive.get(table_name, key)
                remaining = len((after.value if after is not None else "") or "")
                if state is not None:
                    state["chars_after"] = remaining
                tool_successes = max(tool_successes, 1)
        if remaining > limit:
            failures = self._record_overflow_failure(task_key)
            # 压缩没成功 → 清掉服务侧冷却，让「下次写入再试」不被 600 秒冷却掩盖；
            # 真正的重试节奏由这里的失败退避控制。
            self._clear_overflow_cooldown(table_name, key)
            error = (
                f"压缩未达到目标（{remaining} 字 > 目标 {limit} 字）"
                if tool_successes > 0
                else "压缩没有产生有效写入，已保留原文"
            )
            # 失败 / 未达标 → 回滚原文（R19「宁可不压，不静默丢数据」）。
            # 回滚走 set_if_version（面板路径），因此**不会**再次触发自动压缩；
            # 只有确认「库内内容已等于原文」时才删除本次快照，避免回滚失败时丢失唯一副本。
            restored = await self._restore_compression_original(table_name, key, value)
            if restored:
                await self._drop_compression_snapshot(snapshot_id)
            if state is not None:
                state["error"] = error
                state["snapshot_id"] = None if restored else snapshot_id
                if restored:
                    state["chars_after"] = chars_before
            remaining = chars_before if restored else remaining
            self._logger.warning(
                "档案超限压缩未压到上限内，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
                source=source,
                chars_before=chars_before,
                chars_after=remaining,
                target_chars=limit,
                max_total_chars=self._overflow_max_total_chars,
                tool_calls_succeeded=tool_successes,
                tool_failures=tool_failures,
                consecutive_failures=failures,
            )
            return False

        self._overflow_failures.pop(task_key, None)
        self._overflow_retry_after.pop(task_key, None)
        self._logger.info(
            "档案超限压缩完成",
            table_name=table_name,
            key=key,
            source=source,
            chars_before=chars_before,
            chars_after=remaining,
            target_chars=limit,
            snapshot_id=snapshot_id,
        )
        return True

    @staticmethod
    def _overflow_task_key(table_name: str, key: str) -> str:
        return f"overflow:{table_name}:{key}"

    def _overflow_retry_ready(self, task_key: str) -> bool:
        retry_after = self._overflow_retry_after.get(task_key, 0.0)
        return retry_after <= 0.0 or epoch_seconds() >= retry_after

    def _record_overflow_failure(self, task_key: str) -> int:
        """记录一次压缩失败并写入指数退避（复用计数器的退避算法）。"""
        failures = int(self._overflow_failures.get(task_key, 0)) + 1
        self._overflow_failures[task_key] = failures
        self._overflow_retry_after[task_key] = epoch_seconds() + self._backoff_seconds(failures)
        self._prune_overflow_backoff()
        return failures

    def _prune_overflow_backoff(self) -> None:
        """退避表只保留未过期条目，避免长期运行后无界增长。"""
        if len(self._overflow_retry_after) <= MAX_OVERFLOW_BACKOFF_ENTRIES:
            return
        now = epoch_seconds()
        for task_key, retry_after in list(self._overflow_retry_after.items()):
            if retry_after <= now:
                self._overflow_retry_after.pop(task_key, None)
                self._overflow_failures.pop(task_key, None)

    def _clear_overflow_cooldown(self, table_name: str, key: str) -> None:
        """压缩失败后清除服务侧冷却，让下次写入能立刻再试。"""
        clearer = getattr(self._archive, "clear_overflow_cooldown", None)
        if callable(clearer):
            try:
                clearer(table_name, key)
            except Exception:
                return
