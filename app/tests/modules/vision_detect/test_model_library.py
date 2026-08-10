"""模型库(TOML 索引)单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from neobot_app.vision_detect.model_library import ModelLibrary, slugify


def _write_model(models_dir: Path, name: str = "miyin_yolo_320.onnx") -> Path:
    path = models_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-onnx")
    return path


def _read_toml(index_file: Path) -> dict:
    return tomlkit.parse(index_file.read_text(encoding="utf-8"))


@pytest.fixture
def library(tmp_path: Path) -> tuple[ModelLibrary, Path, Path]:
    models_dir = tmp_path / "models"
    index_file = tmp_path / "models.toml"
    return ModelLibrary(models_dir, index_file), models_dir, index_file


def test_slugify() -> None:
    assert slugify("miyin_yolo_320.onnx") == "miyin_yolo_320"
    assert slugify("弥音形象.onnx") == "弥音形象"  # 中文保留
    assert slugify("a b?.onnx") == "a_b"
    assert slugify("...") == "model"


def test_first_scan_creates_skeleton(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    report = lib.refresh()
    assert report.scanned == 1
    assert report.added == 1
    assert index_file.exists()
    doc = _read_toml(index_file)
    assert doc["library"]["default_conf"] == 0.35
    entries = doc["models"]
    assert len(entries) == 1
    assert entries[0]["file"] == "miyin_yolo_320.onnx"
    assert entries[0]["id"] == "miyin_yolo_320"
    assert lib.get("miyin_yolo_320") is not None


def test_refresh_is_idempotent(library: tuple) -> None:
    lib, models_dir, _index_file = library
    _write_model(models_dir)
    lib.refresh()
    report = lib.refresh()
    assert report.added == 0
    assert len(lib.entries()) == 1


def test_user_fields_not_overwritten(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    # 用户填写 description/name
    doc = _read_toml(index_file)
    doc["models"][0]["description"] = "检测弥音形象"
    doc["models"][0]["name"] = "弥音形象检测"
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    # 再次刷新不得覆盖
    report = lib.refresh()
    entry = lib.get("miyin_yolo_320")
    assert entry is not None
    assert entry.description == "检测弥音形象"
    assert entry.name == "弥音形象检测"
    assert entry.auto_generated is False
    assert report.unconfigured == []


def test_unconfigured_model_reported(library: tuple) -> None:
    lib, models_dir, _index_file = library
    _write_model(models_dir)
    report = lib.refresh()
    assert len(report.unconfigured) == 1
    assert "miyin_yolo_320" in report.unconfigured[0]


def test_missing_file_disables_entry(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    (models_dir / "miyin_yolo_320.onnx").unlink()
    report = lib.refresh()
    assert report.missing == 1
    entry = lib.get("miyin_yolo_320")
    assert entry is not None
    assert entry.missing is True
    assert entry.enabled is False
    assert lib.resolve("miyin_yolo_320") is None
    assert lib.enabled_entries() == []


def test_disabled_entry_excluded(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    doc = _read_toml(index_file)
    doc["models"][0]["enabled"] = False
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    lib.refresh()
    assert lib.enabled_entries() == []
    assert lib.resolve("miyin_yolo_320") is None


def test_corrupted_index_recovers(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    index_file.write_text("[[[[ 这不是合法 toml", encoding="utf-8")
    report = lib.refresh()
    assert report.scanned == 1
    assert lib.get("miyin_yolo_320") is not None


def test_classes_auto_resolved_from_data_yaml(library: tuple) -> None:
    lib, models_dir, _index_file = library
    _write_model(models_dir)
    (models_dir / "data.yaml").write_text(
        "names:\n  0: 弥音(面部识别)\n", encoding="utf-8"
    )
    lib.refresh()
    entry = lib.get("miyin_yolo_320")
    assert entry is not None
    assert entry.classes == ["弥音(面部识别)"]


def test_library_defaults_loadable(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    doc = _read_toml(index_file)
    doc["library"]["default_conf"] = 0.6
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    lib.refresh()
    assert lib.config.default_conf == pytest.approx(0.6)


def test_duplicate_id_kept_separate(library: tuple) -> None:
    lib, models_dir, _index_file = library
    _write_model(models_dir, "a.onnx")
    _write_model(models_dir, "b.onnx")
    lib.refresh()
    ids = [entry.id for entry in lib.entries()]
    assert len(ids) == 2
    assert len(set(ids)) == 2
