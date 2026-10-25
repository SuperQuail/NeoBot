"""B站私信轮询回复（默认关闭）。

复用原 private_monitor 的会话轮询语义，但直接接 reply_engine，不再经过
ReplyOrchestrator：每 poll_interval_seconds（默认 1800s）扫一遍最近
session_check_count（默认 50）个会话，对每个会话里新到的、非自己的文本消息
生成一次回复并调用 client.send_message。每轮最多回复 max_replies_per_poll
（默认 50）个会话，没轮到的下一轮继续；每个会话每轮最多回一次（多条新消息
合并进上下文），失败按指数退避。

已回复的 msg_key 会落盘到 data_dir/bilibili/private_replies.json（沿用
comment_monitor 的状态文件格式），进程重启后不会把旧私信再回一遍；data_dir
为空时只在内存里去重（测试/纯内存用法）。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neobot_app.bilibili._compat import (
    RecentIds,
    bilibili_config,
    call_client,
    get_field,
    resolve_client,
)
from neobot_app.bilibili.prompts import PrivateMessageContext
from neobot_app.utils.atomic import atomic_write_text
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.private_monitor")

_MAX_BACKOFF_SECONDS = 3600.0
#: 会话历史注入提示词的最多条数。
_HISTORY_LIMIT = 20


@dataclass
class PrivateMessageEvent:
    """一条新私信。"""

    talker_id: int
    sender_uid: int
    text: str
    timestamp: int
    msg_key: str


class BilibiliPrivateMonitor:
    """B站私信轮询监控器。"""

    def __init__(
        self,
        client: Any = None,
        engine: Any = None,
        *,
        enabled: bool = False,
        poll_interval_seconds: float = 1800.0,
        max_replies_per_poll: int = 50,
        reply_cooldown_seconds: float = 60.0,
        session_check_count: int = 50,
        message_size: int = 20,
        max_seen: int = 2000,
        data_dir: Path | None = None,
    ) -> None:
        self._client = client
        self._engine = engine
        self._enabled = bool(enabled)
        self._poll_interval = max(1.0, float(poll_interval_seconds or 1800.0))
        self._max_per_poll = max(1, int(max_replies_per_poll or 1))
        self._cooldown = max(0.0, float(reply_cooldown_seconds or 0.0))
        self._session_check_count = max(1, int(session_check_count or 50))
        self._message_size = max(1, int(message_size or 20))
        self._processed = RecentIds(max_seen)
        #: 已回复去重落盘位置；data_dir 为空时不落盘（测试/纯内存用法）。
        self._state_path = (
            Path(data_dir) / "bilibili" / "private_replies.json"
            if data_dir is not None
            else None
        )
        self._load_state()
        #: 已知没处理完的会话（发送失败/异常/本轮被截断），供 status 摘要。
        self._pending_talkers: set[int] = set()
        self._processed_count = 0
        self._last_reply_at: dict[int, float] = {}
        self._failures = 0
        self._next_poll_at = 0.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_error = ""

    @classmethod
    def from_config(
        cls,
        client: Any,
        engine: Any,
        config: Any,
        *,
        data_dir: Path | None = None,
        **overrides: Any,
    ) -> "BilibiliPrivateMonitor":
        cfg = bilibili_config(config)
        values: dict[str, Any] = {
            "enabled": bool(getattr(cfg, "private_message_enabled", False)),
            "poll_interval_seconds": float(
                getattr(cfg, "poll_interval_seconds", 1800) or 1800
            ),
            "max_replies_per_poll": int(
                getattr(cfg, "max_replies_per_poll", 50) or 50
            ),
            "reply_cooldown_seconds": float(
                getattr(cfg, "reply_cooldown_seconds", 60.0) or 0.0
            ),
            "data_dir": data_dir,
        }
        values.update(overrides)
        return cls(client, engine, **values)

    # ── 生命周期 ──

    async def start(self) -> None:
        if not self._enabled:
            logger.info("B站私信回复未启用，跳过启动")
            return
        if self._task is not None and not self._task.done():
            return
        self._load_state()
        self._running = True
        self._next_poll_at = 0.0
        self._task = asyncio.create_task(self._loop())
        logger.info(f"B站私信监控器已启动，轮询间隔 {self._poll_interval} 秒")

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._save_state()
        logger.info("B站私信监控器已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def next_poll_interval(self) -> float:
        if self._failures <= 0:
            return self._poll_interval
        return min(self._poll_interval * (2 ** self._failures), _MAX_BACKOFF_SECONDS)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "running": self._running,
            "failures": self._failures,
            "next_poll_interval_seconds": self.next_poll_interval,
            "last_error": self._last_error,
            "pending_sessions": len(self._pending_talkers),
            "processed_messages": self._processed_count,
        }

    # ── 去重状态 ──

    def _load_state(self) -> None:
        path = self._state_path
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(f"B站私信已回复记忆读取失败，按空状态启动：{path}")
            return
        for key in data.get("processed") or []:
            text = str(key or "").strip()
            if text:
                self._processed.add(text)

    def _save_state(self) -> None:
        path = self._state_path
        if path is None:
            return
        try:
            atomic_write_text(
                path,
                json.dumps(
                    {"version": 1, "processed": self._processed.keys()},
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning(f"B站私信已回复记忆保存失败：{path}（{type(exc).__name__}: {exc}）")

    # ── 轮询 ──

    async def _loop(self) -> None:
        while self._running:
            try:
                if time.monotonic() >= self._next_poll_at:
                    await self.poll_once()
                    self._next_poll_at = time.monotonic() + self.next_poll_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._failures += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("B站私信轮询异常")
                # 异常也要推进下一次轮询时间，否则循环会每秒重试、刷屏日志。
                self._next_poll_at = time.monotonic() + self.next_poll_interval
            await asyncio.sleep(1.0)

    async def poll_once(self) -> int:
        """轮询一次，返回本轮成功回复的会话数。"""
        if not self._enabled:
            return 0
        client = resolve_client(self._client)
        if client is None:
            return 0
        if self._engine is None or not getattr(self._engine, "available", False):
            return 0
        # 拉取成功就清掉历史失败计数：即使没有新私信，也算一次正常轮询，
        # 避免一次发送失败把退避永久顶在 1 小时。
        self._failures = 0
        self._last_error = ""
        try:
            sessions = await call_client(
                client.get_sessions, count=self._session_check_count
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"B站私信会话获取失败：{self._last_error}")
            return 0

        replied = 0
        session_list = list(sessions or [])
        for index, session in enumerate(session_list):
            if replied >= self._max_per_poll:
                # 没轮到的会话记入待处理摘要，下一轮继续（已回复的会被去重跳过）。
                logger.info(
                    f"B站私信本轮达到上限，剩余 {len(session_list) - index} 个会话留待下轮"
                )
                for rest in session_list[index:]:
                    rest_id = int(get_field(rest, "talker_id", 0) or 0)
                    if rest_id:
                        self._pending_talkers.add(rest_id)
                break
            talker_id = int(get_field(session, "talker_id", 0) or 0)
            if not talker_id or not self._cooldown_ok(talker_id):
                continue
            try:
                sent = await self._process_session(client, talker_id)
            except asyncio.CancelledError:
                # 取消时把正在处理的会话记回待处理，别让它静默消失。
                self._pending_talkers.add(talker_id)
                raise
            except Exception as exc:
                self._failures += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    f"B站私信处理异常（talker_id={talker_id}），已回池重试：{self._last_error}"
                )
                self._pending_talkers.add(talker_id)
                continue
            if sent:
                replied += 1
        return replied

    async def _process_session(self, client: Any, talker_id: int) -> bool:
        messages = await call_client(
            client.get_messages, talker_id, size=self._message_size
        )
        messages = list(messages or [])
        if not messages:
            self._pending_talkers.discard(talker_id)
            return False
        my_uid = int(getattr(client, "my_uid", 0) or 0)
        ordered = sorted(messages, key=lambda msg: int(get_field(msg, "timestamp", 0) or 0))
        pending: list[PrivateMessageEvent] = []
        for msg in ordered:
            event = _message_event(msg, talker_id, my_uid)
            if event is None or event.msg_key in self._processed:
                continue
            pending.append(event)
        if not pending:
            self._pending_talkers.discard(talker_id)
            return False
        latest = pending[-1]
        history = _history(ordered, my_uid)
        ctx = PrivateMessageContext(
            sender_uid=latest.sender_uid,
            history=history,
            current_message=latest.text,
        )
        text = await self._engine.generate_private_reply(ctx)
        if text is None:
            # 只有模型明确 skip/cancel 才返回 None；provider 异常由引擎抛出，
            # 这里不记 processed，下一轮会重新生成。
            self._mark_processed(pending)
            self._pending_talkers.discard(talker_id)
            return False
        sent = await call_client(client.send_message, latest.talker_id, text)
        if not sent:
            self._failures += 1
            self._pending_talkers.add(talker_id)
            logger.warning(f"B站私信发送失败（talker_id={talker_id}）")
            return False
        self._mark_processed(pending)
        self._pending_talkers.discard(talker_id)
        self._last_reply_at[talker_id] = time.monotonic()
        logger.info(f"B站私信已回复（talker_id={talker_id}，{len(text)} 字）")
        return True

    def _mark_processed(self, events: list[PrivateMessageEvent]) -> None:
        for event in events:
            if self._processed.add(event.msg_key):
                self._processed_count += 1
        self._save_state()

    def _cooldown_ok(self, talker_id: int) -> bool:
        if self._cooldown <= 0:
            return True
        last = self._last_reply_at.get(talker_id)
        if last is None:
            return True
        return time.monotonic() - last >= self._cooldown


def _message_event(msg: Any, talker_id: int, my_uid: int) -> PrivateMessageEvent | None:
    """把客户端消息对象转成事件；自己的消息/非文本消息返回 None。"""
    sender_uid = int(get_field(msg, "sender_uid", 0) or 0)
    if my_uid and sender_uid == my_uid:
        return None
    if bool(get_field(msg, "is_self", False)):
        return None
    msg_type = int(get_field(msg, "msg_type", 1) or 1)
    if msg_type != 1:
        return None
    text = _message_text(msg)
    if not text:
        return None
    timestamp = int(get_field(msg, "timestamp", 0) or 0)
    msg_key = str(get_field(msg, "msg_key", "") or "")
    if not msg_key:
        msg_key = f"{talker_id}:{sender_uid}:{timestamp}:{text[:20]}"
    return PrivateMessageEvent(
        talker_id=talker_id,
        sender_uid=sender_uid,
        text=text,
        timestamp=timestamp,
        msg_key=msg_key,
    )


def _message_text(msg: Any) -> str:
    """客户端优先用 .text 属性；dict/原始 content 走 JSON 解析兜底。"""
    value = get_field(msg, "text", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    content = get_field(msg, "content", "")
    if isinstance(content, dict):
        return str(content.get("content", "") or "").strip()
    raw = str(content or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(parsed, dict):
        return str(parsed.get("content", "") or "").strip()
    return raw


def _history(messages: list[Any], my_uid: int) -> list[dict]:
    history: list[dict] = []
    for msg in messages[-_HISTORY_LIMIT:]:
        sender_uid = int(get_field(msg, "sender_uid", 0) or 0)
        is_bot = bool(get_field(msg, "is_self", False)) or (
            my_uid and sender_uid == my_uid
        )
        history.append(
            {
                "role": "bot" if is_bot else "user",
                "content": _message_text(msg),
                "sender_uid": sender_uid,
                "sender_name": f"UID:{sender_uid}",
                "time": int(get_field(msg, "timestamp", 0) or 0),
            }
        )
    return history
