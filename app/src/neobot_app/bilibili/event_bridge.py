"""BilibiliEventBridge — 连接 B站 monitors 到 NeoBot ReplyOrchestrator。

将 monitor 检测到的新评论/私信转换为 ReplyOrchestrator 可处理的 reply 事件。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BilibiliEventBridge:
    """B站事件桥接器。

    职责：
    - 将 monitor 的原始事件转换为 ReplyOrchestrator 可消费的格式
    - 构建 CommentContext / PrivateMessageContext
    - 决定 agent_mode vs 单次 LLM 调用
    """

    def __init__(self, orchestrator, prompt_builder, client, config):
        self._orchestrator = orchestrator
        self._prompt_builder = prompt_builder
        self._client = client
        self._config = config
        self._reply_locks: dict[str, asyncio.Lock] = {}

    async def handle_new_comment(
        self,
        raw: dict,
        *,
        source: str = "reply_feed",
        aid: int = 0,
        video_info: Optional[dict] = None,
    ) -> None:
        """处理一条新评论（来自 reply_feed 或 视频扫描）。

        构建 CommentContext 并提交给 ReplyOrchestrator。
        """
        from .prompts import CommentContext, CommentNode

        bilibili_cfg = getattr(self._config, "bilibili", None)
        if bilibili_cfg is None or not bilibili_cfg.comment_reply_enabled:
            return

        try:
            if source == "reply_feed":
                ctx = self._build_context_from_reply_feed(raw)
            else:
                ctx = self._build_context_from_video_comment(raw, aid, video_info)

            if ctx is None:
                return

            if bilibili_cfg.simulate:
                logger.info("[模拟] 评论回复: @%s → %s",
                           ctx.reply_target_rpid, ctx.target_title[:30])
                return

            # 提交给 orchestrator
            if self._orchestrator is not None and bilibili_cfg.enable_agent_mode:
                self._orchestrator.start_bilibili_comment_reply(ctx, self._client)
            elif self._prompt_builder is not None:
                prompt = await asyncio.to_thread(
                    self._prompt_builder.build_bilibili_comment_prompt, ctx
                )
                logger.debug("评论提示词已构建: %d 字符", len(prompt))
                # 单次模式交由 orchestrator 处理
                if self._orchestrator is not None:
                    self._orchestrator.start_bilibili_comment_reply(ctx, self._client)

        except Exception:
            logger.exception("处理评论事件失败")

    async def handle_new_private_message(self, msg, session) -> None:
        """处理一条新私信。"""
        from .prompts import PrivateMessageContext

        bilibili_cfg = getattr(self._config, "bilibili", None)
        if bilibili_cfg is None or not bilibili_cfg.private_message_enabled:
            return

        try:
            ctx = self._build_private_context(msg, session)
            if ctx is None:
                return

            if bilibili_cfg.simulate:
                logger.info("[模拟] 私信回复: @%s", msg.sender_uid)
                return

            if self._orchestrator is not None:
                self._orchestrator.start_bilibili_private_reply(ctx, self._client)

        except Exception:
            logger.exception("处理私信事件失败")

    # ── 内部构建方法 ──

    def _build_context_from_reply_feed(self, item: dict):
        """从 reply_feed item 构建 CommentContext。"""
        from .prompts import CommentContext, CommentNode

        item_data = item.get("item", {})
        user_info = item.get("user", {})

        subject_id = int(item_data.get("subject_id", 0) or 0)
        source_id = int(item_data.get("source_id", 0) or 0)
        root_id = int(item_data.get("root_id", 0) or 0)
        business_id = int(item_data.get("business_id", 1) or 1)

        real_root = root_id if root_id != 0 else source_id
        content = item_data.get("message", "") or item_data.get("source_content", "")

        # 构建单个 CommentNode 作为待回复目标
        target_node = CommentNode(
            rpid=source_id,
            uid=user_info.get("mid", 0),
            uname=user_info.get("nickname", ""),
            content=str(content),
            ctime=item.get("reply_time", 0),
        )

        # 确定 target_type
        bid_map = {1: "视频", 11: "动态", 12: "专栏", 17: "动态"}
        target_type = item_data.get("business", bid_map.get(business_id, "视频"))

        return CommentContext(
            bot_name=self._client.my_uid,  # 会被 prompt builder 覆盖
            bot_uid=self._client.my_uid,
            target_oid=subject_id,
            target_type=target_type,
            target_title=item_data.get("title", "") or item_data.get("desc", ""),
            target_url=item_data.get("uri", ""),
            comment_tree=[target_node],
            reply_target_rpid=source_id,
        )

    def _build_context_from_video_comment(
        self, cmt: dict, aid: int, video_info: Optional[dict]
    ):
        """从视频评论数据构建 CommentContext。"""
        from .prompts import CommentContext, CommentNode

        member = cmt.get("member", {})
        content = cmt.get("content", {})
        rpid = cmt.get("rpid", 0)

        target_node = CommentNode(
            rpid=rpid,
            uid=member.get("mid", 0),
            uname=member.get("uname", ""),
            content=content.get("message", ""),
            ctime=cmt.get("ctime", 0),
        )

        title = (video_info or {}).get("title", f"AV{aid}")

        return CommentContext(
            bot_name="",
            bot_uid=self._client.my_uid,
            target_oid=aid,
            target_type="视频",
            target_title=title,
            target_url=f"https://www.bilibili.com/video/av{aid}",
            comment_tree=[target_node],
            reply_target_rpid=rpid,
        )

    def _build_private_context(self, msg, session):
        """从私信消息构建 PrivateMessageContext。"""
        from .prompts import PrivateMessageContext

        return PrivateMessageContext(
            bot_name="",
            bot_uid=self._client.my_uid,
            sender_name=getattr(msg, "sender_name", f"UID:{msg.sender_uid}"),
            sender_uid=msg.sender_uid,
            # 获取对话历史
            history=self._fetch_recent_history(session),
            current_message=getattr(msg, "text", "") or "",
        )

    def _fetch_recent_history(self, session) -> list[dict]:
        """拉取最近的对话历史。"""
        try:
            messages = self._client.get_messages(session.talker_id, size=20)
        except Exception:
            return []

        history: list[dict] = []
        for m in reversed(messages):
            is_bot = m.sender_uid == self._client.my_uid
            history.append({
                "role": "bot" if is_bot else "user",
                "content": m.text,
                "sender_name": f"UID:{m.sender_uid}",
                "sender_uid": m.sender_uid,
                "time": m.timestamp,
            })
        return history
