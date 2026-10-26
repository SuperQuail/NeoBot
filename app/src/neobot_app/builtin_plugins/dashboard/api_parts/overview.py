"""面板总览、系统状态与机器人状态接口。"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from .. import system as system_module
from ._common import _json_ok


class OverviewMixin:
    # ------------------------------------------------------------------
    # 概览 / 系统 / 机器人
    # ------------------------------------------------------------------

    async def overview(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        stats = self.metrics.message_stats()
        system = system_module.snapshot(data_dir=self.console.data_dir)
        plugins = self._plugin_summary()
        return _json_ok(
            {
                "online": bool(bot.get("online")),
                "app_name": bot.get("app_name") or "",
                "app_version": bot.get("app_version") or "",
                "bot_nickname": bot.get("nickname") or "",
                "bot_user_id": bot.get("user_id"),
                "avatar_url": bot.get("avatar_url") or "",
                "uptime_seconds": self.console.uptime_seconds,
                "today_messages": stats["today"],
                "total_messages": stats["total"],
                "plugins_loaded": plugins["loaded"],
                "plugins_total": plugins["total"],
                "plugins_error": plugins["error"],
                "latency_ms": self.metrics.latency_series()["current_ms"],
                "python_version": system.get("python_version"),
                "hostname": system.get("hostname"),
                "standby": bool(self.power_state().get("standby")),
                "notices": self._config_notices(),
            }
        )

    def _config_notices(self) -> list[dict[str, Any]]:
        """控制台首页要提示的配置缺口（只读运行中的配置，不写任何东西）。

        目前只有一条：**未配置超级管理员账号**。这类缺口不会报错、也不影响启动，
        但「余额不足」等系统通知会发不出去 —— 只在启动日志里 warning 一次，
        很容易被忽略到最后。放在首页比放在日志里有用。
        """
        notices: list[dict[str, Any]] = []
        try:
            config_obj = self._config_proxy()
            accounts = getattr(getattr(config_obj, "chat", None), "admin_accounts", None) or []
            if not [str(item).strip() for item in accounts if str(item).strip()]:
                notices.append(
                    {
                        "level": "warning",
                        "text": "尚未配置超级管理员账号，可能影响部分命令使用",
                        "hint": "在「配置管理 → 本体配置 → chat」里填 admin_accounts（QQ 号列表）",
                    }
                )
        except Exception as exc:
            self.logger.warning(f"生成配置提示失败: {exc}")
        return notices

    def power_state(self) -> dict[str, Any]:
        """当前运行状态（运行中 / 待机中）；待机服务未注册时返回 available=False。"""
        service = self._standby_service()
        if service is None:
            return {"available": False, "state": "running", "standby": False}
        try:
            status = dict(service.status())
        except Exception:
            return {"available": False, "state": "running", "standby": False}
        status["available"] = True
        return status

    async def system(self, request: web.Request) -> web.Response:
        payload = system_module.snapshot(data_dir=self.console.data_dir)
        payload["uptime_seconds"] = self.console.uptime_seconds
        return _json_ok(payload)

    async def bots(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        latency = self.metrics.latency_series()
        return web.json_response(
            [
                {
                    "name": bot.get("nickname") or "未连接",
                    "user_id": bot.get("user_id"),
                    "platform": bot.get("app_name") or "OneBot",
                    "status": "on" if bot.get("online") else "off",
                    "latency_ms": latency.get("current_ms"),
                    "avatar_initial": (str(bot.get("nickname") or "N")[:1] or "N"),
                    "avatar_url": bot.get("avatar_url") or "",
                }
            ]
        )

    async def bot_detail(self, request: web.Request) -> web.Response:
        bot = await self.console.bot_info()
        stats = self.metrics.message_stats()
        latency = self.metrics.latency_series()
        return _json_ok(
            {
                "nickname": bot.get("nickname") or "",
                "user_id": bot.get("user_id"),
                "avatar_url": bot.get("avatar_url") or "",
                "online": bool(bot.get("online")),
                "app_name": bot.get("app_name") or "",
                "app_version": bot.get("app_version") or "",
                "latency_ms": latency.get("current_ms"),
                "uptime_seconds": self.console.uptime_seconds,
                "today_messages": stats["today"],
                "total_messages": stats["total"],
            }
        )

    async def series_messages(self, request: web.Request) -> web.Response:
        days = self._int_arg(request, "days", 30, minimum=1, maximum=365)
        return _json_ok({"series": self.metrics.message_series(days), "days": days})

    async def series_latency(self, request: web.Request) -> web.Response:
        return _json_ok(self.metrics.latency_series())

    async def stats_api_calls(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 10, minimum=1, maximum=100)
        return _json_ok(self.metrics.api_calls(limit))

    async def stats_active_users(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 10, minimum=1, maximum=100)
        return _json_ok(self.metrics.active_users(limit))
