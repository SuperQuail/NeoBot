"""工程生成、显式导出与无执行静态校验的回归。"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from neobot_modloader.sdk.tooling import check_project, export_contract, init_project
from plugin_tooling_helpers import make_project, write_contract


def test_init_creates_a_ready_to_check_project(tmp_path: Path) -> None:
    path = tmp_path / "hello"
    report = init_project(path, "hello")
    assert report.ok, report.errors
    assert (path / "__init__.py").is_file()
    assert (path / "tests" / "test_plugin.py").is_file()
    assert (path / "AGENTS.md").is_file()
    assert (path / "GUIDE.md").is_file()
    assert check_project(path).ok
    assert export_contract(path, check=True).ok


def test_init_guide_explains_real_configuration_and_ping_command(tmp_path: Path) -> None:
    path = tmp_path / "hello"
    report = init_project(path, "hello")
    assert report.ok, report.errors
    contract = json.loads((path / "plugin.contract.json").read_text(encoding="utf-8"))
    assert contract["actions"] == []
    assert len(contract["guides"]) == 1
    guide = contract["guides"][0]
    assert guide["id"] == "first-use"
    assert guide["title"] == "从零配置并验证"
    assert guide["completion_action"] is None
    assert guide["demo"] == {"config": {"greeting": "你好，NeoBot"}}
    steps = guide["steps"]
    assert [(step["target"], step.get("form")) for step in steps] == [
        ("config", "start"),
        ("config.greeting", "edit"),
        ("config", "validate"),
        ("config", "save"),
        ("config", "saved"),
        ("config.greeting", None),
    ]
    assert steps[0]["example"] == {"greeting": "pong"}
    assert all(step["example"] == {"greeting": "你好，NeoBot"} for step in steps[1:5])
    assert all(step["chapter"] and step["text"] for step in steps)
    assert "不会发送真实保存请求" in steps[3]["text"]
    assert "重载" in steps[4]["text"]
    assert steps[-1]["command"] == {
        "text": "/ping",
        "context": "在与机器人的私聊中发送",
        "reply": "你好，NeoBot",
    }
    assert "/help" in steps[-1]["text"]
    metadata = tomllib.loads((path / "plugin.toml").read_text(encoding="utf-8"))
    assert metadata["python_dependencies"] == ["pydantic>=2,<3"]


def test_init_never_overwrites_an_existing_directory(tmp_path: Path) -> None:
    path = tmp_path / "hello"
    path.mkdir()
    marker = path / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    report = init_project(path, "hello")
    assert not report.ok
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (path / "plugin.toml").exists()


def test_generated_business_test_runs_against_real_dispatch(tmp_path: Path) -> None:
    path = tmp_path / "hello"
    assert init_project(path, "hello").ok
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(path / "tests"), "-p", "no:cacheprovider", "-q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed" in completed.stdout


async def test_generated_command_runs_through_host_help_and_collision_handling(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from neobot_app.commands.model import Command
    from neobot_app.commands.registry import CommandRegistry
    from neobot_app.commands.service import CommandService
    from neobot_modloader.context import RuntimePluginContext
    from neobot_modloader.loader import FilesystemPluginLoader

    path = tmp_path / "hello"
    assert init_project(path, "hello").ok
    registry = CommandRegistry()
    registry.register(Command(name="ping", description="宿主占位", handler=AsyncMock()))
    adapter = SimpleNamespace(self_id=10001, send=AsyncMock())
    loader = FilesystemPluginLoader()
    loaded = loader.load_one(path)
    context = RuntimePluginContext(
        plugin_name="hello",
        plugin_dir=path,
        data_dir=tmp_path / "data",
        config={"greeting": "新回复"},
        logger=None,
        adapter=adapter,
        app_commands=registry,
    )
    service = CommandService(
        config=SimpleNamespace(
            bot=SimpleNamespace(account=10001),
            chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[]),
        ),
        registry=registry,
        send_callback=AsyncMock(),
        register_builtins=False,
    )
    try:
        await loaded.plugin.on_load(context)
        await loaded.plugin.on_start()
        command = registry.match("/hello__ping")[0]
        assert command.permission == 0
        assert "[来源: hello]" in command.help_line
        assert "发送配置中的回复内容" in command.help_line
        message = SimpleNamespace(user_id=42, message=[{"type": "text", "data": {"text": "/hello__ping"}}])
        result = await service.handle_message(message, kind="private", queue_key="42")
        assert result.consumed
        assert adapter.send.await_args.args[1] == "新回复"
    finally:
        context.app_commands.unregister_all()
        await loaded.plugin.on_stop()
        loader.clear_module_cache(loaded.module_names)
    assert registry.match("/hello__ping")[0] is None


def test_static_check_does_not_execute_plugin_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    path = make_project(
        tmp_path,
        body=f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nraise RuntimeError('do not import')\n",
    )
    report = check_project(path)
    assert report.ok, report.errors
    assert report.executes_plugin is False
    assert not marker.exists()


@pytest.mark.parametrize("settings", [[], [{"id": "business", "input_action": "save"}]])
def test_static_check_and_cli_reject_removed_settings_without_importing_plugin(tmp_path: Path, settings) -> None:
    marker = tmp_path / "executed.txt"
    path = make_project(
        tmp_path,
        body=f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nraise RuntimeError('do not import')\n",
    )
    contract_path = path / "plugin.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["settings"] = settings
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    report = check_project(path)
    assert not report.ok
    assert report.errors == ("plugin.contract.json: 契约含未知字段",)
    assert report.executes_plugin is False
    assert not marker.exists()

    completed = subprocess.run(
        [sys.executable, "-m", "neobot_modloader.sdk", "check", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 1
    cli_report = json.loads(completed.stdout)
    assert cli_report["ok"] is False
    assert cli_report["errors"] == ["plugin.contract.json: 契约含未知字段"]
    assert cli_report["executes_plugin"] is False
    assert "Traceback" not in completed.stderr
    assert not marker.exists()


@pytest.mark.parametrize("value", ["../outside.json", "/outside.json", "C:/outside.json"])
def test_static_check_rejects_contract_path_escape(tmp_path: Path, value: str) -> None:
    path = make_project(tmp_path)
    (path / "plugin.toml").write_text(
        f'name = "sample"\nversion = "0.1.0"\n[sdk]\nversion = 1\ncontract = "{value}"\n',
        encoding="utf-8",
    )
    report = check_project(path)
    assert not report.ok
    assert any("contract" in error for error in report.errors)


def test_static_check_reports_contract_identity_mismatch(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    write_contract(path, "different")
    report = check_project(path)
    assert not report.ok
    assert any("name" in error for error in report.errors)


def test_export_marks_execution_and_clears_imported_modules(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    path = make_project(
        tmp_path,
        body=f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
    )
    before = set(sys.modules)
    report = export_contract(path)
    assert report.ok, report.errors
    assert report.executes_plugin is True
    assert marker.is_file()
    assert not any(name.startswith("neobot_sdk_export.") for name in set(sys.modules) - before)


def test_export_check_detects_stale_contract_without_rewriting_it(tmp_path: Path) -> None:
    path = make_project(tmp_path, body="plugin.description = 'updated'\n")
    contract = path / "plugin.contract.json"
    before = contract.read_bytes()
    report = export_contract(path, check=True)
    assert not report.ok
    assert contract.read_bytes() == before
    assert export_contract(path).ok
    assert export_contract(path, check=True).ok


def test_export_supports_contract_in_a_plain_metadata_directory(tmp_path: Path) -> None:
    path = make_project(tmp_path)
    manifest = path / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'contract = "plugin.contract.json"', 'contract = "metadata/contract.json"'
        ),
        encoding="utf-8",
    )
    assert export_contract(path).ok
    assert (path / "metadata" / "contract.json").is_file()
    assert check_project(path).ok


def test_cli_json_is_not_corrupted_by_plugin_stdout(tmp_path: Path) -> None:
    path = make_project(tmp_path, body="print('plugin output')\n")
    completed = subprocess.run(
        [sys.executable, "-m", "neobot_modloader.sdk", "export", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
    assert "plugin output" in completed.stderr


def test_cli_static_failure_returns_nonzero_and_structured_errors(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "neobot_modloader.sdk", "check", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode != 0
    report = json.loads(completed.stdout)
    assert report["ok"] is False
    assert report["errors"]


def test_plugin_exit_cannot_turn_export_into_success(tmp_path: Path) -> None:
    path = make_project(tmp_path, body="raise SystemExit(0)\n")
    completed = subprocess.run(
        [sys.executable, "-m", "neobot_modloader.sdk", "export", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode != 0
    assert json.loads(completed.stdout)["ok"] is False


def test_export_releases_the_namespace_when_author_code_exits(tmp_path: Path) -> None:
    path = make_project(tmp_path, body="raise SystemExit(0)\n")
    before = set(sys.modules)
    report = export_contract(path)
    imported = {name for name in set(sys.modules) - before if name.startswith("neobot_sdk_export.")}
    try:
        assert not report.ok
        assert not imported
    finally:
        for name in imported:
            sys.modules.pop(name, None)
