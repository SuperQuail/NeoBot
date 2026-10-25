"""B站作为跨聊天通道 — 供 CrossChatSkill 把任务投到 B站、或查询 B站对话。

B站侧没有常驻主 agent，所以「投递任务」= 用一次 LLM 调用把任务改写成符合人设的
B站发言，再由 client 发出去；有生成结果时回传给发起方聊天。

conversation_id 约定（CrossChatSkill 的 target_id）：
  private:<uid>                       B站私信会话（对方的 UID）
  comment:<oid>:<root>:<parent>       视频/稿件评论区楼中楼（type=1）
  dynamic:<oid>:<root>:<parent>       动态评论区（type=17）
  opus:<oid>:<root>:<parent>          图文动态（type=11）
  article:<oid>:<root>:<parent>       专栏（type=12）
  live:<room_id>                      直播间弹幕（由 live_interactor 发送/读历史，仅开播时发送）
"""

from __future__ import annotations

import random
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field, resolve_client
from neobot_app.bilibili.prompts import MAX_LIVE_DANMAKU_CHARS
from neobot_app.reply.postprocess import split_into_sentences_w_remove_punctuation
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.channel")

#: 评论区前缀 -> reply type_（B站 CommentResourceType，与 BilibiliClient 的
#: comment_type 对齐：视频 1、动态 17、专栏/opus 12、番剧 11）。opus 不是番剧 11。
_COMMENT_KINDS = {
    "comment": 1,
    "video": 1,
    "dynamic": 17,
    "opus": 12,
    "article": 12,
}
_MAX_HISTORY_LINES = 30


class BilibiliCrossChatChannel:
    """CrossChatSkill 的 B站后端：send_task / get_history。"""

    def __init__(
        self,
        client: Any = None,
        reply_engine: Any = None,
        live_interactor: Any = None,
    ) -> None:
        # client 可以是 BilibiliClient 或 BilibiliService（调用时重新解析登录态）。
        self._client = client
        self._engine = reply_engine
        self._live = live_interactor

    @property
    def available(self) -> bool:
        return bool(getattr(self._engine, "available", False))

    async def send_task(
        self, conversation_id: str, task: str
    ) -> tuple[bool, str, str]:
        """把任务变成一句 B站发言并发送。返回 (是否成功, 生成的回复, 说明)。"""
        target = parse_conversation_id(conversation_id)
        if target is None:
            return False, "", (
                "B站会话ID格式错误，应为 private:<uid>、live:<room_id> 或 "
                "comment:<oid>:<root>:<parent>（可把点赞/回复目标写在 task 里）"
            )
        if target["kind"] == "live":
            return await self._send_live_task(target["room_id"], task)
        client = resolve_client(self._client)
        if client is None:
            return False, "", "B站未登录或客户端不可用"
        if self._engine is None or not getattr(self._engine, "available", False):
            return False, "", "B站回复引擎不可用"
        history = ""
        if target["kind"] == "private":
            history = await self.get_history(conversation_id, count=20)
        reply = await self._engine.generate_task_reply(str(task or ""), history=history)
        if reply is None:
            return False, "", "B站侧决定不回应这个任务"
        if target["kind"] == "private":
            sent = await call_client(
                client.send_message, target["uid"], reply
            )
        else:
            sent = await call_client(
                client.send_comment_reply,
                oid=target["oid"],
                root=target["root"],
                parent=target["parent"],
                text=reply,
                type_=target["type_"],
            )
        if not sent:
            logger.warning(f"B站跨聊天投递失败：会话 {conversation_id}")
            return False, "", "B站发送失败（可能被风控或评论区已关闭）"
        logger.info(f"B站跨聊天任务已发送：会话 {conversation_id}，{len(reply)} 字")
        return True, reply, "已发送到B站"

    async def _send_live_task(
        self, room_id: int, task: str
    ) -> tuple[bool, str, str]:
        """把任务生成一条直播弹幕；未开播时既不生成也不发送。"""
        if self._live is None:
            return False, "", "B站直播交互器不可用"
        if self._engine is None or not getattr(self._engine, "available", False):
            return False, "", "B站回复引擎不可用"
        try:
            live = await self._live.is_live(room_id)
        except Exception as exc:
            logger.warning(
                f"B站直播开播状态读取失败：房间 {room_id} {type(exc).__name__}: {exc}"
            )
            live = False
        if not live:
            return False, "", "未开播，不互动"
        history = await self.get_history(f"live:{room_id}", count=20)
        frame_context = ""
        try:
            frame_context = await self._live.frame_context(room_id)
        except Exception as exc:
            logger.debug(f"B站直播跨聊天画面读取失败：房间 {room_id} {exc}")
        content = str(task or "")
        if frame_context:
            content += f"\n[当前直播画面]\n{frame_context}"
        reply = await self._engine.generate_task_reply(content, history=history, live=True)
        if reply is None:
            return False, "", "B站侧决定不回应这个任务"
        segments = [
            part.strip()
            for part in split_into_sentences_w_remove_punctuation(
                reply, rng=random.Random(0)
            )
            if part.strip()
        ]
        if not segments:
            return False, "", "B站弹幕为空"
        overlong = [part for part in segments if len(part) > MAX_LIVE_DANMAKU_CHARS]
        if overlong:
            return False, reply, "弹幕超过20字，请改短后重新投递"
        sent_parts: list[str] = []
        for part in segments:
            result = await self._live.send_danmaku(room_id, part)
            if not result.get("ok"):
                detail = str(result.get("error") or "B站直播弹幕发送失败")
                logger.warning(f"B站直播跨聊天投递失败：房间 {room_id} {detail}")
                return False, " ".join(sent_parts), detail
            sent_parts.append(part)
        logger.info(f"B站直播跨聊天任务已发送：房间 {room_id}，{len(reply)} 字")
        return True, reply, "已发送到B站直播间"

    async def get_history(self, conversation_id: str, count: int = 20) -> str:
        """读取 B站对话内容，格式化成给 QQ agent 看的文本。"""
        target = parse_conversation_id(conversation_id)
        if target is None:
            return ""
        limit = max(1, min(int(count or 20), _MAX_HISTORY_LINES * 2))
        if target["kind"] == "live":
            return self._render_live_history(target["room_id"], limit)
        client = resolve_client(self._client)
        if client is None:
            return ""
        try:
            if target["kind"] == "private":
                messages = await call_client(client.get_messages, target["uid"], size=limit)
                return _render_private_history(messages, client)
            # 按 target 的评论区类型取评论：动态/专栏/opus 不能读视频评论区（type=1）。
            page = await call_client(
                client.get_comments, target["oid"], target["type_"], page_size=limit
            )
            items = page.get("items") if isinstance(page, dict) else page
            return _render_comment_history(items, limit)
        except Exception as exc:
            logger.warning(
                f"B站跨聊天历史读取失败：会话 {conversation_id} "
                f"{type(exc).__name__}: {exc}"
            )
            return ""

    def _render_live_history(self, room_id: int, limit: int) -> str:
        if self._live is None:
            return ""
        try:
            formatter = getattr(self._live, "format_history", None)
            if callable(formatter):
                return str(formatter(room_id, limit) or "")
            items = self._live.get_history(room_id, limit)
        except Exception as exc:
            logger.warning(
                f"B站直播历史读取失败：房间 {room_id} {type(exc).__name__}: {exc}"
            )
            return ""
        lines: list[str] = []
        for item in items or []:
            text = str(get_field(item, "text", "") or "").strip()
            if text:
                name = str(get_field(item, "name", "") or "观众")
                lines.append(f"{name}:{text}")
        return "\n".join(lines)


