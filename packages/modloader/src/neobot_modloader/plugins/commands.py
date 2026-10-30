"""声明式命令接入宿主注册表，权限、帮助和重名回退继续由宿主管理。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_modloader.command_dsl import MessagePattern, PatternError
from neobot_modloader.message import Message


def bind_command(plugin: Any, registration: Any, context: Any) -> None:
    if not context.app_commands.available:
        context.logger.warning("宿主命令表不可用，跳过声明式命令注册")
        return
    pattern = registration.pattern
    if pattern.prefix != "/":
        raise PatternError("宿主命令仅支持 / 前缀")
    usage = " ".join(pattern.pattern.split()[1:])

    async def invoke(command_context):
        original = command_context.message
        if hasattr(original, "model_dump"):
            event = original.model_dump(mode="json")
        else:
            event = dict(original) if isinstance(original, dict) else {}
            if getattr(original, "message", None) is not None:
                event["message"] = original.message
        event.setdefault("self_id", getattr(context.adapter, "self_id", None))
        event.setdefault("post_type", "message")
        event.setdefault("message_type", command_context.kind)
        event.setdefault("user_id", command_context.user_id)
        if command_context.kind == "group":
            event.setdefault("group_id", int(command_context.conv_id))
        if not event.get("message"):
            event["message"] = f"/{pattern.command_name} {command_context.raw_args}"
        # 重名回退改变外部命令名，仍以同一份参数声明解析，保留原始消息段。
        actual_pattern = MessagePattern(
            pattern.pattern,
            command=True,
            aliases=(*pattern.aliases, command_context.command.name),
        )
        message = Message(event)
        matched = actual_pattern.match(message)
        if not matched.matched:
            await command_context.reply(f"参数错误，用法: /{command_context.command.name} {usage}".rstrip())
            return None
        captures = {**matched.values, "command_context": command_context}
        async with asyncio.timeout(registration.timeout):
            return await plugin._call_handler(registration.handler, context, event, message, captures)

    context.app_commands.register(
        pattern.command_name,
        description=registration.description,
        usage=usage,
        permission=registration.permission,
        aliases=tuple(alias.removeprefix("/") for alias in pattern.aliases),
        params=tuple((name, "命令参数") for name in pattern.capture_names),
    )(invoke)
