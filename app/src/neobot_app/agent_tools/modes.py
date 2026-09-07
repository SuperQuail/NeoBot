"""Task-tool presentations: compact native calls or programmatic orchestration."""
from __future__ import annotations

import warnings


NATIVE_TOOLS = frozenset({
    "read", "write", "edit", "glob", "grep", "read_image", "lsp",
    "run_python", "pwsh", "bash", "web_search", "web_fetch",
    "job_list", "job_output", "job_kill", "todo_write",
    "ask_user_question", "question_status", "enter_plan_mode", "exit_plan_mode", "skill",
})

# These names add no capability beside the canonical task tools. Directory
# listing, binary writes, downloads, and chat delivery are deliberately absent.
LEGACY_FILE_ALIASES = {
    "sandbox_manager__read_file": "read",
    "sandbox_manager__write_file": "write",
    "sandbox_manager__edit_file": "edit",
    "sandbox_manager__glob_files": "glob",
    "sandbox_manager__grep_files": "grep",
}


def resolve_mode(mode: str, *, ptc_enabled: bool) -> str:
    if mode == "both":
        warnings.warn("agent.tools.mode=both is deprecated and now selects compact native mode; update it to native",
                      FutureWarning, stacklevel=2)
        return "native"
    if mode not in {"native", "ptc"}:
        raise ValueError("agent.tools.mode must be native or ptc")
    if mode == "ptc" and not ptc_enabled:
        raise ValueError("PTC mode requires agent.tools.ptc_enabled=true")
    return mode
