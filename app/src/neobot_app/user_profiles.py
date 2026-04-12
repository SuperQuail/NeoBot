"""User profile refresh and prompt-text assembly helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from neobot_contracts.ports.logging import Logger, NullLogger


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
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UserProfileService:
    """Keep user profiles fresh and render them into prompt-ready text."""

    def __init__(
        self,
        adapter: Any,
        uow_factory: Any,
        config: Any,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._uow_factory = uow_factory
        self._config = config
        self._logger = logger or NullLogger()

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

    async def get_group_name(self, group_id: str | int) -> str:
        group = await self.get_group(group_id)
        if group is not None and getattr(group, "group_name", None):
            return str(group.group_name)
        return f"群聊{group_id}"

    async def render_group_member_list(
        self,
        group_id: str | int,
        message_queue: Any | None = None,
    ) -> str:
        members = self._collect_group_members_from_queue(group_id, message_queue)
        if members is None:
            response = await self._adapter.get_group_member_list(int(group_id))
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
            rendered = self._format_group_member_line(index, member, profile)
            if rendered:
                lines.append(rendered)
        return "\n".join(lines)

    async def render_friend_info(
        self,
        user_id: str | int,
        *,
        profile: Any | None = None,
    ) -> str:
        if profile is None:
            profile = await self.ensure_user_profile(user_id)
        return self._format_friend_info_line(str(user_id), profile)

    @staticmethod
    def _collect_group_members_from_queue(
        group_id: str | int,
        message_queue: Any | None,
    ) -> list[Any] | None:
        if message_queue is None:
            return None

        queue_key = str(group_id)
        try:
            messages = list(message_queue[queue_key])
        except Exception:
            return None

        members_by_user: dict[str, dict[str, Any]] = {}
        ordered_user_ids: list[str] = []
        for message in messages:
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

        return [
            SimpleNamespace(**members_by_user[user_id])
            for user_id in ordered_user_ids
        ]

    def _needs_refresh(self, profile: Any) -> bool:
        if not getattr(self._config.chat, "enable_periodic_user_info_update", False):
            return False

        fetched_at = _normalize_datetime(getattr(profile, "fetched_at", None))
        if fetched_at is None:
            return True

        interval_days = max(1, int(getattr(self._config.chat, "user_info_update_interval_days", 7)))
        return datetime.now(timezone.utc) - fetched_at >= timedelta(days=interval_days)

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
            response = await self._adapter.get_stranger_info(int(user_id))
        except Exception as exc:
            self._logger.warning("刷新用户信息失败", user_id=user_id, error=str(exc))
            return await self.get_user(user_id)

        data = getattr(response, "data", None)
        fields = self._build_user_fields(
            data,
            observed_fields=observed_fields,
            current_profile=current_profile,
        )
        fields["fetched_at"] = datetime.now(timezone.utc)

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
            for key in ("relation_ship", "profile", "known_gender", "birthday"):
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
    def _format_group_member_line(index: int, member: Any, profile: Any | None) -> str:
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

        return f"<群友_{index}>{','.join(segments)}</群友_{index}>"

    @staticmethod
    def _format_friend_info_line(user_id: str, profile: Any | None) -> str:
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

        return f"<聊天对象>{','.join(segments)}</聊天对象>"
