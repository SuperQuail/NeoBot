"""通知事件：撤回、表情回应、戳一戳与用户显示名解析。"""

from __future__ import annotations

import asyncio
from typing import Any
from typing import Dict
from neobot_adapter.model.notice import EmojiReaction
from neobot_adapter.model.notice import GroupMessageDelete
from neobot_adapter.model.notice import GroupPoke
from neobot_adapter.model.notice import PrivateMessageDelete
from neobot_adapter.model.notice import PrivatePoke
from neobot_adapter.utils.parse import safe_parse_model

from .helpers import _build_poke_action_text


class _PipelineNoticeMixin:
    async def _handle_notice(self, event: Dict[str, Any]) -> None:
        notice_type = event.get("notice_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{notice_type}" + (f".{sub_type}" if sub_type else "")
        if notice_type in {"private_message_delete", "friend_recall"}:
            notice = safe_parse_model(event, PrivateMessageDelete)
            queue_key = str(notice.user_id or "")
            if queue_key:
                self._friend_queue.push_notice(queue_key, notice)
        elif notice_type in {"group_message_delete", "group_recall"}:
            notice = safe_parse_model(event, GroupMessageDelete)
            queue_key = str(notice.group_id or "")
            if queue_key:
                self._group_queue.push_notice(queue_key, notice)
        elif notice_type == "message_reaction":
            await self._handle_reaction_notice(event)
        elif notice_type == "notify" and sub_type == "poke":
            await self._handle_poke_notice(event)

        # 构建详情
        details: list[str] = []
        for key in (
            "user_id",
            "operator_id",
            "sender_id",
            "target_id",
            "group_id",
            "message_id",
            "file",
            "duration",
            "honor_type",
            "title",
            "card_new",
            "card_old",
            "emoji_id",
        ):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到通知[{label}] {info}".rstrip())

    async def _handle_reaction_notice(self, event: Dict[str, Any]) -> None:
        from neobot_app.message.queue import ReactionEntry

        notice = safe_parse_model(event, EmojiReaction)
        if notice.message_id is None or notice.emoji_id is None:
            return

        group_id = notice.group_id or event.get("group_id")
        user_id = notice.user_id or event.get("user_id")
        if group_id is not None:
            queue_key = str(group_id)
            queue = self._group_queue
        elif user_id is not None:
            queue_key = str(user_id)
            queue = self._friend_queue
        else:
            return

        operator_name = f"QQ:{user_id}" if user_id is not None else "未知用户"
        if user_id is not None and self._profile_service is not None:
            try:
                profile = await asyncio.wait_for(
                    self._profile_service.get_user(str(user_id)),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if profile is not None and getattr(profile, "nick_name", None):
                    operator_name = profile.nick_name
            except asyncio.TimeoutError:
                self._logger.warning(
                    "表情回应用户资料查询超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        queue.push_reaction(
            queue_key,
            ReactionEntry(
                target_message_id=notice.message_id,
                emoji_id=notice.emoji_id,
                operator_user_id=user_id or 0,
                operator_name=operator_name,
            ),
        )

    async def _handle_poke_notice(self, event: Dict[str, Any]) -> None:
        from neobot_app.message.queue import PokeEntry

        group_id = event.get("group_id")
        if group_id is not None:
            notice = safe_parse_model(event, GroupPoke)
            queue_key = str(notice.group_id or group_id)
            queue = self._group_queue
            sender_id = notice.user_id or 0
            target_id = notice.target_id or 0
            resolved_group_id = notice.group_id or int(group_id)

            sender_name = await self._resolve_name(
                sender_id, group_id=resolved_group_id
            )
            target_name = await self._resolve_name(
                target_id, group_id=resolved_group_id
            )
            action_text = _build_poke_action_text(
                event.get("raw_info"), sender_name, target_name
            )

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=sender_id,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke")
                if notice.sub_type
                else "poke",
                group_id=resolved_group_id,
                sender_name=sender_name,
                target_name=target_name,
                action_text=action_text,
            )
        else:
            notice = safe_parse_model(event, PrivatePoke)
            queue_key = str(notice.user_id or "")
            queue = self._friend_queue
            sender_id = notice.sender_id or notice.user_id or 0
            target_id = notice.target_id or 0

            sender_name = await self._resolve_name(sender_id, group_id=None)
            target_name = await self._resolve_name(target_id, group_id=None)
            action_text = _build_poke_action_text(
                event.get("raw_info"), sender_name, target_name
            )

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=notice.user_id or 0,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke")
                if notice.sub_type
                else "poke",
                group_id=None,
                sender_name=sender_name,
                target_name=target_name,
                action_text=action_text,
            )

        if queue_key:
            queue.push_poke(queue_key, poke)

    async def _resolve_name(self, user_id: int, group_id: int | None = None) -> str:
        """解析用户的显示名称。

        优先级：
        1. 数据库（user_profiles.nick_name / remark）
        2. API：群聊取群成员信息（card > nickname），私聊取陌生人信息
        3. 兜底返回 QQ:xxx
        """
        if not user_id:
            return ""

        # 1. Try database first
        if self._profile_service is not None:
            try:
                profile = await asyncio.wait_for(
                    self._profile_service.get_user(str(user_id)),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if profile is not None:
                    remark = getattr(profile, "remark", None)
                    nick_name = getattr(profile, "nick_name", None)
                    if remark:
                        return str(remark)
                    if nick_name:
                        return str(nick_name)
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析名称时用户资料查询超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        # 2. API fallback
        if group_id is not None:
            try:
                resp = await asyncio.wait_for(
                    self.adapter.get_group_member_info(group_id, user_id),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if resp and resp.data:
                    return (
                        resp.data.card
                        or resp.data.nickname
                        or resp.data.card_or_nickname
                        or f"QQ:{user_id}"
                    )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析群成员名称超时",
                    group_id=group_id,
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass
        else:
            try:
                resp = await asyncio.wait_for(
                    self.adapter.get_stranger_info(user_id),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if resp and resp.data:
                    return resp.data.nickname or f"QQ:{user_id}"
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析陌生人名称超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        return f"QQ:{user_id}"
