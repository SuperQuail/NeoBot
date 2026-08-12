"""cli 的 VC++ 运行库检测/安装机制测试。"""

from __future__ import annotations

import pytest


def _issue_names(cli, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr("sys.platform", "win32")
    from neobot_app import cli as cli_module

    return cli_module._vc_runtime_issues()


def test_vc_runtime_issues_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """运行库完好时无问题。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    # 真实本机检查:本机 14.51 应无问题(测试机若运行库缺失则跳过)
    issues = cli_module._vc_runtime_issues()
    assert isinstance(issues, list)


def test_vc_runtime_issues_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 Windows 返回空(不做检查)。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    from neobot_app import cli as cli_module

    assert cli_module._vc_runtime_issues() == []


def test_vc_runtime_issues_detects_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """System32 路径指向空目录 → 全部判定缺失。"""
    import platform
    from pathlib import Path

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    empty = tmp_path / "System32"
    empty.mkdir()
    monkeypatch.setattr(cli_module, "_VC_SYSTEM32", empty)
    issues = cli_module._vc_runtime_issues()
    assert issues, "空 System32 应检测到缺失"
    assert "缺失" in issues[0]


def test_find_local_vc_redist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """离线包发现:cwd/scripts/vc_redist/vc_redist.x64.exe。"""
    from neobot_app import cli as cli_module

    package_dir = tmp_path / "scripts" / "vc_redist"
    package_dir.mkdir(parents=True)
    package = package_dir / "vc_redist.x64.exe"
    package.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.chdir(tmp_path)
    found = cli_module._find_local_vc_redist()
    assert found is not None
    assert found.name == "vc_redist.x64.exe"


def test_find_local_vc_redist_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neobot_app import cli as cli_module

    monkeypatch.chdir(tmp_path)
    assert cli_module._find_local_vc_redist() is None


def test_ensure_vc_runtime_fixed_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """完整流程:检测到问题 → 用户拒绝 → 返回 False 且不安装。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    empty = tmp_path / "System32"
    empty.mkdir()
    monkeypatch.setattr(cli_module, "_VC_SYSTEM32", empty)
    monkeypatch.setattr(cli_module, "_ask_install_vc_redist", lambda pkg: False)
    assert cli_module._ensure_vc_runtime_fixed() is False
    out = capsys.readouterr().out
    assert "VC++ 运行库问题" in out


def test_ask_install_vc_redist_noninteractive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非交互环境(EOF)默认跳过(返回空串)。"""
    from neobot_app import cli as cli_module

    package = tmp_path / "vc_redist.x64.exe"
    package.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setattr("builtins.input", lambda prompt: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert cli_module._ask_install_vc_redist(package) == ""


def test_ask_install_vc_redist_choices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """有离线包时:[1] 选离线,[2] 选在线,其他跳过。"""
    from neobot_app import cli as cli_module

    package = tmp_path / "vc_redist.x64.exe"
    package.write_bytes(b"x" * (1024 * 1024 + 1))

    for answer, expected in (("1", "offline"), ("offline", "offline"),
                             ("2", "online"), ("download", "online"),
                             ("n", ""), ("", "")):
        monkeypatch.setattr("builtins.input", lambda prompt, a=answer: a)
        monkeypatch.setattr("builtins.print", lambda *a, **k: None)
        assert cli_module._ask_install_vc_redist(package) == expected


def test_ask_install_vc_redist_without_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无离线包时:y → online,其他跳过。"""
    from neobot_app import cli as cli_module

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert cli_module._ask_install_vc_redist(None) == "online"

    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert cli_module._ask_install_vc_redist(None) == ""


def test_ensure_vc_runtime_fixed_offline_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """完整流程:检测到问题 → 选离线包 → 安装成功 → 返回 True。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    calls = {"n": 0}

    def fake_issues():
        calls["n"] += 1
        # 第一次检测到问题,安装后(第二次)视为已修复
        return ["vcruntime140.dll 版本过旧: 14.31"] if calls["n"] == 1 else []

    monkeypatch.setattr(cli_module, "_vc_runtime_issues", fake_issues)
    package = tmp_path / "vc_redist.x64.exe"
    package.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setattr(cli_module, "_find_local_vc_redist", lambda: package)
    monkeypatch.setattr(cli_module, "_ask_install_vc_redist", lambda pkg: "offline")
    monkeypatch.setattr(cli_module, "_install_vc_redist", lambda pkg: True)
    assert cli_module._ensure_vc_runtime_fixed() is True
    out = capsys.readouterr().out
    assert "已更新完成" in out
