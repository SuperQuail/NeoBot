"""组合根各阶段共享的装配状态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _BuildState:
    """create_application 分阶段构建时传递的服务实例（字段按阶段填充）。"""

    _engine: Any = None
    adapter: Any = None
    agent_registry: Any = None
    archive_summary_service: Any = None
    asr_service: Any = None
    avatar_store: Any = None
    balance_checker: Any = None
    bili_runtime: Any = None
    browser: Any = None
    cache_calculator: Any = None
    chat_flow_registry: Any = None
    command_service: Any = None
    config: Any = None
    context_recorder: Any = None
    creator_image_service: Any = None
    credential_manager: Any = None
    debug_recorder: Any = None
    drawing_manager: Any = None
    emoji_service: Any = None
    file_server: Any = None
    friend_queue: Any = None
    group_queue: Any = None
    hot_reload_registry: Any = None
    image_parse_service: Any = None
    image_pool: Any = None
    log_file_path: Any = None
    logger_factory: Any = None
    maintenance_coros: Any = None
    markdown_image_converter: Any = None
    markdown_skill_registry: Any = None
    memory_svcs: Any = None
    notification_hub: Any = None
    plugin: Any = None
    problem_solver_manager: Any = None
    prompt_analyzer: Any = None
    prompt_store: Any = None
    provider: Any = None
    provider_error_message: Any = None
    provider_logger: Any = None
    reply_orchestrator: Any = None
    sandbox: Any = None
    scheduled_task_manager: Any = None
    self_heal_manager: Any = None
    skill_manager: Any = None
    sleep_service: Any = None
    source_roots: Any = None
    standby_service: Any = None
    tts_service: Any = None
    uow_factory: Any = None
    usage: Any = None
    vision_detect_service: Any = None
    vision_provider: Any = None
