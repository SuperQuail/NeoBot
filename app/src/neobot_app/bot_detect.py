"""连接后判定 QQ 机器人身份：每个通道的官方性、账号与昵称。

身份只有在连接建立后才有事实可查：未连接直接返回，不改状态也不发 API。
判定方式是连接后对每个已连接通道并行调用 get_version_info / get_login_info，
用 get_version_info.data.app_name 是否为官方适配器标识区分官方性；账号以
get_login_info 为准。双通道模式下两个号都可能不是 config.bot.account，所以
账号只保留在 detector 里，绝不回写配置。
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

_CHANNEL_OFFICIAL = "official"
_CHANNEL_ONEBOT = "onebot"
#: 主档取用顺序：双通道时 onebot 优先
_PRIMARY_CHANNEL_ORDER = (_CHANNEL_ONEBOT, _CHANNEL_OFFICIAL)


@dataclass(frozen=True, slots=True)
class BotProfile:
    """一次身份判定的结论；kind 未判定前为 unknown。"""

    kind: str = "unknown"  # unknown / official / unofficial
    account: int = 0
    channel: str = ""  # "" / onebot / official
    nickname: str = ""
    source: str = "unresolved"  # unresolved / auto（API 判定）/ forced（official_mode 强制）
    resolved_at: float = 0.0


_UNKNOWN_PROFILE = BotProfile()


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
    """连接建立后逐通道判定 QQ 账号身份，并缓存官方机器人 UIN 段。"""

    def __init__(self, adapter: Any = None, *, logger: "Logger | None" = None) -> None:
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._config: Any = None
        self._group_queue: Any = None
        self._friend_queue: Any = None
        self._profiles: dict[str, BotProfile] = {}
        self._ranges: list[tuple[int, int]] = []
        # on_connect 事件与启动期等待任务可能并发触发，串行化避免重复查询
        self._resolve_lock = asyncio.Lock()

    @property
    def profile(self) -> BotProfile:
        """主档：优先 onebot，其次 official，否则 unknown。"""
        for channel in _PRIMARY_CHANNEL_ORDER:
            profile = self._profiles.get(channel)
            if profile is not None:
                return profile
        return _UNKNOWN_PROFILE

    @property
    def profiles(self) -> dict[str, BotProfile]:
        """各通道最近一次判定结论（快照）。"""
        return dict(self._profiles)

    def profile_for(self, channel: str | None) -> BotProfile:
        """通道对应的判定结论；无通道信息回退主档，未判定的通道返回 unknown。"""
        if not channel:
            return self.profile
        return self._profiles.get(str(channel), _UNKNOWN_PROFILE)

    @property
    def accounts(self) -> dict[str, int]:
        """已判定账号（channel -> QQ 号）；未判定或未取到账号的通道不出现。"""
        return {channel: profile.account for channel, profile in self._profiles.items() if profile.account}

    def account_for(self, channel: str | None) -> int:
        """通道账号；未知通道返回 0。"""
        return self.profile_for(channel).account

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
        """连接后解析所有已连接通道的身份；未连接或判定失败时保持既有结论。"""
        if self._adapter is None or not bool(getattr(self._adapter, "connected", False)):
            return self.profile
        async with self._resolve_lock:
            return await self._resolve_connected()

    async def _resolve_connected(self) -> BotProfile:
        adapter = self._adapter
        if adapter is None or not bool(getattr(adapter, "connected", False)):
            return self.profile
        channels = self._resolve_channels()
        if channels is None:
            # 旧适配器没有通道概念：按单通道处理，保留 account=0 回填配置的旧行为
            await self._resolve_channel(None)
        else:
            for channel in channels:
                await self._resolve_channel(channel)
            self._drop_disabled_profiles()
        if self._profiles:
            self._sync_queues()
        # 启动期原来在 application.start 里刷新的官方机器人 UIN 段，改到身份判定后刷新
        await self.refresh()
        return self.profile

    def _resolve_channels(self) -> tuple[str, ...] | None:
        """本次要判定的通道；旧适配器（没有通道表）返回 None，走单通道旧路径。"""
        adapter = self._adapter
        channels = getattr(adapter, "connected_channels", None)
        if not isinstance(channels, (tuple, list)):
            channels = getattr(adapter, "active_channels", None)
        if not isinstance(channels, (tuple, list)):
            return None
        if not channels:
            # 门面 connected 为 True 但通道表暂空：退回已启用通道，显式 channel 调用
            # 不可用时后端返回 failed，只会保持该通道既有结论
            active = getattr(adapter, "active_channels", ())
            channels = active if isinstance(active, (tuple, list)) else ()
        return tuple(str(channel) for channel in channels if channel)

    def _drop_disabled_profiles(self) -> None:
        """切模式后旧通道的结论作废：只保留仍启用的通道，避免旧账号继续参与自我识别。"""
        active = getattr(self._adapter, "active_channels", None)
        if not isinstance(active, (tuple, list)):
            return
        enabled = {str(channel) for channel in active if channel}
        for channel in [channel for channel in self._profiles if channel not in enabled]:
            self._profiles.pop(channel, None)

    async def _resolve_channel(self, channel: str | None) -> BotProfile | None:
        """解析单个已连接通道；拿不到 version_info 时保持该通道既有结论。"""
        version_info, login_info = await asyncio.gather(
            self._call_api("get_version_info", channel),
            self._call_api("get_login_info", channel),
        )
        version_data = _response_data(version_info)
        if version_data is None:
            self._logger.warning(
                "身份判定失败：get_version_info 重试后仍不可用，保持既有结论",
                channel=channel or "",
            )
            return None

        app_name = str(version_data.get("app_name") or "")
        detected_channel = _CHANNEL_OFFICIAL if app_name == OFFICIAL_ADAPTER_APP_NAME else _CHANNEL_ONEBOT
        # 有通道时以路由通道为准：它才是发送/取号的依据；app_name 不一致只记录
        resolved_channel = str(channel) if channel else detected_channel
        if channel and detected_channel != channel:
            self._logger.warning(
                "通道与后端上报的 app_name 不一致，按路由通道判定",
                channel=channel,
                app_name=app_name,
            )

        mode = normalize_official_mode(getattr(getattr(self._config, "bot", None), "official_mode", "auto"))
        detected = "official" if detected_channel == _CHANNEL_OFFICIAL else "unofficial"
        if mode == "auto":
            kind, source = detected, "auto"
        else:
            kind, source = mode, "forced"
            if mode != detected:
                self._logger.warning(
                    "official_mode 与 get_version_info 判定不一致，按配置强制",
                    official_mode=mode,
                    detected=detected,
                    channel=resolved_channel,
                )

        previous = self._profiles.get(resolved_channel, BotProfile(channel=resolved_channel))
        login_data = _response_data(login_info)
        account = self._resolve_account(login_data, previous)
        profile = BotProfile(
            kind=kind,
            account=account,
            channel=resolved_channel,
            nickname=str((login_data or {}).get("nickname") or previous.nickname or ""),
            source=source,
            resolved_at=time.time(),
        )
        self._profiles[resolved_channel] = profile
        self._logger.info(
            "QQ 机器人通道身份已判定",
            event="bot.identity_resolved",
            kind=kind,
            channel=resolved_channel,
            account=account,
            source=source,
        )
        return profile

    def _resolve_account(self, login_data: dict[str, Any] | None, previous: BotProfile) -> int:
        """账号优先级：配置值 > get_login_info > 既有结论。

        双通道下两个号都必须来自 API：账号只存在 detector 的 profiles/accounts 里，
        不写 config.bot.account（它只有一个值，写哪个号都是错的）。
        """
        api_account = _to_int((login_data or {}).get("user_id"))
        if self._is_multi_channel():
            return api_account or previous.account
        bot_cfg = getattr(self._config, "bot", None)
        configured = _to_int(getattr(bot_cfg, "account", 0))
        if configured:
            return configured
        if api_account:
            if bot_cfg is not None:
                # 写运行期配置：提示词/消息归属等按需读取方立即看到真实账号
                bot_cfg.account = api_account
            return api_account
        return previous.account

    def _is_multi_channel(self) -> bool:
        """是否双通道：门面同时启用多个通道，或配置已切到 dual（只剩一个已连上也算）。"""
        active = getattr(self._adapter, "active_channels", None)
        if active is not None and len(active) > 1:
            return True
        adapter_cfg = getattr(self._config, "adapter", None)
        return str(getattr(adapter_cfg, "mode", "") or "").strip().casefold() == "dual"

    def _sync_queues(self) -> None:
        """同步队列：bot_account 保留主账号，bot_accounts 覆盖全部已判定账号。"""
        accounts = {profile.account for profile in self._profiles.values() if profile.account}
        primary = self.profile
        for queue in (self._group_queue, self._friend_queue):
            if queue is None:
                continue
            if accounts:
                queue.bot_accounts = set(accounts)
            if primary.account:
                queue.bot_account = primary.account

    async def _call_api(self, action: str, channel: str | None = None) -> dict[str, Any] | None:
        """在指定通道调用一个身份查询 API；失败重试一次，仍失败返回 None。"""
        adapter = self._adapter
        if adapter is None:
            return None
        for _ in range(_IDENTITY_API_RETRIES + 1):
            try:
                if channel is None:
                    response = await adapter.call_api(action, {}, _IDENTITY_API_TIMEOUT)
                else:
                    response = await adapter.call_api(action, {}, _IDENTITY_API_TIMEOUT, channel=channel)
            except Exception as exc:
                self._logger.debug(f"身份查询 {action} 失败", error=str(exc), channel=channel or "")
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
