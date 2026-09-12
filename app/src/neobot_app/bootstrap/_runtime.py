"""运行时组件创建（绘图、定时任务、解题、沙箱、浏览器、插件等）"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.config.schemas.env import EnvConfig
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
        import subprocess
        import sys

        __import__("playwright")

        logger.info("未检测到浏览器，正在自动下载 Chromium（约 150MB）…")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("Chromium 自动下载完成")
            return True
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
        logger.warning(f"Chromium 自动下载失败: {stderr_text}")
        return False
    except ImportError:
        logger.info(
            "playwright 未安装，跳过自动下载。"
            "如需浏览器功能请: pip install playwright && python -m playwright install chromium"
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
    """创建浏览器实例、生命周期管理器和公共截图 façade。

    返回的 "screenshots" 永不为 None：浏览器禁用或 Chromium 缺失时
    为 UnavailableScreenshots（调用 render/save 抛 ScreenshotUnavailable）。
    """
    from neobot_app.screenshot import ScreenshotService, UnavailableScreenshots

    browser_cfg = getattr(config.agent, "browser", None)
    result: dict[str, Any] = {
        "browser_instance": None,
        "browser_lifecycle_manager": None,
        "screenshots": UnavailableScreenshots(),
    }

    if not browser_cfg or not browser_cfg.enabled:
        return result

    from neobot_app.browser.agent_browser.manager import _find_chrome_binary
    from neobot_app.browser import BrowserAgentWrapper, BrowserScreenshotBackend

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
    result["screenshots"] = ScreenshotService(
        BrowserScreenshotBackend(browser_instance)
    )
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
    image_model_keys = list(getattr(config.models, "creator_image_model_names", []) or [])
    return CreatorImageService(
        uow_factory=uow_factory,
        adapter=adapter,
        config=creator_config,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        image_pool=image_pool,
        model_names=image_model_keys or None,
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

    assignments = getattr(getattr(config, "models", None), "assignments", None)
    primary_key = str(getattr(assignments, "primary_chat_model", "") or "").strip() if assignments else ""
    primary_definition = (
        config.models.get(primary_key) if primary_key and hasattr(config.models, "get") else None
    )
    if primary_definition is None:
        primary_definition = getattr(config.models, "primary_chat_model", None)
    primary_provider = getattr(primary_definition, "provider", "")
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


def build_self_heal_manager(
    *,
    config: BotConfigSchema,
    logger_factory: Any,
    notification_hub: BackgroundNotificationHub,
    sandbox_service: Any,
    drawing_manager: Any = None,
    creator_image_service: Any = None,
    data_dir: Path | None = None,
    source_roots: list[Path] | None = None,
    log_file: Path | None = None,
    web_search_config: dict | None = None,
    vision_provider: Any = None,
) -> Any:
    """创建 SelfHealManager。配置禁用时返回 None。"""
    from neobot_app.agents.self_heal import SelfHealAgentConfig, SelfHealManager

    schema_cfg = getattr(config.agent, "self_healing", None)
    if schema_cfg is None or not getattr(schema_cfg, "enabled", True):
        return None

    cfg = SelfHealAgentConfig.from_schema(schema_cfg)

    # admin fallback: chat.admin_accounts[0]
    fallback_admin = ""
    admin_accounts = list(getattr(config.chat, "admin_accounts", None) or [])
    if admin_accounts:
        fallback_admin = str(admin_accounts[0])

    repair_hooks: dict[str, Any] = {}
    if drawing_manager is not None and hasattr(drawing_manager, "cancel_cooldown"):
        repair_hooks["clear_drawing_cooldown"] = lambda args: (
            drawing_manager.cancel_cooldown(str(args.get("pipeline_key", "")))
        )
    if creator_image_service is not None and hasattr(
        creator_image_service, "_cleanup_stale_records"
    ):
        async def _hook_trigger_image_cleanup(_args: dict) -> dict:
            try:
                await creator_image_service._cleanup_stale_records()
                return {"ok": True, "result": "image cleanup triggered"}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        repair_hooks["trigger_image_cleanup"] = _hook_trigger_image_cleanup

    return SelfHealManager(
        config=cfg,
        fallback_admin_account=fallback_admin,
        logger=logger_factory.get_logger("app.self_heal"),
        notification_hub=notification_hub,
        sandbox_service=sandbox_service,
        data_dir=data_dir,
        source_roots=source_roots or [],
        log_file=log_file,
        repair_hooks=repair_hooks,
        web_search_config=web_search_config or {},
        vision_provider=vision_provider,
    )


def build_self_heal_agent_wiring(
    *,
    config: BotConfigSchema,
    manager: Any,
    provider: Any,
    provider_logger: Any,
    sandbox_service: Any,
    logger_factory: Any,
    data_dir: Path,
    source_roots: list[Path],
    log_file: Path | None,
    vision_provider: Any = None,
    web_search_config: dict | None = None,
    prompt_store: Any = None,
) -> Any:
    """构建 SelfHealAgent 并绑定到已创建的 Manager。

    provider 不可用（如主模型配置错误导致创建失败）时跳过装配并返回 None，
    自修复功能降级但不影响 Bot 启动。
    """
    if provider is None:
        logger_factory.get_logger("app.self_heal").warning(
            "self-heal agent 未启用：provider 不可用，跳过装配"
        )
        return None

    from neobot_app.agents.self_heal import (
        SelfHealAgentConfig,
        build_self_heal_agent,
    )
    from neobot_app.assembly.agents import build_peer_descriptions
    from neobot_app.bootstrap._providers import build_optional_agent_provider

    # 自修复走 agent_model.self_heal 指定的模型（默认 3：低成本非推理模型），而不是
    # 直接复用主回复 provider —— 复用会带来两个后果：配置的自修复模型编号被忽略，
    # 且 build_self_heal_agent 里的 provider.max_tokens 覆盖会写进共享实例
    # （原生视觉包装器不接受该赋值，启动即崩；真写进去则会压低主模型预算）。
    self_heal_provider = build_optional_agent_provider(
        config=config,
        agent_name="self_heal",
        fallback_provider=provider,
        logger=logger_factory.get_logger("app.provider"),
    )

    schema_cfg = getattr(config.agent, "self_healing", None)
    cfg = (
        SelfHealAgentConfig.from_schema(schema_cfg)
        if schema_cfg is not None
        else SelfHealAgentConfig()
    )
    peer_descriptions = build_peer_descriptions("self_heal")
    agent = build_self_heal_agent(
        self_heal_provider,
        config=cfg,
        logger=logger_factory.get_logger("app.self_heal"),
        manager=manager,
        sandbox_service=sandbox_service,
        data_dir=data_dir,
        source_roots=source_roots,
        log_file=log_file,
        repair_hooks=manager._repair_hooks if manager else None,
        web_search_config=web_search_config or {},
        vision_provider=vision_provider,
        peer_descriptions=peer_descriptions,
        prompt_store=prompt_store,
    )
    return agent
