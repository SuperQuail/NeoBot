"""统一入口回归：custom 覆盖经 ``prompt.assets`` 生效到各提示词消费方。

这些消费方（子 Agent 描述/提示词、自修复文本、睡眠文案、长回复兜底）此前
各自直读 ``PromptStore``/``packaged_template``；本用例锁住它们都改走统一入口
后 custom 覆盖仍然生效，且默认值仍来自 ``templates/prompts.toml``。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.agents.problem_solver_parts.agent import ProblemSolverAgent
from neobot_app.agents.problem_solver_parts.prompts import prompt_text
from neobot_app.agents.self_heal_parts.manager_heal import SelfHealManagerHealMixin
from neobot_app.prompt.store import PromptStore, sync_default_prompts
from neobot_app.reply.orchestrator_parts.settings import SettingsMixin
from neobot_app.runtime.sleep_service import SleepService


def test_custom_overrides_reach_prompt_consumers_through_assets(tmp_path) -> None:
    """custom 覆盖经 assets 生效到子 Agent / 自修复 / 睡眠 / 长回复兜底。"""
    sync_default_prompts(tmp_path)
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.write_text(
        '[problem_solver]\ndescription = "自定义解题简介"\n'
        '[self_heal]\nresume_prompt = "自定义重试提示"\n'
        '[wake_up]\ntemplate = "自定义唤醒提示"\n'
        '[long_reply_fallback]\ntemplate = "自定义兜底回复"\n',
        encoding="utf-8",
    )
    store = PromptStore(tmp_path)

    agent = ProblemSolverAgent(SimpleNamespace(max_tokens=1), prompt_store=store)
    assert agent.description == "自定义解题简介"
    assert prompt_text(store, "description") == "自定义解题简介"

    class _Manager(SelfHealManagerHealMixin):
        _prompt_store = store

    assert _Manager()._prompt_text("resume_prompt") == "自定义重试提示"

    assert SleepService(prompt_store=store).wake_prompt() == "自定义唤醒提示"

    settings = type("_Settings", (SettingsMixin,), {"_prompt_store": store})()
    assert settings._get_long_reply_fallback_template() == "自定义兜底回复"
