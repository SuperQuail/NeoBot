"""Skill 模块注册工厂。"""

from __future__ import annotations

from typing import Any

from neobot_app.skills.base import SkillManager
from neobot_app.skills.archive_crud import ArchiveCRUDSkill
from neobot_app.skills.user_profile import UserProfileSkill
from neobot_app.skills.favorability import FavorabilitySkill
from neobot_app.skills.chat_history import ChatHistorySkill
from neobot_app.skills.group_management import GroupManagementSkill
from neobot_app.skills.friend_management import FriendManagementSkill
from neobot_app.skills.forward_message import ForwardMessageSkill
from neobot_app.skills.sticker_skill import StickerSkill
from neobot_app.skills.drawing_skill import DrawingSkill
from neobot_app.skills.gallery_skill import GallerySkill
from neobot_app.skills.emoji_management import EmojiManagementSkill
from neobot_app.skills.image_send import ImageSendSkill
from neobot_app.skills.image_parse_skill import ImageParseSkill
from neobot_app.skills.willingness_skill import WillingnessSkill
from neobot_app.skills.reminder_skill import ReminderSkill
from neobot_app.skills.birthday_skill import BirthdaySkill
from neobot_app.skills.cross_chat_skill import CrossChatSkill
from neobot_app.skills.background_trigger import BackgroundTriggerSkill
from neobot_app.skills.adaptive_prompt_skill import AdaptivePromptSkill
from neobot_app.skills.file_storage_skill import FileStorageSkill
from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill
from neobot_app.skills.sandbox_maintenance_skill import SandboxMaintenanceSkill
from neobot_app.skills.gift_skill import GiftSkill
from neobot_app.skills.browser_skill import BrowserSkill
from neobot_app.skills.browser_network_skill import BrowserNetworkSkill
from neobot_app.skills.browser_video_skill import BrowserVideoSkill


