"""Lossless image conversion and narrowly classified vision capability failures."""

from __future__ import annotations

import re
from typing import Any

import httpx

from neobot_chat.schema.exceptions import NativeVisionUnsupportedError, ValidationError
from neobot_chat.schema.types import Message

_IMAGE_TYPES = frozenset({"image_url", "image", "input_image"})
_UNSUPPORTED_IMAGE_PATTERNS = (
    r"\b(?:this\s+)?model\b[^\n.]{0,80}\b(?:does not|doesn't|cannot|can't)\s+(?:support|process|accept)\s+(?:\w+\s+){0,3}(?:image|vision|multimodal)",
    r"\b(?:image|vision|multimodal)(?:\s+(?:input|inputs|content|messages))?\s+(?:is|are)\s+not\s+supported\b",
    r"\bimage_url\b[^\n.]{0,40}\bonly supported by\b[^\n.]{0,40}\bmodels?\b",
    r"\bimage_url\b[^\n.]{0,20}\b(?:is )?not supported\b[^\n.]{0,40}\bmodel\b",
    r"\bcontent\b[^\n]{0,80}\b(?:expected|must be|should be)\s+(?:a\s+)?string\b[^\n]{0,60}\barray\b",
)


def contains_images(content: Any) -> bool:
    if isinstance(content, list):
        return any(contains_images(block) for block in content)
    if isinstance(content, dict):
        return content.get("type") in _IMAGE_TYPES or contains_images(content.get("content"))
    return False


def messages_have_images(messages: list[Message]) -> bool:
    return any(contains_images(message.get("content")) for message in messages)


async def raise_if_image_unsupported(response: httpx.Response) -> None:
    """Only explicit capability rejection on 400/422 permits a model downgrade.

    Invalid images, authentication, rate limits and transport/server failures are
    deliberately not capability failures. Never include request image data in logs.
    """
    if response.status_code not in {400, 422}:
        return
    body = (await response.aread()).decode("utf-8", errors="replace")
    if any(re.search(pattern, body, re.IGNORECASE) for pattern in _UNSUPPORTED_IMAGE_PATTERNS):
        raise NativeVisionUnsupportedError(
            f"HTTP {response.status_code}: model does not support image input"
        )


def _image_url(block: dict[str, Any]) -> str:
    value = block.get("image_url")
    url = value.get("url") if isinstance(value, dict) else value
    if not isinstance(url, str) or not url:
        raise ValidationError("image_url must contain a non-empty URL")
    return url


def to_anthropic_content(content: Any) -> Any:
    if not isinstance(content, list):
        if isinstance(content, dict) and contains_images(content):
            return to_anthropic_content([content])
        return content
    result: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            raise ValidationError("Message content blocks must be objects")
        if block.get("type") == "image_url":
            url = _image_url(block)
            if url.startswith("data:"):
                match = re.fullmatch(r"data:(image/[\w.+-]+);base64,(.+)", url, re.DOTALL)
                if not match:
                    raise ValidationError("Anthropic images require a base64 image data URL")
                source = {"type": "base64", "media_type": match[1], "data": match[2]}
            elif url.startswith(("https://", "http://")):
                source = {"type": "url", "url": url}
            else:
                raise ValidationError("Image URL must use http(s) or base64 data URL")
            result.append({"type": "image", "source": source})
        elif block.get("type") == "input_image":
            raise NativeVisionUnsupportedError("Chat provider cannot serialize input_image blocks")
        elif block.get("type") == "tool_result":
            result.append({**block, "content": to_anthropic_content(block.get("content"))})
        else:
            result.append(dict(block))
    return result


def to_openai_content(content: Any) -> Any:
    if not isinstance(content, list):
        if isinstance(content, dict) and contains_images(content):
            return to_openai_content([content])
        return content
    result: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            raise ValidationError("Message content blocks must be objects")
        if block.get("type") == "image":
            source = block.get("source", {})
            if source.get("type") == "url":
                url = source.get("url")
            elif source.get("type") == "base64":
                media_type, data = source.get("media_type"), source.get("data")
                if not media_type or not data:
                    raise ValidationError("Image source requires media_type and data")
                url = f"data:{media_type};base64,{data}"
            else:
                raise NativeVisionUnsupportedError("Chat provider cannot serialize this image source")
            if not isinstance(url, str) or not url:
                raise ValidationError("Image source requires a URL")
            result.append({"type": "image_url", "image_url": {"url": url}})
        elif block.get("type") == "input_image":
            raise NativeVisionUnsupportedError("Chat provider cannot serialize input_image blocks")
        else:
            result.append(dict(block))
    return result


def without_images(content: Any) -> Any:
    """Replace images visibly, retaining text and nested tool-result structure."""
    if isinstance(content, list):
        return [without_images(block) for block in content]
    if isinstance(content, dict):
        if content.get("type") in _IMAGE_TYPES:
            return {"type": "text", "text": "[图片未发送：原生视觉不可用，已切换非视觉模型；不能声称看过此图片。]"}
        if "content" in content:
            return {**content, "content": without_images(content["content"])}
        return dict(content)
    return content
