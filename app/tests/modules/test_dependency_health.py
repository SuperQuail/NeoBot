"""依赖体检与 DrissionPage 兼容层的定向单测。

背景：新环境部署连续踩到两个「装错版本」的坑 ——
DrissionPage 5.0.0b1 没有 ChromiumPage、某个 httpx 没有 AsyncClient，
而报错信息完全看不出装的是哪一版。这些用例锁住两件事：

1. `neobot doctor` 能如实报出版本与缺失符号；
2. DrissionPage 不可用时，浏览器包**仍可导入**，只有真正要驱动浏览器才报错。
"""

from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_SRC = REPO_ROOT / "app" / "src"


def test_doctor_reports_versions_and_symbols() -> None:
    """体检报告必须包含每个被检依赖的版本、路径与结论。"""

    from neobot_app.doctor import collect_dependency_report, format_report

    report = collect_dependency_report()
    modules = {row["module"] for row in report["dependencies"]}
    assert {"DrissionPage", "httpx", "sqlalchemy", "aiohttp", "loguru"} <= modules

    for row in report["dependencies"]:
        assert row["detail"], f"{row['module']} 缺少结论说明"
        if row["ok"]:
            assert row["detail"] == "OK"
            assert row["version"], f"{row['module']} 可用却没有版本号"

    text = format_report(report)
    assert "依赖体检" in text
    assert "Python" in text


def test_doctor_detects_missing_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    """符号缺失时必须判为不可用，并明确指出缺了哪个符号。"""

    from neobot_app import doctor

    class _FakeModule:
        __version__ = "9.9.9"
        __file__ = __file__

    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "httpx":
            return _FakeModule()
        return real_import(name, package)

    monkeypatch.setattr(doctor.importlib, "import_module", fake_import)
    row = doctor._describe("httpx", ("AsyncClient",))

    assert row["ok"] is False
    assert "AsyncClient" in row["detail"]


def test_compat_import_failure_is_recoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟「装成 DrissionPage 5.x」：_compat 不得抛异常，只标记不可用。"""

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name.startswith("DrissionPage"):
            raise ImportError("cannot import name 'ChromiumPage' from 'DrissionPage'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "neobot_app.browser.agent_browser._compat", raising=False)
    compat = importlib.import_module("neobot_app.browser.agent_browser._compat")

    try:
        assert compat.DRISSIONPAGE_AVAILABLE is False
        assert compat.ChromiumPage is None
        with pytest.raises(RuntimeError) as excinfo:
            compat.require_drissionpage()
        assert "ChromiumPage" in str(excinfo.value)
        assert "drissionpage" in str(excinfo.value).lower()
    finally:
        # 复原模块，避免污染后续用例（其它用例会真的 import DrissionPage）
        monkeypatch.undo()
        sys.modules.pop("neobot_app.browser.agent_browser._compat", None)
        importlib.import_module("neobot_app.browser.agent_browser._compat")


def test_browser_package_imports_without_drissionpage(monkeypatch: pytest.MonkeyPatch) -> None:
    """浏览器包必须能在没有 DrissionPage 的环境里导入（可选功能不拖垮启动）。"""

    for name in list(sys.modules):
        if name.startswith(("neobot_app.browser", "DrissionPage")):
            monkeypatch.delitem(sys.modules, name, raising=False)

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "neobot_app.browser.agent_browser" or name.startswith("DrissionPage"):
            raise ImportError("simulated missing optional dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    module = importlib.import_module("neobot_app.browser")

    # 包本身可用（包装类能构造），失败推迟到真正用浏览器时
    assert hasattr(module, "BrowserAgentWrapper")
    monkeypatch.undo()
