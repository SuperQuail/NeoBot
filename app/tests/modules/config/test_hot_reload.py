"""配置热重载分类与 /reload 命令。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.commands.service import CommandService
from neobot_app.config.hot_reload import (
    classify,
    diff_configs,
    diff_snapshot,
    is_hot_reloadable,
    snapshot,
    summarize_changes,
)
from neobot_app.config.schemas.bot import BotConfig

BOT = 88888
SUPER = 10000
OTHER = 20000


def test_classify_known_paths() -> None:
    assert is_hot_reloadable(("chat", "group_chat_chance")) is True
    assert is_hot_reloadable(("willing", "observe_window")) is True
    assert is_hot_reloadable(("message", "max_length")) is True
    assert is_hot_reloadable(("models", "registry")) is False
    assert is_hot_reloadable(("tts", "enabled")) is False
    assert is_hot_reloadable(("adapter", "mode")) is False


def test_specific_rule_wins_over_section_rule() -> None:
    """chat 整体热重载，但 key_word / 缓存参数是启动期快照。"""
    assert is_hot_reloadable(("chat", "key_word")) is False
    assert is_hot_reloadable(("chat", "cache_retention_seconds")) is False
    assert is_hot_reloadable(("chat", "enable_balance_check")) is False
    assert is_hot_reloadable(("chat", "reply_cooldown_seconds")) is True


def test_unknown_path_defaults_to_restart() -> None:
    hot, reason = classify(("brand_new_section", "field"))

    assert hot is False
    assert "需要重启" in reason


def test_diff_configs_groups_hot_and_restart() -> None:
    before = BotConfig()
    after = BotConfig()
    after.chat.group_chat_chance = 0.9
    after.tts.enabled = not before.tts.enabled

    changes = summarize_changes(diff_configs(before, after))

    hot_paths = {item["path"] for item in changes["hot_reload"]}
    restart_paths = {item["path"] for item in changes["needs_restart"]}
    assert "chat.group_chat_chance" in hot_paths
    assert "tts.enabled" in restart_paths
    assert changes["hot_reload_count"] == len(changes["hot_reload"])
    assert changes["needs_restart_count"] == len(changes["needs_restart"])


def test_diff_snapshot_detects_runtime_reload() -> None:
    """真实 ConfigProxy：先快照，再原地替换内部配置。"""
    from neobot_app.config.proxy import ConfigProxy

    config = BotConfig()
    proxy = ConfigProxy(config)
    before = snapshot(proxy)

    config.chat.group_chat_chance = 0.25
    changes = diff_snapshot(before, proxy)

    assert [item.path for item in changes] == ["chat.group_chat_chance"]
    assert changes[0].hot_reload is True
    assert changes[0].before != changes[0].after


def _config():
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


def _message(text: str, user_id: int):
    return SimpleNamespace(
        user_id=user_id, message=[{"type": "text", "data": {"text": text}}]
    )


class _Adapter:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, conversation, segments):
        text = "".join(
            str((segment.get("data") or {}).get("text") or "")
            for segment in segments
            if isinstance(segment, dict) and segment.get("type") == "text"
        )
        self.sent.append(text)
        return SimpleNamespace(status="ok")

    async def send_private_msg(self, user_id, message):
        return await self.send(SimpleNamespace(kind="private", id=str(user_id)), message)


async def _run_reload(
    result_payload, *, user_id: int = SUPER, expect_called: bool = True
) -> str:
    adapter = _Adapter()
    calls: list[int] = []

    async def _callback():
        calls.append(1)
        return result_payload

    service = CommandService(
        config=_config(), adapter=adapter, config_reload_callback=_callback
    )
    handled = await service.handle_message(
        _message("/reload", user_id), kind="private", queue_key=str(user_id)
    )
    assert handled.consumed is True
    assert calls == ([1] if expect_called else [])
    return adapter.sent[-1] if adapter.sent else ""


@pytest.mark.asyncio
async def test_reload_command_reports_hot_and_restart_items() -> None:
    text = await _run_reload(
        {
            "ok": True,
            "message": "配置已热重载：1 项立即生效，1 项需重启后生效。",
            "changes": {
                "hot_reload": [
                    {
                        "path": "chat.group_chat_chance",
                        "before": "0.5",
                        "after": "0.9",
                        "hot_reload": True,
                        "reason": "聊天管线按需读取",
                    }
                ],
                "needs_restart": [
                    {
                        "path": "models.registry",
                        "before": "[]",
                        "after": "[...]",
                        "hot_reload": False,
                        "reason": "运行中的 Provider 已固化",
                    }
                ],
            },
        }
    )

    assert "已生效" in text
    assert "chat.group_chat_chance" in text
    assert "需重启" in text
    assert "models.registry" in text


@pytest.mark.asyncio
async def test_reload_command_is_super_admin_only() -> None:
    text = await _run_reload(
        {"ok": True, "message": "x"}, user_id=OTHER, expect_called=False
    )

    assert "权限" in text or "没有" in text


@pytest.mark.asyncio
async def test_reload_command_handles_missing_callback() -> None:
    adapter = _Adapter()
    service = CommandService(config=_config(), adapter=adapter)
    await service.handle_message(
        _message("/reload", SUPER), kind="private", queue_key=str(SUPER)
    )

    assert "不可用" in adapter.sent[-1]
