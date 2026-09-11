"""模型库端到端仿真：添加供应商 -> 拉取模型 -> 新建模型 -> 保存/刷新 -> 注册。

用一个本地 stub 供应商（真实的 HTTP 服务）替代外部 API，覆盖：
- 面板添加供应商后，模型编辑里的供应商候选立即包含它；
- 能拉取该供应商的模型列表并用于选择；
- 保存模型后立即出现在列表里，重启面板（刷新）后依然存在；
- 模型条目本身不含任何 API Key，密钥来自供应商环境变量；
- 模型类型（生图/视觉/…）可保存并在重载后进入运行时注册表。
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from aiohttp import web

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_chat import get_model_registry

from test_dashboard_api import (
    PASSWORD,
    _FakeAdapter,
    _FakeControl,
    _free_port,
    _login,
)

PROVIDER = "StubProvider"
STUB_KEY = "sk-stub-provider-key"
STUB_MODELS = ["stub-image-xl", "stub-image-fast", "stub-chat-1"]


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


async def _start_stub() -> tuple[web.AppRunner, str]:
    """启动一个假的 OpenAI 兼容供应商，只认固定的 Bearer Key。"""
    app = web.Application()

    async def models(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {STUB_KEY}":
            return web.json_response({"error": {"message": "invalid api key"}}, status=401)
        return web.json_response({"data": [{"id": name} for name in STUB_MODELS]})

    app.router.add_get("/v1/models", models)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", _free_port())
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/v1"


class _HostCommands:
    """模拟宿主 config.reload 命令：重新读取 config.toml 并注册模型。"""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def call(self, name: str):
        if name != "config.reload":
            return {"status": "error", "message": f"未知命令: {name}"}
        import tomlkit

        from neobot_app.config.loader.converter import dict_to_dataclass
        from neobot_app.config.loader.manager import Config
        from neobot_app.config.schemas.bot import BotConfig

        parsed = tomlkit.parse(self._config_path.read_text(encoding="utf-8")).unwrap()
        config_obj = dict_to_dataclass(parsed, BotConfig)
        Config.register_models(config_obj)
        return {"status": "ok", "message": "配置已重载"}


class _Services:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, name: str, default=None):
        return self._mapping.get(name, default)


async def _start_panel(tmp_path: Path, env_path: Path, config_path: Path):
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=tmp_path / "data",
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=_FakeControl(),
        services=_Services({"host_commands": _HostCommands(config_path)}),
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}"


@pytest.fixture()
async def simulated_panel(tmp_path: Path, monkeypatch):
    runner, base_url = await _start_stub()
    # 默认模型库（DeepSeek 系列）需要平台凭据才能注册
    monkeypatch.setenv("DeepSeek_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DeepSeek_APIKey", "sk-stub-deepseek")
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_URL=https://api.deepseek.com\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)

    server, base = await _start_panel(tmp_path, env_path, config_path)
    try:
        yield {
            "server": server,
            "base": base,
            "config_path": config_path,
            "env_path": env_path,
            "tmp_path": tmp_path,
            "provider_url": base_url,
        }
    finally:
        await server.stop()
        await runner.cleanup()
        for key in (f"{PROVIDER}_URL", f"{PROVIDER}_APIKey"):
            os.environ.pop(key, None)
        get_model_registry().clear()


async def test_provider_then_pull_models_then_save_visible_immediately(
    simulated_panel,
) -> None:
    """添加供应商 -> 候选里出现 -> 拉取模型 -> 新建模型 -> 立即可见 -> 重启后仍在。"""
    panel = simulated_panel
    base, config_path = panel["base"], panel["config_path"]
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        # 1) 一键添加供应商（写入 .env，Key 只写不读）
        added = await client.post(
            base + "/api/config/env/platform",
            headers=headers,
            json={"name": PROVIDER, "url": panel["provider_url"], "api_key": STUB_KEY},
        )
        assert added.status_code == 200, added.text

        # 2) 模型库读取：新供应商立即出现在候选里
        models = await client.get(base + "/api/config/models", headers={"X-Token": token})
        payload = models.json()
        assert PROVIDER in payload["provider_options"]
        assert "chat" in payload["model_type_labels"]
        assert payload["role_model_types"]["creator_image_models"] == "image"

        # 3) 拉取该供应商的模型列表
        pulled = await client.post(
            base + "/api/config/models/provider-models",
            headers=headers,
            json={"provider": PROVIDER},
        )
        assert pulled.status_code == 200, pulled.text
        assert pulled.json()["ok"] is True
        assert pulled.json()["models"] == sorted(STUB_MODELS, key=str.casefold)

        # 4) 新建一个生图模型（Key 来自供应商，条目本身没有 key 字段）
        entry = {
            "key": "stub-image",
            "model_type": "image",
            "description": "仿真生图模型",
            "provider": PROVIDER,
            "model_name": "stub-image-xl",
            "native_vision": False,
            "use_system_proxy": False,
            "balance_query_hint": "",
        }
        saved = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={"action": "upsert", "entry": entry, "revision": payload["revision"]},
        )
        assert saved.status_code == 200, saved.text
        saved_payload = saved.json()
        library = {item["key"]: item for item in saved_payload["models"]["library"]}
        assert "stub-image" in library, saved_payload["models"]["library"]
        created = library["stub-image"]
        assert created["model_type"] == "image"
        assert created["type_label"] == "生图模型"
        assert created["key_configured"] is True
        assert created["url_configured"] is True
        assert "api_key" not in created["entry"]
        assert "apiKey" not in created["entry"]

        # 5) 重新读取（等价于刷新页面）：依然在
        again = await client.get(base + "/api/config/models", headers={"X-Token": token})
        keys = {item["key"] for item in again.json()["library"]}
        assert "stub-image" in keys

        # 6) 连通性测试：走真实 HTTP，命中 stub 的模型列表
        probed = await client.post(
            base + "/api/config/models/test",
            headers=headers,
            json={"key": "stub-image"},
        )
        assert probed.status_code == 200, probed.text
        probe_payload = probed.json()
        assert probe_payload["ok"] is True
        assert probe_payload["model_found"] is True
        assert probe_payload["proxy"] is False

    # 7) 重启面板（新实例读同一份文件）：模型仍然存在
    await panel["server"].stop()
    server, base2 = await _start_panel(panel["tmp_path"], panel["env_path"], config_path)
    panel["server"] = server
    try:
        token2, _ = await _login(base2)
        async with httpx.AsyncClient() as client:
            restarted = await client.get(
                base2 + "/api/config/models", headers={"X-Token": token2}
            )
        keys = {item["key"] for item in restarted.json()["library"]}
        assert "stub-image" in keys, "保存后重启（刷新）必须仍然可见"
        entry_after = next(
            item for item in restarted.json()["library"] if item["key"] == "stub-image"
        )
        assert entry_after["model_type"] == "image"
    finally:
        await panel["server"].stop()


async def test_new_model_without_key_gets_auto_reference(simulated_panel) -> None:
    """面板不再填写引用名：后端按模型名自动生成，重名自动追加序号。"""
    panel = simulated_panel
    base = panel["base"]
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        models = await client.get(base + "/api/config/models", headers={"X-Token": token})
        revision = models.json()["revision"]
        entry = {
            "model_type": "image",
            "description": "自动引用名模型",
            "provider": PROVIDER,
            "model_name": "Stub/Image XL",  # 大小写与斜杠都会被规整
        }
        first = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={"action": "upsert", "entry": entry, "revision": revision},
        )
        assert first.status_code == 200, first.text
        assert first.json()["saved_key"] == "stub-image-xl"

        # 同名再来一个 -> 自动加序号
        second = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={
                "action": "upsert",
                "entry": entry,
                "revision": first.json()["revision"],
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["saved_key"] == "stub-image-xl-2"

        keys = {item["key"] for item in second.json()["models"]["library"]}
        assert {"stub-image-xl", "stub-image-xl-2"} <= keys

        # 编辑已有条目时保留原引用名
        again = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={
                "action": "upsert",
                "entry": {
                    "key": "stub-image-xl",
                    "model_type": "image",
                    "description": "改过的描述",
                    "provider": PROVIDER,
                    "model_name": "Stub/Image XL",
                },
                "revision": second.json()["revision"],
            },
        )
        assert again.status_code == 200, again.text
        library = {item["key"]: item for item in again.json()["models"]["library"]}
        assert library["stub-image-xl"]["description"] == "改过的描述"
        assert len([k for k in library if k.startswith("stub-image-xl")]) == 2


async def test_model_type_and_registration_after_reload(simulated_panel) -> None:
    """保存并重载后：模型类型进入注册表，密钥来自供应商而不是模型条目。"""
    panel = simulated_panel
    base = panel["base"]
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        await client.post(
            base + "/api/config/env/platform",
            headers=headers,
            json={"name": PROVIDER, "url": panel["provider_url"], "api_key": STUB_KEY},
        )
        models = await client.get(base + "/api/config/models", headers={"X-Token": token})
        revision = models.json()["revision"]
        # 指向一个已存在的调用方，便于重载后校验注册结果
        saved = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={
                "action": "upsert",
                "entry": {
                    "key": "stub-chat",
                    "model_type": "chat",
                    "description": "仿真对话模型",
                    "provider": PROVIDER,
                    "model_name": "stub-chat-1",
                },
                "revision": revision,
            },
        )
        assert saved.status_code == 200, saved.text
        bound = await client.post(
            base + "/api/config/models/assignments",
            headers=headers,
            json={"assignments": {"agent_model_3": "stub-chat"}},
        )
        assert bound.status_code == 200, bound.text
        # 保存并重载（面板按钮的等价请求）
        reloaded = await client.post(
            base + "/api/config/models/assignments",
            headers=headers,
            json={
                "assignments": {"agent_model_3": "stub-chat"},
                "revision": bound.json()["revision"],
                "reload": True,
            },
        )
        assert reloaded.status_code == 200, reloaded.text

    registered = get_model_registry().get("stub-chat")
    assert registered.model_type == "chat"
    assert registered.provider_name == PROVIDER
    assert registered.base_url == panel["provider_url"]
    assert registered.api_key == STUB_KEY
    assert registered.create_provider().use_system_proxy is False
