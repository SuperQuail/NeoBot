"""生图与图片处理入口。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from neobot_contracts.models.memory import CreatorImageRecord

from neobot_app.drawing.config import (
    DEFAULT_IMAGE_SIZE,
    TMP_SOURCE,
    ImageGenerationError,
)

if TYPE_CHECKING:
    pass

from .helpers import _remove_background, _resize_keep_ratio


class GenerationMixin:
    """生图与图片处理入口。"""

    async def generate_image(
        self,
        *,
        prompt: str,
        references: list[str] | None = None,
        reference_id: int | None = None,
        negative_prompt: str | None = None,
        image_size: str | None = None,
        seed: int | None = None,
        image_source: str | None = None,
        conv_id: str = "",
        model: str | None = None,
    ) -> CreatorImageRecord:
        self._require_image_model()
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")

        resolved_name = self.resolve_model_name(model)
        registered_model, client = self._client_for(resolved_name)

        payload: dict[str, Any] = {
            "model": registered_model.model_name,
            "prompt": prompt,
            "image_size": image_size or DEFAULT_IMAGE_SIZE,
        }
        payload.update(registered_model.settings.extra_body or {})
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed

        resolved_data_urls: list[str] = []
        if reference_id is not None:
            ref = await self._get_reference_by_gallery_no(reference_id)
            if ref is None:
                raise LookupError(f"图库编号 {reference_id} 不存在")
            resolved_data_urls.append(self._image_data_url(Path(ref.file_path), ref.mime_type))
        if references:
            for ref_str in references:
                url = await self._resolve_reference(ref_str.strip(), conv_id=conv_id)
                if url:
                    resolved_data_urls.append(url)

        settings = registered_model.settings
        image_api = str(getattr(settings, "image_api", "auto") or "auto").strip().lower()
        if image_api not in {"auto", "edits", "generations"}:
            image_api = "auto"
        reference_param = str(
            getattr(settings, "image_reference_param", "image") or "image"
        ).strip() or "image"

        response: httpx.Response | None = None
        if resolved_data_urls and image_api in {"auto", "edits"}:
            # 参考图必须走 /images/edits（multipart）：部分中转站会静默忽略
            # /images/generations 上的 image 字段，导致「参考图不生效」
            response = await self._post_edits(
                client,
                registered_model,
                payload=payload,
                references=resolved_data_urls,
            )
            if response is not None and response.status_code in {400, 404, 405}:
                if image_api == "edits":
                    pass  # 显式指定 edits 时不回退，交给下方 raise_for_status 报错
                else:
                    self._logger.warning(
                        f"参考图接口 /images/edits 返回 {response.status_code}，"
                        f"回退到 /images/generations（字段 {reference_param}）"
                    )
                    response = None
        if response is None:
            if resolved_data_urls:
                # 复数形式的字段名（images / image_urls / reference_images）用数组，
                # 单数形式（image / image_url / input_image）单张时用字符串
                payload[reference_param] = (
                    list(resolved_data_urls)
                    if len(resolved_data_urls) > 1 or reference_param.endswith("s")
                    else resolved_data_urls[0]
                )
            response = await client.post("/images/generations", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._logger.error(
                "生图接口返回错误状态码",
                status=response.status_code,
                body=response.text[:500],
            )
            raise ImageGenerationError({
                "error_type": "HTTPStatusError",
                "status_code": exc.response.status_code,
                "response_body": exc.response.text,
                "request_url": str(exc.request.url),
            }) from exc
        try:
            image_bytes = await self._extract_image_bytes(response.json())
        except ValueError as exc:
            self._logger.error(
                "生图接口返回数据解析失败",
                status=response.status_code,
                body=response.text[:500],
            )
            raise ImageGenerationError({
                "error_type": "ValueError",
                "message": str(exc),
                "status_code": response.status_code,
                "response_body": response.text,
            }) from exc
        return await self._save_image_bytes(
            image_bytes,
            source=TMP_SOURCE,
            prompt=prompt,
            description=None,
            image_source=image_source,
        )

    async def process_image(
        self,
        *,
        image: str,
        operation: str,
        width: int | None = None,
        height: int | None = None,
        crop_box: list[int] | None = None,
        quality: int | None = None,
        background_color: str | None = None,
        image_source: str | None = None,
        conv_id: str = "",
    ) -> CreatorImageRecord:
        """本地图片后处理:缩放 / 裁切 / 格式转换 / 去底透明。

        image 支持图片 ID(image_id,如 tmp_xxx / g_xxx)或来源描述符
        (gallery:<图库编号> / emoji:<编号> / file:<路径> / url:<URL> / chat:<msg>:<idx>)。
        operation:
          - resize: 等比缩放;只给 width 或 height 时按单边等比,
            两者都给时精确拉伸
          - crop: 按 crop_box=[left, top, right, bottom] 裁切
          - to_png / to_jpeg: 格式转换(quality 仅 jpeg 生效)
          - remove_background: 纯色背景去底为透明 PNG
            (background_color 指定键色,如 "#00ff00";不指定则自动从边框采样)
        结果保存到临时目录,返回新图片 ID。
        """
        source_path = await self._resolve_process_source(image, conv_id=conv_id)
        operation = (operation or "").strip().lower()
        allowed = {"resize", "crop", "to_png", "to_jpeg", "remove_background"}
        if operation not in allowed:
            raise ValueError(
                f"不支持的操作: {operation}(可选: {', '.join(sorted(allowed))})"
            )

        from PIL import Image, ImageOps

        with Image.open(source_path) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened).convert("RGB")
            if operation == "resize":
                if width and height:
                    img = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
                elif width or height:
                    target = (int(width) if width else None, int(height) if height else None)
                    img = _resize_keep_ratio(img, target)
            elif operation == "crop":
                if not crop_box or len(crop_box) != 4:
                    raise ValueError("crop 操作需要 crop_box=[left, top, right, bottom]")
                left, top, right, bottom = (int(v) for v in crop_box)
                if right <= left or bottom <= top:
                    raise ValueError("crop_box 必须满足 right > left 且 bottom > top")
                img = img.crop((left, top, right, bottom))
            elif operation == "remove_background":
                img = _remove_background(img, background_color=background_color)

            output_format = "PNG"
            if operation == "to_jpeg":
                output_format = "JPEG"
                img = img.convert("RGB")
            elif operation == "remove_background":
                output_format = "PNG"

            buffer = io.BytesIO()
            save_kwargs: dict[str, Any] = {}
            if output_format == "JPEG" and quality:
                save_kwargs["quality"] = max(1, min(int(quality), 100))
            img.save(buffer, format=output_format, **save_kwargs)
            image_bytes = buffer.getvalue()

        return await self._save_image_bytes(
            image_bytes,
            source=TMP_SOURCE,
            prompt=f"process_image({operation})",
            description=None,
            image_source=image_source,
        )

    async def _resolve_process_source(self, image: str, *, conv_id: str = "") -> Path:
        """解析 process_image 的输入:图片 ID 或来源描述符。"""
        image = str(image or "").strip()
        if not image:
            raise ValueError("缺少 image 参数")
        # 先尝试按图片 ID 查找(DB 记录,覆盖 tmp_xxx / g_xxx)
        record = await self._get_existing(image)
        if record is not None and Path(record.file_path).is_file():
            return Path(record.file_path)
        # 再尝试来源描述符(gallery: / emoji: / file: / url: / chat:)
        if ":" in image:
            prefix = image.partition(":")[0].lower().strip()
            if prefix in ("gallery", "g", "emoji", "e", "file", "url", "chat"):
                return await self.resolve_source_to_path(image)
        raise LookupError(f"图片不存在或无法解析: {image}")

