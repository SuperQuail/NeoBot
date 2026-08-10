"""模型库:扫描 ONNX 模型目录 ↔ models.toml 索引。

设计目标(高扩展性):
- 用户只需把 .onnx 放入 models/ 目录,运行 `neobot init` 或重启 bot,
  程序自动生成/合并 models.toml 骨架条目
- 用户只填写每个模型的 id/name/description(给 agent 看的模型描述),
  其余字段(conf/iou/imgsz/classes)可选,程序提供默认与自动解析
- 任何已登记条目的用户填写内容(非空字段)都不会被程序覆盖
- missing 是运行时推断状态,不写回索引文件:文件删除再恢复后自动复活

TOML 使用 tomlkit 读写,保留用户手写注释与格式。
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any

from neobot_app.vision_detect.engine import resolve_names

INDEX_HEADER = (
    "# 本文件由 neobot 自动维护骨架(运行 `neobot init` 可重新扫描 models/ 目录重建)。\n"
    "# 每个 .onnx 文件对应一个模型条目,程序自动生成;请按需填写以下字段:\n"
    "#   id          唯一标识(建议填写,不填则由文件名自动生成,重名自动加后缀)\n"
    "#   name        展示名(建议填写)\n"
    "#   description 模型能力描述(强烈建议填写),会展示给 AI 供其选择模型;\n"
    "#               留空时模型仍可用,但 AI 不知道该模型检测什么\n"
    "#   classes     可选,类别名列表,留空则自动从模型元数据解析\n"
    "#   conf        可选,置信度阈值(0~1,越高越严格,默认 0.35)\n"
    "#   iou         可选,NMS 阈值(默认 0.45);imgsz 可选,输入尺寸(0=自动)\n"
    "#   enabled     可选,false 表示下线该模型(不会被加载)\n"
    "# 示例条目(直接照抄修改即可):\n"
    "# [[models]]\n"
    "# file = \"miyin_face.onnx\"   # 模型文件名(自动生成,一般不用动)\n"
    "# id = \"miyin_face\"\n"
    "# name = \"弥音脸部识别\"\n"
    "# description = \"检测图片中是否出现角色『弥音』的面部/头部形象\"\n"
    "# conf = 0.35\n"
    "# 注意: 手写注释与自定义字段会被保留,不会被程序覆盖。\n"
)

_SAFE_ID_RE = re.compile(r"[^\w-]")


def slugify(name: str) -> str:
    """把文件名转成安全的模型 id(保留中文与字母数字下划线)。

    纯点文件名(如 .onnx / ...)没有有效名称,兜底返回 "model"。
    """
    stem = Path(name).stem
    if stem.startswith("."):
        return "model"
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
    removed: int = 0
    missing: int = 0
    unconfigured: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"扫描模型目录: {self.scanned} 个模型,"
            f"新增登记 {self.added} 个,移除 {self.removed} 个,缺失 {self.missing} 个"
        ]
        if self.unconfigured:
            lines.append("以下模型未填写描述(请编辑 models.toml 补填 description):")
            lines.extend(f"  - {item}" for item in self.unconfigured)
        for error in self.errors:
            lines.append(f"  ! {error}")
        return "\n".join(lines)


def _to_float(value: Any, default: float) -> float:
    try:
        result = float(value)
        return result if result == result else default  # 拒绝 nan
    except (TypeError, ValueError, OverflowError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off"):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class ModelLibrary:
    """ONNX 模型目录 ↔ models.toml 索引库(进程内单例,幂等刷新)。"""

    def __init__(self, models_dir: str | Path, index_file: str | Path):
        self._models_dir = Path(models_dir)
        self._index_file = Path(index_file)
        self._entries: list[ModelEntry] = []
        self._config = LibraryConfig()
        self._lock = threading.Lock()
        self._fingerprint: tuple[int, tuple[tuple[str, int, int], ...]] | None = None

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
        try:
            return sorted(
                path
                for path in self._models_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".onnx"
            )
        except OSError:
            return []

    def _model_signatures(self) -> tuple[tuple[str, int, int], ...]:
        """模型文件签名:(文件名, mtime_ns, size)。

        纳入文件自身 mtime/size,同名覆盖(更新模型权重)时才能感知变化,
        否则热重载会静默使用旧模型。
        """
        signatures: list[tuple[str, int, int]] = []
        for path in self._scan_files():
            try:
                stat = path.stat()
                signatures.append((path.name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                signatures.append((path.name, -1, -1))
        return tuple(signatures)

    def _current_fingerprint(self) -> tuple[int, tuple[tuple[str, int, int], ...]]:
        models = self._model_signatures()
        try:
            mtime = self._index_file.stat().st_mtime_ns if self._index_file.exists() else -1
        except OSError:
            mtime = -1
        return (mtime, models)

    def needs_refresh(self) -> bool:
        """目录文件或索引 mtime 是否变化(廉价检查,每次调用前使用)。"""
        return self._fingerprint != self._current_fingerprint()

    # ── 索引读写 ──

    def _load_index(self) -> dict[str, Any]:
        """读取索引;解析失败时备份损坏文件并返回空(由 refresh 重建骨架)。

        损坏文件的用户内容无法恢复,但绝不静默覆盖:原始文件被备份为
        `models.toml.corrupt.<时间戳>`,并在 ScanReport.errors 中提示。
        """
        try:
            import tomlkit

            doc = tomlkit.parse(self._index_file.read_text(encoding="utf-8"))
            return {"root": doc}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            backup = self._backup_corrupt_index()
            return {"root": None, "parse_error": str(exc), "backup": str(backup)}

    def _backup_corrupt_index(self) -> Path:
        backup = self._index_file.with_name(
            f"{self._index_file.name}.corrupt.{int(time.time())}"
        )
        try:
            self._index_file.replace(backup)
        except OSError:
            pass
        return backup

    def refresh(self, force: bool = False) -> ScanReport:
        """扫描 models/ 目录并与索引合并,幂等。

        Args:
            force: 强制重建:清除索引中文件已不存在的条目(幽灵清理),
                  并重新生成骨架(保留用户已填写的字段)。
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
            if loaded.get("parse_error"):
                report.errors.append(
                    f"索引文件解析失败,已备份为 {loaded.get('backup')},索引已重建为骨架"
                )
        library = root.get("library", {})
        if not isinstance(library, dict):
            library = root["library"] = {}
        # 读取用户保留的默认参数(类型错误时保持程序默认并提示)
        conf = _to_float(library.get("default_conf"), self._config.default_conf)
        iou = _to_float(library.get("default_iou"), self._config.default_iou)
        imgsz = _to_int(library.get("imgsz"), self._config.imgsz)
        self._config = LibraryConfig(default_conf=conf, default_iou=iou, imgsz=imgsz)
        # 注意:不整体替换 library 表(会丢注释),由 _write_index 增量更新键

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

        disk_names: set[str] = set()
        for path in files:
            file_name = path.name
            disk_names.add(file_name)
            if file_name not in merged:
                entry = self._make_skeleton(file_name)
                merged[file_name] = entry.as_dict()
                report.added += 1
            else:
                self._merge_existing(file_name, merged[file_name])

        removed_files: set[str] = set()
        if force:
            # 强制重建:清除文件已不存在的条目
            for file_name in [name for name in merged if name not in disk_names]:
                removed_files.add(file_name)
                merged.pop(file_name, None)
                report.removed += 1
        else:
            # 常规刷新:文件缺失的条目保留(供用户看到),missing 状态运行时推断
            report.missing = sum(1 for name in merged if name not in disk_names)

        # 构建 entries 并处理重复 id(重复者追加序号,写回索引)
        entries: list[ModelEntry] = []
        used_ids: dict[str, int] = {}
        for file_name in sorted(merged):
            raw = merged[file_name]
            entry = ModelEntry(file=file_name, id=str(raw.get("id") or slugify(file_name)))
            for f in dataclass_fields(entry):
                if f.name in ("file", "id", "auto_generated", "missing", "unconfigured", "error"):
                    continue
                if f.name == "classes":
                    value = raw.get(f.name, f.default)
                    if isinstance(value, list):
                        entry.classes = [str(item) for item in value]
                    elif isinstance(value, str) and value.strip():
                        entry.classes = [item.strip() for item in value.split(",") if item.strip()]
                elif f.name in ("conf", "iou"):
                    raw_value = raw.get(f.name)
                    if raw_value is not None:
                        parsed = _to_float(raw_value, float("nan"))
                        if parsed == parsed:  # 解析成功(非 NaN sentinel)
                            setattr(entry, f.name, parsed)
                elif f.name == "imgsz":
                    raw_value = raw.get(f.name)
                    if raw_value is not None:
                        parsed = _to_int(raw_value, -1)
                        if parsed >= 0:  # 解析成功
                            entry.imgsz = parsed
                elif f.name == "enabled":
                    entry.enabled = _to_bool(raw.get(f.name), True)
                else:
                    value = raw.get(f.name, f.default)
                    if value is not None:
                        setattr(entry, f.name, value)
            entry.missing = file_name not in disk_names  # 运行时推断,不依赖索引旧标记
            entry.auto_generated = not (entry.name or entry.description)
            entry.unconfigured = not entry.description.strip()
            if entry.unconfigured and entry.auto_generated:
                report.unconfigured.append(f"{entry.id} (file={entry.file})")
            if not entry.missing and entry.enabled:
                error = self._validate_entry(entry)
                if error:
                    entry.error = error
                    report.errors.append(f"{entry.id}: {error}")
            # 重复 id 处理:追加序号保证唯一,并提示(避免静默改写用户字段)
            unique_id = self._unique_id(entry.id, used_ids)
            if unique_id != entry.id:
                report.errors.append(
                    f"模型 id 重复,已自动改为 {unique_id}(原 {entry.id},file={entry.file})"
                )
                entry.id = unique_id
                merged[file_name]["id"] = unique_id
            entries.append(entry)

        self._write_index(root, report, models=merged, removed_files=removed_files)
        self._entries = entries
        self._fingerprint = self._current_fingerprint()
        return report

    @staticmethod
    def _unique_id(base: str, used: dict[str, int]) -> str:
        count = used.get(base, 0)
        used[base] = count + 1
        return f"{base}_{count + 1}" if count else base

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
        """校验模型文件存在且不是明显损坏的文件(轻量头检查)。

        ONNX 有两种形态:带 "ONNX" 魔数(onnx 库写入)与纯 protobuf
        (ultralytics 等直接导出)。protobuf 首字节应为合法 field 头
        (0x08/0x10/0x0A/0x12...),文本文件/空文件会在此被拦截。
        """
        path = self._models_dir / entry.file
        if not path.exists():
            return f"模型文件不存在: {path}"
        try:
            with open(path, "rb") as handle:
                header = handle.read(8)
            size = path.stat().st_size
        except OSError as exc:
            return f"模型文件不可读: {exc}"
        if header[:4] == b"ONNX":
            return ""
        # protobuf 合法 field 头:field 1-2(wire type 0 或 2),且文件不是空壳
        if header and header[0] in (0x08, 0x10, 0x0A, 0x12) and size >= 1024:
            return ""
        return f"模型文件不是有效的 ONNX 格式(文件头异常): {entry.file}"

    # 程序管理的条目字段(写回时只动这些,保留用户自定义键与注释)
    _MANAGED_KEYS = frozenset(
        {"file", "id", "name", "description", "classes", "conf", "iou", "imgsz", "enabled"}
    )

    def _write_index(
        self,
        root: Any,
        report: ScanReport,
        *,
        models: dict[str, dict[str, Any]],
        removed_files: set[str],
    ) -> None:
        """增量写回索引:保留用户手写注释与自定义字段;写入失败不崩溃,记录错误。"""
        from tomlkit import dumps, table as make_table

        try:
            # library 段:只更新程序管理键,保留表注释
            library = root.get("library")
            if isinstance(library, dict):
                for key, value in self._config.as_dict().items():
                    library[key] = value
            else:
                root["library"] = self._config.as_dict()

            # models 段:已有条目增量更新字段,新增条目追加,删除条目移除
            aot = root.get("models")
            if aot is None:
                from tomlkit import aot as make_aot

                aot = root["models"] = make_aot()
            seen: set[str] = set()
            for table in list(aot):
                if not isinstance(table, dict):
                    continue
                file_name = str(table.get("file") or "")
                seen.add(file_name)
                if file_name in removed_files:
                    aot.remove(table)
                    continue
                data = models.get(file_name)
                if data is None:
                    continue
                for key in self._MANAGED_KEYS:
                    if key in data:
                        table[key] = data[key]
                    elif key in table and key not in ("file", "id"):
                        del table[key]
            for file_name, data in models.items():
                if file_name in seen:
                    continue
                table = make_table()
                for key, value in data.items():
                    table[key] = value
                aot.append(table)

            text = dumps(root)
            if not text.lstrip().startswith("#"):
                text = INDEX_HEADER + text
            self._index_file.parent.mkdir(parents=True, exist_ok=True)
            # 内容无变化时跳过写盘,避免 mtime 抖动引发反复刷新
            if self._index_file.exists():
                try:
                    if self._index_file.read_text(encoding="utf-8") == text:
                        return
                except OSError:
                    pass
            self._index_file.write_text(text, encoding="utf-8")
        except OSError as exc:
            report.errors.append(f"索引写入失败(只读或权限问题): {exc}")

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
