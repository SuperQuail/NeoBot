"""弹幕历史、回复意愿、发送与失败冷却。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Any

from neobot_app.bilibili._compat import call_client
from neobot_app.bilibili.live_parts.constants import (
    _DANMU_STALE_SECONDS,
    _MAX_HISTORY,
    _SEND_FAIL_COOLDOWN_SECONDS,
)
from neobot_app.bilibili.live_parts.helpers import _to_int


class _ReplyMixin:
    """弹幕落历史、按意愿决定是否回复、发弹幕与冷却。"""

    async def _handle_danmu(self, room_id: str, danmu: dict[str, Any]) -> None:
        room_id = str(room_id)
        self._record_history(room_id, danmu)
        _uid = _to_int(danmu.get("uid"))
        if _uid and _uid not in self._user_archive_seen:
            task = asyncio.create_task(
                self._ensure_user_archive(_uid, str(danmu.get("name") or ""))
            )
            self._user_memory_tasks.add(task)
            task.add_done_callback(self._user_memory_tasks.discard)
        recv_at = float(danmu.get("recv_at") or 0.0)
        if recv_at and time.monotonic() - recv_at > _DANMU_STALE_SECONDS:
            self._logger.debug(
                f"B站直播弹幕排队超过 {_DANMU_STALE_SECONDS:.0f} 秒，跳过自动回复：房间 {room_id}"
            )
            return
        lock = self._reply_locks.get(room_id)
        if lock is None:
            lock = self._reply_locks[room_id] = asyncio.Lock()
        async with lock:
            await self._process_danmu(room_id, danmu)

    async def _process_danmu(self, room_id: str, danmu: dict[str, Any]) -> None:
        room = self._rooms.get(room_id)
        if room is None or not room.get("auto_reply", True):
            return
        if self._provider is None:
            return
        client = self._get_client()
        if client is None:
            return
        # 只读缓存：client.my_uid 未缓存时会打网络接口，不能出现在弹幕热路径上。
        my_uid = self._my_uid
        if my_uid and _to_int(danmu.get("uid")) == my_uid:
            return
        text = str(danmu.get("text") or "")
        if not self._should_reply(room_id, danmu, text, my_uid):
            return
        if not self._reply_allowed(room_id):
            return
        if not await self.is_live(_to_int(room_id)):
            return
        result = await self._generate_reply(
            text, _to_int(room_id), str(danmu.get("name") or ""),
            _to_int(danmu.get("uid")),
        )
        replies = result.segments or ([result.text] if result.text else [])
        if not replies:
            return
        if self._screenshot_replies:
            await self._save_reply_frame(room_id)
        target_uid = _to_int(result.reply_to)
        target_name = ""
        if target_uid:
            for item in reversed(self.get_history(_to_int(room_id), _MAX_HISTORY)):
                if _to_int(item.get("uid")) == target_uid:
                    target_name = str(item.get("name") or "")
                    break
        for reply in replies:
            if not await self._post_danmaku(
                client, _to_int(room_id), reply,
                action="自动回复", reply_mid=target_uid, reply_uname=target_name,
            ):
                return
        self._record_reply(room_id)
        self._logger.info(
            f"B站直播已自动回复：房间 {room_id}，{len(replies)} 段，"
            f"共 {sum(len(item) for item in replies)} 字，"
            f"回复给 {target_uid or '无'}"
        )

    def _record_history(self, room_id: str, danmu: dict[str, Any]) -> None:
        text = str(danmu.get("text") or "").strip()
        if not text:
            return
        my_uid = self._my_uid
        entry = {
            "uid": _to_int(danmu.get("uid")),
            "name": str(danmu.get("name") or ""),
            "text": text,
            "ts": time.time(),
            "time": datetime.now().astimezone().strftime("%H:%M:%S"),
            "at_me": bool(my_uid and _to_int(danmu.get("reply_mid")) == my_uid),
        }
        room_history = self._history.get(room_id)
        if room_history is None:
            room_history = self._history[room_id] = deque(maxlen=_MAX_HISTORY)
        room_history.append(entry)
        if self._summary_every:
            self._summary_counts[room_id] += 1
            if self._summary_counts[room_id] >= self._summary_every:
                self._summary_counts[room_id] = 0
                task = asyncio.create_task(self._summarize_live(room_id))
                self._summary_tasks.add(task)
                task.add_done_callback(self._summary_tasks.discard)

    async def _post_danmaku(
        self, client: Any, room_id: int, text: str, *,
        action: str, reply_mid: int = 0, reply_uname: str = "",
    ) -> bool:
        try:
            if reply_mid or reply_uname:
                sent = await call_client(
                    client.send_danmaku, room_id, text,
                    reply_mid=reply_mid, reply_uname=reply_uname,
                )
            else:
                sent = await call_client(client.send_danmaku, room_id, text)
        except Exception as exc:
            self._logger.warning(
                f"B站直播{action}发送失败：房间 {room_id}，"
                f"错误 {type(exc).__name__}: {exc}"
            )
            self._record_send_failure(room_id)
            return False
        if not sent:
            self._logger.warning(f"B站直播{action}发送失败：房间 {room_id}，接口返回失败")
            self._record_send_failure(room_id)
            return False
        self._record_history(
            str(room_id), {"uid": 0, "name": self._bot_name or "你", "text": text}
        )
        return True

    def _known_bot_names(self) -> tuple[str, ...]:
        """QQ 昵称 + B站账号昵称；后者用于识别 B站弹幕里的 @。"""
        names = [self._bot_name, *self._mention_names]
        service = self._service
        status = getattr(service, "status", None)
        if callable(status):
            try:
                uname = str((status() or {}).get("uname") or "").strip()
                if uname:
                    names.append(uname)
            except Exception:
                pass
        return tuple(name for name in names if name)

    def _should_reply(
        self, room_id: str, danmu: dict[str, Any], text: str, my_uid: int = 0
    ) -> bool:
        """直播间回复意愿：和 QQ 群聊同一套 manager/系数/@必回规则。"""
        if not str(text or "").strip():
            return False
        willing = self._willing_service
        if willing is None:
            return True
        try:
            history = self.get_history(_to_int(room_id), 20)
            observed = tuple(
                f"{item.get('name') or '观众'}: {item.get('text') or ''}"
                for item in history
                if str(item.get("text") or "").strip()
            )
            at_me = bool(
                my_uid and _to_int(danmu.get("reply_mid")) == my_uid
            )
            decision = willing.evaluate_live(
                room_id=_to_int(room_id),
                uid=_to_int(danmu.get("uid")),
                name=str(danmu.get("name") or ""),
                text=text,
                observed_messages=observed,
                extra_bot_names=self._known_bot_names(),
                base_probability=self._reply_chance,
                mentioned=at_me or None,
            )
        except Exception as exc:
            self._logger.warning(
                f"直播回复意愿计算失败，按不回复处理：房间 {room_id}，"
                f"错误 {type(exc).__name__}: {exc}"
            )
            return False
        self._logger.info(
            f"直播回复意愿：房间 {room_id}，概率 {decision.probability:.3f}，"
            f"判定{'回复' if decision.should_reply else '不回复'}，"
            f"依据：{'；'.join(decision.reasons)}"
        )
        return bool(decision.should_reply)

    def get_live_willingness(self, room_id: int = 0) -> dict[str, Any]:
        """查看直播间意愿系数（WillingService 的 live:<room> 会话系数）。"""
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        rid = _to_int(room_id)
        if rid > 0:
            return {
                "room_id": rid,
                "coefficient": self._willing_service.get_runtime_conversation_coefficient(
                    f"live:{rid}"
                ),
            }
        summary = self._willing_service.get_runtime_config_summary()
        return {"ok": True, "summary": summary}

    def set_live_willingness(self, room_id: int, value: float) -> dict[str, Any]:
        """设置直播间意愿系数 0.0~1.0（WillingService 的 live:<room> 会话系数）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        coefficient = max(0.0, min(1.0, float(value)))
        self._willing_service.set_runtime_conversation_coefficient(
            f"live:{rid}", coefficient
        )
        return {"ok": True, "room_id": rid, "coefficient": coefficient}

    def remove_live_willingness(self, room_id: int) -> dict[str, Any]:
        rid = _to_int(room_id)
        if self._willing_service is None:
            return {"ok": False, "error": "willing_service 未配置"}
        self._willing_service.remove_runtime_conversation_coefficient(f"live:{rid}")
        return {"ok": True, "room_id": rid}

    def _mentions_bot(self, text: str) -> bool:
        lowered = text.lower()
        return any(name.lower() in lowered for name in self._known_bot_names())

    def _reply_allowed(self, room_id: str) -> bool:
        now = time.monotonic()
        if now < self._send_fail_until.get(str(room_id), 0.0):
            return False
        last = self._last_reply_at.get(room_id)
        return last is None or now - last >= self._cooldown

    def _record_send_failure(self, room_id: Any) -> None:
        """发送失败后的短冷却：冷却期内不再为这个房间生成新回复。"""
        # _post_danmaku 拿到的是 int 房间号，_process_danmu 用的是 str key，统一成 str。
        self._send_fail_until[str(room_id)] = time.monotonic() + _SEND_FAIL_COOLDOWN_SECONDS

    def _record_reply(self, room_id: str) -> None:
        self._last_reply_at[room_id] = time.monotonic()
        self._send_fail_until.pop(str(room_id), None)

    def _record_live_flow(self, room_id: int, system: str, messages: list[dict]) -> None:
        registry = self._flow_registry
        if registry is None:
            return
        try:
            key = f"bilibili_live:{room_id}"
            model = str(getattr(self._provider, "model", "") or "")
            registry.record_prompt(
                key,
                system_prompt=system,
                model=model,
                conversation_kind="bilibili_live",
                conversation_id=str(room_id),
            )
            registry.record_request(key, messages=messages, model=model, iteration=1)
        except Exception:
            pass
