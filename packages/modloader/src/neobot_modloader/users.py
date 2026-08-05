from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from neobot_adapter.model.response import GroupMemberData, StrangerInfoData


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: str
    nickname: str | None = None
    avatar_url: str | None = None
    # 仅群成员资料存在
    group_id: str | None = None
    card: str | None = None
    role: str | None = None  # owner / admin / member
    title: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)  # 只读逃生口，业务代码不应依赖

    @property
    def display_name(self) -> str:
        return self.card or self.nickname or self.user_id


class UserDirectory:
    SUCCESS_TTL = 300.0
    FAILURE_TTL = 30.0

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        # value: (profile, fetched_at, failed)；failed=True 表示所有 API 均未返回
        # 数据（占位负缓存），仅此情况使用 FAILURE_TTL
        self._cache: dict[
            tuple[str, str | None], tuple[UserProfile, float, bool]
        ] = {}

    def _now(self) -> float:
        return time.time()

    def _require_adapter(self) -> Any:
        if self._adapter is None:
            raise RuntimeError("UserDirectory not configured")
        return self._adapter

    def _profile_from_group_member(self, data: GroupMemberData, *, fallback_uid: str) -> UserProfile:
        raw = data.model_dump() if hasattr(data, "model_dump") else {}
        return UserProfile(
            user_id=str(data.user_id) if data.user_id is not None else fallback_uid,
            nickname=data.nickname,
            card=data.card,
            role=data.role,
            title=data.title,
            group_id=str(data.group_id) if data.group_id is not None else None,
            raw=raw,
        )

    def _profile_from_stranger(self, data: StrangerInfoData, *, fallback_uid: str) -> UserProfile:
        raw = data.model_dump() if hasattr(data, "model_dump") else {}
        return UserProfile(
            user_id=str(data.user_id) if data.user_id is not None else fallback_uid,
            nickname=data.nickname,
            raw=raw,
        )

    def _cache_get(self, key: tuple[str, str | None], now: float) -> UserProfile | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        try:
            profile, fetched_at, failed = cached
        except (TypeError, ValueError):
            self._cache.pop(key, None)
            return None
        if not isinstance(profile, UserProfile) or not isinstance(fetched_at, (int, float)):
            self._cache.pop(key, None)
            return None
        ttl = self.FAILURE_TTL if failed else self.SUCCESS_TTL
        if now - fetched_at < ttl:
            return profile
        return None

    async def get(
        self, user_id: str, *, group_id: str | None = None, refresh: bool = False
    ) -> UserProfile:
        uid = str(user_id)
        key = (uid, str(group_id) if group_id is not None else None)
        if not refresh:
            cached = self._cache_get(key, self._now())
            if cached is not None:
                return cached
        adapter = self._require_adapter()
        if group_id is not None:
            try:
                response = await adapter.get_group_member_info(int(group_id), int(uid))
            except Exception:
                response = None
            if response is not None and getattr(response, "data", None) is not None:
                profile = self._profile_from_group_member(response.data, fallback_uid=uid)
                self._cache[key] = (profile, self._now(), False)
                return profile
        if not refresh:
            cached_stranger = self._cache_get((uid, None), self._now())
            if cached_stranger is not None:
                return cached_stranger
        try:
            response = await adapter.get_stranger_info(int(uid))
        except Exception:
            response = None
        if response is not None and getattr(response, "data", None) is not None:
            profile = self._profile_from_stranger(response.data, fallback_uid=uid)
            self._cache[(uid, None)] = (profile, self._now(), False)
            return profile
        profile = UserProfile(user_id=uid)
        now = self._now()
        self._cache[key] = (profile, now, True)
        if group_id is not None and self._cache_get((uid, None), now) is None:
            self._cache[(uid, None)] = (profile, now, True)
        return profile

    def from_event(self, event: dict[str, Any] | BaseModel) -> UserProfile:
        data = event.model_dump() if isinstance(event, BaseModel) else dict(event)
        sender = data.get("sender") or {}
        if isinstance(sender, BaseModel):
            sender = sender.model_dump()
        group_id = data.get("group_id")
        return UserProfile(
            user_id=str(sender.get("user_id") or ""),
            nickname=sender.get("nickname"),
            card=sender.get("card"),
            role=sender.get("role"),
            title=sender.get("title"),
            group_id=str(group_id) if group_id is not None else None,
            avatar_url=None,
            raw=dict(sender),
        )

    async def display_name(
        self, user_id: str, *, group_id: str | None = None, refresh: bool = False
    ) -> str:
        return (await self.get(user_id, group_id=group_id, refresh=refresh)).display_name

    async def get_many(
        self, user_ids: Sequence[str], *, group_id: str | None = None
    ) -> dict[str, UserProfile]:
        if not user_ids:
            return {}
        uid_list: list[str] = []
        for raw_id in user_ids:
            uid = str(raw_id)
            if uid not in uid_list:
                uid_list.append(uid)
        result: dict[str, UserProfile] = {}
        missing: list[str] = []
        now = self._now()
        for uid in uid_list:
            key = (uid, str(group_id) if group_id is not None else None)
            cached = self._cache_get(key, now)
            if cached is not None:
                result[uid] = cached
            else:
                missing.append(uid)
        if not missing:
            return {uid: result[uid] for uid in uid_list}
        if group_id is not None:
            adapter = self._require_adapter()
            if len(missing) == 1:
                result[missing[0]] = await self.get(missing[0], group_id=group_id)
                return {uid: result[uid] for uid in uid_list}
            try:
                response = await adapter.get_group_member_list(int(group_id))
            except Exception:
                response = None
            if response is not None and getattr(response, "data", None) is not None:
                members = {
                    str(member.user_id): member
                    for member in response.data
                    if member is not None and member.user_id is not None
                }
                now = self._now()
                remaining: list[str] = []
                for uid in missing:
                    member = members.get(uid)
                    if member is not None:
                        profile = self._profile_from_group_member(member, fallback_uid=uid)
                        self._cache[(uid, str(group_id))] = (profile, now, False)
                        result[uid] = profile
                    else:
                        remaining.append(uid)
                if remaining:
                    profiles = await asyncio.gather(
                        *(self.get(uid, group_id=group_id) for uid in remaining)
                    )
                    for uid, profile in zip(remaining, profiles):
                        result[uid] = profile
                return {uid: result[uid] for uid in uid_list}
        profiles = await asyncio.gather(
            *(self.get(uid, group_id=group_id) for uid in missing)
        )
        for uid, profile in zip(missing, profiles):
            result[uid] = profile
        return {uid: result[uid] for uid in uid_list}
