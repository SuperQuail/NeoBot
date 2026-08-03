"""env 模块（环境变量文件读取、strip、默认值补全）测试。"""

import os
from pathlib import Path

import pytest

from neobot_app.config.loader.env import load_env
from neobot_app.config.schemas.env import EnvConfig

_ENV_KEYS = (
    "DeepSeek_URL",
    "DeepSeek_APIKey",
    "SiliconFlow_URL",
    "SiliconFlow_APIKey",
    "HuoShan_APIKey",
    "HuoShan_AppId",
)


def _clear_platform_env(monkeypatch) -> None:
    """按 casefold 清理全部平台环境变量（含大小写变体），避免测试间相互泄漏。"""
    for key in _ENV_KEYS:
        for actual in list(os.environ):
            if actual.casefold() == key.casefold():
                monkeypatch.delenv(actual, raising=False)


def _use_env_file(monkeypatch, tmp_path) -> Path:
    """把 ENV_FILE 指向临时 .env 文件并返回该路径。"""
    env_file = tmp_path / ".env"
    monkeypatch.setattr("neobot_app.config.loader.env.ENV_FILE", env_file)
    return env_file


def test_load_env_reads_all_keys_and_keeps_file_unchanged(monkeypatch, tmp_path):
    """.env 中全部键必须写入 os.environ，且已齐全的文件不得被重复补全。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    env_file = _use_env_file(monkeypatch, tmp_path)
    env_file.write_text(
        "DeepSeek_URL=https://api.deepseek.com\n"
        "DeepSeek_APIKey=sk-ds-1\n"
        "SiliconFlow_URL=https://api.siliconflow.cn/v1\n"
        "SiliconFlow_APIKey=sk-sf-1\n"
        "HuoShan_APIKey=hs-ak-1\n"
        "HuoShan_AppId=hs-app-1\n",
        encoding="utf-8",
    )
    original_content = env_file.read_text(encoding="utf-8")

    # Act
    load_env()

    # Assert
    assert os.environ["DeepSeek_URL"] == "https://api.deepseek.com"
    assert os.environ["DeepSeek_APIKey"] == "sk-ds-1"
    assert os.environ["SiliconFlow_APIKey"] == "sk-sf-1"
    assert os.environ["HuoShan_APIKey"] == "hs-ak-1"
    assert os.environ["HuoShan_AppId"] == "hs-app-1"
    assert env_file.read_text(encoding="utf-8") == original_content


def test_load_env_missing_keys_appended_with_default_values(monkeypatch, tmp_path):
    """.env 缺少的键必须按默认值补全追加到文件，已有键不得被重复追加。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    env_file = _use_env_file(monkeypatch, tmp_path)
    env_file.write_text("DeepSeek_URL=https://api.deepseek.com\n", encoding="utf-8")

    # Act
    load_env()

    # Assert
    content = env_file.read_text(encoding="utf-8")
    assert "DeepSeek_URL=https://api.deepseek.com" in content
    assert "DeepSeek_APIKey=" in content
    assert "SiliconFlow_URL=https://api.siliconflow.cn/v1" in content
    assert "HuoShan_AppId=" in content
    assert content.count("DeepSeek_URL=") == 1


def test_load_env_missing_file_generates_template(monkeypatch, tmp_path):
    """.env 不存在时必须生成包含全部键与默认值的模板，且不把默认值写入 os.environ。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    env_file = _use_env_file(monkeypatch, tmp_path)

    # Act
    load_env()

    # Assert
    assert env_file.is_file()
    content = env_file.read_text(encoding="utf-8")
    assert "DeepSeek_URL=https://api.deepseek.com" in content
    assert "DeepSeek_APIKey=" in content
    assert "HuoShan_APIKey=" in content
    for key in _ENV_KEYS:
        assert not any(actual.casefold() == key.casefold() for actual in os.environ)


@pytest.mark.xfail(
    reason=(
        "BUG-0071 'KEY = value' 写法未 strip：键尾/值首空白被原样写入 os.environ，"
        "导致 EnvConfig 按正确键名读取不到且文件被重复补全"
    ),
    strict=False,
)
def test_load_env_key_value_whitespace_is_stripped(monkeypatch, tmp_path):
    """.env 中等号两侧空白（'KEY = value'）必须被 strip 后以正确键名与干净值写入。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    env_file = _use_env_file(monkeypatch, tmp_path)
    env_file.write_text("DeepSeek_APIKey = sk-ds-space\n", encoding="utf-8")

    # Act
    try:
        load_env()

        # Assert
        assert os.environ["DeepSeek_APIKey"] == "sk-ds-space"
        assert env_file.read_text(encoding="utf-8").count("DeepSeek_APIKey=") == 1
    finally:
        os.environ.pop("DeepSeek_APIKey ", None)
        os.environ.pop("DeepSeek_APIKey", None)


def test_load_env_matches_keys_case_insensitively(monkeypatch, tmp_path):
    """.env 中键名大小写不一致时仍必须被识别为已有键，且可被平台配置读取。"""
    # Arrange
    _clear_platform_env(monkeypatch)
    env_file = _use_env_file(monkeypatch, tmp_path)
    env_file.write_text(
        "deepseek_url=https://ds.example.com\n"
        "DEEPSEEK_APIKEY=sk-ds-lower\n",
        encoding="utf-8",
    )

    # Act
    load_env()

    # Assert
    content = env_file.read_text(encoding="utf-8")
    assert "DeepSeek_URL=" not in content
    assert "DeepSeek_APIKey=" not in content
    platform = EnvConfig.get_api_platform_config("DeepSeek")
    assert platform.url == "https://ds.example.com"
    assert platform.api_key == "sk-ds-lower"
