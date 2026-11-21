"""内嵌 QQ 官方机器人协议的 RuntimeAdapter 实现。

HTTP 发送/上传在 send.py/media.py，事件映射在 events.py，action 分发在
actions.py；这里只做生命周期编排：凭据 → token/网关 → READY → 事件投递，
以及扫码绑定（缺凭据时后台跑，不阻塞启动）与运行期 rebind。
"""

from __future__ import annotations

import asyncio
import inspect
import re
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.speaking import SpeechBlocked

from neobot_adapter.model import response
from neobot_adapter.official import actions
from neobot_adapter.request._proxy import bind_core, unbind_core
from neobot_adapter.utils.parse import safe_parse_model
from neobot_adapter.official.auth import (
    BindState,
    CredentialStore,
    Credentials,
    QrBindFlow,
    TokenProvider,
)
from neobot_adapter.official.events import EventMapper
from neobot_adapter.official.gateway import OfficialGateway
from neobot_adapter.official.identity import IdentityMap, MessageIdMap
from neobot_adapter.official.media import MediaUploader, api_data
from neobot_adapter.official.send import (
    MessageSender,
    OfficialApi,
    PassiveReplyCache,
)
from neobot_adapter.official.settings import OfficialSettings
from neobot_adapter.speaking import check_action, check_speech

#: 启动时等待网关 READY 的上限；超时后启动继续，网关会在后台自动重连。
_CONNECT_TIMEOUT_SECONDS = 15.0
#: 网关停止的兜底上限：stop 绝不能把整个运行时拆除挂死。
_STOP_TIMEOUT_SECONDS = 10.0
#: get_msg 能反查的最近消息条数（官方没有历史消息查询接口）。
_RECENT_MESSAGE_LIMIT = 200
_ROBOT_UIN_PATTERN = re.compile(r"robot_uin(?:=|%3D)(\d+)")


class _OfficialCore:
    """官方适配器的最小 core：发言策略钩子 + request 模块需要的 call_api 代理。"""

    def __init__(self, adapter: "OfficialAdapter") -> None:
        self._adapter = adapter
        self.speaking_policy: Any = None

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None:
        return await self._adapter.call_api(action, params, timeout)

    def call_api_sync(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> dict[str, Any] | None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.call_api(action, params, timeout))
        self._adapter._logger.error("OfficialCore.call_api_sync 不能在已运行的事件循环内调用")
        return None


