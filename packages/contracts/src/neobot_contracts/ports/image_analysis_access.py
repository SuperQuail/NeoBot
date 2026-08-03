"""图片分析缓存访问端口。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from neobot_contracts.models.memory import ImageAnalysis


@runtime_checkable
class ImageAnalysisAccess(Protocol):
    """图片分析结果缓存的持久化访问接口。"""

    async def get(self, file_hash: str) -> Optional[ImageAnalysis]: ...

    async def set(
        self,
        file_hash: str,
        *,
        source: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        processed_width: Optional[int] = None,
        processed_height: Optional[int] = None,
        analysis_text: Optional[str] = None,
    ) -> ImageAnalysis: ...

    async def delete(self, file_hash: str) -> bool: ...

    async def exists(self, file_hash: str) -> bool: ...

    async def list(
        self,
        *,
        source_query: Optional[str] = None,
        has_analysis_text: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageAnalysis]: ...
