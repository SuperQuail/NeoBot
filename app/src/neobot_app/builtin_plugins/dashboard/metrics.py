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

from neobot_app.utils.atomic import atomic_write_text
from neobot_contracts.ports.logging import Logger, NullLogger

_API_ACTION_RE = re.compile(r"action['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_]+)")

#: 延迟样本至少要能覆盖的时长（秒），用于按采样间隔推导 deque 容量
_LATENCY_COVERAGE_SECONDS = 3600.0
_LATENCY_MIN_SAMPLES = 60


def latency_sample_capacity(interval_seconds: float) -> int:
    """按采样间隔推导延迟样本容量（默认覆盖最近 60 分钟，至少 60 个样本）。

    采样间隔越大，同样容量能覆盖的时间就越长；这里反过来固定覆盖时长，
    避免「采得极勤、留得极短」（旧实现固定 60 个样本 × 15s = 仅 15 分钟）。
    """
    try:
        interval = float(interval_seconds or 0)
    except (TypeError, ValueError):
        interval = 0.0
    if interval <= 0:
        return _LATENCY_MIN_SAMPLES
    return max(_LATENCY_MIN_SAMPLES, int(_LATENCY_COVERAGE_SECONDS / interval))


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
        #: 超过该秒数的旧样本视为「陈旧」；0 表示不做陈旧判定（保持既有行为）
        self._latency_stale_after = 0.0
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

    def set_log_buffer_capacity(self, size: int) -> None:
        """按新配置重建日志缓冲（保留最近的条目，不清空历史）。"""
        capacity = max(1, int(size))
        if self._log_buffer.maxlen == capacity:
            return
        self._log_buffer = deque(self._log_buffer, maxlen=capacity)

    def set_history_max_days(self, days: int) -> None:
        """按新配置调整指标历史保留天数（立即裁剪超期历史）。"""
        value = max(1, int(days))
        if value == self._history_max_days:
            return
        self._history_max_days = value
        history = list(self._stats.get("history") or [])
        if len(history) > value:
            self._stats["history"] = history[-value:]

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

    def set_latency_stale_after(self, seconds: float) -> None:
        """设置「样本陈旧」阈值（秒）；0 表示不做陈旧判定。

        探针在空闲期完全停止后，deque 里会一直留着几小时前的样本，
        若直接当作 current_ms 返回，面板会把旧值显示成"实时延迟"。
        """
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            value = 0.0
        self._latency_stale_after = max(0.0, value)

    def set_latency_capacity(self, samples: int) -> None:
        """按当前采样间隔调整延迟样本容量（保留最新的样本，不清空历史）。"""
        capacity = max(2, int(samples))
        if self._latency.maxlen == capacity:
            return
        self._latency = deque(self._latency, maxlen=capacity)

    def latency_is_stale(self) -> bool:
        """最近一次样本是否已过期（探针被门控停止后即为 True）。"""
        if self._latency_stale_after <= 0 or not self._latency:
            return False
        last_ts = float(self._latency[-1][0])
        return (time.time() - last_ts) > self._latency_stale_after

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
        stale = self.latency_is_stale()
        return {
            "series": series,
            # 陈旧样本不作为「实时延迟」返回：前端应显示「—」而不是几小时前的旧值
            "current_ms": (series[-1]["ms"] if series and not stale else None),
            "stale": stale,
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
            atomic_write_text(
                self._stats_path,
                json.dumps(self._stats, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            self._logger.warning(f"面板统计文件写入失败: {exc}")

    def flush(self) -> None:
        self._save()
