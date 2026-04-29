from __future__ import annotations

import json
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.reply.event import ReplyEvent
from neobot_app.time_context import now_utc, to_utc


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return to_utc(value).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _to_jsonable(value.model_dump())
        except Exception:
            return repr(value)
    return repr(value)


def _markdown_escape(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


class DebugRecorder:
    def __init__(self, log_dir: Path, logger: Logger | None = None) -> None:
        self._log_dir = log_dir
        self._reply_md_dir = self._log_dir / "reply_events"
        self._lock = threading.Lock()
        self._logger = logger or NullLogger()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._reply_md_dir.mkdir(parents=True, exist_ok=True)
        self._logger.info(
            "DebugRecorder 已初始化",
            log_dir=str(log_dir),
            reply_md_dir=str(self._reply_md_dir),
        )

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def record_packet(self, packet: dict[str, Any]) -> None:
        self._logger.debug("记录数据包", post_type=packet.get("post_type", ""))
        self._write_jsonl(
            "packets.jsonl",
            {
                "recorded_at": now_utc().isoformat(),
                "packet": _to_jsonable(packet),
            },
        )

    def record_reply_event(
        self,
        stage: str,
        event: ReplyEvent,
        **extra: Any,
    ) -> None:
        self._logger.debug("记录回复事件", stage=stage, event_id=event.event_id)
        payload = {
            "recorded_at": now_utc().isoformat(),
            "stage": stage,
            "event": self._serialize_reply_event(event),
        }
        if extra:
            payload["extra"] = _to_jsonable(extra)
        self._write_jsonl("reply_events.jsonl", payload)
        self._write_reply_markdown(payload)

    def _serialize_reply_event(self, event: ReplyEvent) -> dict[str, Any]:
        decision = event.willing_decision
        return {
            "event_id": event.event_id,
            "state": event.state.name,
            "mode": event.mode,
            "conversation_ref": _to_jsonable(event.conversation_ref),
            "message": _to_jsonable(event.message),
            "generated_text": event.generated_text,
            "reply_to_number": event.reply_to_number,
            "message_number_map": event.message_number_map,
            "created_at": _to_jsonable(event.created_at),
            "completed_at": _to_jsonable(event.completed_at),
            "error": event.error,
            "send_response": _to_jsonable(event.send_response),
            "willing_decision": {
                "manager_name": getattr(decision, "manager_name", None),
                "probability": getattr(decision, "probability", None),
                "should_reply": getattr(decision, "should_reply", None),
                "reasons": list(getattr(decision, "reasons", ()) or ()),
            },
        }

    def _write_jsonl(self, file_name: str, payload: dict[str, Any]) -> None:
        target = self._log_dir / file_name
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with target.open("a", encoding="utf-8") as f:
                f.write(line)

    def _write_reply_markdown(self, payload: dict[str, Any]) -> None:
        event = payload["event"]
        stem = self._get_event_filename_stem(event)
        target = self._reply_md_dir / f"{stem}.md"
        is_new = not target.exists()
        lines: list[str] = []
        if is_new:
            lines.extend(self._build_markdown_header(event))
            self._write_event_json(stem, event)
        lines.extend(self._build_markdown_section(payload))
        content = "\n".join(lines) + "\n"
        with self._lock:
            with target.open("a", encoding="utf-8") as f:
                f.write(content)

    @staticmethod
    def _get_event_filename_stem(event: dict[str, Any]) -> str:
        created_at = event.get("created_at", "")
        try:
            dt = datetime.fromisoformat(str(created_at))
        except (ValueError, TypeError):
            dt = now_utc()
        short_id = str(event.get("event_id", ""))[-6:]
        return f"{dt.year}-{dt.month}-{dt.day}-{dt.hour:02d}-{dt.minute:02d}-{short_id}"

    def _write_event_json(self, stem: str, event: dict[str, Any]) -> None:
        target = self._reply_md_dir / f"{stem}.json"
        data = {
            "event_id": event.get("event_id"),
            "created_at": event.get("created_at"),
            "mode": event.get("mode"),
            "conversation_ref": event.get("conversation_ref"),
            "message": event.get("message"),
        }
        with self._lock:
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

    def _build_markdown_header(self, event: dict[str, Any]) -> list[str]:
        conversation = event.get("conversation_ref") or {}
        return [
            f"# Reply Event {event['event_id']}",
            "",
            "| 字段 | 值 |",
            "| --- | --- |",
            f"| 模式 | {event.get('mode') or ''} |",
            f"| 会话类型 | {conversation.get('kind') or ''} |",
            f"| 会话ID | {conversation.get('id') or ''} |",
            f"| 创建时间 | {event.get('created_at') or ''} |",
            "",
        ]

    def _build_markdown_section(self, payload: dict[str, Any]) -> list[str]:
        recorded_at = payload.get("recorded_at", "")
        stage = payload.get("stage", "")
        event = payload["event"]
        extra = payload.get("extra") or {}
        lines = [
            f"## {recorded_at} {stage}",
            "",
            "| 字段 | 值 |",
            "| --- | --- |",
            f"| 状态 | {event.get('state') or ''} |",
            f"| 错误 | {event.get('error') or ''} |",
            f"| 回复预览 | {self._single_line(event.get('generated_text') or '')} |",
            "",
        ]

        prompt = extra.get("prompt")
        if isinstance(prompt, str):
            lines.extend(
                [
                    "### 提示词",
                    "",
                    "```text",
                    _markdown_escape(prompt),
                    "```",
                    "",
                ]
            )

        sub_agents = extra.get("sub_agents")
        if isinstance(sub_agents, list):
            lines.append("### 已启用 Sub Agent")
            lines.append("")
            if sub_agents:
                for item in sub_agents:
                    if isinstance(item, dict):
                        lines.append(
                            f"- `{item.get('name', '')}`: {self._single_line(str(item.get('description', '')))}"
                        )
            else:
                lines.append("- 无")
            lines.append("")

        if "tool_name" in extra:
            lines.extend(
                [
                    "### 工具调用",
                    "",
                    f"- 工具名: `{extra.get('tool_name', '')}`",
                ]
            )
            if "tool_args" in extra:
                lines.extend(
                    [
                        "",
                        "```json",
                        json.dumps(extra["tool_args"], ensure_ascii=False, indent=2),
                        "```",
                    ]
                )
            lines.append("")

        if "tool_result" in extra:
            lines.extend(
                [
                    "### 工具返回",
                    "",
                    "```text",
                    _markdown_escape(str(extra["tool_result"])),
                    "```",
                    "",
                ]
            )

        if "response" in extra:
            lines.extend(
                [
                    "### 模型响应",
                    "",
                    "```json",
                    json.dumps(extra["response"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )

        if "formatted" in extra:
            lines.extend(
                [
                    "### 发送内容",
                    "",
                    "```text",
                    _markdown_escape(str(extra["formatted"])),
                    "```",
                    "",
                ]
            )

        extra_without_special = {
            key: value
            for key, value in extra.items()
            if key
            not in {
                "prompt",
                "sub_agents",
                "tool_name",
                "tool_args",
                "tool_result",
                "response",
                "formatted",
            }
        }
        if extra_without_special:
            lines.extend(
                [
                    "### 额外信息",
                    "",
                    "```json",
                    json.dumps(extra_without_special, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        return lines

    @staticmethod
    def _single_line(value: str) -> str:
        return _markdown_escape(value).replace("\n", " ")[:200]
