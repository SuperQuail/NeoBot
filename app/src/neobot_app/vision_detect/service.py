"""VisionDetectService:YOLO 图像检测服务。

- 进程内单例检测器池:按 (模型路径, 输入尺寸) 缓存检测器
- 双推理栈:.onnx 模型走 onnxruntime;.pt 模型走 PyTorch/ultralytics
  (onnxruntime 在虚拟机等环境无法加载时的备选方案)
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
from neobot_app.vision_detect.engine_torch import TorchYoloDetector
from neobot_app.vision_detect.model_library import ModelEntry, ModelLibrary, ScanReport

__all__ = ["VisionDetectService", "DetectionError"]


class DetectionError(RuntimeError):
    """检测失败(模型缺失/图片损坏/推理引擎不可用)。"""


class VisionDetectService:
    """本地 YOLO 图像检测服务。

    .onnx 模型用 onnxruntime 推理;.onnx 不可用(如虚拟机未透传 CPU 指令集
    导致 DLL 加载失败)时,改用 .pt 模型 + PyTorch(ultralytics) 推理,
    两者都可用时 .onnx 优先。
    """

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
        max_pixels: int = 40_000_000,
    ):
        self._library = ModelLibrary(models_dir, index_file)
        self._detectors: dict[tuple[str, int], OnnxDetector | TorchYoloDetector] = {}
        self._detector_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._auto_refresh = auto_refresh
        self._logger = logger
        self._usable: bool | None = None
        self._torch_usable: bool | None = None
        self._default_conf = default_conf
        self._default_iou = default_iou
        self._default_imgsz = imgsz
        self._closed = False
        # 解码前像素数上限(约 6300x6300),防止超大图解压导致 OOM
        self._max_pixels = max_pixels

    # ── 可用性 ──

    @property
    def onnx_available(self) -> bool:
        """onnxruntime 推理栈是否可用。"""
        if self._usable is None:
            try:
                import onnxruntime  # type: ignore[import-untyped]  # noqa: F401

                self._usable = True
            except Exception:
                self._usable = False
        return self._usable

    @property
    def torch_available(self) -> bool:
        """PyTorch(ultralytics) 推理栈是否可用。"""
        if self._torch_usable is None:
            try:
                import torch  # type: ignore[import-untyped]  # noqa: F401
                import ultralytics  # type: ignore[import-untyped]  # noqa: F401

                self._torch_usable = True
            except Exception:
                self._torch_usable = False
        return self._torch_usable

    def reset_availability(self) -> None:
        """重置推理引擎可用性缓存(环境修复后可重新探测)。"""
        self._usable = None
        self._torch_usable = None

    @property
    def available(self) -> bool:
        if self._closed:
            return False
        if not self._library.enabled_entries():
            return False
        return self.onnx_available or self.torch_available

    def _log(self, message: str) -> None:
        if self._logger is not None:
            try:
                self._logger.warning(message)
            except Exception:
                pass

    # ── 模型库 ──

    def refresh(self, force: bool = False) -> ScanReport:
        """重新扫描模型目录与索引(幂等)。

        同步 [library] 段的默认阈值到服务(它是 models.toml 中的真实生效来源,
        config.toml 的 agent.vision_detect.default_* 仅作为首次生成索引的初始值)。
        """
        report = self._library.refresh(force=force)
        self._default_conf = self._library.config.default_conf
        self._default_iou = self._library.config.default_iou
        self._default_imgsz = self._library.config.imgsz
        self._detectors.clear()
        for entry in report.unconfigured:
            self._log(f"vision_detect 模型未配置描述: {entry}")
        for error in report.errors:
            self._log(f"vision_detect 索引问题: {error}")
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
        """启用模型的元信息列表(供工具描述与 agent 选择模型)。

        backend 字段:onnx(onnxruntime)/ torch(PyTorch/ultralytics)。
        """
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
                    "backend": "torch" if entry.file.lower().endswith(".pt") else "onnx",
                }
            )
        return result

    def _entry_ids(self) -> list[str]:
        return [entry.id for entry in self._library.enabled_entries()]

    def _resolve_ids(self, model_ids: Sequence[str] | None) -> list[ModelEntry]:
        if model_ids is not None:
            if isinstance(model_ids, (str, bytes)):
                raise DetectionError(
                    "model_ids 必须是模型 id 列表(如 [\"model_a\"]),"
                    f"收到字符串: {model_ids!r}"
                )
            # 去重,避免同一模型重复推理
            model_ids = list(dict.fromkeys(model_ids))
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

    def _get_detector(self, entry: ModelEntry) -> OnnxDetector | TorchYoloDetector:
        imgsz = entry.imgsz or self._default_imgsz
        key = (entry.file, int(imgsz or 0))
        detector = self._detectors.get(key)
        if detector is None:
            # 双检锁:冷启动并发首次检测时避免重复构建推理引擎
            with self._detector_lock:
                detector = self._detectors.get(key)
                if detector is None:
                    model_path = self._library.models_dir / entry.file
                    if entry.file.lower().endswith(".pt"):
                        detector = TorchYoloDetector(
                            model_path,
                            names=entry.classes or None,
                            conf=entry.conf if entry.conf is not None else self._default_conf,
                            iou=entry.iou if entry.iou is not None else self._default_iou,
                            imgsz=imgsz,
                        )
                    else:
                        detector = OnnxDetector(
                            model_path,
                            names=entry.classes or None,
                            conf=entry.conf if entry.conf is not None else self._default_conf,
                            iou=entry.iou if entry.iou is not None else self._default_iou,
                            imgsz=imgsz,
                        )
                    self._detectors[key] = detector
        return detector

    # ── 检测接口(同步核心,调用方负责不阻塞事件循环) ──

    _ALL_SUMMARY_LIMIT = 10

    def detect_pil(
        self,
        pil_image: Image.Image,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
        mode: str = "filter",
    ) -> dict[str, Any]:
        """对一张 PIL 图片运行指定模型(缺省 = 全部启用模型)。

        Args:
            mode: "filter" — 按置信度阈值筛查,只显示达标目标(默认);
                  "all" — 不筛查,显示全部检测结果(可能包含低置信度)。
            阈值:filter 模式下用 min_conf(未传则用模型配置的 conf)。

        Returns:
            {
              "ok": True, "mode": str, "elapsed_ms": float, "checked_models": int,
              "results": [{"model", "model_name", "detections": [...]}],
              "summary": "中文摘要(agent 可直接使用)"
            }
        """
        if mode not in ("filter", "all"):
            raise DetectionError(f"无效的 mode: {mode!r}(可选值: filter / all)")
        if self._closed:
            raise DetectionError("视觉检测服务已关闭")
        if not (self.onnx_available or self.torch_available):
            raise DetectionError(
                "本地推理引擎不可用:onnxruntime 加载失败且 PyTorch(ultralytics) 未安装。"
                "请安装 ultralytics 以启用备选推理栈(.pt 模型),"
                "或修复 onnxruntime(.onnx 模型)"
            )
        self._maybe_refresh()
        entries = self._resolve_ids(model_ids)
        if not entries:
            raise DetectionError(
                "没有可用的检测模型,请把 .onnx / .pt 放入模型目录并运行 `neobot init`"
            )
        if min_conf is not None and (isinstance(min_conf, bool) or not 0.0 <= float(min_conf) <= 1.0):
            raise DetectionError(f"min_conf 必须在 0.0 到 1.0 之间,收到: {min_conf!r}")
        total_ms = 0.0
        results: list[dict[str, Any]] = []
        failed: list[str] = []
        for entry in entries:
            try:
                if mode == "all":
                    conf_thr: float | None = 0.0
                else:
                    # min_conf 显式传入即生效(含 0 = 零阈值全量输出);未传用模型默认阈值
                    conf_thr = min_conf if min_conf is not None else None
                dets, elapsed_ms = self._get_detector(entry).detect(
                    pil_image, conf=conf_thr
                )
            except Exception as exc:
                failed.append(f"{entry.id}: {exc}")
                continue
            total_ms += elapsed_ms
            results.append(
                {
                    "model": entry.id,
                    "model_name": entry.name or entry.id,
                    "detections": dets,
                }
            )
        if not results and failed:
            raise DetectionError(f"所有模型推理失败: {'; '.join(failed)}")
        if mode == "all":
            summary = self._summarize_all(results)
        else:
            threshold = min_conf if min_conf is not None else self._default_conf
            summary = self._summarize_filtered(results, threshold)
        return {
            "ok": True,
            "mode": mode,
            "elapsed_ms": round(total_ms, 2),
            "checked_models": len(results),
            "results": results,
            "summary": summary,
            "failed_models": failed or None,
        }

    @staticmethod
    def _label(result: dict[str, Any], total_models: int) -> str:
        """摘要中的模型标签:单模型用展示名,多模型带 id 区分。"""
        name = result["model_name"] or result["model"]
        if total_models > 1:
            return f"{name}({result['model']})"
        return name

    @staticmethod
    def _summarize_filtered(results: list[dict[str, Any]], default_conf: float) -> str:
        hits = [
            (result, det)
            for result in results
            for det in result["detections"]
        ]
        if not hits:
            return (
                f"未检测到任何目标(阈值 {default_conf:.0%})；"
                "如需排查低置信度结果，可降低 min_conf 复查"
            )
        parts = []
        for result, det in hits[: VisionDetectService._ALL_SUMMARY_LIMIT]:
            label = VisionDetectService._label(result, len(results))
            parts.append(f"{label}: {det['name']} 置信度 {det['conf']:.0%}")
        text = "检测到目标: " + " | ".join(parts)
        if len(hits) > VisionDetectService._ALL_SUMMARY_LIMIT:
            text += f" 等共 {len(hits)} 个目标(其余已省略,完整结果见 results)"
        return text

    def _summarize_all(self, results: list[dict[str, Any]]) -> str:
        """all 模式摘要:列出全部检测(限制条数,标注总数)。"""
        total = sum(len(r["detections"]) for r in results)
        if total == 0:
            return "未检测到任何目标"
        lines: list[str] = []
        shown = 0
        for result in results:
            for det in result["detections"]:
                if shown >= self._ALL_SUMMARY_LIMIT:
                    break
                x1, y1, x2, y2 = [int(v) for v in det["box"]]
                label = self._label(result, len(results))
                lines.append(
                    f"{label}: {det['name']} 置信度 {det['conf']:.1%} 位置({x1},{y1})-({x2},{y2})"
                )
                shown += 1
            if shown >= self._ALL_SUMMARY_LIMIT:
                break
        suffix = f" 等共 {total} 条(未按置信度筛查,可能含低置信度结果)" if total > shown else ""
        return "全部检测结果(未按置信度筛查): " + " | ".join(lines) + suffix

    def detect_bytes(
        self,
        image_bytes: bytes,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
        mode: str = "filter",
    ) -> dict[str, Any]:
        """对图片字节运行检测(自动解码,失败返回 ok=False)。"""
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened_image:
                width, height = opened_image.size
                if width * height > self._max_pixels:
                    return {
                        "ok": False,
                        "error": (
                            f"图片过大({width}x{height} = {width * height} 像素,"
                            f"上限 {self._max_pixels}),拒绝解码"
                        ),
                    }
                # 应用 EXIF 方向(手机竖拍照片),否则检测框与视觉内容错位
                from PIL import ImageOps

                oriented = ImageOps.exif_transpose(opened_image)
                oriented.load()
                rgb_image = oriented.convert("RGB")
        except Exception as exc:
            return {"ok": False, "error": f"图片无法解码: {exc}"}
        try:
            return self.detect_pil(rgb_image, model_ids=model_ids, min_conf=min_conf, mode=mode)
        except DetectionError as exc:
            return {"ok": False, "error": str(exc)}

    async def detect_bytes_async(
        self,
        image_bytes: bytes,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
        mode: str = "filter",
    ) -> dict[str, Any]:
        """异步检测(线程池内执行,不阻塞事件循环)。"""
        return await asyncio.to_thread(
            self.detect_bytes, image_bytes, model_ids, min_conf, mode
        )

    # ── 备用接口(当前未接入自动解析链路) ──

    async def inspect_image(
        self,
        image_bytes: bytes,
        *,
        model_ids: Sequence[str] | None = None,
        min_conf: float | None = None,
        mode: str = "filter",
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
                image_bytes, model_ids=model_ids, min_conf=min_conf, mode=mode
            )
        except Exception:
            return None

    # ── 生命周期 ──

    def close(self) -> None:
        """关闭服务:释放检测器池并标记已关闭(之后调用 detect 会明确报错)。"""
        self._closed = True
        self._detectors.clear()
        self._library = ModelLibrary(self._library.models_dir, self._library.index_file)
        self.reset_availability()
