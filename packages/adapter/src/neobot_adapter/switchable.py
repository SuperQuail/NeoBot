"""可切换适配器门面：同一对象内原地切换 OneBot / QQ 官方协议后端。

为什么需要门面：适配器实例被技能、表情包、文件服务、命令服务、事件网关等
几十处直接持有引用。切换通道时重建适配器对象等于全量重新装配。这里保持
对象身份不变，内部原地停止旧后端、启动新后端，事件统一汇入门面自己的
``EventDispatcher``，因此订阅跨切换存活。

切换期间 ``send`` / ``call_api`` 立即返回明确失败而不是阻塞等待：回复编排
与定时任务不应被一次通道切换拖住。
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from typing import Any, Dict, Optional

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

_MODES = frozenset({"onebot", "official"})
_SWITCHING_MESSAGE = "适配器正在切换通道，请稍后重试"
# 可在运行期原地重启对应后端、需要单独比较的配置分组。
_QQ_FIELDS = (
    "qq_appid",
    "qq_client_secret",
    "qq_markdown",
    "qq_base_url",
    "qq_token_url",
    "qq_portal_host",
)
_ONEBOT_FIELDS = ("reverse_ws_host", "reverse_ws_port", "reverse_ws_access_token")


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
        # sandbox_data 只对 local 模式有意义；门面只承载 onebot / official，
        # 保留参数是为了与 create_adapter 的装配入口一致。
        del sandbox_data
        mode = str(getattr(settings, "mode", "onebot") or "onebot").strip().casefold()
        if mode not in _MODES:
            raise ValueError(f"未知适配器模式: {getattr(settings, 'mode', '')}。可选值: onebot, official")
        self._settings: AdapterSettings = settings
        self._active_mode: str = mode
        self._data_dir = data_dir if data_dir is not None else (getattr(settings, "data_dir", "") or None)
        self._logger: Logger = logger if logger is not None else NullLogger()
        self._packet_callback = packet_callback
        self._dispatcher = EventDispatcher(self._logger)
        self._lock = asyncio.Lock()
        self._switching = False
        self._speaking_policy: Any = None
        self._onebot_settings = self._resolve_onebot_settings(settings)
        self._backend = self._build_backend(mode, settings)
        self.on = EventNamespace(self)

    # ── 公开状态 ────────────────────────────────────────────────────

    @property
    def active_mode(self) -> str:
        """当前生效的通道：onebot / official。"""
        return self._active_mode

    @property
    def switching(self) -> bool:
        """切换事务是否正在进行（面板/调用方据此展示与快速失败）。"""
        return self._switching

    @property
    def connected(self) -> bool:
        return bool(self._backend.connected)

    @property
    def requires_connection_wait(self) -> bool:
        return bool(self._backend.requires_connection_wait)

    @property
    def http_url(self) -> str:
        return str(getattr(self._backend, "http_url", "") or "")

    @property
    def ws_url(self) -> str:
        return str(getattr(self._backend, "ws_url", "") or "")

    @property
    def bind_state(self) -> Any:
        """官方后端的扫码绑定状态；onebot 模式下为 None。"""
        return getattr(self._backend, "bind_state", None)

    @property
    def settings(self) -> ReverseWsSettings:
        """OneBot 反向 WS 设置：active 后端是 onebot 时直接委托，否则用保存值。"""
        backend_settings = getattr(self._backend, "settings", None)
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
        if self._active_mode == "onebot":
            self._backend.reconfigure(settings)

    @property
    def core(self) -> Any:
        """active 后端的 core（发言策略等挂在它上面）。"""
        return self._backend.core

    # ── 生命周期 ────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._backend.start()

    async def stop(self) -> None:
        await self._backend.stop()

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        return bool(self._backend.wait_for_connection(timeout))

    async def call_api(
        self,
        action: str,
        params: Dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if self._switching:
            return {
                "status": "failed",
                "retcode": -1,
                "data": None,
                "message": _SWITCHING_MESSAGE,
            }
        return await self._backend.call_api(action, params, timeout, wait_response=wait_response)

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        if self._switching:
            return response.SendMsgResponse(status="failed", retcode=-1, message=_SWITCHING_MESSAGE)
        return await self._backend.send(conversation, message, timeout, wait_response=wait_response)

    # ── 通道切换 ────────────────────────────────────────────────────

    async def switch(self, mode: str) -> tuple[bool, str]:
        """切到指定通道；失败时旧后端会重新启动并保持可用。"""
        target = str(mode or "").strip().casefold()
        if target not in _MODES:
            return False, f"未知适配器模式: {mode}。可选值: onebot, official"
        if self._switching:
            return False, _SWITCHING_MESSAGE
        async with self._lock:
            if target == self._active_mode:
                self._settings = replace(self._settings, mode=target)
                return True, f"当前已是 {target} 模式"
            error = await self._swap_backend(target, self._settings)
            if error is not None:
                return False, error
            return True, f"已切换到 {target} 模式"

    async def apply_channel_config(self, config: Any) -> tuple[bool, str]:
        """按新配置让通道生效（热重载入口，不重建适配器对象）。"""
        settings = self._settings_from_config(config)
        if settings is None:
            return True, "配置中没有 [adapter] 段，适配器保持不变"
        target = settings.mode.strip().casefold()
        if target not in _MODES:
            return False, f"未知适配器模式: {settings.mode}。可选值: onebot, official"
        if self._switching:
            return False, _SWITCHING_MESSAGE
        async with self._lock:
            if target != self._active_mode:
                error = await self._swap_backend(target, settings)
                if error is not None:
                    return False, error
                return True, f"已切换到 {target} 模式"
            restart = (target == "onebot" and self._changed(settings, _ONEBOT_FIELDS)) or (
                target == "official" and self._changed(settings, _QQ_FIELDS)
            )
            if restart:
                error = await self._swap_backend(target, settings)
                if error is not None:
                    return False, error
                return True, f"{target} 适配器已按新配置重启"
            self._settings = replace(settings, mode=target)
            self._onebot_settings = self._resolve_onebot_settings(self._settings)
            return True, "适配器配置未变化"

    # ── 事件入口：订阅挂在门面上，与后端实现无关 ────────────────────

    async def publish(self, event: Dict[str, Any]) -> None:
        """后端事件汇入口（作为后端的 event_sink）。"""
        await self._dispatcher.publish(event)

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

    # ── 内部：后端构造与切换事务 ────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """未在门面上定义的属性/方法（get_group_list 等）委托给 active 后端。"""
        try:
            backend = object.__getattribute__(self, "_backend")
        except AttributeError:
            raise AttributeError(name) from None
        return getattr(backend, name)

    def _build_backend(self, mode: str, settings: AdapterSettings) -> Any:
        if mode == "official":
            # 延迟导入：官方协议依赖 cryptography / qrcode，onebot 部署不必装齐。
            from neobot_adapter.official.adapter import OfficialAdapter
            from neobot_adapter.official.settings import OfficialSettings

            backend: Any = OfficialAdapter(
                OfficialSettings.from_adapter_settings(settings, data_dir=self._data_dir),
                logger=self._logger,
                event_sink=self.publish,
                data_dir=self._data_dir,
            )
        else:
            backend = OneBotAdapter(
                logger=self._logger,
                packet_callback=self._packet_callback,
                host=settings.reverse_ws_host or None,
                port=settings.reverse_ws_port or None,
                access_token=settings.reverse_ws_access_token,
                event_sink=self.publish,
            )
        self._apply_policy(backend)
        return backend

    async def _swap_backend(self, mode: str, settings: AdapterSettings) -> Optional[str]:
        """停旧启新并替换 active 后端；失败时回滚旧后端并返回错误描述。"""
        previous = self._backend
        self._switching = True
        try:
            self._capture_policy(previous)
            try:
                await previous.stop()
            except Exception as exc:
                # 旧后端停不干净也要继续尝试新后端：不切换同样是不可用状态。
                self._logger.error(
                    "停止旧适配器失败，继续尝试启动新适配器",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            try:
                backend = self._build_backend(mode, settings)
                await backend.start()
            except Exception as exc:
                self._logger.error(
                    "新适配器启动失败，回滚旧适配器",
                    target_mode=mode,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                rollback_error = await self._restart_previous(previous)
                suffix = f"；旧适配器恢复失败：{rollback_error}" if rollback_error else "；已回滚到旧适配器"
                return f"{mode} 适配器启动失败：{exc}{suffix}"
            self._backend = backend
            self._active_mode = mode
            self._settings = replace(settings, mode=mode)
            self._onebot_settings = self._resolve_onebot_settings(self._settings)
            return None
        finally:
            self._switching = False

    async def _restart_previous(self, backend: Any) -> str:
        try:
            await backend.start()
        except Exception as exc:
            self._logger.error(
                "回滚旧适配器失败，当前没有可用的事件入口",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return f"{type(exc).__name__}: {exc}"
        return ""

    def _capture_policy(self, backend: Any) -> None:
        policy = getattr(getattr(backend, "core", None), "speaking_policy", None)
        if policy is not None:
            self._speaking_policy = policy

    def _apply_policy(self, backend: Any) -> None:
        core = getattr(backend, "core", None)
        if core is not None and self._speaking_policy is not None:
            core.speaking_policy = self._speaking_policy

    def _changed(self, settings: AdapterSettings, fields: tuple[str, ...]) -> bool:
        return any(getattr(self._settings, name) != getattr(settings, name) for name in fields)

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
            qq_appid=str(getattr(adapter_cfg, "qq_appid", base.qq_appid) or ""),
            qq_client_secret=str(getattr(adapter_cfg, "qq_client_secret", base.qq_client_secret) or ""),
            qq_markdown=bool(getattr(adapter_cfg, "qq_markdown", base.qq_markdown)),
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
