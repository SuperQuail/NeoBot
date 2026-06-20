"""Skill 系统与插件运行时创建"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_modloader import PluginRuntime

from neobot_app.core import DATA_DIR
from neobot_app.skills import build_all_skills


def build_skill_manager(
    *,
    config: Any,
    adapter: Any,
    archive_memory_service: Any,
    profile_service: Any,
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
    browser_instance: Any,
    browser_lifecycle_manager: Any,
    problem_solver_manager: Any,
    image_pool: Any,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    data_dir: Path = Path("."),
) -> Any:
    return build_all_skills(
        disabled_skills=getattr(
            getattr(config.agent, "skill", None), "disabled_skills", None
        ),
        config=config,
        adapter=adapter,
        archive_memory_service=archive_memory_service,
        profile_service=profile_service,
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
        browser_instance=browser_instance,
        browser_lifecycle_manager=browser_lifecycle_manager,
        problem_solver_manager=problem_solver_manager,
        image_pool=image_pool,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        data_dir=data_dir,
    )


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
) -> Any:
    if not config.plugins.enabled:
        return None

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
        auto_install_dependencies=True,
    )
    plugin_runtime.load_all()
    return plugin_runtime
