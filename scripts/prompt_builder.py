#!/usr/bin/env python3
"""
NeoBot Prompt Builder — 提示词可视化编辑与预览工具。

三面板布局：
  左侧：原始提示词文本（可编辑），顶部下拉框选择来源
  右上：使用默认转义值预览
  右下：使用真实 config.toml 值预览（缺失项回退默认值）

编辑后通过保存按钮同步回来源：
  - 主 Agent → config.toml
  - 子 Agent → 对应 _build_system_prompt() 源码
  - 工具包   → 对应 build_xxx_package() 源码
"""

from __future__ import annotations

import ast
import re
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Any

from neobot_app.assembly.agents import AGENT_SHORT_DESCRIPTIONS, build_peer_descriptions

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_SRC = PROJECT_ROOT / "app" / "src"
CONFIG_PATH = PROJECT_ROOT / "app" / "data" / "config.toml"
BOT_SCHEMA_PATH = APP_SRC / "neobot_app" / "config" / "schemas" / "bot.py"
AGENTS_DIR = APP_SRC / "neobot_app" / "agents"
TOOLPACKAGE_DIR = APP_SRC / "neobot_app" / "toolpackage"

sys.path.insert(0, str(APP_SRC))

# ── Tokenizer ──────────────────────────────────────────────────────────────
_TOKENIZER_DIR = PROJECT_ROOT / "scripts" / "deepseek_v3_tokenizer" / "deepseek_v3_tokenizer"
_tokenizer_fn = None
_tokenizer_error = None


def _try_load_tokenizer() -> None:
    """Try to load the DeepSeek V3 tokenizer from the local scripts directory."""
    global _tokenizer_fn, _tokenizer_error
    try:
        import importlib.util

        # Ensure PyTorch is importable before loading transformers.
        # The tokenizer only needs transformers, but transformers checks for
        # PyTorch and will warn/fail if it can't find it.  We try to locate a
        # system PyTorch installation if one isn't already on sys.path.
        if importlib.util.find_spec("torch") is None:
            _inject_system_torch()

        spec = importlib.util.find_spec("transformers")
        if spec is None:
            raise ImportError("transformers 未安装")
        import transformers  # noqa: F401
        tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(_TOKENIZER_DIR), trust_remote_code=True,
        )

        def _encode(text: str) -> int:
            return len(tokenizer.encode(text))

        _tokenizer_fn = _encode
        _tokenizer_error = None
    except Exception as exc:
        _tokenizer_fn = None
        _tokenizer_error = str(exc)


def _inject_system_torch() -> None:
    """Search common locations for a system PyTorch installation and add to sys.path."""
    import os
    import subprocess

    candidates: list[str] = []

    # ---- 1. Ask the current Python interpreter where torch lives ----
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.__file__)"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            torch_init = result.stdout.strip()
            # torch.__file__ → .../torch/__init__.py → parent is the package dir
            pkg_dir = str(Path(torch_init).resolve().parent.parent)
            if pkg_dir not in sys.path:
                candidates.append(pkg_dir)
    except Exception:
        pass

    # ---- 2. pip show torch ----
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "torch"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Location:"):
                    loc = line.split(":", 1)[1].strip()
                    if loc and loc not in sys.path:
                        candidates.append(loc)
    except Exception:
        pass

    # ---- 3. Common Windows paths ----
    for base_env in os.environ.get("PATH", "").split(os.pathsep):
        base = base_env.strip()
        if not base:
            continue
        # Conda / venv patterns
        for tail in ("Lib/site-packages", "lib/site-packages", "site-packages"):
            candidate = str(Path(base).parent / tail)
            if candidate not in candidates:
                candidates.append(candidate)

    # ---- 4. Standard user-site path ----
    import site
    try:
        user_site = site.getusersitepackages()
        if user_site and user_site not in candidates:
            candidates.append(user_site)
    except Exception:
        pass
    try:
        for sp in site.getsitepackages():
            if sp and sp not in candidates:
                candidates.append(sp)
    except Exception:
        pass

    # ---- Apply candidates that exist ----
    injected = False
    for p in candidates:
        p = str(p)
        torch_init = os.path.join(p, "torch", "__init__.py")
        if os.path.isfile(torch_init) and p not in sys.path:
            sys.path.insert(0, p)
            injected = True

    if injected:
        # Force re-check
        import importlib
        importlib.invalidate_caches()


def count_tokens(text: str) -> int:
    """Count tokens using DeepSeek tokenizer, or fall back to char estimate."""
    if _tokenizer_fn is not None:
        try:
            return _tokenizer_fn(text)
        except Exception:
            pass
    # Fallback: rough estimate — CJK chars ~1.5 tokens, ASCII ~0.25 tokens
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿" or "　" <= ch <= "〿")
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - cjk - ascii_chars
    return int(cjk * 1.5 + ascii_chars * 0.3 + other * 0.8) or 1


def tokenizer_status() -> str:
    """Return a human-readable status string for the tokenizer."""
    if _tokenizer_fn is not None:
        return "DeepSeek V3 tokenizer 已加载"
    return f"tokenizer 启动失败，自动使用字符估算 ({_tokenizer_error})"


# Try to load on import
_try_load_tokenizer()


TOKENIZER_STATUS = tokenizer_status()

# ── TOML 读取 ─────────────────────────────────────────────────────────────
try:
    import tomlkit
    HAS_TOMLKIT = True
except ImportError:
    tomlkit = None  # type: ignore
    HAS_TOMLKIT = False

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        if tomllib:
            return tomllib.load(f)
        if HAS_TOMLKIT:
            return tomlkit.parse(f.read().decode("utf-8")).unwrap()
    return {}


