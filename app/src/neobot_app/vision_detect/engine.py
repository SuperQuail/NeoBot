"""ONNX YOLO 推理引擎。

移植自 Yolo 原型仓库(https://github.com/…/Yolo)的 OnnxDetector,
去除 UI/训练依赖,仅保留 onnxruntime + pillow + numpy 推理能力。

与原型相比的改进:
- 类别数从 ONNX 输出 shape 推断,类别名解析失败也不会崩溃(兜底 clsN)
- 类别名解析支持 UTF-8/GBK 编码容错与 classes.txt
- 输出布局判断更健壮(同时兼容 ultralytics 两种导出)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

__all__ = ["OnnxDetector", "letterbox", "nms", "resolve_names", "describe_detections"]


def letterbox(img: np.ndarray, new_shape: tuple[int, int] = (640, 640), color: tuple[int, int, int] = (114, 114, 114)):
    """等比缩放 + 灰边填充到 new_shape,返回 (img, ratio, (dw, dh))。"""
    shape = img.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw = (new_shape[1] - new_unpad[0]) / 2
    dh = (new_shape[0] - new_unpad[1]) / 2
    img = np.asarray(Image.fromarray(img).resize(new_unpad, Image.Resampling.BILINEAR))
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = np.pad(img, ((top, bottom), (left, right), (0, 0)), constant_values=color[0])
    return img, r, (dw, dh)


def scale_boxes(
    boxes_xyxy: np.ndarray,
    img_shape: tuple[int, int],
    orig_shape: tuple[int, int],
    ratio: float,
    pad: tuple[float, float],
) -> np.ndarray:
    """把 letterbox 坐标系下的 xyxy 框还原到原图坐标。"""
    dw, dh = pad
    boxes = boxes_xyxy.copy()
    boxes[:, [0, 2]] -= dw
    boxes[:, [1, 3]] -= dh
    boxes /= ratio
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, orig_shape[1])
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, orig_shape[0])
    return boxes


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float = 0.45) -> list[int]:
    """类别内 NMS,返回保留索引。"""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thr]
    return keep


def _read_text_loose(path: Path) -> str | None:
    """读取文本文件,UTF-8 失败时回退 GBK(早期数据集 data.yaml 为 GBK 编码)。"""
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _parse_names_from_yaml(text: str) -> list[str] | None:
    """解析 data.yaml 中的 names(兼容映射表与列表两种写法)。"""
    names: list[str] = []
    in_names = False
    bracket: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if bracket:
            if "]" in line:
                names.append(line.split("]", 1)[0].strip().strip("\"'"))
                bracket = None
            else:
                names.append(line.strip().strip("\"'"))
            continue
        if not in_names:
            if line.startswith("names:"):
                in_names = True
                rest = line[len("names:"):].strip()
                if rest.startswith("["):
                    bracket = "["
                    rest = rest[1:]
                    if "]" in rest:
                        names.append(rest.split("]", 1)[0].strip().strip("\"'"))
                        bracket = None
                    elif rest:
                        names.append(rest.strip().strip("\"'"))
            continue
        if not line:
            continue
        if ":" in line and not line.startswith("#"):
            if line[0].isdigit() or line[0] in "-":
                names.append(line.split(":", 1)[1].strip().strip("\"'"))
                continue
        if line.startswith("#") or any(key in line for key in ("train:", "val:", "test:")):
            continue
        names.append(line.strip().strip("\"'"))
    return names or None


def _parse_names_from_classes_txt(text: str) -> list[str] | None:
    names = [line.strip() for line in text.splitlines() if line.strip()]
    return names or None


def _try_names_files(candidates: Sequence[Path]) -> list[str] | None:
    for candidate in candidates:
        try:
            text = _read_text_loose(candidate)
        except OSError:
            continue
        if text is None:
            continue
        if candidate.name.lower() == "classes.txt":
            names = _parse_names_from_classes_txt(text)
        else:
            names = _parse_names_from_yaml(text)
        if names:
            return names
    return None


def resolve_names(
    model_path: str | Path,
    *,
    extra_candidates: Sequence[str | Path] | None = None,
) -> list[str] | None:
    """从模型旁的 data.yaml / args.yaml / classes.txt 解析类别名。

    查找顺序:
    1. 模型所在目录的 data.yaml / classes.txt
    2. 模型上一级目录(训练输出目录)的 data.yaml / classes.txt
    3. args.yaml 中 data 字段指向的 data.yaml
    4. extra_candidates(模型库调用方提供的目录/文件)
    """
    p = Path(model_path)
    base = p.parent
    candidates: list[Path] = [
        base / "data.yaml",
        base / "classes.txt",
        base.parent / "data.yaml",
        base.parent / "classes.txt",
    ]
    args_yaml = base.parent / "args.yaml"
    if args_yaml.exists():
        text = _read_text_loose(args_yaml) or ""
        for line in text.splitlines():
            if line.strip().startswith("data:"):
                ref = Path(line.split(":", 1)[1].strip().strip("\"'"))
                candidates.append(ref)
                candidates.append(ref.parent / "classes.txt")
                break
    for extra in extra_candidates or []:
        extra_path = Path(extra)
        candidates.append(extra_path)
        candidates.append(extra_path / "data.yaml")
        candidates.append(extra_path / "classes.txt")
    return _try_names_files(candidates)


class OnnxDetector:
    """单模型 ONNX YOLO 检测器(CPU)。

    输出 dets 结构: [{"cls": int, "name": str, "conf": float, "box": (x1, y1, x2, y2)}]
    第二返回值 elapsed_ms 为 session.run 耗时。
    """

    def __init__(
        self,
        model_path: str | Path,
        names: Sequence[str] | None = None,
        conf: float = 0.35,
        iou: float = 0.45,
        imgsz: int = 0,
    ):
        import onnxruntime as ort  # type: ignore[import-untyped]

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"模型不存在: {self.model_path}")
        self.session = ort.InferenceSession(
            str(self.model_path), providers=["CPUExecutionProvider"]
        )
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape
        self.dynamic = any(isinstance(s, str) for s in shape)
        if len(shape) == 4 and isinstance(shape[2], int):
            self.imgsz = int(shape[2])
        else:
            self.imgsz = 640
        if imgsz > 0:
            self.imgsz = int(imgsz)

        out_shape = self.session.get_outputs()[0].shape
        self._nc_from_output = self._infer_nc(out_shape)
        # 输出布局:ultralytics 标准导出为 [1, C, N](xywh);NMS 后处理导出为 [1, N, C]
        self._out_layout = "xywh"
        if len(out_shape) == 3 and isinstance(out_shape[1], int) and isinstance(out_shape[2], int):
            if out_shape[1] > out_shape[2]:
                self._out_layout = "xyxy"
        if names:
            self.nc = len(names)
            self.names = list(names)
        else:
            # 类别数从输出 shape 推断(5 列 = 4 坐标 + 1 类;N 列 = 5 + N-5 类)
            self.nc = self._nc_from_output
            self.names = [f"cls{i}" for i in range(self.nc)]
        self.conf = conf
        self.iou = iou

    @staticmethod
    def _infer_nc(out_shape: Sequence[int]) -> int:
        """从输出张量 shape 推断类别数(仅用于类别名兜底)。

        ultralytics 标准导出为 [1, C, N] xywh 布局,C = nc + 4;
        通道维 C 通常很小(单类 5,十类 14),锚点维 N 通常很大(数百以上)。
        取两个非批维中的较小者作为通道维,无法判定时保守取 1。
        """
        shape = [int(s) for s in out_shape if isinstance(s, int)]
        non_batch = [s for s in shape if s not in (1, 3)]
        if not non_batch:
            return 1
        if len(non_batch) == 1:
            channels = non_batch[0]
        else:
            channels = min(non_batch)
        if channels >= 6:
            return channels - 4
        if channels >= 5:
            return channels - 4
        return max(1, channels - 4)

    def detect(
        self,
        pil_img: Image.Image,
        imgsz: int | None = None,
        conf: float | None = None,
        iou: float | None = None,
    ) -> tuple[list[dict[str, Any]], float]:
        conf = conf if conf is not None else self.conf
        iou = iou if iou is not None else self.iou
        imgsz = imgsz or self.imgsz
        img = np.asarray(pil_img.convert("RGB"))
        orig_shape = img.shape[:2]
        img_letter, ratio, pad = letterbox(img, (imgsz, imgsz))
        blob = img_letter.transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        t0 = time.perf_counter()
        out = self.session.run(None, {self.input_name: blob})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        pred = out[0]
        if len(pred.shape) == 3:
            pred = pred[0]
        if self._out_layout == "xywh":
            # [C, N] → [N, C],每行一个锚点
            pred = pred.T
        cols = pred.shape[1]
        if cols >= 6:
            # NMS 后处理导出布局([N, 6]: x1,y1,x2,y2,conf,cls)
            boxes = pred[:, :4]
            confs = pred[:, 4]
            cls_ids = np.round(pred[:, 5]).astype(int)
        elif cols >= 5:
            # xywh 布局([N, 4+nc]: cx,cy,w,h,class_scores),类别数以实际列数为准
            scores = pred[:, 4:]
            cls_ids = scores.argmax(1)
            confs = scores[np.arange(len(scores)), cls_ids]
            boxes = pred[:, :4]
        else:
            return [], elapsed_ms

        mask = confs >= conf
        if not mask.any():
            return [], elapsed_ms
        boxes = boxes[mask]
        scores = confs[mask]
        cls_ids = cls_ids[mask]

        if self._out_layout == "xywh":
            # 中心宽高 → 左上右下坐标
            x1 = boxes[:, 0] - boxes[:, 2] / 2
            y1 = boxes[:, 1] - boxes[:, 3] / 2
            x2 = boxes[:, 0] + boxes[:, 2] / 2
            y2 = boxes[:, 1] + boxes[:, 3] / 2
            xyxy = np.stack([x1, y1, x2, y2], axis=1)
        else:
            xyxy = boxes

        keep_idx: list[int] = []
        for c in np.unique(cls_ids):
            idx = np.where(cls_ids == c)[0]
            keep_idx += [idx[i] for i in nms(xyxy[idx], scores[idx], iou)]
        keep = np.array(sorted(keep_idx)) if keep_idx else np.array([], dtype=int)
        if len(keep) == 0:
            return [], elapsed_ms

        xyxy_final = scale_boxes(xyxy[keep], img_letter.shape[:2], orig_shape, ratio, pad)
        dets: list[dict[str, Any]] = []
        for i, k in enumerate(keep):
            x1f, y1f, x2f, y2f = xyxy_final[i]
            cls_id = int(cls_ids[k])
            dets.append(
                {
                    "cls": cls_id,
                    "name": self.names[cls_id] if cls_id < len(self.names) else str(cls_id),
                    "conf": float(scores[k]),
                    "box": (float(x1f), float(y1f), float(x2f), float(y2f)),
                }
            )
        dets.sort(key=lambda d: d["conf"], reverse=True)
        return dets, elapsed_ms


def describe_detections(dets: Sequence[dict[str, Any]], min_conf: float = 0.0) -> str:
    """把检测结果转成中文描述(agent 友好)。"""
    text = []
    for d in dets:
        if d["conf"] < min_conf:
            continue
        x1, y1, x2, y2 = [int(v) for v in d["box"]]
        text.append(f"{d['name']} {d['conf']:.0%} 位置({x1},{y1})-({x2},{y2})")
    return "检测到: " + " | ".join(text) if text else "未检测到目标"
