"""Image parsing sub-agent."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from neobot_chat.providers.base import Provider
from neobot_chat.schema.types import ChatChunk, State
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.message.image_pipeline import prepare_local_image

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


EXPOSED_TO_MAIN_AGENT_NAME = "image_parse"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "只负责按需求解析图片内容,不保存、不导入、不管理图库或表情包,只有在有人要求你看某张图片,但是你读到的图片信息缺乏指定细节的情况下,才调用该agent,传入指定图片以及对应需求。"
    "调用时必须明确提供图片 URL、本地路径、base64 或真实 message_id,以及解析需求,只负责解析聊天中的图片。"
    "头像解析请委托 memory（它会内部调用本agent）；把聊天图片加入图库/表情包请委托 creator。"
)

# 同级 sub agent 描述，用于识别任务是否应委托给其他 agent
PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片到群聊/私聊。\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注、查看聊天记录、解析用户头像（头像解析由 memory 负责，不要直接处理头像解析请求）。\n"
    "- chat_interaction: 聊天互动、群管理、好友管理、发送表情包。\n"
    "你只负责按需求解析图片内容。如果收到的任务是：保存图片、导入图库/表情包 → 告知主Agent委托 creator；头像解析 → 告知主Agent委托 memory；群管理/好友管理 → 告知主Agent委托 chat_interaction。"
)

DEFAULT_REQUIREMENT = "请简洁描述这张图片的主要内容。"
DEFAULT_MIME_TYPE = "image/png"


@dataclass(frozen=True)
class ImageParseRequest:
    requirement: str
    image_url: str | None = None
    image_path: str | None = None
    image_base64: str | None = None
    mime_type: str | None = None
    message_id: int | None = None
    message_number: int | None = None
    image_index: int = 1


class ImageParseAgent:
    """Sub-agent that parses one image through the configured vision provider."""

    def __init__(
        self,
        provider: Provider,
        *,
        adapter: "OneBotAdapter | None" = None,
        logger: Logger | None = None,
    ) -> None:
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self.tool_definitions: list[dict[str, Any]] = []
        self._provider = provider
        self._adapter = adapter
        self._logger = logger or NullLogger()

    async def invoke(self, state: State) -> State:
        messages = list(state.get("messages", []))
        task = self._last_user_text(messages)
        delegate_context = str(state.get("_delegate_context") or "")
        try:
            request = self._parse_request(task)
            image_url = await self._resolve_image_url(request, task, delegate_context)
            result = await self._call_vision_model(
                image_url=image_url,
                requirement=request.requirement,
            )
        except Exception as exc:
            self._logger.warning("图片解析 Agent 执行失败", error=str(exc))
            result = self._missing_image_response(task, delegate_context, exc)
        messages.append({"role": "assistant", "content": result})
        return {**state, "messages": messages}

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        result = await self.invoke(state)
        yield ChatChunk(state=result)

    async def close(self) -> None:
        await self._provider.close()

    async def _call_vision_model(self, *, image_url: str, requirement: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "你是图片解析 Agent。只根据图片和需求给出解析结果，"
                            "不要记录、不要提及数据库或缓存、不要建议后续操作。\n"
                            f"{PEER_AGENT_DESCRIPTIONS}\n"
                            f"解析需求：{requirement}"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        response = await self._provider.chat(messages)
        content = response.get("content", "")
        text = content.strip() if isinstance(content, str) else str(content).strip()
        return text or "图片解析完成，但模型未返回文本。"

    async def _resolve_image_url(self, request: ImageParseRequest, task: str, delegate_context: str = "") -> str:
        if request.image_base64:
            return self._normalize_base64_image_url(request.image_base64, request.mime_type)
        if request.image_path:
            return self._local_image_data_url(request.image_path)
        if request.image_url:
            return await self._image_ref_to_data_url(request.image_url, request.mime_type)

        message_id = request.message_id
        if message_id is None and request.message_number is not None:
            message_id = self._message_id_from_context(task, request.message_number)
        if message_id is None and request.message_number is not None and delegate_context:
            message_id = self._message_id_from_delegate_context(delegate_context, request.message_number)
        if message_id is not None:
            return await self._chat_image_data_url(
                message_id=message_id,
                image_index=request.image_index,
            )

        # 尝试从 delegate_context 中提取第一个可用的图片信息
        if delegate_context and not any([request.image_url, request.image_path, request.image_base64, request.message_id, request.message_number]):
            raise ValueError(
                "缺少图片参数。请提供以下之一：image_url、image_path、image_base64、message_id 或 message_number。"
                "可调用 get_chat_context 获取当前聊天上下文和消息编号映射。"
                "如需要解析头像，请委托 memory agent。"
                "如需要将图片加入图库/表情包，请委托 creator agent。"
            )

        raise ValueError(
            "缺少图片参数。请提供以下之一：image_url、image_path、image_base64、message_id 或 message_number。"
            "如需要解析头像，请委托 memory agent。"
            "如需要将图片加入图库/表情包，请委托 creator agent。"
        )

    def _parse_request(self, task: str) -> ImageParseRequest:
        data = self._extract_json_object(task)
        head = task.split("\n\n", 1)[0]
        requirement = self._first_text(
            data,
            "requirement",
            "request",
            "prompt",
            "需求",
            "解析需求",
        )
        if not requirement:
            requirement = head.strip() or DEFAULT_REQUIREMENT

        image_url = self._first_text(data, "image_url", "url")
        image_path = self._first_text(data, "image_path", "path", "file_path")
        image_base64 = self._first_text(data, "image_base64", "base64", "b64")
        mime_type = self._first_text(data, "mime_type", "mime")
        message_id = self._optional_int(self._first_value(data, "message_id"))
        message_number = self._optional_int(self._first_value(data, "message_number", "number"))
        image_index = self._optional_int(self._first_value(data, "image_index")) or 1

        if not image_url:
            image_url = self._extract_url(head)
        if not image_path:
            image_path = self._extract_labeled_value(head, ("image_path", "path", "file_path", "本地路径"))
        if message_id is None:
            message_id = self._extract_labeled_int(head, ("message_id", "真实 message_id", "消息ID", "消息id"))
        if message_number is None:
            message_number = self._extract_labeled_int(head, ("message_number", "消息编号"))
        if image_index == 1:
            image_index = self._extract_labeled_int(head, ("image_index", "图片序号")) or self._extract_image_index(head) or 1

        return ImageParseRequest(
            requirement=requirement,
            image_url=image_url,
            image_path=image_path,
            image_base64=image_base64,
            mime_type=mime_type,
            message_id=message_id,
            message_number=message_number,
            image_index=max(int(image_index), 1),
        )

    async def _chat_image_data_url(self, *, message_id: int, image_index: int) -> str:
        if self._adapter is None:
            raise RuntimeError("未配置聊天适配器，无法按 message_id 读取聊天图片")
        if image_index <= 0:
            raise ValueError("image_index 必须大于 0")
        result = await self._adapter.call_api("get_msg", {"message_id": message_id})
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            raise LookupError(f"无法读取消息 {message_id}")
        segments = data.get("message")
        if not isinstance(segments, list):
            raise LookupError(f"消息 {message_id} 不包含消息段")
        image_segments = [
            segment
            for segment in segments
            if isinstance(segment, dict) and str(segment.get("type")) in {"image", "cardimage"}
        ]
        if image_index > len(image_segments):
            raise LookupError(f"消息 {message_id} 没有第 {image_index} 张图片")
        segment_data = image_segments[image_index - 1].get("data") or {}
        if not isinstance(segment_data, dict):
            raise LookupError(f"消息 {message_id} 的图片段无效")
        return await self._image_ref_to_data_url(self._segment_image_ref(segment_data), None)

    def _segment_image_ref(self, data: dict[str, Any]) -> str:
        url = data.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
        file_name = data.get("file")
        if not isinstance(file_name, str) or not file_name.strip():
            raise LookupError("图片段缺少 url/file")
        return file_name.strip()

    async def _image_ref_to_data_url(self, ref: str, mime_type: str | None) -> str:
        ref = ref.strip()
        if ref.startswith("data:image/"):
            return ref
        if ref.startswith("base64://"):
            return self._normalize_base64_image_url(ref[9:], mime_type)
        if ref.startswith("file:///"):
            return self._local_image_data_url(ref[8:])
        if ref.startswith("file://"):
            return self._local_image_data_url(ref[7:])
        if ref.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                response = await client.get(ref)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                mime = mime_type or content_type or mimetypes.guess_type(ref)[0] or self._detect_mime(response.content)
                return self._bytes_data_url(response.content, mime)
        path = Path(ref)
        if path.exists() and path.is_file():
            return self._local_image_data_url(str(path))
        if self._adapter is not None:
            result = await self._adapter.call_api("get_image", {"file": ref})
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, dict):
                img_ref = data.get("file") or data.get("url")
                if isinstance(img_ref, str) and img_ref.strip() and img_ref.strip() != ref:
                    return await self._image_ref_to_data_url(img_ref, mime_type)
        raise LookupError("无法读取图片内容")

    def _local_image_data_url(self, image_path: str) -> str:
        prepared = prepare_local_image(image_path)
        return self._bytes_data_url(prepared.image_bytes, prepared.mime_type)

    @staticmethod
    def _bytes_data_url(image_bytes: bytes, mime_type: str | None) -> str:
        mime = mime_type or ImageParseAgent._detect_mime(image_bytes)
        data = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime};base64,{data}"

    @staticmethod
    def _normalize_base64_image_url(value: str, mime_type: str | None) -> str:
        text = value.strip()
        if text.startswith("data:image/"):
            return text
        if text.startswith("base64://"):
            text = text[9:]
        mime = mime_type or DEFAULT_MIME_TYPE
        return f"data:{mime};base64,{text}"

    @staticmethod
    def _detect_mime(image_bytes: bytes) -> str:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
            return "image/gif"
        if image_bytes.startswith(b"BM"):
            return "image/bmp"
        return DEFAULT_MIME_TYPE

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    return content
                return str(content)
        return ""

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _first_value(data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data:
                return data[key]
        return None

    @staticmethod
    def _first_text(data: dict[str, Any], *keys: str) -> str | None:
        value = ImageParseAgent._first_value(data, *keys)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _extract_url(text: str) -> str | None:
        match = re.search(r"(data:image/[^\s]+|https?://[^\s]+|file:///[^\s]+|file://[^\s]+)", text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
        joined = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{joined})\s*[:=：]\s*(.+)", text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip().strip("\"'")

    @staticmethod
    def _extract_labeled_int(text: str, labels: tuple[str, ...]) -> int | None:
        joined = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{joined})\s*[:=：]?\s*(\d+)", text, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_image_index(text: str) -> int | None:
        match = re.search(r"第\s*(\d+)\s*张", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _message_id_from_context(task: str, message_number: int) -> int | None:
        pattern = rf"消息编号\s*{message_number}\s*->\s*message_id\s*(\d+)"
        match = re.search(pattern, task)
        return int(match.group(1)) if match else None

    @staticmethod
    def _message_id_from_delegate_context(delegate_context: str, message_number: int) -> int | None:
        """从主Agent传入的 _delegate_context 中按消息编号查找真实 message_id。"""
        try:
            ctx = json.loads(delegate_context)
        except (json.JSONDecodeError, TypeError):
            return None
        # delegate_context 格式可能是 {"messages": [...]}  或直接是消息列表，或含映射表
        messages = ctx.get("messages") if isinstance(ctx, dict) else None
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict) and msg.get("message_number") == message_number:
                    mid = msg.get("message_id")
                    if mid is not None:
                        return int(mid)
        # 也尝试 mapping 字段
        mapping = ctx.get("mapping") if isinstance(ctx, dict) else None
        if isinstance(mapping, dict):
            mid = mapping.get(str(message_number))
            if mid is not None:
                return int(mid)
        return None

    @staticmethod
    def _missing_image_response(task: str, delegate_context: str, exc: Exception) -> str:
        """当缺少图片信息时，返回友好的引导消息而不是直接报错。"""
        error_msg = str(exc)
        # Only show the "missing image info" hint for ValueError (missing params),
        # not for network/API errors
        if not isinstance(exc, ValueError):
            return f"图片解析失败：{error_msg}"

        hint = (
            "图片解析失败。请提供图片信息：\n"
            "- image_url: 图片链接（http/https/data URL）\n"
            "- image_path: 本地图片路径\n"
            "- image_base64: 图片 base64 编码\n"
            "- message_id: 聊天消息的真实 message_id\n"
            "- message_number: 聊天消息编号（需配合上下文中的消息编号映射使用）\n\n"
        )
        # 如果有 delegate_context，尝试提取消息编号映射帮助排查
        if delegate_context:
            try:
                ctx = json.loads(delegate_context)
            except (json.JSONDecodeError, TypeError):
                pass
            else:
                messages = ctx.get("messages") if isinstance(ctx, dict) else None
                if isinstance(messages, list) and messages:
                    hint += "当前可用的消息编号映射：\n"
                    for msg in messages:
                        if isinstance(msg, dict):
                            mn = msg.get("message_number", "?")
                            mid = msg.get("message_id", "?")
                            text = str(msg.get("text") or msg.get("raw_message") or "")[:60]
                            hint += f"  消息编号 {mn} → message_id {mid}（{text}...）\n"
        hint += (
            "\n注意：头像解析请委托 memory agent；图库/表情包管理请委托 creator agent；"
            "聊天互动/群管理/好友管理请委托 chat_interaction agent。"
        )
        return hint


def build_image_parse_agent(
    provider: Provider,
    *,
    adapter: "OneBotAdapter | None" = None,
    logger: Logger | None = None,
) -> ImageParseAgent:
    return ImageParseAgent(provider=provider, adapter=adapter, logger=logger)
