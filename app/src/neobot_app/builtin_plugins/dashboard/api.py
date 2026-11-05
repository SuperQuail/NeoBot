"""网页面板 HTTP 接口实现。

所有写操作都经过 _require_manage 校验（manage_plugins / allow_remote_manage），
所有响应都只暴露必要信息，密钥类字段默认打码。

handler 按域拆在 api_parts；本模块只保留 DashboardApi 聚合类，
并 re-export 原有的模块级辅助函数与常量，保持既有导入路径不变。
"""

from __future__ import annotations

from .api_parts.base import DashboardApiBase
from .api_parts.auth import AuthMixin
from .api_parts.overview import OverviewMixin
from .api_parts.stats import StatsMixin
from .api_parts.system import SystemMixin
from .api_parts.plugins import PluginsMixin
from .api_parts.plugin_surface import PluginSurfaceMixin
from .api_parts.plugin_views import PluginViewsMixin
from .api_parts.config import ConfigMixin
from .api_parts.deploy import DeployMixin
from .api_parts.models import ModelsMixin
from .api_parts.prompts import PromptsMixin
from .api_parts.chat_flows import ChatFlowsMixin
from .api_parts.archives import ArchivesMixin
from .api_parts.archive_summary import ArchiveSummaryMixin
from .api_parts.admin import AdminMixin

from .api_parts._common import (
    _pydantic_errors,
    _as_text,
    _append_model_reload_hint,
    _deploy_field_defaults,
    _detect_lan_host,
    _json_ok,
    _json_error,
    ENV_RESTART_HINT,
    _env_reload_message,
    _parse_cost_detail,
    _redact_prompt_report,
    _SCHEDULED_ACTION_MESSAGES,
    _prompt_value,
    _status_text,
    installed_name,
    _operation_response,
)

__all__ = [
    "DashboardApi",
    "_pydantic_errors",
    "_as_text",
    "_append_model_reload_hint",
    "_deploy_field_defaults",
    "_detect_lan_host",
    "_json_ok",
    "_json_error",
    "ENV_RESTART_HINT",
    "_env_reload_message",
    "_parse_cost_detail",
    "_redact_prompt_report",
    "_SCHEDULED_ACTION_MESSAGES",
    "_prompt_value",
    "_status_text",
    "installed_name",
    "_operation_response",
]


class DashboardApi(
    AuthMixin,
    OverviewMixin,
    StatsMixin,
    SystemMixin,
    PluginsMixin,
    PluginSurfaceMixin,
    PluginViewsMixin,
    ConfigMixin,
    DeployMixin,
    ModelsMixin,
    PromptsMixin,
    ChatFlowsMixin,
    ArchivesMixin,
    ArchiveSummaryMixin,
    AdminMixin,
    DashboardApiBase,
):
    """面板接口集合。"""
