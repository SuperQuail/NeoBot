"""命令卡片与隐私口径（issue #85）：

- 每条命令的主结果优先出图；渲染不可用时回等价纯文本，**两者都不含任何 QQ 号**；
- 管理员卡片只画头像（取不到头像回落首字母色块），不列号码；
- 出图成功时 handler 返回 None（命令服务不再补发文本）。
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomlkit

from neobot_app.bootstrap import _commands
from neobot_app.commands import card as card_module
from neobot_app.commands.service import CommandService
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig

BOT = 88888
SUPER = 10001
SUB_A = 20002
SUB_B = 30003

BASE_CONFIG = f"""version = "0.6.0"

[bot]
account = 88888
nick_name = "bot"

[chat]
admin_accounts = ["{SUPER}"]
sub_admin_accounts = ["{SUB_A}"]
"""

QQ_PATTERN = re.compile(r"\d{5,15}")


def _card_text(html: str) -> str:
    """卡片里**用户可见的文本**：去掉 <style> 与标签。

    CSS 里的颜色值（如 `#f85149`）会误伤「不含 5-15 位数字」这类断言，
    而它们并不是可见内容。
    """
    without_style = re.sub(r"<style.*?</style>", "", str(html), flags=re.DOTALL)
    return re.sub(r"<[^>]+>", " ", without_style)


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


class _LoggerFactory:
    def get_logger(self, name):
        import logging

        return logging.getLogger(name)


@pytest.fixture()
def config_file(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(BASE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(_commands, "CONFIG_FILE", path)
    monkeypatch.setattr(_commands, "CONFIG_BACKUP_DIR", tmp_path / "config_backup")
    return path


def _service(path: Path) -> tuple[ConfigProxy, CommandService, _Adapter]:
    config = ConfigProxy(
        dict_to_dataclass(tomlkit.parse(path.read_text(encoding="utf-8")).unwrap(), BotConfig)
    )
    adapter = _Adapter()
    service = _commands.build_command_service(
        config=config, adapter=adapter, logger_factory=_LoggerFactory()
    )
    return config, service, adapter


def _message(text: str, user_id: int):
    return SimpleNamespace(
        user_id=user_id,
        message=[{"type": "text", "data": {"text": text}}],
    )


async def _run(config_file: Path, text: str, user_id: int = SUPER):
    _config, service, adapter = _service(config_file)
    await service.handle_message(_message(text, user_id), kind="private", queue_key=str(user_id))
    return (adapter.sent[-1] if adapter.sent else ""), service, adapter


@pytest.fixture()
def captured_cards(monkeypatch) -> list[str]:
    """把卡片 HTML 截下来（不真的截图），返回捕获列表。"""
    captured: list[str] = []

    async def _fake_render(html, **_kwargs):
        captured.append(str(html))
        return None  # 渲染不可用 → 调用方走纯文本降级

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)
    return captured


# ── 隐私口径：回复与卡片里都不许出现 QQ 号 ──────────────────────────


async def test_add_admin_reply_has_no_qq(config_file: Path) -> None:
    reply, _service_, _adapter = await _run(config_file, f"/add_admin {SUB_B}")

    assert "已添加次级管理员" in reply
    assert QQ_PATTERN.search(reply) is None


async def test_del_admin_reply_has_no_qq(config_file: Path) -> None:
    reply, _service_, _adapter = await _run(config_file, f"/del_admin {SUB_A}")

    assert "已删除次级管理员" in reply
    assert QQ_PATTERN.search(reply) is None


async def test_missing_target_reply_lists_counts_not_numbers(config_file: Path) -> None:
    reply, _service_, _adapter = await _run(config_file, "/add_admin")

    assert QQ_PATTERN.search(reply) is None
    assert "超级管理员 1 人" in reply
    assert "次级管理员 1 人" in reply


@pytest.mark.parametrize("text", [f"/add_admin {SUPER}", f"/add_admin {SUB_A}", "/del_admin 99999"])
async def test_guard_branches_have_no_qq(config_file: Path, text: str) -> None:
    reply, _service_, _adapter = await _run(config_file, text)

    assert QQ_PATTERN.search(reply) is None


async def test_admin_card_html_has_no_qq_and_keeps_avatar_slot(
    config_file: Path, captured_cards: list[str]
) -> None:
    await _run(config_file, f"/add_admin {SUB_B}")

    assert captured_cards, "成功路径应当先尝试出图"
    html = captured_cards[-1]
    visible = _card_text(html)
    assert str(SUB_B) not in visible and str(SUB_A) not in visible and str(SUPER) not in visible
    assert QQ_PATTERN.search(visible) is None
    assert "次级管理员已添加" in visible
    # 头像片段已注入（占位符被替换掉），且片段本身只有图片/色块
    assert card_module.AVATAR_MARKER not in html
    assert "cmd-avatar" in html


async def test_admin_card_uses_avatar_store_data_uri(
    config_file: Path, captured_cards: list[str], monkeypatch
) -> None:
    _config, service, _adapter = _service(config_file)

    class _Store:
        def get_data_uri(self, user_id):
            # 真实头像是 base64 PNG 字节，不含号码
            return "data:image/png;base64,AVATARPIXELS"

    service.set_avatar_store(_Store())
    await service.handle_message(
        _message(f"/add_admin {SUB_B}", SUPER), kind="private", queue_key=str(SUPER)
    )

    html = captured_cards[-1]
    assert "data:image/png;base64,AVATARPIXELS" in html, "有 AvatarStore 时应内联头像"
    assert '<div class="cmd-avatar cmd-avatar-fallback"' not in html, "有头像时不该再画色块"
    assert QQ_PATTERN.search(_card_text(html)) is None


async def test_admin_card_falls_back_to_initial_block_without_store(
    config_file: Path, captured_cards: list[str]
) -> None:
    await _run(config_file, f"/add_admin {SUB_B}")

    html = captured_cards[-1]
    assert "cmd-avatar-fallback" in html and ">管<" in html


# ── 出图 / 降级两条路径 ────────────────────────────────────────────


async def test_card_is_sent_and_handler_returns_none(config_file: Path, monkeypatch) -> None:
    sent: list[tuple[str, str, bytes]] = []

    async def _fake_render(_html, **_kwargs):
        return b"PNGDATA"

    async def _fake_send(kind, conv_id, data, **_kwargs):
        sent.append((kind, conv_id, data))
        return True

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)
    _config, service, adapter = _service(config_file)
    monkeypatch.setattr(service, "send_image_bytes", _fake_send)

    await service.handle_message(
        _message(f"/add_admin {SUB_B}", SUPER), kind="private", queue_key=str(SUPER)
    )

    assert sent == [("private", str(SUPER), b"PNGDATA")]
    assert adapter.sent == [], "出图成功时不应再补发文本"


async def test_render_failure_returns_text_with_hint(config_file: Path, monkeypatch) -> None:
    async def _fake_render(_html, **_kwargs):
        return None

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)
    reply, _service_, _adapter = await _run(config_file, f"/add_admin {SUB_B}")

    assert "已添加次级管理员" in reply
    assert card_module.FALLBACK_HINT in reply


async def test_standby_status_card_never_shows_operator_number(
    config_file: Path, captured_cards: list[str]
) -> None:
    from neobot_app.runtime.standby_service import StandbyService

    _config, service, _adapter = _service(config_file)
    standby = StandbyService()
    await standby.enter(reason="排查中", operator=f"private:{SUPER}")
    service.set_standby_service(standby) if hasattr(service, "set_standby_service") else None
    service._standby_service = standby  # 命令只读该属性

    await service.handle_message(_message("/standby_status", SUPER), kind="private", queue_key=str(SUPER))

    visible = _card_text(captured_cards[-1])
    assert "排查中" in visible
    assert "私聊管理员" in visible
    assert QQ_PATTERN.search(visible) is None
