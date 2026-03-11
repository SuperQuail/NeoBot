from __future__ import annotations

import asyncio
import os
import shlex
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAT_SRC = ROOT / "packages" / "chat" / "src"
if str(CHAT_SRC) not in sys.path:
    sys.path.insert(0, str(CHAT_SRC))

from neobot_chat.providers import (  # noqa: E402
    DeepSeekOfficialProvider,
    OpenAIProvider,
)
from neobot_chat.runtime.agent import Agent  # noqa: E402
from neobot_chat.schema.types import (  # noqa: E402
    Message,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolGuardContext,
)
from neobot_chat.tools import build_builtin_toolset  # noqa: E402

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
except ImportError:  # pragma: no cover
    PromptSession = None
    InMemoryHistory = None

PROVIDER = os.getenv("NEOBOT_PROVIDER", "deepseek_official")
API_KEY = os.getenv("NEOBOT_API_KEY", "")
OPENAI_BASE_URL = os.getenv("NEOBOT_OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("NEOBOT_MODEL", "deepseek-reasoner")
STREAM = os.getenv("NEOBOT_STREAM", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SHOW_REASONING = os.getenv("NEOBOT_SHOW_REASONING", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

SYSTEM_PROMPT = (
    "你是 NeoBot。回答简洁、直接、友好。"
    "如果用户要求文件操作、查看目录、运行命令，优先调用工具完成。"
)
ALLOWED_COMMANDS = []


class ConsoleIO:
    def __init__(self) -> None:
        self._session = None
        if PromptSession is not None and InMemoryHistory is not None:
            self._session = PromptSession(history=InMemoryHistory())

    async def prompt(self, label: str) -> str:
        if self._session is not None:
            return await self._session.prompt_async(label)
        return await asyncio.to_thread(input, label)


console = ConsoleIO()


def is_path_allowed(path: str, context: ToolGuardContext) -> bool:
    candidate = Path(path).expanduser()
    base = context.cwd or ROOT
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    )
    return any(
        resolved == allowed or resolved.is_relative_to(allowed)
        for allowed in context.allowed_paths
    )


def is_command_allowed(command: str, context: ToolGuardContext) -> bool:
    if not context.allowed_commands:
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    return any(fnmatch(parts[0], pattern) for pattern in context.allowed_commands)


async def ask_approval(title: str, details: str) -> bool:
    try:
        answer = await console.prompt(f"\n{title}\n{details}\n[y/N]: ")
    except (KeyboardInterrupt, EOFError):
        print("\nApproval cancelled.")
        return False
    return answer.strip().lower() in {"y", "yes"}


async def tool_guard(name: str, args: dict, context: ToolGuardContext) -> bool:
    if name in {"read_file", "write_file", "list_files"}:
        path = str(args.get("path") or ".")
        if is_path_allowed(path, context):
            return True
        return await ask_approval(
            f"Approve {name}?",
            f"path: {path}",
        )

    if name == "execute_command":
        command = str(args.get("command") or "")
        target_cwd = str(args.get("cwd") or context.cwd or ROOT)
        return await ask_approval(
            "Approve execute_command?",
            f"cwd: {target_cwd}\ncommand: {command}",
        )

    if name == "delegate":
        return await ask_approval(
            "Approve delegate?",
            f"args: {args}",
        )

    return True


def on_event(event: str, data: dict) -> None:
    if event == "llm_end" and data.get("tool_calls"):
        print(f"\n[tool_calls] {', '.join(data['tool_calls'])}")
    elif event == "tool_start":
        print(f"\n[tool_start] {data.get('name')} args={data.get('args')}")
    elif event == "tool_end":
        result = str(data.get("result", ""))
        print(f"\n[tool_end] {data.get('name')} result={result[:200]}")
    elif event == "tool_denied":
        print(f"\n[tool_denied] {data.get('name')} args={data.get('args')}")
    elif event == "error":
        print(f"\n[tool_error] {data.get('name')} error={data.get('error')}")


def build_provider() -> OpenAIProvider | DeepSeekOfficialProvider:
    provider_name = PROVIDER.strip().lower()
    if provider_name in {"deepseek_offical", "deepseek_official"}:
        return DeepSeekOfficialProvider(
            api_key=API_KEY,
            base_url="https://api.deepseek.com",
            model=MODEL,
        )
    if provider_name == "openai":
        return OpenAIProvider(
            api_key=API_KEY,
            base_url=OPENAI_BASE_URL,
            model=MODEL,
        )
    raise ValueError(
        f"Unsupported provider: {PROVIDER}. Expected 'openai', 'deepseek_official', or legacy 'deepseek_offical'."
    )


async def chat_loop() -> None:
    if not API_KEY:
        print("Missing NEOBOT_API_KEY. Bye!")
        return

    provider = build_provider()

    policy = ToolAccessPolicy(
        delegate_rule=ToolAccessRule(action="ask", fallback_action="allow"),
        path_out_of_scope_rule=ToolAccessRule(action="ask", fallback_action="deny"),
        command_disallowed_rule=ToolAccessRule(action="ask", fallback_action="deny"),
    )

    agent = Agent(
        provider,
        cwd=ROOT,
        allowed_commands=ALLOWED_COMMANDS,
        system_prompt=SYSTEM_PROMPT,
        on_event=on_event,
        tool_guard=tool_guard,
    )

    messages: list[Message] = []
    system_prompt_sent = False

    print(f"Provider: {PROVIDER}")
    print(f"Model: {MODEL}")
    active_base_url = (
        "https://api.deepseek.com"
        if PROVIDER.strip().lower() in {"deepseek_offical", "deepseek_official"}
        else OPENAI_BASE_URL
    )
    print(f"Base URL: {active_base_url}")
    print(f"Stream: {STREAM}")
    print(f"Show reasoning: {SHOW_REASONING}")
    print(f"CWD: {ROOT}")
    print(f"Allowed commands: {', '.join(ALLOWED_COMMANDS)}")
    print(
        "内置工具：read_file, write_file, list_files, execute_command, list_agents, delegate"
    )
    if PromptSession is None:
        print(
            "提示：未安装 prompt_toolkit，当前回退到 input()；中文删除问题可能仍会出现。"
        )
    print("输入内容开始对话；输入 exit / quit / q 结束。")

    try:
        while True:
            try:
                user_text = (await console.prompt("\nYou: ")).strip()
            except KeyboardInterrupt:
                print("\nInterrupted. Bye!")
                break
            except EOFError:
                print("\nEOF. Bye!")
                break

            if not user_text:
                continue
            if user_text.lower() in {"exit", "quit", "q"}:
                print("Bye!")
                break

            request_messages = [*messages, {"role": "user", "content": user_text}]
            if not system_prompt_sent:
                _, _, prepared_messages = agent._prepare({"messages": request_messages})
                built_prompt = next(
                    (
                        message.get("content")
                        for message in prepared_messages
                        if message.get("role") == "system" and message.get("content")
                    ),
                    None,
                )
            else:
                built_prompt = None
            if built_prompt:
                print("\n--- Final System Prompt ---")
                print(built_prompt)
                print("--- End System Prompt ---")

            messages = request_messages

            print("Assistant: ", end="", flush=True)
            final_state: State | None = None
            printed = False

            try:
                if STREAM:
                    reasoning_started = False
                    async for chunk in agent.stream_invoke({"messages": messages}):
                        if SHOW_REASONING and chunk.reasoning_delta:
                            if not reasoning_started:
                                print("\n[reasoning] ", end="", flush=True)
                                reasoning_started = True
                            print(chunk.reasoning_delta, end="", flush=True)
                        if chunk.delta:
                            if reasoning_started:
                                print("\nAssistant: ", end="", flush=True)
                                reasoning_started = False
                            print(chunk.delta, end="", flush=True)
                            printed = True
                        if chunk.message is not None and reasoning_started:
                            print()
                            reasoning_started = False
                        if chunk.state is not None:
                            final_state = chunk.state
                else:
                    final_state = await agent.invoke({"messages": messages})
                    final_message = (
                        final_state.get("messages", [])[-1]
                        if final_state.get("messages")
                        else None
                    )
                    final_content = (
                        final_message.get("content") if final_message else None
                    )
                    if isinstance(final_content, str) and final_content:
                        print(final_content, end="", flush=True)
                        printed = True
                    elif final_content is not None:
                        print(str(final_content), end="", flush=True)
                        printed = True
            except KeyboardInterrupt:
                print("\nInterrupted. Bye!")
                break

            if not printed:
                print("(no response)", end="")
            print()

            if final_state is None:
                raise RuntimeError("Agent did not return final state")
            messages = list(final_state.get("messages", []))
            if not system_prompt_sent and any(
                message.get("role") == "system" and message.get("content")
                for message in messages
            ):
                system_prompt_sent = True
                agent.system_prompt = None
                messages = [
                    message for message in messages if message.get("role") != "system"
                ]
    finally:
        await agent.close()


if __name__ == "__main__":
    try:
        asyncio.run(chat_loop())
    except KeyboardInterrupt:
        print("\nInterrupted. Bye!")
