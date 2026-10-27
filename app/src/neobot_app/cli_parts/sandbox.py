"""沙箱临时文件清理与维护（由 cli.py 拆分）。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from neobot_app.config.loader.manager import ConfigLoadError


async def _run_sandbox_cleanup() -> int:
    """独立启动 AI agent 执行沙箱维护清理。不依赖运行中的 Bot。"""
    from dataclasses import dataclass

    from neobot_app.assembly.agents import resolve_agent_model_name
    from neobot_app.bootstrap._config import build_config
    from neobot_app.bootstrap._runtime import build_sandbox_components
    from neobot_app.core import DATA_DIR

    print("沙箱维护 Agent 启动中…")
    print()

    # 1. 加载配置
    try:
        config = build_config()
    except ConfigLoadError as exc:
        print(f"配置加载失败：\n{exc}")
        return 1
    sandbox_cfg = getattr(config.agent, "sandbox", None)
    if not sandbox_cfg or not sandbox_cfg.enabled:
        print("错误: 沙箱功能未启用 (agent.sandbox.enabled = false)")
        return 1

    # 2. 构建沙箱组件
    sandbox = build_sandbox_components(config=config, data_dir=DATA_DIR)
    sandbox_service = sandbox["sandbox_service"]
    if sandbox_service is None:
        print("错误: sandbox_service 未构建成功")
        return 1

    print(f"沙箱目录: {DATA_DIR / 'sandbox'}")
    print()

    # 3. 创建 AI Provider
    model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    from neobot_chat.models import create_provider
    try:
        provider = create_provider(model_name)
    except Exception as exc:
        print(f"错误: 无法创建 provider ({model_name}): {exc}")
        return 1
    print(f"AI 模型: {model_name}")

    # 4. 构建 SkillManager（仅沙箱相关技能）
    from neobot_app.skills.base import SkillManager
    from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill
    from neobot_app.skills.sandbox_maintenance_skill import SandboxMaintenanceSkill
    from neobot_app.skills.file_storage_skill import FileStorageSkill

    mgr = SkillManager()
    mgr.register(SandboxManagerSkill(
        sandbox_service=sandbox_service,
        hold_max_minutes=120,
    ))
    mgr.register(SandboxMaintenanceSkill(
        maintenance_manager=sandbox["sandbox_maintenance_manager"],
        sandbox_service=sandbox_service,
        temp_cleaner=sandbox["temp_cleaner"],
    ))
    mgr.register(FileStorageSkill(
        sandbox_service=sandbox_service,
    ))

    # 5. 将 SkillManager 包装为 ToolExecutor → Toolset
    from neobot_chat.tools.toolset import ToolSpec, Toolset

    @dataclass(frozen=True)
    class _SkillToolExecutor:
        _mgr: SkillManager

        def definitions(self):
            # 维护 Agent 自建工具集，不经过主回复管线的按需加载，需拿到全部工具
            return self._mgr.get_all_tools()

        async def execute(self, name: str, args: dict) -> str:
            return await self._mgr.execute(name, args)

        async def close(self) -> None:
            pass

    def _always_allow(_args, _ctx, _policy):
        from neobot_chat.schema.types import ToolAccessRule
        return ToolAccessRule(action="allow")

    tool_defs = mgr.get_all_tools()
    specs = [ToolSpec(definition=d, access_resolver=_always_allow) for d in tool_defs]
    toolset = Toolset(executor=_SkillToolExecutor(mgr), specs=specs)
    print(f"已加载 {len(tool_defs)} 个工具")
    print()

    # 6. 创建 Agent
    from neobot_chat.runtime.agent import Agent

    from neobot_app.prompt.store import (
        DEFAULT_TEMPLATE_FILE,
        PromptStore,
        get_template_value,
        parse_prompt_file,
        sync_default_prompts,
    )

    builtin = parse_prompt_file(DEFAULT_TEMPLATE_FILE).get("maintenance", {})
    maintenance_prompt = str(builtin.get("system_prompt") or "").strip()
    try:
        sync_default_prompts(DATA_DIR)
        prompt_store = PromptStore(DATA_DIR)
        maintenance_prompt = get_template_value(
            prompt_store, "maintenance", "system_prompt"
        ) or maintenance_prompt
    except Exception:
        pass

    agent = Agent(
        provider=provider,
        toolset=toolset,
        system_prompt=maintenance_prompt,
        max_iterations=30,
        command_timeout=120,
    )

    # 7. 执行维护
    print("正在执行沙箱维护…")
    print("─" * 50)
    state = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "请执行一次完整的沙箱维护清理。\n"
                    "按系统提示中的维护流程逐步操作，完成每步后汇报结果。"
                ),
            },
        ],
    }
    try:
        result = await agent.invoke(state)
    except Exception as exc:
        print(f"\n错误: Agent 执行失败: {exc}")
        return 1
    finally:
        try:
            await provider.close()
        except Exception:
            pass

    # 8. 输出结果
    messages = result.get("messages", [])
    for msg in messages:
        role = msg.get("role", "")
        if role == "assistant":
            content = msg.get("content")
            if content:
                print(content)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    print(f"\n[工具] {tc['function']['name']}")
        elif role == "tool":
            content = msg.get("content", "")
            # 截断过长输出
            if len(content) > 200:
                content = content[:200] + "…"
            print(f"  -> {content}")

    print("─" * 50)
    print("\n沙箱维护完成。")
    return 0


def cmd_sandbox_clean(args: argparse.Namespace) -> None:
    """独立执行沙箱清理。"""
    try:
        exit_code = asyncio.run(_run_sandbox_cleanup())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
