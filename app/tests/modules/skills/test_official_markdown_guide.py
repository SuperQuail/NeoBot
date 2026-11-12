"""官方 Markdown 卡片 skill 文档生成与注册。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.skills.official_markdown_guide import sync_official_markdown_skill


class _Registry:
    def __init__(self) -> None:
        self.registered: list[tuple[str, list]] = []

    def unregister_owner(self, owner: str) -> None:
        pass

    def register_many(self, owner: str, items: list) -> None:
        self.registered.append((owner, list(items)))


def test_sync_writes_skill_and_registers(tmp_path) -> None:
    registry = _Registry()
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)

    assert sync_official_markdown_skill(registry=registry, data_dir=tmp_path, logger=logger) is True

    path = tmp_path / "skills" / "qq-official-markdown" / "SKILL.md"
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---\nname: qq-official-markdown\n")
    assert "send_official_markdown" in raw
    assert "Markdown 图片" in raw
    assert "qqbot-cmd-input" in raw
    assert registry.registered[0][0] == "official_markdown"
    assert registry.registered[0][1][0].name == "qq-official-markdown"
