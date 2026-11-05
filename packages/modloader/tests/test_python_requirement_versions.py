"""Python 发行包必须满足完整需求串，而不仅是名称存在。"""

import importlib.metadata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neobot_modloader.loader import (
    is_python_dependency_installed,
    missing_python_dependencies,
    requirement_distribution_name,
)
from neobot_contracts.ports.plugin import PluginState
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


@pytest.mark.parametrize(
    ("requirement", "version", "expected"),
    [
        ("example>=1.0,<2", "1.5.0", True),
        ("example>=2.0", "1.5.0", False),
        ("example!=1.5.0", "1.5.0", False),
        ("example==1.5.*", "1.5.7", True),
        ("example~=1.5.0", "1.6.0", False),
        ("example>=1.0", "1.0rc1", False),
        ("example>=1.0rc1", "1.0rc2", True),
        ("example[feature]>=1.0", "1.5.0", True),
    ],
)
def test_installed_distribution_version_must_match(requirement: str, version: str, expected: bool) -> None:
    with patch(
        "neobot_modloader.loader.importlib.metadata.distribution",
        return_value=SimpleNamespace(version=version),
    ):
        assert is_python_dependency_installed(requirement) is expected


def test_inapplicable_marker_does_not_request_installation() -> None:
    with patch("neobot_modloader.loader.importlib.metadata.distribution") as distribution:
        assert is_python_dependency_installed("example;python_version<'1'")
        distribution.assert_not_called()


def test_missing_distribution_remains_missing() -> None:
    with patch(
        "neobot_modloader.loader.importlib.metadata.distribution",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        assert missing_python_dependencies(("example>=1",)) == ("example>=1",)


def test_missing_distribution_version_is_unsatisfied_instead_of_crashing() -> None:
    with patch(
        "neobot_modloader.loader.importlib.metadata.distribution",
        return_value=SimpleNamespace(version=None),
    ):
        assert is_python_dependency_installed("example>=1") is False


def test_requirement_name_supports_extras_and_normalization() -> None:
    assert requirement_distribution_name("example_package[feature]>=1") == "example-package"


def test_invalid_requirement_is_rejected() -> None:
    with pytest.raises(ValueError):
        is_python_dependency_installed("example>=")


@pytest.mark.parametrize("declaration", ["manifest", "code"])
async def test_invalid_requirement_only_blocks_its_own_plugin(tmp_path: Path, declaration: str) -> None:
    users = tmp_path / "plugins"
    body = "plugin.python_dependencies = ('example>=',)\n" if declaration == "code" else ""
    broken = make_plugin(users, "a_broken", body=body)
    if declaration == "manifest":
        manifest = broken / "plugin.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8") + 'python_dependencies = ["example>="]\n',
            encoding="utf-8",
        )
    make_plugin(users, "solo")
    runtime = make_runtime(tmp_path)

    try:
        await start_runtime(runtime)
        assert runtime.manager.get_record("a_broken") is None
        assert runtime.manager.get_state("solo") is PluginState.RUNNING
        snapshots = {item.name: item for item in runtime.snapshot_plugins()}
        assert snapshots["a_broken"].state == PluginState.ERROR.value
    finally:
        await runtime.stop_all()
