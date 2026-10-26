"""Composition root — 装配并返回 NeoBotApplication。"""

from __future__ import annotations

import asyncio as asyncio
import inspect as inspect
import os as os
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import datetime as datetime, timezone as timezone
from pathlib import Path as Path
from typing import Any as Any
from neobot_contracts.ports.clock import SystemClock as SystemClock
from neobot_storage import backup_sqlite_database as backup_sqlite_database, run_migrations as run_migrations, sqlite_url as sqlite_url
from neobot_app.assembly.storage import build_storage as build_storage
from neobot_app.bootstrap._commands import _make_chat_config_update_callback as _make_chat_config_update_callback, build_command_service as build_command_service, build_credential_manager as build_credential_manager
from neobot_app.bootstrap._config import build_config as build_config
from neobot_app.bootstrap._pipeline import build_pipelines_and_app as build_pipelines_and_app, build_plugin_host as build_plugin_host, build_problem_solver_agent_wiring as build_problem_solver_agent_wiring, build_reply_orchestrator as build_reply_orchestrator, register_config_reload_command as register_config_reload_command, register_host_services as register_host_services
from neobot_app.bootstrap._providers import build_main_provider as build_main_provider, build_vision_provider as build_vision_provider, resolve_vision_model_name as resolve_vision_model_name
from neobot_app.bootstrap._runtime import build_balance_checker as build_balance_checker, build_browser_components as build_browser_components, build_creator_image_service as build_creator_image_service, build_drawing_manager as build_drawing_manager, build_image_pool as build_image_pool, build_markdown_image_converter as build_markdown_image_converter, build_notification_hub as build_notification_hub, build_problem_solver_manager as build_problem_solver_manager, build_sandbox_components as build_sandbox_components, build_scheduled_task_manager as build_scheduled_task_manager, build_self_heal_agent_wiring as build_self_heal_agent_wiring, build_self_heal_manager as build_self_heal_manager
from neobot_app.bootstrap._services import build_adapter_service as build_adapter_service, build_archive_summary_service as build_archive_summary_service, build_context_recorder as build_context_recorder, build_debug_recorder as build_debug_recorder, build_emoji_service as build_emoji_service, build_file_server as build_file_server, build_image_parse_service as build_image_parse_service, build_memory_services as build_memory_services, build_message_queues as build_message_queues, build_tts_service as build_tts_service, build_vision_detect_service as build_vision_detect_service
from neobot_app.bootstrap._skills import build_plugin_runtime as build_plugin_runtime, build_skill_manager as build_skill_manager
from neobot_app.bootstrap._usage import build_usage_components as build_usage_components
from neobot_app.core import DATA_DIR as DATA_DIR, SRC_DATA_DIR as SRC_DATA_DIR
from neobot_app.core.paths import _get_project_root as _get_project_root
from neobot_app.observability.logging import LoguruLoggerFactory as LoguruLoggerFactory, configure_loguru as configure_loguru, register_self_heal_manager as register_self_heal_manager
from neobot_app.prompt.store import PromptStore as PromptStore, sync_default_prompts as sync_default_prompts
from neobot_app.runtime.adapter_supervisor import AdapterSupervisor as AdapterSupervisor
from neobot_app.runtime.application import NeoBotApplication as NeoBotApplication
from neobot_app.runtime.hot_reload_registry import HotReloadRegistry as HotReloadRegistry
from neobot_app.runtime.process_restart import ProcessRestartSignal as ProcessRestartSignal
from neobot_app.runtime.process_stop import ProcessStopSignal as ProcessStopSignal
from neobot_app.runtime.provider_reload import ModelConsumerReload as ModelConsumerReload, ProviderReloadConsumer as ProviderReloadConsumer
from neobot_app.skills.balance_guide import sync_balance_query_skill as sync_balance_query_skill
from neobot_app.utils.data_sync import sync_data_files as sync_data_files
from neobot_app.bootstrap.parts.application import (
    create_application as create_application,
)
from neobot_app.bootstrap.parts.core_reuse import (
    _CORE_CACHE as _CORE_CACHE,
    _REUSE_ENABLED as _REUSE_ENABLED,
    _build_storage as _build_storage,
    _load_config_for_reuse as _load_config_for_reuse,
    _load_config_or_defaults as _load_config_or_defaults,
    _register_flow_task_providers as _register_flow_task_providers,
    _reuse_or as _reuse_or,
    _run_once as _run_once,
    config_load_error as config_load_error,
    disable_core_reuse as disable_core_reuse,
    enable_core_reuse as enable_core_reuse,
    get_cached_core as get_cached_core,
)
from neobot_app.bootstrap.parts.maintenance_agent import (
    _make_maintenance_coro as _make_maintenance_coro,
)
from neobot_app.bootstrap.parts.maintenance_schedule import (
    DEFAULT_MAINTENANCE_INTERVAL_SECONDS as DEFAULT_MAINTENANCE_INTERVAL_SECONDS,
    MAINTENANCE_RESIDENT_SKILLS as MAINTENANCE_RESIDENT_SKILLS,
    MaintenancePlan as MaintenancePlan,
    _MAINTENANCE_RETRY_STATUSES as _MAINTENANCE_RETRY_STATUSES,
    plan_maintenance_run as plan_maintenance_run,
)
from neobot_app.bootstrap.parts.maintenance_services import (
    _build_provider_reload_consumer as _build_provider_reload_consumer,
    _register_billing_hot_reload_rule as _register_billing_hot_reload_rule,
    _warmup_billing_scripts as _warmup_billing_scripts,
    _web_search_config_dict as _web_search_config_dict,
)

#: 配置加载失败的原因（缺失必需项 / config.toml 解析失败）。非空表示「启动即待机」，
#: 让面板先起来、用户就地修配置，改完点「软重启运行」即可，不必重启进程。
#: 变量定义在门面上是有意为之：测试会 monkeypatch neobot_app.bootstrap._CONFIG_ERROR，
#: 配置加载逻辑在 parts/core_reuse.py 中经门面读取/写回，保证补丁生效。
_CONFIG_ERROR = ""
