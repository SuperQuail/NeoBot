"""服务核心：生命周期、模型选择与请求基础能力。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from neobot_adapter import OneBotAdapter
from neobot_chat.providers.base import Provider
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory

from neobot_app.core import DATA_DIR
from neobot_app.drawing.config import (
    DrawServiceConfig,
)

if TYPE_CHECKING:
    from neobot_app.core.file_server import FileServer
    from neobot_app.emoji.service import EmojiService
    from neobot_app.image_pool import ImageStagingPool

from ._facade import facade


class CoreMixin:
    """服务核心：生命周期、模型选择与请求基础能力。"""

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
    _TMP_MAX_AGE_SECONDS = 12 * 60 * 60

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        adapter: OneBotAdapter,
        config: DrawServiceConfig,
        data_dir: Path = DATA_DIR,
        model_name: str = "",  # 生图模型 key（由 bootstrap 传入 [models.assignments].creator_image_models）
        model_names: Sequence[str] | None = None,
        emoji_service: "EmojiService | None" = None,
        vision_provider: Provider | None = None,
        markdown_dir: Path | None = None,
        file_server: "FileServer | None" = None,
        image_pool: "ImageStagingPool | None" = None,
        logger: Logger | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter = adapter
        self._config = config
        self._logger = logger or NullLogger()
        self._emoji_service = emoji_service
        self._vision_provider = vision_provider
        self._file_server = file_server
        self._image_pool = image_pool
        names = tuple(model_names) if model_names else ((model_name,) if model_name else ())
        self._model_names: tuple[str, ...] = tuple(dict.fromkeys(name for name in names if name))
        if not self._model_names:
            # 出厂默认**不预置生图模型**（models.assignments.creator_image_models 为空），而
            # agent.creator 默认开着（图库 / 表情包要用）—— 两者一撞，以前这里直接抛
            # ValueError，全新部署根本起不来（issue #82）。
            # 图库（gallery）、表情包、图库图片解析都挂在本服务的其它方法上，**都不需要**
            # 生图模型，所以这里软降级：只有绘图入口不可用，其余照常。
            self._logger.warning(
                "未配置生图模型，绘图功能不可用（图库 / 表情包不受影响）",
                hint="在 models.assignments.creator_image_models 里加入模型库引用后重启或热重载",
            )
        self._models: dict[str, Any] = {
            name: facade().get_registered_model(name) for name in self._model_names
        }
        self._default_model_name = self._model_names[0] if self._model_names else ""
        self._base_dir = data_dir / "creator"
        self._tmp_dir = self._base_dir / "tmp"
        self._gallery_dir = self._base_dir / "gallery"
        self._markdown_dir = markdown_dir
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._gallery_dir.mkdir(parents=True, exist_ok=True)
        timeout = self._request_timeout_seconds()
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, model in self._models.items():
            model_timeout = float(model.settings.timeout_seconds or timeout)
            self._clients[name] = httpx.AsyncClient(
                base_url=model.base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {model.api_key}"},
                timeout=httpx.Timeout(model_timeout, connect=min(model_timeout, 10.0)),
                trust_env=bool(getattr(model, "use_system_proxy", False)),
            )
        self._model = self._models.get(self._default_model_name)
        self._client = self._clients.get(self._default_model_name)
        # 用户可控 URL 下载使用无凭据 client，避免 API Key 外发
        self._public_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        )
        self._cleanup_task: asyncio.Task[None] | None = None

    #: 没有配置生图模型时，无凭据下载 client 用的兜底超时
    _FALLBACK_REQUEST_TIMEOUT_SECONDS = 60.0

    def _request_timeout_seconds(self) -> float:
        """默认生图模型的请求超时；没配模型时用兜底值（只影响内部 client）。"""
        model = self._models.get(self._default_model_name)
        raw = getattr(getattr(model, "settings", None), "timeout_seconds", None)
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            return self._FALLBACK_REQUEST_TIMEOUT_SECONDS
        return timeout if timeout > 0 else self._FALLBACK_REQUEST_TIMEOUT_SECONDS

    def _require_image_model(self) -> None:
        """没有配置生图模型时抛出可读错误（**绘图入口专用**）。

        图库 / 表情包 / 图片解析走本服务的其它方法，不经过这里：未配置生图模型只意味着
        「画不了图」，不是整个服务不可用（issue #82）。
        """
        if self._model_names:
            return
        raise ValueError(
            "未配置生图模型：models.assignments.creator_image_models 为空。"
            "请在模型库里添加一个生图模型，并把它的引用填进该配置，然后重启或热重载；"
            "图库与表情包不受影响。"
        )

    async def close(self) -> None:
        await self._stop_cleanup_task()
        await self.cleanup_tmp()
        for client in self._clients.values():
            await client.aclose()
        await self._public_client.aclose()

    async def start(self) -> None:
        self._start_cleanup_task()

    async def stop(self) -> None:
        await self._stop_cleanup_task()

    # ------------------------------------------------------------------
    # 生图模型选择（支持配置多个模型/供应商）
    # ------------------------------------------------------------------

    @property
    def default_model_name(self) -> str:
        return self._default_model_name

    @property
    def model_names(self) -> tuple[str, ...]:
        return self._model_names

    def available_models(self) -> list[dict[str, Any]]:
        """可用生图模型清单（供绘图工具描述与面板展示）。"""
        return [
            {
                "name": name,
                "index": index,
                "display_name": self._models[name].display_name,
                "provider": self._models[name].provider_name,
                "model_name": self._models[name].model_name,
                "default": name == self._default_model_name,
            }
            for index, name in enumerate(self._model_names)
        ]

    def resolve_model_name(self, selector: str | None) -> str:
        """把 Agent 给出的选择（序号 / 注册名 / 描述 / 供应商 / 模型名）解析为注册名。"""
        # 没有生图模型时，任何取值都解析不出来：在这里就给「未配置生图模型」的可读错误，
        # 而不是让下游拿空注册名去 self._models[""] 撞 KeyError。
        self._require_image_model()
        if selector is None:
            return self._default_model_name
        raw = str(selector).strip()
        if not raw:
            return self._default_model_name
        if raw in self._models:
            return raw
        if raw.isdigit():
            index = int(raw)
            if 0 <= index < len(self._model_names):
                return self._model_names[index]
        lowered = raw.casefold()
        for name in self._model_names:
            model = self._models[name]
            candidates = {
                str(model.display_name).casefold(),
                str(model.provider_name).casefold(),
                str(model.model_name).casefold(),
            }
            if lowered in candidates:
                return name
        for name in self._model_names:
            model = self._models[name]
            if lowered in str(model.model_name).casefold() or lowered in str(model.provider_name).casefold():
                return name
        available = "、".join(
            f"{index}:{self._models[name].display_name or name}"
            for index, name in enumerate(self._model_names)
        )
        raise ValueError(f"未知生图模型选择 {selector!r}；可用: {available}")

    def _client_for(self, model_name: str) -> tuple[Any, httpx.AsyncClient]:
        return self._models[model_name], self._clients[model_name]

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    def _get_vision_timeout_seconds(self) -> float:
        return 60.0

    async def _read_limited(self, response: Any) -> bytes:
        """分块读取响应体，超过上限即中止。"""
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > facade()._MAX_REMOTE_FETCH_BYTES:
                raise ValueError(
                    f"下载内容过大（{declared} 字节），超过上限 {facade()._MAX_REMOTE_FETCH_BYTES} 字节"
                )
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > facade()._MAX_REMOTE_FETCH_BYTES:
                raise ValueError(
                    f"下载内容过大，超过上限 {facade()._MAX_REMOTE_FETCH_BYTES} 字节，已中止"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await asyncio.wait_for(
            self._adapter.call_api(action, params),
            timeout=self._get_io_timeout_seconds(),
        )

    async def _send_with_timeout(self, conversation_ref: ConversationRef, segments: list[dict[str, Any]]) -> Any:
        return await asyncio.wait_for(
            self._adapter.send(conversation_ref, segments),
            timeout=self._get_io_timeout_seconds(),
        )

