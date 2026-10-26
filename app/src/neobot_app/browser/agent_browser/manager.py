"""
agent-browser — AI 代理浏览器核心管理模块

基于 DrissionPage 的浏览器实例管理。
提供持久化会话、自动重连、有头/无头切换、跨平台兼容。

实现按职责拆到 ``manager_parts``；本模块保留原有模块级名称与
BrowserManager 的公开 API（薄门面 + re-export）。
"""
from __future__ import annotations

import asyncio
import base64
import glob as _glob
import json
import logging
import os
import platform
import shutil
import sys
import threading
import time
import weakref
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from neobot_contracts.ports.screenshot import (
    ScreenshotError,
    ScreenshotOptions,
    ScreenshotResult,
    ScreenshotTargetNotFound,
    validate_screenshot_options,
)

from ._compat import (
    ChromiumBase,
    ChromiumOptions,
    ChromiumPage,
    PageDisconnectedError,
    require_drissionpage,
)
from .manager_parts.lifecycle import LifecycleMixin
from .manager_parts.page_read import PageReadMixin
from .manager_parts.clicks import ClickMixin
from .manager_parts.forms import FormsMixin
from .manager_parts.elements import ElementQueryMixin
from .manager_parts.page_settings import PageSettingsMixin
from .manager_parts.capture import CaptureMixin
from .manager_parts.tabs import TabsMixin
from .manager_parts.cookies_network import CookiesNetworkMixin
from .manager_parts.storage import StorageMixin
from .manager_parts.state_console import StateConsoleMixin
from .manager_parts.process import (
    _INSTANCE_REGISTRY,
    _MAX_RETRIES,
    _REGISTRY_LOCK,
    _RETRY_INTERVAL,
    _WINDOWS,
    _find_chrome_binary,
    _has_other_live_instances,
    _logger,
    _playwright_chromium_path,
    _register_instance,
    _unregister_instance,
)


class BrowserManager(
    LifecycleMixin,
    PageReadMixin,
    ClickMixin,
    FormsMixin,
    ElementQueryMixin,
    PageSettingsMixin,
    CaptureMixin,
    TabsMixin,
    CookiesNetworkMixin,
    StorageMixin,
    StateConsoleMixin,
):
    """管理 DrissionPage 浏览器实例，提供持久化会话和自动重连。"""


__all__ = [
    "asyncio",
    "base64",
    "_glob",
    "json",
    "logging",
    "os",
    "platform",
    "shutil",
    "sys",
    "threading",
    "time",
    "weakref",
    "BytesIO",
    "Path",
    "Any",
    "Optional",
    "Image",
    "ScreenshotError",
    "ScreenshotOptions",
    "ScreenshotResult",
    "ScreenshotTargetNotFound",
    "validate_screenshot_options",
    "ChromiumBase",
    "ChromiumOptions",
    "ChromiumPage",
    "PageDisconnectedError",
    "require_drissionpage",
    "_INSTANCE_REGISTRY",
    "_MAX_RETRIES",
    "_REGISTRY_LOCK",
    "_RETRY_INTERVAL",
    "_WINDOWS",
    "_find_chrome_binary",
    "_has_other_live_instances",
    "_logger",
    "_playwright_chromium_path",
    "_register_instance",
    "_unregister_instance",
    "BrowserManager",
]
