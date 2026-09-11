"""网页面板「提示词」页的后端逻辑测试（纯函数，不起 HTTP 服务）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_app.builtin_plugins.dashboard import prompt_admin
from neobot_app.prompt.store import PromptStore, sync_default_prompts


@pytest.fixture()
def store(tmp_path: Path) -> PromptStore:
    sync_default_prompts(tmp_path)
    return PromptStore(tmp_path)


def test_describe_sections_lists_defaults_and_placeholders(store: PromptStore) -> None:
    payload = prompt_admin.describe_sections(store)
    sections = {item["name"]: item for item in payload["sections"]}

    assert "group_chat" in sections
    keys = {key["path"]: key for key in sections["group_chat"]["keys"]}
    assert "template" in keys
    assert keys["template"]["kind"] == "template"
    assert keys["template"]["overridden"] is False
    assert "bot_name" in keys["template"]["placeholders"]
    assert keys["template"]["value"] == keys["template"]["default"]

    # 子表键必须展开成 runtime.template，面板才能单独编辑
    solver = {key["path"]: key for key in sections["problem_solver"]["keys"]}
    assert "system_prompt" in solver
    assert "runtime.template" in solver
    assert solver["description"]["kind"] == "text"


def test_write_and_remove_override_roundtrip(tmp_path: Path, store: PromptStore) -> None:
    custom_file = Path(store.custom_file)

    prompt_admin.write_override(custom_file, "group_chat", "template", "自定义群聊提示词")
    store.reload()

    described = {item["name"]: item for item in prompt_admin.describe_sections(
        store, custom_sections=prompt_admin.read_custom_sections(custom_file)
    )["sections"]}
    key = next(k for k in described["group_chat"]["keys"] if k["path"] == "template")
    assert key["value"] == "自定义群聊提示词"
    assert key["overridden"] is True
    assert key["default"] != "自定义群聊提示词"
    # 其它分区继续继承默认值
    assert store.template("friend_chat").startswith("<你是谁>")

    prompt_admin.remove_override(custom_file, "group_chat", "template")
    store.reload()
    assert store.template("group_chat").startswith("<你是谁>")


def test_write_override_supports_sub_table(tmp_path: Path, store: PromptStore) -> None:
    custom_file = Path(store.custom_file)

    prompt_admin.write_override(
        custom_file, "problem_solver", "runtime.template", "RT {timeout_seconds}"
    )
    store.reload()

    assert store.sub_section("problem_solver", "runtime")["template"] == "RT {timeout_seconds}"
    # 同一分区的其它键不受影响
    assert "problem-solving agent" in store.get("problem_solver", "system_prompt")


def test_write_override_keeps_backup_and_rejects_bad_path(tmp_path: Path, store: PromptStore) -> None:
    custom_file = Path(store.custom_file)
    prompt_admin.write_override(custom_file, "group_chat", "template", "第一次")
    prompt_admin.write_override(custom_file, "group_chat", "template", "第二次")

    assert custom_file.with_suffix(custom_file.suffix + ".bak").is_file()

    with pytest.raises(ValueError):
        prompt_admin.write_override(custom_file, "", "template", "x")
    with pytest.raises(ValueError):
        prompt_admin.write_override(custom_file, "group_chat", "a.b.c", "x")


def test_preview_renders_escaped_content_and_reports_placeholders() -> None:
    result = prompt_admin.preview_template(
        "你好{bot_name}|当前:{current_datetime}|字面量:{{msg_id=1}}|未知:{nope}"
    )

    assert "你好小助手" in result["rendered"]
    assert "字面量:{msg_id=1}" in result["rendered"]
    # 未提供的占位符原样保留，并被报告出来
    assert "{nope}" in result["rendered"]
    assert result["unresolved"] == ["nope"]
    assert "bot_name" in result["placeholders"]
    assert set(result["values"]) == set(result["placeholders"])


def test_preview_accepts_value_overrides() -> None:
    result = prompt_admin.preview_template(
        "{bot_name} 在 {group_name}", {"bot_name": "弥音", "group_name": "测试群"}
    )

    assert result["rendered"] == "弥音 在 测试群"


def test_sample_values_prefer_real_config() -> None:
    from neobot_app.config.schemas.bot import BotConfig

    config = BotConfig()
    config.bot.nick_name = "弥音"
    config.bot.account = 3830912140
    config.bot.alias_name = ["喵"]
    config.chat.group_description = {"888": "测试群描述"}

    values = prompt_admin.sample_values(config)

    assert values["bot_name"] == "弥音"
    assert values["bot_account"] == "3830912140"
    assert values["other_name"] == ",也有人叫你喵"
    assert values["group_description"] == "测试群描述"
    assert values["group_id"] == "888"
    assert values["current_time"]
