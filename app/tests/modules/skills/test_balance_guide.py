"""余额查询技能：文档生成与注册。"""

from __future__ import annotations

from pathlib import Path

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.skills.balance_guide import (
    NO_HINT_NOTE,
    build_balance_query_document,
    sync_balance_query_skill,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.registered: dict[str, list] = {}

    def unregister_owner(self, owner: str) -> list[str]:
        return self.registered.pop(owner, [])

    def register_many(self, owner: str, skills: list) -> None:
        self.registered[owner] = list(skills)


def test_document_only_lists_models_with_hint() -> None:
    config = BotConfig()
    config.models.primary_chat_model.balance_query_hint = "GET https://api.example.com/user/balance，Authorization: Bearer <key>"

    document, count = build_balance_query_document(config)

    assert count == 1
    assert "primary_chat_model" in document
    assert "https://api.example.com/user/balance" in document
    # 未配置提示的模型不出现在文档里
    assert "agent_model_1" not in document
    assert document.rstrip().endswith(NO_HINT_NOTE)


def test_document_without_any_hint_still_contains_note() -> None:
    document, count = build_balance_query_document(BotConfig())

    assert count == 0
    assert NO_HINT_NOTE in document
    assert document.rstrip().endswith(NO_HINT_NOTE)


def test_sync_writes_file_and_registers_skill(tmp_path: Path) -> None:
    config = BotConfig()
    config.models.vision_model.balance_query_hint = "GET https://vision.example.com/balance"
    registry = FakeRegistry()

    ok = sync_balance_query_skill(
        registry=registry, data_dir=tmp_path, config=config, logger=None
    )

    assert ok is True
    skill_path = tmp_path / "skills" / "balance-query" / "SKILL.md"
    assert skill_path.is_file()
    raw = skill_path.read_text(encoding="utf-8")
    assert raw.startswith("---\nname: balance-query\n")
    assert "GET https://vision.example.com/balance" in raw

    entries = registry.registered["balance"]
    assert len(entries) == 1
    assert entries[0].name == "balance-query"
    assert entries[0].path == skill_path


def test_sync_returns_false_without_registry_but_writes_file(tmp_path: Path) -> None:
    ok = sync_balance_query_skill(
        registry=None, data_dir=tmp_path, config=BotConfig(), logger=None
    )

    assert ok is False
    assert (tmp_path / "skills" / "balance-query" / "SKILL.md").is_file()
