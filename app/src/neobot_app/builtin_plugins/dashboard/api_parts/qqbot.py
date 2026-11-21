"""机器人通道接口：双通道状态、模式切换与官方扫码重新绑定。

状态一律从宿主服务注册表动态读取适配器与 bot_detector：热重载与软重启会替换
注册表里的对象，缓存 self.console.adapter 会一直展示旧通道。

mode=dual 时 OneBot 与官方后端同时运行：连接/账号按通道分别读取，适配器没提供
按通道数据时退回 bot_detector；两边都缺失就返回空值，不抛错。
"""

from __future__ import annotations

import inspect
from typing import Any

from aiohttp import web

from ..config_manager import ConfigConflictError, ConfigValidationError
from ._common import _json_error, _json_ok

#: 面板展示的通道（顺序固定：OneBot 在前）。
_CHANNELS = ("onebot", "official")
_CHANNEL_LABELS = {"onebot": "OneBot 框架", "official": "QQ 官方机器人"}
#: 面板允许切换的模式（local 是开发用内置适配器，不提供切换）。
_ADAPTER_MODES = frozenset({"onebot", "official", "dual"})


class QqbotMixin:
    # ------------------------------------------------------------------
    # 只读状态
    # ------------------------------------------------------------------

    async def qqbot_status(self, request: web.Request) -> web.Response:
        """当前模式与每条通道的连接/账号/绑定状态；任何一段读不到都按空值返回。"""
        adapter = self._service("adapter")
        detector = self._service("bot_detector")
        values = self._qqbot_adapter_config()
        mode = str(
            self._qqbot_field(adapter, "active_mode", "") or values.get("mode") or "official"
        ).strip().casefold()
        active = self._qqbot_active_channels(adapter, mode)
        connected = self._qqbot_connected_channels(adapter, active)
        accounts = self._qqbot_accounts(adapter, detector)
        await self._qqbot_refresh_accounts(adapter, accounts, active, connected)

        manage = self._can_manage(request)
        onebot_info = self._qqbot_onebot_payload()
        bind_state = self._qqbot_field(adapter, "bind_state")
        channels: list[dict[str, Any]] = []
        for name in _CHANNELS:
            info = accounts.get(name) or {}
            item: dict[str, Any] = {
                "name": name,
                "label": _CHANNEL_LABELS[name],
                "active": name in active,
                "connected": name in connected,
                "account": self._qqbot_int(info.get("account")),
                "nickname": str(info.get("nickname") or ""),
                # 扫码绑定=替机器人绑定账号，只有 manage 会话能拿到二维码与链接
                "bind": (
                    self._qqbot_bind_payload(bind_state)
                    if name == "official" and manage
                    else self._qqbot_bind_payload(None)
                ),
                "onebot": (
                    onebot_info
                    if name == "onebot"
                    else {"host": "", "port": 0, "token_set": False}
                ),
            }
            if name == "official":
                item["app_id"] = str(values.get("qq_appid") or "")
            channels.append(item)
        return _json_ok(
            {
                "mode": mode,
                "switching": bool(self._qqbot_field(adapter, "switching", False)),
                "channels": channels,
                "power": self.power_state(),
            }
        )

    # ------------------------------------------------------------------
    # 状态读取辅助（全部容错：切换/实现差异一律当缺失）
    # ------------------------------------------------------------------

    @staticmethod
    def _qqbot_field(source: Any, name: str, default: Any = None) -> Any:
        if source is None:
            return default
        try:
            value = getattr(source, name, default)
        except Exception:
            return default
        return default if value is None else value

    @staticmethod
    def _qqbot_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _qqbot_adapter_config(self) -> dict[str, Any]:
        """运行中配置的 [adapter] 段；配置服务不可用时退回 config.toml 分区值。"""
        try:
            config_obj = self._config_proxy()
            adapter_cfg = getattr(config_obj, "adapter", None)
            if adapter_cfg is not None:
                return {
                    "mode": str(getattr(adapter_cfg, "mode", "") or ""),
                    "qq_appid": str(getattr(adapter_cfg, "qq_appid", "") or ""),
                }
        except Exception:
            pass
        try:
            values = self.console.config_manager.section_values("adapter")
        except Exception:
            return {}
        return dict(values) if isinstance(values, dict) else {}

    @staticmethod
    def _qqbot_channel_names(raw: Any) -> list[str]:
        """把 active_channels/connected_channels（tuple[str, ...]）归一成通道名列表。"""
        try:
            candidates = list(raw or ())
        except TypeError:
            return []
        names: list[str] = []
        for item in candidates:
            name = str(item or "").strip().casefold()
            if name in _CHANNELS and name not in names:
                names.append(name)
        return names

    def _qqbot_active_channels(self, adapter: Any, mode: str) -> list[str]:
        names = self._qqbot_channel_names(self._qqbot_field(adapter, "active_channels"))
        if names:
            return names
        # 适配器没提供按通道列表时按模式推导
        if mode == "dual":
            return list(_CHANNELS)
        return [mode] if mode in _CHANNELS else []

    def _qqbot_connected_channels(self, adapter: Any, active: list[str]) -> list[str]:
        names = self._qqbot_channel_names(self._qqbot_field(adapter, "connected_channels"))
        if names:
            return names
        # 单通道模式可以用全局 connected；dual 下区分不了通道，按未连接展示
        if len(active) == 1 and bool(self._qqbot_field(adapter, "connected", False)):
            return list(active)
        return []

    def _qqbot_accounts(self, adapter: Any, detector: Any) -> dict[str, dict[str, Any]]:
        accounts: dict[str, dict[str, Any]] = {
            name: {"account": 0, "nickname": ""} for name in _CHANNELS
        }
        # bot_detector 是身份判定的权威来源（连接后按通道取号，含昵称）
        profile_for = getattr(detector, "profile_for", None) if detector is not None else None
        if callable(profile_for):
            for name in _CHANNELS:
                try:
                    profile = profile_for(name)
                except Exception:
                    continue
                if profile is None:
                    continue
                if not accounts[name]["account"]:
                    accounts[name]["account"] = self._qqbot_int(
                        getattr(profile, "account", 0)
                    )
                if not accounts[name]["nickname"]:
                    accounts[name]["nickname"] = str(getattr(profile, "nickname", "") or "")
        if detector is not None:
            self._qqbot_merge_accounts(accounts, self._qqbot_field(detector, "accounts"))
        # 适配器按通道维护的账号（双通道门面）作为补充
        self._qqbot_merge_accounts(accounts, self._qqbot_field(adapter, "accounts"))
        # 单通道官方后端的遗留属性兜底
        if not accounts["official"]["account"]:
            accounts["official"]["account"] = self._qqbot_int(
                self._qqbot_field(adapter, "robot_uin", 0)
            )
        if not accounts["official"]["nickname"]:
            accounts["official"]["nickname"] = str(
                self._qqbot_field(adapter, "robot_nickname", "") or ""
            )
        return accounts

    def _qqbot_merge_accounts(
        self, accounts: dict[str, dict[str, Any]], raw: Any
    ) -> None:
        """合并 detector/适配器的 channel→QQ 号映射；未知形状静默跳过。"""
        if not isinstance(raw, dict):
            return
        for raw_name, value in raw.items():
            name = str(raw_name or "").strip().casefold()
            if name in accounts and not accounts[name]["account"]:
                accounts[name]["account"] = self._qqbot_int(value)

    async def _qqbot_refresh_accounts(
        self, adapter: Any, accounts: dict[str, dict[str, Any]], active: list[str], connected: list[str]
    ) -> None:
        """活动通道已连接但账号还空着时，让适配器补一次取号。

        门面的 ensure_accounts 只对未解析的通道发 get_login_info，解析后有缓存，
        所以面板可以放心按轮询节奏调用。
        """
        missing = [
            name
            for name in active
            if name in connected and not accounts.get(name, {}).get("account")
        ]
        ensure = getattr(adapter, "ensure_accounts", None) if adapter is not None else None
        if not missing or not callable(ensure):
            return
        try:
            result = ensure()
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            return
        self._qqbot_merge_accounts(accounts, result)
        self._qqbot_merge_accounts(accounts, self._qqbot_field(adapter, "accounts"))

    def _qqbot_onebot_payload(self) -> dict[str, Any]:
        """OneBot 反向 WS 的**实际生效**监听信息（复用部署页的解析规则）。"""
        try:
            info = self._onebot_connection()
        except Exception:
            return {"host": "", "port": 0, "token_set": False}
        return {
            "host": str(info.get("host") or ""),
            "port": self._qqbot_int(info.get("port")),
            "token_set": bool(info.get("token_enabled") or info.get("token")),
        }

    def _qqbot_bind_payload(self, state: Any) -> dict[str, Any]:
        return {
            "phase": str(self._qqbot_field(state, "phase", "idle") or "idle"),
            "url": str(self._qqbot_field(state, "url", "") or ""),
            "svg": str(self._qqbot_field(state, "svg", "") or ""),
            "expires_at": self._qqbot_scalar(self._qqbot_field(state, "expires_at", 0)),
            "error": str(self._qqbot_field(state, "error", "") or ""),
        }

    @staticmethod
    def _qqbot_scalar(value: Any) -> Any:
        """绑定状态的时间戳可能是 datetime：转成 JSON 能序列化的形式。"""
        if value is None:
            return 0
        if isinstance(value, (str, int, float, bool)):
            return value
        isoformat = getattr(value, "isoformat", None)
        return isoformat() if callable(isoformat) else str(value)

    # ------------------------------------------------------------------
    # 切换模式 / 重新扫码绑定
    # ------------------------------------------------------------------

    async def qqbot_switch(self, request: web.Request) -> web.Response:
        """写入 [adapter].mode 并触发热重载（不软重启、不中断面板）。"""
        denied = self._require_manage(request, action="切换机器人通道")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        mode = str(payload.get("mode") or "").strip().casefold()
        if mode not in _ADAPTER_MODES:
            return _json_error("未知通道模式：可选 onebot / official / dual", status=400)

        try:
            self.console.config_manager.update_section("adapter", {"mode": mode})
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"写入适配器配置失败: {exc}", status=500)

        self.logger.info(
            f"面板切换机器人通道 ip={self.console.request_ip(request)} mode={mode}"
        )
        result = await self._reload_config(with_changes=True)
        if not result.get("ok"):
            return _json_error(
                str(result.get("message") or "配置热重载失败"), status=500, reload=result
            )
        return _json_ok({"mode": mode, **result})

    async def qqbot_unbind(self, request: web.Request) -> web.Response:
        """删除扫码落盘的官方凭据并断开，之后可用配置凭据或重新扫码。"""
        denied = self._require_manage(request, action="解绑官方机器人")
        if denied is not None:
            return denied
        adapter = self._service("adapter")
        unbind = getattr(adapter, "unbind", None) if adapter is not None else None
        if not callable(unbind):
            return _json_error(
                "当前适配器不支持解绑官方机器人（请先把模式切到官方或双通道）", status=503
            )
        try:
            await unbind()
        except Exception as exc:
            self.logger.exception(f"解绑官方机器人失败: {exc}")
            return _json_error(f"解绑官方机器人失败: {exc}", status=500)
        return _json_ok({"message": "已解绑官方机器人，可重新扫码或用配置中的 AppID/AppSecret 启动"})

    async def qqbot_rebind(self, request: web.Request) -> web.Response:
        """让官方适配器重新发起扫码绑定（当前没有官方后端时返回 503）。"""
        denied = self._require_manage(request, action="重新扫码绑定官方机器人")
        if denied is not None:
            return denied
        adapter = self._service("adapter")
        rebind = getattr(adapter, "rebind", None) if adapter is not None else None
        if not callable(rebind):
            return _json_error(
                "当前适配器不支持重新扫码绑定（请先把模式切到官方或双通道）", status=503
            )
        try:
            await rebind()
        except Exception as exc:
            self.logger.exception(f"重新扫码绑定失败: {exc}")
            return _json_error(f"重新扫码绑定失败: {exc}", status=500)
        return _json_ok({"message": "已重新开始扫码绑定，请用手机 QQ 扫码"})
