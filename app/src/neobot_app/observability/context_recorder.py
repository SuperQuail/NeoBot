"""聊天流提示词历史记录器（纯内存 + 逐份 diff + 图片只留哈希）。

面板「聊天流 → 完整提示词」的数据源。每次模型调用的完整上下文都记在这里，
但**不再落盘**（features/spec(10) 取代 spec(3) 的落盘实现）：

- **不落盘**：状态全在内存，重启即清空。既没有 ctx_*.json 残留，也没有
  「全局保留 N 份 × 单份 0.5~1.2 MB」的磁盘占用；旧目录里的历史文件不再读取，
  可在面板「清空提示词历史」时一并删除；
- **逐份 diff**：第 1 份存完整快照，之后每份只存相对上一份的补丁（见 prompt_diff），
  回复管线的 messages 是逐轮追加的，因此补丁极小 —— 100 份历史常驻约 1~2 MB；
- **图片脱敏**：messages 里的 data:image/...;base64 正文换成 sha256 哈希
  （图库去重同口径），面板审查提示词时不再搬运数 MB 的 base64；
- **有界**：全局保留最近 limit 份，超出后从最旧一份开始淘汰并重新定基；
- **失败处理**：读写异常一律只记 debug，绝不反噬回复管线。

读取语义：read_entry / read_latest 返回的是**内部对象**，调用方只读不写
（面板只做 JSON 序列化）；逐份重建时返回的是全新对象，可以放心使用。
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.observability.prompt_diff import (
    apply_patch,
    count_image_refs,
    diff_payload,
    json_safe,
    patch_bytes,
    payload_bytes,
    sanitize_images,
)

#: 完整提示词历史默认全局保留份数
DEFAULT_PROMPT_HISTORY_LIMIT = 100


@dataclass(frozen=True)
class PromptMeta:
    """一份提示词历史的元数据（不含正文）。"""

    seq: int
    pipeline_key: str
    iteration: int
    model: str
    total_messages: int
    bytes: int
    patch_bytes: int
    images: int
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        """转成面板 API 友好的普通字典。"""
        return {
            "seq": self.seq,
            "pipeline_key": self.pipeline_key,
            "iteration": self.iteration,
            "model": self.model,
            "total_messages": self.total_messages,
            "bytes": self.bytes,
            "patch_bytes": self.patch_bytes,
            "images": self.images,
            "recorded_at": self.recorded_at,
        }


class ContextRecorder:
    """把完整聊天上下文留在内存里（逐份 diff），并维护元数据索引。"""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_PROMPT_HISTORY_LIMIT,
        logger: Logger | None = None,
        legacy_dir: Any = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        self._limit = int(limit)
        self._logger = logger or NullLogger()
        self._legacy_dir = legacy_dir
        self._lock = threading.Lock()
        self._seq = 0
        self._entries: dict[int, PromptMeta] = {}
        #: 最旧保留份（完整快照）及其 seq
        self._base_seq = 0
        self._base_payload: Any = None
        #: seq → 相对上一份的补丁（base_seq 之后每一份都有一条，可能是空列表）
        self._patches: dict[int, list[dict[str, Any]]] = {}
        #: 最新一份（完整快照）：面板默认视图 + 下一次记录时的 diff 基线
        self._latest_seq = 0
        self._latest_payload: Any = None
        self._image_refs = 0
        self._log_legacy_hint()
        self._logger.info(
            "ContextRecorder 已初始化（纯内存 + 逐份 diff）", limit=self._limit
        )

    # ── 只读属性 ──

    @property
    def limit(self) -> int:
        """全局保留份数上限。"""
        return self._limit

    @property
    def latest_seq(self) -> int | None:
        """最新一份的 seq；没有历史时返回 None。"""
        with self._lock:
            return self._latest_seq or None

    @property
    def storage_bytes(self) -> int:
        """当前实际驻留的估算体积（快照 + 全部补丁）。

        与「份数 × 单份体积」的落盘口径对比，用来证明 diff 存储的成本下降。
        最新一份的完整快照本身也是下一轮 diff 的基线，因此计入。
        """
        with self._lock:
            total = 0
            if self._base_payload is not None:
                total += payload_bytes(self._base_payload)
            if self._latest_seq and self._latest_seq != self._base_seq:
                total += payload_bytes(self._latest_payload)
            total += sum(item.patch_bytes for item in self._entries.values())
            return total

    @property
    def image_refs(self) -> int:
        """累计脱敏掉的图片引用处数。"""
        with self._lock:
            return self._image_refs

    # ── 写入 ──

    def record_context(self, payload: dict[str, Any]) -> int:
        """记录一次模型调用上下文，返回本次 seq；失败返回 0（不抛异常）。

        写入前先做图片脱敏，再转纯 JSON 结构，然后与上一份求补丁。
        """
        with self._lock:
            self._seq += 1
            seq = self._seq
            try:
                sanitized, replaced, _freed = sanitize_images(payload)
                safe = json_safe(sanitized)
                data = safe if isinstance(safe, dict) else {}
                if self._base_payload is None:
                    self._base_payload = safe
                    self._base_seq = seq
                    patch: list[dict[str, Any]] = []
                else:
                    patch = diff_payload(self._latest_payload, safe)
                self._patches[seq] = patch
                messages = data.get("messages")
                total = _as_int(data.get("messages_count"), default=-1)
                if total < 0:
                    total = len(messages) if isinstance(messages, list) else 0
                self._entries[seq] = PromptMeta(
                    seq=seq,
                    pipeline_key=_pipeline_key(data),
                    iteration=_as_int(data.get("iteration")),
                    model=str(data.get("model") or ""),
                    total_messages=total,
                    bytes=payload_bytes(safe),
                    patch_bytes=patch_bytes(patch),
                    images=count_image_refs(safe),
                    recorded_at=str(data.get("recorded_at") or ""),
                )
                self._latest_seq = seq
                self._latest_payload = safe
                self._image_refs += replaced
                self._prune()
            except Exception as exc:
                self._logger.debug("记录聊天上下文失败(忽略)", seq=seq, error=str(exc))
                return 0
            return seq

    # ── 读取 ──

    def list_entries(self, pipeline_key: str | None = None) -> list[PromptMeta]:
        """列出提示词元数据，按 seq 升序（由旧到新）；可按 pipeline_key 过滤。"""
        with self._lock:
            items = [self._entries[seq] for seq in sorted(self._entries)]
        key = str(pipeline_key).strip() if pipeline_key is not None else ""
        if not key:
            return items
        return [item for item in items if item.pipeline_key == key]

    def read_entry(self, seq: int) -> dict[str, Any] | None:
        """按 seq 读取单份完整提示词；不存在返回 None，不抛异常。"""
        try:
            key = int(seq)
        except (TypeError, ValueError):
            return None
        with self._lock:
            if key not in self._entries:
                return None
            if key == self._latest_seq:
                return self._latest_payload
            if key == self._base_seq:
                return self._base_payload
            return self._materialize(key)

    def read_latest(self) -> dict[str, Any] | None:
        """读取最新一份完整提示词（面板默认视图）；没有历史时返回 None。"""
        with self._lock:
            return self._latest_payload

    def clear(self) -> int:
        """清空内存里的全部历史与旧落盘文件，返回清掉的份数。"""
        with self._lock:
            removed = len(self._entries)
            self._entries.clear()
            self._patches.clear()
            self._base_seq = 0
            self._base_payload = None
            self._latest_seq = 0
            self._latest_payload = None
            self._image_refs = 0
            # seq 保持单调递增，避免面板手里的旧 seq 与新记录撞号
            self._purge_legacy_files()
            return removed

    # ── 内部（调用方需持有 self._lock） ──

    def _materialize(self, seq: int) -> Any:
        """从最旧快照出发逐个应用补丁，重建某一份（返回全新对象）。"""
        payload = copy.deepcopy(self._base_payload)
        for key in range(self._base_seq + 1, seq + 1):
            apply_patch(payload, self._patches.get(key) or [])
        return payload

    def _prune(self) -> None:
        """只保留最新 limit 份：淘汰最旧一份并把它的后继重新定基。"""
        while len(self._entries) > self._limit and len(self._entries) > 1:
            oldest = min(self._entries)
            new_base_seq = oldest + 1
            if new_base_seq not in self._entries:
                break
            self._base_payload = self._materialize(new_base_seq)
            self._base_seq = new_base_seq
            self._patches.pop(new_base_seq, None)
            self._entries.pop(oldest, None)

    def _log_legacy_hint(self) -> None:
        """旧落盘目录存在时提示一次：不再读取，可在面板清空。"""
        path = self._legacy_path()
        if path is None:
            return
        try:
            if not path.exists():
                return
            count = len(list(path.glob("ctx_*.json")))
            if count <= 0:
                return
            self._logger.info(
                "检测到旧的落盘提示词历史（已改为纯内存，不再读取）",
                dir=str(path),
                files=count,
                hint="可在面板「清空提示词历史」或手动删除该目录",
            )
        except Exception as exc:  # pragma: no cover - 只做提示，失败无所谓
            self._logger.debug("检查旧提示词目录失败(忽略)", error=str(exc))

    def _purge_legacy_files(self) -> int:
        """删除旧落盘目录里的 ctx_*.json（清空历史时顺带回收磁盘）。"""
        path = self._legacy_path()
        if path is None:
            return 0
        removed = 0
        try:
            for item in sorted(path.glob("ctx_*.json")):
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    continue
        except Exception as exc:  # pragma: no cover
            self._logger.debug("删除旧提示词文件失败(忽略)", error=str(exc))
        return removed

    def _legacy_path(self) -> Path | None:
        return Path(self._legacy_dir) if self._legacy_dir is not None else None


def _pipeline_key(data: Any) -> str:
    """优先取 payload 里的 pipeline_key，缺失时按 kind:id 兜底拼一个。"""
    if not isinstance(data, dict):
        return ""
    key = str(data.get("pipeline_key") or "").strip()
    if key:
        return key
    kind = str(data.get("conversation_kind") or "").strip()
    conversation_id = str(data.get("conversation_id") or "").strip()
    if kind and conversation_id:
        return f"{kind}:{conversation_id}"
    return ""


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["DEFAULT_PROMPT_HISTORY_LIMIT", "ContextRecorder", "PromptMeta"]
