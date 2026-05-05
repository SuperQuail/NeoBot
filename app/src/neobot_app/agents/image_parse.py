"""Image parsing sub-agent."""

from __future__ import annotations

import asyncio
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
from neobot_app.statistics.tracker import CURRENT_USAGE_MODULE, get_usage_tracker

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


EXPOSED_TO_MAIN_AGENT_NAME = "image_parse"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "图片内容解析。按指定需求解析聊天中的图片内容；可使用主Agent传入的聊天上下文和消息编号映射自动定位“这张图/刚才那张图”。"
    "支持 image_path（本地图片路径）、image_url（HTTP/data/file URL）、image_base64（base64编码）。"
    "仅负责解析回传结果，不保存、不导入、不管理图库/表情包。"
    "如果上下文仍不足以确定图片，会要求主Agent向用户询问更明确的图片或消息编号。"
    "头像解析委托 memory（它内部调用本agent），图片入库委托 creator。"
)

# 同级 sub agent 描述，用于识别任务是否应委托给其他 agent
PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片。\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注/聊天记录、解析用户头像（头像解析由 memory 负责，不要直接处理）、调整好感度。\n"
    "- chat_interaction: 聊天互动、群管理、好友管理、发送表情包。\n"
    "你只负责按需求解析图片内容。如果收到的任务是：保存图片/导入图库/表情包 → 告知主Agent委托 creator；头像解析 → 委托 memory；群管理/好友管理 → 委托 chat_interaction。"
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


