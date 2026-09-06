"""PyInstaller smoke-only entrypoint; deliberately contains no Bot service.

Uses the same helper and dispatch contract as the real CLI. This fixture proves
worker bundling only, not the packaging of all unrelated Bot dependencies.
"""
import sys

from neobot_app.agent_tools.lsp_defaults import (
    PYTHON_LSP_WORKER_FLAG,
    run_python_lsp_worker,
)

if __name__ == "__main__":
    if sys.argv[1:] != [PYTHON_LSP_WORKER_FLAG]:
        raise SystemExit("Smoke fixture only accepts the internal LSP worker flag")
    run_python_lsp_worker()
