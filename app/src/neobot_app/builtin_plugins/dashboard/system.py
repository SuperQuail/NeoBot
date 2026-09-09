"""系统资源采集（CPU / 内存 / 磁盘）。"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:  # psutil 是本体的间接依赖；缺失时退化为可用字段
    import psutil
except Exception:  # pragma: no cover - 仅在极简环境触发
    psutil = None  # type: ignore[assignment]

_BOOT_TS = time.time()


def prime() -> None:
    """预热 CPU 采样，避免首次调用返回 0。"""
    if psutil is None:
        return
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass


def _cpu_percent() -> float | None:
    if psutil is None:
        return None
    try:
        return float(psutil.cpu_percent(interval=None))
    except Exception:
        return None


def _load_average() -> list[float] | None:
    if psutil is None:
        return None
    try:
        return [round(float(item), 2) for item in psutil.getloadavg()]
    except Exception:
        return None


def _memory() -> dict[str, Any]:
    if psutil is None:
        return {}
    try:
        memory = psutil.virtual_memory()
    except Exception:
        return {}
    total_mb = memory.total / (1024 * 1024)
    used_mb = (memory.total - memory.available) / (1024 * 1024)
    return {
        "mem_total_mb": round(total_mb, 1),
        "mem_used_mb": round(used_mb, 1),
        "mem_percent": round(float(memory.percent), 1),
    }


def _disk(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(str(path))
    except OSError:
        return {}
    total_gb = usage.total / (1024**3)
    used_gb = usage.used / (1024**3)
    return {
        "disk_total_gb": round(total_gb, 2),
        "disk_used_gb": round(used_gb, 2),
        "disk_percent": round(used_gb / total_gb * 100, 1) if total_gb else None,
    }


def _process() -> dict[str, Any]:
    if psutil is None:
        return {}
    try:
        process = psutil.Process(os.getpid())
        with process.oneshot():
            memory_mb = process.memory_info().rss / (1024 * 1024)
            started = process.create_time()
            threads = process.num_threads()
    except Exception:
        return {}
    return {
        "process_memory_mb": round(memory_mb, 1),
        "process_threads": int(threads),
        "process_uptime_seconds": int(max(0, time.time() - started)),
    }


def snapshot(*, data_dir: Path) -> dict[str, Any]:
    """返回系统资源快照（缺失项为 None，前端显示为 —）。"""
    payload: dict[str, Any] = {
        "cpu_percent": _cpu_percent(),
        "cpu_count": (psutil.cpu_count() if psutil is not None else os.cpu_count()),
        "load_average": _load_average(),
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "python_impl": sys.implementation.name,
        "pid": os.getpid(),
        "boot_time": _BOOT_TS,
    }
    payload.update(_memory())
    payload.update(_disk(data_dir))
    payload.update(_process())
    return payload
