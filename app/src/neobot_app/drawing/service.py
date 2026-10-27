"""图片生成、存储与参考图解析服务。"""

from __future__ import annotations

import httpx  # noqa: F401  # 测试 monkeypatch 的挂载点：service.httpx.AsyncClient

from neobot_app.message.image_pipeline import (  # noqa: F401  # 测试 monkeypatch 的挂载点
    prepare_local_image_async,
)
from neobot_chat import get_registered_model  # noqa: F401  # 测试 monkeypatch 的挂载点

from .service_parts.cleanup import CleanupMixin
from .service_parts.core import CoreMixin
from .service_parts.delivery import DeliveryMixin
from .service_parts.gallery import GalleryMixin
from .service_parts.generation import GenerationMixin
from .service_parts.helpers import (  # noqa: F401  # 兼容旧的模块级导入（manager 等）
    _MAX_REMOTE_FETCH_BYTES,
    _MIME_EXTENSIONS,
    _decode_data_url,
    _extension_for_mime,
    _json,
    _parse_hex_color,
    _read_sidecar_description,
    _record_payload,
    _remove_background,
    _resize_keep_ratio,
    _sanitize_filename,
)
from .service_parts.references import ReferencesMixin
from .service_parts.sidecars import SidecarsMixin
from .service_parts.storage import StorageMixin


class CreatorImageService(
    CoreMixin,
    CleanupMixin,
    GenerationMixin,
    GalleryMixin,
    DeliveryMixin,
    StorageMixin,
    SidecarsMixin,
    ReferencesMixin,
):
    """生成、存储并发送 Creator Agent 图片。"""


__all__ = ["CreatorImageService"]
