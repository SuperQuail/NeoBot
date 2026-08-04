"""Windows 防火墙控制台端口放行模块测试。

覆盖规则解析、规则存在性检测 (mock 注册表)、警告消息与放行命令生成。
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from neobot_app.console import firewall


def test_parse_rule_value_extracts_fields() -> None:
    """规则注册表值 V2.28|Action=Allow|... 应解析为字段字典。"""
    # Arrange
    value = (
        "V2.28|Action=Allow|Active=TRUE|Dir=In|Protocol=6|"
        "App=D:\\Code\\Python\\NeoBot\\.venv\\Scripts\\python.exe|"
        "LPort=9981|Name=NeoBot"
    )

    # Act
    fields = firewall._parse_rule_value(value)

    # Assert
    assert fields["Action"] == "Allow"
    assert fields["Dir"] == "In"
    assert fields["Active"] == "TRUE"
    assert fields["LPort"] == "9981"
    assert fields["App"].endswith("python.exe")


def test_parse_rule_value_handles_empty_and_unkeyed_parts() -> None:
    """解析应容忍空段与无 '=' 的段。"""
    # Arrange
    value = "V2.28||Action=Block|noise|"

    # Act
    fields = firewall._parse_rule_value(value)

    # Assert
    assert fields["Action"] == "Block"
    assert len(fields) == 1  # 无键段被忽略


@pytest.mark.skipif(not firewall.is_windows(), reason="仅 Windows 平台")
def test_has_inbound_allow_rule_detects_matching_program_rule() -> None:
    """存在与程序路径匹配的入站允许规则时返回 True。"""
    # Arrange: mock 注册表返回一条与当前解释器匹配的规则
    fake_values = [
        (
            "rule-1",
            (
                f"V2.28|Action=Allow|Active=TRUE|Dir=In|Protocol=6|"
                f"App={sys.executable}|LPort=9981|Name=NeoBot"
            ),
            1,
        ),
        ("rule-2", "V2.28|Action=Block|Active=TRUE|Dir=In|App=C:\\other\\x.exe", 1),
        ("rule-3", "V2.28|Action=Allow|Active=TRUE|Dir=Out|App=C:\\other\\y.exe", 1),
    ]

    class _FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __init__(self, values):
            self._values = values

        def QueryInfoKey(self):
            return (0, len(self._values))

        def EnumValue(self, index):
            return self._values[index]

    with patch("winreg.OpenKey", return_value=_FakeKey(fake_values)), \
         patch("winreg.QueryInfoKey", lambda key: key.QueryInfoKey()), \
         patch("winreg.EnumValue", lambda key, index: key.EnumValue(index)):
        assert firewall.has_inbound_allow_rule(sys.executable) is True


@pytest.mark.skipif(not firewall.is_windows(), reason="仅 Windows 平台")
def test_has_inbound_allow_rule_ignores_block_and_outbound() -> None:
    """Block 规则与出站规则不应被误判为放行。"""
    # Arrange: 只有 Block/出站规则, 无匹配的入站允许规则
    fake_values = [
        (
            "rule-1",
            f"V2.28|Action=Block|Active=TRUE|Dir=In|App={sys.executable}",
            1,
        ),
        (
            "rule-2",
            f"V2.28|Action=Allow|Active=TRUE|Dir=Out|App={sys.executable}",
            1,
        ),
    ]

    class _FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __init__(self, values):
            self._values = values

        def QueryInfoKey(self):
            return (0, len(self._values))

        def EnumValue(self, index):
            return self._values[index]

    with patch("winreg.OpenKey", return_value=_FakeKey(fake_values)), \
         patch("winreg.QueryInfoKey", lambda key: key.QueryInfoKey()), \
         patch("winreg.EnumValue", lambda key, index: key.EnumValue(index)):
        assert firewall.has_inbound_allow_rule(sys.executable) is False


@pytest.mark.skipif(not firewall.is_windows(), reason="仅 Windows 平台")
def test_has_inbound_allow_rule_port_rule_counts_as_open() -> None:
    """按端口放行 (未指定程序) 的规则也应视为已放行。"""
    # Arrange: 规则按 LPort 放行, 不绑定程序
    fake_values = [
        (
            "rule-port",
            "V2.28|Action=Allow|Active=TRUE|Dir=In|Protocol=6|LPort=9981|Name=NeoBot",
            1,
        ),
    ]

    class _FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __init__(self, values):
            self._values = values

        def QueryInfoKey(self):
            return (0, len(self._values))

        def EnumValue(self, index):
            return self._values[index]

    with patch("winreg.OpenKey", return_value=_FakeKey(fake_values)), \
         patch("winreg.QueryInfoKey", lambda key: key.QueryInfoKey()), \
         patch("winreg.EnumValue", lambda key, index: key.EnumValue(index)):
        assert firewall.check_console_firewall(9981) is True
        assert firewall.check_console_firewall(9999) is False


def test_firewall_warning_message_contains_actionable_command() -> None:
    """警告消息必须包含可执行的一键放行命令。"""
    # Act
    message = firewall.firewall_warning_message(9981)

    # Assert
    assert "9981" in message
    assert "firewall-open" in message
    assert "管理员" in message


@patch("neobot_app.console.firewall.subprocess.run")
def test_add_inbound_allow_rule_builds_netsh_command(mock_run) -> None:
    """放行命令应包含程序路径、方向、动作与端口。"""
    # Arrange
    mock_run.return_value.returncode = 0

    # Act
    ok = firewall.add_inbound_allow_rule(r"D:\Code\Python\NeoBot\.venv\Scripts\python.exe", 9981)

    # Assert
    assert ok is True
    command = mock_run.call_args.args[0]
    assert "dir=in" in command
    assert "action=allow" in command
    assert "localport=9981" in command
    assert ".venv" in command and "python.exe" in command
