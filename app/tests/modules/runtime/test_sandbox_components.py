"""装配层：``agent.sandbox`` 配置真正落到 SandboxService。

覆盖两件事：
1. ``allowed_read_dirs`` 不再被 bootstrap 硬编码覆盖，配置值生效；
2. ``excluded_workspaces`` 的路径规则（绝对路径、``~`` 展开、相对路径报错）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from neobot_app.bootstrap._runtime import (
    _resolve_allowed_read_dirs,
    _resolve_excluded_workspaces,
    build_sandbox_components,
)


def _sandbox_config(**overrides) -> SimpleNamespace:
    values = {
        "enabled": True,
        "max_total_size_bytes": 4096,
        "temp_max_age_seconds": 60,
        "temp_hold_max_minutes": 1,
        "scan_interval_seconds": 60,
        "allowed_read_dirs": [],
        "excluded_workspaces": [],
        "maintenance": SimpleNamespace(enabled=False, interval_seconds=3600),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _config(sandbox_cfg: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(agent=SimpleNamespace(sandbox=sandbox_cfg))


def test_build_sandbox_components_wires_config_into_service(tmp_path):
    """Arrange 配置里同时给出只读目录与排除工作区，Act 走真实装配函数，
    Assert SandboxService 拿到的是配置值而不是硬编码。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "g.png").write_bytes(b"png")

    components = build_sandbox_components(
        config=_config(
            _sandbox_config(
                allowed_read_dirs=[str(gallery)],
                excluded_workspaces=[str(workspace)],
            )
        ),
        data_dir=tmp_path / "data",
    )
    service = components["sandbox_service"]

    assert service is not None
    assert service.max_total_size == 4096
    assert service.excluded_workspaces == (workspace.resolve(),)
    assert service.is_path_allowed(gallery / "g.png")
    assert service.resolve_agent_path(
        str(workspace / "x.txt"), owner="alice", chat_flow_id="group:1", write=True
    ) == (workspace / "x.txt").resolve()


def test_excluded_workspaces_require_absolute_paths():
    """Arrange 一个相对路径配置，Act 解析，Assert 装配期直接 ValueError。"""
    with pytest.raises(ValueError, match="excluded_workspaces"):
        _resolve_excluded_workspaces(
            _sandbox_config(excluded_workspaces=["relative/workspace"])
        )


def test_excluded_workspaces_expand_tilde_and_keep_missing_dirs(tmp_path):
    """Arrange ``~`` 与一个尚不存在的目录，Act 解析，
    Assert 家目录被展开、缺失目录也保留（首次写入再创建）。"""
    missing = tmp_path / "not-created-yet"

    resolved = _resolve_excluded_workspaces(
        _sandbox_config(excluded_workspaces=["~", "", str(missing)])
    )

    assert resolved == [Path.home().resolve(), missing.resolve()]


def test_allowed_read_dirs_follow_config_and_fallback(tmp_path):
    """Arrange 显式只读目录与字段缺失两种情况，Act 解析，
    Assert 显式值原样生效、缺失时回退到 data_dir 下的 emoji/gallery。"""
    data_dir = tmp_path / "data"
    custom = tmp_path / "custom-read"
    custom.mkdir()

    assert _resolve_allowed_read_dirs(
        _sandbox_config(allowed_read_dirs=[str(custom)]), data_dir
    ) == [custom.resolve()]

    assert _resolve_allowed_read_dirs(
        _sandbox_config(allowed_read_dirs=None), data_dir
    ) == [
        (data_dir / "emoji").resolve(),
        (data_dir / "creator" / "gallery").resolve(),
    ]


def test_default_allowed_read_dirs_resolve_under_data_dir(tmp_path):
    """Arrange 一份真实默认配置（``./data/emoji/`` 等相对写法）与按默认布局放置的
    data_dir，Act 解析，Assert 落到 ``data_dir/emoji`` 与 ``data_dir/creator/gallery``，
    与接线前的硬编码一致。"""
    data_dir = tmp_path / "app" / "data"

    resolved = _resolve_allowed_read_dirs(
        _sandbox_config(
            allowed_read_dirs=["./data/emoji/", "./data/creator/gallery/"]
        ),
        data_dir,
    )

    assert resolved == [
        (data_dir / "emoji").resolve(),
        (data_dir / "creator" / "gallery").resolve(),
    ]


def test_relative_allowed_read_dirs_ignore_process_cwd(tmp_path, monkeypatch):
    """Arrange 把进程 CWD 切到无关目录，Act 解析相对只读目录，
    Assert 结果按数据目录父目录解析、不受 CWD 影响。"""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    data_dir = tmp_path / "app" / "data"

    resolved = _resolve_allowed_read_dirs(
        _sandbox_config(allowed_read_dirs=["./data/emoji/"]), data_dir
    )

    assert resolved == [(data_dir / "emoji").resolve()]
