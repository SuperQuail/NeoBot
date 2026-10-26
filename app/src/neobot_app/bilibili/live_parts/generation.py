"""提示词组装、模型调用与直播间/观众档案记忆。"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from neobot_app.bilibili._compat import get_field
from neobot_app.bilibili.live_parts.constants import (
    _LIVE_ROOM_ARCHIVE_PREFIX,
    _LIVE_USER_ARCHIVE_PREFIX,
    _MAX_HISTORY,
)
from neobot_app.bilibili.live_parts.helpers import _to_int
from neobot_app.bilibili.prompts import (
    LiveDanmakuContext,
    build_live_danmaku_prompt,
    build_live_observation_prompt,
    build_live_scheduled_prompt,
)
from neobot_app.bilibili.tool_reply import ToolReply, run_tool_reply


class _GenerationMixin:
    """组装提示词、调模型，并维护直播间/观众长期记忆。"""

    async def _load_live_summaries(self) -> None:
        """启动时恢复直播间群档案；复用 QQ 的 group_summary/group_profile。"""
        if self._archive_service is None:
            return
        for room_id in list(self._rooms):
            key = _LIVE_ROOM_ARCHIVE_PREFIX + str(room_id)
            for table in ("group_summary", "group_profile"):
                try:
                    item = await self._archive_service.get(table, key)
                    value = str(getattr(item, "value", "") or "").strip()
                    if value:
                        self._room_memory[str(room_id)] = value
                        break
                except Exception as exc:
                    self._logger.debug(
                        f"B站直播档案恢复失败：房间 {room_id}，表 {table}，"
                        f"错误 {type(exc).__name__}: {exc}"
                    )

    async def _ensure_user_archive(self, uid: int, name: str) -> None:
        """每个 B 站观众在 user_profile 里都有对应档案；首次出现时建最小条目。"""
        if self._archive_service is None or uid <= 0 or uid in self._user_archive_seen:
            return
        self._user_archive_seen.add(uid)
        key = _LIVE_USER_ARCHIVE_PREFIX + str(uid)
        try:
            async with self._archive_semaphore:
                item = await self._archive_service.get("user_profile", key)
                if str(getattr(item, "value", "") or "").strip():
                    return
                await self._archive_service.set(
                    "user_profile",
                    key,
                    f"B站昵称：{name or '观众'}\nB站UID：{uid}",
                    ["bilibili_live"],
                )
        except Exception as exc:
            self._logger.debug(f"B站直播观众档案初始化失败：UID {uid}，错误 {type(exc).__name__}: {exc}")

    async def _load_user_memory(self, uid: int) -> str:
        """读取观众在 QQ 侧 user_summary/user_profile 的对应档案。"""
        if self._archive_service is None or uid <= 0:
            return ""
        if uid in self._user_memory:
            return self._user_memory[uid]
        key = _LIVE_USER_ARCHIVE_PREFIX + str(uid)
        value = ""
        for table in ("user_summary", "user_profile"):
            try:
                item = await self._archive_service.get(table, key)
                text = str(getattr(item, "value", "") or "").strip()
                if text:
                    value = text
                    break
            except Exception as exc:
                self._logger.debug(
                    f"B站直播观众档案读取失败：UID {uid}，表 {table}，"
                    f"错误 {type(exc).__name__}: {exc}"
                )
        self._user_memory[uid] = value
        return value

    async def _summarize_live(self, room_id: str) -> None:
        """每 N 条弹幕总结一次；只保留话题/梗/人和事件，不逐条复述。"""
        try:
            lines = self.format_history(_to_int(room_id), self._summary_every)
            if not lines:
                return
            summary = await self._chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是直播弹幕总结器。把弹幕浓缩成一段直播记忆，"
                            "只保留话题、梗、反复出现的人/事件和约定；不要逐条复述，200 字以内。"
                        ),
                    },
                    {"role": "user", "content": lines},
                ],
                error_label="B站直播弹幕总结失败",
            )
            summary = summary.strip()
            if not summary:
                return
            self._room_memory[room_id] = summary[:2000]
            if self._archive_service is not None:
                try:
                    await self._archive_service.set(
                        "group_summary",
                        _LIVE_ROOM_ARCHIVE_PREFIX + str(room_id),
                        summary[:2000],
                        ["bilibili_live"],
                    )
                except Exception as exc:
                    self._logger.debug(f"B站直播总结写档案失败：{type(exc).__name__}: {exc}")
            self._logger.info(f"B站直播弹幕已总结：房间 {room_id}，摘要 {len(summary)} 字")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                f"B站直播弹幕总结失败：房间 {room_id}，错误 {type(exc).__name__}: {exc}"
            )

    async def _live_asr_context(self, room_id: int) -> str:
        """按房间 ASR 开关截取最近 10 秒直播语音；失败只记日志。"""
        if self._asr_service is None:
            return ""
        room = self._rooms.get(str(_to_int(room_id))) or {}
        if not bool(room.get("asr", self._asr_default_enabled)):
            return ""
        try:
            result = await self.transcribe(_to_int(room_id), seconds=10)
        except Exception as exc:
            self._logger.debug(
                f"B站直播 ASR 上下文读取失败：房间 {room_id}，错误 {type(exc).__name__}: {exc}"
            )
            return ""
        if not result.get("ok"):
            return ""
        text = str(result.get("text") or "").strip()
        return text[:1200]

    def _live_persona(self) -> str:
        """读取 custom/prompts.toml 的 [live_chat]；为空则回退 QQ 风格默认提示词。"""
        if self._prompt_store is None:
            return ""
        try:
            from neobot_app.prompt.store import get_template_value

            return str(get_template_value(self._prompt_store, "live_chat") or "").strip()
        except Exception:
            return ""

    async def _generate_observation(self, room_id: int) -> Any:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            text="",
            recent_history=self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            frame_context=await self.frame_context(room_id),
        )
        system, content = build_live_observation_prompt(ctx, self._live_persona())
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            return await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
                allow_reply_to=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"B站直播主动观察生成失败：{type(exc).__name__}: {exc}")
            return None

    async def _auto_look_loop(self) -> None:
        while self._running:
            await asyncio.sleep(30)
            if not self._auto_look_enabled:
                continue
            now = time.monotonic()
            if now - self._last_auto_look < self._auto_look_interval_minutes * 60:
                continue
            self._last_auto_look = now
            for room_id, room in list(self._rooms.items()):
                if not room.get("auto_reply", True):
                    continue
                if not await self.is_live(_to_int(room_id)):
                    continue
                try:
                    result = await self._generate_observation(_to_int(room_id))
                    segments = (
                        result.segments or ([result.text] if result.text else [])
                    ) if result is not None else []
                    if not segments:
                        continue
                    client = self._get_client()
                    if client is None:
                        continue
                    for text in segments:
                        await self._post_danmaku(
                            client, _to_int(room_id), text, action="主动观察"
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._logger.warning(
                        f"B站直播主动观察失败：房间 {room_id}，"
                        f"错误 {type(exc).__name__}: {exc}"
                    )

    async def _generate_reply(
        self, text: str, room_id: int, user_name: str = "", user_id: int = 0
    ) -> Any:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            viewer_name=user_name,
            text=text,
            recent_history=self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            viewer_memory=await self._load_user_memory(user_id),
            frame_context="",
        )
        system, content = build_live_danmaku_prompt(ctx, self._live_persona())
        asr_context = await self._live_asr_context(room_id)
        if asr_context:
            content += f"\n<直播语音>{asr_context}</直播语音>"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            result = await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
                allow_reply_to=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"B站直播回复生成失败：{type(exc).__name__}: {exc}")
            return ToolReply()
        return result

    async def _generate_schedule_danmaku(
        self, prompt: str, context: str, room_id: int
    ) -> list[str]:
        room = self._rooms.get(str(room_id)) or {}
        ctx = LiveDanmakuContext(
            bot_name=self._bot_name,
            bot_data=self._bot_data,
            room_name=str(room.get("name") or ""),
            text=prompt,
            recent_history=context or self.format_history(room_id, _MAX_HISTORY),
            room_memory=self._room_memory.get(str(room_id), ""),
            frame_context="",
            scheduled_prompt=prompt,
        )
        system, content = build_live_scheduled_prompt(ctx, self._live_persona())
        asr_context = await self._live_asr_context(room_id)
        if asr_context:
            content += f"\n<直播语音>{asr_context}</直播语音>"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        self._record_live_flow(room_id, system, messages)
        try:
            result = await run_tool_reply(
                self._provider,
                system,
                content,
                max_chars=self._max_reply_chars,
                split=True,
                timeout=90.0,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"B站直播定时弹幕生成失败：{type(exc).__name__}: {exc}")
            return []
        return result.segments or ([result.text] if result.text else [])

    async def _chat(self, messages: list[dict[str, str]], *, error_label: str) -> str:
        if self._provider is None:
            return ""
        try:
            response = self._provider.chat(messages)
            if inspect.isawaitable(response):
                response = await response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"{error_label}：{type(exc).__name__}: {exc}")
            return ""
        content = response.get("content", "") if isinstance(response, dict) else get_field(response, "content", "")
        return str(content or "")
