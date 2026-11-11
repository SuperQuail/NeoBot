"""可切换适配器门面：同一对象内承载 OneBot / QQ 官方协议后端，可单通道也可双通道。

为什么需要门面：适配器实例被技能、表情包、文件服务、命令服务、事件网关等
几十处直接持有引用。切换通道时重建适配器对象等于全量重新装配。这里保持
对象身份不变，内部原地增删/重启后端，事件统一汇入门面自己的
``EventDispatcher``，因此订阅跨切换存活。

mode=dual 时两个后端同时运行、同时可交互：后端事件在 sink 处标注
``neobot_channel``，send / call_api 未显式指定通道时按「会话出现在哪条通道」
自动选路（默认 OneBot），显式指定不可用通道时返回明确失败而不是静默改投。
事件处理期间还会钉住来源通道（见 ``channel_context``）：处理中发起的 call_api
与查询便捷方法默认查同一条通道，官方会话的 get_msg / get_group_member_* 不会
落到 OneBot 后端。

切换期间 ``send`` / ``call_api`` 立即返回明确失败而不是阻塞等待：回复编排
与定时任务不应被一次通道切换拖住。
"""

from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Any, Dict, Iterator, Optional

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.eventing import (
    EventDispatcher,
    EventHandlerFunc,
    EventNamespace,
    Rule,
    Subscription,
    _HandlerRegistration,
    extract_event_model,
)
from neobot_adapter.factory import AdapterSettings
from neobot_adapter.model import response
from neobot_adapter.onebot import OneBotAdapter
from neobot_adapter.onebot.receiver.settings import ReverseWsSettings

_MODES = frozenset({"onebot", "official", "dual"})
#: 通道固定顺序：默认通道在前（展示、遍历与自动选路都按这个顺序）。
_CHANNELS = ("onebot", "official")
_DEFAULT_CHANNEL = "onebot"
_SWITCHING_MESSAGE = "适配器正在切换通道，请稍后重试"
#: dual 模式停止的兜底上限：单个后端 stop 异常/挂死不能拖住整个运行时拆除。
_STOP_TIMEOUT_SECONDS = 30.0
#: 会话→通道记录的容量上限；超出淘汰最久未活跃的，被淘汰会话退回默认选路。
_CONVERSATION_LIMIT = 8192
#: 可在运行期原地重启对应后端、需要单独比较的配置分组。
_QQ_FIELDS = (
    "qq_appid",
    "qq_client_secret",
    "qq_base_url",
    "qq_token_url",
    "qq_portal_host",
)
_ONEBOT_FIELDS = ("reverse_ws_host", "reverse_ws_port", "reverse_ws_access_token")
#: OneBot 形状的查询便捷方法：必须按事件来源通道选后端，不能固定委托 OneBot。
_CHANNEL_METHODS = frozenset(
    {
        "get_friend_list",
        "get_stranger_info",
        "get_group_list",
        "get_group_member_list",
        "get_group_member_info",
        "get_friend_msg_history",
        "get_group_msg_history",
        "get_msg",
        "get_forward_msg",
    }
)
#: 查询方法失败时用哪种响应模型返回明确 failed（get_forward_msg 返回原始 dict）。
_CHANNEL_METHOD_RESPONSES: Dict[str, Any] = {
    "get_friend_list": response.GetFriendListResponse,
    "get_stranger_info": response.StrangerInfoResponse,
    "get_group_list": response.GetGroupListResponse,
    "get_group_member_list": response.GetGroupMemberListResponse,
    "get_group_member_info": response.GetGroupMemberInfoResponse,
    "get_friend_msg_history": response.GetHistoryMsgListResponse,
    "get_group_msg_history": response.GetHistoryMsgListResponse,
    "get_msg": response.GetSignalMsgResponse,
    "get_forward_msg": None,
}
#: 事件处理期（含其派生的任务）的来源通道；call_api 未显式指定时跟随它。
_EVENT_CHANNEL: ContextVar[Optional[str]] = ContextVar("neobot_event_channel", default=None)


