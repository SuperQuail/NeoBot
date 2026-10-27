"""Markdown 技能匹配与群成员档案/续接说明渲染。"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
from neobot_app.reply.event import ReplyEvent
from .settings import _safe_int
if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

class PromptContextMixin:
    def _match_markdown_skills(self, queue: MessageQueue, queue_key: str) -> list[Any]:
        query = self._last_user_text(queue, queue_key)
        if not query:
            return []
        return (
            self._markdown_skills.match(query, limit=3) if self._markdown_skills else []
        )
    def _last_user_text(self, queue: MessageQueue, queue_key: str) -> str:
        from neobot_app.message.queue import QueueEntryType as _QET

        # 只取「最后一条用户消息」的全部文本段作为技能匹配查询文本：
        # - 从队列末尾逆序遍历，避免把 bot 自己发送的消息（语音/图片等会自推入队列）
        #   或更早的旧话题文本算进去，导致旧技能被错误激活
        # - 优先使用 MessageQueue 注入的 bot_account（bootstrap 已按配置传入），
        #   其次回退到 config.bot.account 解析；两者都为 0/None 时不过滤（保持旧行为）
        bot_account = _safe_int(getattr(queue, "bot_account", None))
        if not bot_account and self._config is not None:
            bot_cfg = getattr(self._config, "bot", None)
            if bot_cfg is not None:
                bot_account = _safe_int(getattr(bot_cfg, "account", 0) or 0)
        for entry in reversed(queue.entries(queue_key)):
            if entry.kind != _QET.MESSAGE or entry.message is None:
                continue
            if bot_account:
                user_id = getattr(entry.message, "user_id", None)
                # 防御性解析：user_id 理论经 pydantic 校验为 int 不可达，
                # 但非数字时按 0 处理（与 bot_account 不等，消息保留），避免崩溃
                if user_id is not None and _safe_int(user_id) == bot_account:
                    continue
            parts: list[str] = []
            segments = getattr(entry.message, "message", None) or []
            for segment in segments:
                if getattr(segment, "type", None) != "text":
                    continue
                text = (segment.data or {}).get("text")
                if text:
                    parts.append(str(text))
            return " ".join(parts).strip()
        return ""
    async def _render_new_member_block(
        self, new_entries: list, rendered_user_ids: set[str]
    ) -> str:
        """渲染「新出现的群友档案」块；渲染成功才登记 uid，失败留给下次重试。"""
        if self._prompt_builder is None or not new_entries:
            return ""
        profile_service = getattr(self._prompt_builder, "_profile_service", None)
        if profile_service is None:
            return ""
        from neobot_app.message.queue import QueueEntryType

        new_user_ids: list[str] = []
        for entry in new_entries:
            if entry.kind != QueueEntryType.MESSAGE or entry.message is None:
                continue
            uid = getattr(entry.message, "user_id", None)
            if uid is None:
                continue
            uid_str = str(uid)
            if uid_str not in rendered_user_ids and uid_str not in new_user_ids:
                new_user_ids.append(uid_str)
        if not new_user_ids:
            return ""
        include_archives = self._inject_member_archives()
        try:
            member_profiles = await profile_service.render_specific_members(
                new_user_ids, include_archives=include_archives
            )
        except Exception as exc:
            self._logger.warning(
                f"新出现的群友档案渲染失败（下次重试）：{type(exc).__name__}: {exc}"
            )
            return ""
        if not member_profiles:
            return ""
        render = getattr(self._prompt_builder, "build_new_member_profiles_text", None)
        block = (
            render(member_profiles)
            if callable(render)
            else f"[新出现的群友档案]\n{member_profiles}"
        )
        if not include_archives:
            hint = getattr(self._prompt_builder, "member_archive_hint", None)
            if callable(hint):
                hint_text = hint()
                if hint_text:
                    block = f"{block}\n{hint_text}"
        rendered_user_ids.update(new_user_ids)
        return block
    async def _build_group_chat_resume_messages(
        self,
        new_entries: list,
        queue_key: str,
        rendered_user_ids: set[str],
        numbering: Any,
        queue_copy: MessageQueue,
    ) -> list[dict[str, str]]:
        """为群聊挂起恢复构建增量消息列表。

        新消息按发送者拆分为 user/assistant 角色消息;
        新成员档案与当前时间渲染为一条 user 说明消息,附在新消息之前。
        """
        from neobot_app.prompt.role_messages import build_role_messages_from_entries


        # 新消息 -> 角色消息
        role_messages = build_role_messages_from_entries(
            new_entries,
            queue_copy,
            queue_key,
            numbering=numbering,
            bot_account=self._get_bot_account(),
            include_boundary_markers=self._show_boundary_markers(),
        )

        # 新成员档案(user 块内容,不插入 system 提示词)；渲染成功才登记 uid。
        new_member_text = await self._render_new_member_block(
            new_entries, rendered_user_ids
        )

        resume_messages: list[dict[str, str]] = []

        # 说明消息(新成员档案 + 续接说明),位于新消息之前。
        # 当前时间由回复前的独立 <当前时间> user 块提供,这里不再重复。
        if new_member_text or role_messages:
            context_text = self._render_resume_context(new_member_text)
            if context_text:
                resume_messages.append({"role": "user", "content": context_text})

        resume_messages.extend(role_messages)
        return resume_messages
    def _is_at_mentioned_event(self, event: ReplyEvent) -> bool:
        service = self._willing_service
        message = getattr(event, "message", None)
        if service is None or message is None:
            return False
        try:
            return bool(service.is_at_mentioned(message))
        except Exception:
            return False
