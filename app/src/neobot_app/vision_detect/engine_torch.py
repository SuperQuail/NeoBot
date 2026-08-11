"""PyTorch YOLO 推理引擎(onnxruntime 不可用时的备选推理栈)。

背景:onnxruntime 在部分部署环境(虚拟机未透传 CPU 指令集 / VC++ 运行库
不全等)会 DLL 初始化失败(错误码 1114),本地视觉检测整体不可用。
本模块改用 PyTorch CPU 推理直接运行 YOLO 权重(.pt),不依赖 onnxruntime。

依赖(可选):`pip install ultralytics`(自带 torch CPU 版)。
未安装时相关模型条目会报错并提示安装,不影响其他引擎。

接口与 OnnxDetector 对齐:detect(pil_img, imgsz, conf, iou) → (dets, elapsed_ms)。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

__all__ = ["TorchYoloDetector"]


class TorchYoloDetector:
    """单模型 PyTorch YOLO 检测器(CPU,ultralytics 引擎)。

    - 模型文件:ultralytics 训练的 .pt 权重(内含架构与类别名)
    - 首次 predict 会加载权重(耗时),后续复用
    - 输出 dets 结构与 OnnxDetector 一致
    """

    def __init__(
        self,
        model_path: str | Path,
        names: Sequence[str] | None = None,
        conf: float = 0.35,
        iou: float = 0.45,
        imgsz: int = 0,
    ):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"模型不存在: {self.model_path}")
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self._model = None
        self._built_in_names: dict[int, str] | None = None
        self._custom_names: list[str] | None = list(names) if names else None

    def _load(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "PyTorch 后端不可用:未安装 ultralytics。"
                "请运行 `pip install ultralytics` 后重试(onnxruntime 不可用环境下的备选推理栈)。"
            ) from exc
        try:
            self._model = YOLO(str(self.model_path))
        except Exception as exc:
            raise RuntimeError(f"PyTorch 模型加载失败({self.model_path.name}): {exc}") from exc
        try:
            names = self._model.names
            if isinstance(names, dict):
                self._built_in_names = {int(k): str(v) for k, v in names.items()}
            elif isinstance(names, list):
                self._built_in_names = {i: str(v) for i, v in enumerate(names)}
        except Exception:
            self._built_in_names = None

    def _name_for(self, cls_id: int) -> str:
        if self._custom_names:
            if cls_id < len(self._custom_names):
                return self._custom_names[cls_id]
            return str(cls_id)
        if self._built_in_names and cls_id in self._built_in_names:
            return self._built_in_names[cls_id]
        return str(cls_id)

    def detect(
        self,
        pil_img: Image.Image,
        imgsz: int | None = None,
        conf: float | None = None,
        iou: float | None = None,
    ) -> tuple[list[dict[str, Any]], float]:
        self._load()
        conf = conf if conf is not None else self.conf
        iou = iou if iou is not None else self.iou
        imgsz = imgsz or self.imgsz or 640
        array = np.asarray(pil_img.convert("RGB"))
        t0 = time.perf_counter()
        results = self._model.predict(
            array,
            device="cpu",
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        dets: list[dict[str, Any]] = []
        if not results:
            return dets, elapsed_ms
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return dets, elapsed_ms
        data = boxes.data
        if hasattr(data, "cpu"):
            data = data.cpu().numpy()
        else:
            data = np.asarray(data)
        if data.ndim != 2 or data.shape[1] < 6:
            return dets, elapsed_ms
        for row in data:
            x1, y1, x2, y2 = [float(v) for v in row[:4]]
            score = float(row[4])
            cls_id = int(row[5])
            dets.append(
                {
                    "cls": cls_id,
                    "name": self._name_for(cls_id),
                    "conf": score,
                    "box": (x1, y1, x2, y2),
                }
            )
        dets.sort(key=lambda d: d["conf"], reverse=True)
        return dets, elapsed_ms
