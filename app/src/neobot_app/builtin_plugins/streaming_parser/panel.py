"""面板业务入口：复用订阅规则，创建前校验当前机器人的群目录。"""

from dataclasses import asdict
from typing import Any

from neobot_adapter.model.response import GetGroupListResponse, GetLoginInfoResponse
from pydantic import ValidationError

from neobot_modloader import ActionError, Plugin

from . import db
from . import panel_models as models
from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .bilibili.urls import live_room_page_url
from .notify import build_card_values, build_fallback_text
from .poller import EVENT_LIVE
from .settings_commands import group_defaults, match_style
from .subscriptions import SubscriptionService


async def groups(state: Any) -> models.Groups:
    try:
        raw_response = await state.ctx.adapter.call_api("get_group_list", {})
        response = GetGroupListResponse.model_validate(raw_response)
        if (
            response.status != "ok"
            or response.retcode not in (None, 0)
            or response.data is None
        ):
            raise ActionError(
                "group_list_unavailable", "群列表读取失败，请检查机器人连接后重试。"
            )
        if not response.data:
            return models.Groups(items=[])
        # RuntimeAdapter 不公开 self_id；有群可选时再通过标准接口读取账号。
        raw_login = await state.ctx.adapter.call_api("get_login_info", {})
        login = GetLoginInfoResponse.model_validate(raw_login)
        if (
            login.status != "ok"
            or login.retcode not in (None, 0)
            or login.data is None
            or login.data.user_id is None
        ):
            raise ActionError(
                "group_list_unavailable", "群列表读取失败，请检查机器人连接后重试。"
            )
    except ActionError:
        raise
    except ValidationError:
        # ValidationError 会带原始输入，不能把适配器响应写入日志。
        state.ctx.logger.warning("机器人群目录响应结构无效，请检查适配器返回格式。")
        raise ActionError(
            "group_list_unavailable", "暂时无法读取机器人所在的群，请检查机器人连接。"
        ) from None
    except Exception as exc:
        # 外部异常文本可能包含请求地址或凭据，只记录阶段和异常类型。
        state.ctx.logger.warning(
            f"读取机器人群目录失败，适配器异常类型：{type(exc).__name__}"
        )
        raise ActionError(
            "group_list_unavailable", "暂时无法读取机器人所在的群，请检查机器人连接。"
        ) from None
    bot_id = str(login.data.user_id)
    return models.Groups(
        items=[
            models.GroupChoice(
                group_id=row.group_id,
                name=row.group_name or str(row.group_id),
                bot_id=bot_id,
            )
            for row in response.data
            if row.group_id is not None
        ]
    )


async def require_group(state: Any, group_id: int) -> None:
    if not any(item.group_id == group_id for item in (await groups(state)).items):
        raise ActionError("group_unavailable", "机器人不在这个群中，请重新选择接收群。")


async def resolve(service: SubscriptionService, target: str) -> models.Target:
    try:
        value = await service.resolve(target)
    except ValueError as exc:
        raise ActionError("invalid_target", str(exc)) from None
    except (BilibiliAPIError, BilibiliTransportError):
        raise ActionError(
            "target_unavailable", "暂时无法识别直播间，请检查链接或稍后重试。"
        ) from None
    return models.Target(**value, url=live_room_page_url(value["room_id"]))


