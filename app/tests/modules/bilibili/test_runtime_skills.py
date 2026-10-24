"""B站 runtime 技能装配：搜索/视频/用户技能必须注册且工具名完整。"""

from __future__ import annotations

from neobot_app.bilibili.runtime import BilibiliRuntime, build_bilibili_skills
from neobot_app.commands.model import PERM_EVERYONE, PERM_SUPER_ADMIN
from neobot_app.commands.registry import CommandRegistry
from neobot_app.config.schemas.bot import BotConfig


class _FakeCommandService:
    def __init__(self) -> None:
        self.registry = CommandRegistry()

    async def reply_to(self, *args, **kwargs) -> None:
        pass

    async def send_image_bytes(self, *args, **kwargs) -> bool:
        return True


def test_bilibili_runtime_registers_search_video_user_skills():
    cfg = BotConfig()
    command_service = _FakeCommandService()
    runtime = BilibiliRuntime(
        config=cfg,
        provider=None,
        archive_service=None,
        uow_factory=None,
        command_service=command_service,
        asr_service=None,
        bot_name=cfg.bot.nick_name,
        bot_data=cfg.bot.bot_data,
    )
    skills = build_bilibili_skills(
        archive_service=None, uow_factory=None, runtime=runtime
    )
    names = {skill.name for skill in skills}
    assert {"bilibili_search", "bilibili_video", "bilibili_user"} <= names
    tool_names = {
        tool["function"]["name"] for skill in skills for tool in skill.get_tools()
    }
    assert {"search_video", "watch_video", "linked_qq_profile"} <= tool_names
    runtime.register_commands(command_service)
    login = command_service.registry.get("login")
    assert login is not None
    # 登录即拿到 B站账号全站写权限，只允许超级管理员换号。
    assert login.permission == PERM_SUPER_ADMIN
    account = command_service.registry.get("B站账号")
    assert account is not None
    assert account.permission == PERM_EVERYONE
    assert command_service.registry.get("biliaccount") is account
    assert command_service.registry.get("bili") is not None