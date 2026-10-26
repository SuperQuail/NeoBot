"""面板手动 / 批量压缩：目标校验、后台任务启动与逐条串行执行。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_app.time_context import epoch_seconds

from .constants import (
    MANUAL_TARGET_FALLBACK_MAX_CHARS,
    MAX_BATCH_COMPRESS_ITEMS,
    MIN_MANUAL_TARGET_CHARS,
)
from .helpers import _tunable


class ManualCompressionMixin:
    """面板发起的单条 / 批量 AI 压缩入口。"""

    # ── 面板手动 / 批量压缩（spec(4) Part C / §4.10.1–§4.10.4）──

    def manual_target_bounds(self) -> tuple[int, int]:
        """手动压缩目标的 ``(下限, 上限)``。

        下限固定 ``MIN_MANUAL_TARGET_CHARS``；上限取全局 ``max_total_chars``，
        为 0（容量治理关闭）时取兜底常量（A44：此时手动压缩仍可用）。
        """
        upper = self._overflow_max_total_chars
        if upper <= 0:
            upper = MANUAL_TARGET_FALLBACK_MAX_CHARS
        return MIN_MANUAL_TARGET_CHARS, int(upper)

    def normalize_manual_target(self, target_chars: Any) -> int:
        """校验并归一化手动压缩目标；非法值抛 ``ValueError``（面板据此 400）。"""
        lower, upper = self.manual_target_bounds()
        try:
            target = int(target_chars)
        except (TypeError, ValueError):
            raise ValueError(f"目标字符数必须是整数（{lower}–{upper}）") from None
        if target < lower:
            raise ValueError(f"目标字符数不能小于 {lower}（低于此值必然丢关键事实）")
        if target > upper:
            raise ValueError(
                f"目标字符数不能大于 {upper}（当前单条档案存储上限；"
                "手动压缩不改写全局配置）"
            )
        return target

    async def start_manual_compression(
        self,
        table_name: str,
        key: str,
        *,
        target_chars: Any,
        operator_ip: str = "",
    ) -> dict[str, Any]:
        """面板「AI 压缩」入口：校验目标 → 判 no-op → 起后台任务并立即返回状态。

        单飞键与自动压缩**共用** ``overflow:{table}:{key}``（D16）：
        同一 (table, key) 已经有一个压缩在跑时不再排第二个模型循环，
        而是如实回「进行中」。
        """
        table_name = str(table_name or "").strip()
        key = str(key or "").strip()
        if not table_name or not key:
            raise ValueError("缺少 table / key")
        target = self.normalize_manual_target(target_chars)

        running = self._find_running_manual_task(table_name, key)
        if running is not None:
            return self._task_payload(running, message="该档案正在压缩中，请稍后查看结果")

        item = await self._archive.get(table_name, key)
        if item is None:
            raise ValueError(f"没有该档案: {table_name}:{key}")
        current = len(item.value or "")
        if current <= target:
            # A32：目标不小于当前字数 → 零 token no-op，绝不调用模型。
            return {
                "ok": True,
                "status": "noop",
                "task_id": None,
                "kind": "single",
                "table": table_name,
                "key": key,
                "target_chars": target,
                "chars_before": current,
                "chars_after": current,
                "snapshot_id": None,
                "error": "",
                "operator_ip": str(operator_ip or ""),
                "noop": True,
                "message": (
                    f"当前 {current} 字已不大于目标 {target} 字，无需压缩（未调用模型）"
                ),
            }
        if self._provider is None:
            raise RuntimeError("档案总结模型不可用（未装配 archive_summary provider），无法压缩")

        task = self._new_manual_task(table_name, key, target, operator_ip)
        task["chars_before"] = current
        task_key = self._overflow_task_key(table_name, key)
        if not self._begin_summary(task_key):
            # 预检之后自动压缩刚好启动：撤回本任务，如实回「进行中」（D16 / A40）。
            self._manual_tasks.pop(str(task["task_id"]), None)
            return {
                "ok": True,
                "status": "running",
                "task_id": None,
                "kind": "single",
                "table": table_name,
                "key": key,
                "target_chars": target,
                "chars_before": current,
                "chars_after": None,
                "snapshot_id": None,
                "error": "",
                "operator_ip": str(operator_ip or ""),
                "message": "该档案正在压缩中（自动或手动），本次未重复触发",
            }
        try:
            pending = asyncio.create_task(
                self._run_compression_job(
                    table_name,
                    key,
                    task_key,
                    target_chars=target,
                    source="manual",
                    operator_ip=str(operator_ip or ""),
                    task_state=task,
                )
            )
        except RuntimeError as exc:
            self._end_summary(task_key)
            self._manual_tasks.pop(str(task["task_id"]), None)
            raise RuntimeError(f"无法调度压缩任务（没有运行中的事件循环）: {exc}") from exc
        self._overflow_tasks.add(pending)
        pending.add_done_callback(self._overflow_tasks.discard)
        self._logger.info(
            "面板触发档案压缩",
            table_name=table_name,
            key=key,
            target_chars=target,
            chars_before=current,
            operator_ip=str(operator_ip or ""),
            task_id=task["task_id"],
        )
        return self._task_payload(
            task,
            message=f"已开始压缩（{current} → 目标 {target} 字）",
        )

    async def start_batch_compression(
        self,
        *,
        target_chars: Any,
        operator_ip: str = "",
        table_name: str | None = None,
    ) -> dict[str, Any]:
        """面板「批量压缩超限档案」入口：一次最多 MAX_BATCH_COMPRESS_ITEMS 条，**逐条串行**。

        统一一个目标；只对 ``chars > target`` 的条目执行，其余标 ``skipped``。
        返回被截断条数与 skipped 明细（A45 / §4.10.1）。
        """
        target = self.normalize_manual_target(target_chars)
        if self._provider is None:
            raise RuntimeError("档案总结模型不可用（未装配 archive_summary provider），无法压缩")
        scope = str(table_name or "").strip() or None
        rows = await self._archive.list_over_limit(
            scope, limit=_tunable("MAX_BATCH_COMPRESS_ITEMS", MAX_BATCH_COMPRESS_ITEMS)
        )
        total_over = await self._archive.count_over_limit(scope)
        truncated = max(0, int(total_over or 0) - len(rows or []))

        task = self._new_manual_task(scope or "", "", target, operator_ip, kind="batch")
        items: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        selected_chars = 0
        for row in rows or []:
            row_table = str(row.get("table_name") or "")
            row_key = str(row.get("key") or "")
            chars = int(row.get("chars") or 0)
            entry: dict[str, Any] = {
                "table": row_table,
                "key": row_key,
                "chars_before": chars,
                "chars_after": None,
                "status": "pending",
                "error": "",
                "snapshot_id": None,
            }
            if chars <= target:
                entry["status"] = "skipped"
                entry["error"] = f"当前 {chars} 字不大于目标 {target} 字"
                skipped.append({"table": row_table, "key": row_key, "reason": entry["error"]})
            else:
                selected_chars += chars
            items.append(entry)
        task["items"] = items
        task["skipped"] = skipped
        task["truncated"] = truncated
        task["chars_before"] = selected_chars
        pending_items = [entry for entry in items if entry["status"] == "pending"]
        if not pending_items:
            task["status"] = "done"
            task["finished_at"] = epoch_seconds()
            task["message"] = (
                f"没有需要压缩的条目（超限 {len(items)} 条，全部不大于目标 {target} 字）"
            )
            return self._task_payload(task)

        try:
            pending = asyncio.create_task(
                self._run_batch_compression(task, target_chars=target, operator_ip=operator_ip)
            )
        except RuntimeError as exc:
            self._manual_tasks.pop(str(task["task_id"]), None)
            raise RuntimeError(f"无法调度批量压缩任务（没有运行中的事件循环）: {exc}") from exc
        self._overflow_tasks.add(pending)
        pending.add_done_callback(self._overflow_tasks.discard)
        self._logger.info(
            "面板触发批量档案压缩",
            target_chars=target,
            count=len(pending_items),
            truncated=truncated,
            operator_ip=str(operator_ip or ""),
            task_id=task["task_id"],
        )
        return self._task_payload(
            task,
            message=(f"已开始逐条压缩 {len(pending_items)} 条超限档案（目标 {target} 字）"),
        )

    async def _run_batch_compression(
        self, task: dict[str, Any], *, target_chars: int, operator_ip: str
    ) -> None:
        """批量压缩主循环：**逐条串行**（任意时刻至多 1 条在跑，A45）。"""
        succeeded = 0
        failed = 0
        try:
            for entry in list(task.get("items") or []):
                if entry.get("status") != "pending":
                    continue
                row_table = str(entry.get("table") or "")
                row_key = str(entry.get("key") or "")
                task_key = self._overflow_task_key(row_table, row_key)
                if not self._begin_summary(task_key):
                    # 同一条正在被自动 / 其它手动任务压缩：跳过而不是排队。
                    entry["status"] = "skipped"
                    entry["error"] = "该档案正在压缩中"
                    task.setdefault("skipped", []).append(
                        {"table": row_table, "key": row_key, "reason": entry["error"]}
                    )
                    continue
                # 面板据此禁用同一条档案的编辑 / 删除（R18 / §4.10.1）。
                entry["status"] = "running"
                state: dict[str, Any] = {}
                try:
                    ok = await self.compress_archive(
                        row_table,
                        row_key,
                        target_chars=target_chars,
                        source="manual",
                        operator_ip=operator_ip,
                        state=state,
                    )
                except Exception as exc:
                    ok = False
                    error = str(exc) or type(exc).__name__
                    state["error"] = error
                    self._record_overflow_failure(task_key)
                    self._clear_overflow_cooldown(row_table, row_key)
                    self._logger.warning(
                        "批量压缩单条失败，保留原内容",
                        table_name=row_table,
                        key=row_key,
                        error=error,
                    )
                finally:
                    self._end_summary(task_key)
                entry["chars_before"] = int(
                    state.get("chars_before") or entry.get("chars_before") or 0
                )
                if state.get("chars_after") is not None:
                    entry["chars_after"] = int(state["chars_after"])
                entry["snapshot_id"] = state.get("snapshot_id")
                entry["error"] = "" if ok else str(state.get("error") or "压缩失败")
                entry["status"] = "done" if ok else "failed"
                succeeded += 1 if ok else 0
                failed += 0 if ok else 1
        except Exception as exc:  # 兜底：批量任务自身异常不影响已完成的条目
            task["error"] = str(exc) or type(exc).__name__
            self._logger.warning("批量档案压缩异常中止", error=task["error"])
        finally:
            done_items = [
                entry for entry in task.get("items") or [] if entry.get("status") == "done"
            ]
            task["chars_after"] = sum(
                int(entry.get("chars_after") or 0) for entry in done_items
            )
            task["snapshot_id"] = None
            task["status"] = "failed" if failed else "done"
            task["finished_at"] = epoch_seconds()
            task["message"] = (
                f"批量压缩完成：成功 {succeeded} 条，失败 {failed} 条，"
                f"跳过 {len(task.get('skipped') or [])} 条"
            )
