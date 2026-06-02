from __future__ import annotations

import hashlib
import importlib
import importlib.util
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType


class PluginModuleImporter:
    def __init__(self) -> None:
        self.last_module_names: tuple[str, ...] = ()

    def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
        for module_name in sorted(module_names, key=len, reverse=True):
            for cached_name in list(sys.modules):
                if cached_name == module_name or cached_name.startswith(f"{module_name}."):
                    sys.modules.pop(cached_name, None)

    def import_module(self, path: Path, plugin_name: str) -> ModuleType:
        importlib.invalidate_caches()
        pycache = path.parent / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache, ignore_errors=True)
        before = {name for name in sys.modules if name.startswith("neobot_user_plugins.")}
        # 使用路径摘要生成模块名，避免同名插件或热重载时误复用旧模块。
        module_name = self.module_name(path, plugin_name)
        sys.modules.setdefault("neobot_user_plugins", ModuleType("neobot_user_plugins"))
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建插件模块 spec: {path}")
        module = importlib.util.module_from_spec(spec)
        if path.name == "__init__.py":
            module.__package__ = module_name
            module.__path__ = [str(path.parent)]
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        after = {
            name
            for name in sys.modules
            if name == module_name
            or name.startswith(f"{module_name}.")
            or (name not in before and name.startswith("neobot_user_plugins."))
        }
        self.last_module_names = tuple(sorted(after))
        return module

    def module_name(self, path: Path, plugin_name: str) -> str:
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        safe_name = re.sub(r"\W", "_", plugin_name)
        return f"neobot_user_plugins.{safe_name}_{digest}"
