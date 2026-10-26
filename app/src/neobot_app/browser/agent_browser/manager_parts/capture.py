"""CaptureMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from neobot_contracts.ports.screenshot import (
    ScreenshotError,
    ScreenshotOptions,
    ScreenshotResult,
    ScreenshotTargetNotFound,
    validate_screenshot_options,
)

from .._compat import ChromiumBase


class CaptureMixin:
    """截图、标注截图与录屏。"""

    # ── 截图 ──

    async def _apply_temporary_capture_metrics(
        self, options: ScreenshotOptions
    ) -> tuple[ChromiumBase, bool, dict[str, Any] | None]:
        """Apply capture metrics before content loads and return restoration state."""
        validate_screenshot_options(options)
        page = await self._ensure_page()
        raw_metrics = await asyncio.to_thread(
            page.run_js,
            """return JSON.stringify({
                width: window.innerWidth, height: window.innerHeight,
                dpr: window.devicePixelRatio
            })""",
        )
        metrics = json.loads(raw_metrics)
        width = options.width or int(metrics["width"])
        height = options.height or int(metrics["height"])
        applied = (
            width != metrics["width"]
            or height != metrics["height"]
            or options.scale != metrics["dpr"]
        )
        previous_override = getattr(self, "_device_metrics_override", None)
        if applied:
            await asyncio.to_thread(
                page.run_cdp,
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=height,
                deviceScaleFactor=options.scale,
                mobile=False,
            )
        return page, applied, previous_override

    async def _restore_temporary_capture_metrics(
        self, state: tuple[ChromiumBase, bool, dict[str, Any] | None]
    ) -> None:
        page, applied, previous_override = state
        if not applied:
            return
        if previous_override is None:
            await asyncio.to_thread(
                page.run_cdp, "Emulation.clearDeviceMetricsOverride"
            )
        else:
            await asyncio.to_thread(
                page.run_cdp,
                "Emulation.setDeviceMetricsOverride",
                **previous_override,
            )

    async def capture(self, options: ScreenshotOptions) -> ScreenshotResult:
        """Capture the current page without writing to disk."""
        state = None
        try:
            state = await self._apply_temporary_capture_metrics(options)
            page = state[0]
            raw_box = await asyncio.to_thread(
                page.run_js,
                """return JSON.stringify({
                    viewport: {x: window.scrollX, y: window.scrollY,
                        width: window.innerWidth, height: window.innerHeight},
                    full: {x: 0, y: 0,
                        width: Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0),
                        height: Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0)}
                })""",
            )
            boxes = json.loads(raw_box)
            if options.mode == "element":
                raw_element = await asyncio.to_thread(
                    page.run_js,
                    """const element = document.querySelector(arguments[0]);
                    if (!element) return null;
                    const rect = element.getBoundingClientRect();
                    return JSON.stringify({x: rect.left + window.scrollX,
                        y: rect.top + window.scrollY, width: rect.width, height: rect.height});""",
                    options.selector,
                )
                if not raw_element:
                    raise ScreenshotTargetNotFound(
                        f"screenshot target not found: {options.selector}"
                    )
                clip = json.loads(raw_element)
                if clip["width"] <= 0 or clip["height"] <= 0:
                    raise ScreenshotTargetNotFound(
                        f"screenshot target has no visible area: {options.selector}"
                    )
            else:
                clip = boxes["full" if options.mode == "full_page" else "viewport"]
            args: dict[str, Any] = {
                "format": options.format,
                "clip": {**clip, "scale": 1},
                "captureBeyondViewport": True,
                "omitBackground": options.transparent,
            }
            if options.format in {"jpeg", "webp"}:
                args["quality"] = options.quality
            response = await asyncio.to_thread(
                page.run_cdp, "Page.captureScreenshot", **args
            )
            data = base64.b64decode(response["data"])
            with Image.open(BytesIO(data)) as image:
                pixel_width, pixel_height = image.size
            return ScreenshotResult(
                data=data,
                format=options.format,
                width=pixel_width,
                height=pixel_height,
                css_width=float(clip["width"]),
                css_height=float(clip["height"]),
                scale=options.scale,
            )
        except ScreenshotError:
            raise
        except Exception as exc:
            raise ScreenshotError("failed to capture screenshot") from exc
        finally:
            if state is not None:
                try:
                    await self._restore_temporary_capture_metrics(state)
                except Exception as exc:
                    if sys.exc_info()[0] is None:
                        raise ScreenshotError(
                            "failed to restore browser metrics after capture"
                        ) from exc

    async def screenshot(self, path: str | Path | None = None, full_page: bool = False) -> bytes:
        """截图，返回 JPEG bytes。

        使用 CDP Page.captureScreenshot 直接调用，避免 DrissionPage 的
        _run_cdp_loaded → wait.doc_loaded() 挂起问题（SPA 页面 readyState 可能卡在 loading）。
        """
        page = await self._ensure_page()

        if full_page:
            import json as _json
            js = "return JSON.stringify({w: document.body.scrollWidth, h: document.body.scrollHeight})"
            raw = await asyncio.to_thread(page.run_js, js)
            size = _json.loads(raw) if raw else {"w": 1280, "h": 720}
            args = {
                "format": "jpeg",
                "quality": 85,
                "clip": {"x": 0, "y": 0, "width": size["w"], "height": size["h"], "scale": 1},
                "captureBeyondViewport": True,
            }
        else:
            args = {"format": "jpeg", "quality": 85}

        import base64
        result = await asyncio.to_thread(lambda: page.run_cdp("Page.captureScreenshot", **args))
        jpg_bytes = base64.b64decode(result["data"])

        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpg_bytes)

        return jpg_bytes

    async def screenshot_annotated(self, name: str = "") -> dict:
        """截图并标注元素编号。"""
        try:
            page = await self._ensure_page()
            from .snapshot import _collect_elements
            elements = await asyncio.to_thread(_collect_elements, page, interactive_only=True)
            shot_path = Path(self._user_data_dir) / f"annotated_{name or 'shot'}.png"
            await asyncio.to_thread(page.get_screenshot, path=str(shot_path), full_page=True)

            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.open(shot_path).convert("RGB")
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("arial.ttf", 16)
                except Exception:
                    font = ImageFont.load_default()
                elements_data = []
                for el_data in elements:
                    rect = el_data.attrs if hasattr(el_data, 'attrs') else {}
                    elements_data.append({"rect": {}})  # simplified for annotation
                for i, el_data in enumerate(elements_data):
                    ref_num = i + 1
                    rect = el_data.get("rect", {})
                    x, y, w, h = rect.get("x", 0), rect.get("y", 0), rect.get("width", 0), rect.get("height", 0)
                    if w > 0 and h > 0:
                        cx, cy = x + w / 2, y + h / 2
                        r = 12
                        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="red")
                        draw.text((cx - 5, cy - 7), str(ref_num), fill="white", font=font)
                stem = shot_path.stem
                anno_path = shot_path.with_name(stem + "_annotated.png")
                img.save(anno_path, "PNG")
                return {"success": True, "path": str(anno_path), "elements": len(elements)}
            except ImportError:
                return {"success": True, "path": str(shot_path), "elements": 0, "note": "PIL not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 录屏 ──

    async def record_start(self, filepath: str = "") -> dict:
        """开始录屏。"""
        async with self._recording_lock:
            try:
                if self._recording:
                    return {"success": False, "error": "已在录制中"}
                await self._ensure_page()
                self._recording = True
                self._recording_frames = []
                self._record_path = filepath or str(Path(self._user_data_dir) / f"recording_{int(time.time())}.gif")
                self._recording_task = asyncio.create_task(self._record_loop())
                return {"success": True, "output": self._record_path}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def record_stop(self) -> dict:
        """停止录屏并保存。"""
        async with self._recording_lock:
            if not self._recording:
                return {"success": False, "error": "未在录制"}
            self._recording = False
            if self._recording_task:
                self._recording_task.cancel()
                self._recording_task = None
            frames = self._recording_frames
            self._recording_frames = []
            if not frames:
                return {"success": True, "frames": 0, "path": ""}
            try:
                from PIL import Image
                import io
                images = [Image.open(io.BytesIO(f)) for f in frames]
                out_path = self._record_path
                if out_path.endswith(".gif"):
                    images[0].save(out_path, save_all=True, append_images=images[1:],
                                   duration=500, loop=0, optimize=False)
                else:
                    out_path = out_path.rsplit(".", 1)[0] + ".gif"
                    images[0].save(out_path, save_all=True, append_images=images[1:],
                                   duration=500, loop=0, optimize=False)
                return {"success": True, "frames": len(frames), "path": out_path}
            except ImportError:
                meta_path = self._record_path + ".json"
                Path(meta_path).write_text(json.dumps({"frames": len(frames)}), encoding="utf-8")
                return {"success": True, "frames": len(frames), "path": meta_path,
                        "note": "PIL not available, saved frame count only"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def _recording_stop(self) -> None:
        """内部停止录屏（不返回结果）。"""
        async with self._recording_lock:
            self._recording = False
            if self._recording_task:
                self._recording_task.cancel()
                self._recording_task = None
            self._recording_frames = []

    async def _record_loop(self) -> None:
        """后台录屏循环。"""
        while self._recording:
            try:
                png = await self.screenshot()
                self._recording_frames.append(png)
                if len(self._recording_frames) > 600:
                    self._recording_frames.pop(0)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def record_restart(self, filepath: str = "") -> dict:
        """重启录屏（停止当前 + 开始新录制）。"""
        if self._recording:
            await self.record_stop()
        return await self.record_start(filepath)
