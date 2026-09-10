"""VisionDetectService 单元测试(monkeypatch OnnxDetector,不依赖真实模型)。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from neobot_app.vision_detect.service import DetectionError, VisionDetectService


class _FakeDetector:
    """伪造 OnnxDetector:miyin 模型命中 0.92,其他模型不命中。

    为覆盖 all 模式,miyin 模型额外返回一条低置信度检测(0.05)。
    """

    def __init__(self, model_path: Path, names=None, conf=0.35, iou=0.45, imgsz=0) -> None:
        self.model_path = Path(model_path)
        self.names = list(names) if names else ["cls0"]
        self.conf = conf

    def detect(self, _pil: Image.Image, conf: float | None = None) -> tuple[list[dict], float]:
        threshold = conf if conf is not None else self.conf
        if self.model_path.name != "miyin_yolo_320.onnx":
            return [], 5.0
        dets = [
            {"cls": 0, "name": "弥音(面部识别)", "conf": 0.92, "box": (1, 2, 3, 4)},
            {"cls": 0, "name": "弥音(面部识别)", "conf": 0.05, "box": (10, 20, 30, 40)},
        ]
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
    (models_dir / "miyin_yolo_320.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    (models_dir / "other.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
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
    _pin_onnx_engine(monkeypatch)
    return _build_service(tmp_path)


def _pin_onnx_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """把推理引擎可用性固定为「onnx 可用、torch 不可用」。

    `onnx_available` / `torch_available` 是**惰性探测真实环境**的属性（首次访问
    真的去 import）。不固定的话，本组用例的行为取决于跑测试的机器：装了
    onnxruntime 就走到「没有可用的检测模型」，没装就提前在引擎检查处抛
    「本地推理引擎不可用」，断言随之失败——这会掩盖真正的回归。

    本文件测的是模型选择与检测逻辑，引擎可用性由引擎相关用例单独覆盖。
    """
    monkeypatch.setattr(
        "neobot_app.vision_detect.service.VisionDetectService.onnx_available",
        property(lambda _self: True),
    )
    monkeypatch.setattr(
        "neobot_app.vision_detect.service.VisionDetectService.torch_available",
        property(lambda _self: False),
    )


def _stub_onnxruntime(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 `import onnxruntime` 在本机成功（用一个空壳模块顶替）。

    用于需要**真实走一遍探测逻辑**的用例：`onnx_available` 靠 import 判定，
    所以这里替换的是 import 目标本身，而不是把探测结果写死。
    """
    import sys
    import types

    module = types.ModuleType("onnxruntime")
    monkeypatch.setitem(sys.modules, "onnxruntime", module)


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
    assert result["mode"] == "filter"
    assert result["checked_models"] == 2
    by_model = {r["model"]: r["detections"] for r in result["results"]}
    assert len(by_model["miyin_yolo_320"]) == 1  # filter 模式只显示 0.92
    assert by_model["other"] == []
    assert "检测到目标" in result["summary"]


def test_detect_mode_all_shows_all_detections(service: VisionDetectService) -> None:
    result = service.detect_pil(Image.new("RGB", (10, 10)), mode="all")
    assert result["mode"] == "all"
    by_model = {r["model"]: r["detections"] for r in result["results"]}
    assert len(by_model["miyin_yolo_320"]) == 2  # 0.92 + 0.05 全部显示
    assert "全部检测结果" in result["summary"]
    assert "未按置信度筛查" in result["summary"]


def test_detect_mode_all_ignores_min_conf(service: VisionDetectService) -> None:
    result = service.detect_pil(Image.new("RGB", (10, 10)), min_conf=0.9, mode="all")
    by_model = {r["model"]: r["detections"] for r in result["results"]}
    assert len(by_model["miyin_yolo_320"]) == 2


def test_detect_invalid_mode_raises(service: VisionDetectService) -> None:
    with pytest.raises(DetectionError, match="无效的 mode"):
        service.detect_pil(Image.new("RGB", (10, 10)), mode="weird")


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
    _pin_onnx_engine(monkeypatch)
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
    monkeypatch.setattr(service, "_torch_usable", False)
    with pytest.raises(DetectionError, match="本地推理引擎不可用"):
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
    monkeypatch.setattr(service, "_torch_usable", False)
    result = await service.inspect_image(_png_bytes())
    assert result is None


