from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable, Dict, Optional

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.models import ConversationRef

from neobot_adapter.eventing import (
    EventDispatcher,
    EventHandlerFunc,
    EventNamespace,
    Rule,
    Subscription,
    _HandlerRegistration,
    extract_event_model,
)
from neobot_adapter.model import response
from neobot_adapter.onebot.receiver.core import AdapterCore
from neobot_adapter.onebot.receiver.settings import ReverseWsSettings
from neobot_adapter.request._proxy import bind_core, unbind_core
from neobot_adapter.request.websocket import WebSocketAPI
from neobot_adapter.utils.parse import safe_parse_model


class OneBotAdapter:
    #: 接收器停止的总宽限（秒）。
    #:
    #: core.stop 偶尔会返回 False（旧接收线程尚未退出）；这里最多重试到该宽限，
    #: 之后**放弃继续等待并报告明确错误**，而不是无条件无限重试 —— 后者会让整个
    #: 运行时的拆除永久卡住（现场：每 8 秒刷一次的停止日志 + 运行时再也无法重建，
    #: 只能杀进程）。监听端口在 server.close() 时已释放，放弃等待不会占住端口。
    _STOP_TOTAL_GRACE_SECONDS = 16.0

    def __init__(
        self,
        *,
        max_queue_size: int = 1000,
        logger: Optional[Logger] = None,
        packet_callback: Callable[[Dict[str, Any]], None] | None = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        access_token: str = "",
    ) -> None:
        self._logger: Logger = logger if logger is not None else NullLogger()
        self._core = AdapterCore(
            max_queue_size=max_queue_size,
            packet_callback=packet_callback,
            host=host,
            port=port,
            access_token=access_token,
        )
        self._dispatcher = EventDispatcher(self._logger)
        self._dispatch_task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()
        self._api: Optional[WebSocketAPI] = None
        self.on = EventNamespace(self)

    @property
    def requires_connection_wait(self) -> bool:
        return True

    @property
    def connected(self) -> bool:
        """当前是否至少有一条 OneBot 反向 WebSocket 连接处于活跃状态。"""
        return bool(self._core.active_connections)

    @property
    def receiver_abandoned(self) -> bool:
        """接收器是否已被放弃（旧线程卡死，进程内无法重建，只能重启进程）。"""
        return self._core.abandoned

    @property
    def http_url(self) -> str:
        """反向 WS 模式没有本地 HTTP 服务；显式声明以统一 RuntimeAdapter 契约。"""
        return ""

    @property
    def ws_url(self) -> str:
        """反向 WS 模式由外部框架主动连入，本端无客户端地址。"""
        return ""

    @property
    def core(self) -> AdapterCore:
        return self._core

    @property
    def settings(self) -> ReverseWsSettings:
        """当前解析后的反向 WS 监听设置（供状态展示与重配比较）。"""
        return self._core.settings

    def reconfigure(self, settings: ReverseWsSettings) -> None:
        """写入新的监听设置；不触碰运行中的接收线程。

        「停下旧服务 → 用新设置重启」由控制面（AdapterSupervisor）编排。
        """
        self._core.apply_settings(settings)

    @property
    def api(self) -> WebSocketAPI:
        if self._api is None:
            self._api = WebSocketAPI(self._core)
        return self._api

    @property
    def on_message(self) -> EventNamespace:
        return self.on.message

    @property
    def on_notice(self) -> EventNamespace:
        return self.on.notice

    @property
    def on_request(self) -> EventNamespace:
        return self.on.request

    @property
    def on_meta_event(self) -> EventNamespace:
        return self.on.meta_event

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

    async def start(self) -> None:
        if self._dispatch_task is not None and not self._dispatch_task.done():
            return
        self._stopping = asyncio.Event()
        bind_core(self._core)
        try:
            self._core.start()
        except Exception:
            # 接收器拒绝重建（旧线程卡死）：不要把核心绑定与「停止中」状态
            # 留在半启动状态，也不要把异常静默吞掉 —— 上层必须能看见失败。
            unbind_core()
            self._stopping.set()
            raise
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        self._dispatch_task.add_done_callback(self._on_dispatch_task_done)

    async def stop(self) -> None:
        self._stopping.set()
        # 从分发循环内部调用 stop()（例如 QQ 命令触发进入待机 / 软重启）时，等待
        # 自己会先空转到超时、再把自己取消：命令回执与拆除流程都会丢。此时只能
        # 放弃等待，让当前命令先返回，分发循环随后会因 _stopping 退出。
        task = self._dispatch_task
        if task is not None and task is not asyncio.current_task():
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                self._logger.warning("适配器分发循环停止超时，正在取消")
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            except Exception as exc:
                self._logger.warning(
                    "适配器分发循环关闭失败",
                    error=str(exc),
                )
        self._dispatch_task = None
        try:
            deadline = time.monotonic() + self._STOP_TOTAL_GRACE_SECONDS
            while not await asyncio.to_thread(self._core.stop, 8.0):
                # False 表示旧接收线程仍活着，不能向上层报告停止完成。
                # 先按现场语义重试；但**必须有尽头**：否则运行时拆除会永远卡在这里。
                if time.monotonic() >= deadline:
                    self._logger.error(
                        "适配器接收器在宽限期内仍未停止，放弃继续等待；"
                        "监听端口已由 server.close() 释放，重建若失败会显式报错",
                        grace_seconds=self._STOP_TOTAL_GRACE_SECONDS,
                    )
                    break
                self._logger.error(
                    "适配器接收器停止尚未完成，仍在等待守护线程退出；不能启动新运行时"
                )
                await asyncio.sleep(0.1)
        finally:
            unbind_core()

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        return self._core.wait_for_connection(timeout)

    async def call_api(
        self,
        action: str,
        params: Dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> Optional[Dict[str, Any]]:
        return await self._core.call_api(
            action, params, timeout, wait_response=wait_response
        )

    def subscribe(
        self,
        event_type: Any,
        handler: EventHandlerFunc,
        **filters: Any,
    ) -> Subscription:
        if isinstance(event_type, str) and "post_type" not in filters:
            filters["post_type"] = event_type
        return self._subscribe(handler, **filters)

    async def get_friend_list(self, timeout: float = 5.0) -> response.GetFriendListResponse:
        result = await self.call_api("get_friend_list", {}, timeout)
        return safe_parse_model(result, response.GetFriendListResponse)

    async def get_stranger_info(
        self,
        user_id: int,
        timeout: float = 5.0,
    ) -> response.StrangerInfoResponse:
        result = await self.call_api("get_stranger_info", {"user_id": user_id}, timeout)
        return safe_parse_model(result, response.StrangerInfoResponse)

    async def get_group_list(
        self,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupListResponse:
        result = await self.call_api("get_group_list", {"no_cache": no_cache}, timeout)
        return safe_parse_model(result, response.GetGroupListResponse)

    async def get_group_member_list(
        self,
        group_id: int,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupMemberListResponse:
        result = await self.call_api(
            "get_group_member_list",
            {"group_id": group_id, "no_cache": no_cache},
            timeout,
        )
        return safe_parse_model(result, response.GetGroupMemberListResponse)

    async def get_group_member_info(
        self,
        group_id: int,
        user_id: int,
        no_cache: bool = False,
        timeout: float = 5.0,
    ) -> response.GetGroupMemberInfoResponse:
        result = await self.call_api(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id, "no_cache": no_cache},
            timeout,
        )
        return safe_parse_model(result, response.GetGroupMemberInfoResponse)

    async def get_friend_msg_history(
        self,
        user_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        params = {
            "user_id": user_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order,
        }
        result = await self.call_api("get_friend_msg_history", params, timeout)
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_group_msg_history(
        self,
        group_id: int,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        params = {
            "group_id": group_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order,
        }
        result = await self.call_api("get_group_msg_history", params, timeout)
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_msg(
        self,
        message_id: int,
        timeout: float = 5.0,
    ) -> response.GetSignalMsgResponse:
        result = await self.call_api("get_msg", {"message_id": message_id}, timeout)
        return safe_parse_model(result, response.GetSignalMsgResponse)

    async def get_forward_msg(
        self,
        message_id: str,
        timeout: float = 5.0,
    ) -> dict[str, Any] | None:
        """获取合并转发消息的具体内容。"""
        return await self.call_api("get_forward_msg", {"message_id": message_id}, timeout)

    async def send_private_msg(
        self,
        user_id: int,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        if isinstance(message, str):
            payload = {
                "user_id": user_id,
                "message": {"type": "text", "data": {"text": message}},
            }
        else:
            payload = {"user_id": user_id, "message": message}
        result = await self.call_api(
            "send_private_msg", payload, timeout, wait_response=wait_response
        )
        return safe_parse_model(result, response.SendMsgResponse)

    async def send_group_msg(
        self,
        group_id: int,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        if isinstance(message, str):
            payload = {
                "group_id": group_id,
                "message": {"type": "text", "data": {"text": message}},
            }
        else:
            payload = {"group_id": group_id, "message": message}
        result = await self.call_api(
            "send_group_msg", payload, timeout, wait_response=wait_response
        )
        return safe_parse_model(result, response.SendMsgResponse)

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        """统一的消息发送接口；wait_response=False 时不等上游 echo 回执。"""
        if conversation.kind == "private":
            return await self.send_private_msg(
                int(conversation.id), message, timeout, wait_response=wait_response
            )
        else:
            return await self.send_group_msg(
                int(conversation.id), message, timeout, wait_response=wait_response
            )

    async def _dispatch_loop(self) -> None:
        while True:
            if self._stopping.is_set():
                break
            event = await asyncio.to_thread(self._core.get_message, True, 0.1)
            if event is None:
                continue
            try:
                await self._dispatcher.publish(event)
            except Exception as exc:
                # 单条坏事件不得打死事件入口：记录后继续处理后续事件。
                self._logger.error(
                    "事件分发失败，已跳过该事件",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

    def _on_dispatch_task_done(self, task: "asyncio.Task[None]") -> None:
        """分发循环退出必须可观测：否则事件入口会静静死去、无人知晓。"""
        if self._stopping.is_set():
            return
        if task.cancelled():
            self._logger.error("适配器分发循环被取消，事件入口已停止")
            return
        exc = task.exception()
        if exc is None:
            self._logger.warning("适配器分发循环已退出，事件入口已停止")
        else:
            self._logger.error(
                "适配器分发循环异常退出，事件入口已停止",
                error_type=type(exc).__name__,
                error=str(exc),
            )

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