def _read_toml_text(path: Path) -> str:
    """Read raw TOML file as text."""
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_toml(path: Path, key_path: list[str], new_value: str) -> bool:
    """Replace a string value in a TOML file at the given [section] / key path.

    Uses tomlkit if available (preserves formatting), otherwise regex-based
    replacement with triple-quoted string detection.
    """
    if not path.exists():
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False

    # ---- tomlkit path (preferred) ----
    if HAS_TOMLKIT:
        try:
            doc = tomlkit.parse(content)
            # Navigate to the parent table
            node: Any = doc
            for seg in key_path[:-1]:
                if isinstance(node, dict) and seg in node:
                    node = node[seg]
                else:
                    return False
            if isinstance(node, dict) and key_path[-1] in node:
                node[key_path[-1]] = new_value
                backup_path = path.with_suffix(path.suffix + ".bak")
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(content)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(tomlkit.dumps(doc))
                return True
        except Exception:
            pass  # fall through to regex

    # ---- Regex fallback ----
    if len(key_path) != 2:
        return False
    section, key = key_path

    # Find the [section] block
    section_re = re.compile(rf"^\[{re.escape(section)}\]", re.MULTILINE)
    sec_m = section_re.search(content)
    if not sec_m:
        return False

    # Find the next section start (or end of file)
    next_sec_m = re.compile(r"^\[", re.MULTILINE).search(content, sec_m.end())
    block_end = next_sec_m.start() if next_sec_m else len(content)
    block = content[sec_m.start():block_end]

    # Find the key within this block and replace its value
    key_re = re.compile(
        rf"(?P<prefix>{re.escape(key)}\s*=\s*)"
        rf"(?:(?P<tq>\"\"\")(?P<tval>.*?)(?P=tq)|"
        rf"(?P<sq>\")(?P<sval>(?:\\.|[^\"])*?)(?P=sq)|"
        rf"(?P<sq2>')(?P<sval2>(?:\\.|[^'])*?)(?P=sq2))",
        re.DOTALL,
    )
    key_m = key_re.search(block)
    if not key_m:
        return False

    # Build replacement value string in TOML format
    if "\n" in new_value or len(new_value) > 80:
        toml_val = f'"""\n{new_value}\n"""'
    else:
        escaped_val = new_value.replace("\\", "\\\\").replace('"', '\\"')
        toml_val = f'"{escaped_val}"'

    new_block = block[:key_m.start()] + f"{key} = {toml_val}" + block[key_m.end():]
    new_content = content[:sec_m.start()] + new_block + content[block_end:]

    backup_path = path.with_suffix(path.suffix + ".bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _toml_escape_value(text: str) -> str:
    """Escape a string for use in a TOML basic string (double-quoted)."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ── Bot schema default reading / writing ─────────────────────────────────

# Map main agent source IDs to the Chat dataclass field names
_SCHEMA_FIELD_MAP = {
    "main_group": "group_prompt_template",
    "main_friend": "friend_prompt_template",
    "main_resume": "group_chat_resume_prompt_template",
}


def read_schema_default(source_id: str) -> str | None:
    """Extract the default value of a prompt field from the Chat dataclass in bot.py."""
    field_name = _SCHEMA_FIELD_MAP.get(source_id)
    if field_name is None:
        return None
    return _extract_dataclass_field_default(BOT_SCHEMA_PATH, "Chat", field_name)


def save_schema_default(source_id: str, new_text: str) -> bool:
    """Replace a prompt field's default value in the Chat dataclass in bot.py."""
    field_name = _SCHEMA_FIELD_MAP.get(source_id)
    if field_name is None:
        return False
    return _write_dataclass_field_default(BOT_SCHEMA_PATH, "Chat", field_name, new_text)


def _find_dataclass_field(
    file_path: Path, class_names: list[str], field_name: str,
) -> tuple[Any, str] | None:
    """Locate a field in one of the given dataclass(es).

    Returns (kw_value_ast_node, source_code) or None.
    Tries each class name in order; first match wins.
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for class_name in class_names:
        cls_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                cls_node = node
                break
        if cls_node is None:
            continue

        for item in cls_node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            if item.target.id != field_name:
                continue
            if not isinstance(item.value, ast.Call):
                continue
            for kw in item.value.keywords:
                if kw.arg == "default" and kw.value is not None:
                    return (kw.value, source)
    return None


def _extract_dataclass_field_default(file_path: Path, class_name: str, field_name: str) -> str | None:
    """Extract the default value string from a dataclass field using AST.

    Searches *class_name* and *Enhanced<class_name>* (if it exists).
    """
    class_names = [class_name, f"Enhanced{class_name}"]
    result = _find_dataclass_field(file_path, class_names, field_name)
    if result is None:
        return None
    kw_value, source = result
    return _eval_ast_expr(kw_value, source)


def _write_dataclass_field_default(
    file_path: Path, class_name: str, field_name: str, new_text: str,
) -> bool:
    """Replace a dataclass field's default value string in the source file.

    Searches *class_name* and *Enhanced<class_name>* (if it exists).
    Uses AST position information to locate the exact byte range of the
    `default` keyword argument value, then replaces it cleanly without
    fragile regex or depth-tracking heuristics.
    """
    class_names = [class_name, f"Enhanced{class_name}"]
    result = _find_dataclass_field(file_path, class_names, field_name)
    if result is None:
        return False
    default_kw_value, content = result

    # Calculate character indices from AST byte offsets
    # AST positions are UTF-8 byte offsets; Python str slicing uses character indices
    lines = content.splitlines(keepends=True)
    encoded = content.encode("utf-8")

    def _byte_to_char(byte_offset: int) -> int:
        return len(encoded[:byte_offset].decode("utf-8"))

    start_offset = _byte_to_char(
        sum(len(l.encode("utf-8")) for l in lines[: default_kw_value.lineno - 1])
        + default_kw_value.col_offset,
    )
    end_offset = _byte_to_char(
        sum(len(l.encode("utf-8")) for l in lines[: default_kw_value.end_lineno - 1])
        + default_kw_value.end_col_offset,
    )

    # Build replacement string
    if "\n" in new_text:
        escaped = new_text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        replacement = f'(\n"""\n{escaped}\n"""\n        )'
    else:
        escaped = new_text.replace("\\", "\\\\").replace('"', '\\"')
        replacement = f'"{escaped}"'

    new_content = content[:start_offset] + replacement + content[end_offset:]

    # Backup + write
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    if not backup_path.exists():
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


# ── Default variable values for preview ──────────────────────────────────

DEFAULT_VALUES_GROUP: dict[str, str] = {
    "current_time": "2026-05-31 12:00:00 (农历四月十五)",
    "group_name": "示例群聊",
    "group_id": "123456789",
    "group_description": "这是一个示例群聊",
    "group_admin": "群主：小明(123456)",
    "group_info": "<群聊档案>\n示例群聊的档案信息\n</群聊档案>\n<近期阶段摘要>\n本周群友讨论了Python和AI相关话题\n</近期阶段摘要>",
    "message_list": (
        "[消息1](09:30) 用户A: 大家早上好\n"
        "[消息2](09:31) 用户B: 早啊，今天天气不错\n"
        "[消息3](09:32) 用户A: 是啊，适合出去玩\n"
        "[消息4](09:35) 用户C: 有人用过最新版的Python 3.13吗？"
    ),
    "member_list": "用户A(123456), 用户B(789012), 用户C(345678)",
    "bot_name": "小助手",
    "bot_account": "999888",
    "other_name": "，也有人叫你Neo、铸币bot",
    "bot_data": "你是一个可爱的机器人，如果你对别人有备注，你会倾向于叫你备注对方的名字",
    "key_word_reaction_list": "",
    "memory_list": "用户A喜欢打游戏\n用户B是学生，最近在学Python",
}

DEFAULT_VALUES_FRIEND: dict[str, str] = {
    "current_time": "2026-05-31 12:00:00 (农历四月十五)",
    "friend_name": "小明",
    "remark": "大学同学",
    "profile": "小明是一个喜欢打游戏的大学生，性格开朗",
    "friend_info": "<对方信息>\nQQ: 123456\n性别: 男\n</对方信息>",
    "message_list": (
        "[消息1](10:00) 小明: 在吗？\n"
        "[消息2](10:01) Bot: 在的，有什么事吗\n"
        "[消息3](10:02) 小明: 帮我查一下Python的文档"
    ),
    "bot_name": "小助手",
    "bot_account": "999888",
    "other_name": "，也有人叫你Neo、铸币bot",
    "bot_data": "你是一个可爱的机器人，如果你对别人有备注，你会倾向于叫你备注对方的名字",
    "key_word_reaction_list": "",
    "memory_list": "小明是你的大学同学，经常找你聊天",
}

DEFAULT_VALUES_RESUME: dict[str, str] = {
    "new_messages": (
        "[消息16](10:05) 用户A: 对了小助手，刚才那个问题查到了吗\n"
        "[消息17](10:06) 用户B: 同问，我也想知道"
    ),
    "new_member_profiles": "[用户D的档案]\n用户D，23岁，UI设计师，刚加入群聊",
    "current_time": "2026-05-31 12:05:00 (农历四月十五)",
}


# ── Sub-agent prompt sources ─────────────────────────────────────────────

@dataclass
class AgentPromptSource:
    """Describes a sub-agent whose prompt we can extract and edit."""

    module_name: str         # e.g. "neobot_app.agents.creator"
    file_path: Path          # e.g. AGENTS_DIR / "creator.py"
    display_name: str        # e.g. "CreatorAgent"
    has_config: bool = False  # whether prompt function takes config
    prompt_func: str = "_build_system_prompt"  # function name to extract from


AGENT_SOURCES: list[AgentPromptSource] = [
    AgentPromptSource(
        "neobot_app.agents.chat_interaction",
        AGENTS_DIR / "chat_interaction.py",
        "ChatInteractionAgent",
    ),
    AgentPromptSource(
        "neobot_app.agents.willingness",
        AGENTS_DIR / "willingness.py",
        "WillingnessControlAgent",
    ),
    AgentPromptSource(
        "neobot_app.agents.creator",
        AGENTS_DIR / "creator.py",
        "CreatorAgent",
        has_config=True,
    ),
    AgentPromptSource(
        "neobot_app.agents.memory",
        AGENTS_DIR / "memory.py",
        "ArchiveMemoryAgent",
        has_config=True,
    ),
    AgentPromptSource(
        "neobot_app.agents.scheduled_task",
        AGENTS_DIR / "scheduled_task.py",
        "ScheduledTaskAgent",
        has_config=True,
    ),
    AgentPromptSource(
        "neobot_app.agents.problem_solver",
        AGENTS_DIR / "problem_solver.py",
        "ProblemSolverAgent",
        has_config=True,
    ),
    AgentPromptSource(
        "neobot_app.agents.cross_chat",
        AGENTS_DIR / "cross_chat.py",
        "CrossChatAgent",
        has_config=True,
    ),
    AgentPromptSource(
        "neobot_app.agents.image_parse",
        AGENTS_DIR / "image_parse.py",
        "ImageParseAgent",
        prompt_func="_call_vision_model",
    ),
]

# Tool package sources
@dataclass
class ToolPackageSource:
    """Describes a tool package whose description/tools we can view and edit."""

    module_name: str
    file_path: Path
    display_name: str
    builder_func: str  # name of the builder function


TOOL_PACKAGE_SOURCES: list[ToolPackageSource] = [
    ToolPackageSource(
        "neobot_app.toolpackage.web_search_package",
        TOOLPACKAGE_DIR / "web_search_package.py",
        "联网搜索 (web_search)",
        "build_web_search_package",
    ),
]


# ── Prompt extraction ────────────────────────────────────────────────────

def _extract_func_source(file_path: Path, func_name: str) -> str | None:
    """Extract the source code of a function from a Python file.

    Uses indentation tracking: the function ends when we encounter a
    non-blank line at the same or lesser indentation as the `def` line.
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    def_re = re.compile(rf"^(?P<indent>\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\(")
    start_idx = None
    def_indent = ""
    for i, line in enumerate(lines):
        m = def_re.match(line)
        if m:
            start_idx = i
            def_indent = m.group("indent")
            break

    if start_idx is None:
        return None

    # Collect function lines (all lines with greater indentation than def)
    result_lines = [lines[start_idx]]
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            result_lines.append(line)
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            break
        line_indent = line[: len(line) - len(line.lstrip())]
        if len(line_indent) <= len(def_indent) and stripped:
            break
        result_lines.append(line)

    return "".join(result_lines)


def _extract_return_strings(file_path: Path, func_name: str) -> str | None:
    """Extract the effective return string from a function.

    Parses the function's AST and concatenates string literals / f-string
    literal parts from all return statements.  For f-strings with injected
    config references, replaces them with placeholder markers.
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_prompt_regex_fallback(file_path, func_name)

    # Find the function node
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            func_node = node
            break

    if func_node is None:
        return _extract_prompt_regex_fallback(file_path, func_name)

    parts: list[str] = []

    class ReturnCollector(ast.NodeVisitor):
        def visit_Return(self, node: ast.Return) -> None:
            if node.value is not None:
                parts.append(_eval_ast_expr(node.value, source))

    ReturnCollector().visit(func_node)
    return "".join(parts) if parts else None


def _eval_ast_expr(node: ast.expr, source: str) -> str:
    """Evaluate a Python AST expression to a string where possible.

    For f-strings with injected variables (like config.xxx), substitutes
    the variable name as a readable placeholder.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        result: list[str] = []
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                result.append(val.value)
            elif isinstance(val, ast.FormattedValue):
                # Extract the expression text from source
                expr_text = ast.get_source_segment(source, val.value) or "?"
                result.append(f"{{{expr_text}}}")
            else:
                result.append(ast.get_source_segment(source, val) or "…")
        return "".join(result)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_ast_expr(node.left, source)
        right = _eval_ast_expr(node.right, source)
        return left + right
    if isinstance(node, ast.Name):
        # Module-level constant reference
        return f"{{{node.id}}}"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
        if node.args:
            return _eval_ast_expr(node.args[0], source)
    if isinstance(node, ast.Attribute):
        seg = ast.get_source_segment(source, node)
        return f"{{{seg}}}" if seg else "?"
    # Fallback: try to extract from source
    seg = ast.get_source_segment(source, node)
    return seg if seg else "?"


def _extract_prompt_regex_fallback(file_path: Path, func_name: str) -> str | None:
    """Regex-based fallback to extract prompt from a function's return statements."""
    func_source = _extract_func_source(file_path, func_name)
    if not func_source:
        return None

    # Remove the `def` line and de-indent
    lines = func_source.splitlines()
    body_lines = lines[1:]  # skip def line
    if not body_lines:
        return None

    # Find minimal indent in body
    min_indent = min(
        (len(line) - len(line.lstrip()))
        for line in body_lines
        if line.strip() and not line.strip().startswith("#")
    )

    dedented = []
    for line in body_lines:
        if line.strip():
            if len(line) >= min_indent:
                dedented.append(line[min_indent:])
            else:
                dedented.append(line.lstrip())
        else:
            dedented.append("")

    body_text = "\n".join(dedented)

    # Find all return statements and capture their expressions
    # This is a heuristic — handles the common pattern:
    #   return ("line1" "line2" f"line3{var}")
    parts: list[str] = []
    lines_iter = iter(enumerate(body_text.splitlines()))
    in_return = False
    return_buf: list[str] = []

    for _i, line in lines_iter:
        stripped = line.strip()
        if stripped.startswith("return "):
            if in_return:
                parts.append(_render_return_buf(return_buf))
            in_return = True
            return_buf = [stripped[7:]]  # after "return "
        elif in_return:
            if stripped and not stripped.startswith("#") and not stripped.startswith(("def ", "class ", "if ", "for ", "while ", "try:", "except", "finally:", "with ", "async ")):
                return_buf.append(stripped)
            elif stripped.startswith("#"):
                continue
            else:
                parts.append(_render_return_buf(return_buf))
                in_return = False
                return_buf = []

    if in_return and return_buf:
        parts.append(_render_return_buf(return_buf))

    return "\n".join(parts) if parts else None


def _render_return_buf(buf: list[str]) -> str:
    """Heuristically render collected return expression parts into a string."""
    joined = " ".join(buf)
    # Remove Python-level concatenation: ("a" "b") -> "ab"
    # Keep f-string markers
    result = re.sub(r'"\s*"', "", joined)
    # Remove trailing parentheses
    result = result.strip()
    if result.startswith("(") and result.endswith(")"):
        result = result[1:-1]
    # Unescape basic escapes
    result = result.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
    # Replace f-string braces with readable markers
    return result


def _extract_module_constant(file_path: Path, constant_name: str) -> str | None:
    """Extract the string value of a module-level constant.

    Handles both single-line assignment and parenthesized multi-line forms.
    Returns the concatenated string content (without outer quotes).
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match: CONSTANT_NAME = ( ... )  or  CONSTANT_NAME = "..."
    # Use a regex that finds the assignment start
    start_re = re.compile(
        rf"^{re.escape(constant_name)}\s*=\s*\(", re.MULTILINE
    )
    single_re = re.compile(
        rf"^{re.escape(constant_name)}\s*=\s*[\"']", re.MULTILINE
    )

    m = start_re.search(content)
    if m:
        # Parenthesized form: find matching closing paren
        start_pos = m.end()  # after the opening (
        # Track nested parens
        depth = 1
        pos = start_pos
        while pos < len(content) and depth > 0:
            if content[pos] == "(":
                depth += 1
            elif content[pos] == ")":
                depth -= 1
            pos += 1
        block = content[start_pos:pos - 1]  # exclude closing )
        # Extract string literals from the block
        return _concat_string_literals(block)

    m = single_re.search(content)
    if m:
        # Single-line form: CONSTANT_NAME = "..." or '...'
        start_pos = m.end() - 1  # point to the opening quote
        quote = content[start_pos]
        end_pos = content.index(quote, start_pos + 1)
        while content[end_pos - 1] == "\\":
            end_pos = content.index(quote, end_pos + 1)
        return content[start_pos + 1:end_pos]

    return None


def _concat_string_literals(block: str) -> str:
    """Extract and concatenate string literals from a Python source block.

    Handles "str", 'str', f"str", and implicit concatenation with commas or
    newlines between adjacent string tokens.
    """
    result: list[str] = []
    # Find all string tokens in the block
    # Match triple-quoted strings and single-quoted strings
    token_re = re.compile(
        r"""(?:f)?               # optional f-prefix
            (?:'''[\s\S]*?'''    # triple single-quote
             |\"""[\s\S]*?\"""   # triple double-quote
             |"[^"\\\n]*(?:\\.[^"\\\n]*)*"   # single-line double-quote
             |'[^'\\\n]*(?:\\.[^'\\\n]*)*'   # single-line single-quote
            )""",
        re.VERBOSE,
    )
    for m in token_re.finditer(block):
        token = m.group(0).strip()
        # Strip optional f-prefix
        if token.startswith("f"):
            token = token[1:]
        # Strip quotes
        if token.startswith('"""') or token.startswith("'''"):
            token = token[3:-3]
        elif token.startswith('"') or token.startswith("'"):
            token = token[1:-1]
        # Unescape common escapes
        token = token.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
        result.append(token)
    return "".join(result)


def save_agent_description(
    source: AgentPromptSource,
    edits: dict[str, str],
) -> bool:
    """Save edits to module-level description constants in an agent file.

    `edits` is a dict mapping constant_name -> new_text for each constant
    to update. Only constants present in edits are modified.
    """
    if not source.file_path.exists() or not edits:
        return False
    with open(source.file_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = content
    for constant_name, new_text in edits.items():
        # Escape the text for Python string literal
        escaped = new_text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        lines = escaped.splitlines()

        if len(lines) == 1:
            # Single line: "text"
            if len(lines[0]) <= 80:
                replacement = f'{constant_name} = "{lines[0]}"'
            else:
                replacement = f'{constant_name} = (\n    "{lines[0]}"\n)'
        else:
            # Multi-line: parenthesized form
            replacement = f"{constant_name} = (\n"
            for i, line in enumerate(lines):
                comma = "," if i < len(lines) - 1 else ""
                if line.strip():
                    replacement += f'    "{line}"{comma}\n'
                else:
                    replacement += f'    "\\n"{comma}\n'
            replacement += ")"

        # Find and replace the constant in content
        # Pattern: CONSTANT_NAME = ( ... )  or  CONSTANT_NAME = "..."
        paren_re = re.compile(
            rf"{re.escape(constant_name)}\s*=\s*\([\s\S]*?\)",
            re.MULTILINE,
        )
        single_re = re.compile(
            rf'{re.escape(constant_name)}\s*=\s*"[^"]*"',
            re.MULTILINE,
        )

        m = paren_re.search(new_content)
        if m:
            new_content = new_content[:m.start()] + replacement + new_content[m.end():]
        else:
            m = single_re.search(new_content)
            if m:
                new_content = new_content[:m.start()] + replacement + new_content[m.end():]

    if new_content == content:
        return False  # no changes made

    # Backup
    backup_path = source.file_path.with_suffix(source.file_path.suffix + ".bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(source.file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def get_agent_prompt(source: AgentPromptSource) -> str | None:
    """Get the system prompt from a sub-agent's prompt function."""
    prompt = _extract_return_strings(source.file_path, source.prompt_func)
    if prompt and len(prompt) > 50:
        return prompt
    # For ImageParseAgent, the prompt is in messages dict structure
    if source.prompt_func == "_call_vision_model":
        return _extract_image_parse_prompt(source.file_path)
    # For functions where the prompt is in messages structure (not return),
    # extract all string content from the function body
    return _extract_all_strings(source.file_path, source.prompt_func)


def _extract_image_parse_prompt(file_path: Path) -> str | None:
    """Extract the inline prompt from ImageParseAgent's _call_vision_model."""
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Find the messages content block — the text field in the user message
    # Pattern: "text": ( "..." "..." f"..." )
    func_source = _extract_func_source(file_path, "_call_vision_model")
    if not func_source:
        return None

    # Find all string fragments within the messages structure
    # Look for the "text" key content
    text_re = re.compile(
        r'"text"\s*:\s*\((.*?)\s*\)\s*,?\s*\}',
        re.DOTALL,
    )
    m = text_re.search(func_source)
    if not m:
        return None

    text_block = m.group(1)
    # Extract string content from f-strings, regular strings, and concatenations
    # Replace f-string braces with readable markers
    prompt = ""
    # Match string literals and f-strings
    str_re = re.compile(
        r'(?:f)?["\']((?:\\.|[^"\\\'])*)["\']',  # noqa: W605
    )
    for part in str_re.finditer(text_block):
        prompt += part.group(1)

    # Unescape
    prompt = prompt.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')

    # Find f-string expression placeholders
    expr_re = re.compile(r'\{([^}]+)\}')
    def _mark_expr(m: re.Match) -> str:
        inner = m.group(1)
        if inner.startswith("PEER_AGENT_DESCRIPTIONS"):
            return "{PEER_AGENT_DESCRIPTIONS}"
        return f"{{{inner.strip()}}}"
    prompt = expr_re.sub(_mark_expr, prompt)

    return prompt if prompt else None


def _extract_all_strings(file_path: Path, func_name: str) -> str | None:
    """Extract the longest string literal from a function body (fallback)."""
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            func_node = node
            break
    if func_node is None:
        return None
    parts: list[str] = []
    class StringCollector(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str) and len(node.value) > 20:
                parts.append(node.value)
            self.generic_visit(node)
    StringCollector().visit(func_node)
    return max(parts, key=len) if parts else None


def get_tool_package_info(source: ToolPackageSource) -> dict[str, Any] | None:
    """Extract tool package information from its builder function using AST."""
    if not source.file_path.exists():
        return None
    with open(source.file_path, "r", encoding="utf-8") as f:
        file_source = f.read()

    try:
        tree = ast.parse(file_source)
    except SyntaxError:
        return None

    # Find the builder function
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == source.builder_func:
            func_node = node
            break

    if func_node is None:
        return None

    # Find the return statement that returns ToolPackage(...)
    info: dict[str, Any] = {"id": "", "name": "", "short_description": "", "description": "", "tools": []}

    class ToolPackageVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name not in ("ToolPackage",):
                self.generic_visit(node)
                return

            for kw in node.keywords:
                if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                    info["id"] = str(kw.value.value)
                elif kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    info["name"] = str(kw.value.value)
                elif kw.arg == "short_description":
                    info["short_description"] = _eval_ast_expr(kw.value, file_source)
                elif kw.arg == "description":
                    info["description"] = _eval_ast_expr(kw.value, file_source)
                elif kw.arg == "tools":
                    if isinstance(kw.value, ast.List):
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Call):
                                call_name = ""
                                if isinstance(elt.func, ast.Name):
                                    call_name = elt.func.id
                                elif isinstance(elt.func, ast.Attribute):
                                    call_name = elt.func.attr
                                if call_name:
                                    info["tools"].append(call_name)
            self.generic_visit(node)

    ToolPackageVisitor().visit(func_node)

    # Also find tool names from `tools = [...]` assignment
    if not info["tools"]:
        class ToolsListVisitor(ast.NodeVisitor):
            def visit_Assign(self, node: ast.Assign) -> None:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "tools":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Call):
                                    call_name = ""
                                    if isinstance(elt.func, ast.Name):
                                        call_name = elt.func.id
                                    if call_name:
                                        info["tools"].append(call_name)
                self.generic_visit(node)
        ToolsListVisitor().visit(func_node)

    return info


# ── Tool definition extraction ──────────────────────────────────────────

@dataclass
class ToolInfo:
    """Parsed tool definition ready for display."""
    name: str
    description: str
    parameters: dict  # JSON Schema dict


def extract_tool_definitions(
    file_path: Path, *, is_tool_package: bool = False,
) -> list[ToolInfo]:
    """Parse tool definitions from an agent or tool-package source file.

    For agents: extracts ``_tool_def("name", "desc", {...})`` calls from the
    executor class's ``definitions()`` method.

    For tool packages: extracts name / description / parameters from
    ``_build_*_tool() -> ToolDefinition`` builder functions.
    """
    if not file_path.exists():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    if is_tool_package:
        return _extract_tool_package_defs(tree, source)

    return _extract_agent_tool_defs(tree, source)


def _extract_agent_tool_defs(tree: ast.Module, source: str) -> list[ToolInfo]:
    """Extract tool definitions from an agent file.

    Finds the first class whose name ends with ``ToolExecutor``, then visits
    its ``definitions`` method looking for ``_tool_def(...)`` calls.
    """
    # Find the ToolExecutor class
    executor_cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("ToolExecutor"):
            executor_cls = node
            break
    if executor_cls is None:
        return []

    # Find the definitions method
    defs_method = None
    for item in executor_cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "definitions":
            defs_method = item
            break
    if defs_method is None:
        return []

    # Collect _tool_def(...) calls
    tools: list[ToolInfo] = []

    class ToolDefVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            if func_name != "_tool_def":
                self.generic_visit(node)
                return

            if len(node.args) < 2:
                self.generic_visit(node)
                return

            try:
                name = _eval_ast_literal(node.args[0], source)
                description = _eval_ast_literal(node.args[1], source)
            except (ValueError, TypeError):
                self.generic_visit(node)
                return

            params: dict = {}
            if len(node.args) >= 3:
                try:
                    params = _eval_ast_literal(node.args[2], source)
                except (ValueError, TypeError):
                    params = {}

            if isinstance(name, str) and isinstance(description, str) and isinstance(params, dict):
                tools.append(ToolInfo(name=name, description=description, parameters=params))
            self.generic_visit(node)

    ToolDefVisitor().visit(defs_method)
    return tools


def _extract_tool_package_defs(tree: ast.Module, source: str) -> list[ToolInfo]:
    """Extract tool definitions from a tool-package file.

    Looks for top-level ``_build_*_tool()`` functions that return a
    ``ToolDefinition`` dict, and parses name / description / parameters.
    """
    tools: list[ToolInfo] = []

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not (node.name.startswith("_build_") and node.name.endswith("_tool")):
            continue

        # Find the return statement
        for item in ast.walk(node):
            if isinstance(item, ast.Return) and item.value is not None:
                try:
                    td = _eval_ast_literal(item.value, source)
                except (ValueError, TypeError):
                    continue

                if isinstance(td, dict):
                    func = td.get("function", {})
                    if isinstance(func, dict):
                        name = func.get("name", "")
                        desc = func.get("description", "")
                        params = func.get("parameters", {})
                        if isinstance(name, str) and isinstance(params, dict):
                            tools.append(ToolInfo(
                                name=name,
                                description=desc if isinstance(desc, str) else "",
                                parameters=params,
                            ))
                # Only take the first return from each builder
                break

    return tools


def _eval_ast_literal(node: ast.expr, source: str) -> Any:
    """Evaluate a Python literal AST node to its Python value.

    Uses ``ast.literal_eval`` which safely handles strings, numbers, bools,
    None, lists, dicts, tuples — but not f-strings or variable references.
    Falls back to the string representation for non-literal nodes.
    """
    # Get the source segment for literal_eval
    seg = ast.get_source_segment(source, node)
    if seg is None:
        raise ValueError("cannot get source segment")

    try:
        return ast.literal_eval(seg)
    except (ValueError, SyntaxError):
        pass

    # Handle JoinedStr (f-strings) — extract interpolated value as text
    if isinstance(node, ast.JoinedStr):
        return _eval_ast_expr(node, source)

    # Handle implicit string concatenation inside parens: ("a" "b")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    # Handle parenthesized expression
    if isinstance(node, ast.Constant):
        return node.value

    # Handle Name nodes (constants)
    if isinstance(node, ast.Name):
        # Try to look up simple constants
        return f"{{{node.id}}}"

    raise ValueError(f"unsupported AST node: {type(node).__name__}")


# ── Config reading ───────────────────────────────────────────────────────

def load_config_toml() -> dict[str, Any]:
    """Load the config.toml as a plain dict."""
    return _read_toml(CONFIG_PATH)


def get_config_value(config: dict[str, Any], key_path: str) -> str:
    """Get a value from config dict by dotted path. Returns empty string if missing."""
    keys = key_path.split(".")
    current: Any = config
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
            if current is None:
                return ""
        else:
            return ""
    return str(current) if not isinstance(current, (dict, list)) else ""


def build_real_config_vars(config: dict[str, Any], is_group: bool) -> dict[str, str]:
    """Build a dict of real config values for variable substitution."""
    bot = config.get("bot", {})
    chat = config.get("chat", {})

    bot_name = str(bot.get("nick_name", "Neo Bot"))
    bot_account = str(bot.get("account", 0))
    bot_data = str(bot.get("bot_data", ""))
    alias_list = bot.get("alias_name", []) or []
    valid_aliases = [a.strip() for a in alias_list if a and a.strip()]
    other_name = ("，也有人叫你" + "、".join(valid_aliases)) if valid_aliases else ""

    base = {
        "current_time": DEFAULT_VALUES_GROUP["current_time"],
        "bot_name": bot_name,
        "bot_account": bot_account,
        "bot_data": bot_data,
        "other_name": other_name,
        "key_word_reaction_list": "",
        "memory_list": DEFAULT_VALUES_GROUP["memory_list"],
    }

    if is_group:
        return {
            **base,
            "group_name": DEFAULT_VALUES_GROUP["group_name"],
            "group_id": DEFAULT_VALUES_GROUP["group_id"],
            "group_description": DEFAULT_VALUES_GROUP["group_description"],
            "group_admin": DEFAULT_VALUES_GROUP["group_admin"],
            "group_info": DEFAULT_VALUES_GROUP["group_info"],
            "message_list": DEFAULT_VALUES_GROUP["message_list"],
            "member_list": DEFAULT_VALUES_GROUP["member_list"],
        }
    else:
        return {
            **base,
            "friend_name": DEFAULT_VALUES_FRIEND["friend_name"],
            "remark": DEFAULT_VALUES_FRIEND["remark"],
            "profile": DEFAULT_VALUES_FRIEND["profile"],
            "friend_info": DEFAULT_VALUES_FRIEND["friend_info"],
            "message_list": DEFAULT_VALUES_FRIEND["message_list"],
        }


def substitute_vars(template: str, variables: dict[str, str]) -> str:
    """Substitute {variable} placeholders in template with values from dict.

    Missing keys are left as-is.  Uses str.format_map with a defaultdict
    that returns the original placeholder for missing keys.
    """
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    try:
        return template.format_map(_SafeDict(variables))
    except (ValueError, KeyError):
        # If format fails (e.g., unmatched braces), return as-is
        return template


# ── Save functions ────────────────────────────────────────────────────────

def save_main_agent_prompt(key_path: list[str], new_text: str) -> bool:
    """Save a main agent prompt template back to config.toml."""
    return _write_toml(CONFIG_PATH, key_path, new_text)


def save_agent_prompt(source: AgentPromptSource, new_text: str) -> bool:
    """Save a sub-agent's system prompt by rewriting its prompt function.

    Replaces the body of the prompt function with a simple return statement
    returning the new prompt text as a triple-quoted string.
    """
    if not source.file_path.exists():
        return False
    with open(source.file_path, "r", encoding="utf-8") as f:
        content = f.read()

    func_name = source.prompt_func
    def_re = re.compile(
        rf"^(\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\([^)]*\)\s*(->\s*[^:]+)?\s*:",
        re.MULTILINE,
    )
    m = def_re.search(content)
    if not m:
        return False

    indent = m.group(1)
    func_start = m.start()
    rest_after_def = content[m.end():]
    func_line_end = m.end() + (rest_after_def.index("\n") + 1 if "\n" in rest_after_def else len(rest_after_def))

    # Find end of function by tracking indentation
    rest = content[func_line_end:]
    func_body_end = 0
    for line in rest.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= len(indent):
                break
        func_body_end += len(line)

    # Build replacement
    signature = m.group(0)[m.group(0).index("def "):]  # "def func_name(...):"
    new_body = f'{indent}{signature}\n{indent}    return (\n'
    body_indent = indent + "    "
    escaped = new_text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    lines = escaped.splitlines()
    if len(lines) == 1:
        new_body += f'{body_indent}"""\\\n{body_indent}{lines[0]}\n{body_indent}"""'
    else:
        new_body += f'{body_indent}"""'
        for line in lines:
            new_body += f'\n{body_indent}{line}'
        new_body += f'\n{body_indent}"""'
    new_body += f'\n{indent})\n'

    new_content = content[:func_start] + new_body + content[func_line_end + func_body_end:]

    # Backup
    backup_path = source.file_path.with_suffix(source.file_path.suffix + ".bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(source.file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def save_agent_func_body(source: AgentPromptSource, new_body: str) -> bool:
    """Save a sub-agent's prompt function by replacing its body with raw source.

    Unlike save_agent_prompt (which wraps the text in a triple-quoted string),
    this function replaces the function body directly, preserving f-strings,
    conditional logic, and other Python constructs needed by config-based agents.
    """
    if not source.file_path.exists():
        return False
    with open(source.file_path, "r", encoding="utf-8") as f:
        content = f.read()

    func_name = source.prompt_func
    def_re = re.compile(
        rf"^(\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\([^)]*\)\s*(->\s*[^:]+)?\s*:",
        re.MULTILINE,
    )
    m = def_re.search(content)
    if not m:
        return False

    indent = m.group(1)
    func_start = m.start()
    rest_after_def = content[m.end():]
    func_line_end = m.end() + (rest_after_def.index("\n") + 1 if "\n" in rest_after_def else len(rest_after_def))

    # Find end of function by tracking indentation
    rest = content[func_line_end:]
    func_body_end = 0
    for line in rest.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= len(indent):
                break
        func_body_end += len(line)

    # Build replacement: signature + indented body
    signature = m.group(0)[m.group(0).index("def "):]  # "def func_name(...):"
    indented_body = "\n".join(
        f"{indent}    {line}" if line.strip() else ""
        for line in new_body.splitlines()
    )
    # Ensure body ends with newline
    if not indented_body.endswith("\n"):
        indented_body += "\n"
    replacement = f"{indent}{signature}\n{indented_body}"

    new_content = content[:func_start] + replacement + content[func_line_end + func_body_end:]

    # Backup
    backup_path = source.file_path.with_suffix(source.file_path.suffix + ".bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(source.file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def save_tool_package_description(source: ToolPackageSource, field: str, new_text: str) -> bool:
    """Save a tool package's description/short_description field.

    This is a simplified approach that uses regex to locate and replace the field.
    """
    if not source.file_path.exists():
        return False
    with open(source.file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the field in the builder function
    pattern = re.compile(
        rf'({re.escape(field)}\s*=\s*\()\s*\n?\s*(?:\w+)?["\'](.*?)["\']\s*\)',
        re.DOTALL,
    )

    def _replacer(m: re.Match) -> str:
        prefix = m.group(1)
        escaped = new_text.replace("\\", "\\\\").replace('"', '\\"')
        return f'{prefix}\n        "{escaped}"\n    )'

    new_content, count = pattern.subn(_replacer, content, count=1)
    if count == 0:
        return False

    backup_path = source.file_path.with_suffix(source.file_path.suffix + ".bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(source.file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


# ── Multi-round pipeline simulation ───────────────────────────────────────

# 200-char filler profiles for each character role
FILLER_PROFILE_USER_A = (
    "张三，25岁，软件工程师，在一家互联网公司工作，平时喜欢打游戏和研究新技术。"
    "最近在学Rust语言，对系统编程很感兴趣。性格开朗，喜欢在群里分享技术文章和段子。"
    "家里养了一只橘猫，经常发猫的照片。周末喜欢和朋友们一起爬山或者去网吧开黑。"
    "对美食也有研究，特别是川菜和日料。"
)
FILLER_PROFILE_USER_B = (
    "李四，22岁，大学生，计算机专业大四学生，正在准备毕业设计。"
    "研究的方向是自然语言处理，对AI很感兴趣。平时喜欢看科幻小说和电影。"
    "最近在准备考研，压力比较大，经常在群里吐槽。业余爱好是摄影和弹吉他。"
    "家里是开餐馆的，偶尔会分享一些做菜心得。性格比较内向但熟了之后很健谈。"
)
FILLER_PROFILE_USER_C = (
    "王五，28岁，产品经理，在一家AI创业公司工作，经常需要和技术团队沟通。"
    "对用户体验和产品设计有独到见解，喜欢研究各种App的设计模式。"
    "已婚，有一个两岁的女儿，经常在群里分享育儿经验。爱好是跑步和读书。"
    "最近在读《思考，快与慢》，对行为经济学产生了浓厚兴趣。"
)
FILLER_PROFILE_BOT = (
    "小助手，AI聊天机器人，基于大语言模型构建。擅长搜索信息、绘图、设置提醒、"
    "管理群聊以及各种实用功能。性格温和友好，乐于助人，但也会适时拒绝无理要求。"
    "对技术问题回答比较专业，对日常聊天则偏向简洁随意。"
    "在群聊中会主动关注大家讨论的话题并在合适时机参与回复。"
)


# Dynamic conversation templates for rounds beyond the hardcoded ones
_DYNAMIC_CONVERSATIONS: list[list[str]] = [
    ["用户A: 话说最近有什么新鲜事吗"],
    ["用户B: 我在看一个新的开源项目，挺有意思的"],
    ["用户C: 推荐一下？我也想看看"],
    ["用户A: @小助手 帮我总结一下今天的聊天内容"],
    ["用户B: 对了，有人知道怎么配置Nginx吗"],
    ["用户C: 这个我熟，我发你一篇教程"],
    ["用户A: 谢谢！周末一起吃饭吗"],
    ["用户B: 好主意，去哪吃"],
]


def _build_round_messages(round_idx: int, is_group: bool, total_rounds: int = 5) -> list[str]:
    """Generate new messages for this round of the conversation pipeline."""
    messages_all = [
        # Round 1: opening
        [
            "[消息1](09:30) 用户A: 大家早上好",
            "[消息2](09:31) 用户B: 早啊，今天有什么计划",
        ],
        # Round 2: discussion starts
        [
            "[消息3](09:35) 用户C: 有人关注最近那个新出的AI模型吗",
            "[消息4](09:36) 用户A: 看了，效果很惊艳，特别是多模态能力",
            "[消息5](09:38) 用户B: 我还在等评测，不知道实际用起来怎么样",
        ],
        # Round 3: database/user info appears
        [
            "[消息6](09:42) 用户A: @小助手 帮我查一下Python 3.13的新特性",
            "[消息7](09:43) 用户C: 话说你们觉得Rust和Go哪个更适合后端？",
            "[消息8](09:45) 用户B: 看场景吧，我最近在用Go写毕设",
        ],
        # Round 4: deeper discussion
        [
            "[消息9](09:50) 用户A: 小助手，帮我把上次说的那个链接再发一次",
            "[消息10](09:51) 用户C: 对了，周末有人去爬山吗",
            "[消息11](09:52) 用户B: 我可能去不了，要赶毕设",
            "[消息12](09:53) 用户A: 毕设做的是什么方向的？",
        ],
        # Round 5: wrap-up
        [
            "[消息13](09:58) 用户B: NLP方向的，情感分析相关",
            "[消息14](09:59) 用户C: 听起来不错，需要帮忙可以找我",
            "[消息15](10:00) 用户A: 我先去开会了，回头聊",
        ],
    ]
    if round_idx < len(messages_all):
        return messages_all[round_idx]
    # For rounds beyond the hardcoded set, generate dynamic messages
    extra = round_idx - len(messages_all)  # 0-indexed extra round offset
    # Base message index: 15 from hardcoded rounds + sum of all prior dynamic messages
    msg_idx_base = 16  # after the 15 hardcoded messages
    for e in range(extra):
        tpl = _DYNAMIC_CONVERSATIONS[e % len(_DYNAMIC_CONVERSATIONS)]
        msg_idx_base += len(tpl)
    template = _DYNAMIC_CONVERSATIONS[extra % len(_DYNAMIC_CONVERSATIONS)]
    result: list[str] = []
    for j, tpl in enumerate(template):
        minute = 30 + (round_idx * 3 + j) % 30
        hour = 10 + (round_idx * 3 + j) // 30
        result.append(f"[消息{msg_idx_base + j}]({hour:02d}:{minute:02d}) {tpl}")
    return result


def _build_round_memory(round_idx: int) -> str:
    """Generate memory items that accumulate over rounds."""
    memories = [
        "",
        "",
        "用户A最近在研究Rust\n用户B在做NLP毕设",
        "用户A最近在研究Rust\n用户B在做NLP毕设（情感分析方向）\n用户C在AI创业公司做PM",
        "用户A最近在研究Rust，喜欢爬山\n用户B在做NLP毕设（情感分析方向），周末要赶工\n用户C在AI创业公司做PM，有个两岁女儿\n上周群友讨论过AI模型的话题",
    ]
    if round_idx < len(memories):
        return memories[round_idx]
    base = memories[-1]
    extras = [
        "\n用户A和用户C约好周末一起吃饭",
        "\n用户B对Nginx配置有了新的了解",
        "\n群友讨论了新技术趋势",
        "\n用户C分享了育儿心得",
        "\n用户A分享了最新的技术文章",
    ]
    for i in range(len(memories), round_idx + 1):
        extra = extras[(i - len(memories)) % len(extras)]
        if extra not in base:
            base += extra
    return base


def simulate_multi_round_pipeline(
    template: str, is_group: bool, num_rounds: int = 5,
) -> list[dict[str, Any]]:
    """Generate N rounds of full prompts with evolving conversation state.

    Returns a list of dicts with:
      - round: int
      - prompt: str (fully substituted)
      - total_tokens: int
      - message_list: str
      - memory_list: str
    """
    rounds: list[dict[str, Any]] = []
    all_messages: list[str] = []
    memory_text = ""
    base_time = "2026-05-31 12:00:00 (农历四月十五)"

    BASE_VARS = DEFAULT_VALUES_GROUP if is_group else DEFAULT_VALUES_FRIEND

    for r in range(num_rounds):
        new_msgs = _build_round_messages(r, is_group, num_rounds)
        all_messages.extend(new_msgs)
        new_mem = _build_round_memory(r)
        if new_mem:
            memory_text = new_mem

        if is_group:
            vars_dict = {
                **BASE_VARS,
                "current_time": base_time,
                "message_list": "\n".join(all_messages),
                "member_list": (
                    "用户A(123456) [档案: " + FILLER_PROFILE_USER_A + "]\n"
                    "用户B(789012) [档案: " + FILLER_PROFILE_USER_B + "]\n"
                    "用户C(345678) [档案: " + FILLER_PROFILE_USER_C + "]\n"
                    "小助手(999888) [档案: " + FILLER_PROFILE_BOT + "]"
                ),
                "memory_list": memory_text,
                "key_word_reaction_list": (
                    "<关键词反应>\n"
                    "提及'AI模型'时: 你可以分享最新的AI资讯\n"
                    "</关键词反应>" if r >= 1 else ""
                ),
                "group_info": (
                    "<群聊档案>\n技术交流群，主要讨论编程和AI\n"
                    "</群聊档案>\n<近期阶段摘要>\n"
                    "本周群友讨论了AI模型、编程语言选择、以及周末活动安排\n"
                    "</近期阶段摘要>" if r >= 2
                    else "<群聊档案>\n技术交流群，主要讨论编程和AI\n</群聊档案>"
                ),
            }
        else:
            vars_dict = {
                **BASE_VARS,
                "current_time": base_time,
                "message_list": "\n".join(all_messages),
                "friend_info": (
                    "<对方信息>\nQQ: 123456\n性别: 男\n"
                    "档案: " + FILLER_PROFILE_USER_A + "\n</对方信息>"
                ),
                "memory_list": memory_text,
                "key_word_reaction_list": "",
            }

        prompt = substitute_vars(template, vars_dict)
        rounds.append({
            "round": r + 1,
            "prompt": prompt,
            "total_tokens": count_tokens(prompt),
            "message_list": vars_dict.get("message_list", ""),
            "memory_list": vars_dict.get("memory_list", ""),
        })

    return rounds


# ── Cache hit simulation ───────────────────────────────────────────────────

def _common_prefix_len(a: str, b: str) -> int:
    """Length of common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def simulate_cache_hits(
    round_prompts: list[str],
) -> list[dict[str, Any]]:
    """Simulate DeepSeek cache behavior across multiple rounds.

    Cache rules:
      1. Request-end cache: full prompt saved after each round
      2. Common prefix cache: shared prefix between consecutive rounds saved
      3. Fixed interval cache: every ~FIXED_INTERVAL tokens a prefix is saved

    Returns per-round stats with cache hit breakdown.
    """
    FIXED_INTERVAL = 4096  # tokens
    cache_units: list[tuple[str, int, str]] = []  # (text, tokens, source_label)

    results: list[dict[str, Any]] = []

    for i, prompt in enumerate(round_prompts):
        total_tokens = count_tokens(prompt)

        # Find best (longest) matching cache prefix
        best_match_text = ""
        best_match_tokens = 0
        best_match_source = "miss"
        for cached_text, cached_tokens, source in cache_units:
            if prompt.startswith(cached_text) and cached_tokens > best_match_tokens:
                best_match_tokens = cached_tokens
                best_match_text = cached_text
                best_match_source = source

        uncached_tokens = total_tokens - best_match_tokens
        hit_rate = best_match_tokens / total_tokens if total_tokens > 0 else 0

        # Collect hit details
        hit_sources: dict[str, int] = {}
        for cached_text, cached_tokens, source in cache_units:
            if prompt.startswith(cached_text) and cached_tokens <= best_match_tokens:
                # Only count sources that contribute uniquely
                pass
        # Simplified: just report the best match
        if best_match_source != "miss":
            hit_sources[best_match_source] = best_match_tokens

        results.append({
            "round": i + 1,
            "total_tokens": total_tokens,
            "cached_tokens": best_match_tokens,
            "uncached_tokens": uncached_tokens,
            "hit_rate": hit_rate,
            "hit_source": best_match_source,
            "hit_sources": hit_sources,
        })

        # Save cache units from this round
        # 1) Request-end: the full prompt
        cache_units.append((prompt, total_tokens, f"R{i+1}全量"))

        # 2) Common prefix with previous round
        if i > 0:
            prev_prompt = round_prompts[i - 1]
            common_len = _common_prefix_len(prompt, prev_prompt)
            if common_len > 10:  # minimum meaningful prefix
                common_text = prompt[:common_len]
                common_tokens = count_tokens(common_text)
                cache_units.append((common_text, common_tokens, f"R{i}-R{i+1}公共前缀"))

        # 3) Fixed interval splits for long sequences
        if total_tokens > FIXED_INTERVAL:
            for split_at in range(FIXED_INTERVAL, total_tokens, FIXED_INTERVAL):
                ratio = split_at / total_tokens
                split_pos = int(len(prompt) * ratio)
                # Align to nearest newline
                nl = prompt.rfind("\n", 0, split_pos)
                if nl > split_pos * 0.8:
                    split_pos = nl
                prefix_text = prompt[:split_pos]
                prefix_tokens = count_tokens(prefix_text)
                cache_units.append(
                    (prefix_text, prefix_tokens, f"R{i+1}间隔{split_at}tok")
                )

    return results


def simulate_cache_for_sub_agent(
    system_prompt: str, agent_key: str = "",
) -> dict[str, Any]:
    """Simulate cache behaviour for a sub-agent.

    The system prompt is treated as the fixed prefix (cached from a prior
    call).  A realistic task input is appended to represent the per-call
    variable portion.  Only system-prompt tokens hit the cache.
    """
    # Build a plausibly-sized simulated input based on the agent type
    simulated_input = _build_sub_agent_input(agent_key)

    full_prompt = system_prompt + "\n\n" + simulated_input
    total_tokens = count_tokens(full_prompt)
    system_tokens = count_tokens(system_prompt)
    input_tokens = total_tokens - system_tokens

    return {
        "prompt": full_prompt,
        "total_tokens": total_tokens,
        "system_tokens": system_tokens,
        "input_tokens": input_tokens,
        "cached_tokens": system_tokens,
        "uncached_tokens": input_tokens,
        "hit_rate": system_tokens / total_tokens if total_tokens > 0 else 0,
        "hit_source": "系统提示词前缀命中（子Agent每次调用的系统提示词相同）",
    }


def _build_sub_agent_input(agent_key: str) -> str:
    """Generate a realistic simulated input for a sub-agent."""
    inputs: dict[str, str] = {
        "chat_interaction": (
            "<聊天记录>\n"
            "[消息1](10:00) 用户A: @小助手 帮我查一下天气\n"
            "[消息2](10:01) 用户B: 今天好像要下雨\n"
            "</聊天记录>\n"
            "<当前任务>判断是否需要回复消息，并生成合适的回复内容</当前任务>"
        ),
        "willingness": (
            "<聊天记录>\n"
            "[消息1](10:00) 用户A: 有没有人知道怎么配置数据库\n"
            "[消息2](10:02) 用户B: 这个网上搜一下就有了\n"
            "</聊天记录>\n"
            "<当前任务>评估Bot参与此对话的意愿程度</当前任务>"
        ),
        "creator": (
            "<任务描述>\n"
            "用户A要求生成一张'夕阳下的海边'的图片，风格为写实油画\n"
            "</任务描述>\n"
            "<附加信息>分辨率: 1024x768, 风格参考: 莫奈</附加信息>"
        ),
        "memory": (
            "<聊天记录>\n"
            "[消息1](10:00) 用户A: 我最近在学Rust，感觉比C++友好多了\n"
            "[消息2](10:01) 用户B: 确实，Rust的编译器提示很友好\n"
            "</聊天记录>\n"
            "<当前任务>提取并归档有价值的用户信息到记忆库</当前任务>"
        ),
        "scheduled_task": (
            "<当前时间>2026-05-31 12:00:00</当前时间>\n"
            "<待处理定时任务>\n"
            "  - 每天09:00 发送早安消息 (群聊123456)\n"
            "  - 每天18:00 提醒用户A背单词\n"
            "</待处理定时任务>\n"
            "<当前任务>检查是否有需要触发的定时任务</当前任务>"
        ),
        "problem_solver": (
            "<任务描述>\n"
            "用户B问：如何在Python中实现一个线程安全的LRU缓存？\n"
            "需要给出带代码示例的详细解答。\n"
            "</任务描述>"
        ),
        "cross_chat": (
            "<源群聊记录>\n"
            "[消息1] 用户A: 隔壁群在讨论什么新技术\n"
            "[消息2] 用户B: 好像是在说WebAssembly\n"
            "</源群聊记录>\n"
            "<当前任务>判断是否需要跨群传递此话题信息</当前任务>"
        ),
        "image_parse": (
            "<图片描述请求>\n"
            "用户A发送了一张图片，要求Bot描述图片内容\n"
            "图片URL: https://example.com/image.png\n"
            "</图片描述请求>"
        ),
    }
    for key, text in inputs.items():
        if key in agent_key:
            return text
    # Generic fallback
    return (
        "<任务描述>\n"
        "处理用户请求：请根据上述信息和上下文完成指定的分析任务。\n"
        "</任务描述>"
    )


# ── GUI Application ──────────────────────────────────────────────────────

class SubAgentPromptEditor:
    """Popup window for editing sub-agent description constants.

    Edits three module-level constants per agent file:
      - EXPOSED_TO_MAIN_AGENT_DESCRIPTION
      - EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION
      - PEER_AGENT_DESCRIPTIONS (if present in source)
    EXPOSED_TO_MAIN_AGENT_NAME is shown read-only.
    """

    _DESCRIPTION = "EXPOSED_TO_MAIN_AGENT_DESCRIPTION"
    _SHORT_DESC = "EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION"
    _PEER_DESC = "PEER_AGENT_DESCRIPTIONS"
    _NAME = "EXPOSED_TO_MAIN_AGENT_NAME"

    def __init__(
        self,
        parent: tk.Widget,
        on_saved_callback: callable | None = None,
    ) -> None:
        self._parent = parent
        self._on_saved_callback = on_saved_callback
        self._current_source: AgentPromptSource | None = None
        self._original_desc: str = ""
        self._original_short: str = ""

        self._build_window()
        self._refresh_agent_list()

    # ── window construction ─────────────────────────────────────────────

    def _build_window(self) -> None:
        self._window = tk.Toplevel(self._parent)
        self._window.title("子Agent 描述编辑器")
        self._window.geometry("1000x750")
        self._window.minsize(700, 500)

        win = self._window
        if isinstance(self._parent, tk.Tk):
            win.transient(self._parent)

        # ── Toolbar ──
        toolbar = ttk.Frame(win)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(toolbar, text="选择 Agent:").pack(side=tk.LEFT, padx=(0, 5))
        self._agent_listbox = tk.Listbox(
            toolbar, height=8, width=22, exportselection=False,
        )
        self._agent_listbox.pack(side=tk.LEFT, padx=(0, 10))
        self._agent_listbox.bind("<<ListboxSelect>>", self._on_agent_selected)

        # Agent info column
        info_frame = ttk.Frame(toolbar)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._agent_info_label = ttk.Label(
            info_frame, text="", foreground="#555", font=("", 9),
        )
        self._agent_info_label.pack(anchor=tk.W)
        self._agent_path_label = ttk.Label(
            info_frame, text="", foreground="gray", font=("", 8),
        )
        self._agent_path_label.pack(anchor=tk.W)
        self._agent_name_label = ttk.Label(
            info_frame, text="", foreground="#0066CC", font=("Consolas", 10, "bold"),
        )
        self._agent_name_label.pack(anchor=tk.W, pady=(4, 0))

        ttk.Button(
            toolbar, text="保存更改 (Ctrl+S)", command=self._save_current,
        ).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(
            toolbar, text="重新加载", command=self._reload_current,
        ).pack(side=tk.RIGHT, padx=(5, 0))

        # ── Main area: three stacked editor sections ──
        main_pane = tk.PanedWindow(
            win, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 1. EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        desc_frame = ttk.LabelFrame(main_pane, text="主Agent 可见描述 (EXPOSED_TO_MAIN_AGENT_DESCRIPTION)")
        desc_frame.columnconfigure(0, weight=1)
        desc_frame.rowconfigure(0, weight=1)
        self._desc_text = tk.Text(
            desc_frame, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=1, undo=True, height=8,
        )
        desc_scroll = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=self._desc_text.yview)
        self._desc_text.configure(yscrollcommand=desc_scroll.set)
        self._desc_text.grid(row=0, column=0, sticky="nsew")
        desc_scroll.grid(row=0, column=1, sticky="ns")
        main_pane.add(desc_frame, stretch="always")

        # 2. EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION
        short_frame = ttk.LabelFrame(main_pane, text="简短描述 (EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION)")
        short_frame.columnconfigure(0, weight=1)
        short_frame.rowconfigure(0, weight=1)
        self._short_text = tk.Text(
            short_frame, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=1, undo=True, height=3,
        )
        short_scroll = ttk.Scrollbar(short_frame, orient=tk.VERTICAL, command=self._short_text.yview)
        self._short_text.configure(yscrollcommand=short_scroll.set)
        self._short_text.grid(row=0, column=0, sticky="nsew")
        short_scroll.grid(row=0, column=1, sticky="ns")
        main_pane.add(short_frame, stretch="always")

        # 3. PEER_AGENT_DESCRIPTIONS (auto-generated, read-only)
        peer_frame = ttk.LabelFrame(main_pane, text="同级 Agent 描述 (PEER_AGENT_DESCRIPTIONS) — 动态生成，只读")
        peer_frame.columnconfigure(0, weight=1)
        peer_frame.rowconfigure(0, weight=1)
        self._peer_text = tk.Text(
            peer_frame, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=1, undo=True, height=6,
            foreground="#555", state=tk.DISABLED,
        )
        peer_scroll = ttk.Scrollbar(peer_frame, orient=tk.VERTICAL, command=self._peer_text.yview)
        self._peer_text.configure(yscrollcommand=peer_scroll.set)
        self._peer_text.grid(row=0, column=0, sticky="nsew")
        peer_scroll.grid(row=0, column=1, sticky="ns")
        self._peer_notice = ttk.Label(
            peer_frame, text="", foreground="#888", font=("", 8),
        )
        self._peer_notice.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 2))
        main_pane.add(peer_frame, stretch="always")

        # Keyboard shortcuts for all text widgets
        for text_widget in (self._desc_text, self._short_text, self._peer_text):
            text_widget.bind("<Control-z>", lambda e: text_widget.edit_undo())
            text_widget.bind("<Control-y>", lambda e: text_widget.edit_redo())
            text_widget.bind("<Control-Z>", lambda e: text_widget.edit_redo())

        # ── Status bar ──
        self._status_label = ttk.Label(
            win, text="", foreground="gray", relief=tk.SUNKEN, anchor=tk.W,
        )
        self._status_label.pack(side=tk.BOTTOM, fill=tk.X)

        win.protocol("WM_DELETE_WINDOW", self._on_close)
        win.bind("<Control-s>", lambda _e: self._save_current())

    # ── agent list ──────────────────────────────────────────────────────

    def _refresh_agent_list(self) -> None:
        self._agent_listbox.delete(0, tk.END)
        for src in AGENT_SOURCES:
            name = _extract_module_constant(src.file_path, self._NAME) or "?"
            self._agent_listbox.insert(tk.END, f"  {name}  —  {src.display_name}")
        if AGENT_SOURCES:
            self._agent_listbox.selection_set(0)
            self._on_agent_selected()

    def _on_agent_selected(self, event: object = None) -> None:
        sel = self._agent_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(AGENT_SOURCES):
            return

        source = AGENT_SOURCES[idx]
        self._current_source = source

        # Load constants
        full_desc = _extract_module_constant(source.file_path, self._DESCRIPTION) or ""
        short_desc = _extract_module_constant(source.file_path, self._SHORT_DESC) or ""
        agent_name = _extract_module_constant(source.file_path, self._NAME) or "?"

        # Populate text editors
        for text_widget, value in [
            (self._desc_text, full_desc),
            (self._short_text, short_desc),
        ]:
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", value)
            text_widget.edit_reset()
            text_widget.config(state=tk.NORMAL)

        # Remember original values for dirty check
        self._original_desc = full_desc
        self._original_short = short_desc

        # PEER_AGENT_DESCRIPTIONS is now dynamically generated
        peer_text = build_peer_descriptions(agent_name)
        self._peer_text.config(state=tk.NORMAL)
        self._peer_text.delete("1.0", tk.END)
        self._peer_text.insert("1.0", peer_text)
        self._peer_text.config(state=tk.DISABLED, foreground="#555")
        self._peer_text.edit_reset()

        own_desc = AGENT_SHORT_DESCRIPTIONS.get(agent_name, "(未注册)")
        self._peer_notice.config(
            text=f"动态生成自 AGENT_SHORT_DESCRIPTIONS（除自身：{own_desc}）。在 assembly/agents.py 中统一维护。"
        )

        # Info
        config_note = "含配置插值" if source.has_config else "静态提示词"
        self._agent_info_label.config(
            text=f"{source.display_name} — {config_note}"
        )
        self._agent_path_label.config(text=str(source.file_path))
        self._agent_name_label.config(text=f"Agent 名称 (只读): {agent_name}")

        self._status_label.config(
            text=f"已加载 {source.display_name} — 2 个可编辑字段（同级描述动态生成）"
        )

    # ── actions ─────────────────────────────────────────────────────────

    def _reload_current(self) -> None:
        if self._current_source is None:
            return
        if self._has_unsaved_changes():
            if not messagebox.askyesno(
                "确认重新加载", "有未保存的更改，确定重新加载？", parent=self._window,
            ):
                return
        self._on_agent_selected()

    def _save_current(self) -> None:
        source = self._current_source
        if source is None:
            return

        edits: dict[str, str] = {}
        edits[self._DESCRIPTION] = self._desc_text.get("1.0", "end-1c").strip()
        edits[self._SHORT_DESC] = self._short_text.get("1.0", "end-1c").strip()

        if not edits[self._DESCRIPTION]:
            messagebox.showwarning("内容为空", "主Agent 可见描述不能为空", parent=self._window)
            return

        success = save_agent_description(source, edits)
        if success:
            self._original_desc = edits[self._DESCRIPTION]
            self._original_short = edits[self._SHORT_DESC]
            for w in (self._desc_text, self._short_text):
                w.edit_modified(False)
            self._status_label.config(text=f"已保存 {source.display_name} — 共 {len(edits)} 个字段")

            cache_key = f"agent_{source.module_name.split('.')[-1]}"
            self._prompt_cache_pop(cache_key)
            if self._on_saved_callback:
                self._on_saved_callback()
        else:
            self._status_label.config(text="保存失败或无更改")

    def _prompt_cache_pop(self, key: str) -> None:
        try:
            parent_app = self._parent
            if hasattr(parent_app, "_prompt_cache"):
                parent_app._prompt_cache.pop(key, None)
        except Exception:
            pass

    def _has_unsaved_changes(self) -> bool:
        current_desc = self._desc_text.get("1.0", "end-1c").strip()
        current_short = self._short_text.get("1.0", "end-1c").strip()
        return current_desc != self._original_desc or current_short != self._original_short

    def _on_close(self) -> None:
        if self._has_unsaved_changes():
            if not messagebox.askyesno(
                "未保存的更改", "有未保存的更改，确定关闭？", parent=self._window,
            ):
                return
        self._window.destroy()


class PromptBuilderApp:
    """Main tkinter application for the Prompt Builder."""

    def __init__(
        self, parent: tk.Widget | None = None,
        on_save_callback: callable | None = None,
        get_chat_streams: callable | None = None,
    ) -> None:
        self._on_save_callback = on_save_callback
        self._get_chat_streams = get_chat_streams
        self._embedded = parent is not None

        if self._embedded:
            self.root = parent
        else:
            self.root = tk.Tk()
            self.root.title("NeoBot Prompt Builder — 提示词编辑器")
            self.root.geometry("1500x900")
            self.root.minsize(1100, 700)

        # State
        self.config: dict[str, Any] = load_config_toml()
        self._current_source_id: str = ""
        self._current_mode: str = "config"  # "config" or "schema" (for main agent)
        self._prompt_cache: dict[str, str] = {}
        self._round_data: list[dict[str, Any]] = []
        self._modified: bool = False

        # Chat stream preview state
        self._stream_list: list[dict[str, Any]] = []
        self._stream_msg_check_vars: list[tk.BooleanVar] = []
        self._stream_round_data: list[dict[str, Any]] = []

        # Build UI
        if not self._embedded:
            self._build_menu()
        self._build_toolbar()
        self._build_panels()
        self._build_statusbar()

        # Load initial data
        self._populate_selector()

        # Bind events
        if not self._embedded:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-s>", lambda _e: self._save_current())

    # ── UI construction ───────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="保存 (Ctrl+S)", command=self._save_current)
        file_menu.add_command(label="重新加载配置", command=self._reload_config)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="刷新预览", command=self._refresh_previews)
        menubar.add_cascade(label="视图", menu=view_menu)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5, 0))

        ttk.Label(toolbar, text="提示词来源:").pack(side=tk.LEFT, padx=(0, 5))

        self._source_var = tk.StringVar()
        self._source_combo = ttk.Combobox(
            toolbar, textvariable=self._source_var, state="readonly", width=45,
        )
        self._source_combo.pack(side=tk.LEFT, padx=(0, 10))
        self._source_combo.bind("<<ComboboxSelected>>", self._on_source_changed)

        self._save_btn = ttk.Button(
            toolbar, text="💾 保存更改", command=self._save_current,
        )
        self._save_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._schema_btn = ttk.Button(
            toolbar, text="📄 编辑Schema默认值", command=self._toggle_schema_mode,
        )
        # Hidden initially; shown only for main agent sources
        self._schema_btn.pack_forget()

        self._refresh_btn = ttk.Button(
            toolbar, text="🔄 刷新预览", command=self._refresh_previews,
        )
        self._refresh_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._sub_agent_btn = ttk.Button(
            toolbar, text="子Agent 描述编辑", command=self._open_sub_agent_editor,
        )
        self._sub_agent_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._sync_label = ttk.Label(toolbar, text="", foreground="gray")
        self._sync_label.pack(side=tk.LEFT, padx=10)

    def _build_panels(self) -> None:
        # Main horizontal paned window: left | right
        self._main_pane = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        self._main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── Left panel: vertical pane (editor + tool info) ──
        left_pane = tk.PanedWindow(
            self._main_pane, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )

        # Editor frame
        editor_frame = ttk.Frame(left_pane)
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self._left_text = tk.Text(
            editor_frame, wrap=tk.WORD, undo=True, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=2,
        )
        left_scroll_y = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL, command=self._left_text.yview)
        self._left_text.configure(yscrollcommand=left_scroll_y.set)
        self._left_text.grid(row=0, column=0, sticky="nsew")
        left_scroll_y.grid(row=0, column=1, sticky="ns")

        self._left_text.bind("<<Modified>>", self._on_text_modified)

        # Tool info panel with draggable split between tree and detail
        tool_frame = ttk.LabelFrame(left_pane, text="可用工具 (Tools)")
        tool_pane = tk.PanedWindow(
            tool_frame, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        tool_pane.pack(fill=tk.BOTH, expand=True)

        # Treeview: compact tool name list
        tree_sub_frame = ttk.Frame(tool_pane)
        tree_sub_frame.columnconfigure(0, weight=1)
        tree_sub_frame.rowconfigure(0, weight=1)
        self._tool_tree = ttk.Treeview(
            tree_sub_frame, columns=("name",), show="headings", height=4,
        )
        self._tool_tree.heading("name", text="工具名称（点击查看详情）")
        self._tool_tree.column("name", width=200)
        self._tool_tree.grid(row=0, column=0, sticky="nsew")
        tool_tree_scroll = ttk.Scrollbar(tree_sub_frame, orient=tk.VERTICAL, command=self._tool_tree.yview)
        self._tool_tree.configure(yscrollcommand=tool_tree_scroll.set)
        tool_tree_scroll.grid(row=0, column=1, sticky="ns")
        self._tool_tree.bind("<<TreeviewSelect>>", self._on_tool_selected)
        tool_pane.add(tree_sub_frame, stretch="always")

        # Detail text for the selected tool
        detail_sub_frame = ttk.Frame(tool_pane)
        detail_sub_frame.columnconfigure(0, weight=1)
        detail_sub_frame.rowconfigure(0, weight=1)
        self._tool_detail_text = tk.Text(
            detail_sub_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED, height=5,
        )
        tool_detail_scroll = ttk.Scrollbar(detail_sub_frame, orient=tk.VERTICAL, command=self._tool_detail_text.yview)
        self._tool_detail_text.configure(yscrollcommand=tool_detail_scroll.set)
        self._tool_detail_text.grid(row=0, column=0, sticky="nsew")
        tool_detail_scroll.grid(row=0, column=1, sticky="ns")
        tool_pane.add(detail_sub_frame, stretch="always")

        left_pane.add(editor_frame, stretch="always")
        left_pane.add(tool_frame, stretch="always")
        self._main_pane.add(left_pane, stretch="always")

        # ── Right panel: previews (notebook with tabs) ──
        right_frame = ttk.Frame(self._main_pane)

        self._right_notebook = ttk.Notebook(right_frame)
        self._right_notebook.pack(fill=tk.BOTH, expand=True)

        # ---- Tab 1: single-round previews ----
        tab_single = ttk.Frame(self._right_notebook)
        single_pane = tk.PanedWindow(
            tab_single, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        single_pane.pack(fill=tk.BOTH, expand=True)

        # Top-right: default preview
        top_right = ttk.LabelFrame(single_pane, text="默认转义预览（Default Variables）")
        top_right.columnconfigure(0, weight=1)
        top_right.rowconfigure(0, weight=1)

        self._default_preview = tk.Text(
            top_right, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED,
        )
        default_scroll_y = ttk.Scrollbar(top_right, orient=tk.VERTICAL, command=self._default_preview.yview)
        self._default_preview.configure(yscrollcommand=default_scroll_y.set)
        self._default_preview.grid(row=0, column=0, sticky="nsew")
        default_scroll_y.grid(row=0, column=1, sticky="ns")

        single_pane.add(top_right, stretch="always")

        # Bottom-right: real config preview
        bottom_right = ttk.LabelFrame(single_pane, text="真实配置预览（Real Config + Default Fallback）")
        bottom_right.columnconfigure(0, weight=1)
        bottom_right.rowconfigure(0, weight=1)

        self._real_preview = tk.Text(
            bottom_right, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED,
        )
        real_scroll_y = ttk.Scrollbar(bottom_right, orient=tk.VERTICAL, command=self._real_preview.yview)
        self._real_preview.configure(yscrollcommand=real_scroll_y.set)
        self._real_preview.grid(row=0, column=0, sticky="nsew")
        real_scroll_y.grid(row=0, column=1, sticky="ns")

        single_pane.add(bottom_right, stretch="always")

        self._right_notebook.add(tab_single, text="单轮预览")

        # ---- Tab 2: multi-round pipeline & cache ----
        tab_multi = ttk.Frame(self._right_notebook)
        tab_multi.columnconfigure(0, weight=1)
        tab_multi.rowconfigure(0, weight=0)
        tab_multi.rowconfigure(1, weight=1)

        # Round-count control bar
        multi_ctrl = ttk.Frame(tab_multi)
        multi_ctrl.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 2))
        ttk.Label(multi_ctrl, text="模拟轮数:").pack(side=tk.LEFT, padx=(0, 5))
        self._round_count_var = tk.IntVar(value=5)
        self._round_count_spin = ttk.Spinbox(
            multi_ctrl, from_=1, to=30, textvariable=self._round_count_var,
            width=5, command=self._on_round_count_changed,
        )
        self._round_count_spin.pack(side=tk.LEFT)
        ttk.Label(multi_ctrl, text="(1-30)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(
            multi_ctrl, text="应用", command=self._on_round_count_changed,
        ).pack(side=tk.LEFT, padx=(10, 0))

        # Use a treeview for the round table + a text widget for details
        multi_pane = tk.PanedWindow(
            tab_multi, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        multi_pane.grid(row=1, column=0, sticky="nsew")

        # Top half: round-by-round summary table (Treeview)
        table_frame = ttk.LabelFrame(multi_pane, text="多轮管线 — 逐轮统计")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("round", "total", "cached", "uncached", "hit_rate", "hit_src")
        self._round_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=6,
        )
        self._round_tree.heading("round", text="轮次")
        self._round_tree.heading("total", text="总Tokens")
        self._round_tree.heading("cached", text="缓存命中")
        self._round_tree.heading("uncached", text="未命中")
        self._round_tree.heading("hit_rate", text="命中率")
        self._round_tree.heading("hit_src", text="命中来源")
        self._round_tree.column("round", width=45, anchor=tk.CENTER)
        self._round_tree.column("total", width=80, anchor=tk.CENTER)
        self._round_tree.column("cached", width=80, anchor=tk.CENTER)
        self._round_tree.column("uncached", width=80, anchor=tk.CENTER)
        self._round_tree.column("hit_rate", width=70, anchor=tk.CENTER)
        self._round_tree.column("hit_src", width=140)
        self._round_tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._round_tree.yview)
        self._round_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky="ns")

        multi_pane.add(table_frame, stretch="always")

        # Bottom half: per-round full prompt preview
        detail_frame = ttk.LabelFrame(multi_pane, text="选中轮次的完整提示词")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)

        self._round_detail = tk.Text(
            detail_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED,
        )
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._round_detail.yview)
        self._round_detail.configure(yscrollcommand=detail_scroll.set)
        self._round_detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")

        multi_pane.add(detail_frame, stretch="always")

        self._right_notebook.add(tab_multi, text="多轮管线 & 缓存")

        # ---- Tab 3: chat stream preview ----
        self._build_chat_stream_tab()

        # Bind tree selection to show detail
        self._round_tree.bind("<<TreeviewSelect>>", self._on_round_selected)

        self._main_pane.add(right_frame, stretch="always")

    def _build_statusbar(self) -> None:
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_var = tk.StringVar(value="就绪")
        statusbar = ttk.Label(
            status_frame, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W,
        )
        statusbar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._tokenizer_label = ttk.Label(
            status_frame,
            text=f"🔢 {TOKENIZER_STATUS}",
            relief=tk.SUNKEN, width=50, anchor=tk.E,
        )
        self._tokenizer_label.pack(side=tk.RIGHT)

    # ── Data loading ──────────────────────────────────────────────────

    def _populate_selector(self) -> None:
        """Build the source selector dropdown with all available prompt sources."""
        entries: list[tuple[str, str]] = []

        # Main agent prompts
        entries.append(("main_group", "【主Agent】群聊提示词模板 (group_prompt_template)"))
        entries.append(("main_friend", "【主Agent】私聊提示词模板 (friend_prompt_template)"))
        entries.append(("main_resume", "【主Agent】管线续接提示词模板 (group_chat_resume_prompt_template)"))

        # Sub-agents
        for src in AGENT_SOURCES:
            eid = f"agent_{src.module_name.split('.')[-1]}"
            entries.append((eid, f"【子Agent】{src.display_name}"))

        # Tool packages
        for src in TOOL_PACKAGE_SOURCES:
            eid = f"tool_{src.display_name.replace(' ', '_')}"
            entries.append((eid, f"【工具包】{src.display_name}"))

        self._source_map: dict[str, Any] = {}
        display_names = []
        for eid, display in entries:
            self._source_map[eid] = display
            display_names.append(display)

        self._source_combo["values"] = display_names
        if display_names:
            self._source_combo.current(0)
            self._load_source_by_display(display_names[0])

    def _load_source_by_display(self, display: str) -> None:
        """Find the source matching the display name and load it."""
        for eid, dname in self._source_map.items():
            if dname == display:
                self._load_source(eid)
                return

    def _load_source(self, source_id: str) -> None:
        """Load a prompt source by ID and display it in the editor."""
        if self._modified:
            if not messagebox.askyesno("未保存的更改", "当前有未保存的更改，是否放弃？", parent=self.root):
                # Revert combo selection
                for eid, dname in self._source_map.items():
                    if dname == self._source_var.get():
                        return
                return

        self._current_source_id = source_id
        self._modified = False
        self._sync_label.config(text="")

        # Show/hide schema toggle button for main agent sources
        _main_sources = ("main_group", "main_friend", "main_resume")
        if source_id in _main_sources:
            self._schema_btn.pack(side=tk.LEFT, padx=(0, 10), before=self._refresh_btn)
        else:
            self._schema_btn.pack_forget()

        # Default to config mode; if currently in schema mode for a different
        # source, reset to config.  Schema mode is only for main agents.
        if source_id not in _main_sources:
            self._current_mode = "config"

        if source_id == "main_group":
            self._update_schema_btn_label()
            is_group = True
            if self._current_mode == "schema":
                prompt = read_schema_default(source_id) or (
                    self.config.get("chat", {}).get("group_prompt_template", "")
                )
            else:
                prompt = self.config.get("chat", {}).get("group_prompt_template", "")
            self._current_vars_default = DEFAULT_VALUES_GROUP
            self._current_vars_real = build_real_config_vars(self.config, is_group=True)
            self._current_save_target = "main_group"
        elif source_id == "main_friend":
            self._update_schema_btn_label()
            is_group = False
            if self._current_mode == "schema":
                prompt = read_schema_default(source_id) or (
                    self.config.get("chat", {}).get("friend_prompt_template", "")
                )
            else:
                prompt = self.config.get("chat", {}).get("friend_prompt_template", "")
            self._current_vars_default = DEFAULT_VALUES_FRIEND
            self._current_vars_real = build_real_config_vars(self.config, is_group=False)
            self._current_save_target = "main_friend"
        elif source_id == "main_resume":
            self._update_schema_btn_label()
            if self._current_mode == "schema":
                prompt = read_schema_default(source_id) or (
                    self.config.get("chat", {}).get("group_chat_resume_prompt_template", "")
                )
            else:
                prompt = self.config.get("chat", {}).get("group_chat_resume_prompt_template", "")
            self._current_vars_default = DEFAULT_VALUES_RESUME
            self._current_vars_real = DEFAULT_VALUES_RESUME  # no per-config vars for resume
            self._current_save_target = "main_resume"
        elif source_id.startswith("agent_"):
            agent_key = source_id[6:]  # remove "agent_" prefix
            src = next((s for s in AGENT_SOURCES if s.module_name.endswith(agent_key)), None)
            if src is None:
                self._set_text("// 未找到该 Agent 源\n")
                return
            prompt = get_agent_prompt(src) or f"// 无法从 {src.file_path.name} 提取提示词\n// 请检查 _build_system_prompt 函数\n"
            self._current_vars_default = {}
            self._current_vars_real = {}
            self._current_save_target = src
        elif source_id.startswith("tool_"):
            tool_key = source_id[5:]
            src = next((s for s in TOOL_PACKAGE_SOURCES if s.display_name.replace(" ", "_") == tool_key), None)
            if src is None:
                self._set_text("// 未找到该工具包\n")
                return
            info = get_tool_package_info(src)
            if info is None:
                prompt = f"// 无法从 {src.file_path.name} 提取工具包信息\n"
            else:
                tools_str = "\n".join(f"  - {t}" for t in info.get("tools", []))
                prompt = (
                    f"ID: {info.get('id', '?')}\n"
                    f"名称: {info.get('name', '?')}\n"
                    f"简短描述: {info.get('short_description', '?')}\n"
                    f"完整描述: {info.get('description', '?')}\n"
                    f"工具列表:\n{tools_str}"
                )
            self._current_vars_default = {}
            self._current_vars_real = {}
            self._current_save_target = src
        else:
            prompt = "// 未知来源\n"
            self._current_vars_default = {}
            self._current_vars_real = {}
            self._current_save_target = None

        self._set_text(prompt)
        self._left_text.edit_modified(False)
        self._prompt_cache[source_id] = prompt
        self._refresh_previews()
        self._refresh_tool_info()

        mode_label = (
            f" [Schema默认值]" if self._current_mode == "schema" and
            source_id in ("main_group", "main_friend")
            else ""
        )
        self._update_status(f"已加载: {self._source_var.get()}{mode_label}")
        self._sync_label.config(text=f"[编辑{'Schema默认' if mode_label else 'Config'}]", foreground="gray")

    def _set_text(self, text: str) -> None:
        """Set the left editor text."""
        self._left_text.delete("1.0", tk.END)
        self._left_text.insert("1.0", text)

    def _get_text(self) -> str:
        """Get the left editor text."""
        return self._left_text.get("1.0", "end-1c")

    # ── Events ────────────────────────────────────────────────────────

    def _on_source_changed(self, _event: object) -> None:
        display = self._source_var.get()
        self._load_source_by_display(display)

    def _toggle_schema_mode(self) -> None:
        """Toggle between editing the config.toml template and the bot.py schema default."""
        if self._modified:
            if not messagebox.askyesno("未保存的更改", "有未保存的更改，切换模式会丢失更改，是否继续？", parent=self.root):
                return
        self._current_mode = "schema" if self._current_mode == "config" else "config"
        self._modified = False
        self._load_source(self._current_source_id)

    def _update_schema_btn_label(self) -> None:
        """Update the schema toggle button text based on current mode."""
        if self._current_mode == "schema":
            self._schema_btn.config(text="📋 切换到Config模板")
        else:
            self._schema_btn.config(text="📄 编辑Schema默认值")

    def _on_text_modified(self, _event: object) -> None:
        if self._left_text.edit_modified():
            self._modified = True
            self._sync_label.config(text="[已修改 - 按 Ctrl+S 保存]", foreground="orange")
            self._left_text.edit_modified(False)

    def _refresh_tool_info(self) -> None:
        """Refresh the tool info panel with definitions for the current source."""
        source_id = self._current_source_id

        tool_infos: list[ToolInfo] = []

        if source_id in ("main_group", "main_friend", "main_resume"):
            reply_tools_path = APP_SRC / "neobot_app" / "reply" / "tools.py"
            tool_infos = extract_tool_definitions(reply_tools_path, is_tool_package=False)

        elif source_id.startswith("agent_"):
            agent_key = source_id[6:]
            src = next((s for s in AGENT_SOURCES if s.module_name.endswith(agent_key)), None)
            if src is not None:
                tool_infos = extract_tool_definitions(src.file_path, is_tool_package=False)

        elif source_id.startswith("tool_"):
            tool_key = source_id[5:]
            src = next((s for s in TOOL_PACKAGE_SOURCES if s.display_name.replace(" ", "_") == tool_key), None)
            if src is not None:
                tool_infos = extract_tool_definitions(src.file_path, is_tool_package=True)

        # Store for lookup on selection
        self._tool_infos = tool_infos

        # Clear tree and detail
        for row in self._tool_tree.get_children():
            self._tool_tree.delete(row)
        self._set_preview_text(self._tool_detail_text, "")

        if not tool_infos:
            self._tool_tree.insert("", tk.END, values=("（无可用工具）",))
            return

        for t in tool_infos:
            self._tool_tree.insert("", tk.END, values=(t.name,), tags=("tool",))

        # Select first tool by default
        first = self._tool_tree.get_children()[0]
        self._tool_tree.selection_set(first)

    def _on_tool_selected(self, _event: object) -> None:
        """Show detail for the selected tool in the tool info panel."""
        import json

        selection = self._tool_tree.selection()
        if not selection:
            return
        idx = self._tool_tree.index(selection[0])
        tool_infos = getattr(self, "_tool_infos", [])
        if idx < 0 or idx >= len(tool_infos):
            return
        t = tool_infos[idx]

        params_json = json.dumps(
            {"type": "object", **t.parameters}, ensure_ascii=False, indent=2,
        )
        detail = (
            f"描述: {t.description}\n\n"
            f"参数 (JSON Schema):\n{params_json}"
        )
        self._set_preview_text(self._tool_detail_text, detail)

    def _refresh_previews(self) -> None:
        """Refresh both preview panels + multi-round pipeline."""
        current_text = self._get_text()
        has_vars = bool(self._current_vars_default)

        # Default preview
        self._set_preview_text(
            self._default_preview,
            substitute_vars(current_text, self._current_vars_default) if has_vars else current_text,
        )

        # Real config preview
        self._set_preview_text(
            self._real_preview,
            substitute_vars(current_text, self._current_vars_real) if has_vars else current_text,
        )

        # Multi-round pipeline + cache
        self._refresh_multi_round()

        if has_vars:
            self._update_status("预览已刷新 — 左侧=模板, 右上=默认值, 右下=真实配置")

    def _refresh_multi_round(self) -> None:
        """Refresh the multi-round pipeline and cache hit display."""
        source_id = self._current_source_id
        template = self._get_text()
        is_main = source_id in ("main_group", "main_friend")

        # Clear tree rows
        for row in self._round_tree.get_children():
            self._round_tree.delete(row)
        self._round_data: list[dict[str, Any]] = []

        if not is_main:
            # Sub-agent: system prompt is the fixed prefix; only input varies per call
            cache = simulate_cache_for_sub_agent(template, source_id)
            self._round_tree.insert("", tk.END, values=(
                "单次",
                str(cache["total_tokens"]),
                str(cache["cached_tokens"]),
                str(cache["uncached_tokens"]),
                f"{cache['hit_rate']:.1%}",
                cache["hit_source"],
            ))
            detail_text = (
                f"===== 子Agent缓存模拟 =====\n"
                f"系统提示词 Tokens: {cache['system_tokens']}\n"
                f"模拟输入 Tokens:   {cache['input_tokens']}\n"
                f"总 Tokens:         {cache['total_tokens']}\n"
                f"缓存命中:          {cache['cached_tokens']} ({cache['hit_rate']:.1%})\n"
                f"命中来源:          {cache['hit_source']}\n"
                f"{'=' * 60}\n\n{cache['prompt']}"
            )
            self._round_data = [{
                "round": "单次",
                "prompt": cache["prompt"],
                "total_tokens": cache["total_tokens"],
                "cached_tokens": cache["cached_tokens"],
                "uncached_tokens": cache["uncached_tokens"],
                "hit_rate": cache["hit_rate"],
                "hit_source": cache["hit_source"],
            }]
            # Select the row and update the detail panel
            first = self._round_tree.get_children()[0]
            self._round_tree.selection_set(first)
            self._set_preview_text(self._round_detail, detail_text)
            return

        # Main agent: generate N-round pipeline
        is_group = (source_id == "main_group")
        num_rounds = self._round_count_var.get()
        rounds = simulate_multi_round_pipeline(template, is_group, num_rounds)
        prompts = [r["prompt"] for r in rounds]
        cache_results = simulate_cache_hits(prompts)

        for i, (rd, cr) in enumerate(zip(rounds, cache_results)):
            self._round_data.append({
                "round": rd["round"],
                "prompt": rd["prompt"],
                "total_tokens": rd["total_tokens"],
                "cached_tokens": cr["cached_tokens"],
                "uncached_tokens": cr["uncached_tokens"],
                "hit_rate": cr["hit_rate"],
                "hit_source": cr["hit_source"],
            })
            self._round_tree.insert("", tk.END, values=(
                f"第{rd['round']}轮",
                str(rd["total_tokens"]),
                str(cr["cached_tokens"]),
                str(cr["uncached_tokens"]),
                f"{cr['hit_rate']:.1%}",
                cr["hit_source"],
            ))

        # Select first round
        if self._round_data:
            first = self._round_tree.get_children()[0]
            self._round_tree.selection_set(first)

    def _on_round_count_changed(self) -> None:
        """Handle round count change — re-run the pipeline."""
        try:
            val = self._round_count_var.get()
            if 1 <= val <= 30:
                self._refresh_multi_round()
        except tk.TclError:
            pass

    def _on_round_selected(self, _event: object) -> None:
        """Show the full prompt for the selected round."""
        selection = self._round_tree.selection()
        if not selection:
            return
        idx = self._round_tree.index(selection[0])
        if 0 <= idx < len(self._round_data):
            data = self._round_data[idx]
            text = (
                f"===== 第{data['round']}轮 ====="
                f"  |  Tokens: {data['total_tokens']}"
                f"  |  缓存命中: {data['cached_tokens']}"
                f"  |  命中率: {data['hit_rate']:.1%}"
                f"\n{'=' * 60}\n\n{data['prompt']}"
            )
            self._set_preview_text(self._round_detail, text)

    # ── Chat stream preview tab ────────────────────────────────────────

    def _build_chat_stream_tab(self) -> None:
        """Build Tab 3 in the preview notebook: chat-stream-driven prompt preview."""
        tab = ttk.Frame(self._right_notebook)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=0)
        tab.rowconfigure(1, weight=1)

        # Top control bar
        ctrl = ttk.Frame(tab)
        ctrl.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 2))
        ttk.Label(ctrl, text="聊天流:").pack(side=tk.LEFT, padx=(0, 5))
        self._cs_stream_var = tk.StringVar()
        self._cs_stream_combo = ttk.Combobox(
            ctrl, textvariable=self._cs_stream_var, state="readonly", width=25,
        )
        self._cs_stream_combo.pack(side=tk.LEFT, padx=(0, 10))
        self._cs_stream_combo.bind("<<ComboboxSelected>>", self._on_chat_stream_selected)
        ttk.Button(ctrl, text="刷新列表", command=self._refresh_chat_stream_list).pack(
            side=tk.LEFT, padx=(0, 10))
        ttk.Button(ctrl, text="构建提示词", command=self._build_chat_stream_prompts).pack(
            side=tk.LEFT, padx=(0, 10))
        self._cs_info_label = ttk.Label(ctrl, text="", foreground="gray")
        self._cs_info_label.pack(side=tk.LEFT, padx=5)

        # Main content pane: message list + round stats
        cs_pane = tk.PanedWindow(
            tab, orient=tk.VERTICAL, sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        cs_pane.grid(row=1, column=0, sticky="nsew")

        # Upper: scrollable message list with checkboxes
        msg_frame = ttk.LabelFrame(cs_pane, text="消息列表（勾选 = 回复触发点）")
        msg_frame.columnconfigure(0, weight=1)
        msg_frame.rowconfigure(0, weight=1)

        self._cs_msg_canvas = tk.Canvas(msg_frame, highlightthickness=0)
        cs_msg_scroll = ttk.Scrollbar(msg_frame, orient=tk.VERTICAL, command=self._cs_msg_canvas.yview)
        self._cs_msg_canvas.configure(yscrollcommand=cs_msg_scroll.set)
        self._cs_msg_inner = ttk.Frame(self._cs_msg_canvas)
        self._cs_msg_inner_id = self._cs_msg_canvas.create_window(
            (0, 0), window=self._cs_msg_inner, anchor="nw")
        self._cs_msg_canvas.grid(row=0, column=0, sticky="nsew")
        cs_msg_scroll.grid(row=0, column=1, sticky="ns")
        self._cs_msg_inner.bind("<Configure>", lambda e: self._cs_msg_canvas.configure(
            scrollregion=self._cs_msg_canvas.bbox("all")))
        self._cs_msg_canvas.bind("<Configure>", lambda e: self._cs_msg_canvas.itemconfig(
            self._cs_msg_inner_id, width=e.width))

        cs_pane.add(msg_frame, stretch="always")

        # Lower: round stats table + detail preview
        lower_frame = ttk.Frame(cs_pane)
        lower_pane = tk.PanedWindow(
            lower_frame, orient=tk.HORIZONTAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        lower_pane.pack(fill=tk.BOTH, expand=True)

        # Round table
        table_frame = ttk.LabelFrame(lower_pane, text="逐轮统计")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        cs_columns = ("round", "total", "cached", "uncached", "hit_rate")
        self._cs_round_tree = ttk.Treeview(
            table_frame, columns=cs_columns, show="headings", height=4,
        )
        self._cs_round_tree.heading("round", text="轮次")
        self._cs_round_tree.heading("total", text="Tokens")
        self._cs_round_tree.heading("cached", text="缓存")
        self._cs_round_tree.heading("uncached", text="未命中")
        self._cs_round_tree.heading("hit_rate", text="命中率")
        self._cs_round_tree.column("round", width=50, anchor=tk.CENTER)
        self._cs_round_tree.column("total", width=65, anchor=tk.CENTER)
        self._cs_round_tree.column("cached", width=65, anchor=tk.CENTER)
        self._cs_round_tree.column("uncached", width=65, anchor=tk.CENTER)
        self._cs_round_tree.column("hit_rate", width=65, anchor=tk.CENTER)
        self._cs_round_tree.grid(row=0, column=0, sticky="nsew")
        cs_tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._cs_round_tree.yview)
        self._cs_round_tree.configure(yscrollcommand=cs_tree_scroll.set)
        cs_tree_scroll.grid(row=0, column=1, sticky="ns")
        lower_pane.add(table_frame, stretch="always")

        # Detail preview
        detail_frame = ttk.LabelFrame(lower_pane, text="选中轮次提示词")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self._cs_round_detail = tk.Text(
            detail_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED,
        )
        cs_detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self._cs_round_detail.yview)
        self._cs_round_detail.configure(yscrollcommand=cs_detail_scroll.set)
        self._cs_round_detail.grid(row=0, column=0, sticky="nsew")
        cs_detail_scroll.grid(row=0, column=1, sticky="ns")
        lower_pane.add(detail_frame, stretch="always")

        cs_pane.add(lower_frame, stretch="always")

        self._cs_round_tree.bind("<<TreeviewSelect>>", self._on_cs_round_selected)
        self._right_notebook.add(tab, text="聊天流预览")

    def _refresh_chat_stream_list(self) -> None:
        """Refresh the chat stream selector from the parent callback."""
        if self._get_chat_streams is None:
            self._cs_info_label.config(text="(未连接到工具测试)", foreground="gray")
            return
        try:
            streams = self._get_chat_streams()
        except Exception:
            self._cs_info_label.config(text="(获取聊天流失败)", foreground="red")
            return
        self._stream_list = list(streams.values()) if isinstance(streams, dict) else []
        names = [s.get("name", "?") for s in self._stream_list]
        self._cs_stream_combo["values"] = names
        self._cs_info_label.config(text=f"共 {len(names)} 个聊天流", foreground="gray")

    def _on_chat_stream_selected(self, _event: object) -> None:
        """Display messages for the selected chat stream."""
        name = self._cs_stream_var.get()
        stream = next((s for s in self._stream_list if s.get("name") == name), None)
        if stream is None:
            return
        ct = "群聊" if stream.get("conversation_type") == "group" else "私聊"
        gid = stream.get("group_id") or stream.get("user_id") or "?"
        self._cs_info_label.config(
            text=f"{stream.get('name')} ({ct}, ID={gid}, {len(stream.get('messages', []))} 条)",
            foreground="gray",
        )

        # Clear previous message widgets
        for w in self._cs_msg_inner.winfo_children():
            w.destroy()
        self._stream_msg_check_vars.clear()

        messages = stream.get("messages", [])
        for i, msg in enumerate(messages):
            var = tk.BooleanVar(value=False)
            self._stream_msg_check_vars.append(var)
            row = ttk.Frame(self._cs_msg_inner)
            row.pack(fill=tk.X, padx=2, pady=1)
            cb = ttk.Checkbutton(row, variable=var)
            cb.pack(side=tk.LEFT)
            sender = msg.get("sender_name", msg.get("sender_id", "?"))
            ts = msg.get("timestamp", "")
            content = msg.get("content", "")
            label = ttk.Label(
                row, text=f"[{i+1}] ({ts}) {sender}: {content}",
                anchor=tk.W, wraplength=500,
            )
            label.pack(side=tk.LEFT, padx=(2, 0))

    def _build_chat_stream_prompts(self) -> None:
        """Build multi-round prompts from the chat stream based on reply trigger breakpoints."""
        name = self._cs_stream_var.get()
        stream = next((s for s in self._stream_list if s.get("name") == name), None)
        if stream is None:
            return

        template = self._get_text()
        is_group = stream.get("conversation_type") == "group"
        messages = stream.get("messages", [])

        # Collect checked indices (breakpoints)
        checked_indices: list[int] = []
        for i, var in enumerate(self._stream_msg_check_vars):
            if i < len(messages) and var.get():
                checked_indices.append(i)

        # Determine rounds based on breakpoints
        if not checked_indices:
            rounds = [(0, len(messages))]
        else:
            rounds = []
            prev = 0
            for bp in checked_indices:
                rounds.append((prev, bp + 1))
                prev = bp + 1
            if prev < len(messages):
                rounds.append((prev, len(messages)))

        # Build prompt for each round
        round_prompts: list[str] = []
        round_details: list[dict[str, Any]] = []

        for r_idx, (start, end) in enumerate(rounds):
            round_msgs = messages[start:end]
            msg_lines: list[str] = []
            member_ids: set[str] = set()
            for mi, m in enumerate(round_msgs):
                sid = str(m.get("sender_id", ""))
                sname = m.get("sender_name", sid)
                member_ids.add(f"{sname}({sid})")
                ts = m.get("timestamp", "")
                msg_lines.append(f"[消息{start + mi + 1}]({ts}) {sname}: {m.get('content', '')}")
            message_list = "\n".join(msg_lines)
            member_list = ", ".join(sorted(member_ids))

            base = DEFAULT_VALUES_GROUP if is_group else DEFAULT_VALUES_FRIEND
            vars_dict: dict[str, str] = {**base}
            vars_dict["message_list"] = message_list
            vars_dict["member_list"] = member_list
            if is_group:
                vars_dict["group_id"] = str(stream.get("group_id", ""))
            else:
                vars_dict["friend_name"] = str(stream.get("user_id", ""))

            prompt = substitute_vars(template, vars_dict)
            round_prompts.append(prompt)
            round_details.append({
                "round": r_idx + 1,
                "prompt": prompt,
                "total_tokens": count_tokens(prompt),
                "message_range": f"[{start+1}-{end}]",
                "message_list": message_list,
            })

        # Compute cache hits
        cache_results = simulate_cache_hits(round_prompts) if len(round_prompts) > 1 else [
            {"cached_tokens": 0, "uncached_tokens": count_tokens(round_prompts[0]), "hit_rate": 0.0, "hit_source": "miss"},
        ]

        # Merge results
        self._stream_round_data = []
        for rd, cr in zip(round_details, cache_results):
            self._stream_round_data.append({
                **rd,
                "cached_tokens": cr["cached_tokens"],
                "uncached_tokens": cr["uncached_tokens"],
                "hit_rate": cr["hit_rate"],
                "hit_source": cr.get("hit_source", "miss"),
            })

        # Update round table
        for row in self._cs_round_tree.get_children():
            self._cs_round_tree.delete(row)
        for d in self._stream_round_data:
            self._cs_round_tree.insert("", tk.END, values=(
                f"第{d['round']}轮 {d['message_range']}",
                str(d["total_tokens"]),
                str(d["cached_tokens"]),
                str(d["uncached_tokens"]),
                f"{d['hit_rate']:.1%}",
            ))
        # Select first round
        if self._stream_round_data:
            first = self._cs_round_tree.get_children()[0]
            self._cs_round_tree.selection_set(first)

    def _on_cs_round_selected(self, _event: object) -> None:
        """Show the full prompt for the selected round in the chat stream tab."""
        sel = self._cs_round_tree.selection()
        if not sel:
            return
        idx = self._cs_round_tree.index(sel[0])
        if 0 <= idx < len(self._stream_round_data):
            d = self._stream_round_data[idx]
            text = (
                f"===== 第{d['round']}轮 {d['message_range']} ====="
                f"  |  Tokens: {d['total_tokens']}"
                f"  |  缓存命中: {d['cached_tokens']}"
                f"  |  命中率: {d['hit_rate']:.1%}"
                f"\n{'=' * 60}\n\n{d['prompt']}"
            )
            self._set_preview_text(self._cs_round_detail, text)

    def _set_preview_text(self, widget: tk.Text, text: str) -> None:
        """Set text in a read-only preview widget."""
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    # ── Save ──────────────────────────────────────────────────────────

    def _save_current(self) -> None:
        """Save the current editor content back to the source."""
        if not self._modified:
            self._update_status("没有需要保存的更改")
            return

        new_text = self._get_text()
        target = self._current_save_target
        success = False

        if target == "main_group":
            if self._current_mode == "schema":
                success = save_schema_default("main_group", new_text)
                label = "bot.py → Chat.group_prompt_template (默认值)"
            else:
                success = save_main_agent_prompt(["chat", "group_prompt_template"], new_text)
                label = "config.toml → chat.group_prompt_template"
        elif target == "main_friend":
            if self._current_mode == "schema":
                success = save_schema_default("main_friend", new_text)
                label = "bot.py → Chat.friend_prompt_template (默认值)"
            else:
                success = save_main_agent_prompt(["chat", "friend_prompt_template"], new_text)
                label = "config.toml → chat.friend_prompt_template"
        elif target == "main_resume":
            if self._current_mode == "schema":
                success = save_schema_default("main_resume", new_text)
                label = "bot.py → Chat.group_chat_resume_prompt_template (默认值)"
            else:
                success = save_main_agent_prompt(["chat", "group_chat_resume_prompt_template"], new_text)
                label = "config.toml → chat.group_chat_resume_prompt_template"
        elif isinstance(target, AgentPromptSource):
            success = save_agent_prompt(target, new_text)
            label = f"{target.file_path.name} → _build_system_prompt()"
        elif isinstance(target, ToolPackageSource):
            # For tool packages, we save the description field
            # Determine which field to update based on what was edited
            success = save_tool_package_description(target, "short_description", new_text)
            label = f"{target.file_path.name} → {target.builder_func}()"
        else:
            messagebox.showwarning("未知来源", "无法确定保存目标", parent=self.root)
            return

        if success:
            self._modified = False
            self._sync_label.config(text="[已保存 ✓]", foreground="green")
            self._update_status(f"已保存到: {label}")
            self._prompt_cache[self._current_source_id] = new_text
            # Reload config if main agent was modified
            if target in ("main_group", "main_friend", "main_resume"):
                self.config = load_config_toml()
                self._current_vars_real = build_real_config_vars(
                    self.config, is_group=(target == "main_group")
                ) if target != "main_resume" else DEFAULT_VALUES_RESUME
            # Notify parent of save for cross-tool sync
            if self._on_save_callback:
                self._on_save_callback()
        else:
            messagebox.showerror(
                "保存失败",
                f"无法保存到 {label}。\n请检查文件是否存在且格式正确。",
                parent=self.root,
            )

    def _reload_config(self) -> None:
        """Reload the config.toml file."""
        self.config = load_config_toml()
        # Rebuild real config vars for current source
        if self._current_source_id == "main_group":
            self._current_vars_real = build_real_config_vars(self.config, is_group=True)
        elif self._current_source_id == "main_friend":
            self._current_vars_real = build_real_config_vars(self.config, is_group=False)
        elif self._current_source_id == "main_resume":
            self._current_vars_real = DEFAULT_VALUES_RESUME
        self._refresh_previews()
        self._update_status("配置已重新加载")

    def _update_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _open_sub_agent_editor(self) -> None:
        """Open the sub-agent prompt editor popup window."""
        SubAgentPromptEditor(
            self.root,
            on_saved_callback=self._on_sub_agent_saved,
        )

    def _on_sub_agent_saved(self) -> None:
        """Called when a sub-agent prompt is saved from the editor."""
        # Clear caches
        self._prompt_cache.clear()
        # Refresh if currently viewing a sub-agent
        if self._current_source_id.startswith("agent_"):
            self._load_source(self._current_source_id)
        self._update_status("子Agent 提示词已保存")
        self.root.after(5000, lambda: self._status_var.set("就绪") if self._status_var.get() == msg else None)

    def _on_close(self) -> None:
        if self._modified:
            if messagebox.askyesno("未保存的更改", "有未保存的更改，确定退出？", parent=self.root):
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self) -> None:
        if not self._embedded:
            self.root.mainloop()


# ── Entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    app = PromptBuilderApp()
    app.run()


if __name__ == "__main__":
    main()