def _normalize_channel(channel: Any) -> Optional[str]:
    name = str(channel or "").strip().casefold()
    return name if name in _CHANNELS else None


def current_channel() -> Optional[str]:
    """当前事件处理上下文所属通道；后台任务/面板等无事件上下文时返回 None。"""
    return _EVENT_CHANNEL.get()


@contextmanager
def channel_context(channel: Optional[str]) -> Iterator[None]:
    """在 with 块内把未显式指定通道的请求钉到 channel；块内新建任务会继承。"""
    normalized = _normalize_channel(channel)
    token = _EVENT_CHANNEL.set(normalized)
    from neobot_adapter.request._proxy import request_channel_context, reset_request_channel

    proxy_token, _ = request_channel_context(normalized)
    try:
        yield
    finally:
        reset_request_channel(proxy_token)
        _EVENT_CHANNEL.reset(token)


def _unknown_mode_message(mode: Any) -> str:
    return f"未知适配器模式: {mode}。可选值: onebot, official, dual"


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _response_data(result: Any) -> dict[str, Any]:
    """从 OneBot 形状的成功响应里取 data；失败响应返回空 dict。"""
    if not isinstance(result, dict):
        return {}
    if str(result.get("status", "ok")).strip().casefold() == "failed":
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


class _FacadeCore:
    """门面 core：speaking_policy 写穿到所有后端，其余属性委托默认后端。

    本体只在装配时 ``adapter.core.speaking_policy = ...`` 一次；双通道下必须
    让两条后端都拿到同一份策略，而调用方仍然按单个后端 core 的方式使用它。
    """

    def __init__(self, adapter: "SwitchableAdapter") -> None:
        object.__setattr__(self, "_adapter", adapter)

    @property
    def speaking_policy(self) -> Any:
        return self._adapter._speaking_policy

    @speaking_policy.setter
    def speaking_policy(self, policy: Any) -> None:
        self._adapter._speaking_policy = policy
        self._adapter._apply_policy_all()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter._default_backend().core, name)


