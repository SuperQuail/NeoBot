"""WIP 配置标记：读得到但不生效的开关，必须在描述里写明（避免用户以为它管用）。

背景：`enable_bot_get_married` 在 schema 与配置参考里都像一个可用开关，但全仓没有任何
消费方 —— 改它不会产生任何效果。面板（`ConfigTreePanel` 渲染字段 description）与配置参考
是用户唯一能看到的提示，标记被删掉就又会变成「看起来能用」。

这条用例同时锁住两处：schema 的 description 与 docs/05-配置参考.md 的表格行。结婚玩法
真正接入时，先改这两处再删本用例。
"""

from __future__ import annotations

from pathlib import Path

from neobot_app.config.schemas.bot import Bot

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_REFERENCE = REPO_ROOT / "docs" / "05-配置参考.md"
WIP_MARKER = "[WIP · 尚未接线]"


def _description(name: str) -> str:
    return str(Bot.__dataclass_fields__[name].metadata.get("description", ""))


def test_marriage_switch_is_marked_as_wip_in_schema() -> None:
    description = _description("enable_bot_get_married")
    assert description.startswith(WIP_MARKER), "配置面板会显示这段描述，必须写明 WIP"
    assert "当前不生效" in description


def test_marriage_switch_is_marked_as_wip_in_reference() -> None:
    row = next(
        (
            line
            for line in CONFIG_REFERENCE.read_text(encoding="utf-8").splitlines()
            if line.startswith("| `enable_bot_get_married`")
        ),
        None,
    )
    assert row is not None, "配置参考里应当有 enable_bot_get_married 一行"
    assert WIP_MARKER in row and "当前不生效" in row