def register_surface(plugin: Plugin, state: Any) -> None:
    service = SubscriptionService(state)

    @plugin.action(
        "subscriptions.groups",
        title="选择接收群",
        permission="read",
        output_model=models.Groups,
    )
    async def list_groups(values, invocation):
        return await groups(state)

    @plugin.action(
        "groups.settings.get",
        title="查看群设置",
        permission="read",
        input_model=models.GroupSettingsInput,
        output_model=models.GroupSettings,
    )
    async def get_group_settings(values, invocation):
        # 本地读取不依赖群目录，也不把继承的默认值写入数据库。
        async with state.database.session() as session:
            row = await db.get_group_setting(session, values.group_id)
            setting = db.setting_view(row)
        effective = (
            asdict(setting)
            if setting is not None
            else {"group_id": values.group_id, **group_defaults(state.config)}
        )
        # 兼容旧配置的风格写法，只规范返回值，不回写或随机挑选固定风格。
        effective["card_style"] = match_style(effective["card_style"]) or "random"
        return models.GroupSettings(**effective, inherited=setting is None)

    @plugin.action(
        "groups.settings.update",
        title="保存群设置",
        permission="manage",
        input_model=models.GroupSettingsUpdateInput,
        output_model=models.GroupSettings,
    )
    async def update_group_settings(values, invocation):
        await require_group(state, values.group_id)
        async with state.database.transaction() as session:
            setting = await db.ensure_group_setting(
                session, values.group_id, group_defaults(state.config)
            )
            for field, value in values.model_dump(exclude={"group_id"}).items():
                setattr(setting, field, value)
            # 只改群设置；已有订阅的推送开关保持原样。
            result = models.GroupSettings(
                **asdict(db.setting_view(setting)), inherited=False
            )
        return result

    @plugin.action(
        "subscriptions.resolve",
        title="识别直播间",
        permission="read",
        input_model=models.TargetInput,
        output_model=models.Target,
    )
    async def resolve_target(values, invocation):
        return await resolve(service, values.target)

    @plugin.action(
        "subscriptions.preview",
        title="预览通知",
        permission="read",
        input_model=models.CreateInput,
        output_model=models.Preview,
    )
    async def preview(values, invocation):
        await require_group(state, values.group_id)
        target = await resolve(service, values.target)
        try:
            info = await state.client.fetch_live_room_info(target.room_id)
        except (BilibiliAPIError, BilibiliTransportError):
            raise ActionError(
                "preview_unavailable", "直播间状态暂时不可用，请稍后重新预览。"
            ) from None
        style = await state.style_for(values.group_id)
        data = build_card_values(
            kind=EVENT_LIVE,
            room_id=target.room_id,
            name=target.name,
            title=info.title,
            area_name=info.area_name,
            online=info.online,
            live_time=info.live_time,
            cover_src=await state.assets.fetch_data_uri(info.cover),
            avatar_src=await state.assets.fetch_data_uri(target.avatar_url),
        )
        html = state.renderer.card_html(data, style=style)
        if html is None:
            raise ActionError(
                "preview_unavailable", "通知卡片模板不可用，请检查插件文件是否完整。"
            )
        return models.Preview(
            target=target,
            style=style,
            html=html,
            fallback_text=build_fallback_text(
                kind=EVENT_LIVE,
                name=target.name,
                title=info.title,
                area_name=info.area_name,
                online=info.online,
                room_id=target.room_id,
            ),
        )

    @plugin.action(
        "subscriptions.create",
        title="开始监听",
        input_model=models.CreateInput,
        output_model=models.Created,
    )
    async def create(values, invocation):
        await require_group(state, values.group_id)
        target = await resolve(service, values.target)
        row, created = await service.create_resolved(
            values.group_id, target.model_dump(exclude={"url"})
        )
        return models.Created(
            created=created, item=models.SubscriptionItem(**asdict(row))
        )

    @plugin.action(
        "subscriptions.list",
        title="查看订阅",
        permission="read",
        input_model=models.ListInput,
        output_model=models.SubscriptionList,
    )
    async def list_subscriptions(values, invocation):
        return models.SubscriptionList(items=await service.list(values.group_id))

    @plugin.action(
        "subscriptions.remove",
        title="取消监听",
        input_model=models.SubscriptionInput,
        output_model=models.Removed,
    )
    async def remove(values, invocation):
        return models.Removed(
            removed=await service.remove(values.group_id, values.room_id)
        )

    @plugin.action(
        "subscriptions.toggle",
        title="调整推送开关",
        input_model=models.ToggleInput,
        output_model=models.Changed,
    )
    async def toggle(values, invocation):
        row = await service.toggle(
            values.group_id,
            values.room_id,
            push_live=values.push_live,
            push_live_end=values.push_live_end,
        )
        if row is None:
            raise ActionError(
                "subscription_not_found", "这条订阅已不存在，请刷新列表。"
            )
        return models.Changed(item=models.SubscriptionItem(**asdict(row)))

    @plugin.action(
        "subscriptions.health",
        title="查看监听状态",
        permission="read",
        input_model=models.ListInput,
        output_model=models.Health,
    )
    async def health(values, invocation):
        return models.Health(**await service.health(values.group_id))

    @plugin.action(
        "subscriptions.ready",
        title="检查首次订阅",
        permission="read",
        output_model=models.Ready,
    )
    async def ready(values, invocation):
        return models.Ready(**await service.ready())

    plugin.resource(
        "subscriptions",
        title="订阅列表",
        list_action="subscriptions.list",
        columns=[
            {"key": "group_id", "title": "接收群"},
            {"key": "name", "title": "主播"},
            {"key": "room_id", "title": "直播间"},
            {"key": "push_live", "title": "开播推送"},
            {"key": "push_live_end", "title": "下播推送"},
        ],
        create_action="subscriptions.create",
        delete_action="subscriptions.remove",
    )
    plugin.view(
        "subscriptions",
        title="直播订阅",
        entry="web/subscriptions/index.html",
        anchors=[
            "group",
            "target",
            "preview",
            "start",
            "status",
            "settings",
            "health-panel",
        ],
    )
