"""核心对象复用（待机软重启）与配置容错加载。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from neobot_storage import backup_sqlite_database, run_migrations
from neobot_app.assembly.storage import build_storage
from neobot_app.core import DATA_DIR


def _facade() -> Any:
    """补丁点在门面模块上：测试会 monkeypatch neobot_app.bootstrap.build_config / _CONFIG_ERROR。"""
    from neobot_app import bootstrap

    return bootstrap


def _config_error() -> str:
    return getattr(_facade(), "_CONFIG_ERROR", "")


def _set_config_error(value: str) -> None:
    _facade()._CONFIG_ERROR = value


def _build_config() -> Any:
    return _facade().build_config()


def _reuse_enabled() -> bool:
    return _REUSE_ENABLED


# ── 核心对象复用（待机软重启）────────────────────────────────
# 软重启要「按新配置重建 bot 运行时」，但核心对象（日志/配置/数据库/适配器/插件主机/
# 命令服务/插件运行时/文件服务/待机服务）必须复用：重建它们会抢端口、丢插件命令、
# 把面板一起重启，还会让几十处持有引用的组件失联。
#
# 因此这里用「显式开启的对象缓存」代替把 1000 行的 _build_app 拆成两段：
# - 默认关闭：普通调用与测试完全不受影响（每次都是全新对象）；
# - 由待机装配路径 enable_core_reuse() 打开：第一次构建把核心对象放进缓存，
#   之后每次 create_application() 复用它们，只重建 bot 侧对象。
_REUSE_ENABLED = False
_CORE_CACHE: dict[str, Any] = {}


def config_load_error() -> str:
    """最近一次配置加载失败的原因（成功时为空串）。"""
    return _config_error()


def _load_config_or_defaults() -> Any:
    """加载配置；失败时**不退出程序**，返回默认配置并记录原因。

    过去缺失必需项或解析失败会让进程直接退出，用户只能改文件再重启。现在改为：
    用默认配置把核心服务（面板、配置编辑、命令、数据库）拉起来并进入待机。
    """
    try:
        config = _build_config()
    except Exception as exc:
        _set_config_error(f"{type(exc).__name__}: {exc}".strip())
        # 失败时不缓存配置：软重启必须重新读文件，否则会一直复用这份兜底配置
        _CORE_CACHE.pop("config", None)
        from neobot_app.config.loader.converter import dict_to_dataclass
        from neobot_app.config.proxy import ConfigProxy
        from neobot_app.config.schemas.bot import BotConfig

        # 兜底也返回 ConfigProxy：配置损坏时面板/QQ 的「配置重载」仍要能跑，
        # 否则会在这条路径上抛 AttributeError，用户就没有别的恢复手段了。
        return ConfigProxy(dict_to_dataclass({}, BotConfig))
    _set_config_error("")
    return config





def enable_core_reuse() -> None:
    """开启核心对象复用（幂等）：待机控制器接线时调用一次。"""
    global _REUSE_ENABLED
    _REUSE_ENABLED = True


def disable_core_reuse() -> None:
    """关闭复用并清空缓存（测试隔离用）。"""
    global _REUSE_ENABLED
    _REUSE_ENABLED = False
    _CORE_CACHE.clear()


def get_cached_core(key: str, default: Any = None) -> Any:
    """读取已缓存的核心对象（未开启复用或未构建时为 default）。"""
    return _CORE_CACHE.get(key, default)


def _reuse_or(key: str, factory: Callable[[], Any]) -> Any:
    """复用缓存中的核心对象；首次调用时用 factory 构建并缓存。"""
    if _REUSE_ENABLED and key in _CORE_CACHE:
        return _CORE_CACHE[key]
    value = factory()
    if _REUSE_ENABLED:
        _CORE_CACHE[key] = value
    return value


def _load_config_for_reuse() -> Any:
    """软重启复用的配置加载：兜底默认值绝不进缓存。

    配置加载失败时 _load_config_or_defaults 返回的是默认配置，若被 _reuse_or
    写回缓存，用户修好 config.toml 后每次软重启都会复用这份空配置、
    _CONFIG_ERROR 也永远清不掉，恢复路径形同虚设。
    """
    config = _reuse_or("config", _load_config_or_defaults)
    if _config_error():
        _CORE_CACHE.pop("config", None)
    return config


def _run_once(key: str, action: Callable[[], Any]) -> None:
    """只执行一次（复用开启时）：避免软重启重复配置日志等全局副作用。"""
    if _REUSE_ENABLED and key in _CORE_CACHE:
        return
    action()
    if _REUSE_ENABLED:
        _CORE_CACHE[key] = True


def _build_storage(db_path: Path, db_url: str, logger_factory: Any) -> Any:
    """迁移前备份 → 跑迁移 → 建引擎（核心对象，软重启复用）。"""
    backup_logger = logger_factory.get_logger("app.db_backup")
    backup_path = backup_sqlite_database(db_path, DATA_DIR / "db_backup", logger=backup_logger)
    if backup_path is not None:
        backup_logger.info(f"迁移前已备份数据库: {backup_path}")
    run_migrations(db_url)
    return build_storage(db_url)


def _register_flow_task_providers(
    registry: Any,
    *,
    drawing_manager: Any = None,
    scheduled_task_manager: Any = None,
    problem_solver_manager: Any = None,
    notification_hub: Any = None,
) -> None:
    """把各后台任务管理器的状态查询挂到聊天流登记处(与回复工具同源)。

    只登记提供 get_pipeline_status 的实例;缺失的来源静默跳过,
    面板仍能显示其余来源的状态。
    """
    sources = {
        "drawing": drawing_manager,
        "scheduled_task": scheduled_task_manager,
        "problem_solver": problem_solver_manager,
        "notification": notification_hub,
    }
    for name, manager in sources.items():
        getter = getattr(manager, "get_pipeline_status", None)
        if callable(getter):
            registry.register_task_provider(name, getter)
