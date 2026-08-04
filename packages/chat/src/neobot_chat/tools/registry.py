from __future__ import annotations

import asyncio
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from neobot_chat.schema.protocol import AgentLike


@dataclass(eq=False)
class _Registration:
    name: str
    agent: AgentLike
    generation: int


@dataclass(eq=False)
class _Removal:
    registration: _Registration
    tasks: set[asyncio.Task] = field(default_factory=set)
    delegates: set[asyncio.Task] = field(default_factory=set)
    operation: asyncio.Task | None = None
    retired: bool = False
    finishing: bool = False
    close_retries: int = 0
    last_error: BaseException | None = None


class AgentRegistry:
    """子 Agent 注册表"""

    def __init__(self):
        self._agents: dict[str, AgentLike] = {}
        self._registrations: dict[str, _Registration] = {}
        self._next_generation = 0
        # Weak identity history rejects reuse without retaining unloaded agents.
        # Non-weakrefable instances are checked by a live-instance scan instead of
        # being strongly retained (see register/_is_agent_in_use).
        self._known_agents: dict[int, weakref.ReferenceType[AgentLike] | AgentLike] = {}
        self._sessions: dict[str, list[dict]] = {}
        # 按 Agent 名跟踪在途 invoke 任务，卸载时只排空属于该 Agent 的任务
        self._in_flight: dict[int, set[asyncio.Task]] = {}
        self._delegates: dict[int, set[asyncio.Task]] = {}
        # 按 session key 保护「读会话 → invoke → 写会话」整段，避免并发覆盖丢失历史
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_lock_users: dict[str, int] = {}
        # 已注销但仍有顽固 invoke 的 Agent 必须保持强引用，任务结束后才能关闭。
        self._retired: dict[int, _Removal] = {}
        self._agent_close_tasks: dict[int, tuple[AgentLike, asyncio.Task]] = {}
        self._removals: dict[int, _Removal] = {}
        self._unregister_tasks: dict[int, asyncio.Task] = {}
        self._callback_tasks: set[asyncio.Task] = set()
        # 由排空/关闭主动取消的委托任务：只有被标记的任务才能把 CancelledError
        # 转成友好文本，外部取消（wait_for 超时、调用方取消、编排器停机）必须上抛。
        self._drained_tasks: set[asyncio.Task] = set()
        self._close_pending = False
        self._close_task: asyncio.Task | None = None
        self._closed = False
        self.delegate_timeout_seconds = 120.0
        self.drain_timeout_seconds = 5.0
        # close() 的排空/回调/重试总预算：防止永不返回的 agent.close() 挂死停机；
        # 超时后标记 _close_pending 并在下一次 close() 时继续收尾。
        self.close_wait_timeout_seconds = 15.0
        # stalled 移除（失败/超时的延迟 close）的最大重试次数。
        self.close_retry_budget = 3
        # 每个 Agent 最多保留的会话数，超出按最旧淘汰（session_id 由模型自由提供）
        self.max_sessions_per_agent = 100

    def register(self, name: str, agent: AgentLike) -> None:
        if self._closed:
            raise RuntimeError("AgentRegistry is closed")
        if name in self._agents:
            raise ValueError(f"Agent already registered: {name}")
        if self._is_agent_in_use(agent):
            raise ValueError(
                "Agent instance has already been registered and cannot be reused or aliased"
            )
        self._next_generation += 1
        registration = _Registration(name, agent, self._next_generation)
        self._agents[name] = agent
        self._registrations[name] = registration
        self._remember_agent(agent)

    def _is_agent_in_use(self, agent: AgentLike) -> bool:
        """同一实例是否仍被注册表以活跃状态持有（别名/重用防护）。

        弱引用历史覆盖「已移除但仍存活」的实例；对不可弱引用的实例，扫描当前
        活跃注册、进行中/已退役移除与关闭中条目，避免永久强持有导致泄漏。
        """
        owner_entry = self._known_agents.get(id(agent))
        owner = (
            owner_entry()
            if isinstance(owner_entry, weakref.ReferenceType)
            else owner_entry
        )
        if owner is agent:
            return True
        for registration in self._registrations.values():
            if registration.agent is agent:
                return True
        for removal in self._removals.values():
            if removal.registration.agent is agent:
                return True
        for close_agent, _close_task in self._agent_close_tasks.values():
            if close_agent is agent:
                return True
        return False

    def _remember_agent(self, agent: AgentLike) -> None:
        owner_key = id(agent)
        try:
            reference = weakref.ref(
                agent,
                lambda completed, key=owner_key: self._known_agent_collected(
                    key, completed
                ),
            )
        except TypeError:
            # 不可弱引用的实例无法在不永久强持有的前提下记住其身份；
            # 活跃期安全由 register() 的扫描检查保证，移除完成后即释放。
            return
        self._known_agents[owner_key] = reference

    def _known_agent_collected(
        self, owner_key: int, reference: weakref.ReferenceType[AgentLike]
    ) -> None:
        # A later object may have reused the same id before this callback runs.
        if self._known_agents.get(owner_key) is reference:
            self._known_agents.pop(owner_key, None)

    def unregister(self, name: str) -> AgentLike | None:
        if self._closed:
            raise RuntimeError("AgentRegistry is closed")
        registration = self._remove_registration(name)
        if registration is None:
            return None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Without a running loop the registry cannot own an asynchronous
            # drain. Hand the instance to the caller without retaining a second
            # close owner.
            generation = registration.generation
            tracked = set(self._in_flight.pop(generation, ()))
            tracked.update(self._delegates.pop(generation, ()))
            for task in tracked:
                self._consume_task_result(task)
            return registration.agent
        self._start_removal(registration, self.drain_timeout_seconds)
        return registration.agent

    async def unregister_and_drain(
        self, name: str, *, drain_timeout_seconds: float | None = None
    ) -> AgentLike | None:
        """注销单个 Agent 并排空其在途委托。

        顺序：先移除注册并清理会话 → 等待/取消该 Agent 的在途任务 →
        任务结束后关闭实例。拒绝取消的任务会被强引用持有并延迟关闭，调用方仍在
        有限时间内返回。不影响其他 Agent 的在途调用。
        """
        operation = self._ensure_unregister(name, drain_timeout_seconds)
        if operation is None:
            return None
        # The registry owns this operation. Cancelling one unload caller must not
        # cancel the drain after the agent has already been removed.
        return await asyncio.shield(operation)

    def _ensure_unregister(
        self, name: str, drain_timeout_seconds: float | None
    ) -> asyncio.Task | None:
        registration = self._remove_registration(name)
        if registration is not None:
            return self._start_removal(registration, drain_timeout_seconds)
        removal = self._latest_removal(name)
        if removal is None:
            return None
        if removal.operation is not None and not removal.operation.done():
            return removal.operation
        if removal.retired or removal.finishing:
            return asyncio.create_task(
                self._return_removed_agent(removal.registration.agent)
            )
        return self._start_removal(
            removal.registration, drain_timeout_seconds, removal=removal
        )

    @staticmethod
    async def _return_removed_agent(agent: AgentLike) -> AgentLike:
        return agent

    def _remove_registration(self, name: str) -> _Registration | None:
        registration = self._registrations.pop(name, None)
        if registration is None:
            return None
        self._agents.pop(name, None)
        self._clear_agent_sessions(name)
        return registration

    def _latest_removal(self, name: str) -> _Removal | None:
        matches = [
            removal
            for removal in self._removals.values()
            if removal.registration.name == name
        ]
        return max(matches, key=lambda item: item.registration.generation, default=None)

    def _start_removal(
        self,
        registration: _Registration,
        drain_timeout_seconds: float | None,
        *,
        removal: _Removal | None = None,
    ) -> asyncio.Task:
        timeout = (
            self.drain_timeout_seconds
            if drain_timeout_seconds is None
            else drain_timeout_seconds
        )
        generation = registration.generation
        if removal is None:
            removal = self._new_removal(registration)
        operation = asyncio.create_task(self._drain_removed_agent(removal, timeout))
        removal.operation = operation
        self._unregister_tasks[generation] = operation
        operation.add_done_callback(
            lambda completed, token=generation: self._unregister_done(token, completed)
        )
        return operation

    def _new_removal(self, registration: _Registration) -> _Removal:
        generation = registration.generation
        invokes = set(self._in_flight.pop(generation, ()))
        delegates = set(self._delegates.pop(generation, ()))
        removal = _Removal(registration, invokes | delegates, delegates)
        self._removals[generation] = removal
        return removal

    def _discard_removal_tasks(
        self, removal: _Removal, tasks: set[asyncio.Task]
    ) -> None:
        for task in tasks:
            self._consume_task_result(task)
        removal.tasks.difference_update(tasks)
        removal.delegates.difference_update(tasks)

    def _pending_removal_tasks(self, removal: _Removal) -> set[asyncio.Task]:
        done = {task for task in removal.tasks if task.done()}
        self._discard_removal_tasks(removal, done)
        return set(removal.tasks)

    async def _drain_removed_agent(
        self, removal: _Removal, timeout: float
    ) -> AgentLike:
        agent = removal.registration.agent
        pending = self._pending_removal_tasks(removal)
        if pending:
            done, still_pending = await asyncio.wait(pending, timeout=timeout)
            self._discard_removal_tasks(removal, done)
            pending_delegates = still_pending & removal.delegates
            pending_invokes = still_pending - removal.delegates
            # Wrappers own cancellation of their inner invokes. Cancelling both
            # concurrently can interrupt cooperative invoke cleanup.
            for task in pending_delegates:
                self._mark_drained(task)
            stubborn_delegates = await self._cancel_wrappers(
                pending_delegates, timeout=timeout
            )
            pending_invokes = {task for task in pending_invokes if not task.done()}
            if stubborn_delegates:
                # A delegate wrapper is already cancelling and awaiting its
                # invoke. Do not concurrently inject another cancellation into
                # cooperative cleanup owned by that wrapper.
                stubborn_invokes = pending_invokes
            else:
                for task in pending_invokes:
                    self._mark_drained(task)
                stubborn_invokes = await self._cancel_and_wait(
                    list(pending_invokes), timeout=timeout
                )
            still_pending = stubborn_delegates | stubborn_invokes
        else:
            still_pending = set()
        if still_pending:
            removal.tasks = still_pending
            removal.delegates.intersection_update(still_pending)
            self._retire(removal)
        else:
            removal.tasks.clear()
            removal.delegates.clear()
            await self._close_removed_agent(removal)
            if removal.retired:
                generation = removal.registration.generation
                removal.retired = False
                self._retired.pop(generation, None)
        return agent

    async def _close_removed_agent(self, removal: _Removal) -> None:
        try:
            await self._close_agent_once(removal.registration.agent)
        except BaseException as error:
            removal.last_error = error
            raise
        else:
            removal.last_error = None

    def _unregister_done(self, generation: int, operation: asyncio.Task) -> None:
        if self._unregister_tasks.get(generation) is operation:
            self._unregister_tasks.pop(generation, None)
        removal = self._removals.get(generation)
        if removal is None or removal.operation is not operation:
            self._consume_task_result(operation)
            return
        removal.operation = None
        if operation.cancelled():
            removal.last_error = RuntimeError("Agent removal operation was cancelled")
        else:
            error = operation.exception()
            if error is not None:
                removal.last_error = error
            elif not removal.retired:
                removal.last_error = None
                self._removals.pop(generation, None)
        self._consume_task_result(operation)

    def _clear_agent_sessions(self, name: str) -> None:
        prefix = f"{name}:"
        for session_key in list(self._sessions):
            if session_key.startswith(prefix):
                self._sessions.pop(session_key, None)
        for session_key in list(self._session_locks):
            if session_key.startswith(prefix) and not self._session_lock_users.get(
                session_key
            ):
                self._session_locks.pop(session_key, None)

    @property
    def names(self) -> list[str]:
        return list(self._agents)

    def snapshot(self) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "description": getattr(agent, "description", ""),
            }
            for name, agent in self._agents.items()
        ]

    def __len__(self) -> int:
        return len(self._agents)

    def __bool__(self) -> bool:
        return bool(self._agents)

    def list_agents(self, name: str | None = None) -> str:
        if not self._agents:
            return "No agents available"

        if name is None:
            lines = [f"- {n}: {a.description}" for n, a in self._agents.items()]
            return "Available agents:\n" + "\n".join(lines)

        agent = self._agents.get(name)
        if not agent:
            return f"Agent '{name}' not found"

        return f"Agent {name}: {agent.description}"

    async def delegate(
        self,
        agent: str | None = None,
        task: str | None = None,
        tasks: list[dict] | None = None,
        previous_response: str | None = None,
        session_id: str | None = None,
        context: str | None = None,
    ) -> str:
        if tasks is not None:
            if not isinstance(context, (str, type(None))):
                return "Invalid context parameter: expected a string or None"
            if not isinstance(tasks, list) or not tasks:
                return "Invalid batch tasks: each task must include non-empty 'agent' and 'task' strings"
            for index, item in enumerate(tasks):
                if not isinstance(item, Mapping):
                    return "Invalid batch tasks: each task must include non-empty 'agent' and 'task' strings"
                validation_error = self._delegate_argument_error(
                    item.get("agent"),
                    item.get("task"),
                    item.get("previous_response"),
                    item.get("session_id"),
                    context,
                )
                if validation_error is None:
                    continue
                if (
                    validation_error == "Missing agent or task parameter"
                    or validation_error.startswith(
                        ("Invalid agent parameter", "Invalid task parameter")
                    )
                ):
                    return "Invalid batch tasks: each task must include non-empty 'agent' and 'task' strings"
                return f"Invalid batch task at index {index}: {validation_error}"
            coros = [
                self.delegate(
                    agent=t["agent"],
                    task=t["task"],
                    previous_response=t.get("previous_response"),
                    session_id=t.get("session_id"),
                    context=context,
                )
                for t in tasks
            ]
            results = await asyncio.gather(*coros, return_exceptions=True)
            rendered: list[str] = []
            for t, result in zip(tasks, results):
                if isinstance(result, BaseException):
                    rendered.append(
                        f"{t['agent']}: Agent failed: {type(result).__name__}: {result}"
                    )
                else:
                    rendered.append(f"{t['agent']}: {result}")
            return "\n\n".join(rendered)

        validation_error = self._delegate_argument_error(
            agent, task, previous_response, session_id, context
        )
        if validation_error is not None:
            return validation_error

        if self._closed:
            return "Agent registry is closed"

        registration = self._registrations.get(agent)
        if registration is None:
            return f"Agent '{agent}' not found"
        generation = registration.generation
        delegate_task = asyncio.current_task()
        if delegate_task is not None:
            self._delegates.setdefault(generation, set()).add(delegate_task)

        try:
            session_key = self._session_key(agent, session_id)
            if session_key:
                # Lock the full read/invoke/write transaction for one session.
                lock = self._session_locks.setdefault(session_key, asyncio.Lock())
                self._session_lock_users[session_key] = (
                    self._session_lock_users.get(session_key, 0) + 1
                )
                try:
                    async with lock:
                        return await self._delegate_once(
                            registration,
                            task,
                            session_key,
                            previous_response,
                            context,
                        )
                finally:
                    users = self._session_lock_users.get(session_key, 1) - 1
                    if users:
                        self._session_lock_users[session_key] = users
                    else:
                        self._session_lock_users.pop(session_key, None)
                        if session_key not in self._sessions:
                            self._session_locks.pop(session_key, None)
            return await self._delegate_once(
                registration, task, None, previous_response, context
            )
        except asyncio.CancelledError:
            # 仅排空/关闭主动取消（预先标记）的委托转成友好文本；外部取消
            # （wait_for 超时、调用方取消、编排器停机）必须传播 CancelledError。
            if delegate_task is not None and delegate_task in self._drained_tasks:
                if self._closed:
                    return f"Agent '{agent}' cancelled: registry closed"
                return f"Agent '{agent}' unloaded"
            raise
        finally:
            if delegate_task is not None:
                delegates = self._delegates.get(generation)
                if delegates is not None:
                    delegates.discard(delegate_task)
                    if not delegates:
                        self._delegates.pop(generation, None)

    @staticmethod
    def _delegate_argument_error(
        agent: object,
        task: object,
        previous_response: object,
        session_id: object,
        context: object,
    ) -> str | None:
        if agent is None or task is None:
            return "Missing agent or task parameter"
        if not isinstance(agent, str):
            return "Invalid agent parameter: expected a string"
        if not isinstance(task, str):
            return "Invalid task parameter: expected a string"
        if not agent.strip() or not task.strip():
            return "Missing agent or task parameter"
        if not isinstance(previous_response, (str, type(None))):
            return "Invalid previous_response parameter: expected a string or None"
        if not isinstance(session_id, (str, type(None))):
            return "Invalid session_id parameter: expected a string or None"
        if not isinstance(context, (str, type(None))):
            return "Invalid context parameter: expected a string or None"
        return None

    async def _delegate_once(
        self,
        registration: _Registration,
        task: str,
        session_key: str | None,
        previous_response: str | None,
        context: str | None,
    ) -> str:
        agent = registration.name
        agent_obj = registration.agent
        generation = registration.generation
        if self._registrations.get(agent) is not registration:
            return f"Agent '{agent}' not found"
        messages = list(self._sessions.get(session_key, [])) if session_key else []
        if previous_response and previous_response.strip():
            messages.append({"role": "assistant", "content": previous_response.strip()})
        messages.append({"role": "user", "content": task})

        invoke = asyncio.create_task(
            agent_obj.invoke(
                {
                    "messages": messages,
                    "_delegate_context": context.strip() if context else "",
                }
            )
        )
        self._in_flight.setdefault(generation, set()).add(invoke)
        invoke.add_done_callback(
            lambda completed, token=generation: self._invoke_done(token, completed)
        )
        try:
            if self._registrations.get(agent) is not registration:
                # 卸载竞态：创建任务期间该 agent 已被 unregister_and_drain 移除，
                # 取消本次调用，避免旧插件代码继续运行
                invoke.cancel()
                await self._cancel_and_wait(
                    [invoke], timeout=self.drain_timeout_seconds
                )
                return f"Agent '{agent}' not found"
            done, pending = await asyncio.wait(
                {invoke}, timeout=self.delegate_timeout_seconds
            )
            if pending:
                # 超时：先取消再等待任务真正结束，避免在途任务脱离 _in_flight 跟踪造成泄漏
                invoke.cancel()
                await self._cancel_and_wait(
                    [invoke], timeout=self.drain_timeout_seconds
                )
                return f"Agent '{agent}' timed out after {self.delegate_timeout_seconds:.0f}s"
            try:
                result = cast(Any, done.pop().result())
            except asyncio.CancelledError:
                if invoke in self._drained_tasks:
                    # 卸载/关闭竞态：invoke 被排空取消，该 agent 已卸载或注册表
                    # 已关闭，返回友好文本而不是把 CancelledError 上抛
                    if self._closed:
                        return f"Agent '{agent}' cancelled: registry closed"
                    return f"Agent '{agent}' unloaded"
                raise
        except asyncio.CancelledError:
            # 外层 delegate 任务被取消时，内层 invoke 必须一并取消并等待完成
            invoke.cancel()
            await self._cancel_and_wait([invoke], timeout=self.drain_timeout_seconds)
            if asyncio.current_task() in self._drained_tasks:
                if self._closed:
                    return f"Agent '{agent}' cancelled: registry closed"
                return f"Agent '{agent}' unloaded"
            raise
        finally:
            if invoke.done():
                self._invoke_done(generation, invoke)
        if not isinstance(result, dict):
            return f"Agent '{agent}' returned invalid state: {type(result).__name__}"
        messages_list = result.get("messages")
        if not isinstance(messages_list, list) or not messages_list:
            return f"Agent '{agent}' returned invalid state: missing messages"
        last_message = messages_list[-1]
        if (
            not isinstance(last_message, dict)
            or last_message.get("role") != "assistant"
        ):
            return f"Agent '{agent}' returned invalid state: missing final assistant message"
        content = last_message.get("content")
        if not isinstance(content, str) or not content.strip():
            return f"Agent '{agent}' returned invalid state: invalid assistant content"
        result_text = content
        if session_key and self._registrations.get(agent) is registration:
            # 回生竞态防护：invoke 期间该 agent 已被卸载（unregister 清会话）时不再写回，
            # 否则会话复活且热重载后的新 Agent 会继承旧历史；结果仍返回给调用方
            self._sessions[session_key] = self._trim_session(
                [
                    *messages,
                    {"role": "assistant", "content": result_text},
                ]
            )
            self._trim_sessions(agent)
        return result_text

    @staticmethod
    def _session_key(agent: str, session_id: str | None) -> str | None:
        session = session_id.strip() if session_id is not None else ""
        if not session:
            return None
        return f"{agent}:{session}"

    @staticmethod
    def _trim_session(messages: list[dict], *, max_messages: int = 16) -> list[dict]:
        system_messages = [
            message for message in messages if message.get("role") == "system"
        ]
        rest = [message for message in messages if message.get("role") != "system"]
        return [*system_messages[:1], *rest[-max_messages:]]

    def _trim_sessions(self, agent: str) -> None:
        """按 Agent 限制会话数量，超出按最旧淘汰（含对应的空闲锁）。"""
        prefix = f"{agent}:"
        keys = [key for key in self._sessions if key.startswith(prefix)]
        overflow = len(keys) - self.max_sessions_per_agent
        if overflow <= 0:
            return
        for key in keys[:overflow]:
            self._sessions.pop(key, None)
            if not self._session_lock_users.get(key):
                self._session_locks.pop(key, None)

    def _invoke_done(self, generation: int, task: asyncio.Task) -> None:
        self._consume_task_result(task)
        tasks = self._in_flight.get(generation)
        if tasks is not None:
            tasks.discard(task)
            if not tasks:
                self._in_flight.pop(generation, None)

    def _retire(self, removal: _Removal) -> None:
        generation = removal.registration.generation
        if removal.retired:
            return
        removal.retired = True
        self._retired[generation] = removal
        for task in list(removal.tasks):
            task.add_done_callback(
                lambda completed, token=generation: self._retired_task_done(
                    token, completed
                )
            )
        self._start_retired_finisher(removal)

    def _retired_task_done(self, generation: int, task: asyncio.Task) -> None:
        self._consume_task_result(task)
        removal = self._retired.get(generation)
        if removal is None:
            return
        removal.tasks.discard(task)
        removal.delegates.discard(task)
        self._start_retired_finisher(removal)

    def _start_retired_finisher(self, removal: _Removal) -> None:
        generation = removal.registration.generation
        if (
            self._retired.get(generation) is not removal
            or removal.finishing
            or self._pending_removal_tasks(removal)
        ):
            return
        removal.finishing = True
        close_task = asyncio.create_task(self._finish_retired(removal))
        self._track_callback_task(close_task)

    async def _finish_retired(self, removal: _Removal) -> None:
        generation = removal.registration.generation
        try:
            await self._close_removed_agent(removal)
        except BaseException:
            # The callback no longer owns this removal after failure. A later
            # close pass may retry it within the persistent retry budget.
            removal.retired = False
            self._retired.pop(generation, None)
            raise
        else:
            removal.retired = False
            self._retired.pop(generation, None)
            self._removals.pop(generation, None)
        finally:
            removal.finishing = False

    def _track_callback_task(self, task: asyncio.Task) -> None:
        self._callback_tasks.add(task)
        task.add_done_callback(self._callback_task_done)

    def _callback_task_done(self, task: asyncio.Task) -> None:
        self._callback_tasks.discard(task)
        self._consume_task_result(task)

    async def _close_agent_once(self, agent: AgentLike) -> None:
        owner_key = id(agent)
        entry = self._agent_close_tasks.get(owner_key)
        if entry is not None and entry[1].done():
            self._agent_close_tasks.pop(owner_key, None)
            self._consume_task_result(entry[1])
            entry = None
        if entry is None:
            close_task = asyncio.create_task(self._close_agent(agent))
            self._agent_close_tasks[owner_key] = (agent, close_task)
            close_task.add_done_callback(
                lambda completed, key=owner_key: self._agent_close_done(key, completed)
            )
        else:
            close_task = entry[1]
        await asyncio.shield(close_task)

    def _agent_close_done(self, owner_key: int, close_task: asyncio.Task) -> None:
        entry = self._agent_close_tasks.get(owner_key)
        if entry is not None and entry[1] is close_task:
            self._agent_close_tasks.pop(owner_key, None)
        self._consume_task_result(close_task)

    @staticmethod
    async def _close_agent(agent: AgentLike) -> None:
        await agent.close()

    @staticmethod
    def _consume_task_result(task: asyncio.Task) -> None:
        """取出任务结果/异常，避免 "Task exception was never retrieved" 告警。"""
        if task.done():
            try:
                task.exception()
            except (asyncio.CancelledError, Exception):
                pass

    def _mark_drained(self, task: asyncio.Task) -> None:
        """记录由排空/关闭主动取消的任务；仅被标记的任务可把取消转成友好文本。"""
        self._drained_tasks.add(task)
        task.add_done_callback(self._drained_task_done)

    def _drained_task_done(self, task: asyncio.Task) -> None:
        self._drained_tasks.discard(task)

    async def _cancel_and_wait(
        self, tasks: list[asyncio.Task], *, timeout: float
    ) -> set[asyncio.Task]:
        """取消任务并等待真正结束。

        顽固 agent（忽略 CancelledError 继续阻塞）在取消宽限超时后 detach：
        不再等待，挂 done_callback 取结果防告警，避免卸载/回复管线永久挂死。

        注意：
        1. 不能用 ``asyncio.wait_for(asyncio.gather(...))``——wait_for 超时取消
           gather 时会等待子任务完成取消，顽固任务会反过来挂死 wait_for。
        2. 不能连续两次 ``task.cancel()``——任务未处理第一次取消时第二次会被
           asyncio 去重忽略；必须「cancel → 等待任务运行 → 再 cancel」循环，
           才能对「忽略前 N 次取消」的 agent 生效。
        """
        if not tasks:
            return set()
        # 取消生效宽限独立于第一重等待超时：至少 0.2s（给正常 agent 处理取消留出
        # 余量），最多 5s（顽固任务在此超时后 detach）
        grace = min(max(timeout * 2, 0.2), 5.0)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        pending = set(tasks)
        while pending:
            for task in pending:
                task.cancel()
            remain = deadline - loop.time()
            if remain <= 0:
                break
            # Give cooperative cancellation cleanup time to finish before another
            # cancel; otherwise repeated cancellation can interrupt that cleanup.
            done, pending = await asyncio.wait(pending, timeout=min(0.1, remain))
            for task in done:
                AgentRegistry._consume_task_result(task)
        for task in pending:
            if not task.done():
                task.add_done_callback(AgentRegistry._consume_task_result)
            else:
                AgentRegistry._consume_task_result(task)
        return pending

    async def _cancel_wrappers(
        self, tasks: set[asyncio.Task], *, timeout: float
    ) -> set[asyncio.Task]:
        if not tasks:
            return set()
        for task in tasks:
            task.cancel()
        grace = min(max(timeout * 2, 0.2), 5.0)
        done, pending = await asyncio.wait(tasks, timeout=grace)
        for task in done:
            self._consume_task_result(task)
        for task in pending:
            task.add_done_callback(self._consume_task_result)
        return pending

    async def _wait_for_owned_tasks(
        self, tasks: set[asyncio.Task], *, deadline: float
    ) -> set[asyncio.Task]:
        """Wait within the close budget without cancelling registry-owned work."""
        pending = {task for task in tasks if not task.done()}
        for task in tasks - pending:
            self._consume_task_result(task)
        if not pending:
            return set()
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return pending
        done, pending = await asyncio.wait(pending, timeout=remaining)
        for task in done:
            self._consume_task_result(task)
        return pending

    def _finalize_done_removals(self) -> None:
        for generation, removal in list(self._removals.items()):
            operation = removal.operation
            if operation is not None and operation.done():
                self._unregister_done(generation, operation)

    def _ensure_retired_finishers(self) -> None:
        for removal in list(self._retired.values()):
            self._start_retired_finisher(removal)

    def _stalled_removals(self) -> list[_Removal]:
        stalled: list[_Removal] = []
        for removal in list(self._removals.values()):
            operation = removal.operation
            pending_tasks = self._pending_removal_tasks(removal)
            if (
                removal.retired
                or removal.finishing
                or pending_tasks
                or (operation is not None and not operation.done())
            ):
                continue
            stalled.append(removal)
        return stalled

    def _orphaned_removals(self) -> list[_Removal]:
        orphaned: list[_Removal] = []
        for removal in list(self._removals.values()):
            operation = removal.operation
            pending_tasks = self._pending_removal_tasks(removal)
            if (
                removal.retired
                or removal.finishing
                or not pending_tasks
                or (operation is not None and not operation.done())
            ):
                continue
            orphaned.append(removal)
        return orphaned

    def _running_removals(self) -> list[_Removal]:
        return [
            removal
            for removal in self._removals.values()
            if removal.operation is not None and not removal.operation.done()
        ]

    @staticmethod
    def _close_errors(removals: list[_Removal]) -> list[BaseException]:
        errors: list[BaseException] = []
        seen: set[int] = set()
        for removal in removals:
            error = removal.last_error
            if error is not None and id(error) not in seen:
                seen.add(id(error))
                errors.append(error)
        return errors

    async def close(self) -> None:
        """关闭注册表：停止接受新委托，等待在途调用（超时取消），随后关闭并清空。"""
        needs_followup = (
            self._close_pending
            or bool(self._callback_tasks)
            or bool(self._removals)
            or bool(self._unregister_tasks)
        )
        if self._close_task is None or (
            self._close_task.done()
            and (
                self._close_task.cancelled()
                or self._close_task.exception() is not None
                or needs_followup
            )
        ):
            self._closed = True
            self._close_task = asyncio.create_task(self._close_impl())
        await asyncio.shield(self._close_task)

    async def _close_impl(self) -> None:
        # _close_pending describes only this pass. A later pass that finishes all
        # surviving work must be able to clear a previous timeout/failure.
        self._close_pending = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.close_wait_timeout_seconds
        operations = {
            operation
            for name in list(self._registrations)
            if (operation := self._ensure_unregister(name, None)) is not None
        }
        operations.update(self._unregister_tasks.values())
        if operations:
            pending = await self._wait_for_owned_tasks(operations, deadline=deadline)
            self._finalize_done_removals()
            if pending:
                self._close_pending = True

        # Callback-owned retired removals finish first. Only after a callback
        # failure relinquishes ownership may the stalled-removal retry path run.
        while not self._close_pending:
            self._finalize_done_removals()
            self._ensure_retired_finishers()
            callbacks = set(self._callback_tasks)
            if callbacks:
                pending = await self._wait_for_owned_tasks(callbacks, deadline=deadline)
                for completed in callbacks - pending:
                    self._callback_task_done(completed)
                self._finalize_done_removals()
                if pending:
                    self._close_pending = True
                    break

            inactive = [*self._stalled_removals(), *self._orphaned_removals()]
            if not inactive:
                self._ensure_retired_finishers()
                if self._callback_tasks:
                    continue
                break
            retry_limit = max(0, self.close_retry_budget)
            retryable = [
                removal for removal in inactive if removal.close_retries < retry_limit
            ]
            if not retryable:
                self._close_pending = True
                break
            retries: set[asyncio.Task] = set()
            for removal in retryable:
                removal.close_retries += 1
                retries.add(
                    self._start_removal(removal.registration, None, removal=removal)
                )
            pending = await self._wait_for_owned_tasks(retries, deadline=deadline)
            self._finalize_done_removals()
            if pending:
                self._close_pending = True
                break

        self._sessions.clear()
        for session_key in list(self._session_locks):
            if not self._session_lock_users.get(session_key):
                self._session_locks.pop(session_key, None)

        self._finalize_done_removals()
        for callback in list(self._callback_tasks):
            if callback.done():
                self._callback_task_done(callback)
        running = self._running_removals()
        stalled = self._stalled_removals()
        orphaned = self._orphaned_removals()
        callbacks = [task for task in self._callback_tasks if not task.done()]
        incomplete = list(dict.fromkeys([*running, *stalled, *orphaned]))
        if incomplete or callbacks:
            self._close_pending = True
            message = (
                "AgentRegistry close incomplete: "
                f"{len(incomplete)} removal(s) and "
                f"{len(callbacks)} callback(s) still pending"
            )
            errors = self._close_errors(incomplete)
            if errors:
                details = "; ".join(
                    f"{type(error).__name__}: {error}" for error in errors
                )
                raise RuntimeError(
                    f"{message}; underlying errors: {details}"
                ) from BaseExceptionGroup("AgentRegistry close errors", errors)
            raise RuntimeError(message)
        self._close_pending = False
