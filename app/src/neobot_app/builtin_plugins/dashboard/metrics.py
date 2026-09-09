"""面板运行指标：消息统计、活跃用户、延迟、API 调用、日志缓冲。

所有数据都来自运行时事件（插件订阅 hook_bus），不依赖日志文本之外的内部实现，
重启后从 data_dir/stats.json 恢复累计消息数与历史。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

_API_ACTION_RE = re.compile(r"action['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_]+)")


class Metrics:
    """面板运行指标聚合器。"""

    def __init__(
        self,
        *,
        data_dir: Path,
        history_max_days: int = 30,
        log_buffer_size: int = 500,
        latency_samples: int = 60,
        user_capacity: int = 200,
        logger: Logger | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._stats_path = self._data_dir / "stats.json"
        self._logger = logger or NullLogger()
        self._history_max_days = max(1, int(history_max_days))
        self._log_buffer: deque[dict[str, Any]] = deque(maxlen=max(1, int(log_buffer_size)))
        self._log_seq = 0
        self._latency: deque[tuple[float, float | None]] = deque(maxlen=max(2, int(latency_samples)))
        self._latency_ok = 0
        self._latency_total = 0
        self._api_calls: dict[str, int] = {}
        self._user_activity: dict[int, dict[str, Any]] = {}
        self._user_capacity = max(1, int(user_capacity))
        self._stats: dict[str, Any] = {
            "total": 0,
            "today": 0,
            "today_date": "",
            "history": [],
            "started_at": time.time(),
        }
        self._lock = asyncio.Lock()
        self._load()

    # ------------------------------------------------------------------
    # 消息统计
    # ------------------------------------------------------------------

    def _roll_date(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._stats.get("today_date") == today:
            return
        previous_date = str(self._stats.get("today_date") or "")
        previous_count = int(self._stats.get("today") or 0)
        if previous_date and previous_count > 0:
            history = self._stats.setdefault("history", [])
            if not history or history[-1].get("date") != previous_date:
                history.append({"date": previous_date, "count": previous_count})
            self._stats["history"] = history[-self._history_max_days :]
        self._stats["today_date"] = today
        self._stats["today"] = 0

    async def record_message(self, event: dict[str, Any]) -> None:
        async with self._lock:
            self._roll_date()
            self._stats["total"] = int(self._stats.get("total") or 0) + 1
            self._stats["today"] = int(self._stats.get("today") or 0) + 1
            total = self._stats["total"]
            if total % 20 == 0:
                self._save()

            user_id = event.get("user_id")
            if isinstance(user_id, int) and user_id > 0:
                sender = event.get("sender") or {}
                nickname = str(
                    sender.get("card") or sender.get("nickname") or ""
                ).strip()
                record = self._user_activity.get(user_id)
                now = time.time()
                if record is None:
                    if len(self._user_activity) >= self._user_capacity:
                        oldest_id = min(
                            self._user_activity.items(),
                            key=lambda item: item[1].get("last_seen", 0),
                        )[0]
                        self._user_activity.pop(oldest_id, None)
                    self._user_activity[user_id] = {
                        "count": 1,
                        "last_seen": now,
                        "nickname": nickname,
                    }
                else:
                    record["count"] = int(record.get("count", 0)) + 1
                    record["last_seen"] = now
                    if nickname:
                        record["nickname"] = nickname

    def message_stats(self) -> dict[str, Any]:
        self._roll_date()
        return {
            "total": int(self._stats.get("total") or 0),
            "today": int(self._stats.get("today") or 0),
            "today_date": str(self._stats.get("today_date") or ""),
            "started_at": float(self._stats.get("started_at") or time.time()),
        }

    def message_series(self, days: int = 30) -> list[dict[str, Any]]:
        self._roll_date()
        history = list(self._stats.get("history") or [])
        today_date = str(self._stats.get("today_date") or "")
        if today_date:
            history.append(
                {"date": today_date, "count": int(self._stats.get("today") or 0)}
            )
        return history[-max(1, int(days)) :]

    def active_users(self, limit: int = 10) -> dict[str, Any]:
        items = [
            {
                "user_id": user_id,
                "count": int(record.get("count", 0)),
                "last_seen": float(record.get("last_seen", 0)),
                "nickname": str(record.get("nickname") or ""),
            }
            for user_id, record in self._user_activity.items()
        ]
        items.sort(key=lambda item: item["count"], reverse=True)
        return {"tracked_users": len(items), "items": items[: max(1, int(limit))]}

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def record_log(self, payload: dict[str, Any]) -> None:
        self._log_seq += 1
        raw_time = str(payload.get("time") or "")
        item = {
            "id": self._log_seq,
            "time": raw_time[11:19] if len(raw_time) >= 19 else raw_time,
            "datetime": raw_time[:19].replace("T", " "),
            "ts": float(payload.get("timestamp") or time.time()),
            "level": str(payload.get("level") or "info").lower(),
            "module": str(payload.get("module") or "—") or "—",
            "message": str(payload.get("message") or ""),
        }
        self._log_buffer.append(item)
        message = item["message"]
        if "API" in message or "api" in message:
            match = _API_ACTION_RE.search(message)
            if match:
                action = match.group(1)
                self._api_calls[action] = self._api_calls.get(action, 0) + 1

    def logs(self, *, since: int = 0, limit: int = 200) -> dict[str, Any]:
        items = [item for item in self._log_buffer if int(item["id"]) > int(since)]
        if limit and limit > 0:
            items = items[-int(limit) :]
        return {
            "items": items,
            "last_id": self._log_seq,
            "total": len(self._log_buffer),
        }

    def api_calls(self, limit: int = 10) -> dict[str, Any]:
        items = [
            {"action": action, "count": count}
            for action, count in sorted(
                self._api_calls.items(), key=lambda item: item[1], reverse=True
            )
        ]
        return {
            "total_calls": sum(self._api_calls.values()),
            "unique_actions": len(self._api_calls),
            "items": items[: max(1, int(limit))],
        }

    # ------------------------------------------------------------------
    # 延迟
    # ------------------------------------------------------------------

    def record_latency(self, milliseconds: float | None, *, ok: bool = True) -> None:
        self._latency_total += 1
        if ok:
            self._latency_ok += 1
        self._latency.append((time.time(), milliseconds))

    def latency_series(self) -> dict[str, Any]:
        series = [
            {"ts": ts, "ms": (None if ms is None else round(float(ms), 1))}
            for ts, ms in self._latency
        ]
        values = [item["ms"] for item in series if item["ms"] is not None]
        success_rate = (
            round(self._latency_ok / self._latency_total * 100, 1)
            if self._latency_total
            else None
        )
        return {
            "series": series,
            "current_ms": series[-1]["ms"] if series else None,
            "avg_ms": round(sum(values) / len(values), 1) if values else None,
            "min_ms": min(values) if values else None,
            "max_ms": max(values) if values else None,
            "success_rate": success_rate,
            "samples": self._latency_total,
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._stats_path.is_file():
            return
        try:
            payload = json.loads(self._stats_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            self._logger.warning(f"面板统计文件读取失败: {exc}")
            return
        if not isinstance(payload, dict):
            return
        history = payload.get("history")
        self._stats = {
            "total": int(payload.get("total") or 0),
            "today": int(payload.get("today") or 0),
            "today_date": str(payload.get("today_date") or ""),
            "history": [
                {"date": str(item.get("date")), "count": int(item.get("count") or 0)}
                for item in (history if isinstance(history, list) else [])
                if isinstance(item, dict) and item.get("date")
            ][-self._history_max_days :],
            "started_at": float(payload.get("started_at") or time.time()),
        }
        self._roll_date()

    def _save(self) -> None:
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._stats_path.write_text(
                json.dumps(self._stats, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self._logger.warning(f"面板统计文件写入失败: {exc}")

    def flush(self) -> None:
        self._save()
