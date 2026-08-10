"""本地视觉检测(ONNX/YOLO)服务包。"""

from neobot_app.vision_detect.engine import OnnxDetector, describe_detections, resolve_names
from neobot_app.vision_detect.model_library import ModelEntry, ModelLibrary, ScanReport
from neobot_app.vision_detect.service import DetectionError, VisionDetectService

__all__ = [
    "OnnxDetector",
    "describe_detections",
    "resolve_names",
    "ModelEntry",
    "ModelLibrary",
    "ScanReport",
    "VisionDetectService",
    "DetectionError",
]
