"""旧后台目标在 only-official 下的映射迁移解析。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.runtime.legacy_bindings import resolve_legacy_official_target
from neobot_app.user_identity import bind_user_identity, link_group_number, link_user_qq


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message: str, **kwargs) -> None:
        self.warnings.append(message)

    def info(self, message: str, **kwargs) -> None:
        self.infos.append(message)


@pytest.fixture(autouse=True)
def _identity(tmp_path):
    from neobot_app.runtime import legacy_bindings

    legacy_bindings._WARNED.clear()
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


def test_legacy_group_maps_to_official_synthetic() -> None:
    assert link_group_number(8000000000003, 123456789, channel="official", trusted=True)[0]
    logger = _Logger()
    adapter = SimpleNamespace(active_channels=("official",))

    result = resolve_legacy_official_target("group", 123456789, adapter=adapter, logger=logger)

    assert result == ("8000000000003", "official")
    assert logger.infos


def test_legacy_private_maps_to_official_synthetic() -> None:
    assert link_user_qq(9000000000003, 3514733681, trusted=True)[0]
    logger = _Logger()
    adapter = SimpleNamespace(active_channels=("official",))

    result = resolve_legacy_official_target("private", 3514733681, adapter=adapter, logger=logger)

    assert result == ("9000000000003", "official")


def test_legacy_target_without_mapping_warns_and_skips() -> None:
    logger = _Logger()
    adapter = SimpleNamespace(active_channels=("official",))

    result = resolve_legacy_official_target("group", 222222222, adapter=adapter, logger=logger)

    assert result is None
    assert logger.warnings
    assert "缺少" in logger.warnings[0]


def test_non_official_mode_keeps_legacy_target() -> None:
    logger = _Logger()
    adapter = SimpleNamespace(active_channels=("onebot", "official"))

    result = resolve_legacy_official_target("group", 222222222, adapter=adapter, logger=logger)

    assert result == ("222222222", "")
    assert logger.warnings == []


def test_synthetic_target_is_kept_in_official_mode() -> None:
    logger = _Logger()
    adapter = SimpleNamespace(active_channels=("official",))

    result = resolve_legacy_official_target("group", 8000000000003, adapter=adapter, logger=logger)

    assert result == ("8000000000003", "official")
