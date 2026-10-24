"""面板 read() 不能把数值字段当成密钥掩码。

`max_output_tokens` / `*_per_mtokens` 这些字段名命中密钥正则（token），旧实现把
它们在 schema 里的 default/value 清成空串并登记进 secrets_set：新增一条模型行时
表单按空串回传，保存必然 400「类型应为 int，实际为 str」。
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from neobot_app.builtin_plugins.dashboard.config_manager import (
    BotConfigManager,
    _mask_toml_source,
)

CONFIG_TEXT = (
    'version = "0.6.0"\n'
    "\n[adapter]\n"
    'local_auth_token = "LTOK-SECRET"\n'
    'reverse_ws_access_token = "RTOK-SECRET"\n'
    "\n[asr]\n"
    'api_key = "ASK-SECRET"\n'
)

#: 字段名命中密钥正则、实际是数值的 7 个字段
NUMERIC_PATHS = (
    ("chat", "private_chat_max_tokens"),
    ("models", "registry", "pricing", "input_price_per_mtokens"),
    ("models", "registry", "pricing", "output_price_per_mtokens"),
    ("models", "registry", "pricing", "cache_hit_price_per_mtokens"),
    ("models", "registry", "settings", "max_output_tokens"),
    ("agent", "problem_solver", "max_tokens"),
    ("agent", "self_healing", "max_tokens"),
)

#: 真正的字符串密钥
SECRET_PATHS = (
    ("adapter", "local_auth_token"),
    ("adapter", "reverse_ws_access_token"),
    ("asr", "api_key"),
)


def _manager(tmp_path: Path) -> tuple[BotConfigManager, Path]:
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    return (
        BotConfigManager(config_path=config_path, backup_dir=tmp_path / "backup"),
        config_path,
    )


def _schema_fields(
    descriptors: list[dict], found: dict[tuple[str, ...], dict] | None = None
) -> dict[tuple[str, ...], dict]:
    """把 schema 描述按 path 展平（含分组与对象数组的条目字段）。"""
    found = {} if found is None else found
    for item in descriptors:
        found[tuple(item.get("path") or ())] = item
        for key in ("fields", "item_fields"):
            children = item.get(key)
            if isinstance(children, list):
                _schema_fields(children, found)
    return found


def test_numeric_token_fields_are_not_masked(tmp_path: Path) -> None:
    manager, _ = _manager(tmp_path)
    document = manager.read()
    fields = _schema_fields(document["schema"])

    for path in NUMERIC_PATHS:
        item = fields[path]
        key = ".".join(path)
        assert isinstance(item["default"], (int, float)), (key, item["default"])
        # 对象数组的 item_fields 没有实例，value 本来就是 None——不能是掩码空串
        assert item["value"] is None or isinstance(item["value"], (int, float)), (
            key,
            item["value"],
        )
        assert key not in document["secrets_set"], key


def test_real_secrets_stay_masked(tmp_path: Path) -> None:
    manager, _ = _manager(tmp_path)
    document = manager.read()
    fields = _schema_fields(document["schema"])

    for path in SECRET_PATHS:
        item = fields[path]
        assert item["type"] == "str"
        assert item["default"] == ""
        assert item["value"] == ""
        assert document["secrets_set"][".".join(path)] is True

    assert document["config"]["adapter"]["local_auth_token"] == ""
    dumped = json.dumps(document, ensure_ascii=False)
    for secret in ("LTOK-SECRET", "RTOK-SECRET", "ASK-SECRET"):
        assert secret not in dumped


def test_mask_toml_source_keeps_numeric_values() -> None:
    assert _mask_toml_source("max_output_tokens = 2048") == "max_output_tokens = 2048"

    masked = _mask_toml_source('local_auth_token = "secret"\nmax_output_tokens = 2048\n')
    assert 'local_auth_token = "***"' in masked
    assert "max_output_tokens = 2048" in masked


def test_read_source_keeps_numeric_lines_but_masks_strings(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)
    config_path.write_text(
        'version = "0.6.0"\n'
        "\n[settings]\n"
        "max_output_tokens = 2048\n"
        "\n[adapter]\n"
        'local_auth_token = "LTOK"\n',
        encoding="utf-8",
    )

    source = manager.read()["source"]

    assert "max_output_tokens = 2048" in source
    assert 'local_auth_token = "***"' in source


def test_new_model_row_from_schema_defaults_saves(tmp_path: Path) -> None:
    """新增模型行：表单用的就是 schema 里的 default，落盘必须是数字。"""
    manager, config_path = _manager(tmp_path)
    document = manager.read()
    registry = _schema_fields(document["schema"])[("models", "registry")]
    assert registry["kind"] == "model_list"

    row = {
        item["name"]: item["default"]
        for item in registry["item_fields"]
        if item["default"] is not None
    }
    row.update(
        {
            "model_ref": "new-model",
            "model_name": "gpt-test",
            "model_type": "chat",
            "provider": "openai",
        }
    )
    models = dict(document["config"]["models"])
    models["registry"] = [*models["registry"], row]
    manager.save(config={**document["config"], "models": models})

    saved_text = config_path.read_text(encoding="utf-8")
    saved = tomllib.loads(saved_text)
    entry = saved["models"]["registry"][-1]
    assert entry["model_ref"] == "new-model"
    assert entry["settings"]["max_output_tokens"] == 2048
    assert isinstance(entry["settings"]["temperature"], float)
    assert isinstance(entry["pricing"]["input_price_per_mtokens"], float)
    assert '"***"' not in saved_text
