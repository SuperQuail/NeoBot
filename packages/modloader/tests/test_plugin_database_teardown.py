"""插件数据库必须在 ERROR 路径也被关闭。

关闭原先只发生在 Plugin.on_stop，而插件处于 ERROR 状态时 _stop_plugin_locked
会跳过 on_stop（callback_needed 只认 LOADED/RUNNING）：声明了数据库的插件若在
on_load/on_start 失败，引擎会一直挂着——Windows 上锁住数据库文件，导致插件
重装/升级失败。
"""

from __future__ import annotations


from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.manager import DefaultPluginManager
from neobot_modloader.plugin import Plugin


class _Logger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def _record(self, level: str, message: str, **kw) -> None:
        self.messages.append((level, message))

    def debug(self, message: str, **kw) -> None:
        self._record("debug", message)

    def info(self, message: str, **kw) -> None:
        self._record("info", message)

    def warning(self, message: str, **kw) -> None:
        self._record("warning", message)

    def error(self, message: str, **kw) -> None:
        self._record("error", message)

    def exception(self, message: str, **kw) -> None:
        self._record("exception", message)


class _FakeDatabase:
    def __init__(self, *, fail: bool = False) -> None:
        self.closed = 0
        self.fail = fail

    async def close(self) -> None:
        self.closed += 1
        if self.fail:
            raise RuntimeError("dispose boom")


def _manager() -> DefaultPluginManager:
    return DefaultPluginManager(logger=_Logger())


async def test_close_databases_is_idempotent() -> None:
    plugin = Plugin("p")
    database = _FakeDatabase()
    plugin._databases["main"] = database  # type: ignore[assignment]

    await plugin.close_databases()
    await plugin.close_databases()

    assert database.closed == 2  # 幂等：重复关闭不再抛错
    assert plugin._bound is False


def _context(name: str):
    return type("Ctx", (), {"plugin_name": name, "data_dir": None, "agents": None})()


async def test_teardown_closes_databases_on_error_path() -> None:
    """不调用 on_stop 的 ERROR 路径也必须关掉数据库。"""
    manager = _manager()
    plugin = Plugin("p")
    database = _FakeDatabase()
    plugin._databases["main"] = database  # type: ignore[assignment]
    manager.register(plugin, _context("p"))
    record = manager.get_record("p")
    assert record is not None
    record.state = PluginState.ERROR
    record.error = RuntimeError("on_load failed")

    errors = await manager._teardown_owned_resources(record)

    assert errors == []
    assert database.closed == 1


async def test_teardown_reports_database_close_failure() -> None:
    manager = _manager()
    plugin = Plugin("p2")
    database = _FakeDatabase(fail=True)
    plugin._databases["main"] = database  # type: ignore[assignment]
    manager.register(plugin, _context("p2"))
    record = manager.get_record("p2")
    assert record is not None

    errors = await manager._teardown_owned_resources(record)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