class SwitchableAdapter:
    def __init__(
        self,
        settings: AdapterSettings,
        *,
        logger: Optional[Logger] = None,
        packet_callback: Any = None,
        sandbox_data: Any = None,
        data_dir: Any = None,
    ) -> None:
        # sandbox_data 只对 local 模式有意义；门面只承载 onebot / official / dual，
        # 保留参数是为了与 create_adapter 的装配入口一致。
        del sandbox_data
        mode = str(getattr(settings, "mode", "onebot") or "onebot").strip().casefold()
        if mode not in _MODES:
            raise ValueError(_unknown_mode_message(getattr(settings, "mode", "")))
        self._settings: AdapterSettings = settings
        self._mode: str = mode
        self._data_dir = data_dir if data_dir is not None else (getattr(settings, "data_dir", "") or None)
        self._logger: Logger = logger if logger is not None else NullLogger()
        self._packet_callback = packet_callback
        self._dispatcher = EventDispatcher(self._logger)
        self._lock = asyncio.Lock()
        self._switching = False
        self._speaking_policy: Any = None
        self._accounts: Dict[str, int] = {}
        # 会话（kind, id）→ 出现过消息的通道；自动选路用，只增不删有上限。
        self._conversation_channels: Dict[tuple[str, str], set[str]] = {}
        self._onebot_settings = self._resolve_onebot_settings(settings)
        self._backends: Dict[str, Any] = {
            channel: self._build_backend(channel, settings) for channel in self._channels_for_mode(mode)
        }
        self._facade_core = _FacadeCore(self)
        self.on = EventNamespace(self)

    # ── 公开状态 ────────────────────────────────────────────────────

    @property
    def active_mode(self) -> str:
        """当前生效模式：onebot / official / dual。"""
        return self._mode

    @property
    def active_channels(self) -> tuple[str, ...]:
        """当前模式启用的通道（不保证已连接）。"""
        return tuple(channel for channel in _CHANNELS if channel in self._backends)

    @property
    def connected_channels(self) -> tuple[str, ...]:
        """当前已连接的通道；单通道未连接时为 ()。"""
        return tuple(
            channel for channel in _CHANNELS if channel in self._backends and bool(self._backends[channel].connected)
        )

    @property
    def switching(self) -> bool:
        """切换事务是否正在进行（面板/调用方据此展示与快速失败）。"""
        return self._switching

    @property
    def connected(self) -> bool:
        return any(bool(backend.connected) for backend in self._backends.values())

    @property
    def requires_connection_wait(self) -> bool:
        return any(bool(backend.requires_connection_wait) for backend in self._backends.values())

    @property
    def http_url(self) -> str:
        return str(getattr(self._default_backend(), "http_url", "") or "")

    @property
    def ws_url(self) -> str:
        return str(getattr(self._default_backend(), "ws_url", "") or "")

    @property
    def bind_state(self) -> Any:
        """官方后端的扫码绑定状态；当前模式未启用官方后端时为 None。"""
        backend = self._backends.get("official")
        return getattr(backend, "bind_state", None) if backend is not None else None

    @property
    def settings(self) -> ReverseWsSettings:
        """OneBot 反向 WS 设置：有 onebot 后端时直接委托，否则用保存值。"""
        backend = self._backends.get("onebot")
        backend_settings = getattr(backend, "settings", None)
        if isinstance(backend_settings, ReverseWsSettings):
            return backend_settings
        return self._onebot_settings

    def reconfigure(self, settings: ReverseWsSettings) -> None:
        """写入新的反向 WS 监听设置；不触碰运行中的接收线程（由控制面重启）。"""
        self._onebot_settings = settings
        self._settings = replace(
            self._settings,
            reverse_ws_host=settings.host,
            reverse_ws_port=settings.port,
            reverse_ws_access_token=settings.access_token,
        )
        backend = self._backends.get("onebot")
        if backend is not None:
            backend.reconfigure(settings)

    @property
    def core(self) -> Any:
        """门面 core：speaking_policy 挂到所有后端，其余委托默认后端。"""
        return self._facade_core

    # ── 账号 ────────────────────────────────────────────────────────

    @property
    def accounts(self) -> Dict[str, int]:
        """已解析的通道账号（channel → QQ 号）；未解析的通道不在这里。"""
        return dict(self._accounts)

    def account_for(self, channel: str) -> int:
        """指定通道的机器人 QQ 号；未知/未解析返回 0。"""
        return int(self._accounts.get(str(channel or "").strip().casefold(), 0))

    async def ensure_accounts(self) -> Dict[str, int]:
        """补齐已连接通道的机器人 QQ 号；已解析的通道不再发请求（可频繁调用）。"""
        pending = [
            channel
            for channel in self.active_channels
            if channel not in self._accounts and bool(self._backends[channel].connected)
        ]
        if pending:
            results = await asyncio.gather(*(self._query_account(channel) for channel in pending))
            for channel, account in zip(pending, results):
                if account > 0:
                    self._accounts[channel] = account
        return dict(self._accounts)

    async def _query_account(self, channel: str) -> int:
        result = await self.call_api("get_login_info", {}, 5.0, channel=channel)
        return _to_int(_response_data(result).get("user_id"))

    # ── 生命周期 ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._accounts.clear()
        if self._mode != "dual":
            await self._default_backend().start()
            return
        backends = list(self._backends.items())
        results = await asyncio.gather(*(backend.start() for _, backend in backends), return_exceptions=True)
        failures = 0
        for (channel, _), result in zip(backends, results):
            if isinstance(result, BaseException):
                failures += 1
                self._logger.error(
                    "适配器通道启动失败，其余通道继续运行",
                    channel=channel,
                    error_type=type(result).__name__,
                    error=str(result),
                )
        if failures and failures == len(backends):
            # 两条都起不来才等同于单通道的启动失败语义。
            raise next(result for result in results if isinstance(result, BaseException))

    async def stop(self) -> None:
        if self._mode != "dual":
            await self._default_backend().stop()
            return
        backends = list(self._backends.values())

        async def _stop_all() -> list[Any]:
            return await asyncio.gather(*(backend.stop() for backend in backends), return_exceptions=True)

        try:
            results = await asyncio.wait_for(_stop_all(), timeout=_STOP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self._logger.error("适配器通道停止超时，已放弃等待", timeout_seconds=_STOP_TIMEOUT_SECONDS)
            return
        for backend, result in zip(backends, results):
            if isinstance(result, BaseException):
                self._logger.error(
                    "适配器通道停止失败",
                    error_type=type(result).__name__,
                    error=str(result),
                )

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        """等待任一通道连上；单通道直接委托后端的等待。"""
        if self._mode != "dual":
            return bool(self._default_backend().wait_for_connection(timeout))
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if self.connected:
                return True
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            time.sleep(0.05 if remaining is None else min(0.05, remaining))

    # ── 发送与 API：显式通道优先，否则自动选路 ──────────────────────

    async def call_api(
        self,
        action: str,
        params: Dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
        channel: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self._switching:
            return {
                "status": "failed",
                "retcode": -1,
                "data": None,
                "message": _SWITCHING_MESSAGE,
            }
        requested = str(channel or "").strip().casefold()
        if requested in ("", "auto"):
            # 事件处理中默认跟事件来源通道：官方会话的查询不能落到 OneBot。
            requested = current_channel()
        selected, error = self._select_channel(None, requested)
        if error is not None:
            return {"status": "failed", "retcode": -1, "data": None, "message": error}
        return await self._backends[selected].call_api(action, params, timeout, wait_response=wait_response)

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
        channel: Optional[str] = None,
        proactive: bool = False,
    ) -> response.SendMsgResponse:
        if self._switching:
            return response.SendMsgResponse(status="failed", retcode=-1, message=_SWITCHING_MESSAGE)
        selected, error = self._select_channel(conversation, channel)
        if error is not None:
            return response.SendMsgResponse(status="failed", retcode=-1, message=error)
        extra = {"proactive": True} if proactive and selected == "official" else {}
        return await self._backends[selected].send(
            conversation, message, timeout, wait_response=wait_response, **extra
        )

    # ── 通道切换 ────────────────────────────────────────────────────

    async def switch(self, mode: str) -> tuple[bool, str]:
        """切到指定模式（含 dual）；失败时旧后端会重新启动并保持可用。"""
        target = str(mode or "").strip().casefold()
        if target not in _MODES:
            return False, _unknown_mode_message(mode)
        if self._switching:
            return False, _SWITCHING_MESSAGE
        async with self._lock:
            if target == self._mode:
                self._settings = replace(self._settings, mode=target)
                return True, f"当前已是 {target} 模式"
            error = await self._apply_mode(target, self._settings)
            if error is not None:
                return False, error
            return True, f"已切换到 {target} 模式"

    async def apply_channel_config(self, config: Any) -> tuple[bool, str]:
        """按新配置让通道生效（热重载入口，不重建适配器对象）。

        保留配置未变的已启动后端，只停被移除的、启新增的、重启配置变化的那个。
        """
        settings = self._settings_from_config(config)
        if settings is None:
            return True, "配置中没有 [adapter] 段，适配器保持不变"
        target = settings.mode.strip().casefold()
        if target not in _MODES:
            return False, _unknown_mode_message(settings.mode)
        if self._switching:
            return False, _SWITCHING_MESSAGE
        async with self._lock:
            same_mode = target == self._mode
            target_channels = self._channels_for_mode(target)
            restart = [
                channel
                for channel in target_channels
                if channel in self._backends and self._changed_for(channel, settings)
            ]
            added = [channel for channel in target_channels if channel not in self._backends]
            removed = [channel for channel in self._backends if channel not in target_channels]
            if same_mode and not (restart or added or removed):
                self._settings = replace(settings, mode=target)
                self._onebot_settings = self._resolve_onebot_settings(self._settings)
                return True, "适配器配置未变化"
            error = await self._apply_mode(target, settings)
            if error is not None:
                return False, error
            if same_mode and restart:
                return True, f"{target} 适配器已按新配置重启"
            return True, f"已切换到 {target} 模式"

    # ── 事件入口：订阅挂在门面上，与后端实现无关 ────────────────────

    async def publish(self, event: Dict[str, Any], channel: Optional[str] = None) -> None:
        """后端事件汇入口（作为各后端的 event_sink）；channel 标注事件来自哪条通道。"""
        if channel is not None:
            event = {**event, "neobot_channel": channel}
            self._remember_conversation(channel, event)
        else:
            channel = _normalize_channel(event.get("neobot_channel"))
        with channel_context(channel):
            await self._dispatcher.publish(event)

    def channels_for_conversation(self, conversation: ConversationRef) -> tuple[str, ...]:
        """该会话出现过消息的通道（固定顺序）；从未出现过返回 ()。

        官方不提供 group_openid ↔ QQ 群号映射（群信息接口只返回 openid/群名等，
        不同 AppID 的 openid 也不同），同一个真实群在两条通道就是两个会话 id；
        这里只按「本进程见过的会话 id」判断通道，不做跨通道猜测关联。
        """

        channels = self._conversation_channels.get((conversation.kind, str(conversation.id)), ())
        return tuple(channel for channel in _CHANNELS if channel in channels)

    def subscribe(
        self,
        event_type: Any,
        handler: EventHandlerFunc,
        **filters: Any,
    ) -> Subscription:
        if isinstance(event_type, str) and "post_type" not in filters:
            filters["post_type"] = event_type
        return self._subscribe(handler, **filters)

    def on_event(
        self,
        func: Optional[EventHandlerFunc] = None,
        *,
        post_type: Optional[str] = None,
        message_type: Optional[str] = None,
        notice_type: Optional[str] = None,
        request_type: Optional[str] = None,
        meta_event_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        rule: Optional[Rule] = None,
        priority: int = 0,
    ) -> Any:
        def decorator(handler: EventHandlerFunc) -> EventHandlerFunc:
            self._register_handler(
                handler,
                post_type=post_type,
                message_type=message_type,
                notice_type=notice_type,
                request_type=request_type,
                meta_event_type=meta_event_type,
                sub_type=sub_type,
                rule=rule,
                priority=priority,
            )
            return handler

        if func is not None:
            return decorator(func)
        return decorator

    def _subscribe(
        self,
        handler: EventHandlerFunc,
        *,
        post_type: Optional[str] = None,
        message_type: Optional[str] = None,
        notice_type: Optional[str] = None,
        request_type: Optional[str] = None,
        meta_event_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        rule: Optional[Rule] = None,
        priority: int = 0,
    ) -> Subscription:
        event_model = extract_event_model(handler)
        registration = _HandlerRegistration(
            handler=handler,
            is_async=inspect.iscoroutinefunction(handler),
            post_type=post_type,
            message_type=message_type,
            notice_type=notice_type,
            request_type=request_type,
            meta_event_type=meta_event_type,
            sub_type=sub_type,
            rule=rule,
            priority=priority,
            event_model=event_model,
        )
        return self._dispatcher.subscribe(registration)

    def _register_handler(self, handler: EventHandlerFunc, **filters: Any) -> None:
        self._subscribe(handler, **filters)

    def _filters_from_path(
        self,
        path: tuple[str, ...],
        *,
        group: bool,
        private: bool,
        sub_type: Optional[str],
    ) -> Dict[str, Optional[str]]:
        filters: Dict[str, Optional[str]] = {
            "post_type": None,
            "message_type": None,
            "notice_type": None,
            "request_type": None,
            "meta_event_type": None,
            "sub_type": sub_type,
        }
        if not path:
            return filters
        root = path[0]
        if root == "message":
            filters["post_type"] = "message"
            if len(path) > 1:
                filters["message_type"] = path[1]
        elif root == "notice":
            filters["post_type"] = "notice"
            if len(path) > 1:
                filters["notice_type"] = path[1]
        elif root == "request":
            filters["post_type"] = "request"
            if len(path) > 1:
                filters["request_type"] = path[1]
        elif root == "meta_event":
            filters["post_type"] = "meta_event"
            if len(path) > 1:
                filters["meta_event_type"] = path[1]
        if group:
            filters["message_type"] = "group"
        if private:
            filters["message_type"] = "private"
        return filters

    # ── 内部：自动选路 ──────────────────────────────────────────────

    def _select_channel(
        self,
        conversation: Optional[ConversationRef],
        channel: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """返回（选中通道, 错误描述）。显式通道不可用时不改投，直接返回错误。"""
        requested = str(channel or "").strip().casefold()
        if requested not in ("", "auto"):
            if requested not in _CHANNELS:
                return None, f"未知适配器通道: {channel}。可选值: onebot, official, auto"
            if not self._channel_usable(requested):
                suffix = "未启用" if requested not in self._backends else "未连接"
                return None, f"适配器通道 {requested} {suffix}，无法使用"
            return requested, None
        if len(self._backends) == 1:
            # 单通道模式保持旧语义：直接交给后端，由它返回自己的失败原因。
            return next(iter(self._backends)), None
        preferred = self._preferred_channel(conversation)
        for candidate in (preferred, *[name for name in _CHANNELS if name != preferred]):
            if self._channel_usable(candidate):
                return candidate, None
        return None, "没有可用的适配器通道（均未启用或未连接）"

    def _preferred_channel(self, conversation: Optional[ConversationRef]) -> str:
        # 只在官方通道出现过消息时用官方；两条都出现或从未出现都走默认通道。
        if conversation is not None and self.channels_for_conversation(conversation) == ("official",):
            return "official"
        return _DEFAULT_CHANNEL

    def _channel_usable(self, channel: str) -> bool:
        backend = self._backends.get(channel)
        return backend is not None and bool(backend.connected)

    def _remember_conversation(self, channel: str, event: Dict[str, Any]) -> None:
        if event.get("post_type") != "message":
            return
        kind = str(event.get("message_type") or "")
        target = event.get("group_id") if kind == "group" else event.get("user_id") if kind == "private" else None
        if target in (None, ""):
            return
        key = (kind, str(target))
        channels = self._conversation_channels.pop(key, None) or set()
        channels.add(channel)
        self._conversation_channels[key] = channels
        while len(self._conversation_channels) > _CONVERSATION_LIMIT:
            self._conversation_channels.pop(next(iter(self._conversation_channels)))

    # ── 内部：后端构造与切换事务 ────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """未在门面上定义的属性/方法（get_group_list 等）按 onebot 优先委托后端。"""
        if name in _CHANNEL_METHODS:
            return self._channel_method(name)
        try:
            backends = object.__getattribute__(self, "_backends")
        except AttributeError:
            raise AttributeError(name) from None
        for channel in _CHANNELS:
            backend = backends.get(channel)
            if backend is None:
                continue
            try:
                return getattr(backend, name)
            except AttributeError:
                continue
        raise AttributeError(name)

    def _default_backend(self) -> Any:
        backend = self._backends.get(_DEFAULT_CHANNEL)
        if backend is not None:
            return backend
        return next(iter(self._backends.values()))

    def _channel_method(self, name: str) -> Any:
        """OneBot 形状查询方法的门面版本：按显式/事件来源通道选后端。"""

        async def invoke(*args: Any, channel: Optional[str] = None, **kwargs: Any) -> Any:
            if self._switching:
                return self._method_failure(name, _SWITCHING_MESSAGE)
            requested = str(channel or "").strip().casefold()
            if requested in ("", "auto"):
                requested = current_channel()
            selected, error = self._select_channel(None, requested)
            if error is not None:
                return self._method_failure(name, error)
            return await getattr(self._backends[selected], name)(*args, **kwargs)

        return invoke

    @staticmethod
    def _method_failure(name: str, message: str) -> Any:
        model = _CHANNEL_METHOD_RESPONSES.get(name)
        if model is None:
            return {"status": "failed", "retcode": -1, "data": None, "message": message}
        return model(status="failed", retcode=-1, message=message)

    def _event_sink_for(self, channel: str) -> Any:
        """把后端事件汇入门面分发器，并标注来源通道。"""

        async def sink(event: Dict[str, Any]) -> None:
            await self.publish(event, channel=channel)

        return sink

    def _build_backend(self, channel: str, settings: AdapterSettings) -> Any:
        if channel == "official":
            # 延迟导入：官方协议依赖 cryptography / qrcode，onebot 部署不必装齐。
            from neobot_adapter.official.adapter import OfficialAdapter
            from neobot_adapter.official.settings import OfficialSettings

            backend: Any = OfficialAdapter(
                OfficialSettings.from_adapter_settings(settings, data_dir=self._data_dir),
                logger=self._logger,
                event_sink=self._event_sink_for(channel),
                data_dir=self._data_dir,
            )
        else:
            backend = OneBotAdapter(
                logger=self._logger,
                packet_callback=self._packet_callback,
                host=settings.reverse_ws_host or None,
                port=settings.reverse_ws_port or None,
                access_token=settings.reverse_ws_access_token,
                event_sink=self._event_sink_for(channel),
            )
        self._apply_policy(backend)
        return backend

    async def _apply_mode(self, target: str, settings: AdapterSettings) -> Optional[str]:
        """把后端集合调整为 target 模式；失败时回滚并返回错误描述，成功返回 None。"""
        target_channels = self._channels_for_mode(target)
        restart = [
            channel for channel in target_channels if channel in self._backends and self._changed_for(channel, settings)
        ]
        added = [channel for channel in target_channels if channel not in self._backends]
        removed = [channel for channel in self._backends if channel not in target_channels]
        if not (restart or added or removed):
            return None

        previous_mode = self._mode
        previous_settings = self._settings
        previous_backends = dict(self._backends)
        started: Dict[str, Any] = {}
        self._switching = True
        try:
            for channel in removed + restart:
                self._capture_policy(previous_backends[channel])
                await self._stop_backend(previous_backends[channel])
            try:
                for channel in restart + added:
                    backend = self._build_backend(channel, settings)
                    await backend.start()
                    started[channel] = backend
            except Exception as exc:
                return await self._rollback_mode(
                    target=target,
                    error=exc,
                    started=started,
                    previous_mode=previous_mode,
                    previous_settings=previous_settings,
                    previous_backends=previous_backends,
                    reverted=removed + restart,
                )
            for channel in removed:
                self._backends.pop(channel, None)
                self._accounts.pop(channel, None)
            for channel in restart + added:
                self._backends[channel] = started[channel]
                self._accounts.pop(channel, None)
            self._mode = target
            self._settings = replace(settings, mode=target)
            self._onebot_settings = self._resolve_onebot_settings(self._settings)
            return None
        finally:
            self._switching = False

    async def _rollback_mode(
        self,
        *,
        target: str,
        error: Exception,
        started: Dict[str, Any],
        previous_mode: str,
        previous_settings: AdapterSettings,
        previous_backends: Dict[str, Any],
        reverted: list[str],
    ) -> str:
        """停掉已启动的新后端、重启被停掉的旧后端，然后恢复旧模式与设置。"""
        for backend in started.values():
            await self._stop_backend(backend)
        rollback_errors: list[str] = []
        for channel in reverted:
            try:
                await previous_backends[channel].start()
            except Exception as exc:
                rollback_errors.append(f"{channel}: {type(exc).__name__}: {exc}")
                self._logger.error(
                    "回滚旧适配器失败，该通道当前不可用",
                    channel=channel,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        self._mode = previous_mode
        self._settings = previous_settings
        self._onebot_settings = self._resolve_onebot_settings(previous_settings)
        self._logger.error(
            "适配器通道变更失败，已回滚",
            target_mode=target,
            error_type=type(error).__name__,
            error=str(error),
        )
        suffix = f"；旧适配器恢复失败：{rollback_errors[0]}" if rollback_errors else "；已回滚到旧适配器"
        return f"{target} 适配器启动失败：{error}{suffix}"

    async def _stop_backend(self, backend: Any) -> None:
        try:
            await backend.stop()
        except Exception as exc:
            # 旧后端停不干净也要继续：不切换同样是不可用状态。
            self._logger.error(
                "停止适配器失败，继续应用通道变更",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _capture_policy(self, backend: Any) -> None:
        policy = getattr(getattr(backend, "core", None), "speaking_policy", None)
        if policy is not None:
            self._speaking_policy = policy

    def _apply_policy(self, backend: Any) -> None:
        core = getattr(backend, "core", None)
        if core is not None and self._speaking_policy is not None:
            core.speaking_policy = self._speaking_policy

    def _apply_policy_all(self) -> None:
        for backend in self._backends.values():
            self._apply_policy(backend)

    def _changed_for(self, channel: str, settings: AdapterSettings) -> bool:
        fields = _QQ_FIELDS if channel == "official" else _ONEBOT_FIELDS
        return self._changed(settings, fields)

    def _changed(self, settings: AdapterSettings, fields: tuple[str, ...]) -> bool:
        return any(getattr(self._settings, name) != getattr(settings, name) for name in fields)

    @staticmethod
    def _channels_for_mode(mode: str) -> tuple[str, ...]:
        return _CHANNELS if mode == "dual" else (mode,)

    def _settings_from_config(self, config: Any) -> Optional[AdapterSettings]:
        adapter_cfg = getattr(config, "adapter", None)
        if adapter_cfg is None:
            return None
        base = self._settings
        return replace(
            base,
            mode=str(getattr(adapter_cfg, "mode", base.mode) or base.mode),
            reverse_ws_host=str(getattr(adapter_cfg, "reverse_ws_host", base.reverse_ws_host) or ""),
            reverse_ws_port=int(getattr(adapter_cfg, "reverse_ws_port", base.reverse_ws_port) or 0),
            reverse_ws_access_token=str(
                getattr(adapter_cfg, "reverse_ws_access_token", base.reverse_ws_access_token) or ""
            ),
            # 官方凭据可只放在环境变量（装配阶段已合入 base）；配置里留空时保留
            # 装配值，避免热重载把 env-only 的机器人打回扫码绑定。
            qq_appid=str(getattr(adapter_cfg, "qq_appid", "") or base.qq_appid),
            qq_client_secret=str(
                getattr(adapter_cfg, "qq_client_secret", "") or base.qq_client_secret
            ),
            qq_base_url=str(getattr(adapter_cfg, "qq_base_url", base.qq_base_url) or base.qq_base_url),
            qq_token_url=str(getattr(adapter_cfg, "qq_token_url", base.qq_token_url) or base.qq_token_url),
            qq_portal_host=str(getattr(adapter_cfg, "qq_portal_host", base.qq_portal_host) or base.qq_portal_host),
        )

    @staticmethod
    def _resolve_onebot_settings(settings: AdapterSettings) -> ReverseWsSettings:
        return ReverseWsSettings.resolve(
            host=str(getattr(settings, "reverse_ws_host", "") or "") or None,
            port=int(getattr(settings, "reverse_ws_port", 0) or 0) or None,
            access_token=str(getattr(settings, "reverse_ws_access_token", "") or ""),
        )