class OfficialAdapter:
    """QQ 官方机器人协议适配器（official 模式的后端）。"""

    def __init__(
        self,
        settings: OfficialSettings,
        *,
        logger: Logger | None = None,
        event_sink: Any | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger if logger is not None else NullLogger()
        self._event_sink = event_sink
        self._data_dir = Path(data_dir) if data_dir else Path(settings.data_dir)
        self._credentials = CredentialStore(self._data_dir)
        #: 构造时的配置凭据；用于区分凭据来源（配置/环境变量 vs 扫码落盘）。
        self._config_credentials = (
            Credentials(settings.app_id, settings.client_secret)
            if settings.app_id and settings.client_secret
            else None
        )
        self._credentials_source = ""
        self._identity = IdentityMap(
            self._data_dir,
            namespace=self._settings.app_id,
            logger=self._logger,
        )
        self._message_ids = MessageIdMap()
        self._passive = PassiveReplyCache()
        self._media = MediaUploader(self._logger)
        self._mapper = EventMapper(
            message_ids=self._message_ids,
            logger=self._logger,
        )
        self._core = _OfficialCore(self)
        self._token_provider: Any = None
        self._api: OfficialApi | None = None
        self._sender: MessageSender | None = None
        self._gateway: OfficialGateway | None = None
        self._started = False
        self._connected = False
        self._robot_uin = 0
        self._robot_nickname = ""
        #: READY 缺 d.user.id 只告警一次；RESUMED 缺 user 属正常情况，不告警。
        self._missing_ready_openid_warned = False
        self._bound = self._load_credentials() is not None
        self._bind_state = BindState()
        #: 连续登录失败后给面板的说明文案；成功连接后清空。
        self._relogin_notice = ""
        self._bind_flow: QrBindFlow | None = None
        self._bind_task: asyncio.Task[None] | None = None
        self._connected_event = threading.Event()
        self._ready_event = asyncio.Event()
        self._recent_messages: OrderedDict[int, dict[str, Any]] = OrderedDict()
        #: 官方通道的已知用户/群：键是 openid 字符串（旧合成号按迁移表解析后也会是 openid）。
        self._known_users: dict[str, dict[str, Any]] = {}
        self._known_groups: dict[str, dict[str, Any]] = {}

    # ── RuntimeAdapter 契约 ─────────────────────────────────────────

    @property
    def settings(self) -> OfficialSettings:
        return self._settings

    @property
    def core(self) -> _OfficialCore:
        return self._core

    @property
    def requires_connection_wait(self) -> bool:
        """没有凭据时连接不可能建立（要用户扫码），启动不必等连接。"""
        return self._bound

    @property
    def connected(self) -> bool:
        gateway = self._gateway
        return bool(self._started and self._connected and gateway is not None and gateway.connected)

    @property
    def http_url(self) -> str:
        return ""

    @property
    def ws_url(self) -> str:
        return ""

    @property
    def bind_state(self) -> BindState:
        return self._bind_state

    @property
    def bound(self) -> bool:
        return self._bound

    @property
    def robot_uin(self) -> int:
        return self._robot_uin

    @property
    def robot_nickname(self) -> str:
        return self._robot_nickname

    @property
    def identity(self) -> IdentityMap:
        return self._identity

    @property
    def message_ids(self) -> MessageIdMap:
        return self._message_ids

    @property
    def api(self) -> OfficialApi | None:
        return self._api

    @property
    def sender(self) -> MessageSender | None:
        return self._sender

    @property
    def known_users(self) -> dict[str, dict[str, Any]]:
        return self._known_users

    @property
    def known_groups(self) -> dict[str, dict[str, Any]]:
        return self._known_groups

    def get_recent_message(self, message_id: int) -> dict[str, Any] | None:
        return self._recent_messages.get(int(message_id))

    def forget_recent_message(self, message_id: int) -> None:
        self._recent_messages.pop(int(message_id), None)

    async def start(self) -> None:
        """有凭据就直接连；没有凭据则后台拉起扫码绑定，立即返回。"""
        if self._started:
            return
        self._started = True
        # request 子模块全是 OneBot 动作：官方核心绑到 official 通道，双通道运行时
        # 不会覆盖 request 助手默认使用的 onebot 通道。
        bind_core(self._core, "official")
        credentials = self._load_credentials()
        if credentials is None:
            self._logger.warning("QQ 官方机器人尚未绑定，已启动扫码绑定流程；绑定成功后将自动连接")
            self._start_bind_flow()
            return
        try:
            await self._connect(credentials)
        except BaseException:
            self._started = False
            unbind_core("official")
            await self._shutdown_runtime()
            raise

    async def stop(self) -> None:
        """幂等且有时限的停止：先取消扫码，再停网关与 HTTP 会话。"""
        self._started = False
        self._connected = False
        self._connected_event.clear()
        self._ready_event.clear()
        await self._cancel_bind_flow()
        await self._shutdown_runtime()
        unbind_core("official")

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        return self._connected_event.wait(timeout)

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> dict[str, Any] | None:
        values = params if isinstance(params, dict) else {}
        check_action(self._core.speaking_policy, action, values, self._logger)
        return await actions.dispatch(self, action, values, timeout)

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
        proactive: bool = False,
    ) -> response.SendMsgResponse:
        check_speech(self._core.speaking_policy, conversation, self._logger)
        sender = self._sender
        if sender is None:
            return _failed_response("QQ 官方机器人尚未连接，无法发送消息")
        return await sender.send(conversation, message, timeout, proactive=proactive)

    async def rebind(self) -> None:
        """重新发起扫码绑定；绑定成功后用新凭据重连，旧连接在成功前保持。"""
        await self._cancel_bind_flow()
        self._bind_state = BindState()
        self._start_bind_flow()

    async def unbind(self) -> None:
        """删除扫码落盘的凭据并断开；下次启动可重新扫码或改用配置凭据。"""
        self._credentials.delete()
        self._bound = False
        self._bind_state = BindState()
        await self.stop()

    def supports_action(self, action: str) -> bool:
        return actions.supports_action(action)

    async def ensure_robot_identity(self) -> None:
        """缓存机器人自身 uin/openid/昵称（@ 判定与 get_login_info 都要用）。"""
        if self._api is None or (self._robot_uin and self._mapper.bot_openid):
            return
        gateway = self._gateway
        if gateway is None or not gateway.connected:
            return
        try:
            payload = await self._api.request("GET", "/users/@me", timeout=10.0)
        except Exception as exc:
            self._logger.warning("获取官方机器人自身信息失败", error=str(exc))
            return
        data = api_data(payload)
        # READY 缺 user.id 时用 /users/@me 的 id 兜底：群全量消息的 @ 判定要用它。
        openid = str(data.get("id") or data.get("user_openid") or "").strip()
        if openid and openid != self._mapper.bot_openid:
            self._mapper.bot_openid = openid
            self._logger.info("已获取官方机器人 openid", bot_openid=openid)
        nickname = str(data.get("username") or data.get("nickname") or "").strip()
        if nickname:
            self._robot_nickname = nickname
            # 群场景 @bot 的 mention id 与 READY openid 不同，昵称是兜底判定的依据。
            self._mapper.bot_username = nickname
        uin = _extract_robot_uin(data)
        if not uin:
            uin = await self._generate_robot_uin()
        if uin:
            self._robot_uin = uin
            self._mapper.self_id = uin
            self._logger.info("已获取官方机器人账号", robot_uin=uin, nickname=self._robot_nickname)

    # ── OneBot 形状的便捷方法（门面 __getattr__ 直接委托到这里） ──────

    async def get_friend_list(self, timeout: float = 5.0) -> response.GetFriendListResponse:
        result = await self.call_api("get_friend_list", {}, timeout)
        return safe_parse_model(result, response.GetFriendListResponse)

    async def get_stranger_info(self, user_id: int, timeout: float = 5.0) -> response.StrangerInfoResponse:
        result = await self.call_api("get_stranger_info", {"user_id": user_id}, timeout)
        return safe_parse_model(result, response.StrangerInfoResponse)

    async def get_group_list(self, no_cache: bool = False, timeout: float = 5.0) -> response.GetGroupListResponse:
        result = await self.call_api("get_group_list", {"no_cache": no_cache}, timeout)
        return safe_parse_model(result, response.GetGroupListResponse)

    async def get_group_member_list(
        self, group_id: int | str, no_cache: bool = False, timeout: float = 5.0
    ) -> response.GetGroupMemberListResponse:
        result = await self.call_api(
            "get_group_member_list",
            {"group_id": group_id, "no_cache": no_cache},
            timeout,
        )
        return safe_parse_model(result, response.GetGroupMemberListResponse)

    async def get_group_member_info(
        self,
        group_id: int | str,
        user_id: int | str,
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
        user_id: int | str,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        result = await self.call_api(
            "get_friend_msg_history",
            {
                "user_id": user_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
            timeout,
        )
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_group_msg_history(
        self,
        group_id: int | str,
        message_seq: int = 0,
        count: int = 20,
        reverse_order: bool = False,
        timeout: float = 5.0,
    ) -> response.GetHistoryMsgListResponse:
        result = await self.call_api(
            "get_group_msg_history",
            {
                "group_id": group_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
            timeout,
        )
        return safe_parse_model(result, response.GetHistoryMsgListResponse)

    async def get_msg(self, message_id: int, timeout: float = 5.0) -> response.GetSignalMsgResponse:
        result = await self.call_api("get_msg", {"message_id": message_id}, timeout)
        return safe_parse_model(result, response.GetSignalMsgResponse)

    async def get_forward_msg(self, message_id: str, timeout: float = 5.0) -> dict[str, Any] | None:
        return await self.call_api("get_forward_msg", {"message_id": message_id}, timeout)

    async def send_private_msg(
        self,
        user_id: int | str,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        result = await self.call_api(
            "send_private_msg",
            {"user_id": user_id, "message": _normalize_message(message)},
            timeout,
        )
        return safe_parse_model(result, response.SendMsgResponse)

    async def send_group_msg(
        self,
        group_id: int | str,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        result = await self.call_api(
            "send_group_msg",
            {"group_id": group_id, "message": _normalize_message(message)},
            timeout,
        )
        return safe_parse_model(result, response.SendMsgResponse)

    # ── 连接编排 ────────────────────────────────────────────────────

    async def _connect(self, credentials: Credentials) -> None:
        self._apply_credentials(credentials)
        gateway = self._gateway
        if gateway is None:
            raise RuntimeError("官方网关未初始化")
        await gateway.start()
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=_CONNECT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            # 连接失败/极慢时不让启动（以及面板启动流程）卡死：网关会后台重连。
            self._logger.warning(
                "QQ 官方网关未在超时内就绪，启动继续并在后台重连",
                timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
            )

    async def _on_auth_exhausted(self) -> None:
        """连续登录/鉴权失败：停自动重连，按凭据来源决定是否删除落盘凭据并转扫码。"""
        if not self._started:
            return
        if self._credentials_source == "config":
            # 配置/环境变量是用户资产，不静默删除；提示修好配置或清空后改为扫码。
            self._logger.error(
                "配置中的 AppID/AppSecret 失效，请检查配置或清空后重新扫码"
            )
        else:
            self._credentials.delete()
            self._bound = False
            self._logger.error("已删除失效的扫码凭据，请用手机 QQ 重新扫码登录")
        self._relogin_notice = "连续登录失败，请用手机 QQ 重新扫码登录"
        if self._bind_task is None or self._bind_task.done():
            self._bind_state = BindState()
        self._start_bind_flow()

    def _apply_credentials(self, credentials: Credentials) -> None:
        self._credentials_source = (
            "config" if credentials == self._config_credentials else "store"
        )
        if (credentials.app_id, credentials.client_secret) != (
            self._settings.app_id,
            self._settings.client_secret,
        ):
            self._settings = replace(
                self._settings,
                app_id=credentials.app_id,
                client_secret=credentials.client_secret,
            )
        self._robot_uin = 0
        self._robot_nickname = ""
        self._missing_ready_openid_warned = False
        self._mapper.reset_identity()
        self._token_provider = TokenProvider(self._settings)
        self._api = OfficialApi(self._settings, self._token_provider, self._logger)
        self._sender = MessageSender(
            api=self._api,
            identity=self._identity,
            message_ids=self._message_ids,
            passive=self._passive,
            media=self._media,
            logger=self._logger,
        )
        self._gateway = OfficialGateway(
            self._settings,
            self._token_provider,
            self._on_event,
            self._logger,
            on_auth_exhausted=self._on_auth_exhausted,
        )

    async def _shutdown_runtime(self) -> None:
        gateway = self._gateway
        self._gateway = None
        api = self._api
        self._api = None
        self._sender = None
        self._token_provider = None
        self._connected = False
        self._ready_event.clear()
        self._connected_event.clear()
        if gateway is not None:
            try:
                await asyncio.wait_for(gateway.stop(), timeout=_STOP_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                self._logger.warning(
                    "官方网关停止超时，已放弃等待",
                    timeout_seconds=_STOP_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                self._logger.warning("官方网关停止失败", error=str(exc))
        if api is not None:
            try:
                await api.close()
            except Exception as exc:
                self._logger.warning("官方 HTTP 会话关闭失败", error=str(exc))

    def _load_credentials(self) -> Credentials | None:
        # 显式配置优先于扫码落盘的凭据：否则面板/配置里换了 AppID 会被旧凭据静默覆盖。
        if self._settings.app_id and self._settings.client_secret:
            return Credentials(
                app_id=self._settings.app_id,
                client_secret=self._settings.client_secret,
            )
        return self._credentials.load()

    async def _generate_robot_uin(self) -> int:
        if self._api is None:
            return 0
        try:
            payload = await self._api.request(
                "POST",
                "/v2/generate_url_link",
                body={"url": "https://q.qq.com/qqbot/"},
                timeout=10.0,
            )
        except Exception as exc:
            self._logger.debug("生成官方机器人链接失败", error=str(exc))
            return 0
        return _extract_robot_uin(api_data(payload))

    # ── 网关事件 ────────────────────────────────────────────────────

    async def _on_event(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        op = payload.get("op")
        if op not in (None, 0):
            return
        event_type = str(payload.get("t") or "")
        if event_type in {"READY", "RESUMED"}:
            data = payload.get("d")
            self._remember_bot_openid(data if isinstance(data, dict) else {}, event_type)
            if self._ready_event.is_set():
                # 断线重连：身份已缓存，补一帧 lifecycle.connect 让上层重新判定。
                self._connected = True
                await self._publish(self._meta_connect_event())
                return
            self._background(self._on_ready())
            return
        event = self._mapper.from_dispatch(payload)
        if event is None:
            return
        self._remember_event(event)
        await self._publish(event)

    async def _on_ready(self) -> None:
        await self.ensure_robot_identity()
        if not self._started:
            # 停止与 READY 竞争时不要把已停止的适配器重新标记成已连接。
            return
        self._connected = True
        self._relogin_notice = ""
        self._ready_event.set()
        self._connected_event.set()
        self._logger.info("QQ 官方机器人已连接", robot_uin=self._robot_uin)
        await self._publish(self._meta_connect_event())

    def _meta_connect_event(self) -> dict[str, Any]:
        return {
            "time": int(time.time()),
            "self_id": self._self_id(),
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": "connect",
        }

    def _self_id(self) -> int:
        return self._robot_uin or self._mapper.self_id

    def _remember_bot_openid(self, data: dict[str, Any], event_type: str) -> None:
        """READY 的 d.user.id / username 是机器人身份最可靠的来源；RESUMED 可能不带 user。"""
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        username = str(user.get("username") or "").strip()
        if username:
            self._mapper.bot_username = username
        openid = str(user.get("id") or user.get("user_openid") or "").strip()
        if not openid:
            if event_type == "READY" and not self._missing_ready_openid_warned:
                self._missing_ready_openid_warned = True
                self._logger.warning(
                    "官方 READY 未提供机器人 openid（d.user.id），群全量消息只能靠昵称/mention 兜底判定 @",
                    event_type=event_type,
                )
            return
        if openid != self._mapper.bot_openid:
            self._mapper.bot_openid = openid
            self._logger.info("已获取官方机器人 openid", bot_openid=openid)
        # 机器人 at 段固定用真 QQ 号（uin）；还没拿到 uin 时不制造假号，
        # self_id 保持 0，由 _append_bot_at 跳过，等 /users/@me 返回后补齐。

    async def _publish(self, event: dict[str, Any]) -> None:
        sink = self._event_sink
        if sink is None:
            return
        try:
            result = sink(event)
            if inspect.isawaitable(result):
                await result
        except SpeechBlocked:
            raise
        except Exception as exc:
            self._logger.error(
                "官方事件投递失败",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _remember_event(self, event: dict[str, Any]) -> None:
        message_id = int(event.get("message_id") or 0)
        if message_id:
            self._recent_messages[message_id] = dict(event)
            while len(self._recent_messages) > _RECENT_MESSAGE_LIMIT:
                self._recent_messages.popitem(last=False)
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        user_id = event.get("user_id")
        if user_id not in (None, "", 0):
            self._known_users[str(user_id)] = {
                "user_id": str(user_id),
                "nickname": str(sender.get("nickname") or ""),
            }
        if event.get("message_type") == "group":
            group_id = event.get("group_id")
            if group_id not in (None, "", 0):
                self._known_groups.setdefault(str(group_id), {"group_id": str(group_id), "group_name": ""})
        official_id = str(event.get("_official_message_id") or "")
        kind = str(event.get("message_type") or "")
        if official_id and kind in {"group", "private"}:
            conversation_id = event.get("group_id") if kind == "group" else event.get("user_id")
            if conversation_id:
                self._passive.remember(kind, conversation_id, official_id)

    def _background(self, awaitable: Any) -> asyncio.Task[None]:
        task = asyncio.ensure_future(awaitable)
        task.add_done_callback(self._log_background_failure)
        return task

    def _log_background_failure(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._logger.error(
                "官方适配器后台任务异常",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    # ── 扫码绑定 ────────────────────────────────────────────────────

    def _start_bind_flow(self) -> None:
        if self._bind_task is not None and not self._bind_task.done():
            return
        self._bind_task = self._background(self._run_bind_flow())

    async def _run_bind_flow(self) -> None:
        flow = QrBindFlow(self._settings, self._logger)
        self._bind_flow = flow
        try:
            state = await flow.start(self._on_bind_state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = BindState(phase="error", error=f"{type(exc).__name__}: {exc}")
            self._bind_state = state
            self._logger.error("QQ 官方机器人扫码绑定异常", error=str(exc))
        finally:
            self._bind_flow = None
            self._bind_task = None
        if state.phase != "success":
            return
        self._bind_state = state
        self._bound = True
        self._logger.info("QQ 官方机器人绑定成功，正在用新凭据重连")
        await self._restart_with_new_credentials()

    def _on_bind_state(self, state: BindState) -> None:
        if self._relogin_notice and state.phase == "pending" and not state.error:
            state = replace(state, error=self._relogin_notice)
        self._bind_state = state

    async def _cancel_bind_flow(self) -> None:
        self._bind_flow = None
        task = self._bind_task
        self._bind_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _restart_with_new_credentials(self) -> None:
        was_started = self._started
        # 扫码得到的新凭据要覆盖运行期 settings，否则 start() 仍会拿旧配置
        stored = self._credentials.load()
        if stored is not None:
            self._settings = replace(
                self._settings,
                app_id=stored.app_id,
                client_secret=stored.client_secret,
            )
        await self._shutdown_runtime()
        self._started = False
        if was_started:
            await self.start()


def _normalize_message(
    message: str | list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    """OneBot 便捷方法允许单个消息段 dict，发送层只收 str/list。"""
    if isinstance(message, dict):
        return [message]
    return message


def _extract_robot_uin(data: dict[str, Any]) -> int:
    for key in ("share_url", "url"):
        text = str(data.get(key) or "")
        if not text:
            continue
        match = _ROBOT_UIN_PATTERN.search(text)
        if match:
            return int(match.group(1))
    return 0


def _failed_response(message: str) -> response.SendMsgResponse:
    return response.SendMsgResponse(
        status="failed",
        retcode=1404,
        message=message,
        wording=message,
        data=None,
    )