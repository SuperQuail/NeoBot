"""聊天流提示词历史记录器（完整提示词落盘 + 轻量内存索引）。

每次模型调用的完整上下文(messages)落盘为一个独立 JSON 文件，供网页面板
「聊天流 → 提示词历史」按需读取（完整内容、不做任何截断）：

- 文件命名: ``ctx_<YYYYmmdd_HHMMSS_ffffff>_<seq>.json``（沿用既有命名）；
- 目录: ``<DATA_DIR>/chat_flows/prompts/``（原 ``debug/context/`` 的历史不迁移、不消费）；
- 保留策略: 全局最近 ``max_files`` 份（默认 100），写满删除最旧整份文件；
- 内存: 只保留 ``PromptMeta`` 轻量索引（约 150 B/条）；默认不保留提示词正文，
  ``latest_in_memory=True`` 时额外把最新一份留在内存，换取常规轮询不读盘；
- 写盘: :func:`neobot_app.utils.atomic.atomic_write_text`（同目录临时文件 + fsync +
  原子替换），读者不会拿到半截 JSON；
- 失败处理: 读写异常一律只记 debug，绝不反噬回复管线。

进程启动时扫描既有文件重建索引，重启后历史仍然可用。
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.utils.atomic import atomic_write_text

#: 文件名形如 ctx_20250912_101112_123456_0007.json
_FILENAME_PATTERN = re.compile(r"^ctx_(\d{8}_\d{6}_\d{6})_(\d+)\.json$")
#: 重建索引时只读文件前缀来提取元数据，避免启动时为上百 MB 的 JSON 全量解析
_META_PROBE_CHARS = 262_144
#: 探针文本中可按顶层缩进(2 空格)提取的标量字段
_PROBE_FIELDS = (
    "pipeline_key",
    "conversation_kind",
    "conversation_id",
    "iteration",
    "model",
    "messages_count",
    "recorded_at",
)
#: 顶层字段缩进恰好 2 个空格，嵌套字段更深，因此锚定缩进不会误取子结构里的同名字段
_PROBE_PATTERNS = {
    field: re.compile(rf'^  "{field}":\s*(.+)$', re.MULTILINE) for field in _PROBE_FIELDS
}


@dataclass(frozen=True)
class PromptMeta:
    """一份落盘提示词的元数据（不含正文，约 150 B/条）。"""

    seq: int
    path: str
    pipeline_key: str
    iteration: int
    model: str
    total_messages: int
    bytes: int
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        """转成面板 API 友好的普通字典。"""
        return {
            "seq": self.seq,
            "path": self.path,
            "pipeline_key": self.pipeline_key,
            "iteration": self.iteration,
            "model": self.model,
            "total_messages": self.total_messages,
            "bytes": self.bytes,
            "recorded_at": self.recorded_at,
        }


class ContextRecorder:
    """把完整聊天上下文写入滚动文件集(全局最新 max_files 份)，并维护元数据索引。"""

    def __init__(
        self,
        log_dir: Path,
        *,
        max_files: int = 100,
        logger: Logger | None = None,
        latest_in_memory: bool = False,
    ) -> None:
        if max_files <= 0:
            raise ValueError("max_files must be greater than 0")
        self._log_dir = Path(log_dir)
        self._max_files = int(max_files)
        self._latest_in_memory = bool(latest_in_memory)
        self._lock = threading.Lock()
        self._logger = logger or NullLogger()
        self._seq = 0
        self._entries: dict[int, PromptMeta] = {}
        self._latest_seq = 0
        self._latest_payload: dict[str, Any] | None = None
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self._rebuild_index()
            if self._latest_in_memory:
                self._preload_latest()
        except Exception as exc:
            self._logger.debug(
                "初始化聊天上下文记录器目录失败(忽略)",
                log_dir=str(self._log_dir),
                error=str(exc),
            )
        self._logger.info(
            "ContextRecorder 已初始化",
            log_dir=str(self._log_dir),
            max_files=self._max_files,
            latest_in_memory=self._latest_in_memory,
            entries=len(self._entries),
        )

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    @property
    def max_files(self) -> int:
        """全局保留份数上限。"""
        return self._max_files

    @property
    def latest_in_memory(self) -> bool:
        """是否把最新一份完整提示词常驻内存。"""
        return self._latest_in_memory

    @property
    def latest_seq(self) -> int | None:
        """最新一份的 seq；目录为空时返回 None。"""
        with self._lock:
            return max(self._entries) if self._entries else None

    def record_context(self, payload: dict[str, Any]) -> Path:
        """落盘一次模型调用上下文，返回目标文件路径。

        写盘失败只记 debug 并返回目标路径（文件可能不存在），不抛异常。
        """
        with self._lock:
            self._seq += 1
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target = self._log_dir / f"ctx_{stamp}_{self._seq:04d}.json"
            try:
                text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
                atomic_write_text(target, text)
                self._entries[self._seq] = self._meta_from_payload(
                    payload, seq=self._seq, path=target, size=len(text.encode("utf-8"))
                )
                if self._latest_in_memory:
                    self._latest_seq = self._seq
                    self._latest_payload = payload
                self._prune()
            except Exception as exc:
                self._logger.debug(
                    "记录聊天上下文失败(忽略)", path=str(target), error=str(exc)
                )
            return target

    def list_entries(self, pipeline_key: str | None = None) -> list[PromptMeta]:
        """列出提示词元数据，按 seq 升序（由旧到新）；可按 pipeline_key 过滤。"""
        with self._lock:
            items = [self._entries[seq] for seq in sorted(self._entries)]
        key = str(pipeline_key).strip() if pipeline_key is not None else ""
        if not key:
            return items
        return [item for item in items if item.pipeline_key == key]

    def read_entry(self, seq: int) -> dict[str, Any] | None:
        """按 seq 读取单份完整提示词全文；不存在或读取失败返回 None，不抛。"""
        try:
            key = int(seq)
        except (TypeError, ValueError):
            return None
        with self._lock:
            return self._read_payload(key)

    def read_latest(self) -> dict[str, Any] | None:
        """读取最新一份完整提示词（面板默认视图）；没有历史时返回 None。"""
        with self._lock:
            if not self._entries:
                return None
            key = max(self._entries)
            return self._read_payload(key)

    def clear(self) -> int:
        """删除全部落盘提示词并清空索引，返回删除的文件数。"""
        with self._lock:
            removed = 0
            for path in sorted(self._log_dir.glob("ctx_*.json")):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
            self._entries.clear()
            self._latest_seq = 0
            self._latest_payload = None
            # seq 保持单调，避免删除失败的残留文件被新文件覆盖
            return removed

    # ── 内部：索引与落盘（调用方需持有 self._lock，初始化阶段除外） ──

    def _read_payload(self, key: int) -> dict[str, Any] | None:
        """读取单个 seq 的完整 JSON；latest_in_memory 命中时不读盘。"""
        meta = self._entries.get(key)
        if meta is None:
            return None
        if (
            self._latest_in_memory
            and self._latest_seq == key
            and self._latest_payload is not None
        ):
            return dict(self._latest_payload)
        try:
            data = json.loads(Path(meta.path).read_text(encoding="utf-8"))
        except Exception as exc:
            self._logger.debug(
                "读取提示词历史失败(忽略)", seq=key, path=meta.path, error=str(exc)
            )
            return None
        return data if isinstance(data, dict) else None

    def _preload_latest(self) -> None:
        """latest_in_memory=True 时，启动后把最新一份读进内存。"""
        if not self._entries:
            return
        key = max(self._entries)
        payload = self._read_payload(key)
        if payload is not None:
            self._latest_seq = key
            self._latest_payload = payload

    def _rebuild_index(self) -> None:
        """扫描目录重建索引（重启后历史仍可用），并顺带按上限清理。"""
        entries: dict[int, PromptMeta] = {}
        max_seq = 0
        for path in sorted(self._log_dir.glob("ctx_*.json")):
            seq, stamp = _parse_filename(path)
            if seq is None:
                continue
            entries[seq] = self._meta_from_file(path, seq=seq, fallback_time=stamp)
            max_seq = max(max_seq, seq)
        self._entries = entries
        self._seq = max_seq
        self._prune()

    def _prune(self) -> None:
        """只保留最新 max_files 份，删除最旧整份文件并同步索引。"""
        files = sorted(self._log_dir.glob("ctx_*.json"))
        overflow = len(files) - self._max_files
        if overflow <= 0:
            return
        for old in files[:overflow]:
            try:
                old.unlink()
            except OSError:
                continue
            seq, _ = _parse_filename(old)
            if seq is None:
                continue
            self._entries.pop(seq, None)
            if self._latest_seq == seq:
                self._latest_seq = 0
                self._latest_payload = None

    def _meta_from_payload(
        self, payload: Any, *, seq: int, path: Path, size: int
    ) -> PromptMeta:
        """从完整 payload 里取元数据。"""
        data = payload if isinstance(payload, dict) else {}
        messages = data.get("messages")
        total = _as_int(data.get("messages_count"), default=-1)
        if total < 0:
            total = len(messages) if isinstance(messages, list) else 0
        return PromptMeta(
            seq=seq,
            path=str(path),
            pipeline_key=_pipeline_key(data),
            iteration=_as_int(data.get("iteration")),
            model=str(data.get("model") or ""),
            total_messages=total,
            bytes=int(size),
            recorded_at=str(data.get("recorded_at") or ""),
        )

    def _meta_from_file(
        self, path: Path, *, seq: int, fallback_time: str
    ) -> PromptMeta:
        """从磁盘既有文件重建元数据（只解析可得字段）。"""
        data: dict[str, Any] = {}
        size = 0
        try:
            size = path.stat().st_size
            data = _probe_metadata(path)
        except Exception as exc:
            self._logger.debug(
                "读取提示词历史元数据失败(忽略)", path=str(path), error=str(exc)
            )
        meta = self._meta_from_payload(data, seq=seq, path=path, size=size)
        if not meta.recorded_at:
            meta = replace(meta, recorded_at=fallback_time)
        return meta


def _parse_filename(path: Path) -> tuple[int | None, str]:
    """从文件名解析 (seq, 时间戳转 ISO)；不匹配返回 (None, "")。"""
    match = _FILENAME_PATTERN.match(path.name)
    if match is None:
        return None, ""
    return int(match.group(2)), _iso_from_stamp(match.group(1))


def _iso_from_stamp(stamp: str) -> str:
    """把文件名里的 YYYYmmdd_HHMMSS_ffffff 转成 ISO 文本。"""
    try:
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S_%f").isoformat()
    except ValueError:
        return ""


def _probe_metadata(path: Path) -> dict[str, Any]:
    """读取文件前缀提取元数据，避免为索引全量解析大 JSON。"""
    with path.open("r", encoding="utf-8") as handle:
        chunk = handle.read(_META_PROBE_CHARS)
    try:
        data = json.loads(chunk)
    except ValueError:
        data = None
    if isinstance(data, dict):
        if "messages_count" in data or "messages" in data:
            return data
        scalars: dict[str, Any] = dict(data)
    else:
        scalars = {}
    for field, pattern in _PROBE_PATTERNS.items():
        if field in scalars:
            continue
        match = pattern.search(chunk)
        if match is None:
            continue
        try:
            scalars[field] = json.loads(match.group(1).rstrip().rstrip(","))
        except ValueError:
            continue
    return scalars


def _pipeline_key(data: dict[str, Any]) -> str:
    """优先取 payload 里的 pipeline_key，缺失时按 kind:id 兜底拼一个。"""
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
