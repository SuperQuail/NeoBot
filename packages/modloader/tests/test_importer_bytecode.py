from __future__ import annotations

import os
import time
from pathlib import Path

from neobot_modloader.loading.importer import PluginModuleImporter


def test_reload_invalidates_nested_bytecode_with_equal_size_and_mtime(tmp_path: Path) -> None:
    package = tmp_path / "plugin"
    nested = package / "nested"
    nested.mkdir(parents=True)
    entry = package / "__init__.py"
    entry.write_text("from .nested import value\n", encoding="utf-8")
    child = nested / "__init__.py"
    child.write_text("value = 'old'\n", encoding="utf-8")
    stamp = int(time.time()) - 5
    os.utime(child, (stamp, stamp))
    importer = PluginModuleImporter()
    first = importer.import_module(entry, "example")
    first_names = importer.last_module_names
    try:
        child.write_text("value = 'new'\n", encoding="utf-8")
        os.utime(child, (stamp, stamp))
        second = importer.import_module(entry, "example")
        assert second.value == "new"
        assert first.value == "old"
    finally:
        importer.clear_module_cache(first_names)
        importer.clear_module_cache(importer.last_module_names)


def test_bytecode_cleanup_does_not_follow_directory_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "__pycache__"
    outside.mkdir(parents=True)
    cached = outside / "keep.pyc"
    cached.write_bytes(b"outside the plugin")
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "linked").symlink_to(outside.parent, target_is_directory=True)
    (root / "__pycache__").symlink_to(outside, target_is_directory=True)
    PluginModuleImporter._clear_bytecode(root / "__init__.py")
    assert cached.read_bytes() == b"outside the plugin"
