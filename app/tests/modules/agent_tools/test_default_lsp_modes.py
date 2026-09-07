"""Real dependency-backed navigation through both shared runtime presentations."""
from __future__ import annotations

import pytest

from neobot_app.agent_tools.contracts import ToolContext
from neobot_app.agent_tools.runtime import AgentToolRuntime
from neobot_app.config.schemas.bot import AgentToolsConfig
from neobot_app.runtime.sandbox_service import SandboxService


@pytest.mark.parametrize("mode", ["native", "ptc"])
async def test_default_python_lsp_through_selected_mode(tmp_path, mode):
    runtime = AgentToolRuntime(SandboxService(tmp_path / "sandbox"), state_dir=tmp_path / "state",
                               config=AgentToolsConfig(mode=mode))
    context = ToolContext("group:123:main", "group:123", user_id=7, human_request=True)

    async def call(name, args):
        if mode == "native":
            return await runtime.execute(name, args, context)
        result = await runtime.execute("run_code", {"code": f"return await tools.{name}({args!r})",
                "description": "Use the installed Python language server"}, context)
        return result["result"]

    try:
        assert runtime.lsp._clients == {}
        await call("write", {"file_path": "sample.py", "content":
            'def greet(name: str) -> str:\n    """Return a greeting."""\n    return "hello " + name\n\nmessage = greet("NeoBot")\n'})
        hovered = await call("lsp", {"operation": "hover", "path": "sample.py", "line": 5, "column": 12})
        assert "greet" in str(hovered["contents"])
        definition = await call("lsp", {"operation": "definition", "path": "sample.py", "line": 5, "column": 12})
        assert definition["locations"][0]["path"] == "sample.py"
        assert definition["locations"][0]["range"]["start"]["line"] == 1
    finally:
        await runtime.close()
    assert runtime.lsp._clients == {}
