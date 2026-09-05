"""cli 的 VC++ 运行库检测/安装机制测试(在线下载模式,无内置离线包)。"""

from __future__ import annotations

from pathlib import Path

import pytest


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

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    empty = tmp_path / "System32"
    empty.mkdir()
    monkeypatch.setattr(cli_module, "_VC_SYSTEM32", empty)
    issues = cli_module._vc_runtime_issues()
    assert issues, "空 System32 应检测到缺失"
    assert "缺失" in issues[0]


def test_ensure_vc_runtime_fixed_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """完整流程:检测到问题 → 用户拒绝 → 返回 False 且不下载不安装。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    empty = tmp_path / "System32"
    empty.mkdir()
    monkeypatch.setattr(cli_module, "_VC_SYSTEM32", empty)
    monkeypatch.setattr(cli_module, "_ask_install_vc_redist", lambda: False)
    monkeypatch.setattr(cli_module, "_download_vc_redist", lambda: None)
    assert cli_module._ensure_vc_runtime_fixed() is False
    out = capsys.readouterr().out
    assert "VC++ 运行库问题" in out
    assert "手动下载安装" in out


def test_ask_install_vc_redist_noninteractive(monkeypatch: pytest.MonkeyPatch) -> None:
    """非交互环境(EOF)默认跳过(返回空串)。"""
    from neobot_app import cli as cli_module

    monkeypatch.setattr("builtins.input", lambda prompt: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert cli_module._ask_install_vc_redist() == ""


def test_ask_install_vc_redist_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    """在线模式:y → online,其他跳过。"""
    from neobot_app import cli as cli_module

    for answer, expected in (("y", "online"), ("yes", "online"),
                             ("n", ""), ("", ""), ("abc", "")):
        monkeypatch.setattr("builtins.input", lambda prompt, a=answer: a)
        monkeypatch.setattr("builtins.print", lambda *a, **k: None)
        assert cli_module._ask_install_vc_redist() == expected


def test_ensure_vc_runtime_fixed_online_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """完整流程:检测到问题 → 在线下载 → 安装成功 → 返回 True。"""
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
    monkeypatch.setattr(cli_module, "_ask_install_vc_redist", lambda: "online")
    monkeypatch.setattr(cli_module, "_download_vc_redist", lambda: package)
    monkeypatch.setattr(cli_module, "_install_vc_redist", lambda pkg: True)
    assert cli_module._ensure_vc_runtime_fixed() is True
    out = capsys.readouterr().out
    assert "已更新完成" in out


def test_ensure_vc_runtime_fixed_download_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """下载失败:返回 False 并提示手动下载官方链接。"""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    from neobot_app import cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "_vc_runtime_issues",
        lambda: ["vcruntime140.dll 版本过旧: 14.31"],
    )
    monkeypatch.setattr(cli_module, "_ask_install_vc_redist", lambda: "online")
    monkeypatch.setattr(cli_module, "_download_vc_redist", lambda: None)
    assert cli_module._ensure_vc_runtime_fixed() is False
    out = capsys.readouterr().out
    assert "下载失败" in out
    assert cli_module.VC_REDIST_URL in out
