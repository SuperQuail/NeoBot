"""Default deployment contract and keyless smoke against the installed pylsp."""
from __future__ import annotations

import os
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from neobot_app.agent_tools.contracts import ToolContext
from neobot_app.agent_tools.lsp import LspTools
from neobot_app.agent_tools.lsp_defaults import (
    PYTHON_LSP_WORKER_FLAG,
    default_python_lsp_servers,
)

CONTEXT = ToolContext(owner="lsp-smoke", chat_flow_id="private:100")


def test_defaults_are_isolated_fresh_and_lazy(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    first = default_python_lsp_servers()
    assert set(first) == {".py", ".pyi"}
    for config in first.values():
        assert config == {"command": [sys.executable, "-I", "-m", "pylsp"], "language_id": "python"}
    first[".py"]["command"].append("changed")
    assert first[".pyi"]["command"][-1] == "pylsp"
    assert default_python_lsp_servers()[".py"]["command"][-1] == "pylsp"
    client = LspTools(lambda _: tmp_path, default_python_lsp_servers())
    assert client.definitions()
    assert client._clients == {}


def test_frozen_default_uses_worker_not_python_module(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(Path("deployment") / "Bot.exe"))
    for config in default_python_lsp_servers().values():
        assert config["command"] == [sys.executable, PYTHON_LSP_WORKER_FLAG]
        assert "-m" not in config["command"]


async def test_empty_mapping_explicitly_disables_lsp(tmp_path):
    tools = LspTools(lambda _: tmp_path, {})
    assert tools.definitions() == []
    result = await tools.execute("lsp", {}, CONTEXT)
    assert result["error"]["code"] == "tool_unavailable"
    assert tools._clients == {}
    await tools.close()


def test_deployment_override_wins_without_mutating_defaults(tmp_path):
    servers = default_python_lsp_servers()
    override = {"command": [sys.executable, "-I", "-c", "pass"], "language_id": "custom-python"}
    servers.update({".py": override})
    tools = LspTools(lambda _: tmp_path, servers)
    assert tools._servers[".py"] == (override["command"], "custom-python")
    assert tools._servers[".pyi"][1] == "python"
    assert default_python_lsp_servers()[".py"]["language_id"] == "python"


@pytest.mark.parametrize("extension", [".py", ".pyi"])
async def test_installed_pylsp_hover_definition_and_cleanup(tmp_path, extension):
    # A formal dependency must be installed. Do not importorskip/mock this smoke.
    assert version("python-lsp-server")
    await _assert_navigation(tmp_path, extension, default_python_lsp_servers())


async def _assert_navigation(tmp_path, extension, servers):
    source = tmp_path / ("sample" + extension)
    source.write_text(
        "def greet(name: str) -> str:\n"
        "    \"\"\"Return a friendly greeting.\"\"\"\n"
        "    return name\n\n"
        "answer = greet(\"Neo\")\n",
        encoding="utf-8",
    )
    # Isolated launch must ignore malicious modules in the owner-controlled cwd.
    (tmp_path / "pylsp.py").write_text("raise RuntimeError(\"workspace shadow loaded\")", encoding="utf-8")
    tools = LspTools(lambda _: tmp_path, servers, timeout_seconds=30)
    assert tools._clients == {}
    process = None
    try:
        args = {"path": source.name, "line": 5, "column": 11}
        hover = await tools.execute("lsp", {**args, "operation": "hover"}, CONTEXT)
        assert hover["ok"], hover
        assert "greet" in hover["contents"]
        assert "Return a friendly greeting" in hover["contents"]
        process = next(iter(tools._clients.values())).process
        assert process is not None and process.returncode is None
        definition = await tools.execute("lsp", {**args, "operation": "definition"}, CONTEXT)
        assert definition["ok"], definition
        assert any(location["path"] == source.name and location["range"]["start"] == {"line": 1, "column": 5}
                   for location in definition["locations"]), definition
        assert next(iter(tools._clients.values())).process is process
        references = await tools.execute("lsp", {**args, "operation": "references"}, CONTEXT)
        assert references["ok"], references
        assert any(location["path"] == source.name and location["range"]["start"]["line"] == 5
                   for location in references["locations"]), references
        unsupported = await tools.execute("lsp", {**args, "operation": "implementation"}, CONTEXT)
        assert unsupported["error"]["code"] == "lsp_unsupported_operation", unsupported
        assert tools._clients == {}
        assert process.returncode is not None
    finally:
        await tools.close()
    assert tools._clients == {}
    assert process is not None and process.returncode is not None


@pytest.mark.parametrize("simulate_frozen", [False, True])
async def test_cli_stdio_worker_never_imports_bot_bootstrap(tmp_path, simulate_frozen):
    source_root = Path(__file__).resolve().parents[3] / "src"
    # A denied import would terminate the real worker and fail navigation.
    script = f"""
import builtins, sys
sys.path.insert(0, {str(source_root)!r})
sys.frozen = {simulate_frozen!r}
if sys.frozen:
    import subprocess
    class ForbiddenPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            raise AssertionError("Frozen worker must not spawn an external Python")
    subprocess.Popen = ForbiddenPopen
sys.argv = ["neobot", {PYTHON_LSP_WORKER_FLAG!r}]
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.startswith(("neobot_app.bootstrap", "neobot_app.config", "neobot_app.runtime")):
        raise AssertionError("Worker imported Bot application state: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
import neobot_app.cli
"""
    servers = {".py": {"command": [sys.executable, "-I", "-c", script], "language_id": "python"}}
    await _assert_navigation(tmp_path, ".py", servers)


@pytest.mark.skipif(not os.environ.get("NEOBOT_LSP_SMOKE_EXE"), reason="Explicit PyInstaller smoke artifact not supplied")
@pytest.mark.parametrize("extension", [".py", ".pyi"])
async def test_frozen_pylsp_hover_definition(tmp_path, monkeypatch, extension):
    """Set NEOBOT_LSP_SMOKE_EXE to the built lsp_frozen_worker_entry fixture."""
    executable = Path(os.environ["NEOBOT_LSP_SMOKE_EXE"]).resolve(strict=True)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "no-external-python"))
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "no-conda"))
    servers = {extension: {"command": [str(executable), PYTHON_LSP_WORKER_FLAG], "language_id": "python"}}
    await _assert_navigation(tmp_path, extension, servers)


@pytest.mark.parametrize("mode", ["missing", "crash"])
async def test_launch_failure_is_sanitized_and_cleans_cache(tmp_path, mode):
    (tmp_path / "sample.py").write_text("value = 1\n", encoding="utf-8")
    command = ([str(tmp_path / "SECRET-missing-executable.exe")] if mode == "missing" else
               [sys.executable, "-I", "-c", "raise RuntimeError(\"SECRET server failure\")"])
    tools = LspTools(lambda _: tmp_path, {".py": {"command": command, "language_id": "python"}})
    try:
        for _ in range(2):
            result = await tools.execute("lsp", {"path": "sample.py", "line": 1, "column": 1, "operation": "hover"}, CONTEXT)
            assert not result["ok"]
            assert result["error"]["code"] == ("lsp_unavailable" if mode == "missing" else "lsp_protocol_error")
            assert "SECRET" not in str(result)
            assert tools._clients == {}
    finally:
        await tools.close()
