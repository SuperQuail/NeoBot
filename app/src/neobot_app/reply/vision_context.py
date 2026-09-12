"""Run-local images: textual history plus a labelled image appendix per request.

原生视觉的"怎么用"说明(位置约定、别改用外部解析模型、加载失败不许猜)属于稳定的
system 提示词内容,见 prompts.toml 的 [native_vision] 分区;本模块只负责每次请求
动态生成的图片附录。
"""

from __future__ import annotations

import json
from typing import Any


def append_image_context(messages: list[dict], parts: list[dict]) -> None:
    """Append only at the request boundary, after all text and complete tool batches."""
    if parts:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "[视觉上下文] 以下图片按对应来源标注排列；未加载的图片仍只有正文文本描述。"},
                *parts,
            ],
        })


def labelled_tool_images(result: Any, *, tool_call_id: str = "", automatic: bool = False) -> list[dict]:
    """Pair every tool image with metadata identifying the source, never raw arguments."""
    metadata = json.loads(str(result))
    images = metadata.get("images") or []
    parts = []
    mode = "默认加载图片" if automatic else "主动加载图片"
    for index, image in enumerate(result.image_parts):
        description = images[index] if index < len(images) else {"index": index}
        parts.extend([
            {"type": "text", "text": f"[{mode}] {tool_call_id}，第 {index + 1} 张；来源与元数据：{json.dumps(description, ensure_ascii=False)}"},
            image,
        ])
    return parts


class ReplyVisionContext:
    """No shared image state; automatic budget never truncates explicitly loaded images."""

    def __init__(self) -> None:
        self.manual_parts: list[dict] = []
        self._automatic: dict[tuple[int, int], list[dict]] = {}

    async def refresh_defaults(
        self, *, queue: Any, queue_key: str, numbering: Any, loader: Any,
        pipeline_key: str, max_images: int,
    ) -> None:
        if max_images <= 0:
            self._automatic.clear()
            return
        from neobot_app.image.source import ImageSourceResolver

        candidates: dict[tuple[int, int], int] = {}
        mapping = numbering.mapping
        displayed = {real_id: number for number, real_id in mapping.items()}
        for entry in queue.entries(queue_key):
            message = getattr(entry, "message", None)
            for item in [*(getattr(entry, "replied_messages", None) or []), message]:
                if item is None:
                    continue
                message_id = getattr(item, "message_id", None)
                if message_id not in displayed:
                    continue
                segments = getattr(item, "message", None) or getattr(item, "content", None) or []
                for index in range(ImageSourceResolver._image_count(segments)):
                    key = (message_id, index)
                    # Quoted images are recent when the quote is recent, without duplicates.
                    candidates.pop(key, None)
                    candidates[key] = displayed[message_id]
        selected = list(candidates.items())[-max_images:]
        labels = {
            key: f"[默认加载图片] 正文消息编号 {number}，消息ID {key[0]}，图片序号 {key[1] + 1}（image_index={key[1]}）"
            for key, number in selected
        }
        cached = self._automatic
        # Replace the selected set *before* awaiting. Cancellation must neither
        # resurrect stale images nor discard already loaded new images.
        self._automatic = {
            key: cached[key] if any(p.get("type") == "image_url" for p in cached.get(key, []))
            else [{"type": "text", "text": f"{labels[key]}；图片尚未加载或加载超时，不能判断其内容。"}]
            for key, _ in selected
        }
        for key, number in selected:
            if any(p.get("type") == "image_url" for p in self._automatic[key]):
                continue
            result = await loader.execute("add_image", {
                "msg_number": number, "image_index": key[1],
                "pipeline_key": pipeline_key, "_numbering_mapping": mapping,
            })
            if result.image_parts:
                self._automatic[key] = [{"type": "text", "text": labels[key]}, *result.image_parts]
            else:
                # Failed loads are visible and may be retried on the next iteration.
                self._automatic[key] = [{"type": "text", "text": f"{labels[key]}；加载失败，未看到图片：{result}"}]

    def request_messages(self, messages: list[dict]) -> list[dict]:
        request = list(messages)
        parts = [part for image in self._automatic.values() for part in image]
        append_image_context(request, [*parts, *self.manual_parts])
        return request


def visible_content_length(content: Any) -> int:
    """Use a conservative image-token allowance, never count base64 as text tokens."""
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    return sum(
        3072 if part.get("type") in {"image_url", "image", "file"}
        else len(str(part.get("text", "")))
        for part in content if isinstance(part, dict)
    )
