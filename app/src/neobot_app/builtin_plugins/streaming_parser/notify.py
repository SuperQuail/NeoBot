"""开播/下播通知：渲染卡片图片 -> 官方图文卡片（或 OneBot 链接文本） -> 可选 AI 回复。

为什么不用官方 Markdown 卡片：
实测把渲染图上传成 qqbot-media 素材再嵌进 Markdown，客户端会把图片平铺成碎块；
真实登录态校验过上传字节与源文件完全一致，问题在素材图在 Markdown 里的客户端渲染。
因此官方通道改用原生图文卡片（msg_type=8，type=tuwen）：一条消息带封面图、标题、
描述与可点链接，封面直接用 B 站直播间原始封面 https 地址；图文卡片失败时退回一条
只含直播间链接的纯文本，链接不会丢。

为什么用 start_background_reply：
插件不在消息事件里，modloader 的 ctx.agent_reply() 依赖 PluginHookBus.dispatch 绑定的
EventContext，定时器里必然返回 False。宿主把 reply_orchestrator 注册成了宿主服务
（app/src/neobot_app/bootstrap/__init__.py:1423），它提供 start_background_reply(...)，
会构造一条系统消息并强制走一次回复管线（orchestrator.py:761-863），这正是我们要的。

推送行为矩阵：
- 官方通道：先发渲染卡片图片消息，再发一条图文卡片（标题=主播 状态，描述=直播标题
  · 分区 · 人气，url=直播间，pic_url=B 站原始封面）；图文卡片失败补一条纯链接文本；
- OneBot 通道：先发渲染卡片图片消息，再发一条只含直播间链接的文本；
- 图片渲染/发送失败：官方仍发图文卡片；OneBot 只发链接文本；
- 所有后台推送都带 proactive=True。
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import db
from .bilibili.urls import live_room_page_url
from .logs import log_at
from .poller import EVENT_LIVE, EVENT_LIVE_END, Transition
from .render import format_live_time, format_online, format_room_id, resolve_style

#: 卡片文件名（发给用户时的附件名）
CARD_FILENAME = "streaming_parser_card.png"
#: 官方图文卡片（msg_type=8）字段上限，与官方协议一致。
_TUWEN_TITLE_LIMIT = 50
_TUWEN_DESCRIPTION_LIMIT = 200







def build_fallback_text(
    *,
    kind: str,
    name: str,
    title: str,
    area_name: str,
    online: int,
    room_id: int,
    label: str | None = None,
) -> str:
    """渲染不可用时的等价纯文本（供面板预览降级；通知本身只发链接文本）。"""
    label = label or ("开播" if kind == EVENT_LIVE else "下播")
    lines = [f"【{label}】{name}"]
    if title:
        lines.append(title)
    extras = [item for item in (area_name, format_online(online) if kind == EVENT_LIVE else "") if item]
    if extras:
        lines.append(" · ".join(extras))
    lines.append(live_room_page_url(room_id))
    return "\n".join(lines)


def live_status_label(live_status: int) -> str:
    """B 站直播状态 → 卡片状态文案。

    1 沿用开播通知的「开播了」，让 /直播状态 的预览与真实推送逐字一致；
    2 是轮播；其余（0/异常值）按未开播展示。
    """
    if int(live_status) == 1:
        return "开播了"
    if int(live_status) == 2:
        return "轮播中"
    return "未开播"




def _one_line(value: Any) -> str:
    """压成一行：昵称/标题里的换行会把图文卡片的标题打乱。"""
    return " ".join(str(value or "").split())


def _https_url(value: Any) -> str:
    """只接受 https 公网地址（官方图文卡片对 url/pic_url 的硬要求）。"""
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def build_tuwen_content(
    *,
    name: str,
    title: str,
    area_name: str,
    online: int,
    room_id: int,
    label: str,
    cover_url: str,
) -> dict[str, str] | None:
    """组装官方图文卡片（msg_type=8）内容；封面不是 https 时返回 None（调用方退回文字链接）。"""
    pic_url = _https_url(cover_url)
    if not pic_url:
        return None
    card_title = f"{_one_line(name) or f'房间 {room_id}'} {label}"[:_TUWEN_TITLE_LIMIT]
    parts = [
        _one_line(title),
        _one_line(area_name),
        format_online(online) if online else "",
    ]
    description = " · ".join(part for part in parts if part) or "点击卡片进入直播间"
    return {
        "title": card_title,
        "description": description[:_TUWEN_DESCRIPTION_LIMIT],
        "url": live_room_page_url(room_id),
        "pic_url": pic_url,
    }


def build_agent_prompt(
    *, kind: str, name: str, title: str, room_id: int, group_id: int | str
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
    status_text: str | None = None,
) -> dict[str, Any]:
    """组装模板需要的全部占位符。推送、状态预览与样例渲染共用，保证样式完全一致。"""
    label = status_text or ("开播了" if kind == EVENT_LIVE else "下播了")
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
    """把状态跳变变成群里的卡片 / 文字，并可选触发一次 AI 回复。

    推送固定两条消息：先发渲染好的卡片图片；官方通道第二条是原生图文卡片
    （封面 + 标题/描述 + 可点直播间链接，失败退回纯链接），OneBot 第二条是链接文本。
    """

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

    def _conversation(self, group_id: int | str) -> Any:
        """不直接依赖 contracts：用 ctx 自己的推断方法构造会话引用。"""
        return self._ctx.conversation_from_event(
            {"message_type": "group", "group_id": group_id}
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
        group_id = str(subscription.group_id)
        name = subscription.name or f"房间 {transition.room_id}"
        snapshot = transition.snapshot
        label = "开播了" if is_live else "下播了"
        style = await self._style_for(group_id)
        card = await self._render_card(subscription, transition, style=style)
        # 用户要求：先发我们的渲染图片（保留 HTML 卡片全部信息），再发官方图文卡片。
        if card is not None:
            await self._send_image(group_id, card)
        await self._send_second_message(
            group_id,
            name=name,
            title=snapshot.title,
            area_name=snapshot.area_name,
            online=snapshot.online,
            room_id=transition.room_id,
            label=label,
            cover_url=snapshot.cover_url,
        )
        if await self._ai_reply_enabled(group_id, is_live=is_live):
            await self._trigger_ai_reply(subscription, transition)


    async def send_status_preview(
        self,
        group_id: int | str,
        *,
        room_id: int,
        name: str,
        avatar_url: str,
        snapshot: Any,
    ) -> None:
        """查询命令用：先发与推送相同的卡片图片，再发官方图文卡片/链接。

        只读：不写 room_states、不触发 AI 回复，避免预览命令吞掉真实的状态跳变。
        """
        label = live_status_label(snapshot.live_status)
        kind = EVENT_LIVE if snapshot.is_living else EVENT_LIVE_END
        style = await self._style_for(group_id)
        avatar_src = await self._assets.fetch_data_uri(avatar_url or "")
        cover_src = await self._assets.fetch_data_uri(snapshot.cover_url)
        values = build_card_values(
            kind=kind,
            room_id=room_id,
            name=name or f"房间 {room_id}",
            title=snapshot.title,
            area_name=snapshot.area_name,
            online=snapshot.online,
            live_time=snapshot.live_time,
            cover_src=cover_src,
            avatar_src=avatar_src,
            status_text=label,
        )
        card = await self._render_values(values, style=style)
        if card is not None:
            await self._send_image(group_id, card)
        await self._send_second_message(
            group_id,
            name=name or f"房间 {room_id}",
            title=snapshot.title,
            area_name=snapshot.area_name,
            online=snapshot.online,
            room_id=room_id,
            label=label,
            cover_url=snapshot.cover_url,
        )

    def _is_official(self, group_id: int | str) -> bool:
        """判定会话是否走官方通道：优先问适配器，取不到时按会话 ID 形态兜底。"""
        conversation = self._conversation(group_id)
        try:
            adapter = getattr(self._ctx, "adapter", None)
            resolver = getattr(adapter, "channels_for_conversation", None)
            if callable(resolver):
                channels = tuple(resolver(conversation) or ())
                if channels:
                    return channels == ("official",)
        except Exception:
            pass
        target = str(getattr(conversation, "id", "") or "").strip()
        # 官方 openid 非纯数字；13 位以上纯数字是旧官方合成号。
        return bool(target) and (not target.isdigit() or len(target) >= 13)

    async def _send_tuwen(self, group_id: int | str, content: dict[str, str]) -> bool:
        """发一条官方图文卡片（msg_type=8）；失败返回 False，由调用方退回文字链接。"""
        payload = [{"type": "official_tuwen", "data": content}]
        try:
            result = await self._ctx.send(
                self._conversation(group_id), payload, proactive=True
            )
        except Exception as exc:
            log_at(self._logger, "warning", f"发送图文卡片失败 (群 {group_id}): {exc!r}")
            return False
        if getattr(result, "status", None) == "failed":
            log_at(self._logger, "warning", f"发送图文卡片失败 (群 {group_id}): 适配器返回 failed")
            return False
        return True

    async def _send_second_message(
        self,
        group_id: int | str,
        *,
        name: str,
        title: str,
        area_name: str,
        online: int,
        room_id: int,
        label: str,
        cover_url: str,
    ) -> None:
        """图片之后的第二条：官方通道发图文卡片（封面 + 信息 + 可点链接），其它通道发纯链接。"""
        if self._is_official(group_id):
            content = build_tuwen_content(
                name=name,
                title=title,
                area_name=area_name,
                online=online,
                room_id=room_id,
                label=label,
                cover_url=cover_url,
            )
            if content is not None and await self._send_tuwen(group_id, content):
                return
        await self._send_text(group_id, live_room_page_url(room_id))

    async def _style_for(self, group_id: int | str) -> str:
        async with self._database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        style_name = setting.card_style if setting is not None else self._config.default_card_style
        return resolve_style(style_name)

    async def _ai_reply_enabled(self, group_id: int | str, *, is_live: bool) -> bool:
        async with self._database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        if setting is None:
            return bool(
                self._config.default_ai_reply_live
                if is_live
                else self._config.default_ai_reply_live_end
            )
        return bool(setting.ai_reply_live if is_live else setting.ai_reply_live_end)

    async def _render_values(self, values: dict[str, Any], *, style: str) -> bytes | None:
        """推送与 /直播状态 共用同一个模板入口，状态预览才不会长成另一张卡片。"""
        return await self._renderer.render_card(values, style=style)

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
        return await self._render_values(values, style=style)


    async def _send_image(self, group_id: int | str, data: bytes) -> bool:
        try:
            await self._ctx.send_image(
                self._conversation(group_id),
                data=data,
                filename=CARD_FILENAME,
                proactive=True,
            )
            return True
        except Exception as exc:
            log_at(self._logger, "warning", f"发送卡片失败 (群 {group_id}): {exc!r}")
            return False

    async def _send_text(self, group_id: int | str, text: str) -> None:
        try:
            await self._ctx.send_group(group_id, text, proactive=True)
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
        group_id = str(subscription.group_id)
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
