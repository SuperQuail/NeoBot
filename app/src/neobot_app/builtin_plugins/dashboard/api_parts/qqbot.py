"""机器人通道接口：当前适配器状态、OneBot / 官方通道切换与重新扫码绑定。

状态一律从宿主服务注册表动态读取适配器：热重载与软重启会替换注册表里的
适配器对象，缓存 self.console.adapter 会一直展示旧通道。
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from ..config_manager import ConfigConflictError, ConfigValidationError
from ._common import _json_error, _json_ok

#: 面板允许切换的通道（local 是开发用内置适配器，不在这里提供切换）。
_ADAPTER_MODES = frozenset({"onebot", "official"})


class QqbotMixin:
    # ------------------------------------------------------------------
    # 只读状态
    # ------------------------------------------------------------------

    async def qqbot_status(self, request: web.Request) -> web.Response:
        """当前通道、连接与官方扫码绑定状态；任何一段读不到都按空值返回。"""
        adapter = self._service("adapter")
        values = self._qqbot_adapter_config()
        mode = str(
            self._qqbot_field(adapter, "active_mode", "") or values.get("mode") or "onebot"
        ).strip().casefold()
        # 绑定二维码/链接等同于「替本机机器人绑定账号」的凭据：只发给有管理权限的会话
        bind = (
            self._qqbot_bind_payload(self._qqbot_field(adapter, "bind_state"))
            if self._can_manage(request)
            else self._qqbot_bind_payload(None)
        )
        return _json_ok(
            {
                "mode": mode,
                "switching": bool(self._qqbot_field(adapter, "switching", False)),
                "connected": bool(self._qqbot_field(adapter, "connected", False)),
                "bind": bind,
                "onebot": self._qqbot_onebot_payload(),
                "official": self._qqbot_official_payload(adapter, values),
                "power": self.power_state(),
            }
        )

    @staticmethod
    def _qqbot_field(source: Any, name: str, default: Any = None) -> Any:
        """读适配器/绑定状态字段；切换与实现差异导致读不到时一律当缺失。"""
        if source is None:
            return default
        try:
            value = getattr(source, name, default)
        except Exception:
            return default
        return default if value is None else value

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

    def _qqbot_onebot_payload(self) -> dict[str, Any]:
        """OneBot 反向 WS 的**实际生效**监听信息（复用部署页的解析规则）。"""
        try:
            info = self._onebot_connection()
        except Exception:
            return {"host": "", "port": 0, "token_set": False}
        return {
            "host": str(info.get("host") or ""),
            "port": int(info.get("port") or 0),
            "token_set": bool(info.get("token_enabled") or info.get("token")),
        }

    def _qqbot_official_payload(
        self, adapter: Any, values: dict[str, Any]
    ) -> dict[str, Any]:
        bind_state = self._qqbot_field(adapter, "bind_state")
        bound = bool(self._qqbot_field(adapter, "bound", False))
        if not bound and str(self._qqbot_field(bind_state, "phase", "") or "") == "success":
            bound = True
        try:
            account = int(self._qqbot_field(adapter, "robot_uin", 0) or 0)
        except (TypeError, ValueError):
            account = 0
        return {
            "bound": bound,
            "app_id": str(values.get("qq_appid") or ""),
            "account": account,
            "nickname": str(self._qqbot_field(adapter, "robot_nickname", "") or ""),
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
    # 切换通道 / 重新扫码绑定
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
            return _json_error("未知通道模式：可选 onebot / official", status=400)

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

    async def qqbot_rebind(self, request: web.Request) -> web.Response:
        """让官方适配器重新发起扫码绑定（onebot 模式下适配器没有该能力）。"""
        denied = self._require_manage(request, action="重新扫码绑定官方机器人")
        if denied is not None:
            return denied
        adapter = self._service("adapter")
        rebind = getattr(adapter, "rebind", None) if adapter is not None else None
        if not callable(rebind):
            return _json_error(
                "当前适配器不支持重新扫码绑定（请先切换到官方机器人通道）", status=503
            )
        try:
            await rebind()
        except Exception as exc:
            self.logger.exception(f"重新扫码绑定失败: {exc}")
            return _json_error(f"重新扫码绑定失败: {exc}", status=500)
        return _json_ok({"message": "已重新开始扫码绑定，请用手机 QQ 扫码"})
