"""ONNX 推理引擎单元测试(fake InferenceSession,不依赖真实模型)。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from neobot_app.vision_detect.engine import (
    OnnxDetector,
    letterbox,
    nms,
    resolve_names,
)


class _FakeValue:
    def __init__(self, name: str, shape: list | tuple) -> None:
        self.name = name
        self.shape = tuple(shape)


class _FakeSession:
    """伪造 onnxruntime InferenceSession:返回固定预测张量。"""

    def __init__(self, pred: np.ndarray, in_shape=(1, 3, 320, 320), out_shape=(1, 5, 2100)) -> None:
        self._pred = np.asarray(pred)
        self._in_shape = tuple(in_shape)
        self._out_shape = tuple(out_shape)
        self.runs: list[dict] = []

    def get_inputs(self) -> list[_FakeValue]:
        return [_FakeValue("images", self._in_shape)]

    def get_outputs(self) -> list[_FakeValue]:
        return [_FakeValue("output0", self._out_shape)]

    def run(self, _output_names, feed: dict) -> list[np.ndarray]:
        self.runs.append(feed)
        return [self._pred]


def _make_detector(
    pred: np.ndarray,
    in_shape=(1, 3, 320, 320),
    out_shape=(1, 5, 2100),
    names: list[str] | None = None,
    conf: float = 0.35,
    iou: float = 0.45,
    out_layout: str | None | object = None,
) -> OnnxDetector:
    det = OnnxDetector.__new__(OnnxDetector)
    det.session = _FakeSession(pred, in_shape, out_shape)
    det.model_path = Path("fake.onnx")
    det.input_name = "images"
    det.imgsz = int(in_shape[2])
    det.dynamic = any(isinstance(s, str) for s in out_shape)
    det.nc = len(names) if names else max(1, int(out_shape[1]) - 4)
    det.names = list(names) if names else [f"cls{i}" for i in range(det.nc)]
    det.conf = conf
    det.iou = iou
    if out_layout is not None:
        det._out_layout = out_layout  # type: ignore[assignment]
    elif det.dynamic:
        det._out_layout = None
    elif isinstance(out_shape[1], int) and isinstance(out_shape[2], int):
        if out_shape[1] > out_shape[2] and out_shape[2] >= 6:
            det._out_layout = "xyxy"
        else:
            det._out_layout = "xywh"
    else:
        det._out_layout = "xywh"
    return det


def _img(size: int = 64) -> Image.Image:
    return Image.new("RGB", (size, size), (128, 128, 128))


def _xywh_anchor(cx: float, cy: float, w: float, h: float, conf: float, cls: int = 0, nc: int = 1) -> list[float]:
    row = [cx, cy, w, h]
    row += [conf if i == cls else 0.0 for i in range(nc)]
    return row


def _pred_xywh(anchors: list[list[float]]) -> np.ndarray:
    """把 [N, 5] anchor 列表转成 ultralytics 导出布局 [1, C, N]。"""
    return np.array([np.array(anchors, dtype=np.float32).T], dtype=np.float32)


# ── letterbox / nms / 坐标还原 ──


def test_letterbox_keeps_ratio_and_pads() -> None:
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    out, ratio, pad = letterbox(img, (320, 320))
    assert out.shape == (320, 320, 3)
    assert ratio == pytest.approx(1.6)  # min(320/100, 320/200)
    assert pad[0] == pytest.approx(0.0)  # dw(宽度方向 padding)
    assert pad[1] == pytest.approx(80.0)  # dh(高度方向 padding)


def test_nms_keeps_best_per_class() -> None:
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [100, 100, 110, 110]], dtype=float)
    scores = np.array([0.5, 0.9, 0.8])
    keep = nms(boxes, scores, iou_thr=0.45)
    assert keep == [1, 2]  # 0 与 1 重叠被抑制


def test_xywh_layout_single_class() -> None:
    """64x64 图,letterbox 到 320(无 padding),anchor 在原图中心。"""
    pred = _pred_xywh([_xywh_anchor(160, 160, 100, 100, 0.9)])
    det = _make_detector(pred, names=["target"], conf=0.35)
    dets, _ms = det.detect(_img())
    assert len(dets) == 1
    d = dets[0]
    assert d["name"] == "target"
    assert d["conf"] == pytest.approx(0.9)
    # 原图 64x64,ratio=5:中心 (32,32),宽高 20
    x1, y1, x2, y2 = d["box"]
    assert (x1, y1) == pytest.approx((22.0, 22.0))
    assert (x2, y2) == pytest.approx((42.0, 42.0))


def test_conf_filter_drops_low_confidence() -> None:
    pred = _pred_xywh(
        [
            _xywh_anchor(160, 160, 100, 100, 0.9),
            _xywh_anchor(50, 50, 40, 40, 0.2),
        ]
    )
    det = _make_detector(pred, conf=0.35)
    dets, _ = det.detect(_img())
    assert len(dets) == 1
    assert dets[0]["conf"] == pytest.approx(0.9)


def test_nms_merges_overlapping_anchors() -> None:
    pred = _pred_xywh(
        [
            _xywh_anchor(160, 160, 100, 100, 0.9),
            _xywh_anchor(170, 165, 110, 105, 0.7),
            _xywh_anchor(40, 40, 30, 30, 0.8),
        ]
    )
    det = _make_detector(pred, conf=0.35, iou=0.45)
    dets, _ = det.detect(_img())
    assert len(dets) == 2
    assert dets[0]["conf"] == pytest.approx(0.9)


def test_no_detections_returns_empty() -> None:
    pred = _pred_xywh([_xywh_anchor(160, 160, 100, 100, 0.05)])
    det = _make_detector(pred, conf=0.35)
    dets, _ = det.detect(_img())
    assert dets == []


def test_xyxy_layout() -> None:
    """[1, N, 6] NMS 导出布局(x1,y1,x2,y2,conf,cls,单类)。"""
    pred = np.array([[[10, 20, 30, 40, 0.8, 0.0]]], dtype=np.float32)
    det = _make_detector(pred, out_shape=(1, 1, 6), names=["target"], conf=0.35, out_layout="xyxy")
    dets, _ = det.detect(_img())
    assert len(dets) == 1
    assert dets[0]["conf"] == pytest.approx(0.8)
    x1, y1, x2, y2 = dets[0]["box"]
    assert (x1, y1) == pytest.approx((10.0 / 5, 20.0 / 5))
    assert (x2, y2) == pytest.approx((30.0 / 5, 40.0 / 5))


def test_multi_class_selects_best_class() -> None:
    pred = np.array(
        [
            [
                [160, 160, 100, 100, 0.9, 1.0],
                [160, 160, 100, 100, 0.9, 0.0],
            ]
        ],
        dtype=np.float32,
    )
    det = _make_detector(pred, out_shape=(1, 2, 6), names=["a", "b"], conf=0.35, out_layout="xyxy")
    dets, _ = det.detect(_img())
    assert len(dets) == 2  # 不同类别不互相抑制
    assert {d["name"] for d in dets} == {"a", "b"}


def test_infer_nc() -> None:
    assert OnnxDetector._infer_nc([1, 5, 2100]) == 1
    assert OnnxDetector._infer_nc([1, 6, 8400]) == 2
    assert OnnxDetector._infer_nc([1, 2100, 6]) == 2
    assert OnnxDetector._infer_nc([]) == 1


def test_names_fallback_when_not_provided() -> None:
    pred = _pred_xywh([_xywh_anchor(160, 160, 100, 100, 0.9)])
    det = _make_detector(pred, names=None, conf=0.35)
    assert det.names == ["cls0"]
    dets, _ = det.detect(_img())
    assert dets[0]["name"] == "cls0"


def test_multi_class_xywh_layout() -> None:
    """多类 xywh 导出(cols = 4 + nc >= 6)不应被误判为 NMS 布局。"""
    # nc=2,两个锚点各命中一类;布局 [1, C=6, N=2]
    anchors = [
        [160, 160, 100, 100, 0.30, 0.95],  # cls1 0.95
        [160, 160, 100, 100, 0.90, 0.05],  # cls0 0.90
    ]
    pred = np.array([np.array(anchors, dtype=np.float32).T], dtype=np.float32)
    det = _make_detector(pred, out_shape=(1, 6, 2), names=["a", "b"], conf=0.35)
    dets, _ = det.detect(_img())
    assert len(dets) == 2
    by_conf = {round(d["conf"], 2): d["name"] for d in dets}
    assert by_conf[0.95] == "b"
    assert by_conf[0.90] == "a"


def test_letterbox_extreme_aspect_ratio() -> None:
    """极端纵横比(如 1:1000)不应崩溃。"""
    for h, w in ((1, 1000), (1000, 1), (640, 1), (2, 2000)):
        img = np.zeros((h, w, 3), dtype=np.uint8)
        out, ratio, pad = letterbox(img, (320, 320))
        assert out.shape == (320, 320, 3)
        assert ratio > 0


def test_dynamic_shape_layout_detected_at_runtime() -> None:
    """动态 shape 模型(运行时输出 [1, N, 6] NMS 布局)应正确解析。"""
    pred = np.array(
        [
            [
                [10, 20, 30, 40, 0.8, 0.0],
                [50, 60, 70, 80, 0.7, 0.0],
            ]
        ],
        dtype=np.float32,
    )
    det = _make_detector(pred, out_shape=(1, "N", 6), names=["target"], conf=0.35, out_layout=None)
    dets, _ = det.detect(_img())
    assert len(dets) == 2
    assert dets[0]["conf"] == pytest.approx(0.8)


def test_dynamic_shape_xywh_layout_detected_at_runtime() -> None:
    """动态 shape 模型(运行时输出 [1, C, N] xywh 布局)应正确解析。"""
    pred = np.array([[[160, 160, 100, 100, 0.9]]], dtype=np.float32)  # [1, 5, 1]
    det = _make_detector(pred, out_shape=(1, 5, "N"), names=["target"], conf=0.35, out_layout=None)
    dets, _ = det.detect(_img())
    assert len(dets) == 1
    assert dets[0]["name"] == "target"


# ── resolve_names ──


def test_resolve_names_from_adjacent_data_yaml(tmp_path: Path) -> None:
    model = tmp_path / "weights" / "model.onnx"
    model.parent.mkdir()
    model.write_bytes(b"fake")
    (tmp_path / "weights" / "data.yaml").write_text(
        "names:\n  0: 弥音(面部识别)\n", encoding="utf-8"
    )
    assert resolve_names(model) == ["弥音(面部识别)"]


def test_resolve_names_from_classes_txt(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "classes.txt").write_text("cat\ndog\n", encoding="utf-8")
    assert resolve_names(model) == ["cat", "dog"]


def test_resolve_names_gbk_fallback(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "data.yaml").write_text(
        "names:\n  0: \u5f25\u97f3\n", encoding="gbk"
    )
    assert resolve_names(model) == ["\u5f25\u97f3"]


def test_resolve_names_none_when_missing(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    assert resolve_names(model) is None


def test_resolve_names_inline_list(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "data.yaml").write_text("names: [cat, dog, bird]\n", encoding="utf-8")
    assert resolve_names(model) == ["cat", "dog", "bird"]


def test_resolve_names_quoted_inline_list(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "data.yaml").write_text("names: ['猫', '狗']\n", encoding="utf-8")
    assert resolve_names(model) == ["猫", "狗"]


def test_resolve_names_dash_list(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "data.yaml").write_text(
        "names:\n  - cat\n  - dog\n", encoding="utf-8"
    )
    assert resolve_names(model) == ["cat", "dog"]


def test_resolve_names_inline_comment(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "data.yaml").write_text(
        "names:\n  0: cat  # 猫\n  1: dog\n", encoding="utf-8"
    )
    assert resolve_names(model) == ["cat", "dog"]
