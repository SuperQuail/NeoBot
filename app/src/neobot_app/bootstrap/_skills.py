"""Skill 系统与插件运行时创建"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_modloader import PluginInstaller, PluginRuntime, PluginStateStore

from neobot_app.builtin_plugins import builtin_plugin_dirs
from neobot_app.core import DATA_DIR
from neobot_app.skills import build_all_skills

if TYPE_CHECKING:
    from neobot_contracts.ports.screenshot import ScreenshotPort


def build_skill_manager(
    *,
    config: Any,
    adapter: Any,
    archive_memory_service: Any,
    profile_service: Any,
    uow_factory: Any,
    emoji_service: Any,
    vision_provider: Any,
    file_server: Any,
    willing_service: Any,
    drawing_manager: Any,
    scheduled_task_manager: Any,
    notification_hub: Any,
    markdown_image_converter: Any,
    creator_image_service: Any,
    sandbox_lock: Any,
    sandbox_service: Any,
    sandbox_maintenance_manager: Any,
    temp_cleaner: Any = None,
    browser_instance: Any,
    browser_lifecycle_manager: Any,
    problem_solver_manager: Any,
    image_pool: Any,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    data_dir: Path = Path("."),
    balance_checker: Any = None,
    agent_registry: Any = None,
    vision_detect_service: Any = None,
    credential_manager: Any = None,
    sleep_service: Any = None,
    agent_provider: Any = None,
) -> Any:
    return build_all_skills(
        disabled_skills=getattr(
            getattr(config.agent, "skill", None), "disabled_skills", None
        ),
        config=config,
        adapter=adapter,
        archive_memory_service=archive_memory_service,
        profile_service=profile_service,
        uow_factory=uow_factory,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        willing_service=willing_service,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        creator_image_service=creator_image_service,
        sandbox_lock=sandbox_lock,
        sandbox_service=sandbox_service,
        sandbox_maintenance_manager=sandbox_maintenance_manager,
        temp_cleaner=temp_cleaner,
        browser_instance=browser_instance,
        browser_lifecycle_manager=browser_lifecycle_manager,
        problem_solver_manager=problem_solver_manager,
        image_pool=image_pool,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        data_dir=data_dir,
        balance_checker=balance_checker,
        agent_registry=agent_registry,
        vision_detect_service=vision_detect_service,
        credential_manager=credential_manager,
        sleep_service=sleep_service,
        agent_provider=agent_provider,
    )


#: 官方插件名 -> config.toml 分区名。官方插件配置直接来自本体配置。
OFFICIAL_CONFIG_SECTIONS: dict[str, str] = {"dashboard": "dashboard"}


def build_official_config_provider(config: Any) -> Any:
    """官方插件配置提供者：把本体配置分区转成插件可用的字典。"""
    from dataclasses import asdict, is_dataclass

    def provide(plugin_name: str) -> dict[str, Any] | None:
        section = OFFICIAL_CONFIG_SECTIONS.get(str(plugin_name))
        if section is None:
            return None
        target = getattr(config, section, None)
        if target is None:
            return None
        if is_dataclass(target) and not isinstance(target, type):
            return asdict(target)
        if isinstance(target, dict):
            return dict(target)
        return None

    return provide


def build_plugin_runtime(
    *,
    config: Any,
    adapter: Any,
    logger_factory: Any,
    hook_bus: Any,
    reply_block_registry: Any,
    runtime_output: Any,
    host_facade: Any,
    file_server: Any,
    agent_registry: Any,
    skills_registry: Any = None,
    screenshots: "ScreenshotPort | None" = None,
    command_registry: Any = None,
) -> Any:
    plugin_dir = Path(config.plugins.dir)
    if not plugin_dir.is_absolute():
        plugin_dir = DATA_DIR / plugin_dir

    from neobot_app.utils import media_sender as _media_sender_module

    class _MediaSenderWrapper:
        def __init__(self, fs: Any) -> None:
            self._fs = fs

        async def send_image(
            self,
            adapter: Any,
            conversation: Any,
            *,
            path: Path | None = None,
            data: bytes | None = None,
            filename: str | None = None,
        ) -> Any:
            if path is not None:
                return await _media_sender_module.send_image(
                    self._fs, adapter, conversation, path
                )
            if data is not None:
                raise NotImplementedError(
                    "send_image with raw data is handled by the plugin runtime context"
                )
            raise ValueError("Must provide path or data+filename")

        async def send_audio(
            self, adapter: Any, conversation: Any, *, path: Path
        ) -> Any:
            return await _media_sender_module.send_audio(
                self._fs, adapter, conversation, path
            )

        def prepare_image_segment(
            self, file_server: Any, file_path: Path
        ) -> dict:
            return _media_sender_module.prepare_image_segment(file_server, file_path)

        def prepare_audio_segment(
            self, file_server: Any, file_path: Path
        ) -> dict:
            return _media_sender_module.prepare_audio_segment(file_server, file_path)

    state_store = PluginStateStore(
        DATA_DIR / "plugin_state.json",
        logger=logger_factory.get_logger("modloader.state"),
    )
    installer = PluginInstaller(
        plugin_dir=plugin_dir,
        logger=logger_factory.get_logger("modloader.installer"),
    )
    plugin_runtime = PluginRuntime(
        plugin_dir=plugin_dir,
        data_dir=DATA_DIR / "plugins_data",
        adapter=adapter,
        logger_factory=logger_factory,
        hook_bus=hook_bus,
        record_ai_reply_block=reply_block_registry.block_event,
        output=runtime_output,
        host=host_facade,
        file_server=file_server,
        media_sender=_MediaSenderWrapper(file_server),
        agent_registry=agent_registry,
        skills_registry=skills_registry,
        screenshots=screenshots,
        app_commands=command_registry,
        auto_install_dependencies=True,
        builtin_plugin_dirs=builtin_plugin_dirs(),
        state_store=state_store,
        official_config_provider=build_official_config_provider(config),
        installer=installer,
        user_plugins_enabled=bool(getattr(config.plugins, "enabled", True)),
    )
    plugin_runtime.load_all()
    return plugin_runtime
