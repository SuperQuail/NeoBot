"""面板压缩任务状态表：进程内 FIFO、TTL 清理与响应体投影。"""

from __future__ import annotations

from typing import Any

from neobot_app.time_context import epoch_seconds, epoch_seconds_int

from .constants import MANUAL_TASK_TTL_SECONDS, MAX_MANUAL_TASKS


class ManualTaskMixin:
    """手动 / 批量压缩的进程内状态表（重启即清空）。"""

    def get_manual_task(self, task_id: str) -> dict[str, Any] | None:
        """按 task_id 取手动 / 批量压缩状态（顺手清理过期与超量记录）。"""
        self._prune_manual_tasks()
        task = self._manual_tasks.get(str(task_id or "").strip())
        if task is None:
            return None
        return self._task_payload(task)

    def _new_manual_task(
        self,
        table_name: str,
        key: str,
        target_chars: int,
        operator_ip: str,
        *,
        kind: str = "single",
    ) -> dict[str, Any]:
        """登记一条手动压缩任务（FIFO 上限 MAX_MANUAL_TASKS）。"""
        self._prune_manual_tasks()
        self._manual_task_seq += 1
        task_id = f"{epoch_seconds_int()}-{self._manual_task_seq}"
        task: dict[str, Any] = {
            "task_id": task_id,
            "kind": kind,
            "table": str(table_name or ""),
            "key": str(key or ""),
            "target_chars": int(target_chars),
            "status": "running",
            "chars_before": 0,
            "chars_after": None,
            "error": "",
            "operator_ip": str(operator_ip or ""),
            "started_at": epoch_seconds(),
            "finished_at": None,
            "snapshot_id": None,
            "message": "",
        }
        if kind == "batch":
            task["items"] = []
            task["skipped"] = []
            task["truncated"] = 0
        self._manual_tasks[task_id] = task
        self._prune_manual_tasks()
        return task

    def _find_running_manual_task(self, table_name: str, key: str) -> dict[str, Any] | None:
        """同一 (table, key) 是否已有在跑的手动压缩（面板去重提示）。"""
        self._prune_manual_tasks()
        for task in self._manual_tasks.values():
            if task.get("status") != "running":
                continue
            if str(task.get("table") or "") == table_name and str(task.get("key") or "") == key:
                return task
        return None

    def _prune_manual_tasks(self) -> None:
        """清理已结束且超过 30 分钟的记录，并按 FIFO 只保留最近 MAX_MANUAL_TASKS 条。

        只清理**已结束**的记录：正在跑的任务永远不淘汰（否则面板轮询会丢状态）。
        """
        now = epoch_seconds()
        for task_id, task in list(self._manual_tasks.items()):
            if task.get("status") == "running":
                continue
            finished = task.get("finished_at")
            if finished and now - float(finished) > MANUAL_TASK_TTL_SECONDS:
                self._manual_tasks.pop(task_id, None)
        if len(self._manual_tasks) <= MAX_MANUAL_TASKS:
            return
        for task_id, task in list(self._manual_tasks.items()):
            if len(self._manual_tasks) <= MAX_MANUAL_TASKS:
                break
            if task.get("status") == "running":
                continue
            self._manual_tasks.pop(task_id, None)

    def _finalize_manual_task(
        self,
        task: dict[str, Any] | None,
        *,
        status: str,
        error: str,
        state: dict[str, Any] | None = None,
    ) -> None:
        """压缩结束后回填状态表（成功 / 失败都在这里收口）。"""
        if not isinstance(task, dict):
            return
        state = state or {}
        if state.get("chars_before") is not None:
            task["chars_before"] = int(state["chars_before"])
        if state.get("chars_after") is not None:
            task["chars_after"] = int(state["chars_after"])
        task["snapshot_id"] = state.get("snapshot_id")
        task["status"] = status
        task["error"] = str(error or "")
        task["finished_at"] = epoch_seconds()
        if status == "done":
            task["message"] = (
                f"{task.get('chars_before', 0)} → {task.get('chars_after', 0)} 字"
                f"（目标 {task.get('target_chars', 0)}）"
            )
        else:
            task["message"] = str(error or "压缩失败，已保留原文")

    @staticmethod
    def _task_payload(task: dict[str, Any], *, message: str | None = None) -> dict[str, Any]:
        """把内部任务字典投影成面板 / 测试可直接消费的响应体。"""
        def _int_or_none(value: Any) -> int | None:
            return None if value is None else int(value)

        payload: dict[str, Any] = {
            "ok": True,
            "task_id": task.get("task_id"),
            "kind": str(task.get("kind") or "single"),
            "status": str(task.get("status") or "running"),
            "table": str(task.get("table") or ""),
            "key": str(task.get("key") or ""),
            "target_chars": int(task.get("target_chars") or 0),
            "chars_before": int(task.get("chars_before") or 0),
            "chars_after": _int_or_none(task.get("chars_after")),
            "snapshot_id": _int_or_none(task.get("snapshot_id")),
            "error": str(task.get("error") or ""),
            "operator_ip": str(task.get("operator_ip") or ""),
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "message": message if message is not None else str(task.get("message") or ""),
        }
        if "items" in task:
            payload["items"] = [dict(item) for item in task.get("items") or []]
            payload["skipped"] = [dict(item) for item in task.get("skipped") or []]
            payload["truncated"] = int(task.get("truncated") or 0)
            payload["succeeded"] = sum(
                1 for item in task.get("items") or [] if item.get("status") == "done"
            )
            payload["failed"] = sum(
                1 for item in task.get("items") or [] if item.get("status") == "failed"
            )
        return payload
