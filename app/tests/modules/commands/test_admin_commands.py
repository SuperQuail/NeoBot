"""内置命令 /add_admin、/del_admin：写盘持久化与失败如实汇报。

回归背景：这两条命令此前会「回复成功但配置没写进去」（[chat] 段缺失时
写进了游离 dict），重启后次级管理员列表就空了。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import tomlkit

from neobot_app.bootstrap import _commands
from neobot_app.commands.service import CommandService
from neobot_app.config.chat_writer import read_sub_admin_accounts
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig

BOT = 88888
SUPER = 10001
SUB = 20002

BASE_CONFIG = """version = "0.6.0"

[bot]
account = 88888
nick_name = "bot"

[chat]
admin_accounts = ["10001"]
sub_admin_accounts = []
"""


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


def _message(text: str, user_id: int):
    return SimpleNamespace(
        user_id=user_id,
        message=[{"type": "text", "data": {"text": text}}],
    )


class _LoggerFactory:
    def get_logger(self, name):
        import logging

        return logging.getLogger(name)


@pytest.fixture()
def config_file(tmp_path: Path, monkeypatch) -> Path:
    """把 CONFIG_FILE / CONFIG_BACKUP_DIR 指向临时目录。"""
    path = tmp_path / "config.toml"
    path.write_text(BASE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(_commands, "CONFIG_FILE", path)
    monkeypatch.setattr(_commands, "CONFIG_BACKUP_DIR", tmp_path / "config_backup")
    return path


def _service(path: Path) -> tuple[ConfigProxy, CommandService, _Adapter]:
    """按真实装配方式构建：ConfigProxy + build_command_service 的保存回调。"""
    config = ConfigProxy(
        dict_to_dataclass(tomlkit.parse(path.read_text(encoding="utf-8")).unwrap(), BotConfig)
    )
    adapter = _Adapter()
    service = _commands.build_command_service(
        config=config, adapter=adapter, logger_factory=_LoggerFactory()
    )
    return config, service, adapter


def _reload(path: Path):
    """模拟重启：从磁盘重新构造配置对象。"""
    return dict_to_dataclass(tomlkit.parse(path.read_text(encoding="utf-8")).unwrap(), BotConfig)


async def _send(service: CommandService, text: str, user_id: int) -> str:
    result = await service.handle_message(
        _message(text, user_id), kind="private", queue_key=str(user_id)
    )
    assert result.consumed is True
    return str(getattr(service, "_last_text", "") or "")


async def _run(path: Path, text: str, user_id: int) -> tuple[str, ConfigProxy, CommandService]:
    config, service, adapter = _service(path)
    await service.handle_message(
        _message(text, user_id), kind="private", queue_key=str(user_id)
    )
    return (adapter.sent[-1] if adapter.sent else ""), config, service


# ---------------------------------------------------------------------------
# 正常路径：写盘 + 热重载 + 重启后仍在
# ---------------------------------------------------------------------------


async def test_add_admin_persists_and_survives_restart(config_file: Path) -> None:
    reply, config, service = await _run(config_file, "/add_admin 30003", SUPER)

    assert "已添加次级管理员" in reply
    assert "30003" in reply
    # 磁盘
    assert read_sub_admin_accounts(config_file) == ("30003",)
    # 内存（热重载生效）
    assert list(config.chat.sub_admin_accounts) == ["30003"]
    assert service.permissions.is_sub_admin(30003) is True
    # 重启
    assert list(_reload(config_file).chat.sub_admin_accounts) == ["30003"]


async def test_add_admin_writes_schema_correct_strings(config_file: Path) -> None:
    await _run(config_file, "/add_admin 30003", SUPER)

    text = config_file.read_text(encoding="utf-8")
    assert 'sub_admin_accounts = ["30003"]' in text


async def test_del_admin_removes_and_persists(config_file: Path) -> None:
    await _run(config_file, "/add_admin 30003", SUPER)
    reply, _config, _service_ = await _run(config_file, "/del_admin 30003", SUPER)

    assert "已删除次级管理员" in reply
    assert read_sub_admin_accounts(config_file) == ()


async def test_sub_admin_gains_permissions_after_restart(config_file: Path) -> None:
    await _run(config_file, "/add_admin 30003", SUPER)
    _config, service, adapter = _service(config_file)

    assert service.permissions.is_sub_admin(30003) is True

    await service.handle_message(
        _message("/add_admin 40004", 30003), kind="private", queue_key="30003"
    )
    assert "没有权限" in (adapter.sent[-1] if adapter.sent else "")


async def test_add_admin_rejects_super_admin_target(config_file: Path) -> None:
    reply, _config, _service_ = await _run(config_file, f"/add_admin {SUPER}", SUPER)

    assert "超级管理员" in reply
    assert read_sub_admin_accounts(config_file) == ()


# ---------------------------------------------------------------------------
# 失败路径：绝不谎报成功
# ---------------------------------------------------------------------------


async def test_write_failure_is_reported_as_error(config_file: Path, monkeypatch) -> None:
    from neobot_app.config import chat_writer

    def _boom(*args, **kwargs):
        raise OSError("只读文件系统")

    monkeypatch.setattr(chat_writer, "_atomic_write", _boom)

    reply, _config, _service_ = await _run(config_file, "/add_admin 30003", SUPER)

    assert reply.startswith("错误")
    assert "写入配置失败" in reply
    assert read_sub_admin_accounts(config_file) == ()


async def test_silent_write_is_detected_and_reported(config_file: Path, monkeypatch) -> None:
    """回读不到写入内容时必须报错（旧实现会回复"已添加"）。"""
    from neobot_app.config import chat_writer

    monkeypatch.setattr(chat_writer, "read_chat_values", lambda *args, **kwargs: {})

    reply, _config, _service_ = await _run(config_file, "/add_admin 30003", SUPER)

    assert reply.startswith("错误")
    assert "回读不一致" in reply


async def test_missing_callback_reports_error(config_file: Path) -> None:
    config = ConfigProxy(
        dict_to_dataclass(
            tomlkit.parse(config_file.read_text(encoding="utf-8")).unwrap(), BotConfig
        )
    )
    adapter = _Adapter()
    service = CommandService(config=config, adapter=adapter)

    await service.handle_message(
        _message("/add_admin 30003", SUPER), kind="private", queue_key="1"
    )

    assert "配置保存能力未注入" in (adapter.sent[-1] if adapter.sent else "")


async def test_missing_chat_section_is_created(config_file: Path) -> None:
    """回归用例：[chat] 段不存在时也必须真的写进去。"""
    config_file.write_text(
        'version = "0.6.0"\n\n[bot]\naccount = 88888\nnick_name = "bot"\n',
        encoding="utf-8",
    )
    config = dict_to_dataclass(
        tomlkit.parse(config_file.read_text(encoding="utf-8")).unwrap(), BotConfig
    )
    config.chat.admin_accounts = [str(SUPER)]
    proxy = ConfigProxy(config)
    adapter = _Adapter()
    service = _commands.build_command_service(
        config=proxy, adapter=adapter, logger_factory=_LoggerFactory()
    )

    await service.handle_message(
        _message("/add_admin 30003", SUPER), kind="private", queue_key="1"
    )

    assert "已添加次级管理员" in (adapter.sent[-1] if adapter.sent else "")
    assert read_sub_admin_accounts(config_file) == ("30003",)


# ---------------------------------------------------------------------------
# 同一类问题的另一个回调
# ---------------------------------------------------------------------------


async def test_chat_update_callback_creates_missing_section(
    config_file: Path, monkeypatch
) -> None:
    config_file.write_text('version = "0.6.0"\n\n[bot]\naccount = 88888\n', encoding="utf-8")
    config = ConfigProxy(
        dict_to_dataclass(
            tomlkit.parse(config_file.read_text(encoding="utf-8")).unwrap(), BotConfig
        )
    )
    callback = _commands._make_chat_config_update_callback(config)

    result = await callback("willing_global_coefficient", 0.35)

    assert result == "ok"
    parsed = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    assert parsed["chat"]["willing_global_coefficient"] == 0.35


async def test_chat_update_callback_rejects_unknown_key(config_file: Path) -> None:
    config = ConfigProxy(
        dict_to_dataclass(
            tomlkit.parse(config_file.read_text(encoding="utf-8")).unwrap(), BotConfig
        )
    )
    callback = _commands._make_chat_config_update_callback(config)

    result = await callback("admin_accounts", ["1"])

    assert result.startswith("错误")
    assert "不允许更新配置键" in result
