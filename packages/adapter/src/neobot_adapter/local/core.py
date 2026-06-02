from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.sandbox import SandboxDataPort

from neobot_adapter.local.server import LocalAdapterServer
from neobot_adapter.local.store import InMemorySandboxDataStore
from neobot_adapter.local.websocket import LocalWebSocketHub


class LocalCore:
    def __init__(
        self,
        *,
        dispatcher: Any,
        host: str = "127.0.0.1",
        port: int = 8090,
        auth_token: str = "",
        bot_user_id: int = 0,
        bot_name: str = "Neo Bot",
        logger: Logger | None = None,
        packet_callback: Any = None,
        sandbox_data: SandboxDataPort | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._logger = logger or NullLogger()
        self._packet_callback = packet_callback
        self._store: Any = sandbox_data or InMemorySandboxDataStore(
            bot_user_id=bot_user_id,
            bot_name=bot_name,
        )
        self._hub = LocalWebSocketHub()
        self._server = LocalAdapterServer(
            core=self,
            host=host,
            port=port,
            auth_token=auth_token,
        )
        self._started = asyncio.Event()

    @property
    def store(self) -> Any:
        return self._store

    @property
    def http_url(self) -> str:
        return self._server.public_http_url()

    @property
    def ws_url(self) -> str:
        return self._server.public_ws_url()

    async def start(self) -> None:
        await self._server.start()
        self._started.set()
        self._logger.info(f"本地适配器 HTTP 服务已启动: {self.http_url}")
        self._logger.info(f"本地适配器 WebSocket 服务已启动: {self.ws_url}")

    async def stop(self) -> None:
        await self._hub.close()
        await self._server.stop()
        self._started.clear()

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        return self._server.running

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        return await self._hub.handle(request)

    def health(self) -> dict[str, Any]:
        return {
            "mode": "local",
            "started": self._server.running,
            "host": self._server.host,
            "port": self._server.port,
            "websocket_clients": self._hub.client_count,
        }

    async def create_message(self, data: dict[str, Any]) -> dict[str, Any]:
        event = self._event_from_message_payload(data)
        stored = await self.ingest_event(event)
        if stored is None:
            raise ValueError("message payload did not create a message event")
        return {
            "event_id": f"local_evt_{int(time.time())}_{stored.message_id}",
            "message_id": stored.message_id,
        }

    async def create_event(self, event: dict[str, Any]) -> dict[str, Any]:
        stored = await self.ingest_event(dict(event))
        message_id = stored.message_id if stored is not None else event.get("message_id")
        return {
            "event_id": f"local_evt_{int(time.time())}_{message_id or 0}",
            "message_id": message_id,
        }

    async def create_outgoing(self, data: dict[str, Any]) -> dict[str, Any]:
        conversation = self._conversation_from_payload(data)
        message = data.get("segments")
        if message is None:
            message = str(data.get("message") or "")
        stored = await self.send(conversation, message)
        return {"message_id": stored.message_id}

    async def ingest_event(self, event: dict[str, Any]) -> Any:
        event.setdefault("time", int(time.time()))
        event.setdefault("self_id", self._store.bot_user_id)
        stored = None
        if event.get("post_type") == "message":
            stored = self._store.add_event(
                event,
                direction="incoming",
                conversation_name=self._conversation_name_from_event(event),
            )
            if stored is not None:
                await self._flush_store()
                await self._hub.broadcast("message.created", stored.to_dict())
        else:
            await self._hub.broadcast("event.received", {"event": event})
        self._record_packet(event)
        await self._dispatcher.publish(event)
        return stored

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
    ) -> Any:
        stored = self._store.add_outgoing(conversation, message)
        await self._flush_store()
        await self._hub.broadcast("message.sent", stored.to_dict())
        return stored

    def list_conversations(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._store.list_conversations()]

    def list_messages(
        self,
        *,
        kind: str,
        conversation_id: str,
        limit: int = 50,
        before_message_id: int | None = None,
    ) -> dict[str, Any]:
        conversation = ConversationRef(kind=kind, id=str(conversation_id))
        messages = self._store.list_messages(
            conversation,
            limit=limit,
            before_message_id=before_message_id,
        )
        return {
            "conversation": {"kind": kind, "id": str(conversation_id)},
            "messages": [item.to_dict() for item in messages],
        }

    async def broadcast_action(
        self,
        action: str,
        params: dict[str, Any],
        result: dict[str, Any] | None,
    ) -> None:
        await self._hub.broadcast(
            "adapter.action",
            {"action": action, "params": params, "result": result},
        )

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None:
        return await self._dispatch_action(action, params or {})

    def call_api_sync(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.call_api(action, params, timeout, websocket))
        self._logger.error("LocalCore.call_api_sync cannot run inside the active event loop")
        return None

    async def _dispatch_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "send_private_msg":
            conversation = ConversationRef(kind="private", id=str(params.get("user_id", "")))
            stored = await self.send(conversation, params.get("message", ""))
            return self._ok({"message_id": stored.message_id})
        if action == "send_group_msg":
            conversation = ConversationRef(kind="group", id=str(params.get("group_id", "")))
            stored = await self.send(conversation, params.get("message", ""))
            return self._ok({"message_id": stored.message_id})
        if action in {"send_private_forward_msg", "send_group_forward_msg"}:
            return await self._send_forward_msg(action, params)
        if action == "get_msg":
            message = self._store.get_msg(int(params.get("message_id") or 0))
            return self._ok(self._store.to_onebot_message_data(message)) if message else self._failed("message not found", retcode=1404)
        if action == "get_forward_msg":
            forward = await self._store.get_forward_message(str(params.get("message_id") or ""))
            return self._ok({"messages": forward.get("messages", [])}) if forward else self._failed("forward message not found", retcode=1404)
        if action == "delete_msg":
            return await self._delete_msg(params)
        if action == "get_image":
            return await self._get_media_file(params, media_type="image")
        if action == "get_record":
            return await self._get_media_file(params, media_type="record")
        if action == "get_qq_avatar":
            user_id = params.get("user_id") or self._store.bot_user_id
            return self._ok({"url": f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"})
        if action == "get_friend_list":
            return self._ok(self._store.friend_list())
        if action == "get_friends_with_category":
            return self._ok(
                [
                    {
                        "categoryId": 0,
                        "categorySortId": 0,
                        "categoryName": "默认好友",
                        "categoryMbCount": len(self._store.friend_list()),
                        "onlineCount": len(self._store.friend_list()),
                        "buddyList": self._store.friend_list(),
                    }
                ]
            )
        if action == "delete_friend":
            deleted = await self._store.delete_friend(str(params.get("user_id", "")))
            await self._flush_store()
            return self._ok(None) if deleted else self._failed("friend not found", retcode=1404)
        if action == "set_friend_remark":
            friend = await self._store.set_friend_remark(
                str(params.get("user_id", "")),
                params.get("remark"),
            )
            await self._flush_store()
            return self._ok(None) if friend else self._failed("friend not found", retcode=1404)
        if action == "set_friend_add_request":
            return await self._set_friend_add_request(params)
        if action == "send_like":
            return self._ok(None)
        if action == "friend_poke":
            await self._publish_notice(
                {
                    "notice_type": "notify",
                    "sub_type": "poke",
                    "sender_id": self._store.bot_user_id,
                    "user_id": self._store.bot_user_id,
                    "target_id": params.get("user_id"),
                }
            )
            return self._ok(None)
        if action == "get_doubt_friends_add_request":
            state = await self._store.export_state()
            pending = [
                item
                for item in state.get("friend_requests", [])
                if item.get("status") == "pending"
            ][: int(params.get("count") or 50)]
            return self._ok(pending)
        if action == "get_group_list":
            return self._ok(self._store.group_list())
        if action == "get_group_info":
            group = await self._store.get_group(str(params.get("group_id", "")))
            return self._ok(group) if group else self._failed("group not found", retcode=1404)
        if action == "get_group_member_list":
            return self._ok(self._store.group_member_list(params.get("group_id", "")))
        if action == "get_group_member_info":
            member = self._store.group_member_info(
                params.get("group_id", ""),
                params.get("user_id", ""),
            )
            return self._ok(member) if member else self._failed("group member not found", retcode=1404)
        if action == "get_group_system_msg":
            return self._ok(self._store.group_system_msg_data())
        if action == "set_group_add_request":
            return await self._set_group_add_request(params)
        if action in {
            "set_group_admin",
            "set_group_card",
            "set_group_ban",
            "set_group_whole_ban",
            "set_group_name",
            "set_group_remark",
            "set_group_kick",
            "batch_delete_group_member",
            "set_group_special_title",
            "set_group_leave",
            "group_poke",
            "get_group_shut_list",
            "get_group_honor_info",
            "get_essence_msg_list",
            "set_essence_msg",
            "delete_essence_msg",
            "_send_group_notice",
            "_get_group_notice",
        }:
            return await self._dispatch_group_action(action, params)
        if action == "get_stranger_info":
            return self._ok(self._store.stranger_info(params.get("user_id", "")))
        if action == "get_friend_msg_history":
            messages = self._store.history(
                ConversationRef(kind="private", id=str(params.get("user_id", ""))),
                count=int(params.get("count") or 20),
                message_seq=int(params.get("message_seq") or 0),
                reverse_order=bool(params.get("reverseOrder", False)),
            )
            return self._ok({"messages": messages})
        if action == "get_group_msg_history":
            messages = self._store.history(
                ConversationRef(kind="group", id=str(params.get("group_id", ""))),
                count=int(params.get("count") or 20),
                message_seq=int(params.get("message_seq") or 0),
                reverse_order=bool(params.get("reverseOrder", False)),
            )
            return self._ok({"messages": messages})
        if action == "set_msg_emoji_like":
            return await self._set_msg_emoji_like(params)
        if action == "fetch_emoji_like":
            message_id = int(params.get("message_id") or 0)
            reactions = await self._store.list_reactions(message_id)
            emoji_id = params.get("emoji_id") or params.get("emojiId")
            if emoji_id is not None:
                reactions = [item for item in reactions if str(item.get("emoji_id")) == str(emoji_id)]
            return self._ok({"likes": reactions, "count": len(reactions)})
        if action == "get_login_info":
            return self._ok(
                {
                    "user_id": self._store.bot_user_id,
                    "nickname": self._store.bot_name,
                }
            )
        if action in {"get_version_info", "get_version"}:
            return self._ok(
                {
                    "app_name": "neobot-local-adapter",
                    "app_version": "1.0.0",
                    "protocol_version": "local-v1",
                }
            )
        if action in {"can_send_image", "can_send_record", "mark_msg_as_read", "mark_group_msg_as_read", "mark_private_msg_as_read", "_mark_all_as_read"}:
            return self._ok(None)
        return self._failed("local adapter does not support this action")

    async def reset_sandbox(self) -> dict[str, Any]:
        await self._store.reset()
        await self._flush_store()
        payload = {"reset": True}
        await self._hub.broadcast("sandbox.reset", payload)
        return payload

    async def export_sandbox_state(self) -> dict[str, Any]:
        return await self._store.export_state()

    async def import_sandbox_state(self, state: dict[str, Any]) -> dict[str, Any]:
        await self._store.load_state(state)
        await self._flush_store()
        payload = {"imported": True}
        await self._hub.broadcast("sandbox.imported", payload)
        return payload

    async def upsert_friend(self, data: dict[str, Any]) -> dict[str, Any]:
        friend = await self._store.upsert_friend(data)
        await self._flush_store()
        await self._hub.broadcast("friend.updated", friend)
        return friend

    async def delete_friend(self, user_id: str) -> dict[str, Any]:
        deleted = await self._store.delete_friend(user_id)
        await self._flush_store()
        payload = {"user_id": user_id, "deleted": deleted}
        await self._hub.broadcast("friend.deleted", payload)
        return payload

    async def upsert_group(self, data: dict[str, Any]) -> dict[str, Any]:
        group = await self._store.upsert_group(data)
        await self._flush_store()
        await self._hub.broadcast("group.updated", group)
        return group

    async def upsert_group_member(self, group_id: str, data: dict[str, Any]) -> dict[str, Any]:
        member = await self._store.upsert_group_member(group_id, data)
        await self._flush_store()
        await self._hub.broadcast("group.member.updated", member)
        return member

    async def remove_group_member(self, group_id: str, user_id: str) -> dict[str, Any]:
        deleted = await self._store.remove_group_member(group_id, user_id)
        await self._flush_store()
        payload = {"group_id": group_id, "user_id": user_id, "deleted": deleted}
        await self._hub.broadcast("group.member.deleted", payload)
        return payload

    async def register_media(self, data: dict[str, Any]) -> dict[str, Any]:
        media = await self._store.put_media(data)
        await self._flush_store()
        await self._hub.broadcast("media.updated", media)
        return media

    async def create_forward_message(self, data: dict[str, Any]) -> dict[str, Any]:
        nodes = data.get("messages") or data.get("nodes") or []
        if not isinstance(nodes, list):
            raise ValueError("messages must be an array")
        item = self._store.put_forward_message_data(nodes, forward_id=data.get("id"))
        await self._flush_store()
        await self._hub.broadcast("forward.updated", item)
        return item

    async def create_friend_request(self, data: dict[str, Any]) -> dict[str, Any]:
        item = await self._store.create_friend_request(data)
        await self._flush_store()
        event = {
            "post_type": "request",
            "request_type": "friend",
            "user_id": item.get("user_id"),
            "comment": item.get("comment") or "",
            "flag": item.get("flag"),
        }
        await self._publish_request(event)
        await self._hub.broadcast("friend.request.created", item)
        return item

    async def create_group_request(self, data: dict[str, Any]) -> dict[str, Any]:
        item = await self._store.create_group_request(data)
        await self._flush_store()
        event = {
            "post_type": "request",
            "request_type": "group",
            "sub_type": item.get("sub_type") or "add",
            "group_id": item.get("group_id"),
            "user_id": item.get("user_id"),
            "comment": item.get("comment") or "",
            "flag": item.get("flag"),
        }
        await self._publish_request(event)
        await self._hub.broadcast("group.request.created", item)
        return item

    async def create_notice(self, data: dict[str, Any]) -> dict[str, Any]:
        event = dict(data)
        event["post_type"] = "notice"
        await self._publish_notice(event)
        return event

    async def _send_forward_msg(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        nodes = params.get("messages") or []
        if not isinstance(nodes, list):
            return self._failed("messages must be an array", retcode=1400)
        forward = await self._store.put_forward_message(nodes)
        conversation = ConversationRef(
            kind="group" if action == "send_group_forward_msg" else "private",
            id=str(params.get("group_id") if action == "send_group_forward_msg" else params.get("user_id")),
        )
        stored = await self.send(
            conversation,
            [{"type": "forward", "data": {"id": forward["id"]}}],
        )
        await self._store.bind_forward_message(forward["id"], stored.message_id)
        await self._flush_store()
        return self._ok({"message_id": stored.message_id, "forward_id": forward["id"]})

    async def _delete_msg(self, params: dict[str, Any]) -> dict[str, Any]:
        message_id = int(params.get("message_id") or 0)
        message = self._store.get_msg(message_id)
        if message is None:
            return self._failed("message not found", retcode=1404)
        deleted = await self._store.mark_message_deleted(message_id, self._store.bot_user_id)
        await self._flush_store()
        if message.conversation.kind == "group":
            await self._publish_notice(
                {
                    "notice_type": "group_recall",
                    "group_id": self._coerce_numeric(message.conversation.id),
                    "user_id": self._coerce_numeric(message.sender.get("user_id")),
                    "operator_id": self._store.bot_user_id,
                    "message_id": message_id,
                }
            )
        else:
            await self._publish_notice(
                {
                    "notice_type": "friend_recall",
                    "user_id": self._coerce_numeric(message.conversation.id),
                    "message_id": message_id,
                }
            )
        return self._ok(deleted)

    async def _get_media_file(self, params: dict[str, Any], *, media_type: str) -> dict[str, Any]:
        file = str(params.get("file") or "")
        if not file:
            return self._failed("file is required", retcode=1400)
        media = await self._store.get_media(file)
        if media is None and self._looks_like_direct_media_ref(file):
            media = {"file": file, "url": file if file.startswith(("http://", "https://")) else None}
        if media is None:
            return self._failed(f"{media_type} not found", retcode=1404)
        file_ref = media.get("file") or media.get("url") or media.get("path") or file
        data = {
            "file": file_ref,
            "url": media.get("url"),
            "file_size": media.get("file_size") or media.get("size"),
            "file_name": media.get("file_name") or str(file_ref).split("/")[-1].split("\\")[-1],
        }
        return self._ok(data)

    async def _set_friend_add_request(self, params: dict[str, Any]) -> dict[str, Any]:
        flag = str(params.get("flag") or "")
        item = await self._store.resolve_friend_request(
            flag,
            approve=bool(params.get("approve", True)),
            remark=params.get("remark"),
        )
        if item is None:
            return self._failed("friend request not found", retcode=1404)
        await self._flush_store()
        if item.get("approve"):
            await self._publish_notice({"notice_type": "friend_add", "user_id": item.get("user_id")})
        return self._ok(None)

    async def _set_group_add_request(self, params: dict[str, Any]) -> dict[str, Any]:
        flag = str(params.get("flag") or "")
        item = await self._store.resolve_group_request(
            flag,
            approve=bool(params.get("approve", True)),
            reason=params.get("reason"),
        )
        if item is None:
            return self._failed("group request not found", retcode=1404)
        await self._flush_store()
        if item.get("approve"):
            await self._publish_notice(
                {
                    "notice_type": "group_increase",
                    "sub_type": "invite" if item.get("sub_type") == "invite" else "approve",
                    "group_id": item.get("group_id"),
                    "user_id": item.get("user_id"),
                    "operator_id": self._store.bot_user_id,
                }
            )
        return self._ok(None)

    async def _set_msg_emoji_like(self, params: dict[str, Any]) -> dict[str, Any]:
        message_id = int(params.get("message_id") or 0)
        emoji_id = str(params.get("emoji_id") or params.get("emojiId") or "")
        message = self._store.get_msg(message_id)
        if message is None:
            return self._failed("message not found", retcode=1404)
        if message.conversation.kind != "group":
            return self._failed("set_msg_emoji_like only supports group messages in local strict mode", retcode=1400)
        user_id = str(params.get("user_id") or self._store.bot_user_id)
        enabled = bool(params.get("set", True))
        if enabled:
            reaction = await self._store.put_reaction(
                {
                    "message_id": message_id,
                    "emoji_id": emoji_id,
                    "user_id": user_id,
                    "group_id": self._coerce_numeric(message.conversation.id),
                }
            )
        else:
            await self._store.remove_reaction(message_id, emoji_id, user_id)
            reaction = {"message_id": message_id, "emoji_id": self._coerce_numeric(emoji_id), "user_id": self._coerce_numeric(user_id)}
        await self._flush_store()
        await self._publish_notice(
            {
                "notice_type": "message_reaction",
                "sub_type": "set" if enabled else "unset",
                "message_id": message_id,
                "emoji_id": self._coerce_numeric(emoji_id),
                "user_id": self._coerce_numeric(user_id),
                "group_id": self._coerce_numeric(message.conversation.id),
            }
        )
        return self._ok(reaction)

    async def _dispatch_group_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        group_id = str(params.get("group_id") or "")
        if action == "get_group_shut_list":
            return self._ok(self._store.group_shut_list(group_id))
        if action == "get_group_honor_info":
            return self._ok({"group_id": self._coerce_numeric(group_id), "current_talkative": None, "talkative_list": [], "performer_list": []})
        if action == "get_essence_msg_list":
            return self._ok([])
        if action in {"set_essence_msg", "delete_essence_msg"}:
            return self._ok(None)
        if action == "_get_group_notice":
            return self._ok([])
        if action == "_send_group_notice":
            notice = {
                "notice_id": f"local_notice_{int(time.time())}",
                "sender_id": self._store.bot_user_id,
                "publisher_time": int(time.time()),
                "message": {"text": params.get("content") or ""},
            }
            return self._ok(notice)
        if action == "group_poke":
            await self._publish_notice(
                {
                    "notice_type": "notify",
                    "sub_type": "poke",
                    "group_id": self._coerce_numeric(group_id),
                    "user_id": self._store.bot_user_id,
                    "target_id": params.get("user_id"),
                }
            )
            return self._ok(None)
        if action == "set_group_name":
            group = self._store.update_group_data(group_id, {"group_name": str(params.get("group_name") or "")})
            await self._flush_store()
            return self._ok(None) if group else self._failed("group not found", retcode=1404)
        if action == "set_group_remark":
            group = self._store.update_group_data(group_id, {"remark_name": str(params.get("remark") or "")})
            await self._flush_store()
            return self._ok(None) if group else self._failed("group not found", retcode=1404)
        if action == "set_group_whole_ban":
            enabled = bool(params.get("enable", True))
            group = self._store.update_group_data(
                group_id,
                {"shut_up_all_timestamp": -1 if enabled else 0},
            )
            await self._flush_store()
            await self._publish_notice(
                {
                    "notice_type": "group_ban",
                    "sub_type": "ban" if enabled else "lift_ban",
                    "group_id": self._coerce_numeric(group_id),
                    "user_id": 0,
                    "operator_id": self._store.bot_user_id,
                    "duration": -1 if enabled else 0,
                }
            )
            return self._ok(None) if group else self._failed("group not found", retcode=1404)
        if action == "set_group_admin":
            role = "admin" if bool(params.get("enable", True)) else "member"
            member = self._store.update_group_member_data(group_id, params.get("user_id"), {"role": role})
            await self._flush_store()
            if member:
                await self._publish_notice(
                    {
                        "notice_type": "group_admin",
                        "sub_type": "set" if role == "admin" else "unset",
                        "group_id": self._coerce_numeric(group_id),
                        "user_id": params.get("user_id"),
                    }
                )
                return self._ok(None)
            return self._failed("group member not found", retcode=1404)
        if action == "set_group_card":
            old = self._store.group_member_info(group_id, params.get("user_id")) or {}
            member = self._store.update_group_member_data(group_id, params.get("user_id"), {"card": str(params.get("card") or "")})
            await self._flush_store()
            if member:
                await self._publish_notice(
                    {
                        "notice_type": "group_card",
                        "group_id": self._coerce_numeric(group_id),
                        "user_id": params.get("user_id"),
                        "card_old": old.get("card") or "",
                        "card_new": member.get("card") or "",
                    }
                )
                return self._ok(None)
            return self._failed("group member not found", retcode=1404)
        if action == "set_group_ban":
            duration = int(params.get("duration") or 0)
            member = self._store.update_group_member_data(
                group_id,
                params.get("user_id"),
                {"shut_up_timestamp": int(time.time()) + duration if duration > 0 else 0},
            )
            await self._flush_store()
            if member:
                await self._publish_notice(
                    {
                        "notice_type": "group_ban",
                        "sub_type": "ban" if duration > 0 else "lift_ban",
                        "group_id": self._coerce_numeric(group_id),
                        "user_id": params.get("user_id"),
                        "operator_id": self._store.bot_user_id,
                        "duration": duration,
                    }
                )
                return self._ok(None)
            return self._failed("group member not found", retcode=1404)
        if action in {"set_group_kick", "batch_delete_group_member"}:
            user_ids = params.get("user_id_list") if action == "batch_delete_group_member" else [params.get("user_id")]
            removed_any = False
            for user_id in user_ids or []:
                if await self._store.remove_group_member(group_id, str(user_id)):
                    removed_any = True
                    await self._publish_notice(
                        {
                            "notice_type": "group_decrease",
                            "sub_type": "kick",
                            "group_id": self._coerce_numeric(group_id),
                            "user_id": user_id,
                            "operator_id": self._store.bot_user_id,
                        }
                    )
            await self._flush_store()
            return self._ok(None) if removed_any else self._failed("group member not found", retcode=1404)
        if action == "set_group_special_title":
            member = self._store.update_group_member_data(group_id, params.get("user_id"), {"title": str(params.get("special_title") or "")})
            await self._flush_store()
            if member:
                await self._publish_notice(
                    {
                        "notice_type": "group_title",
                        "sub_type": "title",
                        "group_id": self._coerce_numeric(group_id),
                        "user_id": params.get("user_id"),
                        "title": member.get("title") or "",
                    }
                )
                return self._ok(None)
            return self._failed("group member not found", retcode=1404)
        if action == "set_group_leave":
            await self._publish_notice(
                {
                    "notice_type": "group_decrease",
                    "sub_type": "leave",
                    "group_id": self._coerce_numeric(group_id),
                    "user_id": self._store.bot_user_id,
                    "operator_id": self._store.bot_user_id,
                }
            )
            return self._ok(None)
        return self._failed("local adapter does not support this group action")

    async def _publish_request(self, event: dict[str, Any]) -> None:
        event["post_type"] = "request"
        await self.ingest_event(event)

    async def _publish_notice(self, event: dict[str, Any]) -> None:
        event["post_type"] = "notice"
        await self.ingest_event(event)
        await self._hub.broadcast("notice.created", {"event": event})

    async def _flush_store(self) -> None:
        flush = getattr(self._store, "flush", None)
        if callable(flush):
            result = flush()
            if asyncio.iscoroutine(result):
                await result

    def _record_packet(self, event: dict[str, Any]) -> None:
        if self._packet_callback is None:
            return
        try:
            self._packet_callback(dict(event))
        except Exception as exc:
            self._logger.warning("local adapter packet callback failed", error=str(exc))

    @staticmethod
    def _coerce_numeric(value: Any) -> int | str:
        text = str(value or "")
        return int(text) if text.isdigit() else text

    @staticmethod
    def _looks_like_direct_media_ref(value: str) -> bool:
        if value.startswith(("http://", "https://", "base64://", "file://")):
            return True
        try:
            return Path(value).expanduser().is_file()
        except OSError:
            return False

    def _event_from_message_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        conversation = self._conversation_from_payload(data)
        sender = data.get("sender") if isinstance(data.get("sender"), dict) else {}
        user_id = sender.get("user_id") or conversation.id
        segments = data.get("segments")
        if segments is None:
            segments = self._store.normalize_message_payload(str(data.get("message") or ""))
        else:
            segments = self._store.normalize_message_payload(segments)
        raw_message = self._store.raw_from_segments(segments)
        event: dict[str, Any] = {
            "time": int(data.get("timestamp") or time.time()),
            "self_id": self._store.bot_user_id,
            "post_type": "message",
            "message_type": conversation.kind,
            "sub_type": "friend" if conversation.kind == "private" else "normal",
            "message_id": data.get("message_id") or self._store.next_message_id(),
            "user_id": int(user_id) if str(user_id).isdigit() else user_id,
            "message": segments,
            "raw_message": raw_message,
            "font": 0,
            "sender": {
                "user_id": int(user_id) if str(user_id).isdigit() else user_id,
                "nickname": sender.get("nickname") or sender.get("card") or f"QQ:{user_id}",
                "card": sender.get("card") or "",
                **{k: v for k, v in sender.items() if k not in {"user_id", "nickname", "card"}},
            },
        }
        if conversation.kind == "group":
            event["group_id"] = int(conversation.id) if conversation.id.isdigit() else conversation.id
        else:
            event["target_id"] = self._store.bot_user_id
        conversation_payload = data.get("conversation")
        if isinstance(conversation_payload, dict) and conversation_payload.get("name"):
            event["_local_conversation_name"] = str(conversation_payload.get("name") or "")
        if bool(data.get("skip_ai_reply", False)):
            event["_neobot_skip_ai_reply"] = True
        return event

    @staticmethod
    def _conversation_from_payload(data: dict[str, Any]) -> ConversationRef:
        conversation = data.get("conversation")
        if not isinstance(conversation, dict):
            raise ValueError("conversation is required")
        kind = str(conversation.get("kind") or "")
        if kind not in {"private", "group"}:
            raise ValueError("conversation.kind must be private or group")
        conversation_id = str(conversation.get("id") or "")
        if not conversation_id:
            raise ValueError("conversation.id is required")
        return ConversationRef(kind=kind, id=conversation_id)

    @staticmethod
    def _conversation_name_from_event(event: dict[str, Any]) -> str:
        name = event.get("_local_conversation_name")
        return str(name or "")

    @staticmethod
    def _ok(data: Any) -> dict[str, Any]:
        return {"status": "ok", "retcode": 0, "message": "", "wording": "", "data": data}

    @staticmethod
    def _failed(message: str, *, retcode: int = 1404) -> dict[str, Any]:
        return {
            "status": "failed",
            "retcode": retcode,
            "message": message,
            "wording": message,
            "data": None,
        }
