"""StandbyController：进入待机停运行时、软重启重建、待机期 OneBot 开关。"""

from __future__ import annotations

import pytest

from neobot_app.bootstrap._standby_runtime import StandbyController
from neobot_app.runtime.standby_service import StandbyService


class _App:
    """假运行时：与生产一致——start()/stop() 会连带启停同一个适配器对象。"""

    def __init__(self, adapter: "_Adapter | None" = None) -> None:
        self.started = 0
        self.stopped = 0
        self.restart_requests = 0
        self._adapter = adapter

    async def start(self) -> None:
        self.started += 1
        if self._adapter is not None:
            await self._adapter.start()

    async def stop(self) -> None:
        self.stopped += 1
        if self._adapter is not None:
            await self._adapter.stop()

    def request_restart(self) -> None:
        self.restart_requests += 1


class _Adapter:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def _controller(standby: StandbyService, created: list[_App]):
    adapter = _Adapter()

    def factory() -> _App:
        app = _App(adapter)
        created.append(app)
        return app

    controller = StandbyController(
        standby_service=standby, runtime_factory=factory, adapter=adapter
    )
    return controller, adapter


@pytest.mark.asyncio
async def test_start_running_builds_and_starts_runtime() -> None:
    standby = StandbyService()
    created: list[_App] = []
    controller, _ = _controller(standby, created)

    await controller.start()

    assert (len(created), created[0].started) == (1, 1)
    assert controller.application is created[0]


@pytest.mark.asyncio
async def test_start_in_standby_does_not_build_runtime() -> None:
    standby = StandbyService(start_in_standby=True, connect_onebot=False)
    created: list[_App] = []
    controller, adapter = _controller(standby, created)

    await controller.start()

    assert created == []
    assert controller.application is None
    assert (adapter.started, adapter.stopped) == (0, 0), "关闭连接时不应启动适配器"


@pytest.mark.asyncio
async def test_start_in_standby_keeps_onebot_when_configured() -> None:
    standby = StandbyService(start_in_standby=True, connect_onebot=True)
    created: list[_App] = []
    controller, adapter = _controller(standby, created)

    await controller.start()

    assert created == []
    assert adapter.started == 1


@pytest.mark.asyncio
async def test_enter_stops_runtime_and_restarts_adapter_when_enabled() -> None:
    standby = StandbyService()
    created: list[_App] = []
    controller, adapter = _controller(standby, created)
    await controller.start()

    standby.set_hooks(on_enter=controller.enter, on_resume=controller.resume)
    ok, message = await standby.enter(reason="token 风暴")

    assert ok is True and "已进入待机" in message
    assert created[0].stopped == 1
    assert controller.application is None
    # app.start 时连过 1 次；进入待机后 app.stop 已断开，控制器再按配置重连 1 次
    assert adapter.started == 2, "待机期默认保持 OneBot 连接"


@pytest.mark.asyncio
async def test_enter_disconnects_onebot_when_disabled() -> None:
    standby = StandbyService(connect_onebot=False)
    created: list[_App] = []
    controller, adapter = _controller(standby, created)
    await controller.start()

    await controller.enter()

    # 适配器由 app.stop() 停掉（生产同一路径）；关闭连接时控制器不应再重复 stop
    assert (adapter.started, adapter.stopped) == (1, 1)


@pytest.mark.asyncio
async def test_resume_rebuilds_runtime_with_fresh_objects() -> None:
    standby = StandbyService()
    created: list[_App] = []
    controller, _ = _controller(standby, created)
    standby.set_hooks(on_enter=controller.enter, on_resume=controller.resume)
    await controller.start()
    await standby.enter(reason="改配置")

    ok, message = await standby.reboot(reason="改完配置")

    assert ok is True
    assert len(created) == 2, "软重启必须重建运行时（新配置才生效）"
    assert (created[1].started, controller.application) == (1, created[1])
    assert "软重启" in message


@pytest.mark.asyncio
async def test_set_onebot_in_standby() -> None:
    standby = StandbyService(connect_onebot=False)
    created: list[_App] = []
    controller, adapter = _controller(standby, created)
    await controller.start()
    standby.set_hooks(on_enter=controller.enter, on_resume=controller.resume)
    await standby.enter(reason="待机")

    ok, message = await controller.set_onebot(True)
    assert ok is True and adapter.started == 2 and "保持" in message

    ok, message = await controller.set_onebot(False)
    assert ok is True and adapter.stopped == 2, "1 次来自 app.stop、1 次来自开关"
    assert "断开" in message


@pytest.mark.asyncio
async def test_set_onebot_rejected_while_running() -> None:
    standby = StandbyService(connect_onebot=False)
    created: list[_App] = []
    controller, _ = _controller(standby, created)
    await controller.start()

    ok, message = await controller.set_onebot(True)

    assert ok is False and "运行中" in message, "运行中的连接由运行时持有，不允许切换"


@pytest.mark.asyncio
async def test_request_process_restart_needs_runtime() -> None:
    standby = StandbyService()
    created: list[_App] = []
    controller, _ = _controller(standby, created)

    assert controller.request_process_restart() is False, "待机时由核心的共享信号负责"

    await controller.start()
    assert controller.request_process_restart() is True
    assert created[0].restart_requests == 1
