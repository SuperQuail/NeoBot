"""嵌入式数据库迁移保留宿主日志，独立 Alembic 命令仍能配置日志。"""

import logging
import logging.config
from pathlib import Path

from alembic import command
from alembic.config import Config

import neobot_storage
from neobot_storage.engine import run_migrations, sqlite_url


def test_embedded_migration_preserves_host_logging(tmp_path, caplog, monkeypatch) -> None:
    root = logging.getLogger()
    host_logger = logging.getLogger("neobot.test.migration_host")
    monkeypatch.setattr(host_logger, "disabled", False)
    monkeypatch.setattr(host_logger, "level", logging.INFO)
    handlers = tuple(root.handlers)
    level = root.level

    run_migrations(sqlite_url(tmp_path / "embedded.db"))

    assert tuple(root.handlers) == handlers
    assert root.level == level
    assert host_logger.disabled is False
    host_logger.warning("宿主日志仍可使用")
    assert "宿主日志仍可使用" in caplog.text


def test_standalone_alembic_still_configures_logging(tmp_path, monkeypatch) -> None:
    package_dir = Path(neobot_storage.__file__).resolve().parent
    ini = package_dir / "alembic.ini"
    config = Config(str(ini))
    config.set_main_option("script_location", str(package_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(tmp_path / "standalone.db"))
    calls = []
    monkeypatch.setattr(
        logging.config,
        "fileConfig",
        lambda filename, **kwargs: calls.append((filename, kwargs)),
    )

    command.current(config)

    assert calls == [(str(ini), {"disable_existing_loggers": False})]
