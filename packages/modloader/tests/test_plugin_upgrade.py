"""维护期升级必须保留真实配置和数据库，失败恢复两者。"""

from contextlib import closing
import shutil
import sqlite3

from neobot_modloader.installer import PluginInstaller
from neobot_modloader.sdk.storage import StorageLease, StorageVersion, stored_version, write_storage
from neobot_modloader.sdk.tooling.upgrade import upgrade_package
from plugin_upgrade_helpers import package, project


def _installed(tmp_path):
    source = project(tmp_path / "old-source", 1)
    plugins = tmp_path / "host/plugins"
    plugins.mkdir(parents=True)
    shutil.copytree(source, plugins / "tasks")
    data = tmp_path / "host/data/tasks"
    data.mkdir(parents=True)
    (data / "config.toml").write_text('caption = "我的历史列表"\n', encoding="utf-8")
    with closing(sqlite3.connect(data / "tasks.sqlite3")) as db, db:
        db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        db.execute("INSERT INTO tasks(text) VALUES ('历史待办')")
    write_storage(data, StorageVersion(1, 1))
    return plugins, data.parent


def _rows(data, column):
    with closing(sqlite3.connect(data / "tasks/tasks.sqlite3")) as db:
        return db.execute(f"SELECT id, {column} FROM tasks").fetchall()


async def test_upgrade_migrates_real_config_and_database_from_final_zip(tmp_path):
    plugins, data = _installed(tmp_path)
    candidate = package(project(tmp_path / "new-source", 2), tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert report.ok, report.errors
    assert report.migrations == ("config:1->2", "data:1->2")
    assert _rows(data, "title") == [(1, "历史待办")]
    assert (data / "tasks/config.toml").read_text(encoding="utf-8") == 'board_title = "我的历史列表"\n'
    assert stored_version(data / "tasks", StorageVersion()) == StorageVersion(2, 2)
    assert len(report.backup_paths) == 2
    assert "online_upgrade" in report.unverified


async def test_migration_failure_does_not_change_installed_code_config_or_rows(tmp_path):
    plugins, data = _installed(tmp_path)
    before = (plugins / "tasks/__init__.py").read_bytes()
    candidate = package(project(tmp_path / "new-source", 2, migration_failure=True), tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert (plugins / "tasks/__init__.py").read_bytes() == before
    assert _rows(data, "text") == [(1, "历史待办")]
    assert (data / "tasks/config.toml").read_text(encoding="utf-8") == 'caption = "我的历史列表"\n'


async def test_candidate_startup_failure_restores_old_data_including_new_writes(tmp_path):
    plugins, data = _installed(tmp_path)
    before = (plugins / "tasks/__init__.py").read_bytes()
    candidate = package(project(tmp_path / "new-source", 2, startup_failure=True), tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert report.restored, report.errors
    assert (plugins / "tasks/__init__.py").read_bytes() == before
    assert _rows(data, "text") == [(1, "历史待办")]
    assert stored_version(data / "tasks", StorageVersion()) == StorageVersion(1, 1)


async def test_upgrade_refuses_when_host_holds_the_storage_lease(tmp_path):
    plugins, data = _installed(tmp_path)
    candidate = package(project(tmp_path / "new-source", 2), tmp_path / "new.zip")
    with StorageLease(data, "tasks"):
        report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert any("退出宿主" in error for error in report.errors)
    assert _rows(data, "text") == [(1, "历史待办")]


async def test_online_installer_refuses_storage_version_change_without_touching_code(tmp_path):
    plugins, data = _installed(tmp_path)
    candidate = package(project(tmp_path / "new-source", 2), tmp_path / "new.zip").read_bytes()

    async def fetcher(url):
        return candidate

    installer = PluginInstaller(plugin_dir=plugins, fetcher=fetcher)
    result = await installer.install("sample/tasks", replace=True, expected_name="tasks")
    assert not result.ok
    assert "维护期升级" in result.error
    assert _rows(data, "text") == [(1, "历史待办")]
    assert 'version = "0.1.0"' in (plugins / "tasks/plugin.toml").read_text()


async def test_upgrade_refuses_history_manifest_and_data_version_mismatch(tmp_path):
    plugins, data = _installed(tmp_path)
    write_storage(data / "tasks", StorageVersion(1, 2))
    candidate = package(project(tmp_path / "new-source", 2), tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert any("历史版本" in error for error in report.errors)
    assert _rows(data, "text") == [(1, "历史待办")]


async def test_upgrade_requires_external_data_directory(tmp_path):
    plugins, _ = _installed(tmp_path)
    candidate = package(project(tmp_path / "new-source", 2), tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=plugins / "private-data", name="tasks")
    assert not report.ok
    assert report.checks == ()
    assert any("代码目录外" in error for error in report.errors)
    assert not (plugins / "private-data").exists()


async def test_upgrade_refuses_candidate_requiring_newer_host_and_restores_history(tmp_path):
    plugins, data = _installed(tmp_path)
    source = project(tmp_path / "new-source", 2)
    manifest = source / "plugin.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("[sdk]", 'min_neobot_version = "999.0"\n[sdk]'),
        encoding="utf-8",
    )
    candidate = package(source, tmp_path / "new.zip")
    report = await upgrade_package(candidate, plugin_dir=plugins, data_dir=data, name="tasks")
    assert not report.ok
    assert _rows(data, "text") == [(1, "历史待办")]
    assert (data / "tasks/config.toml").read_text(encoding="utf-8") == 'caption = "我的历史列表"\n'
    assert stored_version(data / "tasks", StorageVersion()) == StorageVersion(1, 1)
