from __future__ import annotations

import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from neobot_contracts.models import ConversationRef


Direction = Literal["incoming", "outgoing"]


def _id_value(value: Any) -> int | str:
    text = str(value or "")
    return int(text) if text.isdigit() else text


def _id_key(value: Any) -> str:
    return str(value or "")


def _now() -> int:
    return int(time.time())


@dataclass
class LocalConversation:
    kind: str
    id: str
    name: str = ""
    updated_at: int = 0
    last_message_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "updated_at": self.updated_at,
            "last_message_id": self.last_message_id,
        }


@dataclass
class LocalStoredMessage:
    message_id: int
    conversation: ConversationRef
    direction: Direction
    time: int
    sender: dict[str, Any]
    segments: list[dict[str, Any]]
    raw_message: str
    onebot_event: dict[str, Any] = field(default_factory=dict)
    deleted: bool = False
    deleted_at: int | None = None
    operator_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation": {
                "kind": self.conversation.kind,
                "id": self.conversation.id,
            },
            "direction": self.direction,
            "time": self.time,
            "sender": deepcopy(self.sender),
            "segments": deepcopy(self.segments),
            "raw_message": self.raw_message,
            "deleted": self.deleted,
            "deleted_at": self.deleted_at,
            "operator_id": self.operator_id,
        }