def build_all_skills(
    *,
    disabled_skills: list[str] | None = None,
    config: Any = None,
    adapter: Any = None,
    archive_memory_service: Any = None,
    profile_service: Any = None,
    uow_factory: Any = None,
    emoji_service: Any = None,
    vision_provider: Any = None,
    file_server: Any = None,
    willing_service: Any = None,
    drawing_manager: Any = None,
    scheduled_task_manager: Any = None,
    notification_hub: Any = None,
    markdown_image_converter: Any = None,
    creator_image_service: Any = None,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    background_agent_manager: Any = None,
    sandbox_service: Any = None,
    sandbox_lock: Any = None,
    browser_instance: Any = None,
    browser_lifecycle_manager: Any = None,
    problem_solver_manager: Any = None,
    sandbox_maintenance_manager: Any = None,
    **kwargs: Any,
) -> SkillManager:
    """创建 SkillManager 并注册所有可用的 Skill。

    Args:
        disabled_skills: 黑名单列表，指定不注册的 skill 名称。
                        空列表或 None 表示全部注册。
        其他参数: 各 skill 所需的依赖注入。
    """
    mgr = SkillManager()
    disabled = set(disabled_skills or [])

    skills_to_register: list[Any] = []

    if "archive_crud" not in disabled:
        skills_to_register.append(
            ArchiveCRUDSkill(
                archive_service=archive_memory_service,
                allow_delete=(config.agent.archive.allow_delete if config and hasattr(config.agent, "archive") else False),
                allowed_tables=(config.agent.archive.allowed_tables if config and hasattr(config.agent, "archive") else ()),
            )
        )

    # ── 自适应提示词（agent 永久记忆） ──
    if "adaptive_prompt" not in disabled:
        skills_to_register.append(
            AdaptivePromptSkill(
                data_dir=kwargs.get("data_dir"),
                max_chars=(
                    config.agent.memory.adaptive_prompt_max_chars
                    if config and hasattr(config.agent, "memory")
                    else 200
                ),
                enabled=(
                    config.agent.memory.adaptive_prompt_enabled
                    if config and hasattr(config.agent, "memory")
                    else True
                ),
            )
        )

    if "user_profile" not in disabled:
        skills_to_register.append(
            UserProfileSkill(
                profile_service=profile_service,
                adapter=adapter,
                image_parse_provider=vision_provider,
            )
        )

    if "favorability" not in disabled:
        skills_to_register.append(
            FavorabilitySkill(
                profile_service=profile_service,
                max_change=getattr(config.agent.memory, "favorability_max_change", 5) if config and hasattr(config.agent, "memory") else 5,
                min_value=getattr(config.agent.memory, "favorability_min", -1000) if config and hasattr(config.agent, "memory") else -1000,
                max_value=getattr(config.agent.memory, "favorability_max", 1000) if config and hasattr(config.agent, "memory") else 1000,
            )
        )

    if "chat_history" not in disabled:
        skills_to_register.append(ChatHistorySkill(adapter=adapter))

    if "group_management" not in disabled:
        skills_to_register.append(GroupManagementSkill(adapter=adapter))

    if "friend_management" not in disabled:
        skills_to_register.append(FriendManagementSkill(adapter=adapter))

    if "forward_message" not in disabled:
        skills_to_register.append(
            ForwardMessageSkill(
                adapter=adapter,
                display_threshold=50,
                max_nesting=10,
            )
        )

    if "sticker" not in disabled:
        skills_to_register.append(StickerSkill(emoji_service=emoji_service, file_server=file_server))

    if "drawing" not in disabled:
        skills_to_register.append(DrawingSkill(drawing_manager=drawing_manager))

    if "gallery" not in disabled:
        skills_to_register.append(
            GallerySkill(
                creator_image_service=creator_image_service,
                uow_factory=uow_factory,
                vision_provider=vision_provider,
                file_server=file_server,
                adapter=adapter,
            )
        )

    if "emoji_management" not in disabled:
        skills_to_register.append(EmojiManagementSkill(emoji_service=emoji_service))

    if "image_send" not in disabled:
        skills_to_register.append(ImageSendSkill(adapter=adapter, file_server=file_server))

    if "image_parse" not in disabled:
        skills_to_register.append(
            ImageParseSkill(
                vision_provider=vision_provider,
                adapter=adapter,
                group_message_queue=group_message_queue,
                friend_message_queue=friend_message_queue,
            )
        )

    if "willingness" not in disabled:
        skills_to_register.append(WillingnessSkill(willing_service=willing_service))

    if "reminder" not in disabled:
        skills_to_register.append(
            ReminderSkill(uow_factory=uow_factory, config=config)
        )

    if "birthday" not in disabled:
        skills_to_register.append(BirthdaySkill(uow_factory=uow_factory))

    if "cross_chat" not in disabled:
        skills_to_register.append(
            CrossChatSkill(
                config=config,
                adapter=adapter,
                group_message_queue=group_message_queue,
                friend_message_queue=friend_message_queue,
            )
        )

    if "background_trigger" not in disabled:
        skills_to_register.append(
            BackgroundTriggerSkill(manager=problem_solver_manager, config=config)
        )

    # ── Phase 3: 文件存储管理（持久化文件索引和 TODO） ──
    if "file_storage" not in disabled and sandbox_service is not None:
        skills_to_register.append(
            FileStorageSkill(sandbox_service=sandbox_service)
        )

    # ── Phase 3: 沙箱维护管理 ──
    if "sandbox_maintenance" not in disabled and sandbox_maintenance_manager is not None:
        skills_to_register.append(
            SandboxMaintenanceSkill(maintenance_manager=sandbox_maintenance_manager)
        )

    # ── Phase 3: 礼物管理 ──
    if "gift" not in disabled and sandbox_service is not None:
        skills_to_register.append(
            GiftSkill(
                sandbox_service=sandbox_service,
                scheduled_task_manager=scheduled_task_manager,
                notification_hub=notification_hub,
            )
        )

    # ── Phase 3: 沙箱管理器 ──
    if "sandbox_manager" not in disabled and sandbox_service is not None:
        skills_to_register.append(
            SandboxManagerSkill(
                sandbox_service=sandbox_service,
                sandbox_lock=sandbox_lock,
                adapter=adapter,
                file_server=file_server,
                hold_max_minutes=(
                    config.agent.sandbox.temp_hold_max_minutes
                    if config and hasattr(config.agent, "sandbox")
                    else 120
                ),
            )
        )

    # ── Phase 3: 浏览器 Skills（browser_instance 为 None 时不注册） ──
    if "browser" not in disabled and browser_instance is not None:
        skills_to_register.append(
            BrowserSkill(
                browser_instance=browser_instance,
                lifecycle_manager=browser_lifecycle_manager,
                sandbox_service=sandbox_service,
            )
        )
    if "browser_network" not in disabled and browser_instance is not None:
        skills_to_register.append(
            BrowserNetworkSkill(browser_instance=browser_instance)
        )
    if "browser_video" not in disabled and browser_instance is not None:
        skills_to_register.append(
            BrowserVideoSkill(
                browser_instance=browser_instance,
                sandbox_service=sandbox_service,
            )
        )

    for skill in skills_to_register:
        mgr.register(skill)

    return mgr
