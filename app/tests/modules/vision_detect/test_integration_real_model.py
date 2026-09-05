"""真实模型集成测试:弥音_测试数据(4 张命中 + 1 张干扰图不命中)。

依赖:
- 模型文件:`app/data/vision_detect/models/miyin_yolo_320.onnx`
  (由 `neobot init` 登记,last.pt 重新导出的最新训练权重)
  可通过环境变量 NEOBOT_VISION_MODEL_PATH 覆盖
- 测试数据:默认 `D:/Code/Python/Yolo/dataset/弥音_测试数据`
  可通过环境变量 NEOBOT_VISION_TEST_DATA_DIR 覆盖

模型或数据缺失时测试自动跳过(CI 环境无模型不失败)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from neobot_app.core import DATA_DIR
from neobot_app.vision_detect.model_library import ModelLibrary

# 干扰图(不应检出)
NEGATIVE_IMAGE = "A5B18E5758DD29C6E71B28B1F34E495B.png"
# 应检出的图片(文件名 → 最低置信度断言)
POSITIVE_IMAGES = {
    "C860162067F864DA7A83304E17998A7E.png": 0.80,
    "QQ20260808-074744.png": 0.80,
    "QQ20260808-074826.png": 0.80,
    "QQ20260808-074834.png": 0.80,
}


def _model_path() -> Path:
    env = os.getenv("NEOBOT_VISION_MODEL_PATH")
    if env:
        return Path(env)
    return DATA_DIR / "vision_detect" / "models" / "miyin_yolo_320.onnx"


def _test_data_dir() -> Path:
    env = os.getenv("NEOBOT_VISION_TEST_DATA_DIR")
    if env:
        return Path(env)
    return Path(r"D:/Code/Python/Yolo/dataset/弥音_测试数据")


def _index_file() -> Path:
    return DATA_DIR / "vision_detect" / "models.toml"


@pytest.fixture(scope="module")
def detector():
    model_path = _model_path()
    data_dir = _test_data_dir()
    if not model_path.exists():
        pytest.skip(f"模型不存在(跳过真实模型集成测试): {model_path}")
    if not data_dir.is_dir():
        pytest.skip(f"测试数据目录不存在(跳过真实模型集成测试): {data_dir}")

    from neobot_app.vision_detect.engine import OnnxDetector, resolve_names

    library = ModelLibrary(model_path.parent, _index_file())
    entry = next((e for e in library.entries() if e.file == model_path.name), None)
    names = list(entry.classes) if entry and entry.classes else resolve_names(model_path)
    det = OnnxDetector(
        model_path,
        names=names,
        conf=0.35,
        iou=0.45,
    )
    from PIL import Image

    det.detect(Image.new("RGB", (64, 64)))  # warmup
    return det, data_dir


def _top_conf(dets: list[dict]) -> float:
    return max((d["conf"] for d in dets), default=0.0)


def test_negative_image_not_detected(detector) -> None:
    """干扰图不应检出(默认阈值 0.35 下无命中)。"""
    det, data_dir = detector
    dets, _ = det.detect(
        __import__("PIL").Image.open(data_dir / NEGATIVE_IMAGE).convert("RGB")
    )
    assert _top_conf(dets) < 0.35, f"干扰图被误检: {dets}"


def test_positive_images_detected_with_high_confidence(detector) -> None:
    """其余 4 张都应检出,且置信度达标。"""
    from PIL import Image

    det, data_dir = detector
    for name, min_conf in POSITIVE_IMAGES.items():
        image_path = data_dir / name
        if not image_path.exists():
            pytest.skip(f"测试图片缺失: {image_path}")
        dets, _ = det.detect(Image.open(image_path).convert("RGB"))
        conf = _top_conf(dets)
        assert conf >= min_conf, f"{name} 未达标: 最高置信度 {conf:.3f} < {min_conf}"


def test_full_service_flow_with_real_model(detector) -> None:
    """走完整服务链路(VisionDetectService)验证 4+1 区分。"""

    det, data_dir = detector
    from neobot_app.vision_detect.service import VisionDetectService

    service = VisionDetectService(_model_path().parent, _index_file(), auto_refresh=False)
    service.refresh()
    assert service.available

    for name in POSITIVE_IMAGES:
        result = service.detect_bytes((data_dir / name).read_bytes())
        assert result["ok"] is True
        hits = [d for r in result["results"] for d in r["detections"]]
        assert hits, f"{name} 未检出任何目标"
        assert hits[0]["conf"] >= 0.80, f"{name} 置信度不足: {hits[0]['conf']:.3f}"

    negative_result = service.detect_bytes((data_dir / NEGATIVE_IMAGE).read_bytes())
    assert negative_result["ok"] is True
    hits = [d for r in negative_result["results"] for d in r["detections"]]
    assert not hits, f"干扰图被误检: {hits}"
