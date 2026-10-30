"""畸形静态 Schema 必须通过工程与 CLI 入口返回可公开的位置诊断。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from neobot_modloader.sdk.tooling import check_project
from plugin_tooling_helpers import make_project, write_contract

_DEFAULT_VALUE = "synthetic-default-not-for-diagnostics"
_INVALID_SCHEMAS = [
    pytest.param(({"properties": []}, "config.properties"), id="properties-list"),
    pytest.param(({"properties": None}, "config.properties"), id="properties-null"),
    pytest.param(({"patternProperties": []}, "config.patternProperties"), id="patterns-list"),
    pytest.param(({"patternProperties": None}, "config.patternProperties"), id="patterns-null"),
    pytest.param(({"patternProperties": {"[": {}}}, "config.patternProperties"), id="pattern-invalid"),
    pytest.param(
        ({"patternProperties": {"a{999999999999999999999}": {}}}, "config.patternProperties"),
        id="pattern-repeat-overflow",
    ),
    pytest.param(
        ({"patternProperties": {"(" * 3000 + ")" * 3000: {}}}, "config.patternProperties"),
        id="pattern-nesting-overflow",
    ),
    pytest.param(({"$defs": []}, "config.$defs"), id="defs-list"),
    pytest.param(({"definitions": None}, "config.definitions"), id="definitions-null"),
    pytest.param(({"anyOf": {}}, "config.anyOf"), id="any-of-object"),
    pytest.param(({"oneOf": None}, "config.oneOf"), id="one-of-null"),
    pytest.param(({"allOf": {}}, "config.allOf"), id="all-of-object"),
    pytest.param(({"prefixItems": {}}, "config.prefixItems"), id="prefix-items-object"),
    pytest.param(
        ({"properties": {"profile": {"properties": []}}}, "config.properties.profile.properties"),
        id="nested-properties-list",
    ),
    pytest.param(
        (
            {"$defs": {"Item": {"patternProperties": {"[": {}}}}, "$ref": "#/$defs/Item"},
            "config.$defs.Item.patternProperties",
        ),
        id="referenced-pattern-invalid",
    ),
    pytest.param(
        ({"x-shared": {"properties": []}, "$ref": "#/x-shared"}, "config.x-shared.properties"),
        id="referenced-extension-invalid",
    ),
    pytest.param(
        ({"x-neobot": {"input_aliases": None}}, "config.x-neobot.input_aliases"),
        id="aliases-null",
    ),
]


@pytest.fixture(params=_INVALID_SCHEMAS)
def malformed_schema_project(tmp_path: Path, request: pytest.FixtureRequest) -> tuple[Path, str]:
    schema, location = request.param
    path = make_project(tmp_path)
    write_contract(path, "sample", config={**schema, "default": {"field": _DEFAULT_VALUE}})
    return path, location


def test_static_check_reports_malformed_schema(malformed_schema_project: tuple[Path, str]) -> None:
    path, location = malformed_schema_project
    report = check_project(path)
    assert not report.ok
    assert any(location in error for error in report.errors)
    assert _DEFAULT_VALUE not in json.dumps(report.to_dict())
    assert report.executes_plugin is False


def test_cli_reports_malformed_schema_as_json(malformed_schema_project: tuple[Path, str]) -> None:
    path, location = malformed_schema_project
    completed = subprocess.run(
        [sys.executable, "-m", "neobot_modloader.sdk", "check", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["command"] == "check"
    assert report["ok"] is False
    assert any(location in error for error in report["errors"])
    assert report["executes_plugin"] is False
    assert "Traceback" not in completed.stderr
    assert _DEFAULT_VALUE not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "schema",
    [
        None,
        True,
        False,
        {},
        {"properties": {"enabled": True, "disabled": False}},
        {"prefixItems": [True, False, {"type": "string"}], "items": False},
        {"items": {"properties": {"enabled": True}}, "additionalProperties": False},
        {"anyOf": [True, False], "oneOf": [{}, True], "allOf": [True]},
        {"$defs": {"Node": {"properties": {"child": {"$ref": "#/$defs/Node"}}}}, "$ref": "#/$defs/Node"},
    ],
)
def test_static_check_preserves_supported_schema_shapes(tmp_path: Path, schema: object) -> None:
    path = make_project(tmp_path)
    write_contract(path, "sample", config=schema)
    report = check_project(path)
    assert report.ok, report.errors


@pytest.mark.parametrize("keyword", ["input_schema", "output_schema"])
def test_static_check_validates_action_schema_shapes(tmp_path: Path, keyword: str) -> None:
    path = make_project(tmp_path)
    action = {"id": "status", "permission": "read", keyword: {"properties": []}}
    write_contract(path, "sample", actions=[action])
    report = check_project(path)
    assert not report.ok
    assert any(f"actions.status.{keyword}.properties" in error for error in report.errors)