def test_hot_reload_picks_up_new_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    models_dir = tmp_path / "m"
    models_dir.mkdir(exist_ok=True)
    service = VisionDetectService(models_dir, tmp_path / "i.toml", auto_refresh=True)
    (models_dir / "a.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    service.refresh()
    ids = [m["id"] for m in service.list_models()]
    assert "a" in ids
    assert "b" not in ids
    (models_dir / "b.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    ids = [m["id"] for m in service.list_models()]
    assert "b" in ids


def test_detect_partial_failure_keeps_successes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """多模型部分失败:成功的模型结果保留,失败的标注在 failed_models。"""
    from neobot_app.vision_detect import service as service_module

    class _FlakyDetector(_FakeDetector):
        def detect(self, _pil, conf=None):
            if self.model_path.name == "bad.onnx":
                raise RuntimeError("模型损坏")
            return super().detect(_pil, conf)

    monkeypatch.setattr(service_module, "OnnxDetector", _FlakyDetector)
    _pin_onnx_engine(monkeypatch)
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "miyin_yolo_320.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    (models_dir / "bad.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    service = VisionDetectService(models_dir, tmp_path / "models.toml", auto_refresh=False)
    service.refresh()
    for entry in service._library.entries():
        entry.description = "测试模型"
    result = service.detect_pil(Image.new("RGB", (10, 10)))
    assert result["ok"] is True
    assert result["checked_models"] == 1  # 成功的模型
    assert result["failed_models"] and "bad" in result["failed_models"][0]
    assert any(r["model"] == "miyin_yolo_320" for r in result["results"])


def test_detect_all_models_fail_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    class _AllFlaky(_FakeDetector):
        def detect(self, _pil, conf=None):
            raise RuntimeError("全部失败")

    monkeypatch.setattr(service_module, "OnnxDetector", _AllFlaky)
    _pin_onnx_engine(monkeypatch)
    service = _build_service(tmp_path)
    with pytest.raises(DetectionError, match="所有模型推理失败"):
        service.detect_pil(Image.new("RGB", (10, 10)))


def test_close_marks_service_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = _build_service(tmp_path)
    service.close()
    assert service.available is False
    with pytest.raises(DetectionError, match="已关闭"):
        service.detect_pil(Image.new("RGB", (10, 10)))


def test_detect_model_ids_dedup(service: VisionDetectService) -> None:
    result = service.detect_pil(
        Image.new("RGB", (10, 10)), model_ids=["miyin_yolo_320", "miyin_yolo_320"]
    )
    assert result["checked_models"] == 1


def test_detect_model_ids_string_rejected(service: VisionDetectService) -> None:
    with pytest.raises(DetectionError, match="列表"):
        service.detect_pil(Image.new("RGB", (10, 10)), model_ids="miyin_yolo_320")


def test_detect_bytes_oversized_image_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = _build_service(tmp_path)
    service._max_pixels = 100  # 极小上限,2x2 图片即超限
    result = service.detect_bytes(_png_bytes())
    assert result["ok"] is False
    assert "过大" in result["error"]


def test_detect_bytes_applies_exif_orientation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EXIF 方向照片应被转正后再推理。"""
    from neobot_app.vision_detect import service as service_module

    seen: list = []

    class _RecordingDetector(_FakeDetector):
        def detect(self, pil, conf=None):
            seen.append(pil.size)
            return super().detect(pil, conf)

    monkeypatch.setattr(service_module, "OnnxDetector", _RecordingDetector)
    _pin_onnx_engine(monkeypatch)
    service = _build_service(tmp_path)
    # 构造带 Orientation=6(旋转90°)的 JPEG
    buf = io.BytesIO()
    img = Image.new("RGB", (20, 10), (100, 150, 200))
    exif = img.getexif()
    exif[274] = 6
    img.save(buf, format="JPEG", exif=exif)
    result = service.detect_bytes(buf.getvalue())
    assert result["ok"] is True
    assert seen, "检测器应被调用"
    assert seen[-1] == (10, 20), "EXIF 方向应被应用(20x10 → 10x20)"


def test_detect_bytes_min_conf_zero_outputs_all(service: VisionDetectService) -> None:
    """min_conf=0 应真正生效(零阈值,输出全部候选)。"""
    result = service.detect_bytes(_png_bytes(), min_conf=0.0)
    assert result["ok"] is True
    # 0.92 与 0.05 全部输出
    assert len(result["results"][0]["detections"]) == 2


def test_reset_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """环境修复后 reset_availability 必须能重新探测出「已可用」。

    探测逻辑本身要真实跑一遍，因此这里替换 import 目标、而不是把探测结果写死。
    起始状态显式构造成「探测已失败并缓存」(`_usable=False`)，这样结论不依赖
    跑测试的机器上 onnxruntime 是否可用 —— 否则就在断言里换了个地方继续依赖环境。
    """
    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    service = VisionDetectService(
        tmp_path / "models", tmp_path / "models.toml", auto_refresh=False
    )
    monkeypatch.setattr(service, "_usable", False)
    assert service.onnx_available is False
    _stub_onnxruntime(monkeypatch)

    service.reset_availability()

    assert service.onnx_available is True


def test_library_defaults_consumed_by_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """models.toml [library] 段的默认阈值应被服务消费(而非死配置)。"""
    import tomlkit

    from neobot_app.vision_detect import service as service_module

    monkeypatch.setattr(service_module, "OnnxDetector", _FakeDetector)
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "miyin_yolo_320.onnx").write_bytes(b"ONNX\x00\x00\x00\x08fake")
    index_file = tmp_path / "models.toml"
    service = VisionDetectService(models_dir, index_file, default_conf=0.35, auto_refresh=False)
    service.refresh()
    # 用户修改 [library] 默认阈值
    doc = tomlkit.parse(index_file.read_text(encoding="utf-8"))
    doc["library"]["default_conf"] = 0.9
    index_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    service.refresh()
    assert service._default_conf == pytest.approx(0.9)
    models = service.list_models()
    assert models[0]["conf"] == pytest.approx(0.9)

