"""静态契约检查不得执行插件，也不得泄露错误值。"""

from copy import deepcopy

import pytest

from neobot_modloader.sdk.contract import validate_contract


def make_contract() -> dict:
    return {
        "schema_version": 1,
        "plugin": {"name": "demo", "version": "1.0.0", "description": "示例"},
        "config": {"type": "object", "properties": {"enabled": {"type": "boolean"}}},
        "actions": [
            {"id": "items.list", "permission": "read", "input_schema": None, "output_schema": None},
            {"id": "items.add", "permission": "manage", "input_schema": None, "output_schema": None},
        ],
        "resources": [
            {
                "id": "items",
                "list_action": "items.list",
                "create_action": "items.add",
                "columns": [{"key": "name", "title": "名称"}],
            }
        ],
        "guides": [
            {
                "id": "first",
                "steps": [{"target": "config.enabled", "text": "开启功能"}],
                "completion_action": "items.list",
            }
        ],
    }


def test_valid_contract_is_checked_without_mutation() -> None:
    contract = make_contract()
    before = deepcopy(contract)
    assert validate_contract(contract) == []
    assert contract == before


@pytest.mark.parametrize("value", [None, [], True, {"schema_version": True}, {"schema_version": 2}])
def test_invalid_documents_return_diagnostics(value) -> None:
    assert validate_contract(value)


@pytest.mark.parametrize(
    "settings",
    [
        [],
        None,
        [{"id": "business", "title": "业务设置", "input_action": "items.add"}],
    ],
)
def test_removed_settings_contract_is_not_silently_accepted(settings) -> None:
    contract = make_contract()
    contract["settings"] = settings
    assert validate_contract(contract) == ["契约含未知字段"]


def test_unknown_contract_fields_do_not_echo_author_keys_or_values() -> None:
    contract = make_contract()
    contract["synthetic-private-author-key"] = "synthetic-private-author-value"
    assert validate_contract(contract) == ["契约含未知字段"]


@pytest.mark.parametrize(
    "target",
    ["settings.business", "settings.business.enabled", "settings.business.items.add", "settings.business.resource"],
)
def test_removed_settings_guide_targets_are_rejected(target: str) -> None:
    contract = make_contract()
    contract["guides"][0]["steps"][0]["target"] = target
    errors = validate_contract(contract)
    assert any("guides.first.steps[0].target" in error for error in errors)
    assert target not in str(errors)


def test_cross_references_and_read_only_checks_are_validated() -> None:
    contract = make_contract()
    contract["resources"][0]["list_action"] = "items.add"
    contract["guides"][0]["completion_action"] = "missing"
    contract["guides"][0]["steps"][0]["target"] = "config.removed"
    errors = validate_contract(contract)
    assert any("list_action" in error for error in errors)
    assert any("completion_action" in error for error in errors)
    assert any("guides.first.steps[0].target" in error for error in errors)


def test_duplicate_actions_are_not_silently_overwritten() -> None:
    contract = make_contract()
    contract["actions"].append(dict(contract["actions"][0]))
    assert any("items.list" in error for error in validate_contract(contract))


def test_sensitive_schema_defaults_are_rejected_without_echoing_values() -> None:
    contract = make_contract()
    contract["config"]["properties"]["cookie"] = {
        "type": "string",
        "default": "SESSDATA=synthetic-contract-value",
    }
    errors = validate_contract(contract)
    assert any("cookie" in error and "default" in error for error in errors)
    assert "synthetic-contract-value" not in str(errors)


def test_non_json_and_nonfinite_values_are_rejected() -> None:
    contract = make_contract()
    contract["plugin"]["extra"] = float("nan")
    assert validate_contract(contract)


def test_command_diagnostics_report_fields_without_echoing_author_values() -> None:
    contract = make_contract()
    contract["guides"][0]["steps"][0]["command"] = {
        "text": "",
        "context": 42,
        "reply": False,
        "execute": "synthetic-private-author-value",
    }
    errors = validate_contract(contract)
    for field in ("text", "context", "reply"):
        assert any(f"guides.first.steps[0].command.{field}" in error for error in errors)
    assert "synthetic-private-author-value" not in str(errors)
