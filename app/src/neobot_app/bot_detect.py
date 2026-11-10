"""连接后判定 QQ 机器人身份：通道（onebot / 官方）、官方性与账号。

身份只有在连接建立后才有事实可查：未连接直接返回，不改状态也不发 API。
判定方式是连接后并行调用 get_version_info / get_login_info，用
get_version_info.data.app_name 是否为官方适配器标识区分通道。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME
from neobot_contracts.ports.logging import NullLogger

from neobot_app.config.schemas.bot_parts.core import normalize_official_mode

if TYPE_CHECKING:
    from neobot_contracts.ports.logging import Logger

#: 身份查询单次超时（秒）
_IDENTITY_API_TIMEOUT = 5.0
#: 身份查询失败后的重试次数
_IDENTITY_API_RETRIES = 1

_CHANNEL_OFFICIAL = "qq-official"
_CHANNEL_ONEBOT = "onebot"


@dataclass(frozen=True, slots=True)
class BotProfile:
    """一次身份判定的结论；kind 未判定前为 unknown。"""

    kind: str = "unknown"  # unknown / official / unofficial
    account: int = 0
    channel: str = ""  # "" / onebot / qq-official
    source: str = "unresolved"  # unresolved / auto（API 判定）/ forced（official_mode 强制）
    resolved_at: float = 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _response_data(response: Any) -> dict[str, Any] | None:
    """从 OneBot 形状的成功响应里取 data；失败响应返回 None。"""
    if not isinstance(response, dict):
        return None
    if str(response.get("status", "ok")).strip().casefold() == "failed":
        return None
    retcode = response.get("retcode", 0)
    if retcode not in (None, 0):
        return None
    data = response.get("data")
    return data if isinstance(data, dict) else None


class BotDetector:
    """连接建立后判定 QQ 账号身份，并缓存官方机器人 UIN 段。"""

    def __init__(self, adapter: Any = None, *, logger: "Logger | None" = None) -> None:
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._config: Any = None
        self._group_queue: Any = None
        self._friend_queue: Any = None
        self._profile = BotProfile()
        self._ranges: list[tuple[int, int]] = []
        # on_connect 事件与启动期等待任务可能并发触发，串行化避免重复查询
        self._resolve_lock = asyncio.Lock()

    @property
    def profile(self) -> BotProfile:
        return self._profile

    def bind(
        self,
        config: Any,
        *,
        group_queue: Any = None,
        friend_queue: Any = None,
    ) -> None:
        """绑定运行期配置与消息队列（装配期调用；热重载时由 reapply 重放）。"""
        self._config = config
        if group_queue is not None:
            self._group_queue = group_queue
        if friend_queue is not None:
            self._friend_queue = friend_queue

    async def reapply(
        self,
        config: Any,
        *,
        group_queue: Any = None,
        friend_queue: Any = None,
    ) -> BotProfile:
        """配置热重载后重放身份判定（绑定新配置，已连接时立即重新解析）。"""
        self.bind(config, group_queue=group_queue, friend_queue=friend_queue)
        return await self.resolve_identity()

    async def resolve_identity(self) -> BotProfile:
        """连接后解析通道/官方性/账号；未连接或判定失败时保持既有结论。"""
        if self._adapter is None or not bool(getattr(self._adapter, "connected", False)):
            return self._profile
        async with self._resolve_lock:
            return await self._resolve_connected()

    async def _resolve_connected(self) -> BotProfile:
        adapter = self._adapter
        if adapter is None or not bool(getattr(adapter, "connected", False)):
            return self._profile
        version_info, login_info = await asyncio.gather(
            self._call_api("get_version_info"),
            self._call_api("get_login_info"),
        )
        version_data = _response_data(version_info)
        if version_data is None:
            self._logger.warning("身份判定失败：get_version_info 重试后仍不可用，保持既有结论")
            return self._profile

        channel = (
            _CHANNEL_OFFICIAL
            if str(version_data.get("app_name") or "") == OFFICIAL_ADAPTER_APP_NAME
            else _CHANNEL_ONEBOT
        )
        mode = normalize_official_mode(getattr(getattr(self._config, "bot", None), "official_mode", "auto"))
        detected = "official" if channel == _CHANNEL_OFFICIAL else "unofficial"
        if mode == "auto":
            kind, source = detected, "auto"
        else:
            kind, source = mode, "forced"
            if mode != detected:
                self._logger.warning(
                    "official_mode 与 get_version_info 判定不一致，按配置强制",
                    official_mode=mode,
                    detected=detected,
                    channel=channel,
                )

        account = self._apply_account(_response_data(login_info))
        # 启动期原来在 application.start 里刷新的官方机器人 UIN 段，改到身份判定后刷新
        await self.refresh()

        self._profile = BotProfile(
            kind=kind,
            account=account,
            channel=channel,
            source=source,
            resolved_at=time.time(),
        )
        self._logger.info(
            "QQ 机器人身份已判定",
            event="bot.identity_resolved",
            kind=kind,
            channel=channel,
            account=account,
            source=source,
        )
        return self._profile

    def _apply_account(self, login_data: dict[str, Any] | None) -> int:
        """账号优先级：配置值 > get_login_info > 既有结论；配置为 0 时用 API 值回填。"""
        bot_cfg = getattr(self._config, "bot", None)
        configured = _to_int(getattr(bot_cfg, "account", 0))
        api_account = _to_int((login_data or {}).get("user_id"))
        if configured:
            account = configured
        elif api_account:
            account = api_account
            if bot_cfg is not None:
                # 写运行期配置：提示词/消息归属等按需读取方立即看到真实账号
                bot_cfg.account = account
        else:
            account = self._profile.account
        if account:
            for queue in (self._group_queue, self._friend_queue):
                if queue is not None:
                    queue.bot_account = account
        return account

    async def _call_api(self, action: str) -> dict[str, Any] | None:
        """调用一个身份查询 API；失败重试一次，仍失败返回 None。"""
        adapter = self._adapter
        if adapter is None:
            return None
        for _ in range(_IDENTITY_API_RETRIES + 1):
            try:
                response = await adapter.call_api(action, {}, _IDENTITY_API_TIMEOUT)
            except Exception as exc:
                self._logger.debug(f"身份查询 {action} 失败", error=str(exc))
                continue
            if _response_data(response) is not None:
                return response
        return None

    async def refresh(self) -> None:
        """从 QQ 后端查询机器人 UIN 段并缓存；失败保持既有区间。"""
        if self._adapter is None:
            return

        from neobot_adapter.request.private import get_robot_uin_range

        try:
            response = await get_robot_uin_range()
        except Exception:
            return

        data = getattr(response, "data", None)
        if not data:
            return

        ranges: list[tuple[int, int]] = []
        for item in data:
            min_uin = getattr(item, "minUin", None)
            max_uin = getattr(item, "maxUin", None)
            if min_uin is not None and max_uin is not None:
                ranges.append((int(min_uin), int(max_uin)))
        self._ranges = ranges

    def is_official_bot(self, user_id: int | str) -> bool:
        """检查用户 ID 是否落在已知的官方机器人 UIN 段内。"""
        if not self._ranges:
            return False
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False
        return any(min_uin <= uid <= max_uin for min_uin, max_uin in self._ranges)

    @property
    def ranges(self) -> list[tuple[int, int]]:
        return list(self._ranges)
