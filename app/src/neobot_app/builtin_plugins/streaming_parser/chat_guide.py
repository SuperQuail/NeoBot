"""聊天订阅向导：等待不占据事件分发，写入前重新检查权限。"""

from typing import Any

from neobot_modloader import (
    IncomingEvent,
    MessageWaitBusy,
    Plugin,
    Reply,
    RuntimePluginContext,
    starts_with,
)

from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .subscriptions import SubscriptionService


def register_chat_guide(plugin: Plugin, state: Any) -> None:
    @plugin.command("监听向导", permission=1, description="分步填写直播间并确认订阅")
    async def start(
        incoming: IncomingEvent,
        reply: Reply,
        ctx: RuntimePluginContext,
        command_context,
    ) -> None:
        if incoming.scope[1] != "group" or incoming.group_id is None:
            await reply.send("请在需要接收通知的群中使用 /监听向导。")
            return
        ctx.create_task(
            run_guide(state, ctx, incoming, reply, command_context),
            name="streaming-subscription-guide",
        )


async def run_guide(state, ctx, origin, reply, command_context) -> None:
    try:
        async with ctx.message_session(origin):
            await collect_subscription(state, ctx, origin, reply, command_context)
    except MessageWaitBusy:
        await reply.send("当前已有订阅向导，请先完成或等待超时。")
    except TimeoutError:
        await reply.send("订阅向导已超时，未添加订阅。")
    except ValueError:
        await reply.send("无法识别直播间，请检查链接后重新使用 /监听向导。")
    except (BilibiliAPIError, BilibiliTransportError):
        await reply.send("直播间服务暂不可用，未添加订阅，请稍后重试。")


async def collect_subscription(state, ctx, origin, reply, command_context) -> None:
    """先收集目标，再确认；确认前不修改订阅数据。"""
    service = SubscriptionService(state)
    message = await ctx.wait_for_message(
        origin,
        rule=~starts_with("/"),
        prompt="请在 60 秒内发送直播间链接或房间号，发送“取消”退出。",
    )
    target = message.chain.exclude("at", "reply").plain_text.strip()
    if target == "取消":
        await reply.send("已取消订阅向导。")
        return
    resolved = await service.resolve(target)
    answer = await ctx.wait_for_message(
        origin,
        rule=~starts_with("/"),
        prompt=f"将为本群监听 {resolved['name']}（{resolved['room_id']}）。发送“确认”保存，其他文字取消。",
    )
    if answer.chain.plain_text.strip() != "确认":
        await reply.send("已取消，未添加订阅。")
        return
    if not command_context.service.permissions.can(origin.user_id, 1):
        await reply.send("管理权限已变化，未添加订阅。")
        return
    row, created = await service.create_resolved(origin.group_id, resolved)
    await reply.send(
        f"{'已开始监听' if created else '已更新监听信息'}：{row.name}（{row.room_id}）。"
    )
