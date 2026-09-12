"""CLI --version：版本号动态取自包版本，不再硬编码。

回归背景：`cli.py` 原先写死 `version="%(prog)s 1.0.0"`，
升级 8 个工作区包版本后 CLI 仍报 1.0.0，与实际包版本脱节。
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import pytest

from neobot_app import cli
from neobot_app.core import APP_VERSION


def _run_version(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    monkeypatch.setattr(sys, "argv", ["neobot", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 0
    return capsys.readouterr().out.strip()


def test_version_flag_matches_app_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--version 输出必须等于 APP_VERSION（而不是某个写死的字面量）。"""
    assert _run_version(monkeypatch, capsys) == f"neobot {APP_VERSION}"


def test_version_flag_follows_app_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """把 APP_VERSION 换成哨兵值，输出要跟着变 —— 证明是动态读取而非硬编码。"""
    monkeypatch.setattr(cli, "APP_VERSION", "9.9.9-alpha.1")

    assert _run_version(monkeypatch, capsys) == "neobot 9.9.9-alpha.1"


def test_app_version_reads_installed_package_metadata() -> None:
    """APP_VERSION 来源于已安装包元数据（开发态为可编辑安装）。"""
    try:
        expected = version("neobot-app")
    except PackageNotFoundError:
        expected = "0.0.0"

    assert APP_VERSION == expected
