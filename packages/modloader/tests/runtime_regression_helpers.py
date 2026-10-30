"""依赖和配置回归用的最小包插件，不连接任何外部服务。"""

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.runtime import PluginRuntime


class LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


def make_plugin(
    root: Path,
    name: str,
    *,
    dependencies: tuple[str, ...] = (),
    code_dependencies: tuple[str, ...] | None = None,
    version: str = "1.0.0",
    enabled: bool = True,
    hot_reload: bool = True,
    defaults: dict[str, int] | None = None,
    body: str = "",
) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [f'name = "{name}"', f'version = "{version}"']
    lines.append(f"enabled = {str(enabled).lower()}")
    lines.append(f"hot_reload = {str(hot_reload).lower()}")
    if dependencies:
        lines.append(f"dependencies = {list(dependencies)!r}")
    if defaults:
        lines.append("[config]")
        lines.extend(f"{key} = {value}" for key, value in defaults.items())
    (directory / "plugin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    code_dependencies = dependencies if code_dependencies is None else code_dependencies
    (directory / "__init__.py").write_text(
        "from neobot_modloader import Plugin\n"
        f"plugin = Plugin({name!r}, version={version!r}, dependencies={code_dependencies!r})\n" + body,
        encoding="utf-8",
    )
    return directory


def make_runtime(root: Path, **kwargs: Any) -> PluginRuntime:
    return PluginRuntime(
        plugin_dir=root / "plugins",
        data_dir=root / "data",
        adapter=object(),
        logger_factory=LoggerFactory(),
        **kwargs,
    )


async def start_runtime(runtime: PluginRuntime) -> None:
    runtime.load_all()
    await runtime.load_registered()
    await runtime.start_all()
