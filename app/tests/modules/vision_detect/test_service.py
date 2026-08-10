"""VisionDetectService 单元测试(monkeypatch OnnxDetector,不依赖真实模型)。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from neobot_app.vision_detect.service import DetectionError, VisionDetectService


class _FakeDetector:
    """伪造 OnnxDetector:miyin 模型命中 0.92,其他模型不命中。"""

    def __init__(self, model_path: Path, names=None, conf=0.35, iou=0.45, imgsz=0) -> None:
        self.model_path = Path(model_path)
        self.names = list(names) if names else ["cls0"]
        self.conf = conf

    def detect(self, _pil: Image.Image, conf: float | None = None) -> tuple[list[dict], float]:
        threshold = conf if conf is not None else self.conf
        if self.model_path.name != "miyin_yolo_320.onnx":
            return [], 5.0
        dets = [{"cls": 0, "name": "弥音(面部识别)", "conf": 0.92, "box": (1, 2, 3, 4)}]
        return [d for d in dets if d["conf"] >= threshold], 5.0


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(buf, format="PNG")
    return buf.getvalue()


def _build_service(
    tmp_path: Path, *, names: list[str] | None = None, auto_refresh: bool = False
) -> VisionDetectService:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "miyin_yolo_320.onnx").write_bytes(b"fake")
    (models_dir / "other.onnx").write_bytes(b"fake")
    service = VisionDetectService(
        models_dir, tmp_path / "models.toml", auto_refresh=auto_refresh
    )
    service.refresh()
    for entry in service._library.entries():
        entry.description = "测试模型"
    return service


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VisionDetectService:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    return _build_service(tmp_path)


def test_list_models_descriptions(service: VisionDetectService) -> None:
    models = service.list_models()
    ids = [m["id"] for m in models]
    assert "miyin_yolo_320" in ids
    assert "other" in ids
    assert all(m["description"] for m in models)
    assert "miyin_yolo_320" in str(service.list_models())


def test_detect_all_models(service: VisionDetectService) -> None:
    result = service.detect_pil(Image.new("RGB", (10, 10)))
    assert result["ok"] is True
    assert result["checked_models"] == 2
    by_model = {r["model"]: r["detections"] for r in result["results"]}
    assert len(by_model["miyin_yolo_320"]) == 1
    assert by_model["other"] == []
    assert "检测到目标" in result["summary"]


def test_detect_single_model_selection(service: VisionDetectService) -> None:
    result = service.detect_pil(Image.new("RGB", (10, 10)), model_ids=["other"])
    assert result["checked_models"] == 1
    assert result["results"][0]["model"] == "other"
    assert "未检测到任何目标" in result["summary"]


def test_detect_unknown_model_raises(service: VisionDetectService) -> None:
    with pytest.raises(DetectionError, match="未知模型"):
        service.detect_pil(Image.new("RGB", (10, 10)), model_ids=["nope"])


def test_detect_bytes_corrupt_image(service: VisionDetectService) -> None:
    result = service.detect_bytes(b"not-an-image")
    assert result["ok"] is False
    assert "无法解码" in result["error"]


def test_detect_bytes_min_conf_filter(service: VisionDetectService) -> None:
    result = service.detect_bytes(_png_bytes(), min_conf=0.95)
    assert result["ok"] is True
    assert result["results"][0]["detections"] == []


def test_detect_bytes_ok(service: VisionDetectService) -> None:
    result = service.detect_bytes(_png_bytes())
    assert result["ok"] is True
    assert result["summary"].startswith("检测到目标")


def test_available_false_when_no_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = VisionDetectService(tmp_path / "empty", tmp_path / "empty.toml", auto_refresh=False)
    service.refresh()
    assert service.available is False
    with pytest.raises(DetectionError, match="没有可用的检测模型"):
        service.detect_pil(Image.new("RGB", (10, 10)))


def test_onnx_unavailable_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = _build_service(tmp_path)
    monkeypatch.setattr(service, "_usable", False)
    with pytest.raises(DetectionError, match="onnxruntime 不可用"):
        service.detect_pil(Image.new("RGB", (10, 10)))


async def test_detect_bytes_async(service: VisionDetectService) -> None:
    result = await service.detect_bytes_async(_png_bytes())
    assert result["ok"] is True


async def test_inspect_image_returns_none_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = _build_service(tmp_path)
    monkeypatch.setattr(service, "_usable", False)
    result = await service.inspect_image(_png_bytes())
    assert result is None


def test_hot_reload_picks_up_new_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    models_dir = tmp_path / "m"
    models_dir.mkdir(exist_ok=True)
    service = VisionDetectService(models_dir, tmp_path / "i.toml", auto_refresh=True)
    (models_dir / "a.onnx").write_bytes(b"fake")
    service.refresh()
    ids = [m["id"] for m in service.list_models()]
    assert "a" in ids
    assert "b" not in ids
    (models_dir / "b.onnx").write_bytes(b"fake")
    ids = [m["id"] for m in service.list_models()]
    assert "b" in ids
