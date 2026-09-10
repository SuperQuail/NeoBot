"""Stateful, observable main-model vision fallback, not a general failover policy."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from neobot_chat.providers.base import Provider
from neobot_chat.providers.vision import messages_have_images, without_images
from neobot_chat.schema.exceptions import NativeVisionUnsupportedError, ValidationError
from neobot_chat.schema.types import ChatChunk, Message, ToolDefinition


class NativeVisionFallbackProvider:
    """Use a configured fallback route after an explicit vision rejection.

    ``native_vision`` and ``model`` reflect the active provider immediately.
    ``vision_degradation`` and response ``extensions['native_vision_fallback']``
    expose the reason and routes to the agent. A new instance (configuration
    reload) resets this state.

    Two fallback modes:

    - vision-capable fallback (``strip_images=False``, the default when the
      fallback declares ``native_vision=True``): messages and tools pass through
      unchanged, so images are still understood by the fallback model;
    - text-only fallback (``strip_images=True``): images are removed and a system
      notice plus visible placeholders are injected, so no model assumes it saw
      removed images.
    """

    def __init__(
        self,
        primary: Provider | None,
        fallback: Provider,
        *,
        logger: Any,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
        startup_reason: str | None = None,
        strip_images: bool | None = None,
    ) -> None:
        if primary is fallback:
            raise ValidationError("Native vision fallback must use a different provider")
        if primary is None and not startup_reason:
            raise ValidationError("Missing primary provider requires a startup failure reason")
        fallback_has_vision = bool(getattr(fallback, "native_vision", False))
        if strip_images is None:
            strip_images = not fallback_has_vision
        if strip_images and fallback_has_vision:
            raise ValidationError("Image-stripping fallback must be a non-vision provider")
        self._primary = primary
        self._fallback = fallback
        self._logger = logger
        self._primary_name = primary_name
        self._fallback_name = fallback_name
        self._strip_images = strip_images
        self._degradation: dict[str, Any] | None = None
        if startup_reason:
            self._degrade(startup_reason)

    @property
    def native_vision(self) -> bool:
        # 保留图片的回退路由（视觉模型）按定义可以接收图片：即使该模型注册项
        # 未声明 native_vision，请求中的图片也是原样发送的，能力必须如实上报，
        # 否则上层会误判为"看不到图片"而改走图片解析流程。
        if self._degradation is not None and not self._strip_images:
            return True
        active = self._fallback if self._degradation else self._primary
        return bool(getattr(active, "native_vision", False))

    @property
    def model(self) -> str:
        return getattr(self._fallback if self._degradation else self._primary, "model", "")

    @property
    def vision_degradation(self) -> dict[str, Any] | None:
        return dict(self._degradation) if self._degradation else None

    def _degrade(self, reason: str) -> None:
        if self._degradation is not None:
            return
        if self._strip_images:
            notice = (
                "原生视觉已降级：当前已切换到配置的非视觉模型。图片内容未发送，不能声称已看到图片；"
                "图片挂载工具已禁用。若回答需要图片信息，请在后续轮次使用恢复后的图片解析工具，"
                "或明确说明暂时无法查看图片。"
            )
            log = self._logger.error
        else:
            notice = (
                f"原生视觉回退：主模型不可用或无法处理图片，已自动切换到视觉模型"
                f"（{self._fallback_name}）。图片仍随请求发送，回答可正常基于图片内容。"
            )
            log = getattr(self._logger, "warning", self._logger.error)
        self._degradation = {
            "reason": reason,
            "from_model": self._primary_name,
            "to_model": self._fallback_name,
            "notice": notice,
        }
        log(
            f"Native vision fallback ({self._primary_name} -> {self._fallback_name}): {reason}. {notice}"
        )

    def _fallback_messages(self, messages: list[Message]) -> list[Message]:
        assert self._degradation is not None
        if not self._strip_images:
            # 视觉模型能看懂图片，原样转发，不做任何改写。
            return list(messages)
        result: list[Message] = [{"role": "system", "content": self._degradation["notice"]}]
        for message in messages:
            copied = dict(message)
            if "content" in message:
                content = without_images(message["content"])
                # Text-only models may reject arrays even without image blocks.
                if isinstance(content, list) and all(
                    isinstance(block, dict) and block.get("type") == "text" for block in content
                ):
                    content = "\n".join(str(block.get("text", "")) for block in content)
                copied["content"] = content
            result.append(copied)
        return result

    def _fallback_tools(self, tools: list[ToolDefinition] | None) -> list[ToolDefinition] | None:
        if tools is None or not self._strip_images:
            return tools
        return [tool for tool in tools if not tool["function"]["name"].startswith("image_context__")]

    def _annotate(self, message: Message) -> Message:
        return {
            **message,
            "extensions": {
                **(message.get("extensions") or {}),
                "native_vision_fallback": self.vision_degradation,
            },
        }

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> Message:
        if self._degradation is None:
            assert self._primary is not None
            try:
                return await self._primary.chat(messages, tools=tools)
            except NativeVisionUnsupportedError as exc:
                if not getattr(self._primary, "native_vision", False) or not messages_have_images(messages):
                    raise
                self._degrade(str(exc))
        response = await self._fallback.chat(
            self._fallback_messages(messages), tools=self._fallback_tools(tools)
        )
        return self._annotate(response)

    async def stream(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[ChatChunk]:
        if self._degradation is None:
            assert self._primary is not None
            started = False
            try:
                async for chunk in self._primary.stream(messages, tools=tools):
                    started = True
                    yield chunk
                return
            except NativeVisionUnsupportedError as exc:
                # Never replay a request after publishing partial output.
                if started or not getattr(self._primary, "native_vision", False) or not messages_have_images(messages):
                    raise
                self._degrade(str(exc))
        async for chunk in self._fallback.stream(
            self._fallback_messages(messages), tools=self._fallback_tools(tools)
        ):
            if chunk.message is not None:
                chunk = ChatChunk(
                    delta=chunk.delta,
                    reasoning_delta=chunk.reasoning_delta,
                    message=self._annotate(chunk.message),
                    state=chunk.state,
                )
            yield chunk

    async def close(self) -> None:
        providers = [self._fallback]
        if self._primary is not None:
            providers.append(self._primary)
        results = await asyncio.gather(*(provider.close() for provider in providers), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