@dataclass(frozen=True)
class ContextImageCandidate:
    message_number: int
    message_id: int | None
    line: str


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

    def _get_model_timeout_seconds(self) -> float:
        return 60.0

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    async def invoke(self, state: State) -> State:
        messages = list(state.get("messages", []))
        task = self._last_user_text(messages)
        delegate_context = str(state.get("_delegate_context") or "")
        tm = CURRENT_USAGE_MODULE.set("agent:image_parse")
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
        finally:
            CURRENT_USAGE_MODULE.reset(tm)
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
        response = await asyncio.wait_for(
            self._provider.chat(messages),
            timeout=self._get_model_timeout_seconds(),
        )

        usage = (response.get("extensions") or {}).get("usage")
        if isinstance(usage, dict) and hasattr(self._provider, "model"):
            try:
                await get_usage_tracker().record(
                    module=CURRENT_USAGE_MODULE.get("agent:image_parse"),
                    model_name=self._provider.model,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                )
            except Exception:
                pass

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

        if request.message_number is not None:
            raise ValueError(
                f"上下文中无法将消息编号 {request.message_number} 转换为真实 message_id。"
                "请主Agent确认消息编号映射是否包含该消息，或向用户询问要解析哪条图片消息。"
            )

        if delegate_context and not any([
            request.image_url,
            request.image_path,
            request.image_base64,
            request.message_id,
            request.message_number,
        ]):
            candidate = self._infer_image_candidate_from_context(task, delegate_context)
            if candidate is not None:
                if candidate.message_id is None:
                    raise ValueError(
                        f"已在上下文中找到图片消息编号 {candidate.message_number}，但缺少真实 message_id 映射。"
                        "请主Agent补充该消息编号对应的 message_id。"
                    )
                return await self._chat_image_data_url(
                    message_id=candidate.message_id,
                    image_index=request.image_index,
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
            requirement = self._extract_labeled_value(
                head, ("requirement", "request", "prompt", "需求", "解析需求")
            )
        if not requirement:
            requirement = self._clean_requirement_text(head) or DEFAULT_REQUIREMENT

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
        if message_number is None:
            message_number = self._extract_message_number_phrase(head)
        if image_index == 1:
            image_index = self._extract_labeled_int(head, ("image_index", "图片序号")) or self._extract_image_index(head) or 1

        if not any([image_url, image_path, image_base64, message_id is not None, message_number is not None]):
            image_path = self._extract_filesystem_path(head)

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
        result = await asyncio.wait_for(
            self._adapter.call_api("get_msg", {"message_id": message_id}),
            timeout=self._get_io_timeout_seconds(),
        )
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
        if ref.startswith("file://"):
            local_ref = ref[7:]  # strip 'file://'
            if local_ref.startswith("//"):
                local_ref = local_ref[2:]  # strip authority '//' (e.g. file:///home/...)
            return self._local_image_data_url(local_ref)
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
            result = await asyncio.wait_for(
                self._adapter.call_api("get_image", {"file": ref}),
                timeout=self._get_io_timeout_seconds(),
            )
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, dict):
                img_ref = data.get("file") or data.get("url")
                if isinstance(img_ref, str) and img_ref.strip() and img_ref.strip() != ref:
                    return await self._image_ref_to_data_url(img_ref, mime_type)
        raise LookupError("无法读取图片内容")

    @staticmethod
    def _local_image_data_url(image_path: str) -> str:
        path = image_path.strip()
        if path.startswith("file://"):
            path = path[7:]  # strip 'file://'
            if path.startswith("//"):
                path = path[2:]  # strip authority '//'
        prepared = prepare_local_image(path)
        return ImageParseAgent._bytes_data_url(prepared.image_bytes, prepared.mime_type)

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
    def _extract_message_number_phrase(text: str) -> int | None:
        patterns = (
            r"消息\s*(\d+)",
            r"编号\s*(\d+)",
            r"第\s*(\d+)\s*(?:条|个)?\s*消息",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        return None

    _PARAM_LABELS = (
        "image_path", "image_url", "image_base64", "message_id",
        "message_number", "image_index", "mime_type", "mime",
        "requirement", "request", "prompt", "需求", "解析需求",
        "path", "file_path", "url", "base64", "b64", "本地路径",
    )

    _PARAM_LINE_RE = re.compile(
        r"^\s*(?:" + "|".join(re.escape(l) for l in _PARAM_LABELS) + r")\s*[:=：].*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )

    _FILESYSTEM_PATH_RE = re.compile(
        r"(?:[A-Za-z]:[\\/][^\s<>:|?*]+|/(?:[^\s<>:|?*]+/)*[^\s<>:|?*]+|~/[^\s<>:|?*]+)"
    )

    @staticmethod
    def _clean_requirement_text(text: str) -> str:
        return ImageParseAgent._PARAM_LINE_RE.sub("", text).strip()

    @staticmethod
    def _extract_filesystem_path(text: str) -> str | None:
        match = ImageParseAgent._FILESYSTEM_PATH_RE.search(text)
        if not match:
            return None
        candidate = match.group(0).strip()
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return candidate
        return None

    @staticmethod
    def _message_id_from_context(task: str, message_number: int) -> int | None:
        pattern = rf"消息编号\s*{message_number}\s*->\s*message_id\s*=?\s*(\d+)"
        match = re.search(pattern, task)
        return int(match.group(1)) if match else None

    @staticmethod
    def _message_id_from_delegate_context(delegate_context: str, message_number: int) -> int | None:
        """从主Agent传入的 _delegate_context 中按消息编号查找真实 message_id。"""
        mapping = ImageParseAgent._message_number_mapping_from_context(delegate_context)
        if message_number in mapping:
            return mapping[message_number]

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
    def _message_number_mapping_from_context(context: str) -> dict[int, int]:
        mapping: dict[int, int] = {}
        pattern = r"消息编号\s*(\d+)\s*->\s*message_id\s*=?\s*(\d+)"
        for match in re.finditer(pattern, context):
            mapping[int(match.group(1))] = int(match.group(2))
        return mapping

    @staticmethod
    def _context_image_candidates(delegate_context: str) -> list[ContextImageCandidate]:
        mapping = ImageParseAgent._message_number_mapping_from_context(delegate_context)
        candidates: list[ContextImageCandidate] = []
        for line in delegate_context.splitlines():
            if not ImageParseAgent._line_has_image_marker(line):
                continue
            match = re.match(r"\s*(\d+)\s*[:：]", line)
            if not match:
                continue
            number = int(match.group(1))
            candidates.append(
                ContextImageCandidate(
                    message_number=number,
                    message_id=mapping.get(number),
                    line=line.strip(),
                )
            )
        return candidates

    @staticmethod
    def _line_has_image_marker(line: str) -> bool:
        return any(marker in line for marker in ("[图片", "[卡片图片", "[CQ:image", "[CQ:cardimage"))

    @staticmethod
    def _infer_image_candidate_from_context(
        task: str,
        delegate_context: str,
    ) -> ContextImageCandidate | None:
        candidates = ImageParseAgent._context_image_candidates(delegate_context)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        text = task.strip()
        latest_markers = (
            "这张",
            "这个图",
            "这图",
            "刚才",
            "刚刚",
            "上一张",
            "上面",
            "最后",
            "最新",
            "图片",
            "图里",
            "图中",
        )
        if any(marker in text for marker in latest_markers):
            return candidates[-1]
        return None

    @staticmethod
    def _missing_image_response(task: str, delegate_context: str, exc: Exception) -> str:
        """当缺少图片信息时，返回友好的引导消息而不是直接报错。"""
        error_msg = str(exc)
        # Only show the "missing image info" hint for ValueError (missing params),
        # not for network/API errors
        if not isinstance(exc, ValueError):
            return f"图片解析失败：{error_msg}"

        context_hint = ""
        if delegate_context:
            candidates = ImageParseAgent._context_image_candidates(delegate_context)
            if candidates:
                context_hint = "\n当前上下文中可见的图片消息：\n" + "\n".join(
                    f"- 消息编号 {item.message_number}"
                    f"{f' -> message_id {item.message_id}' if item.message_id is not None else '（缺少 message_id 映射）'}"
                    f": {item.line[:80]}"
                    for item in candidates
                )
                if len(candidates) > 1:
                    context_hint += (
                        "\n请主Agent向用户询问要解析哪一张图片，或重新委托时明确传入 message_number/message_id。"
                    )
            else:
                context_hint = "\n我已查看主Agent上下文，但没有找到可解析的图片消息。请主Agent向用户询问需要解析哪张图片，或让用户发送/指定图片。"

        hint = (
            "图片解析失败。"
            f"{context_hint}\n\n"
            "重新委托时请提供图片信息之一：\n"
            "- image_url: 图片链接（http/https/data URL）\n"
            "- image_path: 本地图片路径\n"
            "- image_base64: 图片 base64 编码\n"
            "- message_id: 聊天消息的真实 message_id\n"
            "- message_number: 聊天消息编号（需配合上下文中的消息编号映射使用）\n\n"
        )
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
