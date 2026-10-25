"""开播/下播通知：渲染卡片 -> 发到群 -> 可选触发一次 AI 回复。

为什么用 start_background_reply：
插件不在消息事件里，modloader 的 ctx.agent_reply() 依赖 PluginHookBus.dispatch 绑定的
EventContext，定时器里必然返回 False。宿主把 reply_orchestrator 注册成了宿主服务
（app/src/neobot_app/bootstrap/__init__.py:1423），它提供 start_background_reply(...)，
会构造一条系统消息并强制走一次回复管线（orchestrator.py:761-863），这正是我们要的。
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import db
from .bilibili.urls import live_room_page_url
from .logs import log_at
from .poller import EVENT_LIVE, Transition
from .render import format_live_time, format_online, format_room_id, resolve_style

#: 卡片文件名（发给用户时的附件名）
CARD_FILENAME = "streaming_parser_card.png"


def build_fallback_text(
    *, kind: str, name: str, title: str, area_name: str, online: int, room_id: int
) -> str:
    """渲染不可用时的等价纯文本（本体约定：缺浏览器不报错，退化成文字）。"""
    label = "开播" if kind == EVENT_LIVE else "下播"
    lines = [f"【{label}】{name}"]
    if title:
        lines.append(title)
    extras = [item for item in (area_name, format_online(online) if kind == EVENT_LIVE else "") if item]
    if extras:
        lines.append(" · ".join(extras))
    lines.append(live_room_page_url(room_id))
    return "\n".join(lines)


def build_agent_prompt(
    *, kind: str, name: str, title: str, room_id: int, group_id: int
) -> str:
    """交给 agent 的提示词：明确告知「已经通知过」，避免它重复播报。"""
    if kind == EVENT_LIVE:
        action = "开播了"
        tail = "你已经把开播卡片发到群里了，不需要再重复通知一次。"
    else:
        action = "下播了"
        tail = "你已经把下播卡片发到群里了，不需要再重复通知一次。"
    return (
        f"[系统通知] 主播「{name}」{action}：{title or "（无标题）"}\n"
        f"直播间：{live_room_page_url(room_id)}\n"
        f"{tail}你可以选择说一句合适的话，也可以什么都不说。"
    )


def build_card_values(
    *,
    kind: str,
    room_id: int,
    name: str,
    title: str,
    area_name: str,
    online: int,
    live_time: Any,
    cover_src: str,
    avatar_src: str,
) -> dict[str, Any]:
    """组装模板需要的全部占位符。推送与样例渲染共用，保证两边完全一致。"""
    label = "开播了" if kind == EVENT_LIVE else "下播了"
    return {
        "avatar_src": avatar_src,
        "cover_src": cover_src,
        "name": name or f"房间 {room_id}",
        "title": title or "（无标题）",
        "area_name": area_name,
        "online_text": format_online(online),
        "live_time_text": format_live_time(live_time) if kind == EVENT_LIVE else "",
        "status_text": label,
        "room_id": format_room_id(room_id),
        "host_label": "Bilibili Live",
    }


class Notifier:
    """把状态跳变变成群里的卡片 / 文字，并可选触发一次 AI 回复。"""

    def __init__(
        self,
        *,
        ctx: Any,
        database: Any,
        renderer: Any,
        assets: Any,
        config: Any,
        logger: Any = None,
    ) -> None:
        self._ctx = ctx
        self._database = database
        self._renderer = renderer
        self._assets = assets
        self._config = config
        self._logger = logger

    def _conversation(self, group_id: int) -> Any:
        """不直接依赖 contracts：用 ctx 自己的推断方法构造会话引用。"""
        return self._ctx.conversation_from_event(
            {"message_type": "group", "group_id": int(group_id)}
        )

    async def handle_transition(self, transition: Transition) -> None:
        async with self._database.session() as session:
            followers = [
                db.sub_view(row)
                for row in await db.followers_of_room(session, transition.room_id)
            ]
        for subscription in followers:
            try:
                await self._notify_one(subscription, transition)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 单个群推送失败不能拖住其他群：记日志后继续下一个群。
                # 代价是这次跳变已经落库、不会再重放（见计划文档 T6 的补偿建议）。
                log_at(
                    self._logger,
                    "warning",
                    f"群 {subscription.group_id} 推送失败"
                    f"（房间 {transition.room_id} {transition.kind}）: {exc!r}",
                )

    async def _notify_one(self, subscription: Any, transition: Transition) -> None:
        is_live = transition.kind == EVENT_LIVE
        enabled = subscription.push_live if is_live else subscription.push_live_end
        if not enabled:
            return
        group_id = int(subscription.group_id)
        style = await self._style_for(group_id)
        card = await self._render_card(subscription, transition, style=style)
        sent_image = False
        if card is not None:
            sent_image = await self._send_image(group_id, card)
        if not sent_image:
            await self._send_text(
                group_id,
                build_fallback_text(
                    kind=transition.kind,
                    name=subscription.name or f"房间 {transition.room_id}",
                    title=transition.snapshot.title,
                    area_name=transition.snapshot.area_name,
                    online=transition.snapshot.online,
                    room_id=transition.room_id,
                ),
            )
        if await self._ai_reply_enabled(group_id, is_live=is_live):
            await self._trigger_ai_reply(subscription, transition)

    async def _style_for(self, group_id: int) -> str:
        async with self._database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        style_name = setting.card_style if setting is not None else self._config.default_card_style
        return resolve_style(style_name)

    async def _ai_reply_enabled(self, group_id: int, *, is_live: bool) -> bool:
        async with self._database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        if setting is None:
            return bool(
                self._config.default_ai_reply_live
                if is_live
                else self._config.default_ai_reply_live_end
            )
        return bool(setting.ai_reply_live if is_live else setting.ai_reply_live_end)

    async def _render_card(self, subscription: Any, transition: Transition, *, style: str) -> bytes | None:
        snapshot = transition.snapshot
        avatar_src = await self._assets.fetch_data_uri(subscription.avatar_url or "")
        cover_src = await self._assets.fetch_data_uri(snapshot.cover_url)
        values = build_card_values(
            kind=transition.kind,
            room_id=transition.room_id,
            name=subscription.name or f"房间 {transition.room_id}",
            title=snapshot.title,
            area_name=snapshot.area_name,
            online=snapshot.online,
            live_time=snapshot.live_time,
            cover_src=cover_src,
            avatar_src=avatar_src,
        )
        return await self._renderer.render_card(values, style=style)

    async def _send_image(self, group_id: int, data: bytes) -> bool:
        try:
            await self._ctx.send_image(
                self._conversation(group_id), data=data, filename=CARD_FILENAME
            )
            return True
        except Exception as exc:
            log_at(self._logger, "warning", f"发送卡片失败 (群 {group_id}): {exc!r}")
            return False

    async def _send_text(self, group_id: int, text: str) -> None:
        try:
            await self._ctx.send_group(group_id, text)
        except Exception as exc:
            log_at(self._logger, "warning", f"发送通知失败 (群 {group_id}): {exc!r}")

    def _service(self, name: str) -> Any:
        """按名取宿主服务；缺失返回 None。

        注意：不能缓存结果——软重启会重建 reply_orchestrator 等对象并以 override 覆盖注册表，
        缓存下来的会是已关闭的死对象。
        """
        try:
            services = self._ctx.plugin_host.services
        except Exception:
            return None
        try:
            return services.get(name)
        except Exception:
            return None

    async def _trigger_ai_reply(self, subscription: Any, transition: Transition) -> bool:
        """让 agent 就这次开播/下播说一次话（失败只记日志，不影响推送）。

        优先级：notification_hub.publish（会把通知镜像进消息队列，agent 后续轮次也能看到）
        -> reply_orchestrator.start_background_reply -> record_notification 兜底。
        """
        group_id = int(subscription.group_id)
        prompt = build_agent_prompt(
            kind=transition.kind,
            name=subscription.name or f"房间 {transition.room_id}",
            title=transition.snapshot.title,
            room_id=transition.room_id,
            group_id=group_id,
        )
        reasons = [f"直播间 {transition.room_id} {transition.kind}"]

        hub = self._service("notification_hub")
        publish = getattr(hub, "publish", None)
        if callable(publish):
            try:
                started = await publish(
                    source="streaming_parser",
                    kind="group",
                    conversation_id=str(group_id),
                    content=prompt,
                    manager_name="streaming_parser",
                    reasons=reasons,
                )
                log_at(
                    self._logger,
                    "debug",
                    f"群 {group_id} 通知已投递（起新管线={bool(started)}）",
                )
                return True
            except Exception as exc:
                log_at(self._logger, "warning", f"notification_hub 投递失败，降级直连编排器: {exc!r}")

        orchestrator = self._service("reply_orchestrator")
        start = getattr(orchestrator, "start_background_reply", None)
        if callable(start):
            try:
                result = start(
                    kind="group",
                    conversation_id=str(group_id),
                    content=prompt,
                    manager_name="streaming_parser",
                    reasons=reasons,
                )
            except Exception as exc:
                log_at(self._logger, "warning", f"触发 AI 回复失败 (群 {group_id}): {exc!r}")
                return False
            if result is not None:
                return True
            # 该会话已有活跃回复管线时会被跳过，这是宿主的有意设计；
            # 至少把通知写进队列，让 agent 在后续轮次里知道这件事。
            log_at(self._logger, "debug", f"群 {group_id} 已有回复管线，改为写入通知队列")
            record = getattr(orchestrator, "record_notification", None)
            if callable(record):
                try:
                    record(
                        kind="group",
                        conversation_id=str(group_id),
                        source="streaming_parser",
                        content=prompt,
                    )
                except Exception as exc:
                    log_at(self._logger, "warning", f"写入通知队列失败: {exc!r}")
            return False
        log_at(self._logger, "warning", "宿主未提供 notification_hub / reply_orchestrator，跳过 AI 回复")
        return False

