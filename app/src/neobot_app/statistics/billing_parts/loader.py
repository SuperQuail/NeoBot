"""BillingService 的模板同步与脚本加载/重载。"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .constants import _TEMPLATE_MANIFEST, _BUILTIN_PATH, _TEMPLATES_DIR
from .core import BUILTIN_SCRIPTS, _LoadedPolicy, _ScriptStat

class LoaderMixin:

    # ------------------------------------------------------------------
    # 模板同步 / 脚本清单
    # ------------------------------------------------------------------

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _manifest_path(self) -> Path:
        return self._custom_dir / _TEMPLATE_MANIFEST

    def _read_manifest(self) -> dict[str, str]:
        """读取「本程序上次写入的模板内容哈希」清单（R5/A13）。"""
        path = self._manifest_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - 清单损坏时按空处理
            return {}
        if not isinstance(data, dict):  # pragma: no cover - 非法结构
            return {}
        return {str(key): str(value) for key, value in data.items()}

    def _write_manifest(self, manifest: Mapping[str, str]) -> None:
        try:
            self._manifest_path().write_text(
                json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover - 磁盘错误
            self._logger.debug("计费模板清单写入失败", error=str(exc))

    def template_names(self) -> list[str]:
        """面板可选的脚本名：**内置脚本** + templates/ 下的模板。"""
        names: set[str] = set(BUILTIN_SCRIPTS)
        if _TEMPLATES_DIR.is_dir():
            names |= {item.stem for item in _TEMPLATES_DIR.glob("*.py")}
        return sorted(names)

    def sync_templates(self) -> list[str]:
        """把内置模板同步到 <DATA_DIR>/Billing/（**不覆盖用户改动**，A13）。

        覆盖判定（三者之一）：
        1. 目标不存在 → 写入；
        2. 目标内容与模板一致 → 无需动作；
        3. 目标内容与本程序**上次写入**的内容一致（用户没改过）→ 用新模板覆盖；
        否则视为用户自行修改过，**保持原样**并只记日志。
        """
        if not _TEMPLATES_DIR.is_dir():  # pragma: no cover - 源码树里必然存在
            self._logger.warning("计费模板目录缺失", dir=str(_TEMPLATES_DIR))
            return []
        manifest = self._read_manifest()
        written: list[str] = []
        for template in sorted(_TEMPLATES_DIR.glob("*.py")):
            target = self._custom_dir / template.name
            try:
                template_hash = self._sha256_file(template)
                if target.exists():
                    current_hash = self._sha256_file(target)
                    if current_hash == template_hash:
                        manifest[template.name] = template_hash
                        continue
                    if manifest.get(template.name) != current_hash:
                        self._logger.info(
                            "计费模板已被用户修改，保持原样不覆盖",
                            template=template.name,
                            target_path=str(target),
                        )
                        continue
                target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError as exc:  # pragma: no cover - 磁盘错误
                self._logger.warning(
                    "计费模板同步失败", template=template.name, error=str(exc)
                )
                continue
            manifest[template.name] = template_hash
            written.append(template.name)
            self._logger.info("已同步计费模板", target_path=str(target))
        self._write_manifest(manifest)
        return written

    def _resolve_script_path(self, name: str) -> Path | None:
        safe = str(name or "").strip()
        if not safe or safe in {".", ".."} or Path(safe).name != safe:
            return None
        for candidate in (
            self._custom_dir / f"{safe}.py",
            self._custom_dir / safe / "__init__.py",
        ):
            if candidate.exists():
                return candidate
        return None

    def list_scripts(self) -> list[str]:
        """可用脚本名（目录内 *.py 与 <name>/__init__.py）。"""
        names: set[str] = set()
        if self._custom_dir.is_dir():
            for item in self._custom_dir.iterdir():
                if item.is_file() and item.suffix == ".py" and item.stem != "__init__":
                    names.add(item.stem)
                elif item.is_dir() and (item / "__init__.py").exists():
                    names.add(item.name)
        return sorted(names)

    def available_scripts(self) -> list[str]:
        return sorted(set(self.list_scripts()) | set(self.template_names()))

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def _import_module(self, name: str, path: Path) -> Any:
        module_name = f"neobot_app_custom_billing_{name}"
        kwargs: dict[str, Any] = {}
        if path.name == "__init__.py":
            kwargs["submodule_search_locations"] = [str(path.parent)]
        spec = importlib.util.spec_from_file_location(module_name, path, **kwargs)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load billing script: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _instantiate(self, candidate: Any) -> Any:
        if not inspect.isclass(candidate):
            return candidate
        kwargs: dict[str, Any] = {}
        parameters: Any
        try:
            parameters = inspect.signature(candidate).parameters
        except (TypeError, ValueError):  # pragma: no cover - 内建类型无签名
            parameters = {}
        if "config" in parameters:
            kwargs["config"] = self.current_config()
        if "logger" in parameters:
            logger = self._logger
            binder = getattr(logger, "bind", None)
            kwargs["logger"] = binder(component="billing.custom") if callable(binder) else logger
        return candidate(**kwargs)

    @staticmethod
    def _resolve_entry(module: Any, path: Path) -> Callable[[Mapping[str, Any]], Any]:
        """解析脚本入口：函数式 compute_cost(ctx) 或类式 BillingPolicy.compute(ctx)。"""
        func = getattr(module, "compute_cost", None)
        if callable(func):
            return func
        policy_obj = getattr(module, "BillingPolicy", None)
        if policy_obj is None:
            raise AttributeError(
                f"计价脚本 {path.name} 必须定义 compute_cost(ctx) 或 BillingPolicy.compute(ctx)"
            )
        if inspect.isclass(policy_obj):
            return policy_obj
        # 允许直接导出实例（与 willing 的「实例或类」同构）
        compute = getattr(policy_obj, "compute", None)
        if callable(compute):
            return compute
        raise TypeError(
            f"计价脚本 {path.name} 的 BillingPolicy 必须提供 compute(ctx)"
        )

    def _load_policy(self, name: str, *, force: bool = False) -> _LoadedPolicy | None:
        path = self._resolve_script_path(name)
        if path is None:
            builtin = BUILTIN_SCRIPTS.get(name)
            if builtin is not None:
                # 内置脚本：不需要用户脚本文件。mtime/size 恒为 0（内容随代码走）。
                policy = _LoadedPolicy(
                    name=name, path=_BUILTIN_PATH, mtime_ns=0, size=0, compute=builtin
                )
                with self._lock:
                    self._policies[name] = policy
                    self._missing.discard(name)
                record = self._stats.setdefault(name, _ScriptStat(name=name))
                record.ok = True
                record.path = str(_BUILTIN_PATH)
                record.error = ""
                record.loaded_at = datetime.now(timezone.utc).isoformat()
                self._errors.pop(name, None)
                return policy
            self._errors[name] = f"脚本 {name} 不存在于 {self._custom_dir}"
            with self._lock:
                self._missing.add(name)
            stat_record = self._stats.setdefault(name, _ScriptStat(name=name))
            stat_record.ok = False
            stat_record.error = self._errors[name]
            return None

        try:
            file_stat = path.stat()
        except OSError as exc:  # pragma: no cover - 文件被并发删除
            self._errors[name] = f"{type(exc).__name__}: {exc}"
            return None

        with self._lock:
            existing = self._policies.get(name)
        if (
            not force
            and existing is not None
            and existing.path == path
            and existing.mtime_ns == file_stat.st_mtime_ns
            and existing.size == file_stat.st_size
        ):
            return existing

        started = time.perf_counter()
        try:
            module = self._import_module(name, path)
            entry: Any = self._resolve_entry(module, path)
            if inspect.isclass(entry):
                entry = getattr(self._instantiate(entry), "compute", None)
            if not callable(entry):
                raise TypeError("BillingPolicy 必须提供 compute(ctx)")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._errors[name] = message
            record = self._stats.setdefault(name, _ScriptStat(name=name))
            record.ok = False
            record.path = str(path)
            record.error = message
            self._logger.warning(
                "计费脚本加载失败，保留旧策略",
                script=name,
                path=str(path),
                error=message,
            )
            return existing

        policy = _LoadedPolicy(
            name=name,
            path=path,
            mtime_ns=file_stat.st_mtime_ns,
            size=file_stat.st_size,
            compute=entry,
        )
        with self._lock:
            self._policies[name] = policy
            self._missing.discard(name)
        record = self._stats.setdefault(name, _ScriptStat(name=name))
        record.ok = True
        record.path = str(path)
        record.error = ""
        record.elapsed_ms = (time.perf_counter() - started) * 1000.0
        record.loaded_at = datetime.now(timezone.utc).isoformat()
        record.reload_count += 1
        self._errors.pop(name, None)
        return policy

    def ensure_policy(self, name: str) -> _LoadedPolicy | None:
        """按需加载；reload_on_change 时以 mtime_ns + size 判定是否重载（R4）。"""
        key = str(name or "").strip()
        if not key:
            return None
        if self.settings.reload_on_change:
            return self._load_policy(key)
        with self._lock:
            policy = self._policies.get(key)
        if policy is not None:
            return policy
        return self._load_policy(key)

    def reload_scripts(self, names: Iterable[str] | None = None) -> dict[str, Any]:
        """显式重载：names 为空时重载已加载的全部脚本（A12）。"""
        if names is None:
            with self._lock:
                targets = sorted(self._policies)
            if not targets:
                targets = self.list_scripts()
        else:
            targets = sorted({str(item).strip() for item in names if str(item).strip()})
        self.sync_templates()
        result: dict[str, Any] = {}
        for name in targets:
            policy = self._load_policy(name, force=True)
            record = self._stats.get(name)
            error = self._errors.get(name, "")
            result[name] = {
                "ok": policy is not None and not error,
                "error": error,
                "path": str(policy.path) if policy is not None else (record.path if record else ""),
            }
        return {
            "reloaded": sorted(result),
            "results": result,
            "errors": {name: info["error"] for name, info in result.items() if not info["ok"]},
        }

    def warmup(self, names: Iterable[str]) -> dict[str, Any]:
        """启动装配期按「注册表里出现过的 billing_script 名字集合」去重预加载（§4.2）。"""
        result: dict[str, Any] = {}
        for name in sorted({str(item or "").strip() for item in names if str(item or "").strip()}):
            policy = self._load_policy(name)
            result[name] = {
                "ok": policy is not None,
                "error": self._errors.get(name, ""),
                "path": str(policy.path) if policy is not None else "",
            }
        return result
