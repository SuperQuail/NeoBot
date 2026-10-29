"""Permission-gated /作息 management with narrowly scoped reply bypass."""

import re
from neobot_contracts.models import ConversationRef
from .config import Window

HELP = (
    "用法：/作息 状态；/作息 设置 默认|本群|本私聊 1,2,3 HH:MM-HH:MM [次日]；"
    "/作息 静默 默认|本群|本私聊 30m；/作息 恢复 默认|本群|本私聊。"
    "星期1–7为周一至周日；时长单位s/m/h/d；设置将替换该范围时段。"
)


def scope_for(label, conversation):
    if label == "默认":
        return "default"
    if label == "本群" and conversation.kind == "group":
        return f"group:{conversation.id}"
    if label == "本私聊" and conversation.kind == "private":
        return f"private:{conversation.id}"
    raise ValueError("范围与当前会话不匹配")


async def run_command(runtime, ctx):
    # Also guard direct handler invocation; never enter bypass or touch disk first.
    permissions = getattr(getattr(ctx, "service", None), "permissions", None)
    if permissions is None or not permissions.can(ctx.user_id, 1):
        return None
    conversation = ConversationRef(ctx.kind, str(ctx.conv_id))
    args = list(ctx.args)
    try:
        if args == ["状态"]:
            text = runtime.status(conversation)
        elif len(args) == 2 and args[0] == "恢复":
            scope = scope_for(args[1], conversation)
            if not runtime.account:
                raise ValueError("宿主未配置机器人账号")
            runtime.mutes.clear(runtime.account, scope)
            text = "已解除该范围临时静默；日程和睡眠状态仍然生效。"
        elif len(args) == 3 and args[0] == "静默":
            scope = scope_for(args[1], conversation)
            duration = re.fullmatch(r"([1-9]\d{0,8})([smhd])", args[2])
            if duration is None:
                raise ValueError("时长格式错误")
            if not runtime.account:
                raise ValueError("宿主未配置机器人账号")
            seconds = int(duration[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration[2]]
            runtime.mutes.set(runtime.account, scope, seconds)
            text = "已设置临时静默。"
        elif len(args) in (4, 5) and args[0] == "设置":
            scope = scope_for(args[1], conversation)
            if len(args) == 5 and args[4] != "次日":
                raise ValueError("跨夜标志须为次日")
            start, end = args[3].split("-")
            window = Window(
                weekdays=[int(d) for d in args[2].split(",")], start=start, end=end, next_day=len(args) == 5
            )
            config = runtime.config.model_dump()
            if scope == "default":
                config["windows"] = [window.model_dump()]
            else:
                config["overrides"] = [
                    o for o in config["overrides"] if (o["kind"], o["id"]) != (conversation.kind, conversation.id)
                ]
                config["overrides"].append(
                    dict(kind=conversation.kind, id=conversation.id, windows=[window.model_dump()])
                )
            await runtime.save_config(config)
            text = "已保存并立即生效。"
        else:
            text = HELP
    except (ValueError, TypeError):
        text = HELP
    except OSError:
        text = "保存失败，原设置保留，请检查插件数据目录权限。"
    with runtime.registry.bypass("speaking_schedule"):
        await runtime.ctx.send(conversation, text)
    return None