def parse_conversation_id(conversation_id: Any) -> dict | None:
    """解析 conversation_id；非法格式返回 None。"""
    text = str(conversation_id or "").strip()
    parts = text.split(":")
    if len(parts) == 2 and parts[0] in ("private", "pmsg"):
        try:
            uid = int(parts[1])
        except ValueError:
            return None
        return {"kind": "private", "uid": uid} if uid > 0 else None
    if len(parts) == 2 and parts[0] == "live":
        try:
            room_id = int(parts[1])
        except ValueError:
            return None
        return {"kind": "live", "room_id": room_id} if room_id > 0 else None
    if len(parts) == 4 and parts[0] in _COMMENT_KINDS:
        try:
            oid, root, parent = (int(parts[1]), int(parts[2]), int(parts[3]))
        except ValueError:
            return None
        if oid <= 0 or root <= 0 or parent <= 0:
            return None
        return {
            "kind": "comment",
            "type_": _COMMENT_KINDS[parts[0]],
            "oid": oid,
            "root": root,
            "parent": parent,
        }
    return None


def _render_private_history(messages: Any, client: Any) -> str:
    my_uid = int(getattr(client, "my_uid", 0) or 0)
    lines: list[str] = []
    ordered = sorted(
        list(messages or []), key=lambda msg: int(get_field(msg, "timestamp", 0) or 0)
    )
    for msg in ordered[-_MAX_HISTORY_LINES:]:
        text = _message_text(msg)
        if not text:
            continue
        sender = int(get_field(msg, "sender_uid", 0) or 0)
        who = "你" if (my_uid and sender == my_uid) or get_field(msg, "is_self", False) else f"UID:{sender}"
        lines.append(f"{who}:{text}")
    return "\n".join(lines)


def _render_comment_history(comments: Any, limit: int) -> str:
    lines: list[str] = []
    for comment in list(comments or [])[:limit]:
        member = get_field(comment, "member", None) or {}
        content = get_field(comment, "content", None) or {}
        uname = str(get_field(member, "uname", "") or "?")
        message = str(get_field(content, "message", "") or "").replace("\n", " ")
        if message:
            lines.append(f"@{uname}:{message}")
    return "\n".join(lines)


def _message_text(msg: Any) -> str:
    text = get_field(msg, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    content = get_field(msg, "content", "")
    if isinstance(content, dict):
        return str(content.get("content", "") or "").strip()
    raw = str(content or "").strip()
    return raw if int(get_field(msg, "msg_type", 1) or 1) == 1 else ""
