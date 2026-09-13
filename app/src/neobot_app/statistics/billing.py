"""可脚本化的消耗计费（spec(4) Part A）。

设计要点（见 ``features/spec(4)-scripted-billing-and-model-params/description.md`` §4.1-§4.4）：

- 计价脚本放在 ``<DATA_DIR>/Billing/``，按名加载（``<name>.py`` 或 ``<name>/__init__.py``），
  加载写法照抄 ``neobot_app.willing.service``，另补三处 willing 没有的能力：
  ``st_mtime_ns + st_size`` 变更自动重载、执行超时、异常/非法值兜底；
- 脚本只做**纯计算**：框架只注入纯数据 ``ctx``（``MappingProxyType`` + 顶层深拷贝），
  不注入 provider / DB session / 服务对象（R7）；
- 默认关闭（``[billing].enabled=false``）：此时不加载任何脚本、不建线程池，
  全部模型走内建线性公式（``builtin_cost``，与改造前逐字相同）；
- 任何失败都**不抛异常、不中断落库**：脚本缺失/加载失败/抛异常/超时/返回值非法
  一律回落内建公式，并把来源写成 ``builtin`` / ``fallback:*``（R3/R6）。
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import inspect
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.core.paths import get_data_dir

#: 来源闭集（见 §4.4「新增列」表）
SOURCE_BUILTIN = "builtin"
SOURCE_MISSING = "fallback:missing"
SOURCE_ERROR = "fallback:error"
SOURCE_TIMEOUT = "fallback:timeout"

#: ``cost_detail`` 序列化后的字符上限；超过即截断（永不因分项过大导致落库失败）
MAX_COST_DETAIL_CHARS = 8192

#: 默认超时（毫秒）；与 ``[billing].timeout_ms`` 默认值一致
DEFAULT_TIMEOUT_MS = 200

#: 常驻线程池大小 / 允许同时在跑（或排队）的求值上限
BILLING_MAX_WORKERS = 2
BILLING_MAX_INFLIGHT = 2

#: 脚本可读取的 usage 原始量（其余键不透传，保持 ctx 边界清晰）
_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "completion_tokens_details",
)

#: 模板脚本目录（随仓库分发，启动时同步到 <DATA_DIR>/Billing/）
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

#: 记录「本程序上次写入各模板的内容哈希」，用于判定用户是否改过模板文件
_TEMPLATE_MANIFEST = ".templates.json"

#: 进程内共享的计价脚本线程池：脚本是同步函数，UsageTracker.record 走
#: loop.run_in_executor；[billing].enabled=false 时不创建（零开销）。
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def get_billing_executor() -> ThreadPoolExecutor:
    """惰性创建进程内专用计价线程池（默认 2 线程）。"""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=BILLING_MAX_WORKERS,
                thread_name_prefix="billing",
            )
        return _EXECUTOR


def builtin_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    pricing: Any,
) -> float:
    """内建线性计费公式（**逐字**保留改造前 tracker.py 的实现）。"""
    effective_cache_miss = cache_miss_tokens if cache_miss_tokens > 0 else input_tokens
    return (
        cache_hit_tokens * float(getattr(pricing, "cache_hit_price_per_mtokens", 0.0) or 0.0)
        + effective_cache_miss * float(getattr(pricing, "input_price_per_mtokens", 0.0) or 0.0)
        + output_tokens * float(getattr(pricing, "output_price_per_mtokens", 0.0) or 0.0)
    ) / 1_000_000.0


@dataclass(frozen=True, slots=True)
class BillingSettings:
    """[billing] 段的运行时视图。"""

    enabled: bool = False
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    reload_on_change: bool = True
    record_detail: bool = True

    @property
    def timeout_seconds(self) -> float:
        return max(1, int(self.timeout_ms)) / 1000.0

    @classmethod
    def from_config(cls, config: Any) -> "BillingSettings":
        section = getattr(config, "billing", None) if config is not None else None
        if section is None:
            return cls()
        return cls(
            enabled=bool(getattr(section, "enabled", False)),
            timeout_ms=_coerce_int(
                getattr(section, "timeout_ms", DEFAULT_TIMEOUT_MS), DEFAULT_TIMEOUT_MS
            ),
            reload_on_change=bool(getattr(section, "reload_on_change", True)),
            record_detail=bool(getattr(section, "record_detail", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timeout_ms": self.timeout_ms,
            "reload_on_change": self.reload_on_change,
            "record_detail": self.record_detail,
        }


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class BillingOutcome:
    """一次计费求值的结果（含来源与分项）。"""

    cost_cny: float
    source: str = SOURCE_BUILTIN
    components: Mapping[str, float] | None = None
    note: str = ""
    detail_json: str | None = None
    elapsed_ms: float = 0.0
    error: str = ""

    @property
    def is_script(self) -> bool:
        return self.source.startswith("script:")

    def to_payload(self) -> dict[str, Any]:
        """面板 preview 用的载荷（分项为已解析的 dict）。"""
        return {
            "cost_cny": self.cost_cny,
            "source": self.source,
            "components": dict(self.components) if self.components else {},
            "note": self.note,
            "elapsed_ms": round(self.elapsed_ms, 4),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class _LoadedPolicy:
    name: str
    path: Path
    mtime_ns: int
    size: int
    compute: Callable[[Mapping[str, Any]], Any]


@dataclass
class _ScriptStat:
    """面板展示用的加载 / 求值状态。"""

    name: str
    path: str = ""
    ok: bool = False
    error: str = ""
    loaded_at: str = ""
    elapsed_ms: float = 0.0
    reload_count: int = 0
    #: 最近一次求值（含兜底）耗时与来源，供 GET /api/config/billing 展示
    last_eval_ms: float = 0.0
    last_source: str = ""
    eval_count: int = 0
    fallback_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "ok": self.ok,
            "error": self.error,
            "loaded_at": self.loaded_at,
            "elapsed_ms": round(self.elapsed_ms, 4),
            "reload_count": self.reload_count,
            "last_eval_ms": round(self.last_eval_ms, 4),
            "last_source": self.last_source,
            "eval_count": self.eval_count,
            "fallback_count": self.fallback_count,
        }


def freeze_context(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """把脚本输入冻结成只读映射（顶层 MappingProxyType + 深拷贝）。

    传副本而非引用，脚本即使改写嵌套结构也不会污染调用方状态。
    """
    return MappingProxyType({str(key): copy.deepcopy(value) for key, value in payload.items()})


def _plain(value: Any) -> Any:
    """把 dataclass / 映射转成脚本可直接读取的纯数据。"""
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return asdict(value)
        except Exception:  # pragma: no cover - asdict 对常规 dataclass 不会失败
            return {}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def build_billing_context(
    *,
    model_key: str,
    model_name: str,
    provider: str,
    model_type: str,
    module: str,
    usage: Mapping[str, Any],
    pricing: Any,
    settings: Any,
    billing_config: Mapping[str, Any] | None = None,
    conversation_kind: str = "",
    conversation_id: str = "",
    occurred_at: datetime | None = None,
) -> Mapping[str, Any]:
    """组装脚本 ctx（字段清单见 spec §4.2）。"""
    moment = occurred_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone()
    usage_payload = {
        key: usage.get(key) for key in _USAGE_KEYS if isinstance(usage, Mapping) and key in usage
    }
    payload: dict[str, Any] = {
        "model_key": str(model_key or ""),
        "model_name": str(model_name or ""),
        "provider": str(provider or ""),
        "model_type": str(model_type or "chat"),
        "module": str(module or ""),
        "usage": usage_payload,
        "pricing": _plain(pricing),
        "settings": _plain(settings),
        "billing_config": dict(billing_config or {}),
        "conversation": {"kind": str(conversation_kind or ""), "id": str(conversation_id or "")},
        "occurred_at": moment.isoformat(),
        "local_time": local.isoformat(),
        "tzname": local.tzname() or "",
    }
    return freeze_context(payload)


def _serialize_detail(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= MAX_COST_DETAIL_CHARS:
        return text
    head = json.dumps(
        {"truncated": True, "components": payload.get("components", {})},
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    if len(head) > MAX_COST_DETAIL_CHARS:
        head = json.dumps({"truncated": True}, separators=(",", ":"))
    return head[:MAX_COST_DETAIL_CHARS]


def _to_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


class BillingService:
    """<DATA_DIR>/Billing/ 脚本加载器 + 策略求值。"""

    def __init__(
        self,
        *,
        config: Any = None,
        config_provider: Callable[[], Any] | None = None,
        logger: Logger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._config_fixed = config
        self._config_provider = config_provider
        self._logger = logger or NullLogger()
        self._data_dir = Path(data_dir) if data_dir is not None else get_data_dir()
        self._custom_dir = self._data_dir / "Billing"
        try:
            self._custom_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - 目录不可写时只告警
            self._logger.warning("计费脚本目录创建失败", dir=str(self._custom_dir), error=str(exc))
        self._policies: dict[str, _LoadedPolicy] = {}
        self._stats: dict[str, _ScriptStat] = {}
        self._errors: dict[str, str] = {}
        #: 绑定了名字但文件不存在的脚本（用于区分 fallback:missing 与 fallback:error）
        self._missing: set[str] = set()
        self._lock = threading.RLock()
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self.sync_templates()

    # ------------------------------------------------------------------
    # 基础属性
    # ------------------------------------------------------------------

    @property
    def custom_dir(self) -> Path:
        return self._custom_dir

    def current_config(self) -> Any:
        if self._config_provider is not None:
            try:
                return self._config_provider()
            except Exception:  # pragma: no cover - 配置代理异常时退回固定配置
                return self._config_fixed
        return self._config_fixed

    @property
    def settings(self) -> BillingSettings:
        """每次现取 [billing]，改配置无需重启（R4/Q13）。"""
        return BillingSettings.from_config(self.current_config())

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
        if not _TEMPLATES_DIR.is_dir():
            return []
        return sorted(item.stem for item in _TEMPLATES_DIR.glob("*.py"))

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

    def bindings(self, targets: Iterable[tuple[str, str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
        """面板用：每个模型条目的绑定情况（model_key → 脚本 / 是否可用 / 最近耗时）。"""
        items: list[dict[str, Any]] = []
        for model_key, script, config in targets:
            name = str(script or "").strip()
            if not name:
                items.append({
                    "model_key": model_key,
                    "billing_script": "",
                    "billing_config": dict(config or {}),
                    "source": SOURCE_BUILTIN,
                    "available": True,
                    "error": "",
                })
                continue
            status = self._stats.get(name)
            policy = self.ensure_policy(name) if self.settings.enabled else None
            error = self._errors.get(name, "")
            items.append({
                "model_key": model_key,
                "billing_script": name,
                "billing_config": dict(config or {}),
                "source": f"script:{name}" if policy is not None else (
                    SOURCE_MISSING if name in self._missing else SOURCE_ERROR
                ),
                "available": policy is not None,
                "error": error,
                "loaded_at": status.loaded_at if status else "",
                "last_eval_ms": round(status.last_eval_ms, 4) if status else 0.0,
                "eval_count": status.eval_count if status else 0,
            })
        return items

    # ------------------------------------------------------------------
    # 求值
    # ------------------------------------------------------------------

    def _acquire_slot(self) -> bool:
        with self._inflight_lock:
            if self._inflight >= BILLING_MAX_INFLIGHT:
                return False
            self._inflight += 1
            return True

    def _release_slot(self) -> None:
        with self._inflight_lock:
            if self._inflight > 0:
                self._inflight -= 1

    def _track_future(self, future: Any) -> None:
        """把「槽位」绑定到**任务真正结束**：脚本超时后线程仍占用线程池，

        只有等它结束（或提交前被取消）才归还槽位，从而兑现「池内任务上限」的兜底。
        """
        future.add_done_callback(lambda _fut: self._release_slot())

    def _eval_source_for_missing(self, name: str) -> str:
        return SOURCE_MISSING if name in self._missing else SOURCE_ERROR

    def _record_eval(self, name: str, outcome: BillingOutcome) -> None:
        with self._lock:
            record = self._stats.setdefault(name, _ScriptStat(name=name))
            record.last_eval_ms = outcome.elapsed_ms
            record.last_source = outcome.source
            record.eval_count += 1
            if not outcome.is_script:
                record.fallback_count += 1

    async def compute_cost(
        self,
        *,
        script_name: str,
        ctx: Mapping[str, Any],
        fallback_cost: float,
    ) -> BillingOutcome:
        """求值入口：任何失败都回落到 fallback_cost，**从不抛异常**（R3）。"""
        settings = self.settings
        name = str(script_name or "").strip()
        if not settings.enabled or not name:
            return BillingOutcome(cost_cny=fallback_cost, source=SOURCE_BUILTIN)

        policy = self.ensure_policy(name)
        if policy is None:
            outcome = self._fallback(
                settings,
                self._eval_source_for_missing(name),
                fallback_cost,
                self._errors.get(name, ""),
            )
            self._record_eval(name, outcome)
            return outcome

        if not self._acquire_slot():
            self._logger.warning(
                "计费脚本并发已达上限，回落到内建公式",
                script=name,
                limit=BILLING_MAX_INFLIGHT,
            )
            outcome = self._fallback(
                settings, SOURCE_ERROR, fallback_cost, "billing pool saturated"
            )
            self._record_eval(name, outcome)
            return outcome

        started = time.perf_counter()
        tracked = False
        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(get_billing_executor(), policy.compute, ctx)
            # 槽位在**任务真正结束**时归还（超时后线程仍在跑，槽位不释放）
            self._track_future(future)
            tracked = True
            result = await asyncio.wait_for(future, timeout=settings.timeout_seconds)
        except (asyncio.TimeoutError, TimeoutError):
            elapsed = (time.perf_counter() - started) * 1000.0
            self._logger.warning(
                "计费脚本求值超时，回落到内建公式",
                script=name,
                timeout_ms=settings.timeout_ms,
                elapsed_ms=round(elapsed, 3),
            )
            outcome = self._fallback(
                settings,
                SOURCE_TIMEOUT,
                fallback_cost,
                f"timeout after {settings.timeout_ms}ms",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            if not tracked:  # pragma: no cover - 线程池/事件循环异常时才走到
                self._release_slot()
            self._logger.warning(
                "计费脚本求值异常，回落到内建公式",
                script=name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            outcome = self._fallback(
                settings,
                SOURCE_ERROR,
                fallback_cost,
                f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome

        elapsed = (time.perf_counter() - started) * 1000.0
        outcome = self._interpret(
            result,
            script_name=name,
            fallback_cost=fallback_cost,
            settings=settings,
            elapsed_ms=elapsed,
        )
        self._record_eval(name, outcome)
        return outcome

    def preview(
        self,
        *,
        script_name: str,
        ctx: Mapping[str, Any],
        fallback_cost: float = 0.0,
        timeout_ms: int | None = None,
    ) -> BillingOutcome:
        """只读试算（同步）：不写库、不改任何状态；超时同样兜底（§4.4 preview）。

        与 ``compute_cost`` 的差别：**不检查** ``[billing].enabled``——保存配置前
        必须能先试算脚本（A1 的两次对照即走这里）。
        """
        settings = self.settings
        name = str(script_name or "").strip()
        if not name:
            return BillingOutcome(cost_cny=fallback_cost, source=SOURCE_BUILTIN)
        policy = self.ensure_policy(name)
        if policy is None:
            outcome = self._fallback(
                settings,
                self._eval_source_for_missing(name),
                fallback_cost,
                self._errors.get(name, ""),
            )
            self._record_eval(name, outcome)
            return outcome

        limit_ms = max(
            1, _coerce_int(timeout_ms, settings.timeout_ms) if timeout_ms else settings.timeout_ms
        )
        if not self._acquire_slot():
            outcome = self._fallback(
                settings, SOURCE_ERROR, fallback_cost, "billing pool saturated"
            )
            self._record_eval(name, outcome)
            return outcome
        started = time.perf_counter()
        future = get_billing_executor().submit(policy.compute, ctx)
        self._track_future(future)
        try:
            result = future.result(timeout=limit_ms / 1000.0)
        except BaseException as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            timed_out = isinstance(exc, TimeoutError)
            outcome = self._fallback(
                settings,
                SOURCE_TIMEOUT if timed_out else SOURCE_ERROR,
                fallback_cost,
                f"timeout after {limit_ms}ms" if timed_out else f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome
        elapsed = (time.perf_counter() - started) * 1000.0
        outcome = self._interpret(
            result,
            script_name=name,
            fallback_cost=fallback_cost,
            settings=settings,
            elapsed_ms=elapsed,
        )
        self._record_eval(name, outcome)
        return outcome

    def _fallback(
        self,
        settings: BillingSettings,
        source: str,
        fallback_cost: float,
        error: str,
        *,
        elapsed_ms: float = 0.0,
    ) -> BillingOutcome:
        detail = None
        if settings.record_detail and error:
            detail = _serialize_detail({"error": error})
        return BillingOutcome(
            cost_cny=fallback_cost,
            source=source,
            detail_json=detail,
            elapsed_ms=elapsed_ms,
            error=error,
        )

    def _interpret(
        self,
        result: Any,
        *,
        script_name: str,
        fallback_cost: float,
        settings: BillingSettings,
        elapsed_ms: float,
    ) -> BillingOutcome:
        components: dict[str, float] | None = None
        note = ""
        source = f"script:{script_name}"

        if isinstance(result, Mapping):
            cost = _to_finite_float(result.get("cost_cny"))
            if cost is None:
                return self._fallback(
                    settings,
                    SOURCE_ERROR,
                    fallback_cost,
                    "脚本返回值缺少合法的 cost_cny",
                    elapsed_ms=elapsed_ms,
                )
            raw_components = result.get("components")
            if isinstance(raw_components, Mapping):
                cleaned = {
                    str(key): number
                    for key, number in (
                        (key, _to_finite_float(item)) for key, item in raw_components.items()
                    )
                    if number is not None
                }
                components = cleaned or None
            raw_note = result.get("note")
            if isinstance(raw_note, str):
                note = raw_note.strip()
            raw_source = result.get("source")
            if isinstance(raw_source, str) and raw_source.strip():
                source = f"script:{raw_source.strip()}"
        else:
            cost = _to_finite_float(result)
            if cost is None:
                return self._fallback(
                    settings,
                    SOURCE_ERROR,
                    fallback_cost,
                    "脚本返回值不是有限数值",
                    elapsed_ms=elapsed_ms,
                )

        detail = None
        if settings.record_detail:
            payload: dict[str, Any] = {}
            if components:
                payload["components"] = components
            if note:
                payload["note"] = note
            if payload:
                detail = _serialize_detail(payload)
        return BillingOutcome(
            cost_cny=cost,
            source=source,
            components=components,
            note=note,
            detail_json=detail,
            elapsed_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # 面板
    # ------------------------------------------------------------------

    def script_status(self, name: str) -> dict[str, Any] | None:
        record = self._stats.get(str(name or "").strip())
        return record.to_dict() if record is not None else None

    def describe(self) -> dict[str, Any]:
        """GET /api/config/billing 的主体。"""
        settings = self.settings
        return {
            "enabled": settings.enabled,
            "timeout_ms": settings.timeout_ms,
            "reload_on_change": settings.reload_on_change,
            "record_detail": settings.record_detail,
            "directory": str(self._custom_dir),
            "scripts": self.available_scripts(),
            "templates": self.template_names(),
            "policies": {name: self._stats[name].to_dict() for name in sorted(self._stats)},
            "errors": dict(self._errors),
        }