class LocalMessageStore:
    def __init__(self, *, bot_user_id: int = 0, bot_name: str = "Neo Bot") -> None:
        self._bot_user_id = int(bot_user_id or 0)
        self._bot_name = bot_name or "Neo Bot"
        self.reset_state()

    @property
    def bot_user_id(self) -> int:
        return self._bot_user_id

    @property
    def bot_name(self) -> str:
        return self._bot_name

    def reset_state(self) -> None:
        self._next_message_id = 1_000_000
        self._next_request_id = 1
        self._next_forward_id = 1
        self._messages_by_id: dict[int, LocalStoredMessage] = {}
        self._message_order: list[int] = []
        self._conversation_messages: dict[tuple[str, str], list[int]] = {}
        self._conversations: dict[tuple[str, str], LocalConversation] = {}
        self._users: dict[str, dict[str, Any]] = {}
        self._friends: dict[str, dict[str, Any]] = {}
        self._groups: dict[str, dict[str, Any]] = {}
        self._group_members: dict[str, dict[str, dict[str, Any]]] = {}
        self._friend_requests: dict[str, dict[str, Any]] = {}
        self._group_requests: dict[str, dict[str, Any]] = {}
        self._media: dict[str, dict[str, Any]] = {}
        self._forward_messages: dict[str, dict[str, Any]] = {}
        self._forward_aliases: dict[str, str] = {}
        self._reactions: dict[str, dict[str, Any]] = {}

    def next_message_id(self) -> int:
        message_id = self._next_message_id
        self._next_message_id += 1
        return message_id

    def export_state_sync(self) -> dict[str, Any]:
        return {
            "version": 1,
            "bot": {"user_id": self._bot_user_id, "nickname": self._bot_name},
            "counters": {
                "next_message_id": self._next_message_id,
                "next_request_id": self._next_request_id,
                "next_forward_id": self._next_forward_id,
            },
            "conversations": [item.to_dict() for item in self._conversations.values()],
            "messages": [
                self._message_to_state(self._messages_by_id[mid])
                for mid in self._message_order
                if mid in self._messages_by_id
            ],
            "users": list(deepcopy(self._users).values()),
            "friends": list(deepcopy(self._friends).values()),
            "groups": list(deepcopy(self._groups).values()),
            "group_members": deepcopy(self._group_members),
            "friend_requests": list(deepcopy(self._friend_requests).values()),
            "group_requests": list(deepcopy(self._group_requests).values()),
            "media": list(deepcopy(self._media).values()),
            "forward_messages": list(deepcopy(self._forward_messages).values()),
            "forward_aliases": deepcopy(self._forward_aliases),
            "reactions": list(deepcopy(self._reactions).values()),
        }

    def load_state_sync(self, state: dict[str, Any]) -> None:
        self.reset_state()
        bot = state.get("bot") if isinstance(state.get("bot"), dict) else {}
        if bot.get("user_id") is not None:
            try:
                self._bot_user_id = int(bot.get("user_id") or 0)
            except (TypeError, ValueError):
                self._bot_user_id = 0
        if bot.get("nickname"):
            self._bot_name = str(bot.get("nickname") or self._bot_name)

        for item in state.get("conversations") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            conversation_id = str(item.get("id") or "")
            if kind and conversation_id:
                self._conversations[(kind, conversation_id)] = LocalConversation(
                    kind=kind,
                    id=conversation_id,
                    name=str(item.get("name") or ""),
                    updated_at=int(item.get("updated_at") or 0),
                    last_message_id=item.get("last_message_id"),
                )

        max_message_id = 999_999
        for item in state.get("messages") or []:
            if not isinstance(item, dict):
                continue
            message = self._message_from_state(item)
            if message is None:
                continue
            self._save(message, conversation_name="")
            self._learn_from_message(message)
            max_message_id = max(max_message_id, message.message_id)

        self._users = {
            _id_key(item.get("user_id")): dict(item)
            for item in state.get("users") or []
            if isinstance(item, dict) and item.get("user_id") is not None
        }
        self._friends = {
            _id_key(item.get("user_id")): self._normalize_friend(item)
            for item in state.get("friends") or []
            if isinstance(item, dict) and item.get("user_id") is not None
        }
        self._groups = {
            _id_key(item.get("group_id")): self._normalize_group(item)
            for item in state.get("groups") or []
            if isinstance(item, dict) and item.get("group_id") is not None
        }
        members = state.get("group_members") if isinstance(state.get("group_members"), dict) else {}
        self._group_members = {
            str(group_id): {
                str(user_id): self._normalize_group_member(str(group_id), member)
                for user_id, member in group_members.items()
                if isinstance(member, dict)
            }
            for group_id, group_members in members.items()
            if isinstance(group_members, dict)
        }
        self._friend_requests = {
            str(item.get("flag")): dict(item)
            for item in state.get("friend_requests") or []
            if isinstance(item, dict) and item.get("flag")
        }
        self._group_requests = {
            str(item.get("flag")): dict(item)
            for item in state.get("group_requests") or []
            if isinstance(item, dict) and item.get("flag")
        }
        self._media = {}
        for item in state.get("media") or []:
            if isinstance(item, dict):
                self.put_media_data(item)
        self._forward_messages = {
            str(item.get("id")): dict(item)
            for item in state.get("forward_messages") or []
            if isinstance(item, dict) and item.get("id")
        }
        aliases = state.get("forward_aliases") if isinstance(state.get("forward_aliases"), dict) else {}
        self._forward_aliases = {str(k): str(v) for k, v in aliases.items()}
        self._reactions = {}
        for item in state.get("reactions") or []:
            if isinstance(item, dict):
                self.put_reaction_data(item)

        counters = state.get("counters") if isinstance(state.get("counters"), dict) else {}
        self._next_message_id = max(
            int(counters.get("next_message_id") or 1_000_000),
            max_message_id + 1,
            1_000_000,
        )
        self._next_request_id = max(int(counters.get("next_request_id") or 1), self._next_request_id)
        self._next_forward_id = max(int(counters.get("next_forward_id") or 1), self._next_forward_id)
        self._refresh_group_member_counts()

    def add_event(
        self,
        event: dict[str, Any],
        *,
        direction: Direction,
        conversation_name: str = "",
    ) -> LocalStoredMessage | None:
        conversation = self._conversation_from_event(event)
        if conversation is None:
            return None
        message_id = self._ensure_message_id(event)
        timestamp = int(event.get("time") or time.time())
        segments = self._normalize_segments(event.get("message"))
        raw_message = str(event.get("raw_message") or self.raw_from_segments(segments))
        sender = self._sender_from_event(event, direction=direction)
        stored = LocalStoredMessage(
            message_id=message_id,
            conversation=conversation,
            direction=direction,
            time=timestamp,
            sender=sender,
            segments=segments,
            raw_message=raw_message,
            onebot_event=deepcopy(event),
        )
        self._save(stored, conversation_name=conversation_name)
        self._learn_from_message(stored)
        return stored

    def add_outgoing(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
    ) -> LocalStoredMessage:
        message_id = self.next_message_id()
        timestamp = int(time.time())
        segments = self.normalize_message_payload(message)
        raw_message = self.raw_from_segments(segments)
        sender = {
            "user_id": str(self._bot_user_id),
            "nickname": self._bot_name,
            "is_bot": True,
        }
        event: dict[str, Any] = {
            "time": timestamp,
            "self_id": self._bot_user_id,
            "post_type": "message_sent",
            "message_type": conversation.kind,
            "sub_type": "friend" if conversation.kind == "private" else "normal",
            "message_id": message_id,
            "user_id": self._bot_user_id,
            "message": segments,
            "raw_message": raw_message,
            "font": 0,
            "sender": sender,
        }
        if conversation.kind == "group":
            event["group_id"] = _id_value(conversation.id)
        else:
            event["target_id"] = _id_value(conversation.id)
        stored = LocalStoredMessage(
            message_id=message_id,
            conversation=conversation,
            direction="outgoing",
            time=timestamp,
            sender=sender,
            segments=segments,
            raw_message=raw_message,
            onebot_event=event,
        )
        self._save(stored)
        self._learn_media_from_message(stored)
        return stored

    def get_msg(self, message_id: int) -> LocalStoredMessage | None:
        return self._messages_by_id.get(int(message_id))

    def list_messages(
        self,
        conversation: ConversationRef,
        *,
        limit: int = 50,
        before_message_id: int | None = None,
    ) -> list[LocalStoredMessage]:
        limit = max(1, min(int(limit), 200))
        ids = list(self._conversation_messages.get((conversation.kind, conversation.id), []))
        if before_message_id is not None:
            try:
                index = ids.index(int(before_message_id))
                ids = ids[:index]
            except ValueError:
                ids = [mid for mid in ids if mid < int(before_message_id)]
        selected = ids[-limit:]
        return [self._messages_by_id[mid] for mid in selected if mid in self._messages_by_id]

    def list_conversations(self) -> list[LocalConversation]:
        return sorted(
            self._conversations.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def friend_list(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._friends.values()]

    def group_list(self) -> list[dict[str, Any]]:
        self._refresh_group_member_counts()
        return [deepcopy(item) for item in self._groups.values()]

    def group_member_list(self, group_id: int | str) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._group_members.get(str(group_id), {}).values()]

    def group_member_info(self, group_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        member = self._group_members.get(str(group_id), {}).get(str(user_id))
        return deepcopy(member) if member is not None else None

    def stranger_info(self, user_id: int | str) -> dict[str, Any]:
        key = str(user_id)
        if key in self._users:
            return deepcopy(self._users[key])
        if key in self._friends:
            return deepcopy(self._friends[key])
        for members in self._group_members.values():
            if key in members:
                return deepcopy(members[key])
        return {"user_id": _id_value(key), "nickname": f"QQ:{key}"}

    def history(
        self,
        conversation: ConversationRef,
        *,
        count: int = 20,
        message_seq: int = 0,
        reverse_order: bool = False,
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(count), 200))
        ids = list(self._conversation_messages.get((conversation.kind, conversation.id), []))
        if message_seq:
            seq = int(message_seq)
            ids = [mid for mid in ids if mid < seq]
        selected = ids[-count:]
        if reverse_order:
            selected = list(reversed(selected))
        return [
            self._to_onebot_message_data(self._messages_by_id[mid])
            for mid in selected
            if mid in self._messages_by_id
        ]

    def to_onebot_message_data(self, message: LocalStoredMessage) -> dict[str, Any]:
        return self._to_onebot_message_data(message)

    def upsert_user_data(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = user.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required")
        key = _id_key(user_id)
        current = deepcopy(self._users.get(key, {}))
        current.update(deepcopy(user))
        current["user_id"] = _id_value(user_id)
        current.setdefault("nickname", f"QQ:{key}")
        self._users[key] = current
        return deepcopy(current)

    def upsert_friend_data(self, friend: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_friend(friend)
        key = _id_key(normalized["user_id"])
        current = deepcopy(self._friends.get(key, {}))
        current.update(normalized)
        self._friends[key] = current
        self.upsert_user_data(current)
        return deepcopy(current)

    def delete_friend_data(self, user_id: int | str) -> bool:
        return self._friends.pop(str(user_id), None) is not None

    def set_friend_remark_data(self, user_id: int | str, remark: str | None) -> dict[str, Any] | None:
        key = str(user_id)
        friend = self._friends.get(key)
        if friend is None:
            return None
        friend["remark"] = remark or ""
        return deepcopy(friend)

    def upsert_group_data(self, group: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_group(group)
        key = _id_key(normalized["group_id"])
        current = deepcopy(self._groups.get(key, {}))
        current.update(normalized)
        self._groups[key] = current
        self._refresh_group_member_counts()
        return deepcopy(self._groups[key])

    def get_group_data(self, group_id: int | str) -> dict[str, Any] | None:
        group = self._groups.get(str(group_id))
        return deepcopy(group) if group is not None else None

    def upsert_group_member_data(self, group_id: int | str, member: dict[str, Any]) -> dict[str, Any]:
        group_key = str(group_id)
        self._groups.setdefault(
            group_key,
            self._normalize_group({"group_id": group_id, "group_name": f"群聊{group_key}"}),
        )
        normalized = self._normalize_group_member(group_key, member)
        user_key = _id_key(normalized["user_id"])
        members = self._group_members.setdefault(group_key, {})
        current = deepcopy(members.get(user_key, {}))
        current.update(normalized)
        members[user_key] = current
        self.upsert_user_data(current)
        self._refresh_group_member_counts()
        return deepcopy(current)

    def remove_group_member_data(self, group_id: int | str, user_id: int | str) -> bool:
        members = self._group_members.get(str(group_id), {})
        removed = members.pop(str(user_id), None) is not None
        self._refresh_group_member_counts()
        return removed

    def update_group_member_data(self, group_id: int | str, user_id: int | str, fields: dict[str, Any]) -> dict[str, Any] | None:
        member = self._group_members.get(str(group_id), {}).get(str(user_id))
        if member is None:
            return None
        member.update(fields)
        if "card" in fields:
            nickname = member.get("nickname") or f"QQ:{user_id}"
            member["card_or_nickname"] = fields.get("card") or nickname
        return deepcopy(member)

    def update_group_data(self, group_id: int | str, fields: dict[str, Any]) -> dict[str, Any] | None:
        group = self._groups.get(str(group_id))
        if group is None:
            return None
        group.update(fields)
        return deepcopy(group)

    def group_shut_list(self, group_id: int | str) -> list[dict[str, Any]]:
        now = _now()
        return [
            deepcopy(member)
            for member in self._group_members.get(str(group_id), {}).values()
            if int(member.get("shut_up_timestamp") or 0) > now
        ]

    def mark_message_deleted_data(self, message_id: int, operator_id: int | str | None = None) -> dict[str, Any] | None:
        message = self.get_msg(int(message_id))
        if message is None:
            return None
        message.deleted = True
        message.deleted_at = _now()
        message.operator_id = operator_id
        message.onebot_event["deleted"] = True
        message.onebot_event["deleted_at"] = message.deleted_at
        if operator_id is not None:
            message.onebot_event["operator_id"] = operator_id
        return self._to_onebot_message_data(message)

    def put_media_data(self, media: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(media)
        key = str(normalized.get("file") or normalized.get("url") or normalized.get("path") or "")
        if not key:
            raise ValueError("media file/url/path is required")
        normalized.setdefault("file", key)
        normalized.setdefault("file_name", str(normalized.get("file") or key).split("/")[-1].split("\\")[-1])
        self._media[str(normalized.get("file") or key)] = normalized
        if normalized.get("url"):
            self._media[str(normalized["url"])] = normalized
        if normalized.get("path"):
            self._media[str(normalized["path"])] = normalized
        return deepcopy(normalized)

    def get_media_data(self, file: str) -> dict[str, Any] | None:
        media = self._media.get(str(file))
        return deepcopy(media) if media is not None else None

    def create_friend_request_data(self, request: dict[str, Any]) -> dict[str, Any]:
        flag = str(request.get("flag") or f"friend_{self._next_request_id}")
        self._next_request_id += 1
        user_id = request.get("user_id") or request.get("uin")
        if user_id is None:
            raise ValueError("user_id is required")
        item = {
            "flag": flag,
            "request_type": "friend",
            "user_id": _id_value(user_id),
            "comment": str(request.get("comment") or request.get("msg") or ""),
            "nickname": str(request.get("nickname") or request.get("nick") or f"QQ:{user_id}"),
            "status": "pending",
            "time": int(request.get("time") or _now()),
        }
        item.update({k: deepcopy(v) for k, v in request.items() if k not in item})
        self._friend_requests[flag] = item
        self.upsert_user_data({"user_id": user_id, "nickname": item["nickname"]})
        return deepcopy(item)

    def resolve_friend_request_data(
        self,
        flag: str,
        *,
        approve: bool,
        remark: str | None = None,
    ) -> dict[str, Any] | None:
        item = self._friend_requests.get(str(flag))
        if item is None:
            return None
        item["status"] = "approved" if approve else "rejected"
        item["resolved_at"] = _now()
        item["approve"] = bool(approve)
        if remark is not None:
            item["remark"] = remark
        if approve:
            self.upsert_friend_data(
                {
                    "user_id": item.get("user_id"),
                    "nickname": item.get("nickname") or f"QQ:{item.get('user_id')}",
                    "remark": remark or "",
                }
            )
        return deepcopy(item)

    def create_group_request_data(self, request: dict[str, Any]) -> dict[str, Any]:
        flag = str(request.get("flag") or f"group_{self._next_request_id}")
        self._next_request_id += 1
        group_id = request.get("group_id")
        user_id = request.get("user_id") or request.get("requester_uin") or request.get("invitor_uin")
        if group_id is None:
            raise ValueError("group_id is required")
        if user_id is None:
            raise ValueError("user_id is required")
        sub_type = str(request.get("sub_type") or "add")
        item = {
            "flag": flag,
            "request_type": "group",
            "sub_type": sub_type,
            "group_id": _id_value(group_id),
            "user_id": _id_value(user_id),
            "comment": str(request.get("comment") or request.get("message") or ""),
            "nickname": str(request.get("nickname") or request.get("requester_nick") or f"QQ:{user_id}"),
            "status": "pending",
            "time": int(request.get("time") or _now()),
        }
        item.update({k: deepcopy(v) for k, v in request.items() if k not in item})
        self._group_requests[flag] = item
        self.upsert_group_data({"group_id": group_id, "group_name": request.get("group_name") or f"群聊{group_id}"})
        self.upsert_user_data({"user_id": user_id, "nickname": item["nickname"]})
        return deepcopy(item)

    def resolve_group_request_data(
        self,
        flag: str,
        *,
        approve: bool,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        item = self._group_requests.get(str(flag))
        if item is None:
            return None
        item["status"] = "approved" if approve else "rejected"
        item["resolved_at"] = _now()
        item["approve"] = bool(approve)
        if reason is not None:
            item["reason"] = reason
        if approve:
            self.upsert_group_member_data(
                item["group_id"],
                {
                    "user_id": item["user_id"],
                    "nickname": item.get("nickname") or f"QQ:{item['user_id']}",
                    "role": "member",
                },
            )
        return deepcopy(item)

    def group_system_msg_data(self) -> dict[str, Any]:
        invited = []
        join = []
        for item in self._group_requests.values():
            data = {
                "request_id": item.get("flag"),
                "group_id": item.get("group_id"),
                "checked": item.get("status") != "pending",
                "actor": self._bot_user_id if item.get("status") != "pending" else None,
            }
            if item.get("sub_type") == "invite":
                data.update(
                    {
                        "group_name": self._groups.get(str(item.get("group_id")), {}).get("group_name", ""),
                        "invitor_nick": item.get("nickname"),
                        "invitor_uin": item.get("user_id"),
                    }
                )
                invited.append(data)
            else:
                data.update(
                    {
                        "requester_uin": item.get("user_id"),
                        "requester_nick": item.get("nickname"),
                        "message": item.get("comment") or "",
                    }
                )
                join.append(data)
        return {"invited_requests": invited, "join_requests": join}

    def put_forward_message_data(self, nodes: list[dict[str, Any]], forward_id: str | None = None) -> dict[str, Any]:
        fid = str(forward_id or f"local_forward_{self._next_forward_id}")
        self._next_forward_id += 1
        item = {"id": fid, "messages": deepcopy(nodes), "time": _now()}
        self._forward_messages[fid] = item
        return deepcopy(item)

    def bind_forward_message_data(self, forward_id: str, message_id: int) -> None:
        if forward_id:
            self._forward_aliases[str(message_id)] = str(forward_id)

    def get_forward_message_data(self, lookup_id: str) -> dict[str, Any] | None:
        key = str(lookup_id)
        forward_id = key if key in self._forward_messages else self._forward_aliases.get(key)
        if forward_id is None and key.isdigit():
            message = self.get_msg(int(key))
            if message is not None:
                for segment in message.segments:
                    if segment.get("type") != "forward":
                        continue
                    data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
                    candidate = str(data.get("id") or "")
                    if candidate in self._forward_messages:
                        forward_id = candidate
                        break
        if forward_id is None:
            return None
        item = self._forward_messages.get(forward_id)
        return deepcopy(item) if item is not None else None

    def put_reaction_data(self, reaction: dict[str, Any]) -> dict[str, Any]:
        message_id = int(reaction.get("message_id") or 0)
        emoji_id = str(reaction.get("emoji_id") or reaction.get("emojiId") or "")
        user_id = str(reaction.get("user_id") or self._bot_user_id)
        if not message_id or not emoji_id:
            raise ValueError("message_id and emoji_id are required")
        item = {
            "message_id": message_id,
            "emoji_id": _id_value(emoji_id),
            "user_id": _id_value(user_id),
            "group_id": reaction.get("group_id"),
            "time": int(reaction.get("time") or _now()),
        }
        item.update({k: deepcopy(v) for k, v in reaction.items() if k not in item})
        self._reactions[f"{message_id}:{emoji_id}:{user_id}"] = item
        return deepcopy(item)

    def remove_reaction_data(self, message_id: int, emoji_id: str, user_id: str) -> bool:
        return self._reactions.pop(f"{int(message_id)}:{emoji_id}:{user_id}", None) is not None

    def list_reactions_data(self, message_id: int) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in self._reactions.values()
            if int(item.get("message_id") or 0) == int(message_id)
        ]

    def _save(self, message: LocalStoredMessage, *, conversation_name: str = "") -> None:
        self._messages_by_id[message.message_id] = message
        if message.message_id not in self._message_order:
            self._message_order.append(message.message_id)
        key = (message.conversation.kind, message.conversation.id)
        ids = self._conversation_messages.setdefault(key, [])
        if message.message_id not in ids:
            ids.append(message.message_id)
        conv = self._conversations.get(key)
        if conv is None:
            conv = LocalConversation(
                kind=message.conversation.kind,
                id=message.conversation.id,
                name=conversation_name,
            )
            self._conversations[key] = conv
        if conversation_name and not conv.name:
            conv.name = conversation_name
        conv.updated_at = message.time
        conv.last_message_id = message.message_id

    def _learn_from_message(self, message: LocalStoredMessage) -> None:
        sender = dict(message.sender)
        user_id = str(sender.get("user_id") or "")
        if not user_id:
            return
        nickname = sender.get("nickname") or sender.get("card") or f"QQ:{user_id}"
        self.upsert_user_data(
            {
                "user_id": user_id,
                "nickname": nickname,
                "sex": sender.get("sex"),
                "age": sender.get("age"),
            }
        )
        if message.conversation.kind == "private":
            self.upsert_friend_data(
                {
                    "user_id": user_id,
                    "nickname": nickname,
                    "remark": sender.get("remark") or "",
                    "sex": sender.get("sex"),
                    "age": sender.get("age"),
                }
            )
        else:
            group_id = message.conversation.id
            self.upsert_group_data(
                {
                    "group_id": group_id,
                    "group_name": self._conversations[(message.conversation.kind, group_id)].name
                    or f"群聊{group_id}",
                }
            )
            self.upsert_group_member_data(
                group_id,
                {
                    "user_id": user_id,
                    "nickname": nickname,
                    "card": sender.get("card") or "",
                    "sex": sender.get("sex"),
                    "age": sender.get("age"),
                    "role": sender.get("role") or "member",
                },
            )
        self._learn_media_from_message(message)

    def _learn_media_from_message(self, message: LocalStoredMessage) -> None:
        for segment in message.segments:
            seg_type = str(segment.get("type") or "")
            if seg_type not in {"image", "cardimage", "record", "video", "file"}:
                continue
            data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
            file = data.get("file") or data.get("url") or data.get("path")
            if not file:
                continue
            media = dict(data)
            media.setdefault("type", seg_type)
            media.setdefault("file", file)
            try:
                self.put_media_data(media)
            except ValueError:
                pass

    def _conversation_from_event(self, event: dict[str, Any]) -> ConversationRef | None:
        message_type = event.get("message_type")
        if message_type == "private":
            user_id = event.get("user_id") or event.get("target_id")
            if user_id is None:
                return None
            return ConversationRef(kind="private", id=str(user_id))
        if message_type == "group":
            group_id = event.get("group_id")
            if group_id is None:
                return None
            return ConversationRef(kind="group", id=str(group_id))
        return None

    def _ensure_message_id(self, event: dict[str, Any]) -> int:
        value = event.get("message_id")
        if value is not None:
            try:
                message_id = int(value)
                self._next_message_id = max(self._next_message_id, message_id + 1)
                return message_id
            except (TypeError, ValueError):
                pass
        message_id = self.next_message_id()
        event["message_id"] = message_id
        return message_id

    def _sender_from_event(self, event: dict[str, Any], *, direction: Direction) -> dict[str, Any]:
        sender = event.get("sender")
        if not isinstance(sender, dict):
            sender = {}
        user_id = event.get("user_id") or sender.get("user_id")
        return {
            **sender,
            "user_id": str(user_id) if user_id is not None else "",
            "nickname": sender.get("nickname") or (f"QQ:{user_id}" if user_id is not None else ""),
            "is_bot": direction == "outgoing",
        }

    def _to_onebot_message_data(self, message: LocalStoredMessage) -> dict[str, Any]:
        data = deepcopy(message.onebot_event)
        data["message_id"] = message.message_id
        data["real_id"] = message.message_id
        data["message_seq"] = message.message_id
        data["message_format"] = "array"
        data["message"] = deepcopy(message.segments)
        data["raw_message"] = message.raw_message
        data["sender"] = deepcopy(message.sender)
        if message.deleted:
            data["deleted"] = True
            data["deleted_at"] = message.deleted_at
            data["operator_id"] = message.operator_id
        return data

    def _message_to_state(self, message: LocalStoredMessage) -> dict[str, Any]:
        data = message.to_dict()
        data["onebot_event"] = deepcopy(message.onebot_event)
        return data

    def _message_from_state(self, item: dict[str, Any]) -> LocalStoredMessage | None:
        conversation_data = item.get("conversation") if isinstance(item.get("conversation"), dict) else {}
        kind = str(conversation_data.get("kind") or "")
        conversation_id = str(conversation_data.get("id") or "")
        if kind not in {"private", "group"} or not conversation_id:
            return None
        try:
            message_id = int(item.get("message_id") or 0)
        except (TypeError, ValueError):
            return None
        if not message_id:
            return None
        direction = "outgoing" if item.get("direction") == "outgoing" else "incoming"
        segments = self._normalize_segments(item.get("segments") or item.get("message"))
        onebot_event = deepcopy(item.get("onebot_event")) if isinstance(item.get("onebot_event"), dict) else {}
        if not onebot_event:
            onebot_event = {
                "post_type": "message" if direction == "incoming" else "message_sent",
                "message_type": kind,
                "message_id": message_id,
                "message": segments,
                "raw_message": item.get("raw_message") or self.raw_from_segments(segments),
                "sender": deepcopy(item.get("sender") or {}),
            }
        return LocalStoredMessage(
            message_id=message_id,
            conversation=ConversationRef(kind=kind, id=conversation_id),
            direction=direction,
            time=int(item.get("time") or _now()),
            sender=deepcopy(item.get("sender") or onebot_event.get("sender") or {}),
            segments=segments,
            raw_message=str(item.get("raw_message") or self.raw_from_segments(segments)),
            onebot_event=onebot_event,
            deleted=bool(item.get("deleted", False)),
            deleted_at=item.get("deleted_at"),
            operator_id=item.get("operator_id"),
        )

    def _normalize_friend(self, friend: dict[str, Any]) -> dict[str, Any]:
        user_id = friend.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required")
        key = _id_key(user_id)
        return {
            **deepcopy(friend),
            "user_id": _id_value(user_id),
            "nickname": str(friend.get("nickname") or friend.get("nick") or f"QQ:{key}"),
            "remark": str(friend.get("remark") or ""),
        }

    def _normalize_group(self, group: dict[str, Any]) -> dict[str, Any]:
        group_id = group.get("group_id")
        if group_id is None:
            raise ValueError("group_id is required")
        key = _id_key(group_id)
        current_member_count = len(self._group_members.get(key, {}))
        return {
            **deepcopy(group),
            "group_id": _id_value(group_id),
            "group_name": str(group.get("group_name") or group.get("name") or f"群聊{key}"),
            "member_count": int(group.get("member_count") or current_member_count),
            "max_member_count": int(group.get("max_member_count") or max(current_member_count, 200)),
        }

    def _normalize_group_member(self, group_id: int | str, member: dict[str, Any]) -> dict[str, Any]:
        user_id = member.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required")
        user_key = _id_key(user_id)
        nickname = str(member.get("nickname") or member.get("card") or f"QQ:{user_key}")
        card = str(member.get("card") or "")
        return {
            **deepcopy(member),
            "group_id": _id_value(group_id),
            "user_id": _id_value(user_id),
            "nickname": nickname,
            "card": card,
            "card_or_nickname": card or nickname,
            "role": str(member.get("role") or "member"),
        }

    def _refresh_group_member_counts(self) -> None:
        for group_id, group in self._groups.items():
            member_count = len(self._group_members.get(group_id, {}))
            group["member_count"] = member_count
            group["max_member_count"] = max(int(group.get("max_member_count") or 0), member_count, 200)

    @classmethod
    def normalize_message_payload(cls, message: str | list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(message, str):
            return [{"type": "text", "data": {"text": message}}]
        if isinstance(message, dict):
            return [message]
        return cls._normalize_segments(message)

    @staticmethod
    def _normalize_segments(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [
                {"type": str(item.get("type") or ""), "data": deepcopy(item.get("data") or {})}
                for item in value
                if isinstance(item, dict)
            ]
        if isinstance(value, dict):
            return [{"type": str(value.get("type") or ""), "data": deepcopy(value.get("data") or {})}]
        if isinstance(value, str):
            return [{"type": "text", "data": {"text": value}}]
        return []

    @staticmethod
    def raw_from_segments(segments: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for segment in segments:
            seg_type = str(segment.get("type") or "")
            data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
            if seg_type == "text":
                parts.append(str(data.get("text") or ""))
            elif seg_type:
                parts.append(f"[{seg_type}]")
        return "".join(parts)


class InMemorySandboxDataStore(LocalMessageStore):
    async def reset(self) -> None:
        self.reset_state()

    async def export_state(self) -> dict[str, Any]:
        return self.export_state_sync()

    async def load_state(self, state: dict[str, Any]) -> None:
        self.load_state_sync(state)

    async def flush(self) -> None:
        return None

    async def upsert_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_user_data(user)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        user = self._users.get(str(user_id))
        return deepcopy(user) if user is not None else None

    async def upsert_friend(self, friend: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_friend_data(friend)

    async def delete_friend(self, user_id: str) -> bool:
        return self.delete_friend_data(user_id)

    async def list_friends(self) -> list[dict[str, Any]]:
        return self.friend_list()

    async def set_friend_remark(self, user_id: str, remark: str | None) -> dict[str, Any] | None:
        return self.set_friend_remark_data(user_id, remark)

    async def upsert_group(self, group: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_group_data(group)

    async def get_group(self, group_id: str) -> dict[str, Any] | None:
        return self.get_group_data(group_id)

    async def list_groups(self) -> list[dict[str, Any]]:
        return self.group_list()

    async def upsert_group_member(self, group_id: str, member: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_group_member_data(group_id, member)

    async def remove_group_member(self, group_id: str, user_id: str) -> bool:
        return self.remove_group_member_data(group_id, user_id)

    async def get_group_member(self, group_id: str, user_id: str) -> dict[str, Any] | None:
        return self.group_member_info(group_id, user_id)

    async def list_group_members(self, group_id: str) -> list[dict[str, Any]]:
        return self.group_member_list(group_id)

    async def mark_message_deleted(self, message_id: int, operator_id: int | str | None = None) -> dict[str, Any] | None:
        return self.mark_message_deleted_data(message_id, operator_id)

    async def put_media(self, media: dict[str, Any]) -> dict[str, Any]:
        return self.put_media_data(media)

    async def get_media(self, file: str) -> dict[str, Any] | None:
        return self.get_media_data(file)

    async def create_friend_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.create_friend_request_data(request)

    async def resolve_friend_request(
        self,
        flag: str,
        *,
        approve: bool,
        remark: str | None = None,
    ) -> dict[str, Any] | None:
        return self.resolve_friend_request_data(flag, approve=approve, remark=remark)

    async def create_group_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.create_group_request_data(request)

    async def resolve_group_request(
        self,
        flag: str,
        *,
        approve: bool,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        return self.resolve_group_request_data(flag, approve=approve, reason=reason)

    async def put_forward_message(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return self.put_forward_message_data(nodes)

    async def bind_forward_message(self, forward_id: str, message_id: int) -> None:
        self.bind_forward_message_data(forward_id, message_id)

    async def get_forward_message(self, lookup_id: str) -> dict[str, Any] | None:
        return self.get_forward_message_data(lookup_id)

    async def put_reaction(self, reaction: dict[str, Any]) -> dict[str, Any]:
        return self.put_reaction_data(reaction)

    async def remove_reaction(self, message_id: int, emoji_id: str, user_id: str) -> bool:
        return self.remove_reaction_data(message_id, emoji_id, user_id)

    async def list_reactions(self, message_id: int) -> list[dict[str, Any]]:
        return self.list_reactions_data(message_id)
