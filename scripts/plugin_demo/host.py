"""将最终插件 ZIP 安装进独立目录，启动真实运行时和网页面板。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.installer import PluginInstaller
from neobot_modloader.loader import FilesystemPluginLoader, LoadedPlugin
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.sdk.storage import close_runtime_storage
from neobot_modloader.sdk.tooling import build_package, export_contract

from .ports import DEMO_PICTURE_URI, DemoAdapter, DemoLiveTransport, demo_image_download

DEMO_PASSWORD = "NeoBot-Panel-2026"
REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMING_SOURCE = REPO_ROOT / "app/src/neobot_app/builtin_plugins/streaming_parser"


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


class DemoDashboardServer(DashboardServer):
    async def _probe_bot(self) -> dict:
        info = await super()._probe_bot()
        info["avatar_url"] = DEMO_PICTURE_URI
        return info


class DemoLoader(FilesystemPluginLoader):
    def _load_package(self, plugin_path: Path):
        loaded = super()._load_package(plugin_path)
        if isinstance(loaded, LoadedPlugin) and loaded.name == "streaming_parser":
            module = next(
                sys.modules[name]
                for name in loaded.module_names
                if getattr(sys.modules[name], "plugin", None) is loaded.plugin
            )
            module.HttpxTransport = DemoLiveTransport
            cache = module.AssetCache

            def assets(*arguments, **options):
                return cache(*arguments, downloader=demo_image_download, **options)

            module.AssetCache = assets
        return loaded


@dataclass
class DemoApplication:
    server: DashboardServer
    runtime: PluginRuntime
    adapter: DemoAdapter
    data_dir: Path

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.bound_port}"

    async def close(self) -> None:
        await self.server.stop()
        for name in reversed(list(self.runtime.manager.names())):
            await self.runtime.unload_plugin(name, force=True)
        close_runtime_storage(self.runtime)


async def create_demo(data_dir: Path, *, port: int = 19981, samples: tuple[Path, ...] = ()) -> DemoApplication:
    """此目录只放演示数据；不会读取用户真实配置、会话或外部服务凭据。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    packages = data_dir / "packages"
    packages.mkdir(exist_ok=True)
    archives: dict[str, bytes] = {}
    for source in (STREAMING_SOURCE, *samples):
        exported = export_contract(source)
        if not exported.ok:
            raise RuntimeError("导出演示插件失败: " + "; ".join(exported.errors))
        package = packages / f"{source.name}.zip"
        built = build_package(source, package)
        if not built.ok:
            raise RuntimeError("打包演示插件失败: " + "; ".join(built.errors))
        archives[source.name] = package.read_bytes()

    async def fetcher(url: str) -> bytes:
        for name, payload in archives.items():
            if f"/{name}/" in url:
                return payload
        raise ValueError("演示安装器没有声明该插件包")

    installer = PluginInstaller(plugin_dir=data_dir / "plugins", fetcher=fetcher)
    adapter = DemoAdapter()
    runtime = PluginRuntime(
        plugin_dir=installer.plugin_dir,
        data_dir=data_dir / "runtime",
        adapter=adapter,
        loader=DemoLoader(namespace="neobot_demo_plugins"),
        logger_factory=_LoggerFactory(),
        installer=installer,
    )
    config = data_dir / "config.toml"
    config.write_text('version = "0.6.0"\n', encoding="utf-8")
    env = data_dir / ".env"
    env.write_text("# 演示不使用真实平台凭据。\n", encoding="utf-8")
    panel_data = data_dir / "panel"
    PanelPasswordStore(panel_data / "auth.json").set_password(DEMO_PASSWORD)
    server = DemoDashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=port),
        data_dir=panel_data,
        logger=NullLogger(),
        adapter=adapter,
        plugin_control=runtime.control,
        config_path=config,
        env_path=env,
        backup_dir=data_dir / "backups",
    )
    application = DemoApplication(server, runtime, adapter, data_dir)
    try:
        for name in archives:
            result = await installer.install(f"demo/{name}")
            if not result.ok:
                raise RuntimeError(f"演示包安装失败: {result.error}")
        runtime.load_all()
        await runtime.load_registered()
        await runtime.start_all()
        failures = [item for item in runtime.snapshot_plugins() if item.state != "running"]
        if failures:
            raise RuntimeError("演示插件未就绪: " + "; ".join(f"{item.name}: {item.error}" for item in failures))
        await server.start()
        return application
    except BaseException:
        await application.close()
        raise


async def serve_demo(data_dir: Path, *, port: int, samples: tuple[Path, ...]) -> None:
    application = await create_demo(data_dir, port=port, samples=samples)
    try:
        print(f"演示地址：{application.url}/#/plugins", flush=True)
        print(f"演示密码：{DEMO_PASSWORD}", flush=True)
        print("群与直播间使用合成数据；插件包、数据库、轮询和面板实际运行。", flush=True)
        print(f"演示数据：{application.data_dir}", flush=True)
        await asyncio.Event().wait()
    finally:
        await application.close()
