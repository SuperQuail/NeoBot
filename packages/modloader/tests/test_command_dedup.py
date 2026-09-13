"""spec(4) Part D：插件命令注册桥的命名去重（R26 / D21 / A63-A66）。

新语义：**先试原名**；只有冲突（同名或别名）才回退 {plugin}__{name}；
两者都占用则只记 warning、跳过注册，不抛异常、不阻断插件加载。
prefixed=True 保留改造前的「一律加前缀」旧语义。
"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_modloader.context import PluginCommand, PluginCommandRegistrar


class FakeCommandRegistry:
    """与本体 CommandRegistry 同语义的替身：同名 / 别名冲突抛 ValueError。"""

    def __init__(self) -> None:
        self._commands: dict[str, Any] = {}

    def register(self, command: Any) -> None:
        if command.name in self._commands:
            raise ValueError(f"命令已注册: /{command.name}")
        for alias in command.aliases:
            if alias in self._commands:
                raise ValueError(f"命令别名冲突: /{alias}")
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def unregister(self, name: str) -> bool:
        command = self._commands.pop(name, None)
        if command is None:
            return False
        for alias in command.aliases:
            self._commands.pop(alias, None)
        return True

    def get(self, name: str) -> Any | None:
        return self._commands.get(name)

    def names(self) -> list[str]:
        return sorted(self._commands)


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def info(self, message: str) -> None:  # pragma: no cover - 用例不依赖
        pass


def make_registrar(
    registry: FakeCommandRegistry | None = None,
    *,
    plugin: str = "dashboard",
    cleanups: list[Any] | None = None,
) -> tuple[PluginCommandRegistrar, FakeCommandRegistry, RecordingLogger]:
    registry = registry or FakeCommandRegistry()
    logger = RecordingLogger()
    registrar = PluginCommandRegistrar(
        plugin_name=plugin,
        registry=registry,
        record_cleanup=(cleanups.append if cleanups is not None else None),
        logger=logger,
    )
    return registrar, registry, logger


def command(name: str, **kwargs: Any) -> PluginCommand:
    return PluginCommand(name=name, description="测试", handler=lambda ctx: None, **kwargs)


def test_original_name_wins_without_conflict() -> None:
    """A63：无冲突时命令名就是原名，并且带上来源标记。"""
    registrar, registry, _logger = make_registrar()

    registrar.register(command("status"))

    assert registry.get("status") is not None
    assert registry.get("dashboard__status") is None
    assert registry.get("status").source == "dashboard"
    assert registry.get("status").help_line.endswith("[来源: dashboard]")


def test_conflict_falls_back_to_prefixed_name_and_warns() -> None:
    """A64：与本体同名命令冲突时自动改成 dashboard__status，写 WARNING，不抛异常。"""
    registry = FakeCommandRegistry()
    registry.register(command("status"))  # 本体内置同名命令
    registrar, _registry, logger = make_registrar(registry)

    registrar.register(command("status"))  # 不得抛异常

    assert registry.get("status").source == ""
    prefixed = registry.get("dashboard__status")
    assert prefixed is not None
    assert prefixed.source == "dashboard"
    assert registrar.renames() == [("status", "dashboard__status")]
    assert any("重名" in message for message in logger.warnings)


def test_alias_conflict_also_falls_back() -> None:
    """原名与既有命令的别名冲突时同样回退到前缀名（别名也走去重）。"""
    registry = FakeCommandRegistry()
    registry.register(command("stat", aliases=("status",)))
    registrar, _registry, logger = make_registrar(registry)

    registrar.register(command("status"))  # 不抛异常

    assert registry.get("status").name == "stat"  # 原名被别名占用，保持不动
    assert registry.get("dashboard__status") is not None
    assert registrar.renames() == [("status", "dashboard__status")]
    assert any("重名" in message for message in logger.warnings)


def test_alias_conflict_on_both_attempts_gives_up() -> None:
    """前缀名仍被同一别名占用时整条放弃（只记 warning，不抛异常）。"""
    registry = FakeCommandRegistry()
    registry.register(command("stat", aliases=("status",)))
    registry.register(command("dash", aliases=("dashboard__status",)))
    registrar, _registry, logger = make_registrar(registry)

    registrar.register(command("status"))

    assert registry.get("dashboard__status").name == "dash"
    assert registrar.renames() == []
    assert any("跳过注册" in message for message in logger.warnings)


def test_both_names_taken_skips_without_raising() -> None:
    """A64：原名与前缀名都被占用时只记 warning，跳过注册，不阻断插件加载。"""
    registry = FakeCommandRegistry()
    registry.register(command("status"))
    registry.register(command("dashboard__status"))
    registrar, _registry, logger = make_registrar(registry)

    registrar.register(command("status"))  # 不抛异常

    assert registry.get("status").source == ""
    assert registry.get("dashboard__status").source == ""
    assert any("跳过注册" in message for message in logger.warnings)
    # 未成功注册的插件不记录清理回调
    assert registrar._registered == set()


def test_prefixed_true_keeps_legacy_semantics() -> None:
    """A66：prefixed=True 时行为与改造前一致（一律加 {plugin}__ 前缀）。"""
    registrar, registry, _logger = make_registrar()

    registrar.register(command("ping"), prefixed=True)

    assert registry.get("ping") is None
    assert registry.get("dashboard__ping") is not None
    assert registry.get("dashboard__ping").source == "dashboard"


def test_decorator_usage_registers_handler_and_permission() -> None:
    """装饰器用法：@registrar.register("ping", description=..., permission=1)。"""
    registrar, registry, _logger = make_registrar()

    @registrar.register("ping", description="响应测试", usage="[次数]", permission=1)
    async def _ping(ctx: Any) -> str:
        return "pong"

    registered = registry.get("ping")
    assert registered is not None
    assert registered.handler is _ping
    assert registered.description == "响应测试"
    assert registered.usage == "[次数]"
    assert registered.permission == 1
    assert registered.help_line.endswith("[来源: dashboard]")


def test_unregister_all_removes_commands_and_renames() -> None:
    """A58 的注册桥部分：unregister_all 摘除命令并清空改名记录。"""
    cleanups: list[Any] = []
    registrar, registry, _logger = make_registrar(cleanups=cleanups)
    registrar.register(command("status"))
    assert cleanups, "首次注册成功应记录清理回调"

    registrar.unregister_all()

    assert registry.names() == []
    assert registrar.renames() == []


def test_unavailable_registry_raises() -> None:
    registrar = PluginCommandRegistrar(
        plugin_name="p", registry=None, record_cleanup=None, logger=None
    )
    assert registrar.available is False
    registrar.unregister_all()  # 幂等
    with pytest.raises(RuntimeError):
        registrar.register(command("x"))


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__]))
