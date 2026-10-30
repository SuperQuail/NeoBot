"""测试公共设施：离线响应夹具、假传输层，以及无 NeoBot 环境下的 modloader 替身。"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import types
from typing import Any

import pytest

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
#: 强制走「无 NeoBot」分支，用来在本地复现 CI 环境
FORCE_STUB = os.environ.get("STREAMING_PARSER_TEST_FORCE_STUB") == "1"


def install_modloader_stub() -> bool:
    """没有 NeoBot 时（例如 GitHub CI）装一个最小替身，让插件模块可以被 import。

    只覆盖「导入期」需要的符号；真正的运行期能力（数据库、截图端口）在 CI 里不可用，
    相关测试会用 pytest.skip 显式跳过，而不是假装通过。
    """
    if not FORCE_STUB:
        try:
            import neobot_modloader  # noqa: F401

            return False
        except ImportError:
            pass

    stub = types.ModuleType("neobot_modloader")
    stub.IS_TEST_STUB = True  # type: ignore[attr-defined]

    class _Plugin:
        def __init__(self, name: str, **kwargs: Any) -> None:
            self.name = name
            self.version = kwargs.get("version", "0.1.0")
            self.dependencies: tuple[str, ...] = ()

        def _decorator(self, *args: Any, **kwargs: Any):
            def wrap(func):
                return func

            return wrap

        command = _decorator
        message = _decorator
        regex = _decorator
        tool = _decorator
        agent = _decorator
        capability = _decorator
        on_load = _decorator
        on_startup = _decorator
        on_shutdown = _decorator
        action = _decorator
        resource = _decorator
        guide = _decorator
        view = _decorator

        def sqlite_database(self, *args: Any, **kwargs: Any) -> Any:
            # 导入期只要求返回一个对象；真正的数据库能力在 CI 里不可用，
            # test_db.py 会显式跳过而不是假装通过。
            return object()

    class _Migration:
        def __init__(self, version: int, name: str, upgrade: Any) -> None:
            self.version = version
            self.name = name
            self.upgrade = upgrade

    class _RenderOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    stub.Plugin = _Plugin  # type: ignore[attr-defined]
    stub.ActionError = RuntimeError  # type: ignore[attr-defined]
    stub.Migration = _Migration  # type: ignore[attr-defined]
    stub.FontFace = _Migration  # type: ignore[attr-defined]
    stub.RenderOptions = _RenderOptions  # type: ignore[attr-defined]
    stub.ScreenshotOptions = _RenderOptions  # type: ignore[attr-defined]
    sys.modules["neobot_modloader"] = stub
    return True


USING_MODLOADER_STUB = install_modloader_stub()


def install_plugin_package_alias() -> bool:
    """保证 import streaming_parser 在任何环境都能解析。

    仓库目录名就是插件名（例如 GitHub 上叫 NeoBot_StreamingParser），
    所以不能靠目录名导入；这里按文件位置把插件目录注册成 streaming_parser 包。
    返回是否新建了别名。
    """
    if "streaming_parser" in sys.modules:
        return False
    try:
        import streaming_parser  # noqa: F401

        return False
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(
        "streaming_parser",
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    if spec is None or spec.loader is None:
        return False
    module = importlib.util.module_from_spec(spec)
    sys.modules["streaming_parser"] = module
    spec.loader.exec_module(module)
    return True


USING_PLUGIN_ALIAS = install_plugin_package_alias()

# 这个导入必须放在替身安装之后（替身要先注册进 sys.modules），故豁免 E402。
from bilibili.client import RawResponse  # noqa: E402

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def normalize_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """修掉本机 NO_PROXY 里的 [::1] 写法。

    httpx 解析 NO_PROXY 时会把 [::1] 当成带端口的 host，直接抛
    InvalidURL: Invalid port ':1]'（NeoBot 根 conftest.py 是靠清空代理规避的）。
    这里只去掉方括号，保留本地代理，让联网测试仍能走用户自己的代理。
    """
    for key in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(key)
        if value and "[::1]" in value:
            monkeypatch.setenv(key, value.replace("[::1]", "::1"))


@pytest.fixture
def load_fixture():
    """读取 tests/fixtures 下的 JSON 夹具。"""

    def _load(name: str) -> Any:
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    return _load


def json_response(payload: Any, *, status: int = 200, url: str = "") -> RawResponse:
    return RawResponse(status=status, body=payload, url=url)


def text_response(text: str, *, status: int = 200) -> RawResponse:
    return RawResponse(status=status, body=text)


class FakeTransport:
    """按队列返回预设响应，并记录每次请求，用于离线验证。"""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(
        self, *, method: str, url: str, headers: dict[str, str], timeout: float
    ) -> RawResponse:
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("FakeTransport 没有更多预设响应")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_transport():
    def _make(responses: list[Any]) -> FakeTransport:
        return FakeTransport(responses)

    return _make


@pytest.fixture
def sleep_recorder():
    """记录退避 sleep 的时长，避免测试真的等待。"""
    recorded: list[float] = []

    async def _sleep(seconds: float) -> None:
        recorded.append(seconds)

    return recorded, _sleep
