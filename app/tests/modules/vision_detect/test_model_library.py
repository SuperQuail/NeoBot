"""模型库(TOML 索引)单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from neobot_app.vision_detect.model_library import ModelLibrary, slugify


def _write_model(models_dir: Path, name: str = "miyin_yolo_320.onnx") -> Path:
    path = models_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ONNX\x00\x00\x00\x08fake-model")
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
    assert lib.resolve("miyin_yolo_320") is None
    assert lib.enabled_entries() == []


def test_missing_file_restored_auto_revives(library: tuple) -> None:
    """文件删除后恢复,模型应自动复活(不必手动编辑索引)。"""
    lib, models_dir, _index_file = library
    _write_model(models_dir)
    lib.refresh()
    (models_dir / "miyin_yolo_320.onnx").unlink()
    lib.refresh()
    assert lib.resolve("miyin_yolo_320") is None
    # 恢复文件
    _write_model(models_dir)
    report = lib.refresh()
    assert report.missing == 0
    entry = lib.get("miyin_yolo_320")
    assert entry is not None
    assert entry.missing is False
    assert lib.resolve("miyin_yolo_320") is not None
    assert lib.enabled_entries() == [entry]


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


def test_corrupt_index_backs_up_and_recovers(library: tuple) -> None:
    """索引损坏时:备份损坏文件、重建骨架、报告错误,不静默吞掉。"""
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    # 用户填写内容
    doc = _read_toml(index_file)
    doc["models"][0]["description"] = "用户的重要描述"
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    # 写坏
    index_file.write_text("[[[[ 这不是合法 toml", encoding="utf-8")
    report = lib.refresh()
    assert report.errors, "损坏索引应产生错误报告"
    assert lib.get("miyin_yolo_320") is not None  # 重建骨架后模型仍可用
    # 损坏文件被备份
    backups = list(index_file.parent.glob("models.toml.corrupt.*"))
    assert backups, "损坏的索引文件应被备份"
    assert index_file.exists(), "索引文件应被重建"


def test_corrupt_index_backup_keeps_user_data(library: tuple) -> None:
    """损坏文件中保留的用户内容可通过备份找回。"""
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    # 用户填写描述后文件被截断损坏(合法头部 + 用户内容 + 非法尾部)
    index_file.write_text(
        "[[models]]\n"
        'file = "miyin_yolo_320.onnx"\n'
        'description = "用户的重要描述"\n'
        "{ broken tail",
        encoding="utf-8",
    )
    lib.refresh()
    backups = list(index_file.parent.glob("models.toml.corrupt.*"))
    assert backups
    content = backups[0].read_text(encoding="utf-8")
    assert "用户的重要描述" in content


def test_force_removes_ghost_entries(library: tuple) -> None:
    lib, models_dir, _index_file = library
    _write_model(models_dir, "a.onnx")
    lib.refresh()
    (models_dir / "a.onnx").unlink()
    # 常规刷新:条目保留(标记 missing)
    report = lib.refresh()
    assert report.missing == 1
    assert lib.get("a") is not None
    # force:清除幽灵条目
    report = lib.refresh(force=True)
    assert report.removed == 1
    assert lib.get("a") is None


def test_duplicate_slug_ids_get_suffixes(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir, "a b.onnx")
    _write_model(models_dir, "a_b.onnx")
    lib.refresh()
    ids = [entry.id for entry in lib.entries()]
    assert len(ids) == len(set(ids)) == 2
    assert "a_b" in ids
    doc = _read_toml(index_file)
    file_ids = [m["id"] for m in doc["models"]]
    assert len(file_ids) == len(set(file_ids))


def test_bad_field_types_do_not_crash(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    doc = _read_toml(index_file)
    doc["library"]["default_conf"] = "abc"
    doc["models"][0]["conf"] = "abc"
    doc["models"][0]["imgsz"] = "large"
    doc["models"][0]["enabled"] = "false"
    doc["models"][0]["classes"] = "猫,狗"
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    lib.refresh()
    entry = lib.get("miyin_yolo_320")
    assert entry is not None
    assert entry.conf is None  # 非法 conf 回退
    assert entry.imgsz is None  # 非法 imgsz 回退
    assert entry.enabled is False  # 字符串 false 正确解析
    assert entry.classes == ["猫", "狗"]  # 逗号字符串转列表


def test_slugify_edge_cases() -> None:
    assert slugify(".onnx") == "model"
    assert slugify("...") == "model"


def test_refresh_without_changes_does_not_rewrite(library: tuple) -> None:
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    lib.refresh()
    mtime1 = index_file.stat().st_mtime_ns
    lib.refresh()
    mtime2 = index_file.stat().st_mtime_ns
    assert mtime1 == mtime2, "无变化时不应重写索引文件"


def test_model_file_replacement_detected(library: tuple) -> None:
    """同名覆盖模型文件(更新权重)应被感知为变化。"""
    lib, models_dir, _index_file = library
    _write_model(models_dir)
    lib.refresh()
    assert lib.needs_refresh() is False
    # 同名覆盖(内容与 mtime 都变化)
    path = models_dir / "miyin_yolo_320.onnx"
    import time as _time

    _time.sleep(0.01)
    path.write_bytes(b"ONNX\x00\x00\x00\x08new-model-content")
    assert lib.needs_refresh() is True, "模型文件被替换后应触发刷新"
    lib.refresh()
    assert lib.needs_refresh() is False


def test_user_comments_and_custom_fields_preserved(library: tuple) -> None:
    """用户手写注释与自定义字段在刷新后应被保留。"""
    lib, models_dir, index_file = library
    _write_model(models_dir)
    lib.refresh()
    # 用户添加注释、自定义字段、library 注释
    index_file.write_text(
        "# 用户文件头注释\n"
        "[library]  # 用户 library 注释\n"
        "default_conf = 0.35\n"
        "custom_flag = \"keep-me\"\n"
        "\n"
        "[[models]]  # 用户条目注释\n"
        'file = "miyin_yolo_320.onnx"\n'
        'id = "miyin_yolo_320"\n'
        'description = "我的描述"\n'
        'custom_note = "我的备注"\n'
        "# 条目尾部注释\n",
        encoding="utf-8",
    )
    lib.refresh()
    content = index_file.read_text(encoding="utf-8")
    assert "用户文件头注释" in content
    assert "用户 library 注释" in content
    assert 'custom_flag = "keep-me"' in content
    assert "用户条目注释" in content
    assert 'custom_note = "我的备注"' in content
    assert "条目尾部注释" in content
    # 用户字段保留
    entry = lib.get("miyin_yolo_320")
    assert entry is not None and entry.description == "我的描述"


def test_invalid_onnx_marked_as_error(library: tuple) -> None:
    """损坏的模型文件(文本/空文件)应在扫描时被标记 error 并排除。"""
    lib, models_dir, _index_file = library
    bad = models_dir / "bad.onnx"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("this is not a real onnx model", encoding="utf-8")
    report = lib.refresh()
    assert report.errors, "损坏模型应产生错误报告"
    entry = lib.get("bad")
    assert entry is not None
    assert entry.error
    assert lib.resolve("bad") is None
    assert lib.enabled_entries() == []


def test_protobuf_onnx_without_magic_accepted(library: tuple) -> None:
    """无 ONNX 魔数的纯 protobuf 模型(ultralytics 导出)应被接受。"""
    lib, models_dir, _index_file = library
    path = models_dir / "proto.onnx"
    path.parent.mkdir(parents=True, exist_ok=True)
    # protobuf field 头 + 足够大小
    path.write_bytes(b"\x08\x07\x12\x07pytorch" + b"\x00" * 2048)
    report = lib.refresh()
    assert not report.errors, f"合法 protobuf 模型不应报错: {report.errors}"
    assert lib.resolve("proto") is not None
