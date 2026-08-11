"""本地视觉检测(YOLO,onnxruntime / PyTorch 双推理栈)服务包。"""

from neobot_app.vision_detect.engine import OnnxDetector, resolve_names
from neobot_app.vision_detect.engine_torch import TorchYoloDetector
from neobot_app.vision_detect.model_library import ModelEntry, ModelLibrary, ScanReport
from neobot_app.vision_detect.service import DetectionError, VisionDetectService

__all__ = [
    "OnnxDetector",
    "TorchYoloDetector",
    "resolve_names",
    "ModelEntry",
    "ModelLibrary",
    "ScanReport",
    "VisionDetectService",
    "DetectionError",
]
