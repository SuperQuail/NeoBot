#!/usr/bin/env python3
"""
NeoBot Tools Editor — 工具调试与手动调用 GUI。

功能：
  - 选择 Agent / 工具包，浏览其工具列表
  - 手动填写工具参数并执行
  - 查看 AI 响应文本 + 完整原始返回（JSON 美化）
  - WebSocket 连接状态指示器（绿色已连接 / 红色未连接）
  - 独立 test_data 目录，不影响真实 data 文件夹
  - AI 绘图 / TTS 虚拟回复调试模式
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
import tkinter as tk
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Any

# ── Prompt Builder integration ────────────────────────────────────────────
from prompt_builder import PromptBuilderApp

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_SRC = PROJECT_ROOT / "app" / "src"
CONFIG_PATH = PROJECT_ROOT / "app" / "data" / "config.toml"
BOT_SCHEMA_PATH = APP_SRC / "neobot_app" / "config" / "schemas" / "bot.py"
AGENTS_DIR = APP_SRC / "neobot_app" / "agents"
TOOLPACKAGE_DIR = APP_SRC / "neobot_app" / "toolpackage"
TEST_DATA_DIR = Path(__file__).resolve().parent / "test_data"

sys.path.insert(0, str(APP_SRC))

# ── TOML parsing ─────────────────────────────────────────────────────────
try:
    import tomllib as _tomllib
except ImportError:
    _tomllib = None  # type: ignore[assignment]

try:
    import tomlkit as _tomlkit
    HAS_TOMLKIT = True
except ImportError:
    _tomlkit = None  # type: ignore[assignment]
    HAS_TOMLKIT = False


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        if _tomllib:
            return _tomllib.load(f)
        if HAS_TOMLKIT:
            return _tomlkit.parse(f.read().decode("utf-8")).unwrap()
    return {}


# ── Tool definition extraction (reused from prompt_builder) ─────────────

@dataclass
class ToolInfo:
    name: str
    description: str
    parameters: dict  # JSON Schema dict
    agent_key: str = ""  # e.g. "creator", "main", "web_search"


@dataclass
class AgentPromptSource:
    module_name: str
    file_path: Path
    display_name: str
    has_config: bool = False
    prompt_func: str = "_build_system_prompt"


AGENT_SOURCES: list[AgentPromptSource] = [
    AgentPromptSource("neobot_app.agents.chat_interaction", AGENTS_DIR / "chat_interaction.py", "ChatInteractionAgent"),
    AgentPromptSource("neobot_app.agents.willingness", AGENTS_DIR / "willingness.py", "WillingnessControlAgent"),
    AgentPromptSource("neobot_app.agents.creator", AGENTS_DIR / "creator.py", "CreatorAgent", has_config=True),
    AgentPromptSource("neobot_app.agents.memory", AGENTS_DIR / "memory.py", "ArchiveMemoryAgent", has_config=True),
    AgentPromptSource("neobot_app.agents.scheduled_task", AGENTS_DIR / "scheduled_task.py", "ScheduledTaskAgent", has_config=True),
    AgentPromptSource("neobot_app.agents.problem_solver", AGENTS_DIR / "problem_solver.py", "ProblemSolverAgent", has_config=True),
]


@dataclass
class ToolPackageSource:
    module_name: str
    file_path: Path
    display_name: str
    builder_func: str


TOOL_PACKAGE_SOURCES: list[ToolPackageSource] = [
    ToolPackageSource(
        "neobot_app.toolpackage.web_search_package",
        TOOLPACKAGE_DIR / "web_search_package.py",
        "联网搜索 (web_search)",
        "build_web_search_package",
    ),
]

# Mapping from tool package display name to internal handler key
TOOL_PACKAGE_HANDLER_KEYS: dict[str, str] = {
    "联网搜索 (web_search)": "web_search",
}


def _eval_ast_literal(node: ast.expr, source: str) -> Any:
    seg = ast.get_source_segment(source, node)
    if seg is None:
        raise ValueError("cannot get source segment")
    try:
        return ast.literal_eval(seg)
    except (ValueError, SyntaxError):
        pass
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                parts.append("{}")
        return "".join(parts)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return f"{{{node.id}}}"
    raise ValueError(f"unsupported AST node: {type(node).__name__}")


def extract_tool_definitions(file_path: Path, *, is_tool_package: bool = False) -> list[ToolInfo]:
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
    executor_cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("ToolExecutor"):
            executor_cls = node
            break
    if executor_cls is None:
        return []
    defs_method = None
    for item in executor_cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "definitions":
            defs_method = item
            break
    if defs_method is None:
        return []

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
    tools: list[ToolInfo] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not (node.name.startswith("_build_") and node.name.endswith("_tool")):
            continue
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
                break
    return tools


def collect_all_tools() -> dict[str, list[ToolInfo]]:
    """Collect tools from all agents, main reply, and tool packages."""
    all_tools: dict[str, list[ToolInfo]] = {}

    # Main reply tools
    reply_path = APP_SRC / "neobot_app" / "reply" / "tools.py"
    reply_tools = extract_tool_definitions(reply_path)
    for t in reply_tools:
        t.agent_key = "main"
    all_tools["main"] = reply_tools

    # Sub-agents
    for src in AGENT_SOURCES:
        agent_tools = extract_tool_definitions(src.file_path)
        agent_key = src.module_name.split(".")[-1]
        for t in agent_tools:
            t.agent_key = agent_key
        all_tools[agent_key] = agent_tools

    # Tool packages
    for src in TOOL_PACKAGE_SOURCES:
        pkg_tools = extract_tool_definitions(src.file_path, is_tool_package=True)
        pkg_key = TOOL_PACKAGE_HANDLER_KEYS.get(src.display_name, src.display_name.replace(" ", "_"))
        for t in pkg_tools:
            t.agent_key = pkg_key
        all_tools[pkg_key] = pkg_tools

    return all_tools


# ── Config loading ───────────────────────────────────────────────────────

def load_config() -> dict[str, Any]:
    return _read_toml(CONFIG_PATH)


def get_model_config(config: dict[str, Any], model_name: str = "primary_chat_model") -> dict[str, Any]:
    """Extract model config for creating a provider."""
    models = config.get("models", {})
    return models.get(model_name, {})


# ── Test data directory setup ────────────────────────────────────────────

def ensure_test_data_dir() -> None:
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (TEST_DATA_DIR / "creator").mkdir(exist_ok=True)
    (TEST_DATA_DIR / "tts").mkdir(exist_ok=True)
    (TEST_DATA_DIR / "tmp").mkdir(exist_ok=True)


# ── Virtual reply system ─────────────────────────────────────────────────

VIRTUAL_REPLY_TEMPLATES_FILE = TEST_DATA_DIR / "virtual_reply_templates.json"

DEFAULT_VIRTUAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "generate_image": {
        "description": "AI 绘图虚拟回复模板",
        "response": '{"ok": true, "image_id": "img_virtual_001", "image_url": "http://localhost:{file_port}/files/creator/virtual_sample.png", "message": "这是一张虚拟生成的图片（调试模式）"}',
        "wait_seconds": 2.0,
    },
    "speak": {
        "description": "TTS 语音合成虚拟回复模板",
        "response": '{"ok": true, "audio_url": "http://localhost:{file_port}/files/tts/virtual_sample.wav", "message": "这是虚拟合成的语音（调试模式）"}',
        "wait_seconds": 1.5,
    },
    "draw": {
        "description": "绘图虚拟回复模板",
        "response": '{"ok": true, "image_id": "img_virtual_002", "image_url": "http://localhost:{file_port}/files/creator/virtual_draw.png", "message": "虚拟绘图完成（调试模式）"}',
        "wait_seconds": 3.0,
    },
}


def load_virtual_templates() -> dict[str, dict[str, Any]]:
    if VIRTUAL_REPLY_TEMPLATES_FILE.exists():
        try:
            with open(VIRTUAL_REPLY_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge with defaults to ensure all keys exist
            merged = dict(DEFAULT_VIRTUAL_TEMPLATES)
            merged.update(loaded)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_VIRTUAL_TEMPLATES)


def save_virtual_templates(templates: dict[str, dict[str, Any]]) -> None:
    ensure_test_data_dir()
    with open(VIRTUAL_REPLY_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


# ── WebSocket client (for QQ connection) ─────────────────────────────────

@dataclass
class WSConnectionState:
    connected: bool = False
    url: str = ""
    error: str = ""


class SimpleWSClient:
    """Minimal WebSocket client to connect to OneBot-compatible QQ framework."""

    def __init__(self) -> None:
        self._state = WSConnectionState()
        self._ws = None
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._on_state_change: list[callable] = []

    @property
    def state(self) -> WSConnectionState:
        return self._state

    def on_state_change(self, callback: callable) -> None:
        self._on_state_change.append(callback)

    def _notify(self) -> None:
        for cb in self._on_state_change:
            try:
                cb(self._state)
            except Exception:
                pass

    def connect(self, host: str, port: int, access_token: str = "") -> None:
        """Initiate async WebSocket connection in the background event loop."""
        if self._loop is None or self._loop.is_closed():
            self._state = WSConnectionState(connected=False, error="事件循环未启动")
            self._notify()
            return

        url = f"ws://{host}:{port}/onebot"
        if access_token:
            url += f"?access_token={access_token}"

        async def _connect() -> None:
            try:
                import websockets
            except ImportError:
                self._state = WSConnectionState(connected=False, url=url, error="websockets 库未安装 (pip install websockets)")
                self._notify()
                return
            try:
                self._ws = await websockets.connect(url, max_size=10 * 1024 * 1024, ping_interval=20, ping_timeout=10)
                self._state = WSConnectionState(connected=True, url=url)
                self._notify()
                # Keep connection alive, receive pongs
                while True:
                    try:
                        await asyncio.wait_for(self._ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        try:
                            await self._ws.ping()
                        except Exception:
                            break
                    except Exception:
                        break
            except Exception as exc:
                self._state = WSConnectionState(connected=False, url=url, error=str(exc))
                self._notify()
            finally:
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                if self._state.connected:
                    self._state = WSConnectionState(connected=False, url=url, error="连接已断开")
                    self._notify()

        self._task = self._loop.create_task(_connect())

    def disconnect(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._state = WSConnectionState(connected=False)
        self._notify()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def send_api(self, action: str, params: dict[str, Any]) -> str:
        """Send a OneBot API call and return the JSON response string."""
        if not self._state.connected or self._ws is None:
            return json.dumps({"ok": False, "error": "WebSocket 未连接"}, ensure_ascii=False)
        import uuid
        echo = str(uuid.uuid4())[:8]
        payload = json.dumps({"action": action, "params": params, "echo": echo}, ensure_ascii=False)
        try:
            await self._ws.send(payload)
            resp = await asyncio.wait_for(self._ws.recv(), timeout=10)
            return resp
        except asyncio.TimeoutError:
            return json.dumps({"ok": False, "error": "API 调用超时 (10s)"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


# ── AI Model Provider ────────────────────────────────────────────────────

def create_model_provider(config: dict[str, Any]) -> Any:
    """Create an AI model provider from config."""
    try:
        from neobot_chat.models import create_provider, get_registered_model
    except ImportError:
        return None

    model_name = config.get("chat", {}).get("primary_model", "primary_chat_model")
    try:
        model = get_registered_model(model_name)
        if model is not None:
            return model.create_provider()
    except Exception:
        pass

    # Fallback: create directly from model config section
    model_cfg = get_model_config(config, model_name)
    if not model_cfg:
        return None

    try:
        provider = create_provider(model_cfg.get("provider", "openai"))
        return provider
    except Exception:
        return None


# ── Chat stream model ────────────────────────────────────────────────────

@dataclass
class ChatStream:
    stream_id: str
    name: str
    conversation_type: str  # "group" or "private"
    group_id: str = ""
    user_id: str = ""
    messages: list[dict] = field(default_factory=list)
    is_real: bool = False  # receiving real QQ messages
    reply_pipeline_active: bool = False


# ── Tool execution environment ───────────────────────────────────────────

@dataclass
class ToolExecResult:
    tool_name: str
    args: dict[str, Any]
    text_response: str
    raw_response: str  # always the original string
    elapsed_ms: float
    is_virtual: bool = False


class ToolExecutionEnv:
    """Lightweight environment for executing tools in isolation."""

    def __init__(self, config: dict[str, Any], ws_client: SimpleWSClient,
                 virtual_mode: bool = True) -> None:
        self.config = config
        self.ws_client = ws_client
        self.virtual_mode = virtual_mode
        self.virtual_templates = load_virtual_templates()

    def _make_virtual_result(self, tool_name: str, args: dict[str, Any]) -> ToolExecResult:
        """Create a virtual reply for image/TTS tools."""
        tmpl = self.virtual_templates.get(tool_name, {})
        wait_s = tmpl.get("wait_seconds", 1.0)
        time.sleep(wait_s)

        response_text = tmpl.get("response", f'{{"ok": true, "message": "虚拟回复: {tool_name}({json.dumps(args, ensure_ascii=False)})"}}')
        # Substitute placeholders
        file_port = self.config.get("file_server", {}).get("port", "8080")
        response_text = response_text.replace("{file_port}", str(file_port))

        return ToolExecResult(
            tool_name=tool_name,
            args=args,
            text_response=response_text,
            raw_response=response_text,
            elapsed_ms=wait_s * 1000,
            is_virtual=True,
        )

    async def execute_tool(self, agent_key: str, tool_name: str,
                           args: dict[str, Any]) -> ToolExecResult:
        """Execute a tool by dispatching to the appropriate handler."""
        t0 = time.perf_counter()

        # Virtual mode for image/TTS tools
        virtual_tools = {"generate_image", "speak", "draw"}
        if self.virtual_mode and tool_name in virtual_tools:
            result = self._make_virtual_result(tool_name, args)
            result.elapsed_ms = (time.perf_counter() - t0) * 1000
            return result

        # Route to handler based on agent_key
        handler = getattr(self, f"_handle_{agent_key}", None)
        if handler is not None:
            try:
                text_resp = await handler(tool_name, args)
            except Exception as exc:
                text_resp = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        else:
            text_resp = json.dumps({"ok": False, "error": f"未知 agent: {agent_key}"}, ensure_ascii=False)

        elapsed = (time.perf_counter() - t0) * 1000
        return ToolExecResult(
            tool_name=tool_name,
            args=args,
            text_response=text_resp,
            raw_response=text_resp,
            elapsed_ms=elapsed,
        )

    # ── Handler: main (ReplyToolExecutor tools) ──

    async def _handle_main(self, tool_name: str, args: dict[str, Any]) -> str:
        ws = self.ws_client

        if tool_name == "send_reply":
            content = args.get("content", "")
            target_id = args.get("target_id", 0)
            conv_type = args.get("conversation_type", "group")
            if conv_type == "group":
                resp = await ws.send_api("send_group_msg", {"group_id": target_id, "message": content})
            else:
                resp = await ws.send_api("send_private_msg", {"user_id": target_id, "message": content})
            return resp

        if tool_name == "speak":
            content = args.get("content", "")
            target_id = args.get("target_id", 0)
            conv_type = args.get("conversation_type", "group")
            # TTS: generate audio then send
            segments = [
                {"type": "record", "data": {"file": f"http://localhost:8080/files/tts/virtual_sample.wav"}},
            ]
            if conv_type == "group":
                resp = await ws.send_api("send_group_msg", {"group_id": target_id, "message": segments})
            else:
                resp = await ws.send_api("send_private_msg", {"user_id": target_id, "message": segments})
            return resp

        if tool_name == "send_emoji":
            emoji_id = args.get("emoji_id", "")
            target_id = args.get("target_id", 0)
            conv_type = args.get("conversation_type", "group")
            segments = [{"type": "image", "data": {"file": emoji_id}}]
            if conv_type == "group":
                resp = await ws.send_api("send_group_msg", {"group_id": target_id, "message": segments})
            else:
                resp = await ws.send_api("send_private_msg", {"user_id": target_id, "message": segments})
            return resp

        if tool_name == "react_emoji":
            emoji_id = args.get("emoji_id", "")
            message_id = args.get("message_id", 0)
            return await ws.send_api("set_msg_emoji_like", {"message_id": message_id, "emoji_id": emoji_id})

        if tool_name == "poke_user":
            user_id = args.get("user_id", 0)
            return await ws.send_api("friend_poke", {"user_id": user_id})

        if tool_name == "wait":
            seconds = float(args.get("seconds", 10))
            await asyncio.sleep(min(seconds, 60))
            return json.dumps({"ok": True, "waited": seconds})

        if tool_name == "cancel":
            return json.dumps({"ok": True, "message": "回复已取消"})

        if tool_name == "adjust_reply_willingness":
            return json.dumps({"ok": True, "message": "回复意愿已调整（调试模式）"})

        if tool_name in ("list_agents", "list_tools"):
            return json.dumps({"ok": True, "agents": [s.display_name for s in AGENT_SOURCES]}, ensure_ascii=False)

        if tool_name == "delegate":
            return json.dumps({"ok": True, "message": "委托任务已提交（调试模式）"})

        if tool_name in ("check_background_tasks", "check_last_drawing"):
            return json.dumps({"ok": True, "tasks": [], "message": "暂无后台任务"})

        # Generic: try as QQ API
        return await ws.send_api(tool_name, args)

    # ── Handler: creator ──

    async def _handle_creator(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "generate_image":
            prompt = args.get("prompt", "")
            return json.dumps({
                "ok": True,
                "image_id": "img_test_001",
                "prompt": prompt,
                "message": f"图片生成请求已提交（调试模式），prompt: {prompt[:100]}...",
                "url": "http://localhost:8080/files/creator/test_sample.png",
            }, ensure_ascii=False)

        if tool_name == "import_image":
            return json.dumps({"ok": True, "message": "图片已导入（调试模式）"})

        return json.dumps({"ok": True, "message": f"creator/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    # ── Handler: memory ──

    async def _handle_memory(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "read_archive":
            table = args.get("table_name", "")
            key = args.get("key", "")
            return json.dumps({"ok": True, "found": False, "message": f"archive({table}/{key}) 在测试环境中无数据"}, ensure_ascii=False)

        if tool_name == "save_archive":
            return json.dumps({"ok": True, "message": "存档已保存（测试数据库）"}, ensure_ascii=False)

        if tool_name == "get_chat_context":
            return json.dumps({"ok": True, "context": "测试聊天上下文（调试模式）"}, ensure_ascii=False)

        return json.dumps({"ok": True, "message": f"memory/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    # ── Handler: scheduled_task ──

    async def _handle_scheduled_task(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "create_task":
            return json.dumps({"ok": True, "task_uuid": "test-task-001", "message": "定时任务已创建（调试模式）"}, ensure_ascii=False)
        if tool_name == "list_tasks":
            return json.dumps({"ok": True, "tasks": []}, ensure_ascii=False)
        if tool_name == "delete_task":
            return json.dumps({"ok": True, "message": "任务已删除（调试模式）"}, ensure_ascii=False)
        return json.dumps({"ok": True, "message": f"scheduled_task/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    # ── Handler: web_search (tool package) ──

    async def _handle_web_search(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "search":
            query = args.get("query", "")
            return json.dumps({
                "ok": True,
                "results": [
                    {"title": f"搜索结果: {query}", "url": "https://example.com/1", "snippet": "这是搜索结果的摘要（调试模式）"},
                ],
            }, ensure_ascii=False)
        if tool_name == "read":
            url = args.get("url", "")
            return json.dumps({"ok": True, "url": url, "content": f"[调试模式] 网页内容: {url}"}, ensure_ascii=False)
        if tool_name == "status":
            return json.dumps({"ok": True, "searches_remaining": 10, "reset_time": "2026-06-01T00:00:00Z"}, ensure_ascii=False)
        return json.dumps({"ok": True, "message": f"web_search/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    # ── Fallback handlers ──

    async def _handle_chat_interaction(self, tool_name: str, args: dict[str, Any]) -> str:
        return json.dumps({"ok": True, "message": f"chat_interaction/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    async def _handle_willingness(self, tool_name: str, args: dict[str, Any]) -> str:
        return json.dumps({"ok": True, "message": f"willingness/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)

    async def _handle_problem_solver(self, tool_name: str, args: dict[str, Any]) -> str:
        return json.dumps({"ok": True, "message": f"problem_solver/{tool_name} 已执行（调试模式）"}, ensure_ascii=False)


# ── Delegate streaming window ─────────────────────────────────────────────

class DelegateStreamWindow:
    """Real-time streaming display for delegate agent execution."""

    def __init__(
        self,
        parent: tk.Tk,
        agent_name: str,
        task: str,
        async_mgr: "AsyncLoopManager",
        agent_registry: Any,
        session_id: str = "",
        previous_response: str = "",
        context: str = "",
    ) -> None:
        self._parent = parent
        self._async_mgr = async_mgr
        self._agent_registry = agent_registry
        self._agent_name = agent_name
        self._task = task
        self._session_id = session_id
        self._previous_response = previous_response
        self._context = context

        self._result_text: str = ""
        self._error_text: str = ""
        self._done = False
        self._chunk_queue: queue.Queue = queue.Queue()
        self._start_time: float = 0.0

        self._build_window()
        self._start_stream()

    def _build_window(self) -> None:
        self._window = tk.Toplevel(self._parent)
        self._window.title(f"Delegate 流式输出: {self._agent_name}")
        self._window.geometry("900x650")
        self._window.transient(self._parent)

        # Info bar
        info_frame = ttk.Frame(self._window)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(info_frame, text=f"Agent:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(info_frame, text=self._agent_name, foreground="#0066CC").pack(side=tk.LEFT, padx=(4, 20))
        ttk.Label(info_frame, text=f"Task:", font=("", 9, "bold")).pack(side=tk.LEFT)
        task_display = self._task[:80] + "..." if len(self._task) > 80 else self._task
        ttk.Label(info_frame, text=task_display, foreground="#333").pack(side=tk.LEFT, padx=(4, 20))

        self._elapsed_label = ttk.Label(info_frame, text="耗时: --", foreground="gray")
        self._elapsed_label.pack(side=tk.RIGHT)

        self._status_label = ttk.Label(info_frame, text="运行中...", foreground="blue")
        self._status_label.pack(side=tk.RIGHT, padx=(0, 10))

        # Main paned area: thinking + output
        main_pane = tk.PanedWindow(
            self._window, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Thinking panel
        thinking_frame = ttk.LabelFrame(main_pane, text="思考过程 (Reasoning)")
        thinking_frame.columnconfigure(0, weight=1)
        thinking_frame.rowconfigure(0, weight=1)
        self._thinking_text = tk.Text(
            thinking_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED,
            background="#FFF8E7",
        )
        thinking_scroll = ttk.Scrollbar(thinking_frame, orient=tk.VERTICAL, command=self._thinking_text.yview)
        self._thinking_text.configure(yscrollcommand=thinking_scroll.set)
        self._thinking_text.grid(row=0, column=0, sticky="nsew")
        thinking_scroll.grid(row=0, column=1, sticky="ns")
        main_pane.add(thinking_frame, stretch="always")

        # Output panel
        output_frame = ttk.LabelFrame(main_pane, text="输出 (Output)")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        self._output_text = tk.Text(
            output_frame, wrap=tk.WORD, font=("Consolas", 10),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED,
        )
        output_scroll = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self._output_text.yview)
        self._output_text.configure(yscrollcommand=output_scroll.set)
        self._output_text.grid(row=0, column=0, sticky="nsew")
        output_scroll.grid(row=0, column=1, sticky="ns")
        main_pane.add(output_frame, stretch="always")

        # Tool calls panel
        tool_frame = ttk.LabelFrame(main_pane, text="工具调用 (Tool Calls)")
        tool_frame.columnconfigure(0, weight=1)
        tool_frame.rowconfigure(0, weight=1)
        self._tool_text = tk.Text(
            tool_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED, height=6,
            foreground="#555",
        )
        tool_scroll = ttk.Scrollbar(tool_frame, orient=tk.VERTICAL, command=self._tool_text.yview)
        self._tool_text.configure(yscrollcommand=tool_scroll.set)
        self._tool_text.grid(row=0, column=0, sticky="nsew")
        tool_scroll.grid(row=0, column=1, sticky="ns")
        main_pane.add(tool_frame, stretch="always")

        # Bottom buttons
        btn_frame = ttk.Frame(self._window)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self._close_btn = ttk.Button(btn_frame, text="关闭", command=self._window.destroy, state=tk.DISABLED)
        self._close_btn.pack(side=tk.RIGHT)

        self._window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_stream(self) -> None:
        self._start_time = time.monotonic()
        asyncio.run_coroutine_threadsafe(self._run_stream(), self._async_mgr.loop)
        self._poll()

    async def _run_stream(self) -> None:
        try:
            agent_obj = self._agent_registry._agents.get(self._agent_name)
            if agent_obj is None:
                self._chunk_queue.put(("error", f"Agent '{self._agent_name}' 未注册"))
                return

            messages: list[dict] = []
            if self._previous_response and self._previous_response.strip():
                messages.append({"role": "assistant", "content": self._previous_response.strip()})
            messages.append({"role": "user", "content": self._task})

            state: dict = {"messages": messages}
            if self._context:
                state["_delegate_context"] = self._context

            async for chunk in agent_obj.stream_invoke(state):
                if chunk.reasoning_delta:
                    self._chunk_queue.put(("reasoning", chunk.reasoning_delta))
                if chunk.delta:
                    self._chunk_queue.put(("delta", chunk.delta))
                if chunk.message:
                    tool_calls = chunk.message.get("tool_calls")
                    if tool_calls:
                        for tc in tool_calls:
                            func_name = tc.get("function", {}).get("name", "?")
                            func_args = tc.get("function", {}).get("arguments", "{}")
                            try:
                                args_parsed = json.loads(func_args)
                                args_display = json.dumps(args_parsed, ensure_ascii=False, indent=2)
                            except (json.JSONDecodeError, ValueError):
                                args_display = str(func_args)
                            self._chunk_queue.put(("tool_call", f"{func_name}\n{args_display}"))
                if chunk.state:
                    messages = chunk.state.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        content = last_msg.get("content", "")
                        self._result_text = content if isinstance(content, str) else str(content)
        except Exception as exc:
            self._chunk_queue.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            self._chunk_queue.put(("done", None))

    def _poll(self) -> None:
        """Poll for new chunks from the async stream and update UI."""
        try:
            while True:
                kind, payload = self._chunk_queue.get_nowait()
                if kind == "done":
                    self._on_stream_done()
                    return
                if kind == "error":
                    self._append_error(payload)
                elif kind == "reasoning":
                    self._append_thinking(payload)
                elif kind == "delta":
                    self._append_output(payload)
                elif kind == "tool_call":
                    self._append_tool_call(payload)
        except queue.Empty:
            pass

        elapsed = time.monotonic() - self._start_time
        self._elapsed_label.config(text=f"耗时: {elapsed:.1f}s")

        if not self._done:
            self._window.after(100, self._poll)

    def _append_thinking(self, text: str) -> None:
        self._thinking_text.config(state=tk.NORMAL)
        self._thinking_text.insert(tk.END, text)
        self._thinking_text.see(tk.END)
        self._thinking_text.config(state=tk.DISABLED)

    def _append_output(self, text: str) -> None:
        self._output_text.config(state=tk.NORMAL)
        self._output_text.insert(tk.END, text)
        self._output_text.see(tk.END)
        self._output_text.config(state=tk.DISABLED)

    def _append_tool_call(self, text: str) -> None:
        self._tool_text.config(state=tk.NORMAL)
        self._tool_text.insert(tk.END, f"── 调用工具 ──\n{text}\n\n")
        self._tool_text.see(tk.END)
        self._tool_text.config(state=tk.DISABLED)

    def _append_error(self, text: str) -> None:
        self._output_text.config(state=tk.NORMAL)
        self._output_text.insert(tk.END, f"\n[错误] {text}\n")
        self._output_text.see(tk.END)
        self._output_text.config(state=tk.DISABLED)

    def _on_stream_done(self) -> None:
        self._done = True
        elapsed = time.monotonic() - self._start_time
        self._elapsed_label.config(text=f"耗时: {elapsed:.1f}s")
        self._status_label.config(text="完成", foreground="green")
        self._close_btn.config(state=tk.NORMAL)

        if not self._result_text and not self._error_text:
            thinking_content = self._thinking_text.get("1.0", "end-1c").strip()
            output_content = self._output_text.get("1.0", "end-1c").strip()
            if thinking_content and not output_content:
                self._result_text = f"[Agent 仅返回思考内容，无最终文本输出]\n\n{thinking_content[:2000]}"

    def _on_close(self) -> None:
        if not self._done:
            if not messagebox.askyesno("确认关闭", "Agent 仍在运行中，确定要关闭此窗口吗？", parent=self._window):
                return
        self._window.destroy()

    @property
    def result(self) -> str:
        return self._result_text

    @property
    def is_done(self) -> bool:
        return self._done


# ── Async event loop (runs in background thread) ─────────────────────────

class AsyncLoopManager:
    """Manages an asyncio event loop in a background thread."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._ready.clear()

        def _run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self._loop = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def run_async(self, coro, timeout: float = 60) -> Any:
        """Run a coroutine in the background loop and return the result."""
        if self._loop is None:
            raise RuntimeError("事件循环未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)


# ── GUI Application ──────────────────────────────────────────────────────

class ToolsEditorApp:
    """Main GUI application."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("NeoBot Tools Editor — 工具调试器")
        self.root.geometry("1400x900")

        # Load config
        self.config: dict[str, Any] = load_config()

        # Async loop
        self._async_mgr = AsyncLoopManager()
        self._async_mgr.start()

        # WebSocket
        self._ws_client = SimpleWSClient()
        self._ws_client.set_loop(self._async_mgr.loop)
        self._ws_client.on_state_change(self._on_ws_state_changed)

        # Execution env
        self._build_exec_env()

        # Chat streams
        self._chat_streams: dict[str, ChatStream] = {}
        self._current_chat_stream_id: str = ""

        # Real willingness service (lazy init)
        self._willing_service: Any = None
        self._willing_init_error: str = ""

        # Collect tools
        self._all_tools = collect_all_tools()
        self._current_tools: list[ToolInfo] = []
        self._current_agent_key: str = "main"

        # Prompt builder (lazy init in tab 3)
        self._prompt_builder_app: Any = None

        # Agent registry for delegate (lazy init)
        self._agent_registry: Any = None
        self._agent_registry_built = False

        # Build UI
        self._build_menu()
        self._build_toolbar()
        self._build_panels()
        self._build_statusbar()

        # Populate
        self._populate_agent_selector()
        self._select_agent("main")
        self._refresh_stream_selectors()

        # Window close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_exec_env(self) -> None:
        self._virtual_mode = tk.BooleanVar(value=True)
        self._long_wait_var = tk.BooleanVar(value=False)
        self._long_wait_seconds_var = tk.StringVar(value="30")
        self._exec_env = ToolExecutionEnv(
            self.config, self._ws_client,
            virtual_mode=self._virtual_mode.get(),
        )

    def _get_agent_registry(self) -> Any:
        """Lazy-build AgentRegistry for delegate tool. Returns None on failure."""
        if self._agent_registry_built:
            return self._agent_registry

        self._agent_registry_built = True
        try:
            import tomlkit as _tk
            from neobot_app.config.loader.converter import dict_to_dataclass
            from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
            from neobot_app.config.loader.manager import Config
            from neobot_contracts.ports.logging import NullLogger as NL
            from neobot_chat.models import get_model_registry
            from neobot_chat import AgentRegistry as AR, create_provider as cp

            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config_dict = _tk.parse(f.read()).unwrap()
            bot_config = dict_to_dataclass(config_dict, BotConfigSchema)

            # Register models so create_provider works
            try:
                Config.register_models(bot_config)
            except SystemExit:
                pass

            registry = AR()
            active_logger = NL()

            def _factory(agent_name: str) -> Any:
                model_index_map = {
                    "creator": 1, "memory": 1, "chat_interaction": 1,
                    "willingness": 1, "scheduled_task": 1,
                    "problem_solver": 1,
                }
                index = model_index_map.get(agent_name, 1)
                model_names = {0: "primary_chat_model", 1: "agent_model_1",
                               2: "agent_model_2", 3: "agent_model_3"}
                model_name = model_names.get(index, "agent_model_1")

                # Check if specific agent model routing exists
                routing = getattr(bot_config, "agent_model", None)
                if routing is not None:
                    routed_index = getattr(routing, agent_name, index)
                    try:
                        routed_index = int(routed_index)
                    except (TypeError, ValueError):
                        routed_index = index
                    model_name = model_names.get(routed_index, model_name)

                # Fallback to primary if agent model not found
                try:
                    return cp(model_name)
                except Exception:
                    try:
                        return cp("primary_chat_model")
                    except Exception:
                        return None

            # Build problem_solver agent
            ps_config = getattr(bot_config.agent, "problem_solver", None)
            if ps_config is not None and getattr(ps_config, "enabled", True):
                try:
                    from neobot_app.agents.problem_solver import (
                        build_problem_solver_agent, ProblemSolverAgentConfig,
                    )
                    provider = _factory("problem_solver")
                    if provider is not None:
                        registry.register(
                            "problem_solver",
                            build_problem_solver_agent(
                                provider,
                                config=ps_config,
                                logger=active_logger,
                            ),
                        )
                        active_logger.info("已注册 problem_solver agent")
                except Exception as exc:
                    active_logger.warning(f"无法注册 problem_solver agent: {exc}")

            # Build willingness agent
            willingness_config = getattr(bot_config.agent, "willingness", None)
            if willingness_config is not None and getattr(willingness_config, "enabled", True):
                try:
                    from neobot_app.agents.willingness import build_willingness_control_agent
                    ws = self._init_willing_service()
                    if ws is not None:
                        provider = _factory("willingness")
                        if provider is not None:
                            registry.register(
                                "willingness",
                                build_willingness_control_agent(
                                    provider,
                                    willing_service=ws,
                                    logger=active_logger,
                                ),
                            )
                            active_logger.info("已注册 willingness agent")
                except Exception as exc:
                    active_logger.warning(f"无法注册 willingness agent: {exc}")

            self._agent_registry = registry
            if len(registry) > 0:
                names = ", ".join(registry.names)
                self._set_status(f"Agent 注册表已构建: {names}")
            else:
                self._set_status("Agent 注册表为空 — 无可用子 Agent")
            return registry
        except Exception as exc:
            self._set_status(f"Agent 注册表构建失败: {exc}")
            self._agent_registry = None
            return None

    # ── Menu ────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="重新加载配置", command=self._reload_config)
        file_menu.add_command(label="编辑虚拟回复模板...", command=self._open_virtual_template_editor)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        debug_menu = tk.Menu(menubar, tearoff=0)
        debug_menu.add_checkbutton(label="虚拟回复模式", variable=self._virtual_mode,
                                   command=self._on_virtual_mode_toggled)
        menubar.add_cascade(label="调试", menu=debug_menu)

    # ── Toolbar ──────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5, 0))

        # Agent selector
        ttk.Label(toolbar, text="Agent / 工具包:").pack(side=tk.LEFT, padx=(0, 5))
        self._agent_var = tk.StringVar()
        self._agent_combo = ttk.Combobox(toolbar, textvariable=self._agent_var, state="readonly", width=35)
        self._agent_combo.pack(side=tk.LEFT, padx=(0, 10))
        self._agent_combo.bind("<<ComboboxSelected>>", self._on_agent_selected)

        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        # WebSocket status
        self._ws_indicator = tk.Canvas(toolbar, width=16, height=16, highlightthickness=0)
        self._ws_indicator.pack(side=tk.LEFT, padx=(0, 5))
        self._ws_indicator_dot = self._ws_indicator.create_oval(2, 2, 14, 14, fill="red", outline="darkgray")

        self._ws_status_label = ttk.Label(toolbar, text="QQ 未连接", foreground="gray")
        self._ws_status_label.pack(side=tk.LEFT, padx=(0, 10))

        # Connect button
        self._ws_connect_btn = ttk.Button(toolbar, text="连接 QQ", command=self._toggle_ws_connection)
        self._ws_connect_btn.pack(side=tk.LEFT)

        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        # Virtual mode indicator
        self._virtual_label = ttk.Label(toolbar, text="", foreground="orange")
        self._virtual_label.pack(side=tk.LEFT, padx=(10, 0))
        self._update_virtual_label()

        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        # Long wait option
        self._long_wait_cb = ttk.Checkbutton(
            toolbar, text="长时等待", variable=self._long_wait_var,
        )
        self._long_wait_cb.pack(side=tk.LEFT, padx=(10, 2))
        self._long_wait_spin = ttk.Spinbox(
            toolbar, textvariable=self._long_wait_seconds_var,
            from_=5, to=600, width=5,
        )
        self._long_wait_spin.pack(side=tk.LEFT)
        ttk.Label(toolbar, text="秒", foreground="gray").pack(side=tk.LEFT)

    # ── Panels ───────────────────────────────────────────────────────────

    def _build_panels(self) -> None:
        # Top-level notebook: tabs for tool simulation & chat simulation
        self._main_notebook = ttk.Notebook(self.root)
        self._main_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── Tab 1: Tool Simulation ──
        tab1 = ttk.Frame(self._main_notebook)
        self._main_pane = tk.PanedWindow(
            tab1, orient=tk.HORIZONTAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        self._main_pane.pack(fill=tk.BOTH, expand=True)

        # ── Left: tool list + param form ──
        left_pane = tk.PanedWindow(
            self._main_pane, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )

        # Tool list
        tool_list_frame = ttk.LabelFrame(left_pane, text="可用工具（点击选择）")
        tool_list_pane = tk.PanedWindow(
            tool_list_frame, orient=tk.VERTICAL,
            sashwidth=8, sashrelief=tk.RAISED, sashpad=2,
        )
        tool_list_pane.pack(fill=tk.BOTH, expand=True)

        tree_sub_frame = ttk.Frame(tool_list_pane)
        tree_sub_frame.columnconfigure(0, weight=1)
        tree_sub_frame.rowconfigure(0, weight=1)
        self._tool_tree = ttk.Treeview(
            tree_sub_frame, columns=("name",), show="headings", height=6,
        )
        self._tool_tree.heading("name", text="工具名称")
        self._tool_tree.column("name", width=180)
        self._tool_tree.grid(row=0, column=0, sticky="nsew")
        tool_scroll = ttk.Scrollbar(tree_sub_frame, orient=tk.VERTICAL, command=self._tool_tree.yview)
        self._tool_tree.configure(yscrollcommand=tool_scroll.set)
        tool_scroll.grid(row=0, column=1, sticky="ns")
        self._tool_tree.bind("<<TreeviewSelect>>", self._on_tool_selected)
        tool_list_pane.add(tree_sub_frame, stretch="always")

        desc_sub_frame = ttk.Frame(tool_list_pane)
        desc_sub_frame.columnconfigure(0, weight=1)
        desc_sub_frame.rowconfigure(0, weight=1)
        self._tool_desc_text = tk.Text(
            desc_sub_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED, height=4,
        )
        desc_scroll = ttk.Scrollbar(desc_sub_frame, orient=tk.VERTICAL, command=self._tool_desc_text.yview)
        self._tool_desc_text.configure(yscrollcommand=desc_scroll.set)
        self._tool_desc_text.grid(row=0, column=0, sticky="nsew")
        desc_scroll.grid(row=0, column=1, sticky="ns")
        tool_list_pane.add(desc_sub_frame, stretch="always")

        left_pane.add(tool_list_frame, stretch="always")

        # Parameter form
        param_frame = ttk.LabelFrame(left_pane, text="工具参数")
        param_frame.columnconfigure(0, weight=1)
        param_frame.rowconfigure(0, weight=1)
        self._param_canvas = tk.Canvas(param_frame, highlightthickness=0)
        param_pane_scroll = ttk.Scrollbar(param_frame, orient=tk.VERTICAL, command=self._param_canvas.yview)
        self._param_canvas.configure(yscrollcommand=param_pane_scroll.set)
        self._param_inner = ttk.Frame(self._param_canvas)
        self._param_inner_id = self._param_canvas.create_window((0, 0), window=self._param_inner, anchor="nw")
        self._param_canvas.grid(row=0, column=0, sticky="nsew")
        param_pane_scroll.grid(row=0, column=1, sticky="ns")
        self._param_inner.bind("<Configure>", lambda e: self._param_canvas.configure(
            scrollregion=self._param_canvas.bbox("all")))
        self._param_canvas.bind("<Configure>", lambda e: self._param_canvas.itemconfig(
            self._param_inner_id, width=e.width))
        self._param_widgets: dict[str, tk.Widget] = {}
        self._param_fields: dict[str, dict] = {}

        btn_frame = ttk.Frame(param_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self._execute_btn = ttk.Button(btn_frame, text="执行工具", command=self._execute_tool)
        self._execute_btn.pack(side=tk.LEFT, padx=(0, 10))
        self._execute_status = ttk.Label(btn_frame, text="", foreground="gray")
        self._execute_status.pack(side=tk.LEFT)

        left_pane.add(param_frame, stretch="always")

        # Chat context: stream selector
        self._chat_ctx_frame = ttk.LabelFrame(left_pane, text="聊天流上下文 (Chat Context)")
        self._chat_ctx_frame.columnconfigure(0, weight=1)
        ctx_sel_frame = ttk.Frame(self._chat_ctx_frame)
        ctx_sel_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(ctx_sel_frame, text="选择聊天流:").pack(side=tk.LEFT, padx=(0, 5))
        self._ctx_stream_var = tk.StringVar()
        self._ctx_stream_combo = ttk.Combobox(ctx_sel_frame, textvariable=self._ctx_stream_var, state="readonly", width=30)
        self._ctx_stream_combo.pack(side=tk.LEFT, padx=(0, 5))
        self._ctx_stream_combo.bind("<<ComboboxSelected>>", self._on_ctx_stream_selected)
        ttk.Button(ctx_sel_frame, text="+ 新建", command=self._create_chat_stream_dialog).pack(side=tk.LEFT)

        self._ctx_info_label = ttk.Label(self._chat_ctx_frame, text="", foreground="gray", font=("", 8))
        self._ctx_info_label.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        left_pane.add(self._chat_ctx_frame, stretch="always")
        self._main_pane.add(left_pane, stretch="always")

        # ── Right: response display ──
        right_frame = ttk.Frame(self._main_pane)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=0)
        right_frame.rowconfigure(1, weight=1)
        info_frame = ttk.Frame(right_frame)
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._result_info_label = ttk.Label(info_frame, text="", foreground="gray")
        self._result_info_label.pack(side=tk.LEFT)
        self._resp_notebook = ttk.Notebook(right_frame)
        self._resp_notebook.grid(row=1, column=0, sticky="nsew")
        text_tab = ttk.Frame(self._resp_notebook)
        text_tab.columnconfigure(0, weight=1)
        text_tab.rowconfigure(0, weight=1)
        self._resp_text = tk.Text(text_tab, wrap=tk.WORD, font=("Consolas", 10),
                                   relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED)
        resp_scroll_y = ttk.Scrollbar(text_tab, orient=tk.VERTICAL, command=self._resp_text.yview)
        self._resp_text.configure(yscrollcommand=resp_scroll_y.set)
        self._resp_text.grid(row=0, column=0, sticky="nsew")
        resp_scroll_y.grid(row=0, column=1, sticky="ns")
        self._resp_notebook.add(text_tab, text="响应文本")
        raw_tab = ttk.Frame(self._resp_notebook)
        raw_tab.columnconfigure(0, weight=1)
        raw_tab.rowconfigure(0, weight=1)
        self._raw_text = tk.Text(raw_tab, wrap=tk.WORD, font=("Consolas", 10),
                                  relief=tk.SUNKEN, borderwidth=2, state=tk.DISABLED)
        raw_scroll_y = ttk.Scrollbar(raw_tab, orient=tk.VERTICAL, command=self._raw_text.yview)
        self._raw_text.configure(yscrollcommand=raw_scroll_y.set)
        self._raw_text.grid(row=0, column=0, sticky="nsew")
        raw_scroll_y.grid(row=0, column=1, sticky="ns")
        self._resp_notebook.add(raw_tab, text="完整返回 (Raw JSON)")
        for color, tag in [("#8B0000", "json_key"), ("#006400", "json_str"),
                           ("#0000CD", "json_num"), ("#8B8B00", "json_bool")]:
            self._raw_text.tag_configure(tag, foreground=color)

        self._main_pane.add(right_frame, stretch="always")
        self._main_notebook.add(tab1, text="模拟工具调用")

        # ── Tab 2: Chat Stream Simulation ──
        self._build_chat_sim_tab()

        # ── Tab 3: Prompt Editor (from prompt_builder.py) ──
        self._build_prompt_editor_tab()

    def _build_chat_sim_tab(self) -> None:
        """Build Tab 2: chat stream simulation."""
        tab2 = ttk.Frame(self._main_notebook)
        tab2.columnconfigure(0, weight=0)
        tab2.columnconfigure(1, weight=1)
        tab2.rowconfigure(0, weight=0)
        tab2.rowconfigure(1, weight=1)

        # ── Top bar ──
        top_bar = ttk.Frame(tab2)
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(5, 2))

        ttk.Button(top_bar, text="+ 新建聊天流", command=self._create_chat_stream_dialog).pack(side=tk.LEFT, padx=(0, 10))

        # Real QQ toggle
        self._sim_real_qq_var = tk.BooleanVar(value=False)
        self._sim_real_qq_cb = ttk.Checkbutton(
            top_bar, text="接受真实 QQ 消息", variable=self._sim_real_qq_var,
            command=self._on_sim_real_qq_toggled, state=tk.DISABLED,
        )
        self._sim_real_qq_cb.pack(side=tk.LEFT, padx=(0, 10))

        # Reply pipeline toggle
        self._sim_pipeline_var = tk.BooleanVar(value=False)
        self._sim_pipeline_cb = ttk.Checkbutton(
            top_bar, text="启动回复管线", variable=self._sim_pipeline_var,
            command=self._on_sim_pipeline_toggled,
        )
        self._sim_pipeline_cb.pack(side=tk.LEFT, padx=(0, 10))

        # Pipeline status indicator
        self._sim_pipeline_indicator = tk.Canvas(top_bar, width=14, height=14, highlightthickness=0)
        self._sim_pipeline_indicator.pack(side=tk.LEFT, padx=(0, 5))
        self._sim_pipeline_dot = self._sim_pipeline_indicator.create_oval(2, 2, 12, 12, fill="red", outline="darkgray")
        self._sim_pipeline_label = ttk.Label(top_bar, text="管线未启动", foreground="gray")
        self._sim_pipeline_label.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(top_bar, text="选择聊天流:").pack(side=tk.LEFT, padx=(0, 5))
        self._sim_stream_var = tk.StringVar()
        self._sim_stream_combo = ttk.Combobox(top_bar, textvariable=self._sim_stream_var, state="readonly", width=30)
        self._sim_stream_combo.pack(side=tk.LEFT, padx=(0, 5))
        self._sim_stream_combo.bind("<<ComboboxSelected>>", self._on_sim_stream_selected)
        ttk.Button(top_bar, text="删除选中流", command=self._delete_chat_stream).pack(side=tk.LEFT)

        # ── Left: stream list ──
        left_frame = ttk.Frame(tab2)
        left_frame.grid(row=1, column=0, sticky="ns", padx=(5, 2), pady=(0, 5))
        left_frame.rowconfigure(0, weight=1)

        self._sim_stream_tree = ttk.Treeview(
            left_frame, columns=("name", "type", "msgs"), show="headings", height=15,
        )
        self._sim_stream_tree.heading("name", text="名称")
        self._sim_stream_tree.heading("type", text="类型")
        self._sim_stream_tree.heading("msgs", text="消息数")
        self._sim_stream_tree.column("name", width=120)
        self._sim_stream_tree.column("type", width=50, anchor=tk.CENTER)
        self._sim_stream_tree.column("msgs", width=50, anchor=tk.CENTER)
        self._sim_stream_tree.grid(row=0, column=0, sticky="nsew")
        sim_tree_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._sim_stream_tree.yview)
        self._sim_stream_tree.configure(yscrollcommand=sim_tree_scroll.set)
        sim_tree_scroll.grid(row=0, column=1, sticky="ns")
        self._sim_stream_tree.bind("<<TreeviewSelect>>", self._on_sim_stream_tree_select)

        # ── Right: message area ──
        right_pane = tk.PanedWindow(tab2, orient=tk.VERTICAL,
                                     sashwidth=8, sashrelief=tk.RAISED, sashpad=2)
        right_pane.grid(row=1, column=1, sticky="nsew", padx=(2, 5), pady=(0, 5))

        # Message display
        msg_display_frame = ttk.LabelFrame(right_pane, text="消息记录")
        msg_display_frame.columnconfigure(0, weight=1)
        msg_display_frame.rowconfigure(0, weight=1)
        self._sim_msg_text = tk.Text(
            msg_display_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED,
        )
        sim_msg_scroll = ttk.Scrollbar(msg_display_frame, orient=tk.VERTICAL, command=self._sim_msg_text.yview)
        self._sim_msg_text.configure(yscrollcommand=sim_msg_scroll.set)
        self._sim_msg_text.grid(row=0, column=0, sticky="nsew")
        sim_msg_scroll.grid(row=0, column=1, sticky="ns")
        right_pane.add(msg_display_frame, stretch="always")

        # Input area
        input_frame = ttk.LabelFrame(right_pane, text="发送虚拟消息")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=0)
        input_frame.rowconfigure(1, weight=0)
        input_frame.rowconfigure(2, weight=1)

        row1 = ttk.Frame(input_frame)
        row1.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 2))
        ttk.Label(row1, text="发送者ID:").pack(side=tk.LEFT, padx=(0, 5))
        self._sim_sender_var = tk.StringVar(value="user_001")
        ttk.Entry(row1, textvariable=self._sim_sender_var, width=15).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row1, text="发送者名:").pack(side=tk.LEFT, padx=(0, 5))
        self._sim_sender_name_var = tk.StringVar(value="测试用户")
        ttk.Entry(row1, textvariable=self._sim_sender_name_var, width=15).pack(side=tk.LEFT)

        row2 = ttk.Frame(input_frame)
        row2.grid(row=1, column=0, sticky="ew", padx=5, pady=(2, 5))
        self._sim_input_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._sim_input_var, font=("Consolas", 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(row2, text="发送", command=self._sim_send_message).pack(side=tk.LEFT)

        # Willingness result display
        self._sim_willingness_text = tk.Text(
            input_frame, wrap=tk.WORD, font=("Consolas", 9),
            relief=tk.SUNKEN, borderwidth=1, state=tk.DISABLED, height=4,
        )
        willingness_scroll = ttk.Scrollbar(input_frame, orient=tk.VERTICAL, command=self._sim_willingness_text.yview)
        self._sim_willingness_text.configure(yscrollcommand=willingness_scroll.set)
        self._sim_willingness_text.grid(row=2, column=0, sticky="nsew", padx=5, pady=(0, 5))
        willingness_scroll.grid(row=2, column=1, sticky="ns", pady=(0, 5))

        right_pane.add(input_frame, stretch="always")

        self._main_notebook.add(tab2, text="聊天流模拟")

    def _build_prompt_editor_tab(self) -> None:
        """Build Tab 3: embedded prompt builder from prompt_builder.py."""
        tab3 = ttk.Frame(self._main_notebook)
        # Use a container frame with padding
        self._prompt_builder_app = PromptBuilderApp(
            parent=tab3,
            on_save_callback=self._on_prompt_saved,
            get_chat_streams=self._get_chat_streams_for_prompt,
        )
        self._main_notebook.add(tab3, text="提示词编辑")

        # Add a convenient button to open sub-agent editor
        sub_agent_btn = ttk.Button(
            tab3, text="子Agent 描述编辑器",
            command=self._open_sub_agent_editor_from_prompt,
        )
        sub_agent_btn.pack(side=tk.TOP, anchor=tk.NE, padx=8, pady=(4, 0))

    def _open_sub_agent_editor_from_prompt(self) -> None:
        """Open the sub-agent prompt editor from the embedded prompt builder."""
        if self._prompt_builder_app is not None:
            self._prompt_builder_app._open_sub_agent_editor()

    def _on_prompt_saved(self) -> None:
        """Called when prompt builder saves — refresh tools in sync."""
        self._all_tools = collect_all_tools()
        # Refresh current agent's tool list in the tree
        if self._current_agent_key in self._all_tools:
            self._current_tools = self._all_tools[self._current_agent_key]
            self._tool_tree.delete(*self._tool_tree.get_children())
            for t in self._current_tools:
                self._tool_tree.insert("", tk.END, values=(t.name,))
        self._set_status("提示词已保存 — 工具列表已同步更新")

    def _get_chat_streams_for_prompt(self) -> dict[str, dict[str, Any]]:
        """Return chat streams data for the prompt builder preview tab."""
        result: dict[str, dict[str, Any]] = {}
        for sid, s in self._chat_streams.items():
            result[s.name] = {
                "stream_id": sid,
                "name": s.name,
                "conversation_type": s.conversation_type,
                "group_id": s.group_id,
                "user_id": s.user_id,
                "messages": s.messages,
            }
        return result

    # ── Status bar ───────────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_var = tk.StringVar(value="就绪 — 请选择工具并填写参数")
        statusbar = ttk.Label(status_frame, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W)
        statusbar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._mode_label = ttk.Label(status_frame, text="", foreground="orange", relief=tk.SUNKEN, width=25, anchor=tk.E)
        self._mode_label.pack(side=tk.RIGHT)
        self._update_mode_label()

    # ── Populate selectors ───────────────────────────────────────────────

    def _populate_agent_selector(self) -> None:
        entries: list[str] = []

        # Main
        entries.append("【主Agent】reply/tools.py")

        # Sub-agents
        for src in AGENT_SOURCES:
            key = src.module_name.split(".")[-1]
            entries.append(f"【子Agent】{src.display_name} ({key})")

        # Tool packages
        for src in TOOL_PACKAGE_SOURCES:
            entries.append(f"【工具包】{src.display_name}")

        self._agent_combo["values"] = entries
        if entries:
            self._agent_combo.current(0)

    def _select_agent(self, agent_key: str) -> None:
        self._current_agent_key = agent_key
        self._current_tools = self._all_tools.get(agent_key, [])

        # Update tree (name only)
        self._tool_tree.delete(*self._tool_tree.get_children())
        for t in self._current_tools:
            self._tool_tree.insert("", tk.END, values=(t.name,))

        # Clear params, description, and response
        self._clear_params()
        self._clear_response()
        self._set_tool_description("")

        # Check for virtual tools
        virtual_tool_names = {"generate_image", "speak", "draw"}
        has_virtual = any(t.name in virtual_tool_names for t in self._current_tools)
        if has_virtual and self._virtual_mode.get():
            self._set_status(f"已选择 {agent_key} — {len(self._current_tools)} 个工具 — 绘图/TTS 使用虚拟回复模式")
        else:
            self._set_status(f"已选择 {agent_key} — {len(self._current_tools)} 个工具")

    # ── Event handlers ───────────────────────────────────────────────────

    def _on_agent_selected(self, event: object) -> None:
        sel = self._agent_var.get()
        if sel.startswith("【主Agent】"):
            self._select_agent("main")
        elif sel.startswith("【子Agent】"):
            # Extract key from "【子Agent】CreatorAgent (creator)"
            m = re.search(r"\((\w+)\)", sel)
            if m:
                self._select_agent(m.group(1))
        elif sel.startswith("【工具包】"):
            for display, key in TOOL_PACKAGE_HANDLER_KEYS.items():
                if display in sel:
                    self._select_agent(key)
                    break

    def _on_tool_selected(self, event: object) -> None:
        sel = self._tool_tree.selection()
        if not sel:
            return
        values = self._tool_tree.item(sel[0], "values")
        if not values:
            return
        tool_name = values[0]
        tool = next((t for t in self._current_tools if t.name == tool_name), None)
        if tool is None:
            return
        self._build_param_form(tool)
        self._set_tool_description(tool.description)

    def _build_param_form(self, tool: ToolInfo) -> None:
        """Dynamically build parameter input fields from JSON Schema."""
        self._clear_params()

        params = tool.parameters
        properties = params.get("properties", {})
        required_list: list[str] = params.get("required", [])

        # Parse chat context for auto-fill
        chat_ctx = self._parse_chat_context()

        if not properties:
            ttk.Label(self._param_inner, text="此工具无需参数", foreground="gray").pack(anchor=tk.W, padx=5, pady=5)
            return

        row = 0
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue

            prop_type = prop_schema.get("type", "string")
            prop_desc = prop_schema.get("description", "")
            is_required = prop_name in required_list
            # Auto-fill from chat context, fall back to schema default
            if prop_name in chat_ctx:
                default_val = chat_ctx[prop_name]
            else:
                default_val = prop_schema.get("default", "")

            # Label: name [type] * (description)
            type_tag = f"[{prop_type}]"
            label_text = f"{prop_name} {type_tag}"
            if is_required:
                label_text += " *"
            if prop_desc:
                label_text += f"\n{prop_desc[:80]}"

            label = ttk.Label(self._param_inner, text=label_text, justify=tk.LEFT)
            label.grid(row=row, column=0, sticky="w", padx=5, pady=2)

            # Highlight fields auto-filled from chat context
            if prop_name in chat_ctx:
                label.config(foreground="#0066CC")

            if prop_type == "boolean":
                var = tk.BooleanVar(value=bool(default_val))
                widget = ttk.Checkbutton(self._param_inner, variable=var)
                widget.var = var  # type: ignore[attr-defined]
            elif prop_type in ("integer", "number"):
                var = tk.StringVar(value=str(default_val) if default_val != "" else "0")
                widget = ttk.Entry(self._param_inner, textvariable=var, width=40)
                widget.var = var  # type: ignore[attr-defined]
            elif prop_type == "array":
                default_str = json.dumps(default_val, ensure_ascii=False) if default_val else "[]"
                if not isinstance(default_val, (list, dict)):
                    default_str = str(default_val) if default_val else "[]"
                var = tk.StringVar(value=default_str)
                widget = ttk.Entry(self._param_inner, textvariable=var, width=40)
                widget.var = var  # type: ignore[attr-defined]
            elif "enum" in prop_schema:
                var = tk.StringVar(value=str(default_val) if default_val else "")
                widget = ttk.Combobox(self._param_inner, textvariable=var,
                                      values=prop_schema["enum"], state="readonly", width=37)
                widget.var = var  # type: ignore[attr-defined]
            else:
                var = tk.StringVar(value=str(default_val) if default_val != "" else "")
                widget = ttk.Entry(self._param_inner, textvariable=var, width=40)
                widget.var = var  # type: ignore[attr-defined]

            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            self._param_widgets[prop_name] = widget
            self._param_fields[prop_name] = prop_schema
            row += 1

        self._param_inner.columnconfigure(1, weight=1)

    def _clear_params(self) -> None:
        for widget in self._param_inner.winfo_children():
            widget.destroy()
        self._param_widgets.clear()
        self._param_fields.clear()

    def _parse_chat_context(self) -> dict[str, Any]:
        """Build context dict from the selected chat stream."""
        stream = self._chat_streams.get(self._current_chat_stream_id)
        if stream is None:
            return {}
        ctx: dict[str, Any] = {}
        if stream.conversation_type == "group" and stream.group_id:
            ctx["group_id"] = int(stream.group_id)
            ctx["conversation_type"] = "group"
            ctx["target_id"] = int(stream.group_id)
        elif stream.conversation_type == "private" and stream.user_id:
            ctx["user_id"] = int(stream.user_id)
            ctx["conversation_type"] = "private"
            ctx["target_id"] = int(stream.user_id)
        if stream.messages:
            last_msg = stream.messages[-1]
            ctx["message_id"] = last_msg.get("message_id", 0)
            ctx["content"] = last_msg.get("content", "")
            ctx["sender_id"] = last_msg.get("sender_id", "")
            ctx["sender_name"] = last_msg.get("sender_name", "")
        return ctx

    # ── Chat stream management ─────────────────────────────────────────

    def _create_chat_stream_dialog(self) -> None:
        """Popup to create a new chat stream."""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建聊天流")
        dialog.geometry("350x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        f = ttk.Frame(dialog, padding=15)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="名称:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        name_var = tk.StringVar(value=f"Stream_{len(self._chat_streams)+1}")
        ttk.Entry(f, textvariable=name_var, width=30).grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        ttk.Label(f, text="类型:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        type_var = tk.StringVar(value="group")
        type_frame = ttk.Frame(f)
        type_frame.grid(row=1, column=1, sticky="w", pady=(0, 5), padx=(5, 0))
        ttk.Radiobutton(type_frame, text="群聊", variable=type_var, value="group").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(type_frame, text="私聊", variable=type_var, value="private").pack(side=tk.LEFT)

        ttk.Label(f, text="Group/User ID:").grid(row=2, column=0, sticky="w")
        id_var = tk.StringVar(value="123456789")
        ttk.Entry(f, textvariable=id_var, width=30).grid(row=2, column=1, sticky="ew", padx=(5, 0))
        f.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(15, 0), sticky="e")

        def _create() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("输入错误", "名称不能为空", parent=dialog)
                return
            sid = str(uuid.uuid4())[:8]
            ct = type_var.get()
            stream = ChatStream(
                stream_id=sid, name=name, conversation_type=ct,
                group_id=id_var.get() if ct == "group" else "",
                user_id=id_var.get() if ct == "private" else "",
            )
            self._chat_streams[sid] = stream
            self._refresh_stream_selectors()
            # Select the new stream
            self._ctx_stream_var.set(stream.name)
            self._sim_stream_var.set(stream.name)
            self._current_chat_stream_id = sid
            self._update_ctx_info()
            self._refresh_sim_stream_display()
            dialog.destroy()

        ttk.Button(btn_frame, text="创建", command=_create).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)

    def _delete_chat_stream(self) -> None:
        """Delete the currently selected chat stream."""
        sid = self._current_chat_stream_id
        if not sid or sid not in self._chat_streams:
            return
        name = self._chat_streams[sid].name
        if not messagebox.askyesno("确认删除", f"确定要删除聊天流 \"{name}\" 吗？"):
            return
        del self._chat_streams[sid]
        self._current_chat_stream_id = ""
        self._ctx_stream_var.set("")
        self._sim_stream_var.set("")
        self._update_ctx_info()
        self._refresh_stream_selectors()
        self._refresh_sim_stream_display()

    def _refresh_stream_selectors(self) -> None:
        """Update both stream selector comboboxes."""
        names = [s.name for s in self._chat_streams.values()]
        self._ctx_stream_combo["values"] = names
        self._sim_stream_combo["values"] = names

        # Also update Tab 2 stream tree
        self._sim_stream_tree.delete(*self._sim_stream_tree.get_children())
        for s in self._chat_streams.values():
            tag = "pipeline_active" if s.reply_pipeline_active else ""
            self._sim_stream_tree.insert("", tk.END, iid=s.stream_id, values=(
                s.name, "群聊" if s.conversation_type == "group" else "私聊",
                len(s.messages),
            ), tags=(tag,))
        self._sim_stream_tree.tag_configure("pipeline_active", background="#90EE90")

    def _on_ctx_stream_selected(self, event: object) -> None:
        name = self._ctx_stream_var.get()
        for sid, s in self._chat_streams.items():
            if s.name == name:
                self._current_chat_stream_id = sid
                self._update_ctx_info()
                return

    def _update_ctx_info(self) -> None:
        """Update the chat context info label in Tab 1."""
        stream = self._chat_streams.get(self._current_chat_stream_id)
        if stream is None:
            self._ctx_info_label.config(text="未选择聊天流 — 参数自动填充不可用")
            return
        ct = "群聊" if stream.conversation_type == "group" else "私聊"
        gid = stream.group_id or stream.user_id
        self._ctx_info_label.config(
            text=f"已选: {stream.name} ({ct}, ID={gid}, {len(stream.messages)} 条消息)"
        )

    # ── Tab 2: Chat simulation handlers ────────────────────────────────

    def _on_sim_stream_selected(self, event: object) -> None:
        name = self._sim_stream_var.get()
        for sid, s in self._chat_streams.items():
            if s.name == name:
                self._current_chat_stream_id = sid
                self._refresh_sim_stream_display()
                return

    def _on_sim_stream_tree_select(self, event: object) -> None:
        sel = self._sim_stream_tree.selection()
        if not sel:
            return
        sid = sel[0]
        if sid in self._chat_streams:
            self._current_chat_stream_id = sid
            self._sim_stream_var.set(self._chat_streams[sid].name)
            self._refresh_sim_stream_display()

    def _refresh_sim_stream_display(self) -> None:
        """Refresh the Tab 2 message display for the current stream."""
        self._sim_msg_text.config(state=tk.NORMAL)
        self._sim_msg_text.delete("1.0", tk.END)

        stream = self._chat_streams.get(self._current_chat_stream_id)
        if stream is None:
            self._sim_msg_text.insert("1.0", "← 请选择或新建一个聊天流")
            self._sim_msg_text.config(state=tk.DISABLED)
            return

        for i, msg in enumerate(stream.messages):
            ts = msg.get("timestamp", "")
            sender = msg.get("sender_name", msg.get("sender_id", "?"))
            content = msg.get("content", "")
            is_bot = msg.get("is_bot", False)
            prefix = "Bot" if is_bot else sender
            self._sim_msg_text.insert(tk.END, f"[{i+1}] ({ts}) {prefix}: ", "sender")
            self._sim_msg_text.insert(tk.END, f"{content}\n")
            if msg.get("willingness"):
                w = msg["willingness"]
                self._sim_msg_text.insert(tk.END, f"    └─ 回复意愿: {w}\n", "willingness")

        self._sim_msg_text.tag_configure("sender", foreground="#0066CC", font=("Consolas", 9, "bold"))
        self._sim_msg_text.tag_configure("willingness", foreground="#888888", font=("Consolas", 8))
        self._sim_msg_text.config(state=tk.DISABLED)
        self._sim_msg_text.see(tk.END)

    def _sim_send_message(self) -> None:
        """Send a virtual message to the current chat stream."""
        stream = self._chat_streams.get(self._current_chat_stream_id)
        if stream is None:
            messagebox.showwarning("未选择", "请先选择或新建一个聊天流")
            return

        content = self._sim_input_var.get().strip()
        if not content:
            return

        sender_id = self._sim_sender_var.get().strip()
        sender_name = self._sim_sender_name_var.get().strip()

        msg = {
            "message_id": int(time.time() * 1000),
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "is_bot": False,
        }

        # Use real willingness service if available, fall back to heuristic
        willingness = self._evaluate_willingness(stream, msg)
        msg["willingness"] = willingness

        stream.messages.append(msg)
        self._sim_input_var.set("")
        self._refresh_sim_stream_display()
        self._refresh_stream_selectors()
        self._update_ctx_info()

        # Show willingness result
        self._sim_willingness_text.config(state=tk.NORMAL)
        self._sim_willingness_text.delete("1.0", tk.END)
        self._sim_willingness_text.insert("1.0", f"回复意愿判断: {willingness}\n")
        self._sim_willingness_text.insert(tk.END, f"消息内容: {content}\n")
        self._sim_willingness_text.insert(tk.END, f"发送者: {sender_name} ({sender_id})\n")
        if stream.reply_pipeline_active:
            self._sim_willingness_text.insert(tk.END, "\n[回复管线已启动] 将使用真实场景代码处理此消息...\n")
            self._sim_willingness_text.insert(tk.END, "(管线处理为异步过程，结果将在消息列表中显示)\n")
        else:
            self._sim_willingness_text.insert(tk.END, "\n[提示] 可勾选\"启动回复管线\"使用真实代码处理\n")
        self._sim_willingness_text.config(state=tk.DISABLED)

    # ── Willingness evaluation (real code + heuristic fallback) ──────

    def _init_willing_service(self) -> Any:
        """Try to instantiate the real WillingService from the project. Returns None on failure.
        Uses direct TOML parsing + dict_to_dataclass to avoid Config.load() which
        calls register_models() and sys.exit(1) on missing env vars."""
        if self._willing_service is not None:
            return self._willing_service
        if self._willing_init_error:
            return None
        try:
            import tomlkit as _tk
            from neobot_app.config.loader.converter import dict_to_dataclass
            from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
            from neobot_app.willing import WillingService
            from neobot_contracts.ports.logging import NullLogger

            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config_dict = _tk.parse(f.read()).unwrap()
            bot_config = dict_to_dataclass(config_dict, BotConfigSchema)
            self._willing_service = WillingService(
                config=bot_config,
                logger=NullLogger(),
            )
            self._set_status("已加载真实回复意愿模块 (QuailWillingManager)")
            return self._willing_service
        except Exception as exc:
            self._willing_init_error = str(exc)
            self._set_status(f"无法加载真实意愿模块: {exc}，使用启发式模拟")
            return None

    def _evaluate_willingness(self, stream: ChatStream, msg: dict) -> str:
        """Evaluate reply willingness using real code or heuristic fallback."""
        try:
            ws = self._init_willing_service()
            if ws is None:
                return self._heuristic_willingness(stream, msg)
            from neobot_adapter.model.message import PrivateMessage, GroupMessage
            from neobot_app.message.queue import MessageQueue

            # Build the appropriate message object
            sender_id = int(msg.get("sender_id", 0)) if msg.get("sender_id", "").isdigit() else 0
            raw_msg = msg.get("content", "")
            message_id = msg.get("message_id", 0)

            if stream.conversation_type == "group":
                group_id = int(stream.group_id) if stream.group_id.isdigit() else 0
                chat_msg: Any = GroupMessage(
                    message_id=message_id,
                    user_id=sender_id,
                    message=None,
                    raw_message=raw_msg,
                    group_id=group_id,
                    sender={"nickname": msg.get("sender_name", ""), "user_id": sender_id},
                )
                queue_key = stream.group_id
            else:
                user_id = int(stream.user_id) if stream.user_id.isdigit() else 0
                chat_msg = PrivateMessage(
                    message_id=message_id,
                    user_id=sender_id,
                    message=None,
                    raw_message=raw_msg,
                    target_id=user_id,
                    sender={"nickname": msg.get("sender_name", ""), "user_id": sender_id},
                )
                queue_key = stream.user_id

            # Build a MessageQueue with existing messages as context
            queue = MessageQueue(max_size=100)
            for prev in stream.messages:
                prev_text = prev.get("content", "")
                prev_sender = int(prev.get("sender_id", 0)) if prev.get("sender_id", "").isdigit() else 0
                if stream.conversation_type == "group":
                    prev_msg: Any = GroupMessage(
                        message_id=prev.get("message_id", 0),
                        user_id=prev_sender,
                        message=None,
                        raw_message=prev_text,
                        group_id=group_id,
                        sender={"nickname": prev.get("sender_name", ""), "user_id": prev_sender},
                    )
                else:
                    prev_msg = PrivateMessage(
                        message_id=prev.get("message_id", 0),
                        user_id=prev_sender,
                        message=None,
                        raw_message=prev_text,
                        target_id=user_id,
                        sender={"nickname": prev.get("sender_name", ""), "user_id": prev_sender},
                    )
                queue.push(queue_key, prev_msg)

            # Call the real willingness service
            decision = ws.evaluate(
                message=chat_msg,
                queue=queue,
                queue_key=queue_key,
            )

            reasons_str = ", ".join(decision.reasons) if decision.reasons else "无"
            return (
                f"{'有意' if decision.should_reply else '无意'}回复 "
                f"(manager={decision.manager_name}, "
                f"prob={decision.probability:.3f}, "
                f"should_reply={decision.should_reply}, "
                f"reasons: {reasons_str})"
            )
        except Exception as exc:
            # Fall back to heuristic on any error
            return f"[真实模块出错: {exc}] {self._heuristic_willingness(stream, msg)}"

    def _heuristic_willingness(self, stream: ChatStream, msg: dict) -> str:
        """Simple heuristic willingness simulation (fallback)."""
        content = msg.get("content", "")
        triggers = ["@", "bot", "机器人", "小助手", "帮我", "查", "搜", "画", "提醒", "天气"]
        score = 0.0
        reasons = []
        for t in triggers:
            if t.lower() in content.lower():
                score += 0.2
                reasons.append(t)
        if "?" in content or "？" in content or "吗" in content:
            score += 0.1
            reasons.append("疑问句")
        if len(content) > 20:
            score += 0.05
            reasons.append("长消息")
        score = min(score, 1.0)
        source = "[启发式模拟]"
        if score >= 0.3:
            return f"有意回复 {source} (score={score:.2f}, 触发: {', '.join(reasons) if reasons else '无'})"
        return f"无意回复 {source} (score={score:.2f})"

    def _on_sim_real_qq_toggled(self) -> None:
        if self._sim_real_qq_var.get():
            if not self._ws_client.state.connected:
                messagebox.showwarning("未连接", "请先连接 QQ 后再开启此功能")
                self._sim_real_qq_var.set(False)
                return
            self._set_status("已开启真实 QQ 消息接收 — 新消息将自动创建聊天流")
        else:
            self._set_status("已关闭真实 QQ 消息接收")

    def _on_sim_pipeline_toggled(self) -> None:
        stream = self._chat_streams.get(self._current_chat_stream_id)
        active = self._sim_pipeline_var.get()
        if stream:
            stream.reply_pipeline_active = active
        if active:
            self._sim_pipeline_indicator.itemconfig(self._sim_pipeline_dot, fill="green2")
            self._sim_pipeline_label.config(text="管线运行中", foreground="green")
            self._set_status("回复管线已启动 — 新消息将使用真实场景代码处理")
        else:
            self._sim_pipeline_indicator.itemconfig(self._sim_pipeline_dot, fill="red")
            self._sim_pipeline_label.config(text="管线未启动", foreground="gray")
            self._set_status("回复管线已停止")
        self._refresh_stream_selectors()

    def _get_param_values(self) -> dict[str, Any]:
        """Read current values from the parameter form."""
        values: dict[str, Any] = {}
        for prop_name, widget in self._param_widgets.items():
            prop_schema = self._param_fields.get(prop_name, {})
            prop_type = prop_schema.get("type", "string")

            if isinstance(widget, ttk.Checkbutton):
                values[prop_name] = widget.var.get()  # type: ignore[attr-defined]
            elif prop_type == "integer":
                try:
                    values[prop_name] = int(widget.var.get())  # type: ignore[attr-defined]
                except ValueError:
                    values[prop_name] = 0
            elif prop_type == "number":
                try:
                    values[prop_name] = float(widget.var.get())  # type: ignore[attr-defined]
                except ValueError:
                    values[prop_name] = 0.0
            elif prop_type == "array":
                try:
                    values[prop_name] = json.loads(widget.var.get())  # type: ignore[attr-defined]
                except (json.JSONDecodeError, ValueError):
                    values[prop_name] = []
            elif prop_type == "boolean":
                values[prop_name] = widget.var.get()  # type: ignore[attr-defined]
            else:
                values[prop_name] = widget.var.get()  # type: ignore[attr-defined]
        return values

    def _execute_tool(self) -> None:
        """Execute the selected tool with current parameters."""
        sel = self._tool_tree.selection()
        if not sel:
            messagebox.showwarning("未选择工具", "请先在左侧选择要执行的工具")
            return

        tool_name = self._tool_tree.item(sel[0], "values")[0]
        args = self._get_param_values()

        # Special path for delegate tool: use real agent registry + streaming window
        if tool_name == "delegate":
            self._execute_delegate(args)
            return

        self._execute_status.config(text="执行中...", foreground="blue")
        self._execute_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        try:
            self._exec_env.virtual_mode = self._virtual_mode.get()
            # Determine timeout: long wait mode overrides default 60s
            timeout = 60.0
            if self._long_wait_var.get():
                try:
                    timeout = float(self._long_wait_seconds_var.get())
                except ValueError:
                    timeout = 30.0
                self._set_status(f"长时等待模式: 最长等待 {timeout:.0f} 秒...")
            result: ToolExecResult = self._async_mgr.run_async(
                self._exec_env.execute_tool(self._current_agent_key, tool_name, args),
                timeout=timeout,
            )
            # Check if response time exceeded tool's default wait
            default_wait = self._exec_env.virtual_templates.get(tool_name, {}).get("wait_seconds", 0)
            timeout_notice = ""
            if default_wait and result.elapsed_ms > default_wait * 1000 * 1.5:
                timeout_notice = f" (注意: 已超过默认等待 {default_wait}s)"
            self._display_result(result)
            self._execute_status.config(text="完成", foreground="green")
            self._set_status(f"{tool_name} 执行完成 — {result.elapsed_ms:.0f}ms"
                             f"{' (虚拟回复)' if result.is_virtual else ''}{timeout_notice}")
        except Exception as exc:
            error_msg = str(exc)
            self._display_error(error_msg)
            self._execute_status.config(text="失败", foreground="red")
            self._set_status(f"执行失败: {error_msg}")
        finally:
            self._execute_btn.config(state=tk.NORMAL)
            # Reset status after a few seconds
            self.root.after(3000, lambda: self._execute_status.config(text=""))

    def _execute_delegate(self, args: dict[str, Any]) -> None:
        """Execute delegate tool with real agent registry and streaming display."""
        agent_name = args.get("agent", "")
        task = args.get("task", "")
        tasks = args.get("tasks", None)
        previous_response = args.get("previous_response", "")
        session_id = args.get("session_id", "")

        self._execute_status.config(text="构建 Agent...", foreground="blue")
        self._execute_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        registry = self._get_agent_registry()

        if registry is None or len(registry) == 0:
            self._display_error("Agent 注册表为空，无法执行 delegate。请检查模型配置和 API 环境变量。")
            self._execute_status.config(text="失败", foreground="red")
            self._execute_btn.config(state=tk.NORMAL)
            self.root.after(3000, lambda: self._execute_status.config(text=""))
            return

        # Handle batch tasks
        if tasks and isinstance(tasks, list) and len(tasks) > 0:
            self._execute_delegate_batch(tasks, previous_response, session_id, registry)
            return

        if not agent_name:
            self._display_error("缺少 agent 参数")
            self._execute_status.config(text="失败", foreground="red")
            self._execute_btn.config(state=tk.NORMAL)
            self.root.after(3000, lambda: self._execute_status.config(text=""))
            return

        if agent_name not in registry._agents:
            available = ", ".join(registry.names)
            self._display_error(f"Agent '{agent_name}' 未注册。可用: {available}")
            self._execute_status.config(text="失败", foreground="red")
            self._execute_btn.config(state=tk.NORMAL)
            self.root.after(3000, lambda: self._execute_status.config(text=""))
            return

        # Build delegate context from selected chat stream
        context = ""
        stream = self._chat_streams.get(self._current_chat_stream_id)
        if stream is not None:
            ctx_parts = [
                f"会话类型: {'群聊' if stream.conversation_type == 'group' else '私聊'}",
                f"会话ID: {stream.group_id or stream.user_id}",
            ]
            context = "\n".join(ctx_parts)

        # Open streaming window (starts async work immediately)
        timeout = 120.0
        if self._long_wait_var.get():
            try:
                timeout = float(self._long_wait_seconds_var.get())
            except ValueError:
                timeout = 120.0

        stream_win = DelegateStreamWindow(
            self.root, agent_name, task,
            self._async_mgr, registry,
            session_id=session_id,
            previous_response=previous_response,
            context=context,
        )

        self._execute_status.config(text="流式传输中...", foreground="blue")
        self._set_status(f"Delegate → {agent_name}: {task[:60]}...")

        # Poll until done, keeping UI alive
        deadline = time.monotonic() + timeout
        while not stream_win.is_done:
            self.root.update()
            time.sleep(0.05)
            if time.monotonic() > deadline:
                self._display_error(f"Delegate 超时 ({timeout:.0f}s)")
                self._execute_status.config(text="超时", foreground="red")
                self._execute_btn.config(state=tk.NORMAL)
                self._set_status(f"Delegate 超时: {agent_name}")
                self.root.after(3000, lambda: self._execute_status.config(text=""))
                return

        result_text = stream_win.result or "[Agent 未返回文本内容]"

        # Display result in the normal response panels
        self._display_result(ToolExecResult(
            tool_name="delegate",
            args=args,
            text_response=result_text,
            raw_response=result_text,
            elapsed_ms=(time.monotonic() - (deadline - timeout)) * 1000,
        ))
        self._execute_status.config(text="完成", foreground="green")
        self._set_status(f"Delegate → {agent_name} 完成")
        self._execute_btn.config(state=tk.NORMAL)
        self.root.after(3000, lambda: self._execute_status.config(text=""))

    def _execute_delegate_batch(
        self,
        tasks: list[dict],
        previous_response: str,
        session_id: str,
        registry: Any,
    ) -> None:
        """Execute batch delegate tasks, each in its own streaming window."""
        results: list[str] = []
        for i, t in enumerate(tasks):
            agent_name = t.get("agent", "")
            task = t.get("task", "")
            prev = t.get("previous_response", previous_response)
            sid = t.get("session_id", session_id)

            if agent_name not in registry._agents:
                results.append(f"{agent_name}: Agent 未注册")
                continue

            self._set_status(f"Delegate 批量 [{i+1}/{len(tasks)}] → {agent_name}...")
            self.root.update_idletasks()

            stream_win = DelegateStreamWindow(
                self.root, agent_name, task,
                self._async_mgr, registry,
                session_id=sid,
                previous_response=prev,
            )

            timeout = 300.0
            deadline = time.monotonic() + timeout
            while not stream_win.is_done:
                self.root.update()
                time.sleep(0.05)
                if time.monotonic() > deadline:
                    results.append(f"{agent_name}: 超时")
                    break

            if stream_win.is_done:
                results.append(f"{agent_name}: {stream_win.result or '[无输出]'}")

        combined = "\n\n".join(results)
        self._display_result(ToolExecResult(
            tool_name="delegate",
            args={"tasks": tasks},
            text_response=combined,
            raw_response=combined,
            elapsed_ms=0,
        ))
        self._execute_status.config(text="完成", foreground="green")
        self._set_status(f"Delegate 批量完成: {len(tasks)} 个任务")
        self._execute_btn.config(state=tk.NORMAL)
        self.root.after(3000, lambda: self._execute_status.config(text=""))

    def _display_result(self, result: ToolExecResult) -> None:
        # Text response
        self._resp_text.config(state=tk.NORMAL)
        self._resp_text.delete("1.0", tk.END)

        text = result.text_response
        # Try to pretty-print JSON
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            pass

        self._resp_text.insert("1.0", text)
        self._resp_text.config(state=tk.DISABLED)

        # Raw JSON (formatted and colorized)
        self._raw_text.config(state=tk.NORMAL)
        self._raw_text.delete("1.0", tk.END)
        self._insert_json_with_highlight(result.raw_response)
        self._raw_text.config(state=tk.DISABLED)

        # Info
        mode = "虚拟回复" if result.is_virtual else "真实执行"
        self._result_info_label.config(
            text=f"工具: {result.tool_name} | 模式: {mode} | 耗时: {result.elapsed_ms:.0f}ms")

    def _display_error(self, error: str) -> None:
        self._resp_text.config(state=tk.NORMAL)
        self._resp_text.delete("1.0", tk.END)
        self._resp_text.insert("1.0", f"执行出错:\n{error}")
        self._resp_text.config(state=tk.DISABLED)

        self._raw_text.config(state=tk.NORMAL)
        self._raw_text.delete("1.0", tk.END)
        self._raw_text.insert("1.0", json.dumps({"ok": False, "error": error}, ensure_ascii=False, indent=2))
        self._raw_text.config(state=tk.DISABLED)

        self._result_info_label.config(text=f"错误: {error[:100]}", foreground="red")

    def _clear_response(self) -> None:
        for text_widget in (self._resp_text, self._raw_text):
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.config(state=tk.DISABLED)
        self._result_info_label.config(text="")

    def _set_tool_description(self, text: str) -> None:
        """Display tool description in the scrollable description panel."""
        self._tool_desc_text.config(state=tk.NORMAL)
        self._tool_desc_text.delete("1.0", tk.END)
        if text:
            self._tool_desc_text.insert("1.0", text)
        self._tool_desc_text.config(state=tk.DISABLED)

    def _insert_json_with_highlight(self, text: str) -> None:
        """Insert JSON text with basic syntax highlighting."""
        try:
            parsed = json.loads(text)
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            formatted = text

        self._raw_text.insert("1.0", formatted)

        # Apply line-by-line syntax highlighting
        total_lines = formatted.count("\n") + 1
        for line_no in range(1, total_lines + 1):
            line_content = self._raw_text.get(f"{line_no}.0", f"{line_no}.end")

            # Highlight keys: "key": pattern
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:', line_content):
                key_start = f"{line_no}.{m.start()}"
                key_end = f"{line_no}.{m.end() - 1}"  # up to just before colon
                self._raw_text.tag_add("json_key", key_start, key_end)

            # Highlight string values: : "value"
            for m in re.finditer(r':\s+"((?:[^"\\]|\\.)*)"', line_content):
                q_idx = m.group().index('"')
                str_start = f"{line_no}.{m.start() + q_idx}"
                str_end = f"{line_no}.{m.end()}"
                self._raw_text.tag_add("json_str", str_start, str_end)

            # Highlight numbers
            for m in re.finditer(r'(?<=:\s)(\d+(?:\.\d+)?)(?=\s*[,\]\n\r]|$)', line_content):
                self._raw_text.tag_add("json_num", f"{line_no}.{m.start()}", f"{line_no}.{m.end()}")

            # Highlight booleans and null
            for kw in ("true", "false", "null"):
                for m in re.finditer(rf'(?<=:\s)({kw})(?=\s*[,\]\n\r]|$)', line_content):
                    self._raw_text.tag_add("json_bool", f"{line_no}.{m.start()}", f"{line_no}.{m.end()}")

    def _on_ws_state_changed(self, state: WSConnectionState) -> None:
        """Called from background thread — schedule UI update."""
        self.root.after(0, self._update_ws_ui, state)

    def _update_ws_ui(self, state: WSConnectionState) -> None:
        self._ws_connect_btn.config(state=tk.NORMAL)
        if state.connected:
            self._ws_indicator.itemconfig(self._ws_indicator_dot, fill="green2")
            self._ws_status_label.config(text=f"QQ 已连接 ({state.url})", foreground="green")
            self._ws_connect_btn.config(text="断开连接")
            self._sim_real_qq_cb.config(state=tk.NORMAL)
        else:
            self._ws_indicator.itemconfig(self._ws_indicator_dot, fill="red")
            err = f" — {state.error}" if state.error else ""
            self._ws_status_label.config(text=f"QQ 未连接{err}", foreground="gray")
            self._ws_connect_btn.config(text="连接 QQ")
            self._sim_real_qq_var.set(False)
            self._sim_real_qq_cb.config(state=tk.DISABLED)

    def _toggle_ws_connection(self) -> None:
        if self._ws_client.state.connected:
            self._ws_client.disconnect()
            return

        dialog = WSConnectDialog(self.root)
        self.root.wait_window(dialog.window)
        if dialog.result:
            self._ws_connect_btn.config(text="连接中...", state=tk.DISABLED)
            self._ws_status_label.config(text="正在连接...", foreground="gray")
            self._ws_client.connect(dialog.result["host"], dialog.result["port"])

    def _on_virtual_mode_toggled(self) -> None:
        self._exec_env.virtual_mode = self._virtual_mode.get()
        self._update_virtual_label()
        self._update_mode_label()
        self._set_status(f"虚拟回复模式: {'开启' if self._virtual_mode.get() else '关闭（使用真实模型）'}")

    def _update_virtual_label(self) -> None:
        if self._virtual_mode.get():
            self._virtual_label.config(text="虚拟回复模式（绘图/TTS）", foreground="orange")
        else:
            self._virtual_label.config(text="真实模型模式", foreground="darkgreen")

    def _update_mode_label(self) -> None:
        if self._virtual_mode.get():
            self._mode_label.config(text="模式: 虚拟回复", foreground="orange")
        else:
            self._mode_label.config(text="模式: 真实调用", foreground="darkgreen")

    def _reload_config(self) -> None:
        self.config = load_config()
        self._exec_env = ToolExecutionEnv(self.config, self._ws_client, virtual_mode=self._virtual_mode.get())
        # Also reload prompt builder config if embedded
        if self._prompt_builder_app is not None:
            self._prompt_builder_app._reload_config()
        self._set_status("配置已重新加载")

    def _open_virtual_template_editor(self) -> None:
        """Open the virtual reply template editor window."""
        editor = VirtualTemplateEditor(self.root, self._exec_env)
        self.root.wait_window(editor.window)

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _on_close(self) -> None:
        # Check prompt builder for unsaved changes
        if self._prompt_builder_app is not None and self._prompt_builder_app._modified:
            if not messagebox.askyesno("未保存的更改", "提示词编辑器中有未保存的更改，确定退出？"):
                return
        self._ws_client.disconnect()
        self._async_mgr.stop()
        self.root.destroy()


# ── Virtual template editor window ───────────────────────────────────────

class VirtualTemplateEditor:
    """Popup window for editing virtual reply templates."""

    def __init__(self, parent: tk.Tk, exec_env: ToolExecutionEnv) -> None:
        self._exec_env = exec_env
        self.window = tk.Toplevel(parent)
        self.window.title("虚拟回复模板编辑器")
        self.window.geometry("900x650")
        self.window.transient(parent)

        self._templates = load_virtual_templates()
        self._current_key: str = ""
        self._notebook = ttk.Notebook(self.window)
        self._notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._text_widgets: dict[str, dict[str, tk.Text]] = {}

        for key, tmpl in self._templates.items():
            tab = ttk.Frame(self._notebook)
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=0)
            tab.rowconfigure(1, weight=0)
            tab.rowconfigure(2, weight=0)
            tab.rowconfigure(3, weight=1)

            desc = tmpl.get("description", key)
            ttk.Label(tab, text=f"描述: {desc}", foreground="gray").grid(row=0, column=0, sticky="w", padx=5, pady=(5, 2))

            # Wait seconds
            wait_frame = ttk.Frame(tab)
            wait_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
            ttk.Label(wait_frame, text="等待时长 (秒):").pack(side=tk.LEFT, padx=(0, 5))
            wait_var = tk.StringVar(value=str(tmpl.get("wait_seconds", 1.0)))
            wait_entry = ttk.Entry(wait_frame, textvariable=wait_var, width=10)
            wait_entry.pack(side=tk.LEFT)

            # Response template
            ttk.Label(tab, text="回复模板 (支持 {file_port} 占位符):", anchor=tk.W).grid(
                row=2, column=0, sticky="w", padx=5, pady=(5, 2))

            text_widget = tk.Text(tab, wrap=tk.WORD, font=("Consolas", 10), relief=tk.SUNKEN, borderwidth=2, height=18)
            text_widget.grid(row=3, column=0, sticky="nsew", padx=5, pady=(0, 5))
            text_widget.insert("1.0", tmpl.get("response", ""))

            scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scroll.set)
            scroll.grid(row=3, column=1, sticky="ns", pady=(0, 5))

            tab.rowconfigure(3, weight=1)

            self._text_widgets[key] = {"response": text_widget, "wait_var": wait_var}
            self._notebook.add(tab, text=key)

        # Buttons
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="恢复默认", command=self._reset_defaults).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)

    def _save(self) -> None:
        for key, widgets in self._text_widgets.items():
            self._templates[key]["response"] = widgets["response"].get("1.0", "end-1c")
            try:
                self._templates[key]["wait_seconds"] = float(widgets["wait_var"].get())
            except ValueError:
                pass
        save_virtual_templates(self._templates)
        self._exec_env.virtual_templates = self._templates
        self.window.destroy()

    def _reset_defaults(self) -> None:
        if not messagebox.askyesno("确认", "恢复所有模板为默认值？"):
            return
        self._templates = dict(DEFAULT_VIRTUAL_TEMPLATES)
        for key, widgets in self._text_widgets.items():
            tmpl = self._templates.get(key, {})
            widgets["response"].delete("1.0", tk.END)
            widgets["response"].insert("1.0", tmpl.get("response", ""))
            widgets["wait_var"].set(str(tmpl.get("wait_seconds", 1.0)))
        save_virtual_templates(self._templates)
        self._exec_env.virtual_templates = self._templates


# ── WebSocket connection dialog ──────────────────────────────────────────

class WSConnectDialog:
    """Popup dialog for choosing QQ connection mode."""

    def __init__(self, parent: tk.Tk) -> None:
        self.result: dict[str, Any] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("连接 QQ — OneBot 反向 WebSocket")
        self.window.geometry("420x240")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        # Read config defaults
        cfg_host = os.environ.get("NEO_BOT_ADAPTER_HOST", "127.0.0.1")
        cfg_port = os.environ.get("NEO_BOT_ADAPTER_PORT", "8080")

        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="选择连接方式:", font=("", 10, "bold")).pack(anchor=tk.W)

        # ── Option 1: from config ──
        self._mode_var = tk.StringVar(value="config")
        cfg_frame = ttk.Frame(main_frame)
        cfg_frame.pack(fill=tk.X, pady=(10, 5))
        ttk.Radiobutton(cfg_frame, text="使用 config 配置连接", variable=self._mode_var,
                        value="config", command=self._on_mode_changed).pack(anchor=tk.W)
        cfg_info = ttk.Frame(cfg_frame)
        cfg_info.pack(fill=tk.X, padx=(25, 0), pady=(2, 0))
        ttk.Label(cfg_info, text=f"地址: {cfg_host}:{cfg_port}", foreground="gray").pack(anchor=tk.W)

        # ── Option 2: custom ──
        custom_frame = ttk.Frame(main_frame)
        custom_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Radiobutton(custom_frame, text="自定义连接地址", variable=self._mode_var,
                        value="custom", command=self._on_mode_changed).pack(anchor=tk.W)

        addr_frame = ttk.Frame(custom_frame)
        addr_frame.pack(fill=tk.X, padx=(25, 0), pady=(2, 0))
        ttk.Label(addr_frame, text="Host:").pack(side=tk.LEFT, padx=(0, 5))
        self._host_var = tk.StringVar(value="127.0.0.1")
        self._host_entry = ttk.Entry(addr_frame, textvariable=self._host_var, width=18)
        self._host_entry.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(addr_frame, text="Port:").pack(side=tk.LEFT, padx=(0, 5))
        self._port_var = tk.StringVar(value="8080")
        self._port_entry = ttk.Entry(addr_frame, textvariable=self._port_var, width=7)
        self._port_entry.pack(side=tk.LEFT)

        # ── Buttons ──
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))
        ttk.Button(btn_frame, text="连接", command=self._on_connect).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=self.window.destroy).pack(side=tk.RIGHT)

        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        is_custom = self._mode_var.get() == "custom"
        state = "normal" if is_custom else "disabled"
        self._host_entry.config(state=state)
        self._port_entry.config(state=state)

    def _on_connect(self) -> None:
        if self._mode_var.get() == "config":
            host = os.environ.get("NEO_BOT_ADAPTER_HOST", "127.0.0.1")
            port_str = os.environ.get("NEO_BOT_ADAPTER_PORT", "8080")
        else:
            host = self._host_var.get().strip()
            port_str = self._port_var.get().strip()

        if not host:
            messagebox.showwarning("输入错误", "Host 不能为空", parent=self.window)
            return
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("输入错误", "Port 必须是整数", parent=self.window)
            return

        self.result = {"host": host, "port": port}
        self.window.destroy()


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    ensure_test_data_dir()
    app = ToolsEditorApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
