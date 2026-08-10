"""VisionDetectService:YOLO/ONNX 图像检测服务。

- 进程内单例检测器池:按 (模型路径, 输入尺寸) 缓存 onnxruntime Session
- 热重载:每次调用前廉价检查模型目录/索引变化,变化时增量重建
- 模型可被 agent 主动选择:list_models() 提供每个模型的 id/name/description
- 备用接口 inspect_image():当前未接入自动图片解析链路,注释标明备用

线程安全:refresh 由锁保护;detect 调用方负责不阻塞事件循环(见 detect_bytes_async)。
"""

from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from neobot_app.vision_detect.engine import OnnxDetector
from neobot_app.vision_detect.model_library import ModelEntry, ModelLibrary, ScanReport

__all__ = ["VisionDetectService", "DetectionError"]


class DetectionError(RuntimeError):
    """检测失败(模型缺失/图片损坏/onnxruntime 不可用)。"""


class VisionDetectService:
    """本地 ONNX/YOLO 图像检测服务。"""

    def __init__(
        self,
        models_dir: str | Path,
        index_file: str | Path,
        *,
        default_conf: float = 0.35,
        default_iou: float = 0.45,
        imgsz: int = 0,
        auto_refresh: bool = True,
        logger: Any = None,
    ):
        self._library = ModelLibrary(models_dir, index_file)
        self._detectors: dict[tuple[str, int], OnnxDetector] = {}
        self._refresh_lock = threading.Lock()
        self._auto_refresh = auto_refresh
        self._logger = logger
        self._usable: bool | None = None
        self._default_conf = default_conf
        self._default_iou = default_iou
        self._default_imgsz = imgsz

    # ── 可用性 ──

    @property
    def onnx_available(self) -> bool:
        """onnxruntime 是否可用(不可用时服务整体禁用,skill 不注册)。"""
        if self._usable is None:
            try:
                import onnxruntime  # type: ignore[import-untyped]  # noqa: F401

                self._usable = True
            except Exception:
                self._usable = False
        return self._usable

    @property
    def available(self) -> bool:
        return self.onnx_available and bool(self._library.enabled_entries())

    def _log(self, message: str) -> None:
        if self._logger is not None:
            try:
                self._logger.warning(message)
            except Exception:
                pass

    # ── 模型库 ──

    def refresh(self, force: bool = False) -> ScanReport:
        """重新扫描模型目录与索引(幂等)。"""
        report = self._library.refresh(force=force)
        self._detectors.clear()
        for entry in report.unconfigured:
            self._log(f"vision_detect 模型未配置描述: {entry}")
        return report

    def _maybe_refresh(self) -> None:
        if self._auto_refresh and self._library.needs_refresh():
            try:
                with self._refresh_lock:
                    if self._library.needs_refresh():
                        self.refresh()
            except Exception as exc:
                self._log(f"vision_detect 自动刷新失败: {exc}")

    def list_models(self) -> list[dict[str, Any]]:
        """启用模型的元信息列表(供工具描述与 agent 选择模型)。"""
        self._maybe_refresh()
        result: list[dict[str, Any]] = []
        for entry in self._library.enabled_entries():
            result.append(
                {
                    "id": entry.id,
                    "name": entry.name or entry.id,
                    "description": entry.description,
                    "classes": list(entry.classes),
                    "conf": entry.conf if entry.conf is not None else self._default_conf,
                    "imgsz": entry.imgsz or self._default_imgsz,
                    "file": entry.file,
                }
            )
        return result

    def _entry_ids(self) -> list[str]:
        return [entry.id for entry in self._library.enabled_entries()]

    def _resolve_ids(self, model_ids: Sequence[str] | None) -> list[ModelEntry]:
        entries = self._library.enabled_entries()
        if not model_ids:
            return entries
        resolved: list[ModelEntry] = []
        unknown: list[str] = []
        for model_id in model_ids:
            entry = next((e for e in entries if e.id == model_id), None)
            if entry is None:
                unknown.append(model_id)
            else:
                resolved.append(entry)
        if unknown:
            raise DetectionError(
                f"未知模型: {', '.join(unknown)};可用模型: {', '.join(self._entry_ids()) or '无'}"
            )
        return resolved

    def _get_detector(self, entry: ModelEntry) -> OnnxDetector:
        imgsz = entry.imgsz or self._default_imgsz
        key = (entry.file, int(imgsz or 0))
        detector = self._detectors.get(key)
        if detector is None:
            detector = OnnxDetector(
                self._library.models_dir / entry.file,
                names=entry.classes or None,
                conf=entry.conf if entry.conf is not None else self._default_conf,
                iou=entry.iou if entry.iou is not None else self._default_iou,
                imgsz=imgsz,
            )
            self._detectors[key] = detector
        return detector

    # ── 检测接口(同步核心,调用方负责不阻塞事件循环) ──

    def detect_pil(
        self,
        pil_image: Image.Image,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
    ) -> dict[str, Any]:
        """对一张 PIL 图片运行指定模型(缺省 = 全部启用模型)。

        Returns:
            {
              "ok": True, "elapsed_ms": float, "checked_models": int,
              "results": [{"model", "model_name", "detections": [...]}],
              "summary": "中文摘要(agent 可直接使用)"
            }
        """
        if not self.onnx_available:
            raise DetectionError("onnxruntime 不可用,视觉检测服务未启用")
        self._maybe_refresh()
        entries = self._resolve_ids(model_ids)
        if not entries:
            raise DetectionError("没有可用的检测模型,请把 .onnx 放入模型目录并运行 `neobot init`")
        total_ms = 0.0
        results: list[dict[str, Any]] = []
        for entry in entries:
            try:
                dets, elapsed_ms = self._get_detector(entry).detect(
                    pil_image, conf=min_conf if min_conf is not None else None
                )
            except Exception as exc:
                raise DetectionError(f"模型 {entry.id} 推理失败: {exc}") from exc
            total_ms += elapsed_ms
            results.append(
                {
                    "model": entry.id,
                    "model_name": entry.name or entry.id,
                    "detections": dets,
                }
            )
        hits = [
            (result, det)
            for result in results
            for det in result["detections"]
        ]
        if hits:
            parts = []
            for result, det in hits:
                label = result["model_name"] if len(results) > 1 else result["model"]
                parts.append(f"{label}: {det['name']} 置信度 {det['conf']:.0%}")
            summary = "检测到目标: " + " | ".join(parts)
        else:
            summary = "未检测到任何目标"
        return {
            "ok": True,
            "elapsed_ms": round(total_ms, 2),
            "checked_models": len(results),
            "results": results,
            "summary": summary,
        }

    def detect_bytes(
        self,
        image_bytes: bytes,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
    ) -> dict[str, Any]:
        """对图片字节运行检测(自动解码,失败返回 ok=False)。"""
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            pil_image.load()
        except Exception as exc:
            return {"ok": False, "error": f"图片无法解码: {exc}"}
        try:
            return self.detect_pil(pil_image, model_ids=model_ids, min_conf=min_conf)
        except DetectionError as exc:
            return {"ok": False, "error": str(exc)}

    async def detect_bytes_async(
        self,
        image_bytes: bytes,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
    ) -> dict[str, Any]:
        """异步检测(线程池内执行,不阻塞事件循环)。"""
        return await asyncio.to_thread(
            self.detect_bytes, image_bytes, model_ids, min_conf
        )

    # ── 备用接口(当前未接入自动解析链路) ──

    async def inspect_image(
        self,
        image_bytes: bytes,
        *,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
    ) -> dict[str, Any] | None:
        """【备用接口,当前未启用】自动图片解析链路钩子。

        计划:未来在 app/src/neobot_app/image/parser.py 的 _parse_single_image
        视觉模型调用之前插入检测,命中时把结果并入图片描述文本。

        设计说明:
        - 本接口保持独立,不改变 parser.py 现有行为
        - 接入时以本接口返回的 summary 作为描述前缀或独立通知
        - 接口返回 None 表示服务不可用(调用方应静默跳过)
        """
        if not self.available:
            return None
        try:
            return await self.detect_bytes_async(
                image_bytes, model_ids=model_ids, min_conf=min_conf
            )
        except Exception:
            return None

    # ── 生命周期 ──

    def close(self) -> None:
        self._detectors.clear()
        self._library = ModelLibrary(self._library.models_dir, self._library.index_file)
