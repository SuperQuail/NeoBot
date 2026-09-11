"""待机控制器：把「进入待机 / 软重启运行」接到 bot 运行时的停与建上。

职责边界：本模块**只做生命周期编排**，不构建任何组件，也不 import bootstrap：

- 运行时由组合根注入的 runtime_factory 创建（通常是 create_application(reuse=core)），
  因此每次 resume 都会按当前配置重新构建 bot 侧对象；
- 适配器与插件运行时归「核心」所有：进入待机不停它们（面板与 QQ 连接不能断）；
- 待机期是否保持 OneBot 连接由 StandbyService.connect_onebot 决定，控制器只负责
  对同一个适配器对象 start/stop，不重建对象（重建会让几十处持有引用的组件失联）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

#: 运行时工厂：返回一个具备 start()/stop()（以及可选 request_restart()）的对象
RuntimeFactory = Callable[[], Any]


class StandbyController:
    """待机状态与 bot 运行时之间的唯一编排者。"""

    def __init__(
        self,
        *,
        standby_service: Any,
        runtime_factory: RuntimeFactory,
        adapter: Any = None,
        logger: Logger | None = None,
        initial_application: Any = None,
    ) -> None:
        self._standby = standby_service
        self._factory = runtime_factory
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._app: Any | None = None
        self._initial = initial_application
        self._adapter_running = False

    @property
    def application(self) -> Any | None:
        """当前 bot 运行时；待机时为 None。"""
        return self._app

    # ── 生命周期 ────────────────────────────────────────────

    async def start(self) -> None:
        """进程启动：非待机则构建并启动运行时；待机则只按需保持 OneBot 连接。"""
        if self._standby.is_standby():
            # 启动即待机：启动前建好的初始运行时从未 start()，且可能是用兜底配置建的；
            # resume 会按最新配置重新构建，因此这里直接放弃引用，避免它一直被挂着。
            self._initial = None
            await self._sync_adapter(desired=bool(self._standby.connect_onebot))
            self._logger.warning(
                "以待机状态启动：仅启动核心服务（面板/配置/命令）",
                connect_onebot=bool(self._standby.connect_onebot),
            )
            return
        if self._app is None and self._initial is not None:
            # 复用启动时已经建好的运行时，避免开机白建一份 bot 侧对象
            application = self._initial
            self._initial = None
            await application.start()
            self._app = application
            self._adapter_running = self._adapter is not None
            return
        await self._start_runtime()

    async def enter(self) -> tuple[bool, str]:
        """进入待机：停掉 bot 运行时并释放引用，核心服务与面板保持运行。"""
        # 先摘掉引用再 await stop()：入口循环一旦观察到运行时退出，
        # 读到的 application 必须已经是 None，不能是正在停止的旧对象。
        application, self._app = self._app, None
        self._adapter_running = False
        if application is not None:
            await application.stop()
        await self._sync_adapter(desired=bool(self._standby.connect_onebot))
        return True, "bot 运行时已停止：只保留面板、配置与命令，/reboot 可软重启运行。"

    async def resume(self) -> tuple[bool, str]:
        """软重启运行：按当前配置在进程内重建并启动 bot 运行时。"""
        application, self._app = self._app, None
        self._adapter_running = False
        if application is not None:
            await application.stop()
        await self._start_runtime()
        return True, "已按当前配置软重启运行（进程未重启，面板未断线）。"

    async def set_onebot(self, enabled: bool) -> tuple[bool, str]:
        """待机期启停 OneBot 连接（运行中不生效：运行时自己持有连接）。"""
        if self._app is not None:
            return False, "运行中始终使用 OneBot 连接；请先进入待机再切换。"
        if not await self._sync_adapter(desired=bool(enabled)):
            return False, "切换 OneBot 连接失败（详见日志）；当前连接状态未改变。"
        if enabled:
            return True, "待机期已保持 OneBot 连接：QQ 命令仍可用。"
        return True, "待机期已断开 OneBot 连接：仅面板可用。"

    def request_process_restart(self) -> bool:
        """请求进程级重启（加载代码改动）。

        待机时 bot 运行时不存在，进程重启信号由核心持有的共享对象负责
        （接线见组合根）；此处只报告「本控制器无法处理」。
        """
        if self._app is None:
            return False
        request = getattr(self._app, "request_restart", None)
        if not callable(request):
            return False
        request()
        return True

    # ── 内部 ────────────────────────────────────────────────

    async def _start_runtime(self) -> None:
        application = self._factory()
        await application.start()
        self._app = application
        # 运行时的 start() 会启动适配器；保持标记一致，避免多余的 start/stop
        self._adapter_running = self._adapter is not None

    async def _sync_adapter(self, *, desired: bool) -> bool:
        """按需启停适配器；返回是否成功（失败时保持原状态并如实上报）。"""
        if self._adapter is None or desired == self._adapter_running:
            return True
        try:
            if desired:
                await self._adapter.start()
            else:
                await self._adapter.stop()
        except Exception as exc:
            # 待机期适配器起不来（端口占用等）绝不能拖垮核心：面板与命令必须继续可用，
            # 保持原状态，用户可在面板「运行状态」里重试切换。
            self._logger.error(f"待机期切换 OneBot 连接失败: {exc}")
            return False
        self._adapter_running = desired
        self._logger.info(
            "待机期已保持 OneBot 连接" if desired else "待机期已断开 OneBot 连接"
        )
        return True
