"""定时任务、电源与进程管理接口。"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from ..security import is_loopback
from ._common import _json_ok, _json_error, _SCHEDULED_ACTION_MESSAGES


class AdminMixin:
    # ------------------------------------------------------------------
    # 定时任务（读走管理器投影，写走 reminder skill）
    # ------------------------------------------------------------------

    def _scheduled_task_manager(self) -> Any:
        return self._service("scheduled_task_manager")

    async def scheduled_tasks(self, request: web.Request) -> web.Response:
        from .. import scheduled_admin

        include_disabled = str(request.query.get("include_disabled") or "") not in {
            "0",
            "false",
            "",
        }
        limit = self._int_arg(request, "limit", 200, minimum=1, maximum=2000)
        payload = await scheduled_admin.read_managed_tasks(
            self._scheduled_task_manager(),
            include_disabled=include_disabled,
            limit=limit,
        )
        payload["editable"] = self._can_manage(request)
        return _json_ok(payload)

    async def scheduled_tasks_action(self, request: web.Request) -> web.Response:
        """新建/编辑/启停/删除定时任务。"""
        from .. import scheduled_admin

        denied = self._require_manage(request, action="管理定时任务")
        if denied is not None:
            return denied
        body = await self._read_json(request)
        action = str(body.get("action") or "").strip()
        try:
            result = await scheduled_admin.execute_action(
                self._service("skill_manager"), action, body
            )
        except ValueError as exc:
            return _json_error(str(exc))
        except RuntimeError as exc:
            return _json_error(str(exc), status=503)
        if not result.get("ok"):
            return _json_error(str(result.get("error") or "操作失败"))
        message = _SCHEDULED_ACTION_MESSAGES.get(action, "操作完成")
        self.logger.info(
            f"面板管理定时任务 ip={self.console.request_ip(request)} action={action}"
        )
        return _json_ok({"message": message, "action": action, "result": result})

    # ------------------------------------------------------------------
    # 运行状态（待机 / 软重启运行）
    # ------------------------------------------------------------------

    async def power_status(self, request: web.Request) -> web.Response:
        return _json_ok(self.power_state())

    async def _power_reason(self, request: web.Request) -> str:
        """读取可选请求体里的原因；空 body 视为无参数。"""
        try:
            payload = await self._read_json(request)
        except ValueError:
            payload = {}
        return str(payload.get("reason") or "").strip()

    def _schedule_power_action(self, *, action: str, runner, log: str) -> str:
        """把「停运行时/重建运行时」这类重活丢到后台任务，接口立刻返回。

        软重启要重建全部 bot 侧对象（可能几十秒），同步等待会让面板请求超时，
        期间事件循环也被占住（面板看起来像卡死）。后台执行后，前端按
        /api/admin/power 轮询即可看到状态变化，界面不需要额外改造。
        """
        self.logger.info(log)

        async def _worker() -> None:
            try:
                ok, message = await runner()
            except Exception as exc:
                self.logger.exception(f"{action}异常: {exc}")
                return
            if not ok:
                self.logger.error(f"{action}失败: {message}")

        task = asyncio.create_task(_worker())
        # 必须持有强引用：返回值被丢弃的后台任务可能被 GC 回收，待机/软重启会静默半途而废。
        self._power_tasks.add(task)
        task.add_done_callback(self._power_tasks.discard)
        return f"已开始{action}：面板会自动刷新状态，不需要重启进程。"

    async def admin_standby(self, request: web.Request) -> web.Response:
        """进入待机：停掉 bot 运行时，只保留面板与核心服务。

        进入待机后回复与记忆管线不再工作，但面板、命令与配置热重载仍然可用，
        改完配置用 /reboot（或面板「软重启运行」）即可恢复，不必重启进程。
        """
        denied = self._require_manage(request, action="进入待机")
        if denied is not None:
            return denied
        service = self._standby_service()
        if service is None:
            return _json_error("待机服务不可用，请重启 NeoBot", status=503)
        reason = await self._power_reason(request)
        operator = f"panel:{self.console.request_ip(request)}"
        message = self._schedule_power_action(
            action="进入待机",
            runner=lambda: service.enter(reason=reason or "panel", operator=operator),
            log=f"面板请求进入待机 ip={operator} reason={reason or 'panel'}",
        )
        return _json_ok({**self.power_state(), "message": message})

    async def admin_resume(self, request: web.Request) -> web.Response:
        """退出待机：按当前配置重建并启动 bot 运行时。"""
        return await self._soft_restart(request)

    async def admin_reboot(self, request: web.Request) -> web.Response:
        """软重启 bot 运行时：不重启进程，面板与连接保持可用。"""
        return await self._soft_restart(request)

    async def _soft_restart(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request, action="软重启运行")
        if denied is not None:
            return denied
        service = self._standby_service()
        if service is None:
            return _json_error("待机服务不可用，请重启 NeoBot", status=503)
        reason = await self._power_reason(request)
        operator = f"panel:{self.console.request_ip(request)}"
        message = self._schedule_power_action(
            action="软重启运行",
            runner=lambda: service.resume(reason=reason or "panel", operator=operator),
            log=f"面板请求软重启运行 ip={operator} reason={reason or 'panel'}",
        )
        return _json_ok({**self.power_state(), "message": message})

    async def admin_standby_onebot(self, request: web.Request) -> web.Response:
        """待机期是否保持与 OneBot 的连接（立即生效）。"""
        denied = self._require_manage(request, action="切换待机连接")
        if denied is not None:
            return denied
        service = self._standby_service()
        if service is None:
            return _json_error("待机服务不可用，请重启 NeoBot", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        enabled = bool(payload.get("enabled"))
        operator = f"panel:{self.console.request_ip(request)}"
        ok, message = await service.set_connect_onebot(enabled, operator=operator)
        if not ok:
            return _json_error(message)
        return _json_ok({**self.power_state(), "message": message})

    async def admin_shutdown(self, request: web.Request) -> web.Response:
        """优雅关闭整个进程（等价收到 SIGTERM）。

        与 `admin_restart` 的区别：那个换一代运行时（面板与进程都留着），
        这个让进程退出。宿主（NapCatQQ Desktop 这类进程管理器）用它请 NeoBot
        自己开始收尾——Windows 上它没法发 POSIX 信号，本机子进程也没有控制台，
        所以 HTTP 是唯一可用的「请它退」手段。

        只接受本机来源：这是关停整个进程的入口，不该被远端触发。
        """
        if not is_loopback(self.console.request_ip(request)):
            return _json_error("关闭入口只接受本机请求", status=403)
        denied = self._require_manage(request, action="关闭 NeoBot")
        if denied is not None:
            return denied
        # 与重启同源：核心信号跨代际存活，待机态 / 切换中也收得到
        signal = self._service("process_stop")
        stop = getattr(signal, "request", None)
        if not callable(stop):
            return _json_error("优雅关闭入口不可用，请手动停止 NeoBot", status=503)
        self.logger.info(f"面板请求优雅关闭 NeoBot ip={self.console.request_ip(request)}")
        # 立刻接受并返回：重复请求在信号里合并。调用方（如桌面端）拿到 200 后
        # 应当按进程存活轮询等待，而不是把「已请求」当成「已关闭」。
        stop()
        return _json_ok({"message": "已请求优雅关闭；须等待清理完成（记忆总结可能数分钟）"})

    async def admin_restart(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        # The core signal survives standby and failed/rebuilding generations.
        # Never capture a retiring application when a core entry point exists.
        signal = self._service("process_restart")
        restart = getattr(signal, "request", None)
        if not callable(restart):
            application = self._service("application")
            restart = getattr(application, "request_restart", None)
        if not callable(restart):
            return _json_error("重启入口不可用，请手动重启 NeoBot", status=503)
        self.logger.info(f"面板请求重启 NeoBot ip={self.console.request_ip(request)}")
        if signal is not None and callable(getattr(signal, "request", None)):
            # Accept durably now. Repeated requests coalesce in the signal; a
            # delayed callback must not allow another runtime to be published.
            restart()
        else:
            asyncio.get_running_loop().call_later(0.5, restart)
        return _json_ok({"message": "已请求优雅重启；须等待清理完成，若关闭卡住需手动处理或显式强制重启"})

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _int_arg(
        request: web.Request, name: str, default: int, *, minimum: int, maximum: int
    ) -> int:
        raw = request.query.get(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _find_snapshot(control: Any, name: str) -> Any:
        if control is None:
            return None
        try:
            snapshots = control.snapshot()
        except Exception:
            return None
        for item in snapshots:
            if item.name == name:
                return item
        return None
