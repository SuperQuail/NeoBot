from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from neobot_modloader.agent import AgentRequest
from neobot_modloader.command_dsl import MessagePattern, RegexPattern
from neobot_modloader.database import Migration, PluginDatabase
from neobot_modloader.message import Message
from neobot_modloader.plugins.agents import bind_agents
from neobot_modloader.plugins.dispatch import bind_handlers
from neobot_modloader.plugins.injection import resolve_handler_kwargs
from neobot_modloader.plugins.markdown_skills import bind_markdown_skills
from neobot_modloader.plugins.registration import (
    AgentRegistration,
    Handler,
    HandlerRegistration,
    ToolRegistration,
    looks_like_context,
    validate_agent_name,
    validate_parse_error,
    validate_plugin_name,
    validate_tool_name,
)
from neobot_modloader.plugins.tools import bind_tools


class Plugin:
    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        description: str = "",
        usage: str = "",
        author: str = "",
        config: type[BaseModel] | None = None,
        command_prefix: str = "/",
        dependencies: Sequence[str] = (),
        priority: int = 0,
        min_neobot_version: str | None = None,
        python_dependencies: Sequence[str] = (),
    ) -> None:
        self.name = validate_plugin_name(name)
        self.version = str(version)
        self.description = description
        self.usage = usage
        self.author = author
        self.config_model = config
        self.command_prefix = MessagePattern(
            "_prefix_validation", command=True, prefix=command_prefix
        ).prefix
        self.dependencies = tuple(dependencies)
        self.priority = int(priority)
        self.min_neobot_version = min_neobot_version
        self.python_dependencies = tuple(python_dependencies)
        self._registrations: list[HandlerRegistration] = []
        self._load_handlers: list[Handler] = []
        self._startup_handlers: list[Handler] = []
        self._shutdown_handlers: list[Handler] = []
        self._agent_registrations: list[AgentRegistration] = []
        self._tool_registrations: list[ToolRegistration] = []
        self._databases: dict[str, PluginDatabase] = {}
        self._context: Any | None = None
        self._config: BaseModel | None = None
        self._bound = False

    def sqlite_database(
        self,
        name: str = "main",
        *,
        filename: str | None = None,
        metadata: Any | None = None,
        migrations: Sequence[Migration] = (),
        pragmas: Mapping[str, str] | None = None,
    ) -> PluginDatabase:
        """声明一个插件独立数据库；实际初始化发生在插件加载阶段。"""
        if name in self._databases:
            raise ValueError(f"插件 {self.name} 已注册同名数据库: {name}")
        filename = filename or f"{name}.sqlite3"
        for existing in self._databases.values():
            if existing.filename.casefold() == filename.casefold():
                raise ValueError(
                    f"插件 {self.name} 已注册使用同名文件的数据库: {filename!r}"
                )
        database = PluginDatabase(
            self.name,
            name,
            filename=filename,
            metadata=metadata,
            migrations=tuple(migrations),
            pragmas=pragmas,
        )
        self._databases[name] = database
        return database

    def command(
        self,
        pattern: str,
        *,
        prefix: str | None = None,
        aliases: Sequence[str] | None = None,
        priority: int = 10,
        block: bool = True,
        timeout: float | None = None,
        parse_error: str = "reply",
    ) -> Callable[[Handler], Handler]:
        """Register a slash command handler.

        With ``parse_error="ignore"``, a matching command whose arguments do
        not parse is treated as unhandled: it neither runs the handler nor
        applies this registration's block settings.
        """
        compiled = MessagePattern(
            pattern,
            command=True,
            aliases=tuple(aliases or ()),
            prefix=prefix if prefix is not None else self.command_prefix,
        )
        validate_parse_error(parse_error)

        def decorate(handler: Handler) -> Handler:
            self._registrations.append(
                HandlerRegistration(
                    kind="command",
                    pattern=compiled,
                    handler=handler,
                    priority=priority,
                    block=block,
                    block_ai_reply=False,
                    timeout=timeout,
                    parse_error=parse_error,
                    command_prefix=prefix,
                )
            )
            return handler

        return decorate

    def message(
        self,
        pattern: str | None = None,
        *,
        text: str | None = None,
        contains: str | Sequence[str] | None = None,
        keywords: str | Sequence[str] | None = None,
        regex: str | re.Pattern[str] | None = None,
        startswith: str | None = None,
        endswith: str | None = None,
        fullmatch: str | None = None,
        group: bool = False,
        private: bool = False,
        rule: Callable[[dict[str, Any]], Any] | None = None,
        priority: int = 10,
        block: bool = False,
        block_ai_reply: bool = False,
        timeout: float | None = None,
        parse_error: str = "ignore",
    ) -> Callable[[Handler], Handler]:
        if group and private:
            raise ValueError("group and private cannot both be True")
        validate_parse_error(parse_error)
        compiled = MessagePattern(pattern, command=False)
        regex_filter: re.Pattern[str] | None = None
        if regex is not None:
            regex_filter = RegexPattern(regex).pattern

        def decorate(handler: Handler) -> Handler:
            self._registrations.append(
                HandlerRegistration(
                    kind="message",
                    pattern=compiled,
                    handler=handler,
                    priority=priority,
                    block=block,
                    block_ai_reply=block_ai_reply,
                    timeout=timeout,
                    parse_error=parse_error,
                    group=group,
                    private=private,
                    text=text,
                    contains=contains,
                    keywords=keywords,
                    regex=regex_filter,
                    startswith=startswith,
                    endswith=endswith,
                    fullmatch=fullmatch,
                    rule=rule,
                )
            )
            return handler

        return decorate

    def regex(
        self,
        pattern: str | re.Pattern[str],
        *,
        flags: int = 0,
        group: bool = False,
        private: bool = False,
        rule: Callable[[dict[str, Any]], Any] | None = None,
        priority: int = 10,
        block: bool = False,
        block_ai_reply: bool = False,
        timeout: float | None = None,
        parse_error: str = "ignore",
    ) -> Callable[[Handler], Handler]:
        """Register a regex message handler.

        The pattern is searched against ``message.text``. Named groups
        ``(?P<name>...)`` are injected into the handler by parameter name;
        DI parameters (Reply, config, ...) are resolved as usual.
        """
        if group and private:
            raise ValueError("group and private cannot both be True")
        validate_parse_error(parse_error)
        compiled = RegexPattern(pattern, flags=flags)

        def decorate(handler: Handler) -> Handler:
            self._registrations.append(
                HandlerRegistration(
                    kind="regex",
                    pattern=compiled,
                    handler=handler,
                    priority=priority,
                    block=block,
                    block_ai_reply=block_ai_reply,
                    timeout=timeout,
                    parse_error=parse_error,
                    group=group,
                    private=private,
                    rule=rule,
                )
            )
            return handler

        return decorate

    def agent(
        self,
        name: str,
        *,
        description: str = "",
        factory: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> Callable[[Handler], Handler]:
        local_name = validate_agent_name(name)
        tool_definitions = [dict(tool) for tool in tools] if tools is not None else None

        def decorate(handler: Handler) -> Handler:
            self._agent_registrations.append(
                AgentRegistration(
                    name=local_name,
                    description=str(description),
                    handler=handler,
                    factory=bool(factory),
                    tools=tool_definitions,
                )
            )
            return handler

        return decorate

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Handler], Handler]:
        """注册一个可被主 Agent 调用的工具。

        处理器参数会从模型传入的 JSON 参数中解析（参数 schema 由签名自动生成，
        也可通过 ``parameters=`` 显式覆盖）。类型注解优先：例如
        ``config: dict`` 和 ``ctx: str`` 是模型参数；仅无注解的约定名称或
        ``Config``/context/``Logger`` 等 DI 注解会由运行时注入。

        Tool 没有入站事件。``Reply`` DI 会在绑定时被拒绝；``Message`` DI
        只能得到空的合成消息。如需响应当前消息，请使用 command/message handler。
        """
        validate_tool_name(name)

        def decorate(handler: Handler) -> Handler:
            self._tool_registrations.append(
                ToolRegistration(
                    name=name,
                    description=str(description),
                    handler=handler,
                    parameters=dict(parameters) if parameters is not None else None,
                )
            )
            return handler

        return decorate

    def on_load(self, value: Any) -> Any:
        """Register a load hook, or load the plugin when passed a context.

        Lifecycle hooks have no inbound event. Message DI receives an empty
        synthetic message and Reply.send cannot infer a conversation; use the
        runtime context or Bot for lifecycle-originated work instead.
        """
        if callable(value) and not looks_like_context(value):
            self._load_handlers.append(value)
            return value
        return self._load(value)

    def on_startup(self, handler: Handler) -> Handler:
        """Register a startup hook; lifecycle hooks have no inbound event."""
        self._startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Handler) -> Handler:
        """Register a shutdown hook; lifecycle hooks have no inbound event."""
        self._shutdown_handlers.append(handler)
        return handler

    async def on_start(self) -> None:
        for handler in self._startup_handlers:
            await self._call_lifecycle(handler)

    async def on_stop(self) -> None:
        errors: list[Exception] = []
        try:
            for handler in reversed(self._shutdown_handlers):
                try:
                    await self._call_lifecycle(handler)
                except Exception as exc:
                    errors.append(exc)
        finally:
            for database in self._databases.values():
                try:
                    await database.close()
                except Exception as exc:
                    errors.append(exc)
            self._bound = False
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("插件关闭处理器执行失败", errors)

    async def _load(self, context: Any) -> None:
        self._context = context
        self._config = (
            self.config_model.model_validate(dict(context.config))
            if self.config_model is not None
            else None
        )
        await self._bind_databases()
        if not self._bound:
            self._apply_command_prefix()
            # 订阅、Tool、SKILL.md 和 Agent 只绑定一次；reload/stop 会由 manager 清理旧绑定。
            bind_handlers(self, self._registrations, context)
            await bind_tools(self, self._tool_registrations, context)
            await bind_markdown_skills(self, context)
            await bind_agents(self, self._agent_registrations, context)
            self._bound = True
        for handler in self._load_handlers:
            await self._call_lifecycle(handler)

    def _apply_command_prefix(self) -> None:
        prefix = self.command_prefix
        configured = getattr(self._config, "command_prefix", None)
        if configured is not None:
            prefix = MessagePattern(
                "_prefix_validation", command=True, prefix=configured
            ).prefix
        for registration in self._registrations:
            if registration.kind != "command" or registration.command_prefix is not None:
                continue
            old_prefix = registration.pattern.prefix
            pattern = registration.pattern.pattern
            if old_prefix and pattern.startswith(old_prefix):
                pattern = pattern.removeprefix(old_prefix)
            aliases = tuple(
                alias.removeprefix(old_prefix)
                if old_prefix and alias.startswith(old_prefix)
                else alias
                for alias in registration.pattern.aliases
            )
            registration.pattern = MessagePattern(
                pattern,
                command=True,
                aliases=aliases,
                prefix=prefix,
            )

    async def _bind_databases(self) -> None:
        if not self._databases:
            return
        databases_dir = self._context.data_dir / "databases"
        bound: list[PluginDatabase] = []
        try:
            for database in self._databases.values():
                await database.bind(databases_dir)
                bound.append(database)
        except Exception:
            for database in reversed(bound):
                try:
                    await database.close()
                except Exception:
                    pass
            raise

    async def _call_lifecycle(self, handler: Handler) -> Any:
        if self._context is None:
            return None
        return await self._call_handler(handler, self._context, {}, Message({}), {})

    async def _call_handler(
        self,
        handler: Handler,
        context: Any,
        event: dict[str, Any],
        message: Message,
        captures: dict[str, Any],
    ) -> Any:
        kwargs = await resolve_handler_kwargs(
            handler,
            context=context,
            event=event,
            message=message,
            captures=captures,
            config=self._config,
            config_model=self.config_model,
            agent_request=None,
        )
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _call_agent_handler(
        self,
        handler: Handler,
        context: Any,
        request: AgentRequest,
    ) -> Any:
        kwargs = await resolve_handler_kwargs(
            handler,
            context=context,
            event={},
            message=Message({}),
            captures={},
            config=self._config,
            config_model=self.config_model,
            agent_request=request,
        )
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
