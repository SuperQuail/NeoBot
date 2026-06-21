"""运行时组件创建（绘图、定时任务、解题、沙箱、浏览器、插件等）"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.config.schemas.env import EnvConfig
from neobot_app.core import DATA_DIR
from neobot_app.image_pool import ImageStagingPool
from neobot_app.runtime.notifications import BackgroundNotificationHub
from neobot_app.runtime.scheduled_tasks import ScheduledTaskConfig, ScheduledTaskManager
from neobot_app.runtime.sandbox_lock import SandboxLock
from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.runtime.sandbox_maintenance import SandboxMaintenanceManager
from neobot_app.runtime.browser_lifecycle import BrowserLifecycleManager
from neobot_app.runtime.temp_cleaner import TempCleaner
from neobot_app.statistics.balance import BalanceChecker


def _auto_install_chromium() -> bool:
    """尝试通过 Playwright 自动下载 Chromium。"""
    from neobot_app.observability.logging import LoguruLoggerFactory

    logger = LoguruLoggerFactory().get_logger("app.bootstrap")
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_dir
        import subprocess

        driver_path = get_driver_dir()
        driver_exe = compute_driver_executable()
        cli = Path(driver_path) / driver_exe
        logger.info("未检测到浏览器，正在自动下载 Chromium（约 150MB）…")
        result = subprocess.run(
            [str(cli), "install", "chromium"],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        if result.returncode == 0:
            logger.info("Chromium 自动下载完成")
            return True
        logger.warning(f"Chromium 自动下载失败: {result.stderr.strip()}")
        return False
    except ImportError:
        logger.info(
            "playwright 未安装，跳过自动下载。"
            "如需浏览器功能请: pip install playwright && playwright install chromium"
        )
        return False
    except Exception as exc:
        logger.warning(f"Chromium 自动下载异常: {exc}")
        return False


def build_notification_hub(*, logger_factory: Any) -> BackgroundNotificationHub:
    return BackgroundNotificationHub(
        logger=logger_factory.get_logger("app.background_notifications"),
    )


def build_image_pool() -> ImageStagingPool:
    return ImageStagingPool(ttl_seconds=300)


def build_drawing_manager(
    *,
    config: BotConfigSchema,
    logger_factory: Any,
    notification_hub: BackgroundNotificationHub,
) -> Any:
    from neobot_app.drawing import BackgroundDrawingManager, DrawServiceConfig

    creator_config = DrawServiceConfig.from_schema(config.agent.creator)
    return BackgroundDrawingManager(
        config=creator_config,
        logger=logger_factory.get_logger("app.drawing"),
        notification_hub=notification_hub,
    )


def build_scheduled_task_manager(
    *,
    config: BotConfigSchema,
    uow_factory: Any,
    logger_factory: Any,
    notification_hub: BackgroundNotificationHub,
) -> Any:
    scheduled_task_config = ScheduledTaskConfig.from_schema(config.scheduled_task)
    if not scheduled_task_config.enabled:
        return None
    return ScheduledTaskManager(
        uow_factory=uow_factory,
        config=scheduled_task_config,
        logger=logger_factory.get_logger("app.scheduled_task"),
        notification_hub=notification_hub,
    )


def build_problem_solver_manager(
    *,
    config: BotConfigSchema,
    logger_factory: Any,
    notification_hub: BackgroundNotificationHub,
) -> Any:
    from neobot_app.agents.problem_solver import (
        ProblemSolverManager,
        ProblemSolverAgentConfig,
    )

    problem_solver_config = ProblemSolverAgentConfig.from_schema(
        getattr(config.agent, "problem_solver", None)
    )
    if not problem_solver_config.enabled:
        return None
    return ProblemSolverManager(
        config=problem_solver_config,
        logger=logger_factory.get_logger("app.problem_solver"),
        notification_hub=notification_hub,
    )


def build_browser_components(
    *,
    config: BotConfigSchema,
    data_dir: Path,
    logger: Any,
) -> dict[str, Any]:
    """创建浏览器实例和生命周期管理器。"""
    browser_cfg = getattr(config.agent, "browser", None)
    result: dict[str, Any] = {
        "browser_instance": None,
        "browser_lifecycle_manager": None,
    }

    if not browser_cfg or not browser_cfg.enabled:
        return result

    from neobot_app.browser.agent_browser.manager import _find_chrome_binary
    from neobot_app.browser import BrowserAgentWrapper

    if not _find_chrome_binary():
        _auto_install_chromium()

    if not _find_chrome_binary():
        logger.warning("浏览器已启用但未能找到或下载 Chromium，浏览器功能不可用")
        return result

    idle_timeout = int(getattr(browser_cfg, "auto_close_idle_seconds", 600)) // 60
    lifecycle_manager = BrowserLifecycleManager(
        idle_timeout_minutes=max(idle_timeout, 1),
        hold_max_minutes=browser_cfg.hold_max_minutes,
    )
    browser_instance = BrowserAgentWrapper(
        data_dir=data_dir / "browser",
        headless=getattr(browser_cfg, "headless", True),
        port=getattr(browser_cfg, "port", 0),
        browser_path=getattr(browser_cfg, "browser_path", ""),
        lifecycle_manager=lifecycle_manager,
    )
    lifecycle_manager.set_browser_instance(browser_instance)

    async def _close_flow_tabs(chat_flow_id: str, tab_ids: set) -> None:
        if browser_instance is None:
            return
        tabs_result = await browser_instance.list_tabs()
        if isinstance(tabs_result, list):
            tabs = tabs_result
        elif isinstance(tabs_result, dict):
            tabs = tabs_result.get("tabs", [])
        else:
            return
        id_to_index = {t["tab_id"]: t["index"] for t in tabs if "tab_id" in t and "index" in t}
        indices = sorted(
            (id_to_index[tid] for tid in tab_ids if tid in id_to_index),
            reverse=True,
        )
        for idx in indices:
            try:
                await browser_instance.close_tab(idx)
            except Exception:
                pass

    lifecycle_manager.set_close_callback(_close_flow_tabs)
    result["browser_instance"] = browser_instance
    result["browser_lifecycle_manager"] = lifecycle_manager
    return result


def build_markdown_image_converter(
    *,
    data_dir: Path,
    browser_instance: Any,
    logger_factory: Any,
) -> Any:
    from neobot_app.reply.markdown_image import MarkdownImageConverter

    return MarkdownImageConverter(
        output_dir=data_dir / "markdown_images",
        browser_instance=browser_instance,
        logger=logger_factory.get_logger("app.markdown_image"),
    )


def build_sandbox_components(
    *,
    config: BotConfigSchema,
    data_dir: Path,
) -> dict[str, Any]:
    """创建沙箱、临时清理、维护管理器。"""
    sandbox_cfg = getattr(config.agent, "sandbox", None)
    result: dict[str, Any] = {
        "sandbox_lock": SandboxLock(),
        "sandbox_service": None,
        "temp_cleaner": None,
        "sandbox_maintenance_manager": None,
    }

    if not sandbox_cfg or not sandbox_cfg.enabled:
        return result

    result["sandbox_service"] = SandboxService(
        sandbox_root=data_dir / "sandbox",
        lock=result["sandbox_lock"],
        allowed_read_dirs=[
            data_dir / "emoji",
            data_dir / "creator" / "gallery",
        ],
        max_total_size_bytes=sandbox_cfg.max_total_size_bytes,
    )
    result["temp_cleaner"] = TempCleaner(
        temp_dir=data_dir / "sandbox" / "temp",
        max_age_seconds=sandbox_cfg.temp_max_age_seconds,
        logger=None,  # injected below
    )
    result["sandbox_maintenance_manager"] = SandboxMaintenanceManager(
        sandbox_root=data_dir / "sandbox",
        enabled=(
            sandbox_cfg.maintenance.enabled
            if sandbox_cfg else True
        ),
        sandbox_service=result["sandbox_service"],
        logger=None,  # injected below
    )
    return result


def build_creator_image_service(
    *,
    uow_factory: Any,
    adapter: Any,
    config: BotConfigSchema,
    emoji_service: Any,
    vision_provider: Any,
    file_server: Any,
    image_pool: ImageStagingPool,
    logger_factory: Any,
) -> Any:
    from neobot_app.drawing import DrawServiceConfig, CreatorImageService

    creator_config = DrawServiceConfig.from_schema(config.agent.creator)
    return CreatorImageService(
        uow_factory=uow_factory,
        adapter=adapter,
        config=creator_config,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        image_pool=image_pool,
        logger=logger_factory.get_logger("app.creator_image"),
    )


def build_balance_checker(
    *,
    config: BotConfigSchema,
    notification_hub: BackgroundNotificationHub,
    logger_factory: Any,
) -> Any:
    chat_cfg = config.chat
    if not getattr(chat_cfg, "enable_balance_check", False):
        return None

    primary_provider = getattr(
        getattr(config.models, "primary_chat_model", None), "provider", ""
    )
    if primary_provider.strip().casefold() not in {"deepseek", "deepseek_offical", "deepseek_official"}:
        logger_factory.get_logger("app.provider").info("主模型非 DeepSeek，余额检查自动禁用")
        return None

    ds_config = EnvConfig.get_api_platform_config("DeepSeek")
    if not ds_config.api_key or not getattr(chat_cfg, "admin_accounts", None):
        logger_factory.get_logger("app.provider").warning(
            "余额检查已启用但缺少 DeepSeek API Key 或管理员账户，自动禁用"
        )
        return None

    logger_factory.get_logger("app.provider").info("余额检查已启用")
    return BalanceChecker(
        api_key=ds_config.api_key,
        base_url=ds_config.url or "https://api.deepseek.com",
        notification_hub=notification_hub,
        admin_accounts=list(chat_cfg.admin_accounts),
        balance_threshold=getattr(chat_cfg, "balance_threshold", 1.0),
        cooldown_seconds=getattr(chat_cfg, "balance_check_cooldown_seconds", 300),
        logger=logger_factory.get_logger("app.balance"),
    )
