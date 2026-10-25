"""B站评论/@ 轮询回复。

默认关闭（config.bilibili.comment_reply_enabled=false）。开启后每
poll_interval_seconds（默认 1800s）检查一次「回复我的」与「@我的」通知，
只处理发给 bot 的评论：每轮最多回复 max_replies_per_poll 条（默认 50），
本轮没轮到的进待回复池（上限 1000）下一轮继续；按通知/评论去重、同一楼中楼
有回复冷却，接口失败按指数退避（上限 1 小时）。生成与发送分别走
reply_engine / client。

通知中心接口不支持游标：每路单次最多看 feed_limit 条（默认 20），超出部分
这一轮看不到，靠待回复池与后续轮询补齐；长期积压要调大 feed_limit。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from neobot_app.bilibili._compat import (
    RecentIds,
    bilibili_config,
    call_client,
    get_field,
    resolve_client,
)
from neobot_app.bilibili.prompts import CommentContext, CommentNode
from neobot_app.utils.atomic import atomic_write_text
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.comment_monitor")

#: reply_feed/at_feed 的 business_id -> 内容类型名，数值即评论区的 type，
#: 必须与 BilibiliClient.COMMENT_TYPES 一致（视频 1、番剧 11、专栏/opus 12、动态 17）。
BUSINESS_TYPES = {1: "视频", 11: "番剧", 12: "专栏", 17: "动态"}
_MAX_BACKOFF_SECONDS = 3600.0
#: 待回复池上限；满了以后新事件留到下一轮重新拉取，避免内存无界增长。
_PENDING_LIMIT = 1000


@dataclass
class CommentEvent:
    """一条待处理的 B站评论/@ 通知。"""

    source: str = "reply_feed"
    notification_id: int = 0
    oid: int = 0
    business_id: int = 1
    user_uid: int = 0
    user_name: str = ""
    content: str = ""
    ctime: int = 0
    root_id: int = 0
    parent_id: int = 0
    target_title: str = ""
    target_url: str = ""

    @property
    def target_type(self) -> str:
        return BUSINESS_TYPES.get(self.business_id, "动态")

    @property
    def comment_type(self) -> int:
        """回复时提交的评论区 type；未知 business_id 落回视频(1)，不要乱投分区。"""
        return self.business_id if self.business_id in BUSINESS_TYPES else 1

    @property
    def dedupe_key(self) -> str:
        # 同一条评论可能同时出现在「回复我的」和「@我的」两个通知流，按评论去重。
        return f"{self.oid}:{self.parent_id}"

    def to_context(self) -> CommentContext:
        node = CommentNode(
            rpid=self.parent_id,
            uid=self.user_uid,
            uname=self.user_name,
            content=self.content,
            ctime=self.ctime,
        )
        return CommentContext(
            target_oid=self.oid,
            target_type=self.target_type,
            business_id=self.business_id,
            target_title=self.target_title,
            target_url=self.target_url,
            comment_tree=[node],
            reply_target_rpid=self.parent_id,
            reply_root_rpid=self.root_id,
        )


def parse_feed_item(item: Any, source: str = "reply_feed") -> CommentEvent | None:
    """把 reply_feed / at_feed 的原始 item 转成事件；无法回复的条目返回 None。"""
    data = get_field(item, "item", None) or {}
    user = get_field(item, "user", None) or {}
    oid = int(get_field(data, "subject_id", 0) or 0)
    parent_id = int(get_field(data, "source_id", 0) or 0)
    root_raw = int(get_field(data, "root_id", 0) or 0)
    business_id = int(get_field(data, "business_id", 1) or 1)
    if source == "at_feed":
        # @ 通知没有 message；source_content 是触发 @ 的那条评论，content 未必存在。
        candidates = ("source_content", "content", "message")
    else:
        candidates = ("message", "source_content", "content")
    content = ""
    for key in candidates:
        content = str(get_field(data, key, "") or "").strip()
        if content:
            break
    if not oid or not parent_id or not content:
        return None
    return CommentEvent(
        source=source,
        notification_id=int(get_field(item, "id", 0) or 0),
        oid=oid,
        business_id=business_id,
        user_uid=int(get_field(user, "mid", 0) or 0),
        user_name=str(get_field(user, "nickname", "") or ""),
        content=content,
        # reply_feed 用 reply_time，at_feed 用 at_time。
        ctime=int(
            get_field(item, "reply_time", 0) or get_field(item, "at_time", 0) or 0
        ),
        root_id=root_raw or parent_id,
        parent_id=parent_id,
        target_title=str(
            get_field(data, "title", "") or get_field(data, "desc", "") or ""
        ),
        target_url=str(get_field(data, "uri", "") or ""),
    )


class BilibiliCommentMonitor:
    """「回复我的」+「@我的」轮询监控器。"""

    def __init__(
        self,
        client: Any = None,
        engine: Any = None,
        *,
        enabled: bool = False,
        poll_interval_seconds: float = 1800.0,
        max_replies_per_poll: int = 50,
        reply_cooldown_seconds: float = 60.0,
        feed_limit: int = 20,
        max_seen: int = 2000,
        data_dir: Path | None = None,
    ) -> None:
        # client 既可以是 BilibiliClient，也可以是 BilibiliService（每轮重新解析，
        # 登录状态在运行期会变）。
        self._client = client
        self._engine = engine
        self._enabled = bool(enabled)
        self._poll_interval = max(1.0, float(poll_interval_seconds or 1800.0))
        self._max_per_poll = max(1, int(max_replies_per_poll or 1))
        self._cooldown = max(0.0, float(reply_cooldown_seconds or 0.0))
        self._feed_limit = max(1, int(feed_limit or 20))
        self._processed = RecentIds(max_seen)
        # data_dir 为空时不落盘（测试/纯内存用法）；生产由 runtime 传 DATA_DIR。
        self._state_path = (
            Path(data_dir) / "bilibili" / "comment_replies.json"
            if data_dir is not None
            else None
        )
        self._load_state()
        #: 本轮没轮到的待回复事件，按 dedupe_key 去重，下一轮优先处理。
        self._pending: dict[str, CommentEvent] = {}
        self._last_reply_at: dict[str, float] = {}
        self._failures = 0
        self._next_poll_at = 0.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_error = ""

    @classmethod
    def from_config(
        cls, client: Any, engine: Any, config: Any, **overrides: Any
    ) -> "BilibiliCommentMonitor":
        """按 config.bilibili（或 BotConfig）构造；未配置的通知默认关闭。"""
        cfg = bilibili_config(config)
        values: dict[str, Any] = {
            "enabled": bool(getattr(cfg, "comment_reply_enabled", False)),
            "poll_interval_seconds": float(
                getattr(cfg, "poll_interval_seconds", 1800) or 1800
            ),
            "max_replies_per_poll": int(
                getattr(cfg, "max_replies_per_poll", 50) or 50
            ),
            "reply_cooldown_seconds": float(
                getattr(cfg, "reply_cooldown_seconds", 60.0) or 0.0
            ),
        }
        values.update(overrides)
        return cls(client, engine, **values)

    # ── 生命周期 ──

    async def start(self) -> None:
        if not self._enabled:
            logger.info("B站评论回复未启用，跳过启动")
            return
        if self._task is not None and not self._task.done():
            return
        self._load_state()
        self._running = True
        self._next_poll_at = 0.0
        self._task = asyncio.create_task(self._loop())
        logger.info(f"B站评论监控器已启动，轮询间隔 {self._poll_interval} 秒")

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
        logger.info("B站评论监控器已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def next_poll_interval(self) -> float:
        """含失败退避的实际轮询间隔（秒）。"""
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
            "pending": len(self._pending),
        }

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
                logger.exception("B站评论轮询异常")
                # 异常也要推进下一次轮询时间，否则循环会每秒重试、刷屏日志。
                self._next_poll_at = time.monotonic() + self.next_poll_interval
            await asyncio.sleep(1.0)

    def _load_state(self) -> None:
        path = self._state_path
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(f"B站评论已回复记忆读取失败，按空状态启动：{path}")
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
            logger.warning(f"B站评论已回复记忆保存失败：{path}（{type(exc).__name__}: {exc}）")

    async def poll_once(self) -> int:
        """轮询一次，返回本轮成功回复的条数。"""
        if not self._enabled:
            return 0
        client = resolve_client(self._client)
        if client is None:
            return 0
        if self._engine is None or not getattr(self._engine, "available", False):
            return 0
        # 拉取成功就清掉历史失败计数：即使本轮没有新通知，也是一次正常轮询。
        # 只在成功路径清零，避免一次发送失败把退避永久顶在 1 小时。
        self._failures = 0
        self._last_error = ""
        try:
            events = await self._fetch_events(client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"B站评论通知获取失败：{self._last_error}")
            return 0

        # 先并入池（池中的旧事件排在新事件前面），再按上限逐条处理。
        self._enqueue(events)
        if not self._pending:
            return 0

        replied = 0
        attempts = 0
        my_uid = int(getattr(client, "my_uid", 0) or 0)
        for key in list(self._pending):
            if replied >= self._max_per_poll or attempts >= self._max_per_poll:
                # 剩余事件留在池里，下一轮继续。
                logger.info(f"B站评论本轮达到上限，剩余 {len(self._pending)} 条留待下轮")
                break
            event = self._pending.pop(key)
            if my_uid and event.user_uid == my_uid:
                continue
            if event.dedupe_key in self._processed:
                continue
            if not self._cooldown_ok(event):
                self._pending[key] = event
                continue
            attempts += 1
            try:
                sent = await self._reply(event, client)
            except asyncio.CancelledError:
                # 停机取消时事件已经 pop 出来，放回池里，别丢这条回复。
                self._pending.setdefault(key, event)
                raise
            except Exception as exc:
                self._failures += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    f"B站评论回复异常（oid={event.oid} rpid={event.parent_id}），已回池重试：{self._last_error}"
                )
                self._pending[key] = event
                continue
            if sent:
                replied += 1
            elif event.dedupe_key not in self._processed:
                # 发送失败/暂时不满足条件：回池，下一轮重试。
                self._pending[key] = event
        return replied

    async def _fetch_events(self, client: Any) -> list[CommentEvent]:
        events: list[CommentEvent] = []
        get_reply_feed = getattr(client, "get_reply_feed", None)
        if callable(get_reply_feed):
            items = list(await call_client(get_reply_feed, limit=self._feed_limit) or [])
            self._warn_if_truncated(items, "回复我的")
            events.extend(_parse_items(items, "reply_feed"))
        # 「@我的」通知是独立接口；client 没实现时只处理「回复我的」。
        get_at_feed = getattr(client, "get_at_feed", None)
        if callable(get_at_feed):
            items = list(await call_client(get_at_feed, limit=self._feed_limit) or [])
            self._warn_if_truncated(items, "提到我的")
            events.extend(_parse_items(items, "at_feed"))
        batch_keys: set[str] = set()
        unique: list[CommentEvent] = []
        for event in events:
            if event.dedupe_key in batch_keys:
                continue
            batch_keys.add(event.dedupe_key)
            unique.append(event)
        return unique

    def _warn_if_truncated(self, items: list[Any], source: str) -> None:
        """水位线提示：接口没有游标，拉满 feed_limit 说明可能有更旧的通知没看到。"""
        if len(items) >= self._feed_limit:
            logger.warning(
                f"B站「{source}」通知达到单次拉取上限 {self._feed_limit} 条，"
                "更旧的通知可能延迟；必要时调大 feed_limit"
            )

    def _enqueue(self, events: list[CommentEvent]) -> None:
        """合并本轮新事件；池满时新事件跳过，下一轮会重新拉到。"""
        dropped = 0
        for event in events:
            key = event.dedupe_key
            if key in self._pending or key in self._processed:
                continue
            if len(self._pending) >= _PENDING_LIMIT:
                # shortcut: 池满丢新事件，下一轮靠 feed 重新拉到；长期积压需换持久化队列。
                dropped += 1
                continue
            self._pending[key] = event
        if dropped:
            logger.warning(
                f"B站评论待回复池已满（上限 {_PENDING_LIMIT}），{dropped} 条新事件留待下轮"
            )

    def _cooldown_ok(self, event: CommentEvent) -> bool:
        if self._cooldown <= 0:
            return True
        key = f"{event.oid}:{event.root_id}"
        last = self._last_reply_at.get(key)
        if last is None:
            return True
        return time.monotonic() - last >= self._cooldown

    async def _reply(self, event: CommentEvent, client: Any) -> bool:
        ctx = event.to_context()
        text = await self._engine.generate_comment_reply(ctx)
        if text is None:
            # 只有模型明确 skip/cancel 才返回 None：这条通知记掉，避免每轮重复生成
            # 烧 token；provider 异常由引擎抛出，会走回池重试，不在这里吞掉。
            self._processed.add(event.dedupe_key)
            self._save_state()
            logger.debug(f"B站评论跳过回复（oid={event.oid} rpid={event.parent_id}）")
            return False
        sent = await call_client(
            client.send_comment_reply,
            oid=event.oid,
            root=event.root_id,
            parent=event.parent_id,
            text=text,
            type_=event.comment_type,
        )
        if not sent:
            self._failures += 1
            logger.warning(f"B站评论回复发送失败（oid={event.oid} rpid={event.parent_id}）")
            return False
        self._processed.add(event.dedupe_key)
        self._save_state()
        self._last_reply_at[f"{event.oid}:{event.root_id}"] = time.monotonic()
        logger.info(f"B站评论已回复（oid={event.oid} rpid={event.parent_id}，{len(text)} 字）")
        return True


def _parse_items(items: Any, source: str) -> list[CommentEvent]:
    events: list[CommentEvent] = []
    for item in items or []:
        try:
            event = parse_feed_item(item, source)
        except Exception:
            logger.debug(f"跳过无法解析的B站通知条目（source={source}）")
            continue
        if event is not None:
            events.append(event)
    return events
