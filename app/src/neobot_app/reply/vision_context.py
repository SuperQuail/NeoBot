"""Run-local images: textual history plus a labelled image appendix per request.

原生视觉的"怎么用"说明(位置约定、别改用外部解析模型、加载失败不许猜)属于稳定的
system 提示词内容,见 prompts.toml 的 [native_vision] 分区;本模块只负责每次请求
动态生成的图片附录。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from neobot_app.prompt.assets import text
from neobot_app.utils.prompt_text import single_line_prompt_text


def _vision_text(key: str, *, prompt_store: Any = None, **values: Any) -> str:
    """读取视觉上下文标签：custom 覆盖 / enabled / 内置模板统一走 assets。"""
    return text("label_vision_context", key, store=prompt_store, values=values)


def _text_part(content: str) -> list[dict]:
    """标签被关闭时不要注入空文本段。"""
    return [{"type": "text", "text": content}] if content else []


#: 默认图附录/主动加载图片的公共坐标说明：两个入口必须能对上同一张图，
#: 模型因此不必跨两套坐标系换算（fix(16)）。
def _image_label(sender: str, *, number: Any = None, message_id: Any = None, image_index: Any = None, fallback_index: int = 0, prompt_store: Any = None) -> str:
    parts: list[str] = []
    if sender:
        parts.append(
            _vision_text("sender", prompt_store=prompt_store, sender=sender)
        )
    if number is not None:
        parts.append(
            _vision_text("message_number", prompt_store=prompt_store, number=number)
        )
    if message_id is not None:
        parts.append(
            _vision_text("message_id", prompt_store=prompt_store, message_id=message_id)
        )
    if isinstance(image_index, int):
        parts.append(
            _vision_text(
                "image_index",
                prompt_store=prompt_store,
                index=image_index + 1,
                raw_index=image_index,
            )
        )
    else:
        parts.append(
            _vision_text("fallback_index", prompt_store=prompt_store, index=fallback_index + 1)
        )
    separator = _vision_text("label_separator", prompt_store=prompt_store)
    return separator.join(part for part in parts if part)


def _sender_label(queue: Any, labels: dict, labels_by_user: dict, message: Any) -> str:
    """按聊天记录同一套规则取发送者标签（含重名 QQ 后缀）。

    测试/降级用的轻量 queue 可能没有这两个方法：拿不到就退化为不带发送者，
    图片本身仍按原逻辑加载。
    """
    try:
        label = queue._message_sender_label(
            message, sender_labels=labels, sender_labels_by_user=labels_by_user
        )
    except (AttributeError, TypeError):
        return ""
    return single_line_prompt_text(label)


def append_image_context(
    messages: list[dict], parts: list[dict], *, prompt_store: Any = None
) -> None:
    """Append only at the request boundary, after all text and complete tool batches."""
    if not parts:
        return
    intro = _vision_text("intro", prompt_store=prompt_store)
    messages.append({
        "role": "user",
        "content": [
            *_text_part(intro),
            *parts,
        ],
    })


def labelled_tool_images(
    result: Any, *, tool_call_id: str = "", automatic: bool = False, prompt_store: Any = None
) -> list[dict]:
    """Pair every tool image with metadata identifying the source, never raw arguments.

    坐标与默认图附录一致（发送者/正文消息编号/消息ID/图片序号）；tool_call_id 只
    作为定位串保留，不再单独用「第 N 张」这类另一套序号。
    """
    metadata = json.loads(str(result))
    images = metadata.get("images") or []
    parts = []
    mode = (
        _vision_text("mode_default", prompt_store=prompt_store)
        if automatic
        else _vision_text("mode_active", prompt_store=prompt_store)
    )
    for index, image in enumerate(result.image_parts):
        description = images[index] if index < len(images) else {"index": index}
        coordinate = _image_label(
            single_line_prompt_text(description.get("sender")),
            number=description.get("msg_number"),
            message_id=description.get("message_id"),
            image_index=description.get("image_index"),
            fallback_index=index,
            prompt_store=prompt_store,
        )
        prefix = (
            _vision_text(
                "tool_prefix",
                prompt_store=prompt_store,
                tool_call_id=tool_call_id,
            )
            if tool_call_id
            else ""
        )
        label_text = _vision_text(
            "tool_label",
            prompt_store=prompt_store,
            mode=mode,
            prefix=prefix,
            coordinate=coordinate,
            metadata=json.dumps(description, ensure_ascii=False),
        )
        parts.extend([
            *_text_part(label_text),
            image,
        ])
    return parts


class ReplyVisionContext:
    """No shared image state; automatic budget never truncates explicitly loaded images."""

    def __init__(self, prompt_store: Any = None) -> None:
        self._prompt_store = prompt_store
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
        senders: dict[tuple[int, int], str] = {}
        mapping = numbering.mapping
        displayed = {real_id: number for number, real_id in mapping.items()}
        entries = queue.entries(queue_key)
        try:
            sender_labels, sender_labels_by_user = queue._build_sender_labels(entries)
        except (AttributeError, TypeError):
            sender_labels, sender_labels_by_user = {}, {}
        for entry in entries:
            message = getattr(entry, "message", None)
            for item in [*(getattr(entry, "replied_messages", None) or []), message]:
                if item is None:
                    continue
                message_id = getattr(item, "message_id", None)
                if message_id not in displayed:
                    continue
                segments = getattr(item, "message", None) or getattr(item, "content", None) or []
                sender = _sender_label(queue, sender_labels, sender_labels_by_user, item)
                for index in range(ImageSourceResolver._image_count(segments)):
                    key = (message_id, index)
                    # Quoted images are recent when the quote is recent, without duplicates.
                    candidates.pop(key, None)
                    candidates[key] = displayed[message_id]
                    senders[key] = sender
        selected = list(candidates.items())[-max_images:]
        store = self._prompt_store
        labels = {
            key: _vision_text(
                "default_label",
                prompt_store=store,
                label=_image_label(
                    senders.get(key, ""),
                    number=number,
                    message_id=key[0],
                    image_index=key[1],
                    prompt_store=store,
                ),
            )
            for key, number in selected
        }
        cached = self._automatic
        # Replace the selected set *before* awaiting. Cancellation must neither
        # resurrect stale images nor discard already loaded new images.
        self._automatic = {
            key: cached[key] if any(p.get("type") == "image_url" for p in cached.get(key, []))
            else _text_part(
                _vision_text(
                    "not_loaded",
                    prompt_store=store,
                    label=labels[key],
                )
            )
            for key, _ in selected
        }
        pending = [
            (key, number) for key, number in selected
            if not any(p.get("type") == "image_url" for p in self._automatic[key])
        ]
        if not pending:
            return

        async def load(key: tuple[int, int], number: int) -> None:
            result = await loader.execute("add_image", {
                "msg_number": number, "image_index": key[1],
                "pipeline_key": pipeline_key, "_numbering_mapping": mapping,
            })
            if result.image_parts:
                self._automatic[key] = [*_text_part(labels[key]), *result.image_parts]
            else:
                # Failed loads are visible and may be retried on the next iteration.
                self._automatic[key] = _text_part(
                    _vision_text(
                        "load_failed",
                        prompt_store=store,
                        label=labels[key],
                        error=result,
                    )
                )

        # 并发拉取：默认一次挑 4 张，串行会把每张的超时叠起来（4 × 15 秒 = 一轮 60 秒
        # 纯等待，正好吃掉群聊静默预算）。并发后最坏只等一次超时；每张图各自写回自己的
        # key，外层 wait_for 取消时已加载完的不会被丢掉。
        await asyncio.gather(
            *(load(key, number) for key, number in pending),
            return_exceptions=True,
        )

    def request_messages(self, messages: list[dict]) -> list[dict]:
        request = list(messages)
        parts = [part for image in self._automatic.values() for part in image]
        append_image_context(
            request, [*parts, *self.manual_parts], prompt_store=self._prompt_store
        )
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
