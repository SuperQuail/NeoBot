"""取消、切分与发送回复工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.reply.output_guard import clean_segments, clean_text
from neobot_app.reply.postprocess import (
    ReplyPostProcessResult,
    ReplySplitPreview,
    build_over_limit_guidance,
    build_over_limit_reject_hint,
    process_reply_text,
)
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def


class _ReplyToolsMixin:
    async def _execute_cancel(self, args: dict) -> str:
        if self._cancel is None:
            return "错误：cancel 处理器未配置"
        reason = str(args.get("reason") or "").strip()
        await self._cancel(reason=reason if reason else None)
        self._ai_check_pending = False
        return "回复已取消" if not reason else f"回复已取消：{reason}"

    def _execute_split_reply(self, args: dict) -> str:
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        result = self._preview_split(clean_text(text, known_sender_names=self._sender_names()))
        self.remember_split_preview(result)
        payload = {
            "ok": bool(result.messages),
            "original_text": text,
            "messages": result.messages,
            "fallback_used": result.fallback_used,
            "reason": result.reason,
        }
        if not result.messages:
            payload["error"] = "回复内容清洗后为空；取消本轮请直接调用 cancel 工具"
        return json.dumps(payload, ensure_ascii=False)

    async def _execute_send_reply(self, args: dict) -> str:
        if self._send_reply is None:
            return "错误：send_reply 处理器未配置"
        raw_text = str(args.get("text") or "")
        statements = self._normalize_statements(args.get("segments"))
        if not raw_text.strip() and not statements and not args.get("images"):
            return "错误：回复内容不能为空（text、segments、images 至少给一个）"
        # 发送前清洗（根因在 role_messages：历史 assistant 消息曾被渲染成
        # 「编号: 名字: 正文」，模型照抄了这个格式）。工具层先清一遍，模型方能
        # 看到自己真正发出去的是什么；sender 侧还有同一套兜底，防止清洗后为空。
        sender_names = self._sender_names()
        text = clean_text(raw_text, known_sender_names=sender_names)
        ai_check_approved = bool(args.get("ai_check_approved") is True)
        # segments 的三种形态：字符串=已确认的最终分条；对象 raw=true=该条整段直发；
        # 对象不带 raw=该条交给系统自动切分。逐条清洗以保住每条自己的 raw 归属。
        plain_segments = bool(statements) and all(kind == "final" for _, kind in statements)
        statement_texts = tuple(text for text, _ in statements) if statements else ()
        # Provenance 只对「纯字符串 segments」成立；对象语句是新的显式编排，不走预览溯源。
        matched_preview = plain_segments and any(
            preview.matches(text, statement_texts) for preview in self._split_previews
        )
        cleaned_all = clean_segments(
            statement_texts or (), known_sender_names=sender_names,
            suppress_control_tokens=not matched_preview,
        )
        # 清洗可能丢条目（control-token-only / 标注残渣）；能一一对应才保留逐条 raw 归属。
        statement_kinds = [kind for _, kind in statements] if statements else []
        kinds = statement_kinds if len(cleaned_all) == len(statement_kinds) else ["final"] * len(cleaned_all)
        segments = cleaned_all or None
        split_preview = ReplySplitPreview(text, tuple(segments)) if matched_preview and segments else None
        send_original = bool(args.get("send_original") is True)
        # raw 是 send_original 的「本来就不该切」入口：两者共用同一条整段直发路径
        # （跳过自动切分、AI 检查与超限拦截），差别只在语义与回执的 raw 标记。
        raw = bool(args.get("raw") is True)
        send_original = send_original or raw
        if statements and not segments and not send_original:
            # text is only a placeholder when explicit segments were selected.
            text = ""
        if not text.strip() and not segments and not args.get("images"):
            return (
                "错误：回复内容清洗后为空，未发送。取消本轮请直接调用 cancel 工具。"
                "历史消息行首的 \"[msg_id=...]\"、消息编号、发送者名字都是系统标注，"
                "不是要你模仿的输出格式；请只发送你要说的正文，不要带这些前缀，"
                "也不要把思考过程/草稿写进正文，然后重新调用 send_reply。"
            )
        raw_images = args.get("images")
        images: list[int] | None = None
        if raw_images is not None:
            if not isinstance(raw_images, list):
                return f"错误：images 必须为列表，收到 {type(raw_images).__name__}"
            try:
                images = [int(n) for n in raw_images]
            except (ValueError, TypeError):
                return f"错误：images 必须为整数列表，收到 {raw_images}"
        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return f"错误：reply_to 必须为整数，收到 {reply_to}"
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return f"错误：mention 必须为整数列表，收到 {raw_mention}"

        if not (send_original or segments or images) and not self._preview_split(text).messages:
            return "错误：回复内容清洗后为空，未发送。取消本轮请直接调用 cancel 工具。"

        if self._ai_reply_check and not (
            send_original or ai_check_approved or segments
        ):
            result = self._preview_split(text)
            return self._build_ai_check_prompt(result)

        if (
            self._ai_reply_check_lightweight
            and not self._ai_reply_check
            and not (send_original or ai_check_approved or segments)
        ):
            result = self._preview_split(text)
            if result.fallback_used:
                return self._build_ai_check_prompt(result)

        if self._enable_ai_reply_regenerate and not send_original and not segments:
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    + build_over_limit_reject_hint(
                        max_length=self._long_reply_max_length,
                        max_sentence_count=self._long_reply_max_sentence_count,
                    )
                )

        if self._enable_ai_reply_regenerate and not send_original and ai_check_approved:
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    "当前切分结果为默认回复，并非你的原意。"
                    + build_over_limit_reject_hint(
                        max_length=self._long_reply_max_length,
                        max_sentence_count=self._long_reply_max_sentence_count,
                    )
                )

        # 「多条语句」模式：raw 只对声明它的那条负责，未声明的交给系统自动切分。
        send_segments = segments
        expanded_bodies: list[str] | None = None
        expanded_raw: list[bool] = []
        if segments and not send_original and any(kind == "auto" for kind in kinds):
            expanded_bodies = []
            for position, (body, kind) in enumerate(zip(segments, kinds), start=1):
                if kind != "auto":
                    expanded_bodies.append(body)
                    expanded_raw.append(kind == "raw")
                    continue
                result = self._preview_split(body)
                if result.fallback_used:
                    return (
                        f"错误：第 {position} 条语句无法自动切分（{result.reason}）。"
                        "请把这条拆成更小的语句、对它设置 raw=true 整段发送，或改用 send_long_reply。"
                    )
                for piece in result.messages:
                    expanded_bodies.append(piece)
                    expanded_raw.append(False)
            send_segments = expanded_bodies

        delivered = await self._send_reply(
            text=text,
            reply_to=reply_to,
            mention=mention,
            segments=send_segments,
            send_original=send_original,
            images=images,
            **({"split_preview": split_preview} if split_preview is not None else {}),
        )
        if delivered is False:
            # sender 侧兜底判定「清洗后什么都不剩」：绝不能不吭声地当成发过，
            # 那样模型会以为已经回复，整轮就此结束。
            return (
                "错误：没有可发送的正文或图片，未发送（回复内容清洗后为空时不会发送空消息）。"
                "取消本轮请直接调用 cancel 工具。"
                "不要把消息编号、发送者名字、[msg_id=...] 这类系统标注写进正文，"
                "也不要把思考过程/草稿当成正文；请只发送你要说的那句话，然后重试。"
            )
        self._ai_check_pending = False
        # 回执按「实际发出去的样子」给：raw/send_original 是整段一条，segments 逐条，
        # 其余是自动切分结果——与 sender._build_reply_messages 同一套口径。
        preview: ReplyPostProcessResult | None = None
        if send_original:
            # sender 在 text 清洗后为空时退回 segments，回执跟它保持一致。
            bodies = [text.strip()] if text.strip() else list(segments or [])
            # 整段 raw 由回执顶层的 raw 字段表达，逐条不再重复标记。
            body_raw = [False] * len(bodies)
        elif expanded_bodies is not None:
            bodies = expanded_bodies
            body_raw = expanded_raw
        elif segments:
            bodies = list(segments)
            body_raw = [kind == "raw" for kind in kinds]
        else:
            preview = self._preview_split(text)
            bodies = list(preview.messages)
            body_raw = [False] * len(bodies)
        parts: list[dict] = [
            {"index": index, "type": "image", "image": number}
            for index, number in enumerate(images or [], start=1)
        ]
        for body, is_raw in zip(bodies, body_raw):
            part: dict = {"index": len(parts) + 1, "type": "text", "text": body}
            if is_raw:
                part["raw"] = True
            parts.append(part)
        if images:
            summary = f"已发送（{len(images)} 张图片 + {len(bodies)} 条文字）"
        elif send_original:
            summary = "已发送原文：1 条消息"
        else:
            summary = f"已发送 {len(bodies)} 条消息"
        payload = {
            "ok": True,
            "raw": raw,
            "sent_count": len(parts),
            "parts": parts,
            "summary": summary,
        }
        if preview is not None and preview.fallback_used:
            payload["fallback_used"] = True
            payload["reason"] = preview.reason
        return json.dumps(payload, ensure_ascii=False)

    def remember_split_preview(self, result: ReplyPostProcessResult) -> None:
        """Record only previews actually exposed to the model, never internal checks."""
        if result.messages and not result.fallback_used:
            text = clean_text(result.original_text, known_sender_names=self._sender_names())
            if text:
                self._split_previews.append(ReplySplitPreview(text, tuple(result.messages)))

    def _preview_split(self, text: str) -> ReplyPostProcessResult:
        return process_reply_text(
            text,
            bot_name=self._bot_name,
            fallback_template=self._long_reply_fallback_template,
            max_length=self._long_reply_max_length,
            max_sentence_count=self._long_reply_max_sentence_count,
        )

    @staticmethod
    def _normalize_statements(value: Any) -> list[tuple[str, str]] | None:
        """segments 兼容三种形态：字符串=最终分条；{text,raw:true}=整段直发；
        {text}（或 raw:false）=交给系统自动切分。返回 (文本, final|raw|auto)。"""
        if not isinstance(value, list):
            return None
        statements: list[tuple[str, str]] = []
        for entry in value:
            if isinstance(entry, dict):
                text = str(entry.get("text") or "").strip()
                if text:
                    statements.append((text, "raw" if entry.get("raw") is True else "auto"))
                continue
            text = str(entry or "").strip()
            if text:
                statements.append((text, "final"))
        return statements or None

    @staticmethod
    def _normalize_segments(value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        segments = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, (dict, list)) and not item:
                continue
            text = str(item).strip()
            if text:
                segments.append(text)
        return segments or None

    def _build_ai_check_prompt(self, result: ReplyPostProcessResult) -> str:
        self.remember_split_preview(result)
        self._ai_check_pending = True
        lines = [
            "AI回复检查已开启，暂未发送。",
            "请检查切分后的分条回复是否存在严重问题或明显歧义。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(
                f"注意：因 {result.reason or '未知原因'}，已触发默认回复替换，当前切分结果为默认回复文本。"
            )
            # 明确给出出路：Markdown 直发 / 分批发送 / 精简重发，三选一。
            lines.extend(
                build_over_limit_guidance(
                    max_length=self._long_reply_max_length,
                    max_sentence_count=self._long_reply_max_sentence_count,
                )
            )
            lines.append(
                "若仍要发送上面这段默认回复，请再次调用 send_reply，传入原 text、"
                "segments 为上述切分结果、ai_check_approved=true。"
                "如不应发送任何回复，请调用 cancel。"
            )
        else:
            lines.append(
                "如果没有严重问题或歧义，请再次调用 send_reply，传入原 text、segments 为上述切分结果、ai_check_approved=true。"
            )
            lines.append(
                "如果切分有问题但仍要发送原文，请调用 send_reply 并设置 send_original=true；如果不应发送，请调用 cancel。"
            )
        return "\n".join(lines)

    def _sender_names(self) -> list[str]:
        """发送前清洗用的「本会话出现过的发送者名字」集合。

        必须与发送层（ReplySender）拿到的是同一份集合，否则会出现
        「工具层说已发送、发送层却清空丢弃」的静默缝（审查实测：
        群名片≠配置昵称时 text="169: 某群友:" 会从这条缝漏过去）。

        名字来源：配置昵称 + 队列里出现过的全部发送者（昵称/群名片）。
        队列由 MessageNumbering 持有（见 numbering.MessageNumbering(queue=...)），
        拿不到时退化为「只有配置昵称 + 本会话发送者快照」。
        """
        names = self._known_sender_names()
        if str(self._bot_name or "").strip():
            names.insert(0, str(self._bot_name).strip())
        seen: set[str] = set()
        unique: list[str] = []
        for name in names:
            text = str(name or "").strip()
            if text and text not in seen:
                seen.add(text)
                unique.append(text)
        return unique

    def _known_sender_names(self) -> list[str]:
        """从编号实例持有的队列里取全部发送者显示名（取不到就返回空）。"""
        method = getattr(self._numbering, "known_sender_names", None)
        if callable(method):
            try:
                return list(method())
            except Exception:
                return []
        return []

    def _define_reply_tools(self, tools: list[ToolDefinition]) -> None:
        if self._cancel is not None:
            tools.append(
                _tool_def(
                    "cancel",
                    "主动结束本轮回复事件。当认为自己不适合参与当前话题、不需要回复、"
                    "或已通过其他方式完成互动时调用。调用后本轮回复立即结束，不再发送任何消息。"
                    "取消必须真正调用本工具，不要先发送 cancel 或取消说明；reason 不会发到聊天。",
                    {
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "可选，取消回复的简要原因。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        tools.append(
            _tool_def(
                "split_reply",
                "只切分回复文本，不发送。用于在发送前查看分条结果；send_reply 实际发送时也会自动切分。"
                "确认本预览后，把原 text 和完整 messages 作为 segments 传给 send_reply；AI检查开启时可设置 ai_check_approved=true。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "需要切分的回复内容。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        tools.append(
            _tool_def(
                "send_reply",
                "向当前会话发送回复，可附带表情包图片。agent 模式下这是对外发言的唯一出口："
                "只有调用本工具（长文用 send_long_reply）才会真正发出消息，"
                "直接输出的正文不会发送，且本轮会被判为失败。"
                "发送图片时每张图片单独作为一条消息发送，文字另外单独发送；"
                "图片与文字不会合并到同一条消息里。"
                "文字发送时自动按句子切分：标点或换行处断开，相邻的短句可能再合并，"
                "所以一段话通常会变成几条消息，回执会列出实际发成的每条内容；"
                "超过长度或条数上限时会被拦截，回执会提示改用 send_long_reply 或分批发送。"
                "需要原样整段发送（代码、排版或必须保持完整的一段话）时设 raw=true："
                "不切分、整段作为一条消息发出，也不触发 AI 回复检查或超限拦截；"
                "需要多条语句时用 segments 分开，每条对象可单独设 raw："
                "例如数学公式那条设 raw=true 保持完整，其余语句交给系统自动切分。"
                "本工具只发送消息，不结束本轮；发送后仍可继续调用其他工具。"
                "只有 cancel 会结束一轮回复；允许在同一轮内多次发送，用于长任务的开工与进度。"
                "text/segments 只放你要说的那句话本身：不要带消息编号、发送者名字、"
                "[msg_id=...]、[被回复消息] 这类系统标注（它们是系统给你读的，不是输出格式），"
                "也不要把思考过程、草稿、计划或 <think> 标签写进去。"
                "例如要回一句「你好呀」，text 就写 \"你好呀\"，不要写 \"12: 某群友: 你好呀\"；"
                "要引用某条消息时用 reply_to 传编号，正文里不要再写一遍编号和名字。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "回复内容，只填你要说的那句话本身，尽量自然简洁。"
                            "不要带编号/名字/[msg_id=...] 等系统标注，也不要写思考过程。"
                            "用 segments 提供多条语句时可以省略；text、segments、images 至少给一个。",
                        },
                        "reply_to": {
                            "type": "integer",
                            "description": "可选，要引用回复的消息编号。由 agent 根据上下文自行决定是否需要引用。",
                        },
                        "mention": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效，由 agent 自行决定是否 @ 以及 @ 谁。仅在需要提醒通知某人时使用。正文里需要表达 @ 时，没有特殊情况应在 @ 后留一个空格（例如「@ 某人」）；特殊需要可自行不加。",
                        },
                        "segments": {
                            "type": "array",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string"},
                                            "raw": {"type": "boolean"},
                                        },
                                        "required": ["text"],
                                    },
                                ],
                            },
                            "description": "可选，按顺序提供多条语句，每条作为一条消息发送。"
                            "字符串元素=已确认的最终分条，系统不再切分（回传 split_reply/AI 检查预览时用这种，"
                            "text 必须保留原文且 segments 必须是完整预览）；"
                            "对象 {text, raw}：raw=true 该条整段直发（不切分、跳过该条的 AI 检查与超限拦截，"
                            "公式/代码/排版用），不加 raw 或 raw=false 则该条交给系统自动切分。"
                            "支持混合，例如 [{\"text\":\"公式 $a^2+b^2=c^2$\",\"raw\":true},{\"text\":\"其余照常说。\"}]。"
                            "每条的正文只放自己的话，不要带编号/发送者名字/[msg_id=...] 等系统标注，也不要写思考过程；"
                            "只剩标注或只剩思考的条目会被丢弃。",
                        },
                        "images": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要发送的表情包编号列表。每张图片单独作为一条消息发送，文字另外单独发送，不会合并到同一条消息。",
                        },
                        "ai_check_approved": {
                            "type": "boolean",
                            "description": "AI回复检查开启时，确认切分结果没有严重问题或歧义后设为 true。",
                        },
                        "send_original": {
                            "type": "boolean",
                            "description": "AI回复检查开启且切分结果有问题但仍要发送时设为 true；会发送整段原文，不再切分，但不会跳过输出安全清洗。对于 @ 和引用消息也适用。与 raw 走同一条整段直发路径，只是语义不同：send_original 是「检查后仍要发原文」，raw 是「本来就不需要切分」。对整段 text 生效，且优先于 segments 的逐条 raw。",
                        },
                        "raw": {
                            "type": "boolean",
                            "description": "需要原样整段发送时设为 true：不切分，把清洗后的整段文本作为一条消息发出，也不触发 AI 回复检查与超限拦截。适合代码、排版或必须保持完整的一段话；默认 false（自动按句子切分）。只对 text 整段生效；想只让 segments 里某一条语句不切分，请在该条对象里设 raw=true。与 send_original 等价于同一条直发路径，只是意图不同。",
                        },
                    },
                    "required": [],
                },
            ),
        )
