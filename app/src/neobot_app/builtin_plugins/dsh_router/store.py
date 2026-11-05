"""任务记录存储：``plugins_data/dsh_router/tasks.json`` 的原子读写。

磁盘格式::

    {"version": 1, "tasks": [ {task_id, pipeline_key, ...}, ... ]}

约定：

- 只做「读改写一份 JSON」，不做查询优化 —— 单机 daemon 场景任务量在个位数；
- 写入走「临时文件 + ``os.replace``」，进程被杀不会留下半份文件；
- 文件损坏/字段缺失按「空存储 / 该条跳过」处理并告警，绝不因存储问题让插件加载失败。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

#: 磁盘格式版本；不兼容变更必须 +1。
STORE_VERSION = 1

#: 未结束状态（计入 max_tasks_per_chat 与「有无活跃任务」判断）。
ACTIVE_STATUSES = frozenset({"dispatched", "running", "cancelling"})

#: 已结束状态。
TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled", "stale"})


@dataclass(slots=True)
class TaskRecord:
    """一条被派发的 DSH 任务；字段全部可 JSON 序列化。"""

    task_id: str
    pipeline_key: str
    owner_user_id: int | None = None
    cwd: str = ""
    mode: str = "write"
    prompt: str = ""
    status: str = "dispatched"
    created_at: float = 0.0
    updated_at: float = 0.0
    last_event_at: float = 0.0
    summary: str = ""
    worker_session_id: str = ""
    artifacts: list[str] = field(default_factory=list)
    last_notice_at: float = 0.0
    pending_permission: dict[str, Any] | None = None

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "pipeline_key": self.pipeline_key,
            "owner_user_id": self.owner_user_id,
            "cwd": self.cwd,
            "mode": self.mode,
            "prompt": self.prompt,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_event_at": self.last_event_at,
            "summary": self.summary,
            "worker_session_id": self.worker_session_id,
            "artifacts": list(self.artifacts),
            "last_notice_at": self.last_notice_at,
            "pending_permission": dict(self.pending_permission) if self.pending_permission else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TaskRecord | None:
        try:
            task_id = str(payload.get("task_id") or "").strip()
            pipeline_key = str(payload.get("pipeline_key") or "").strip()
            if not task_id or not pipeline_key:
                return None
            owner = payload.get("owner_user_id")
            permission = payload.get("pending_permission")
            artifacts = payload.get("artifacts") or []
            return cls(
                task_id=task_id,
                pipeline_key=pipeline_key,
                owner_user_id=int(owner) if owner is not None else None,
                cwd=str(payload.get("cwd") or ""),
                mode=str(payload.get("mode") or "write"),
                prompt=str(payload.get("prompt") or ""),
                status=str(payload.get("status") or "dispatched"),
                created_at=float(payload.get("created_at") or 0.0),
                updated_at=float(payload.get("updated_at") or 0.0),
                last_event_at=float(payload.get("last_event_at") or 0.0),
                summary=str(payload.get("summary") or ""),
                worker_session_id=str(payload.get("worker_session_id") or ""),
                artifacts=[str(item) for item in artifacts] if isinstance(artifacts, list) else [],
                last_notice_at=float(payload.get("last_notice_at") or 0.0),
                pending_permission=dict(permission) if isinstance(permission, dict) else None,
            )
        except (TypeError, ValueError):
            return None


class TaskStore:
    """单文件任务表；所有公开方法都在进程内串行执行。"""

    def __init__(self, path: Path, *, logger: Logger | None = None) -> None:
        self.path = Path(path)
        self._logger = logger or NullLogger()
        self._lock = RLock()
        self._tasks: dict[str, TaskRecord] = {}
        self._loaded = False

    # ── 读写 ────────────────────────────────────────────────────

    def load(self, *, force: bool = False) -> None:
        with self._lock:
            if self._loaded and not force:
                return
            self._tasks = {}
            self._loaded = True
            if not self.path.is_file():
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._logger.warning(f"任务存储读取失败，已按空存储处理: {self.path}: {exc}")
                return
            raw = payload.get("tasks") if isinstance(payload, dict) else None
            if not isinstance(raw, list):
                self._logger.warning(f"任务存储格式异常，已按空存储处理: {self.path}")
                return
            for item in raw:
                if not isinstance(item, dict):
                    continue
                record = TaskRecord.from_dict(item)
                if record is None:
                    continue
                self._tasks[record.task_id] = record

    def save(self) -> None:
        with self._lock:
            self.load()
            payload = {
                "version": STORE_VERSION,
                "tasks": [record.to_dict() for record in self._tasks.values()],
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".tasks-", suffix=".tmp")
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                        handle.write(text)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temp_name, self.path)
                except BaseException:
                    try:
                        os.unlink(temp_name)
                    except OSError:
                        pass
                    raise
            except Exception as exc:
                self._logger.warning(f"任务存储写入失败: {self.path}: {exc}")

    # ── 查询 ────────────────────────────────────────────────────

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            self.load()
            return self._tasks.get(str(task_id or "").strip())

    def list(self, pipeline_key: str | None = None) -> list[TaskRecord]:
        """按 created_at 升序列出；给定 pipeline_key 时只列该聊天流。"""
        with self._lock:
            self.load()
            records = list(self._tasks.values())
        if pipeline_key is not None:
            key = str(pipeline_key or "").strip()
            records = [record for record in records if record.pipeline_key == key]
        return sorted(records, key=lambda item: (item.created_at, item.task_id))

    def active(self, pipeline_key: str) -> list[TaskRecord]:
        return [record for record in self.list(pipeline_key) if record.active]

    # ── 写入 ────────────────────────────────────────────────────

    def create(self, record: TaskRecord) -> TaskRecord:
        with self._lock:
            self.load()
            now = time.time()
            if not record.created_at:
                record.created_at = now
            if not record.updated_at:
                record.updated_at = record.created_at
            self._tasks[record.task_id] = record
            self.save()
            return record

    def update(self, task_id: str, **fields: Any) -> TaskRecord | None:
        """按字段更新并落盘；未知字段忽略，任务不存在返回 None。"""
        with self._lock:
            self.load()
            record = self._tasks.get(str(task_id or "").strip())
            if record is None:
                return None
            for name, value in fields.items():
                if hasattr(record, name):
                    setattr(record, name, value)
            record.updated_at = float(fields.get("updated_at") or time.time())
            self.save()
            return record

    def all(self) -> list[TaskRecord]:
        return self.list()


__all__ = [
    "ACTIVE_STATUSES",
    "STORE_VERSION",
    "TERMINAL_STATUSES",
    "TaskRecord",
    "TaskStore",
]
