"""User profile refresh and prompt-text assembly helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.favorability import favorability_to_text
from neobot_app.time_context import now_utc, to_utc


def _sex_to_text(value: object) -> str | None:
    raw = getattr(value, "value", value)
    if raw == "male":
        return "男"
    if raw == "female":
        return "女"
    return None


def _normalize_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return to_utc(value)


class UserProfileService:
    """Keep user profiles fresh and render them into prompt-ready text."""

    def __init__(
        self,
        adapter: Any,
        uow_factory: Any,
        config: Any,
        logger: Logger | None = None,
        archive_memory_service: Any | None = None,
    ) -> None:
        self._adapter = adapter
        self._uow_factory = uow_factory
        self._config = config
        self._logger = logger or NullLogger()
        self._archive_memory_service = archive_memory_service

    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0

    async def _adapter_call(self, awaitable: Any, *, action: str, **log_fields: Any) -> Any:
        try:
            return await asyncio.wait_for(
                awaitable,
                timeout=self._get_dependency_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "user profile adapter call timed out",
                action=action,
                timeout_seconds=self._get_dependency_timeout_seconds(),
                **log_fields,
            )
            raise

    async def ensure_user_profile(
        self,
        user_id: str | int,
        *,
        observed_fields: Optional[dict[str, Any]] = None,
    ) -> Any | None:
        user_id_str = str(user_id)
        record = await self.get_user(user_id_str)
        if record is not None and observed_fields:
            record = await self._merge_observed_fields(user_id_str, record, observed_fields)

        if record is None or self._needs_refresh(record):
            record = await self._refresh_user_profile(
                user_id_str,
                observed_fields=observed_fields,
                current_profile=record,
            )
        return record

    async def get_user(self, user_id: str | int) -> Any | None:
        async with self._uow_factory() as uow:
            return await uow.profiles.get_user(str(user_id))

    async def get_group(self, group_id: str | int) -> Any | None:
        async with self._uow_factory() as uow:
            return await uow.profiles.get_group(str(group_id))

    async def update_user_remark(self, user_id: str | int, remark: str | None) -> Any | None:
        user_id_str = str(user_id)
        remark_text = str(remark or "").strip()
        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(user_id_str, remark=remark_text)
            await uow.commit()
            return await uow.profiles.get_user(user_id_str)

    async def update_user_avatar_analysis(
        self,
        user_id: str | int,
        avatar_analysis: str | None,
    ) -> Any | None:
        user_id_str = str(user_id)
        avatar_text = str(avatar_analysis or "").strip()
        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(user_id_str, avatar_analysis=avatar_text)
            await uow.commit()
            return await uow.profiles.get_user(user_id_str)

    async def update_user_favorability(
        self,
        user_id: str | int,
        favorability: int,
    ) -> Any | None:
        user_id_str = str(user_id)
        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(user_id_str, favorability=favorability)
            await uow.commit()
            return await uow.profiles.get_user(user_id_str)

    async def get_group_name(self, group_id: str | int) -> str:
        group = await self.get_group(group_id)
        if group is not None and getattr(group, "group_name", None):
            return str(group.group_name)
        return f"群聊{group_id}"

    async def render_group_owner_text(
        self,
        group_id: str | int,
        message_queue: Any | None = None,
    ) -> str:
        """获取群主信息文本：'群主：name（QQ：123456）'，从队列或 API 动态查找。"""
        group_id_int = _safe_int(group_id)
        members = None

        # 先从消息队列中查找（轻量，无 API 调用）
        members = self._collect_group_members_from_queue(group_id, message_queue)

        # 队列中找不到则调用 API
        if not members and group_id_int is not None:
            try:
                response = await self._adapter_call(
                    self._adapter.get_group_member_list(group_id_int),
                    action="get_group_member_list",
                    group_id=str(group_id),
                )
                members = response.data if response and response.data else []
            except Exception:
                pass

        if members:
            for member in members:
                role = _normalize_role(getattr(member, "role", None))
                if role == "owner":
                    user_id = getattr(member, "user_id", None)
                    if user_id is None:
                        continue
                    card = getattr(member, "card", None)
                    nickname = getattr(member, "nickname", None)
                    name = card or nickname or f"QQ:{user_id}"
                    return f"群主：{name}（QQ：{user_id}）"

        return ""

    async def render_group_member_list(
        self,
        group_id: str | int,
        message_queue: Any | None = None,
        *,
        archive_fetch_window: int | None = None,
    ) -> str:
        members = self._collect_group_members_from_queue(
            group_id, message_queue, window=archive_fetch_window,
        )
        if members is None:
            response = await self._adapter_call(
                self._adapter.get_group_member_list(int(group_id)),
                action="get_group_member_list",
                group_id=str(group_id),
            )
            members = response.data if response and response.data else []

        lines: list[str] = []
        for index, member in enumerate(members, start=1):
            user_id = getattr(member, "user_id", None)
            if user_id is None:
                continue
            profile = await self.ensure_user_profile(
                user_id,
                observed_fields=self._observed_fields_from_group_member(member),
            )
            archive_text = await self._fetch_user_archive(str(user_id))
            rendered = self._format_group_member_line(index, member, profile, archive_text=archive_text)
            if rendered:
                lines.append(rendered)
        return "\n".join(lines)

    async def render_bot_group_admin_status(
        self,
        group_id: str | int,
        bot_account: str | int,
        message_queue: Any | None = None,
    ) -> str:
        is_admin = await self.is_bot_group_admin(
            group_id,
            bot_account,
            message_queue=message_queue,
        )
        return "你是该群管理员" if is_admin else "你不是该群管理员"

    async def is_bot_group_admin(
        self,
        group_id: str | int,
        bot_account: str | int,
        *,
        message_queue: Any | None = None,
    ) -> bool:
        role = await self._get_bot_group_role(group_id, bot_account, message_queue=message_queue)
        return role in {"owner", "admin"}

    async def render_friend_info(
        self,
        user_id: str | int,
        *,
        profile: Any | None = None,
    ) -> str:
        if profile is None:
            profile = await self.ensure_user_profile(user_id)
        archive_text = await self._fetch_user_archive(str(user_id))
        return self._format_friend_info_line(str(user_id), profile, archive_text=archive_text)

    async def _fetch_user_archive(self, user_id: str) -> str | None:
        if self._archive_memory_service is None:
            return None
        try:
            item = await self._archive_memory_service.get("user_profile", user_id)
        except Exception:
            return None
        if item is not None and item.value:
            return item.value.strip()
        return None

    @staticmethod
    def _collect_group_members_from_queue(
        group_id: str | int,
        message_queue: Any | None,
        *,
        window: int | None = None,
    ) -> list[Any] | None:
        if message_queue is None:
            return None

        queue_key = str(group_id)

        # When a window is configured, only scan the newest N messages
        # (by weighted count: pokes = 0.2, etc.) instead of the full queue.
        if window is not None:
            recent_messages = getattr(message_queue, "get_recent_messages", None)
            recent_sender_ids_method = getattr(message_queue, "get_recent_sender_ids", None)
            if recent_messages is not None and recent_sender_ids_method is not None:
                messages = recent_messages(queue_key, float(window))
                sender_ids = recent_sender_ids_method(queue_key, float(window))

                members_by_user: dict[str, dict[str, Any]] = {}
                ordered_user_ids: list[str] = []

                # Build member entries from recent messages (richest sender info)
                for message in messages:
                    user_id = getattr(message, "user_id", None)
                    if user_id is None:
                        continue
                    user_id_str = str(user_id)
                    existing = members_by_user.get(user_id_str)
                    sender = getattr(message, "sender", None)

                    if existing is None:
                        members_by_user[user_id_str] = {
                            "user_id": user_id,
                            "nickname": getattr(sender, "nickname", None) if sender else None,
                            "card": getattr(sender, "card", None) if sender else None,
                            "sex": getattr(sender, "sex", None) if sender else None,
                            "role": getattr(sender, "role", None) if sender else None,
                        }
                        ordered_user_ids.append(user_id_str)
                    else:
                        # Enrich existing entry with any missing sender fields
                        if sender is not None:
                            for field in ("nickname", "card", "sex", "role"):
                                val = getattr(sender, field, None)
                                if val is not None and existing.get(field) is None:
                                    existing[field] = val

                # Add poke/reaction senders not already covered
                for user_id in sender_ids:
                    user_id_str = str(user_id)
                    if user_id_str not in members_by_user:
                        members_by_user[user_id_str] = {
                            "user_id": user_id,
                            "nickname": None,
                            "card": None,
                            "sex": None,
                            "role": None,
                        }
                        ordered_user_ids.append(user_id_str)

                return [
                    SimpleNamespace(**members_by_user[uid])
                    for uid in ordered_user_ids
                ]

        # Fallback: scan the full queue (current behaviour)
        try:
            entries = list(message_queue[queue_key])
        except Exception:
            return None

        members_by_user: dict[str, dict[str, Any]] = {}
        ordered_user_ids: list[str] = []
        for message in entries:
            user_id = getattr(message, "user_id", None)
            if user_id is None:
                continue

            user_id_str = str(user_id)
            if user_id_str not in members_by_user:
                members_by_user[user_id_str] = {
                    "user_id": user_id,
                    "nickname": None,
                    "card": None,
                    "sex": None,
                    "role": None,
                }
                ordered_user_ids.append(user_id_str)

            sender = getattr(message, "sender", None)
            if sender is None:
                continue

            nickname = getattr(sender, "nickname", None)
            if nickname:
                members_by_user[user_id_str]["nickname"] = nickname

            card = getattr(sender, "card", None)
            if card:
                members_by_user[user_id_str]["card"] = card

            sex = getattr(sender, "sex", None)
            if sex is not None:
                members_by_user[user_id_str]["sex"] = sex

            role = getattr(sender, "role", None)
            if role is not None:
                members_by_user[user_id_str]["role"] = role

        return [
            SimpleNamespace(**members_by_user[user_id])
            for user_id in ordered_user_ids
        ]

    async def _get_bot_group_role(
        self,
        group_id: str | int,
        bot_account: str | int,
        *,
        message_queue: Any | None = None,
    ) -> str | None:
        bot_account_int = _safe_int(bot_account)
        if bot_account_int is None:
            return None

        group_id_int = _safe_int(group_id)
        if group_id_int is not None:
            getter = getattr(self._adapter, "get_group_member_info", None)
            if getter is not None:
                try:
                    response = await self._adapter_call(
                        getter(group_id_int, bot_account_int),
                        action="get_group_member_info",
                        group_id=str(group_id),
                        bot_account=str(bot_account),
                    )
                    role = _normalize_role(getattr(getattr(response, "data", None), "role", None))
                    if role:
                        return role
                except Exception as exc:
                    self._logger.warning(
                        "查询 Bot 群成员信息失败",
                        group_id=str(group_id),
                        bot_account=str(bot_account),
                        error=str(exc),
                    )

            try:
                response = await self._adapter_call(
                    self._adapter.get_group_member_list(group_id_int),
                    action="get_group_member_list",
                    group_id=str(group_id),
                )
                role = _find_member_role(getattr(response, "data", None), bot_account_int)
                if role:
                    return role
            except Exception as exc:
                self._logger.warning(
                    "查询群成员列表失败",
                    group_id=str(group_id),
                    bot_account=str(bot_account),
                    error=str(exc),
                )

        members = self._collect_group_members_from_queue(group_id, message_queue)
        return _find_member_role(members, bot_account_int)

    def _needs_refresh(self, profile: Any) -> bool:
        if not getattr(self._config.chat, "enable_periodic_user_info_update", False):
            return False

        fetched_at = _normalize_datetime(getattr(profile, "fetched_at", None))
        if fetched_at is None:
            return True

        interval_days = max(1, int(getattr(self._config.chat, "user_info_update_interval_days", 7)))
        return now_utc() - fetched_at >= timedelta(days=interval_days)

    async def _merge_observed_fields(
        self,
        user_id: str,
        profile: Any,
        observed_fields: dict[str, Any],
    ) -> Any:
        changed_fields: dict[str, Any] = {}
        for field_name, value in observed_fields.items():
            if value in (None, ""):
                continue
            current = getattr(profile, field_name, None)
            if current in (None, "") and value != current:
                changed_fields[field_name] = value

        if not changed_fields:
            return profile

        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(
                user_id,
                **changed_fields,
                fetched_at=getattr(profile, "fetched_at", None),
            )
            await uow.commit()
            return await uow.profiles.get_user(user_id)

    async def _refresh_user_profile(
        self,
        user_id: str,
        *,
        observed_fields: Optional[dict[str, Any]] = None,
        current_profile: Any | None = None,
    ) -> Any | None:
        try:
            response = await self._adapter_call(
                self._adapter.get_stranger_info(int(user_id)),
                action="get_stranger_info",
                user_id=user_id,
            )
        except Exception as exc:
            self._logger.warning("刷新用户信息失败", user_id=user_id, error=str(exc))
            return await self.get_user(user_id)

        data = getattr(response, "data", None)
        fields = self._build_user_fields(
            data,
            observed_fields=observed_fields,
            current_profile=current_profile,
        )
        fields["fetched_at"] = now_utc()

        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(user_id, **fields)
            await uow.commit()
            return await uow.profiles.get_user(user_id)

    @staticmethod
    def _build_user_fields(
        data: Any,
        *,
        observed_fields: Optional[dict[str, Any]] = None,
        current_profile: Any | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        current_values = current_profile.__dict__ if current_profile is not None else {}
        if observed_fields:
            fields.update({k: v for k, v in observed_fields.items() if v not in (None, "")})

        if data is None:
            for key in ("relation_ship", "profile", "known_gender", "birthday", "avatar_analysis"):
                if key not in fields and current_values.get(key) not in (None, ""):
                    fields[key] = current_values[key]
            return fields

        fields.update(
            {
                "nick_name": getattr(data, "nickname", None) or fields.get("nick_name") or current_values.get("nick_name") or "",
                "sex": getattr(getattr(data, "sex", None), "value", getattr(data, "sex", None)) or fields.get("sex") or current_values.get("sex") or "",
                "age": getattr(data, "age", None) or current_values.get("age"),
                "city": getattr(data, "city", None) or current_values.get("city") or "",
                "country": getattr(data, "country", None) or current_values.get("country") or "",
                "long_nick": getattr(data, "long_nick", None) or current_values.get("long_nick") or "",
                "remark": getattr(data, "remark", None) or fields.get("remark") or current_values.get("remark") or "",
                "relation_ship": fields.get("relation_ship") or current_values.get("relation_ship") or "",
                "profile": fields.get("profile") or current_values.get("profile") or "",
                "known_gender": fields.get("known_gender") or current_values.get("known_gender") or "",
                "avatar_analysis": fields.get("avatar_analysis") or current_values.get("avatar_analysis") or "",
                "labs": ",".join(getattr(data, "labs", None) or []) or current_values.get("labs") or "",
            }
        )

        birthday_year = getattr(data, "birthday_year", None)
        birthday_month = getattr(data, "birthday_month", None)
        birthday_day = getattr(data, "birthday_day", None)
        if birthday_year and birthday_month and birthday_day:
            fields["birthday"] = f"{birthday_year}-{birthday_month}-{birthday_day}"
        elif "birthday" not in fields:
            fields["birthday"] = current_values.get("birthday") or ""

        return fields

    @staticmethod
    def _observed_fields_from_group_member(member: Any) -> dict[str, Any]:
        return {
            "nick_name": getattr(member, "nickname", None),
            "sex": getattr(getattr(member, "sex", None), "value", getattr(member, "sex", None)),
        }

    @staticmethod
    def _build_qq_profile_segment(profile: Any | None) -> str | None:
        """Build a compact QQ profile info segment with a disclaimer.

        These fields are set by the QQ user themselves and may not be accurate.
        """
        if profile is None:
            return None

        parts: list[str] = []

        age = getattr(profile, "age", None)
        if age is not None and str(age).strip():
            parts.append(f"年龄:{age}")

        birthday = getattr(profile, "birthday", None)
        if birthday and str(birthday).strip():
            parts.append(f"生日:{birthday}")

        country = getattr(profile, "country", None)
        city = getattr(profile, "city", None)
        location_parts: list[str] = []
        if country and str(country).strip():
            location_parts.append(str(country).strip())
        if city and str(city).strip():
            location_parts.append(str(city).strip())
        if location_parts:
            parts.append(f"所在地:{' '.join(location_parts)}")

        long_nick = getattr(profile, "long_nick", None)
        if long_nick and str(long_nick).strip():
            parts.append(f"个性签名:{long_nick}")

        labs = getattr(profile, "labs", None)
        if labs and str(labs).strip():
            parts.append(f"标签:{labs}")

        relation_ship = getattr(profile, "relation_ship", None)
        if relation_ship and str(relation_ship).strip():
            parts.append(f"情感状态:{relation_ship}")

        if not parts:
            return None

        return f"QQ个人资料({','.join(parts)})(注意:以上信息由QQ用户自行填写,未必真实)"

    @staticmethod
    def _format_group_member_line(
        index: int,
        member: Any,
        profile: Any | None,
        *,
        archive_text: str | None = None,
    ) -> str:
        user_id = getattr(member, "user_id", None)
        if user_id is None:
            return ""

        nickname = getattr(member, "nickname", None) or getattr(profile, "nick_name", None) or f"QQ:{user_id}"
        remark = getattr(profile, "remark", None)
        nickname_part = f"昵称:{nickname}"
        if remark:
            nickname_part += f"(你对Ta的备注:{remark})"

        segments = [nickname_part]
        card = getattr(member, "card", None)
        if card:
            segments.append(f"群昵称:{card}")
        segments.append(f"QQ号:{user_id}")

        qq_gender = _sex_to_text(getattr(member, "sex", None)) or _sex_to_text(getattr(profile, "sex", None))
        if qq_gender:
            segments.append(f"QQ登记的性别:{qq_gender}")

        known_gender = _sex_to_text(getattr(profile, "known_gender", None)) or (
            getattr(profile, "known_gender", None) if getattr(profile, "known_gender", None) else None
        )
        if known_gender:
            segments.append(f"Ta告诉你的性别:{known_gender}")

        profile_text = getattr(profile, "profile", None)
        if profile_text:
            segments.append(f"你对Ta的印象:{profile_text}")

        avatar_analysis = getattr(profile, "avatar_analysis", None)
        if avatar_analysis:
            segments.append(f"头像记忆:{avatar_analysis}")

        qq_profile = UserProfileService._build_qq_profile_segment(profile)
        if qq_profile:
            segments.append(qq_profile)

        favorability = getattr(profile, "favorability", 0) or 0
        favorability_label = favorability_to_text(favorability)
        segments.append(f"好感度:{favorability_label}({favorability})")

        if archive_text:
            segments.append(f"你记得关于Ta的信息:{archive_text}")

        return f"<群友_{index}>{','.join(segments)}</群友_{index}>"

    @staticmethod
    def _format_friend_info_line(
        user_id: str,
        profile: Any | None,
        *,
        archive_text: str | None = None,
    ) -> str:
        nickname = getattr(profile, "nick_name", None) or f"QQ:{user_id}"
        remark = getattr(profile, "remark", None)
        nickname_part = f"昵称:{nickname}"
        if remark:
            nickname_part += f"(你对Ta的备注:{remark})"

        segments = [nickname_part, f"QQ号:{user_id}"]

        qq_gender = _sex_to_text(getattr(profile, "sex", None))
        if qq_gender:
            segments.append(f"QQ登记的性别:{qq_gender}")

        known_gender = _sex_to_text(getattr(profile, "known_gender", None)) or (
            getattr(profile, "known_gender", None) if getattr(profile, "known_gender", None) else None
        )
        if known_gender:
            segments.append(f"Ta告诉你的性别:{known_gender}")

        profile_text = getattr(profile, "profile", None)
        if profile_text:
            segments.append(f"你对Ta的印象:{profile_text}")

        avatar_analysis = getattr(profile, "avatar_analysis", None)
        if avatar_analysis:
            segments.append(f"头像记忆:{avatar_analysis}")

        qq_profile = UserProfileService._build_qq_profile_segment(profile)
        if qq_profile:
            segments.append(qq_profile)

        favorability = getattr(profile, "favorability", 0) or 0
        favorability_label = favorability_to_text(favorability)
        segments.append(f"好感度:{favorability_label}({favorability})")

        if archive_text:
            segments.append(f"你记得关于Ta的信息:{archive_text}")

        return f"<聊天对象>{','.join(segments)}</聊天对象>"


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_role(value: object) -> str | None:
    role = getattr(value, "value", value)
    if role is None:
        return None
    role_text = str(role).strip().lower()
    return role_text or None


def _find_member_role(members: Any, bot_account: int) -> str | None:
    if not members:
        return None
    for member in members:
        user_id = _safe_int(getattr(member, "user_id", None))
        if user_id != bot_account:
            continue
        return _normalize_role(getattr(member, "role", None))
    return None
