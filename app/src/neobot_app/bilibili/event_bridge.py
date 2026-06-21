"""BilibiliEventBridge — 连接 B站 monitors 到 NeoBot ReplyOrchestrator。

将 monitor 检测到的新评论/私信转换为 ReplyOrchestrator 可处理的 reply 事件。
"""

from __future__ import annotations

import asyncio
from loguru import logger
from typing import Any, Optional



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

            # 异步补充内容详情（UP主、简介等）
            await self._enrich_comment_context(ctx)

            # 提交给 orchestrator
            if self._orchestrator is not None:
                self._orchestrator.start_bilibili_comment_reply(ctx, self._client)

        except Exception:
            logger.exception("处理评论事件失败")

    async def _enrich_comment_context(self, ctx: Any) -> None:
        """异步补充内容详情：UP主、扩展简介等。"""
        try:
            if ctx.business_id == 1:  # 视频
                from bilibili_api.video import Video

                v = Video(aid=ctx.target_oid)
                info = await v.get_info()
                if info:
                    owner = info.get("owner", {}) or {}
                    ctx.target_up_name = owner.get("name", "") or ctx.target_up_name
                    ctx.target_title = info.get("title", "") or ctx.target_title
                    ctx.target_desc = info.get("desc", "") or ctx.target_desc
                    logger.debug("视频详情获取成功: oid={} title={} up={}",
                                 ctx.target_oid, ctx.target_title, ctx.target_up_name)
            elif ctx.business_id in (11, 17):  # 动态
                await self._enrich_dynamic_context(ctx)
        except Exception:
            pass  # 内容获取失败不影响回复

    async def _enrich_dynamic_context(self, ctx: Any) -> None:
        """补充动态详情。"""
        from bilibili_api import sync as _sync

        # 策略1: 从 uri 提取 dynamic_id
        dynamic_id = 0
        uri = ctx.target_url or ""
        if "t.bilibili.com/" in uri:
            import re as _re
            m = _re.search(r"t\.bilibili\.com/(\d+)", uri)
            if m:
                dynamic_id = int(m.group(1))
                logger.debug("从 uri 提取 dynamic_id={}", dynamic_id)

        # 策略2: 用 subject_id
        if not dynamic_id and ctx.target_oid:
            dynamic_id = ctx.target_oid
            logger.debug("用 subject_id 作为 dynamic_id={}", dynamic_id)

        if not dynamic_id:
            return

        try:
            from bilibili_api.dynamic import Dynamic

            dyn = Dynamic(dynamic_id=dynamic_id)
            info = await dyn.get_info()
            if info:
                item = info.get("item", {}) or info
                ctx.target_title = item.get("title", "") or ctx.target_title
                desc = item.get("description", "") or item.get("desc", "")
                ctx.target_desc = desc or ctx.target_desc

                # 动态的 UP 主
                user = info.get("user", {}) or info.get("author", {}) or info.get("owner", {})
                ctx.target_up_name = (
                    user.get("name", "") or info.get("uname", "") or ctx.target_up_name
                )
                logger.debug("动态详情获取成功: dynamic_id={} title={:.40} up={}",
                             dynamic_id, ctx.target_title, ctx.target_up_name)
            else:
                logger.debug("动态 {} 获取详情为空", dynamic_id)
        except Exception as e:
            logger.debug("动态 {} 详情获取失败: {}", dynamic_id, e)
            pass

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
            business_id=business_id,
            target_title=item_data.get("title", "") or item_data.get("desc", ""),
            target_desc=item_data.get("desc", "") or item_data.get("message", ""),
            target_url=item_data.get("uri", ""),
            comment_tree=[target_node],
            reply_target_rpid=source_id,
            reply_root_rpid=real_root,
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
            reply_root_rpid=rpid,  # 视频评论为顶层，root=parent=rpid
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
