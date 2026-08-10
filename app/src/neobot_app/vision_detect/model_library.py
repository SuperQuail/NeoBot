"""模型库:扫描 ONNX 模型目录 ↔ models.toml 索引。

设计目标(高扩展性):
- 用户只需把 .onnx 放入 models/ 目录,运行 `neobot init` 或重启 bot,
  程序自动生成/合并 models.toml 骨架条目
- 用户只填写每个模型的 id/name/description(给 agent 看的模型描述),
  其余字段(conf/iou/imgsz/classes)可选,程序提供默认与自动解析
- 任何已登记条目的用户填写内容(非空字段)都不会被程序覆盖

TOML 使用 tomlkit 读写:保留用户手写注释与格式。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any

from neobot_app.vision_detect.engine import resolve_names

INDEX_HEADER = (
    "# 本文件由 neobot 自动维护骨架(运行 `neobot init` 可重新扫描 models/ 目录重建)。\n"
    "# 不要手工添加 [[models]] 条目;请按需填写每个模型的以下字段:\n"
    "#   id          唯一标识(必填),agent 使用它选择模型\n"
    "#   name        展示名(建议填写)\n"
    "#   description 模型能力描述(建议填写),会展示给 AI 供其选择模型:\n"
    "#               例如「检测图片中是否出现角色『弥音』的面部/头部形象」\n"
    "#   classes     可选,类别名列表,留空则自动从模型元数据解析\n"
    "#   conf/iou    可选,覆盖默认阈值;imgsz 可选,覆盖输入尺寸(0=自动)\n"
    "#   enabled     可选,false 表示下线该模型(不会被加载)\n"
)

_SAFE_ID_RE = re.compile(r"[^\w-]")


def slugify(name: str) -> str:
    """把文件名转成安全的模型 id(保留中文与字母数字下划线)。"""
    stem = Path(name).stem
    slug = _SAFE_ID_RE.sub("_", stem).strip("_")
    return slug or "model"


@dataclass
class LibraryConfig:
    """全局默认推理参数,可被单个模型覆盖。"""

    default_conf: float = 0.35
    default_iou: float = 0.45
    imgsz: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"default_conf": self.default_conf, "default_iou": self.default_iou, "imgsz": self.imgsz}


@dataclass
class ModelEntry:
    """单个模型的登记信息(与 toml [[models]] 条目一一对应)。"""

    file: str
    id: str
    name: str = ""
    description: str = ""
    classes: list[str] = field(default_factory=list)
    conf: float | None = None
    iou: float | None = None
    imgsz: int | None = None
    enabled: bool = True
    auto_generated: bool = True
    missing: bool = False
    unconfigured: bool = True
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in dataclass_fields(self):
            if f.name in ("auto_generated", "missing", "unconfigured", "error"):
                continue
            value = getattr(self, f.name)
            if value != f.default or f.name in ("file", "id"):
                result[f.name] = value
        return result


@dataclass
class ScanReport:
    """一次扫描的结果摘要。"""

    scanned: int = 0
    added: int = 0
    missing: int = 0
    unconfigured: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"扫描模型目录: {self.scanned} 个模型,新增登记 {self.added} 个,缺失 {self.missing} 个"]
        if self.unconfigured:
            lines.append("以下模型未填写描述(请编辑 models.toml 补填 description):")
            lines.extend(f"  - {item}" for item in self.unconfigured)
        for error in self.errors:
            lines.append(f"  ! {error}")
        return "\n".join(lines)


class ModelLibrary:
    """ONNX 模型目录 ↔ models.toml 索引库(进程内单例,幂等刷新)。"""

    def __init__(self, models_dir: str | Path, index_file: str | Path):
        self._models_dir = Path(models_dir)
        self._index_file = Path(index_file)
        self._entries: list[ModelEntry] = []
        self._config = LibraryConfig()
        self._lock = threading.Lock()
        self._fingerprint: tuple[int, tuple[str, ...]] | None = None

    # ── 目录扫描 ──

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    @property
    def index_file(self) -> Path:
        return self._index_file

    def _scan_files(self) -> list[Path]:
        if not self._models_dir.exists():
            return []
        return sorted(
            path
            for path in self._models_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".onnx"
        )

    def _current_fingerprint(self) -> tuple[int, tuple[str, ...]]:
        files = self._scan_files()
        names = tuple(path.name for path in files)
        try:
            mtime = self._index_file.stat().st_mtime_ns if self._index_file.exists() else -1
        except OSError:
            mtime = -1
        return (mtime, names)

    def needs_refresh(self) -> bool:
        """目录文件或索引 mtime 是否变化(廉价检查,每次调用前使用)。"""
        return self._fingerprint != self._current_fingerprint()

    # ── 索引读写 ──

    def _load_index(self) -> dict[str, Any]:
        try:
            import tomlkit

            doc = tomlkit.parse(self._index_file.read_text(encoding="utf-8"))
            return {"doc": doc, "root": doc}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def refresh(self, force: bool = False) -> ScanReport:
        """扫描 models/ 目录并与索引合并,幂等。

        Args:
            force: 强制重建索引文件骨架(保留用户已填写字段)。
        """
        with self._lock:
            return self._refresh_locked(force=force)

    def _refresh_locked(self, *, force: bool) -> ScanReport:
        report = ScanReport()
        files = self._scan_files()
        report.scanned = len(files)
        loaded = self._load_index()
        root: Any = loaded.get("root")
        if root is None:
            from tomlkit import document

            root = document()
            root["library"] = self._config.as_dict()
        library = root.get("library", {})
        if not isinstance(library, dict):
            library = root["library"] = {}
        # 读取用户保留的默认参数(未设置时保持程序默认)
        self._config = LibraryConfig(
            default_conf=float(library.get("default_conf", self._config.default_conf)),
            default_iou=float(library.get("default_iou", self._config.default_iou)),
            imgsz=int(library.get("imgsz", self._config.imgsz)),
        )
        root["library"] = self._config.as_dict()

        merged: dict[str, dict[str, Any]] = {}
        raw_entries = root.get("models", [])
        if isinstance(raw_entries, list):
            for raw in raw_entries:
                if not isinstance(raw, dict):
                    continue
                file_name = str(raw.get("file") or "")
                if not file_name:
                    continue
                merged[file_name] = dict(raw)

        entry_files: set[str] = set()
        for path in files:
            file_name = path.name
            entry_files.add(file_name)
            raw = merged.get(file_name)
            if raw is None:
                entry = self._make_skeleton(file_name)
                merged[file_name] = entry.as_dict()
                report.added += 1
            else:
                self._merge_existing(file_name, raw)

        for file_name, raw in list(merged.items()):
            if file_name in entry_files:
                continue
            raw["enabled"] = False
            raw["missing"] = True
            report.missing += 1

        # 重建 entries 列表并写回索引
        entries: list[ModelEntry] = []
        models_list: list[dict[str, Any]] = []
        for file_name in sorted(merged):
            raw = merged[file_name]
            entry = ModelEntry(file=file_name, id=str(raw.get("id") or slugify(file_name)))
            for f in dataclass_fields(entry):
                if f.name in ("file", "id", "auto_generated", "missing", "unconfigured", "error"):
                    continue
                value = raw.get(f.name, f.default)
                if f.name == "classes" and isinstance(value, list):
                    entry.classes = [str(item) for item in value]
                elif value is not None:
                    setattr(entry, f.name, value)
            entry.missing = bool(raw.get("missing", False))
            entry.enabled = bool(raw.get("enabled", True))
            # auto_generated:程序生成的骨架,用户还未填写任何内容(不写回文件,由程序推断)
            entry.auto_generated = not (entry.name or entry.description)
            entry.unconfigured = not entry.description.strip()
            if entry.unconfigured and entry.auto_generated:
                report.unconfigured.append(f"{entry.id} (file={entry.file})")
            if not entry.missing and entry.enabled:
                error = self._validate_entry(entry)
                if error:
                    entry.error = error
                    report.errors.append(f"{entry.id}: {error}")
            entries.append(entry)
            out = entry.as_dict()
            if entry.missing:
                out["missing"] = True
            models_list.append(out)

        root["models"] = models_list
        self._write_index(root)
        self._entries = entries
        self._fingerprint = self._current_fingerprint()
        return report

    def _make_skeleton(self, file_name: str) -> ModelEntry:
        """为新发现的模型生成骨架条目(类别名尝试自动解析)。"""
        entry = ModelEntry(file=file_name, id=slugify(file_name))
        resolved = resolve_names(self._models_dir / file_name)
        if resolved:
            entry.classes = list(resolved)
        return entry

    def _merge_existing(self, file_name: str, raw: dict[str, Any]) -> None:
        """已有条目:只修正 id 缺失/类别名缺失,不覆盖用户填写内容。"""
        if not raw.get("id"):
            raw["id"] = slugify(file_name)
        if not raw.get("classes"):
            resolved = resolve_names(self._models_dir / file_name)
            if resolved:
                raw["classes"] = list(resolved)

    def _validate_entry(self, entry: ModelEntry) -> str:
        path = self._models_dir / entry.file
        if not path.exists():
            return f"模型文件不存在: {path}"
        return ""

    def _write_index(self, root: Any) -> None:
        from tomlkit import dumps

        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        text = dumps(root)
        if not text.lstrip().startswith("#"):
            text = INDEX_HEADER + text
        self._index_file.write_text(text, encoding="utf-8")

    # ── 对外查询 ──

    @property
    def config(self) -> LibraryConfig:
        return self._config

    def entries(self) -> list[ModelEntry]:
        return list(self._entries)

    def enabled_entries(self) -> list[ModelEntry]:
        return [entry for entry in self._entries if entry.enabled and not entry.missing and not entry.error]

    def get(self, model_id: str) -> ModelEntry | None:
        for entry in self._entries:
            if entry.id == model_id:
                return entry
        return None

    def resolve(self, model_id: str) -> ModelEntry | None:
        entry = self.get(model_id)
        if entry is not None and entry.enabled and not entry.missing and not entry.error:
            return entry
        return None
