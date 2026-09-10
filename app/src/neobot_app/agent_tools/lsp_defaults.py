"""Deployment-owned Python LSP defaults (lazy stdio, no PATH or Node dependency).

The frozen CLI must dispatch ``PYTHON_LSP_WORKER_FLAG`` before importing the
application/bootstrap. PyInstaller must collect pylsp entry-point metadata,
plugins and Jedi/Parso grammar data; see the deployment hook.
"""
from __future__ import annotations

import sys
from typing import Any

PYTHON_LSP_WORKER_FLAG = "--neobot-python-lsp-worker"


def default_python_lsp_servers() -> dict[str, dict[str, Any]]:
    """Return fresh extension mappings; constructing defaults starts no process.

    Callers may replace entries or omit defaults when composing low-level
    LspTools. User-facing disabling uses ``lsp_enabled=false``; an empty user
    server mapping retains these defaults. Source installs use this interpreter
    in isolated mode so a workspace ``pylsp.py``
    cannot shadow the installed server. A frozen executable is *not* Python; it
    re-enters only the dedicated stdio worker, never ``Bot.exe -m pylsp``.
    """
    # ⚠️ sys.executable 在 Linux/macOS 上可能是符号链接（uv / pyenv / 系统
    # python3 建的 venv 都如此）：这里必须原样使用，下游（LspTools、部署配置
    # 解析）也不得用 Path.resolve()/realpath() 解析它——穿透到基础解释器后
    # 子进程看不到 venv 的 site-packages，pylsp 起不来。详见 lsp.py 中的说明。
    command = (
        [sys.executable, PYTHON_LSP_WORKER_FLAG]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-I", "-m", "pylsp"]
    )
    return {
        extension: {"command": list(command), "language_id": "python"}
        for extension in (".py", ".pyi")
    }


def run_python_lsp_worker() -> None:
    """Run only pylsp over binary stdio; never accept CLI TCP/WebSocket options."""
    if getattr(sys, "frozen", False):
        from jedi.api import environment

        # Jedi otherwise probes VIRTUAL_ENV/CONDA_PREFIX or tries to execute
        # sys.executable as Python. This dedicated child already embeds Python;
        # keep analysis in this worker, independent of external interpreters.
        environment.get_default_environment = environment.InterpreterEnvironment

    from pylsp.python_lsp import PythonLSPServer, start_io_lang_server

    server_class = PythonLSPServer
    if getattr(sys, "frozen", False):
        class FrozenPythonLSPServer(PythonLSPServer):
            def m_initialize(self, initializationOptions=None, **kwargs):
                # pylsp 1.15 formats hover signatures by spawning Python -m
                # black. Formatting is cosmetic; retain the original signature
                # rather than ever treating the frozen Bot executable as Python.
                options = dict(initializationOptions or {})
                settings = dict(options.get("pylsp", {}))
                settings["signature"] = {**settings.get("signature", {}), "formatter": None}
                options["pylsp"] = settings
                return super().m_initialize(initializationOptions=options, **kwargs)

        server_class = FrozenPythonLSPServer

    start_io_lang_server(sys.stdin.buffer, sys.stdout.buffer, False, server_class)
