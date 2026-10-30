"""插件托管任务与一次性消息等待，停用时先取消再释放业务资源。"""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Coroutine
from contextlib import asynccontextmanager

from neobot_modloader.events import IncomingEvent


class MessageWaitBusy(RuntimeError):
    """同一用户在当前插件已有进行中的交互。"""


class PluginMessaging:
    def __init__(self) -> None:
        self._message_tasks: set[asyncio.Task] = set()
        self._message_waiters: dict[tuple, asyncio.Future] = {}
        self._messaging_closed = False
        self._message_sessions: set[tuple] = set()

    @asynccontextmanager
    async def message_session(self, origin: IncomingEvent):
        """多步骤交互共用一把用户会话锁，包括查询外部服务期间。"""
        if self._messaging_closed:
            raise RuntimeError("插件正在停止")
        if origin.scope in self._message_sessions:
            raise MessageWaitBusy("当前用户已有未结束的插件交互")
        self._message_sessions.add(origin.scope)
        try:
            yield
        finally:
            self._message_sessions.discard(origin.scope)

    def create_task(self, coroutine: Coroutine, *, name: str | None = None) -> asyncio.Task:
        """登记后台业务；异常由插件日志报告，关闭时等待取消完成。"""
        if self._messaging_closed:
            coroutine.close()
            raise RuntimeError("插件正在停止，不能创建任务")
        task = asyncio.create_task(coroutine, name=name)
        self._message_tasks.add(task)
        task.add_done_callback(self._message_task_done)
        return task

    def _message_task_done(self, task: asyncio.Task) -> None:
        self._message_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error(f"插件后台任务失败：{type(error).__name__}")

    async def close_tasks(self) -> None:
        self._messaging_closed = True
        for future in tuple(self._message_waiters.values()):
            future.cancel()
        tasks = tuple(self._message_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_for_message(
        self,
        origin: IncomingEvent,
        *,
        timeout: float = 60,
        rule=None,
        prompt: str | None = None,
    ) -> IncomingEvent:
        """等待同一机器人、会话和用户的下一条合格消息；匹配后消费该消息。"""
        if origin.kind != "message" or origin.user_id is None or origin.scope[1] not in {"group", "private"}:
            raise ValueError("消息等待必须由明确的入站消息发起")
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("timeout 必须是有限正数")
        if self._messaging_closed:
            raise RuntimeError("插件正在停止")
        if origin.scope in self._message_waiters:
            raise MessageWaitBusy("当前用户已有未结束的插件交互")
        future = asyncio.get_running_loop().create_future()
        self._message_waiters[origin.scope] = future

        async def matches(raw):
            if future.done() or IncomingEvent(raw).scope != origin.scope:
                return False
            result = rule(raw) if rule is not None else True
            if inspect.isawaitable(result):
                result = await result
            return bool(result) and not future.done()

        async def receive(raw):
            if not future.done():
                future.set_result(IncomingEvent(dict(raw)))

        subscription = None
        try:
            subscription = self.hook_bus.subscribe(
                receive, post_type="message", rule=matches, priority=1000, block=True
            )
            async with asyncio.timeout(timeout):
                if prompt is not None:
                    await self.reply(dict(origin.raw), prompt)
                return await future
        finally:
            if subscription is not None:
                subscription.unsubscribe()
            self._message_waiters.pop(origin.scope, None)
            future.cancel()
