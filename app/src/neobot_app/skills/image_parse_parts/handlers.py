"""parse_image 工具的处理函数与注册表。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import base64
from pathlib import Path

from neobot_app.utils.logger import get_module_logger
from neobot_app.image.speaking import check_image_policy, pipeline_conversation
from neobot_contracts.ports.speaking import SpeechBlocked

from .helpers import _json

if TYPE_CHECKING:
    from ..image_parse_skill import ImageParseSkill

logger = get_module_logger("skills.image_parse")

# ── Handler ──

async def _handle_parse_image(self: ImageParseSkill, args: dict) -> str:
    if self._vision_provider is None:
        # 视觉模型不可用只写日志；不要把错误文案交给 agent/聊天流。
        logger.warning("图片解析视觉模型未配置，跳过解析（仅记录日志）")
        return _json({"ok": True, "skipped": True, "note": ""})
    requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
    image_path = args.get("image_path")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")
    image_path_list = args.get("image_path_list") or []
    image_url_list = args.get("image_url_list") or []
    msg_number = args.get("msg_number")
    message_id = args.get("message_id")
    chat_flow_id = args.get("chat_flow_id")
    image_indices_arg = args.get("image_indices") or []
    pipeline_key = str(args.get("pipeline_key", "")).strip()
    conversation = pipeline_conversation(pipeline_key)
    check_image_policy(self._adapter, conversation)

    try:
        timeout_seconds = float(int(args.get("timeout_seconds", 300) or 300))
    except (TypeError, ValueError, OverflowError):
        return _json({"ok": False, "error": "timeout_seconds 必须是数字(秒)"})
    timeout_seconds = max(1.0, min(timeout_seconds, 1800.0))

    if not any([
        image_path, image_url, image_base64, msg_number, message_id, chat_flow_id,
        image_path_list, image_url_list,
    ]):
        return _json({
            "ok": False,
            "error": "请提供 image_path/image_url/image_base64/msg_number/message_id/chat_flow_id 或对应的 *_list 数组中的至少一种",
        })

    try:
        content_parts: list[dict] = [{"type": "text", "text": requirement}]

        from neobot_app.image.parser import _build_vision_image_part

        def _add_image_part(raw: bytes) -> None:
            content_parts.append(_build_vision_image_part(raw))

        # ── 收集所有图片字节，跟踪其来源索引 ──
        # 当且仅当只有一张时返回兼容的 {"ok": True, "description": "..."} 旧格式
        # 多张时返回 {"ok": True, "descriptions": [{"index": i, "description": "..."}, ...]}
        # 失败的图片位置也会被记录为 {"index": i, "ok": False, "error": ...}

        errors: list[dict] = []
        single_image: bytes | None = None
        multi_images: list[bytes | None] = []

        def _is_multi_mode() -> bool:
            return bool(image_path_list or image_url_list or image_indices_arg)

        def _record_bytes(raw: bytes | None, error_msg: str | None = None) -> None:
            """记录一张图的下载结果：成功入 multi_images，失败记 errors。"""
            multi_images.append(raw)
            if raw is None:
                errors.append({"index": len(multi_images) - 1, "ok": False, "error": error_msg or "下载失败"})

        # ── 路径/URL/base64 多图（显式 list 优先）──
        if image_path_list:
            for p in image_path_list:
                try:
                    raw = Path(str(p)).expanduser().read_bytes()
                    _record_bytes(raw)
                except Exception as exc:
                    _record_bytes(None, f"读取本地图片失败: {exc}")
        elif image_url_list:
            for u in image_url_list:
                content_parts.append({"type": "image_url", "image_url": {"url": str(u)}})
                multi_images.append(b"\x00url\x00")  # placeholder，URL 直接走 content_parts
            # URL 不计入 download 失败评估，这里直接清空同位置 errors 标记
        elif image_path:
            try:
                raw = Path(str(image_path)).expanduser().read_bytes()
                single_image = raw
            except Exception as exc:
                return _json({"ok": False, "error": f"读取本地图片失败: {exc}"})
        elif image_url:
            single_image = b"\x00url\x00"  # 标记 URL 单图
            content_parts.append({"type": "image_url", "image_url": {"url": str(image_url)}})
        elif image_base64:
            try:
                raw = base64.b64decode(str(image_base64))
                single_image = raw
            except Exception as exc:
                return _json({"ok": False, "error": f"base64 解码失败: {exc}"})
        elif msg_number:
            numbering_mapping = args.get("_numbering_mapping")
            if isinstance(numbering_mapping, dict):
                numbering_mapping = {int(k): int(v) for k, v in numbering_mapping.items()}
            else:
                numbering_mapping = None
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_msg_number(
                    pipeline_key, int(msg_number), indices,
                    numbering_mapping=numbering_mapping, timeout=timeout_seconds,
                )
                for i, (raw, err) in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({"index": i, "ok": False, "error": err or f"无法从消息编号 {msg_number}（第 {i} 张图片）获取图片"})
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes, err_reason = await self._resolve_by_msg_number(
                    pipeline_key, int(msg_number), image_index,
                    numbering_mapping=numbering_mapping, timeout=timeout_seconds,
                )
                if image_bytes is None:
                    return _json({"ok": False, "error": err_reason or f"无法从消息编号 {msg_number}（第 {image_index} 张图片）获取图片"})
                single_image = image_bytes
        elif message_id:
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_message_id_with_errors(
                    int(message_id),
                    indices,
                    timeout=timeout_seconds,
                )
                for i, (raw, err) in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({
                            "index": i,
                            "ok": False,
                            "error": err or f"无法从消息 {message_id} 获取第 {i} 张图片",
                        })
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes, err_reason = await self._resolve_by_message_id_with_error(
                    int(message_id),
                    image_index,
                    timeout=timeout_seconds,
                )
                if image_bytes is None:
                    return _json({
                        "ok": False,
                        "error": err_reason or f"无法从消息 {message_id} 获取第 {image_index} 张图片",
                    })
                single_image = image_bytes
        elif chat_flow_id:
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_chat_flow(chat_flow_id, indices, timeout=timeout_seconds)
                for i, raw in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({"index": i, "ok": False, "error": f"无法从 {chat_flow_id} 获取第 {i} 张图片"})
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes = await self._resolve_by_chat_flow(chat_flow_id, image_index, timeout=timeout_seconds)
                if image_bytes is None:
                    return _json({"ok": False, "error": f"无法从 {chat_flow_id} 获取第 {image_index} 张图片"})
                single_image = image_bytes

        # ── 把 multi_images 中真正下载到的字节加入 content_parts（URL 已加入）──
        if _is_multi_mode():
            # multi_images 中混合真实 bytes / None / URL placeholder
            success_count = 0
            for entry in multi_images:
                if entry is None:
                    continue
                if entry == b"\x00url\x00":
                    success_count += 1
                    continue
                _add_image_part(entry)
                success_count += 1
            if success_count == 0:
                return _json({"ok": False, "error": "全部图片下载失败", "details": errors})
        else:
            if single_image is not None and single_image != b"\x00url\x00":
                _add_image_part(single_image)

        # ── 调用 vision 模型 ──
        check_image_policy(self._adapter, conversation)
        result = await self._vision_provider.chat([{"role": "user", "content": content_parts}])
        text = result.get("content", "") if isinstance(result, dict) else str(result)

        if _is_multi_mode():
            # 多图时 vision 模型通常返回整段文本涵盖所有图；
            # 这里把整段描述放 descriptions 数组每项的 description 字段（共享文本，
            # 同时单独给每项 index 与 ok 状态）。如模型按序输出了多段，
            # agent 仍可从 text 中按顺序分辨。
            descriptions = []
            for i, entry in enumerate(multi_images):
                if entry is None:
                    descriptions.append({"index": i, "ok": False, "error": "下载失败"})
                else:
                    descriptions.append({"index": i, "ok": True, "description": text[:2000]})
            return _json({
                "ok": True,
                "descriptions": descriptions,
                "full_text": text[:2000],
                "errors": errors or None,
            })
        return _json({"ok": True, "description": text[:2000]})
    except SpeechBlocked:
        raise
    except Exception as e:
        return _json({"ok": False, "error": f"{type(e).__name__}: {e}"})

_HANDLERS = {
    "parse_image": _handle_parse_image,
}
