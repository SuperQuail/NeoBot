"""用显式合成历史快照验收两个最终包的维护期升级。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

from neobot_modloader.installer import MAX_ARCHIVE_BYTES, PluginInstaller
from neobot_modloader.sdk.storage import StorageLease

from .files import safe_relative_path
from .upgrade import _verify, upgrade_package


def _fixture(path: Path) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or set(fixture) != {"schema_version", "config_toml", "sqlite", "expected_config"}:
        raise ValueError("升级样例必须声明 schema_version/config_toml/sqlite/expected_config")
    if fixture["schema_version"] != 1 or not isinstance(fixture["config_toml"], str):
        raise ValueError("升级样例版本或 TOML 配置无效")
    tomllib.loads(fixture["config_toml"])
    if not isinstance(fixture["expected_config"], dict) or not fixture["expected_config"]:
        raise ValueError("升级样例必须包含非空的配置读回断言")
    if not isinstance(fixture["sqlite"], list) or not fixture["sqlite"]:
        raise ValueError("升级样例必须包含 SQLite 历史数据和读回断言")
    for database in fixture["sqlite"]:
        if not isinstance(database, dict) or set(database) != {"file", "setup", "query", "rows"}:
            raise ValueError("SQLite 样例必须声明 file/setup/query/rows")
        setup = database["setup"]
        valid_setup = isinstance(setup, list) and bool(setup) and all(isinstance(sql, str) for sql in setup)
        valid_readback = isinstance(database["query"], str) and isinstance(database["rows"], list)
        if not valid_setup or not valid_readback:
            raise ValueError("SQLite 样例 SQL 或预期行无效")
    return fixture


def _seed_history_databases(data: Path, databases: list[dict]) -> None:
    """各库在独立事务中恢复合成历史数据，连接随该库初始化完成而关闭。"""
    for database in databases:
        path = safe_relative_path(data, database["file"], label="sqlite.file")
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            for sql in database["setup"]:
                connection.execute(sql)


def _verify_sqlite_readback(data: Path, databases: list[dict], readback: list[dict]) -> None:
    """逐库追加只读验收证据，发生不匹配时仍保留已经完成的读回。"""
    for database in databases:
        path = safe_relative_path(data, database["file"], label="sqlite.file")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            rows = [list(row) for row in connection.execute(database["query"]).fetchall()]
        readback.append({"file": database["file"], "query": database["query"], "rows": rows})
        if rows != database["rows"]:
            raise ValueError("升级后的 SQLite 业务数据读回与预期不一致")


async def check_upgrade(previous: Path, candidate: Path, fixture: Path, output: Path, *, timeout: float = 30.0) -> dict:
    """保留隔离宿主供检查；样例仅用于测试，不能指向真实用户数据。"""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "ok": False,
        "checks": [],
        "errors": [],
        "artifacts": {},
        "boundary": "maintenance_only",
        "host": str(output / "host"),
        "unverified": ["real_services", "online_upgrade", "post_commit_data_restore"],
    }
    try:
        if timeout <= 0:
            raise ValueError("timeout 必须大于零")
        dataset = _fixture(fixture)
        report["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        report["config_before"] = tomllib.loads(dataset["config_toml"])
        for label, package in (("previous", previous), ("candidate", candidate)):
            if not package.is_file() or package.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError("最终包不存在或超过安装器体积上限")
            report["artifacts"][label] = {
                "path": str(package.resolve()),
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
            }
        host = output / "host"
        host.mkdir()
        plugins, data_root = host / "plugins", host / "data"
        archive = previous.read_bytes()

        async def fetcher(url: str) -> bytes:
            return archive

        async with asyncio.timeout(timeout):
            installed = await PluginInstaller(plugin_dir=plugins, fetcher=fetcher).install("sdk/history")
            if not installed.ok or installed.path is None:
                raise ValueError(f"历史包安装失败: {installed.error}")
            name = installed.path.name
            data = data_root / name
            data.mkdir(parents=True)
            (data / "config.toml").write_text(dataset["config_toml"], encoding="utf-8")
            _seed_history_databases(data, dataset["sqlite"])
            with StorageLease(data_root, name) as lease:
                await _verify(plugins, data_root, name, lease)
            report["checks"].append("history_start")
            upgrade = await upgrade_package(
                candidate, plugin_dir=plugins, data_dir=data_root, name=name, timeout=timeout
            )
            report["upgrade"] = upgrade.to_dict()
            if not upgrade.ok:
                raise ValueError("维护期升级失败: " + "; ".join(upgrade.errors))
            report["checks"].append("maintenance_upgrade")
            config = tomllib.loads((data / "config.toml").read_text(encoding="utf-8"))
            report["config_after"] = config
            if any(config.get(key) != value for key, value in dataset["expected_config"].items()):
                raise ValueError("升级后的配置读回与预期不一致")
            report["checks"].append("config_readback")
            report["sqlite_readback"] = []
            _verify_sqlite_readback(data, dataset["sqlite"], report["sqlite_readback"])
            report["checks"].append("sqlite_readback")
        report["ok"] = True
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError, sqlite3.Error, TimeoutError) as exc:
        report["errors"].append(str(exc) or "历史升级验收超时")
    (output / "upgrade-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return report
