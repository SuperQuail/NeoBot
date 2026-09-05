"""命令系统单元测试:解析 / 权限树 / 内置命令 / 热重载回调。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.builtin import _extract_target_qq
from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
    Command,
)
from neobot_app.commands.permissions import PermissionManager
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService

BOT = 88888
SUPER = 10000
SUB = 30000


def _config(*, admin_accounts: list[int] | None = None, sub_admin_accounts: list[int] | None = None):
    chat = SimpleNamespace(
        admin_accounts=list(admin_accounts if admin_accounts is not None else [SUPER]),
        sub_admin_accounts=list(sub_admin_accounts or []),
    )
    bot = SimpleNamespace(account=BOT)
    return SimpleNamespace(chat=chat, bot=bot)


def _text_message(text: str, *, user_id: int = 1, at_qqs: list[int] | None = None):
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs or []:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


def _service(config=None, **kwargs) -> CommandService:
    return CommandService(
        config=config if config is not None else _config(),
        adapter=SimpleNamespace(send=lambda conv, segments: None),
        register_builtins=kwargs.get("register_builtins", True),
    )


# ── 解析 ──


def test_match_command_with_leading_spaces() -> None:
    registry = CommandRegistry()
    registry.register(Command(name="help", description="帮助", handler=lambda ctx: "x"))
    # / 前允许任意空格
    command, raw, args = registry.match("   /help")
    assert command is not None and command.name == "help"
    # 命令名后参数
    command, raw, args = registry.match("  /help  123456  ")
    assert command is not None
    assert args == ["123456"]
    # 非命令形态:/ 前有字符
    assert registry.match("大家 /help") is None
    # / 开头但未注册
    command, raw, args = registry.match("/nope")
    assert command is None


def test_match_rejects_non_whitespace_before_slash() -> None:
    registry = CommandRegistry()
    registry.register(Command(name="help", description="h", handler=lambda c: "x"))
    assert registry.match("  /help") is not None
    assert registry.match("x/help") is None
    assert registry.match("/help extra") is not None


# ── 权限树 ──


def test_permission_levels() -> None:
    permissions = PermissionManager(
        _config(admin_accounts=[SUPER, 20000], sub_admin_accounts=[SUB])
    )
    assert permissions.is_super_admin(SUPER)
    assert permissions.is_super_admin(20000)
    assert not permissions.is_super_admin(SUB)
    assert permissions.is_sub_admin(SUB)
    assert permissions.is_sub_admin(SUPER)
    assert permissions.can(99999, PERM_EVERYONE)
    assert not permissions.can(99999, PERM_SUB_ADMIN)
    assert not permissions.can(SUB, PERM_SUPER_ADMIN)
    assert permissions.can(SUPER, PERM_SUPER_ADMIN)


# ── 触发与消费 ──


async def test_group_command_requires_at() -> None:
    service = _service()
    result = await service.handle_message(
        _text_message("/help", user_id=1), kind="group", queue_key="42"
    )
    assert result.consumed is False  # 未 @bot
    result = await service.handle_message(
        _text_message("/help", user_id=1, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    assert result.consumed is True


async def test_private_command_without_at() -> None:
    service = _service()
    result = await service.handle_message(
        _text_message("/help", user_id=1), kind="private", queue_key="1"
    )
    assert result.consumed is True


async def test_unknown_command_passes_through() -> None:
    service = _service()
    result = await service.handle_message(
        _text_message("/unknown_cmd", user_id=1, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is False  # 移交正常聊天管线


async def test_permission_denied_consumes_and_replies() -> None:
    sent: list[tuple] = []

    async def send(kind, conv, text, at_user_id):
        sent.append((kind, conv, text, at_user_id))

    service = CommandService(
        config=_config(),
        adapter=SimpleNamespace(send=lambda c, s: None),
        send_callback=send,
        register_builtins=True,
    )
    result = await service.handle_message(
        _text_message("/reboot", user_id=99999, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert sent and "没有权限" in sent[0][2]


# ── 内置命令:add_admin / del_admin ──


def _admin_service(save_result: str = "ok") -> tuple[CommandService, list[list[int]]]:
    saved: list[list[int]] = []

    async def save(new_list):
        saved.append(new_list)
        return save_result

    service = CommandService(
        config=_config(admin_accounts=[SUPER], sub_admin_accounts=[SUB]),
        adapter=SimpleNamespace(send=lambda c, s: None),
        config_save_callback=save,
        register_builtins=True,
    )
    return service, saved


async def test_add_admin_by_qq() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/add_admin 40000", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == [[SUB, 40000]]


async def test_add_admin_by_at() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/add_admin", user_id=SUPER, at_qqs=[BOT, 50000]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == [[SUB, 50000]]


async def test_add_admin_super_admin_protected() -> None:
    # 20000 是超级管理员(配置增减),命令不能修改
    saved2: list[list[int]] = []

    async def save(new_list):
        saved2.append(new_list)
        return "ok"

    service = CommandService(
        config=_config(admin_accounts=[SUPER, 20000], sub_admin_accounts=[SUB]),
        adapter=SimpleNamespace(send=lambda c, s: None),
        config_save_callback=save,
        register_builtins=True,
    )
    result = await service.handle_message(
        _text_message("/add_admin 20000", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved2 == []  # 超级管理员不能通过命令修改


async def test_add_admin_duplicate() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/add_admin 30000", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == []


async def test_del_admin() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/del_admin 30000", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == [[]]


async def test_del_admin_not_admin() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/del_admin 99999", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == []


async def test_add_admin_requires_super() -> None:
    service, saved = _admin_service()
    result = await service.handle_message(
        _text_message("/add_admin 40000", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert saved == []  # 次级管理员不能添加管理员


def test_extract_target_qq_prefers_at() -> None:
    service = _service(register_builtins=False)
    ctx = SimpleNamespace(service=service, at_qqs=[50000, 60000], args=["70000"])
    assert _extract_target_qq(ctx) == 50000
    ctx2 = SimpleNamespace(service=service, at_qqs=[], args=["@80000", "90000"])
    assert _extract_target_qq(ctx2) == 80000
    ctx3 = SimpleNamespace(service=service, at_qqs=[], args=["abc"])
    assert _extract_target_qq(ctx3) is None
    # 只有 @bot 时不应把 bot 当作目标
    ctx4 = SimpleNamespace(service=service, at_qqs=[BOT], args=[])
    assert _extract_target_qq(ctx4) is None


# ── sync_reply 语义 ──


async def test_sync_reply_returns_background() -> None:
    async def handler(ctx) -> str:
        return "执行结果"

    service = _service(register_builtins=False)
    service.registry.register(
        Command(name="sync_demo", description="同步回复", sync_reply=True, handler=handler)
    )
    result = await service.handle_message(
        _text_message("/sync_demo", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert result.background is not None
    assert "执行结果" in result.background


# ── 热重载:权限动态生效 ──


async def test_permissions_reflect_config_reload() -> None:
    config = _config(admin_accounts=[SUPER], sub_admin_accounts=[])
    service = _service(config=config)
    # 模拟热重载:配置对象替换为含次级管理员的新配置
    service._config = _config(admin_accounts=[SUPER], sub_admin_accounts=[40000])
    result = await service.handle_message(
        _text_message("/add_admin 50000", user_id=40000, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    # 40000 现在是次级管理员,但 add_admin 需要超级管理员权限 → 拒绝并消费
    assert result.consumed is True
