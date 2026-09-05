"""TorchYoloDetector 单元测试(fake ultralytics,不依赖真实 torch 安装)。"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from neobot_app.vision_detect.engine_torch import TorchYoloDetector


class _FakeBoxes:
    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    def __len__(self) -> int:
        return len(self.data)


class _FakeResult:
    def __init__(self, data: np.ndarray) -> None:
        self.boxes = _FakeBoxes(data)


class _FakeYoloModel:
    def __init__(self, path: str, names) -> None:
        self.names = names
        self._last_kwargs: dict = {}

    def predict(self, source, **kwargs):
        self._last_kwargs = kwargs
        data = np.array(
            [
                [10.0, 20.0, 30.0, 40.0, 0.92, 0],
                [5.0, 5.0, 15.0, 15.0, 0.45, 1],
            ]
        )
        return [_FakeResult(data)]


def _install_fake_ultralytics(names, monkeypatch: pytest.MonkeyPatch) -> list:
    """把 fake ultralytics 注入 sys.modules(monkeypatch 自动还原),返回模型实例列表。"""
    created: list[_FakeYoloModel] = []

    def yolo_factory(path: str, **kwargs):
        model = _FakeYoloModel(path, names)
        created.append(model)
        return model

    fake_module = types.ModuleType("ultralytics")
    fake_module.YOLO = yolo_factory
    monkeypatch.setitem(sys.modules, "ultralytics", fake_module)
    return created


@pytest.fixture
def fake_pt(tmp_path: Path) -> Path:
    path = tmp_path / "miyin.pt"
    path.write_bytes(b"PK\x03\x04fake-model-content")
    return path


def test_detect_uses_builtin_names(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _install_fake_ultralytics({0: "miyin", 1: "other"}, monkeypatch)
    detector = TorchYoloDetector(fake_pt)
    dets, elapsed_ms = detector.detect(Image.new("RGB", (64, 64)))
    assert elapsed_ms >= 0
    assert [d["name"] for d in dets] == ["miyin", "other"]
    assert dets[0]["conf"] == pytest.approx(0.92)
    assert dets[0]["cls"] == 0
    assert dets[0]["box"] == pytest.approx((10.0, 20.0, 30.0, 40.0))
    assert created[0]._last_kwargs["device"] == "cpu"
    assert created[0]._last_kwargs["conf"] == 0.35
    assert created[0]._last_kwargs["imgsz"] == 640


def test_detect_custom_names_priority(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ultralytics({0: "miyin", 1: "other"}, monkeypatch)
    detector = TorchYoloDetector(fake_pt, names=["角色A", "角色B"])
    dets, _ = detector.detect(Image.new("RGB", (64, 64)))
    assert [d["name"] for d in dets] == ["角色A", "角色B"]


def test_detect_passes_conf_imgsz(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _install_fake_ultralytics({0: "a"}, monkeypatch)
    detector = TorchYoloDetector(fake_pt, conf=0.5, iou=0.6, imgsz=320)
    detector.detect(Image.new("RGB", (64, 64)))
    kwargs = created[0]._last_kwargs
    assert kwargs["conf"] == 0.5
    assert kwargs["iou"] == 0.6
    assert kwargs["imgsz"] == 320


def test_detect_empty_result(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = _install_fake_ultralytics({0: "a"}, monkeypatch)
    detector = TorchYoloDetector(fake_pt)
    detector.detect(Image.new("RGB", (64, 64)))  # 触发模型加载
    created[0].predict = lambda source, **kwargs: [_FakeResult(np.zeros((0, 6)))]
    dets, elapsed_ms = detector.detect(Image.new("RGB", (64, 64)))
    assert dets == []


def test_missing_ultralytics_raises(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ultralytics", None)
    detector = TorchYoloDetector(fake_pt)
    with pytest.raises(RuntimeError, match="ultralytics"):
        detector.detect(Image.new("RGB", (64, 64)))


def test_missing_model_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        TorchYoloDetector(tmp_path / "nope.pt")


def test_names_list_style(fake_pt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ultralytics(["cat", "dog"], monkeypatch)
    detector = TorchYoloDetector(fake_pt)
    dets, _ = detector.detect(Image.new("RGB", (64, 64)))
    assert [d["name"] for d in dets] == ["cat", "dog"]
