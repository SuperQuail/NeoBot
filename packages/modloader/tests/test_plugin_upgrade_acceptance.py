"""历史包升级验收必须真实启动旧版并核对迁移后的业务数据。"""

import json

from neobot_modloader.sdk.tooling.upgrade_check import check_upgrade
from plugin_upgrade_helpers import package, project


def _fixture(path, *, expected="历史待办"):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "config_toml": 'caption = "历史面板"\n',
                "sqlite": [
                    {
                        "file": "tasks.sqlite3",
                        "setup": [
                            "CREATE TABLE tasks(id INTEGER PRIMARY KEY, text TEXT NOT NULL)",
                            "INSERT INTO tasks(text) VALUES ('历史待办')",
                        ],
                        "query": "SELECT id, title FROM tasks ORDER BY id",
                        "rows": [[1, expected]],
                    }
                ],
                "expected_config": {"board_title": "历史面板"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


async def test_upgrade_check_proves_history_config_and_rows_from_two_final_packages(tmp_path):
    old = package(project(tmp_path / "old", 1), tmp_path / "old.zip")
    new = package(project(tmp_path / "new", 2), tmp_path / "new.zip")
    report = await check_upgrade(old, new, _fixture(tmp_path / "fixture.json"), tmp_path / "report")
    assert report["ok"], report["errors"]
    assert report["checks"] == ["history_start", "maintenance_upgrade", "config_readback", "sqlite_readback"]
    assert report["upgrade"]["migrations"] == ("config:1->2", "data:1->2")
    assert report["artifacts"]["previous"]["sha256"] != report["artifacts"]["candidate"]["sha256"]


async def test_upgrade_check_rejects_data_readback_mismatch(tmp_path):
    old = package(project(tmp_path / "old", 1), tmp_path / "old.zip")
    new = package(project(tmp_path / "new", 2), tmp_path / "new.zip")
    report = await check_upgrade(
        old, new, _fixture(tmp_path / "fixture.json", expected="不应凭空出现"), tmp_path / "report"
    )
    assert not report["ok"]
    assert "SQLite" in report["errors"][0]
    assert report["sqlite_readback"] == [
        {"file": "tasks.sqlite3", "query": "SELECT id, title FROM tasks ORDER BY id", "rows": [[1, "历史待办"]]}
    ]


async def test_upgrade_check_reports_restored_state_on_candidate_start_failure(tmp_path):
    old = package(project(tmp_path / "old", 1), tmp_path / "old.zip")
    new = package(project(tmp_path / "new", 2, startup_failure=True), tmp_path / "new.zip")
    report = await check_upgrade(old, new, _fixture(tmp_path / "fixture.json"), tmp_path / "report")
    assert not report["ok"]
    assert report["upgrade"]["restored"]
