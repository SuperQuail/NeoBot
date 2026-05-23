from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Sequence

from neobot_contracts.ports.logging import Logger, NullLogger


@dataclass(frozen=True, slots=True)
class PythonDependencyInstallResult:
    requirements: tuple[str, ...]
    installed: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


class PythonDependencyInstaller:
    def __init__(self, *, logger: Logger | None = None, input_func: Callable[[str], str] | None = None) -> None:
        self._logger = logger or NullLogger()
        self._input = input_func or input

    def confirm_and_install(self, requirements: Sequence[str]) -> PythonDependencyInstallResult:
        unique = tuple(dict.fromkeys(str(item).strip() for item in requirements if str(item).strip()))
        if not unique:
            return PythonDependencyInstallResult(requirements=(), installed=False)

        prompt = "检测到插件需要安装以下 PyPI 依赖：\n"
        prompt += "\n".join(f"  - {requirement}" for requirement in unique)
        prompt += "\n是否使用当前 Python 环境自动安装？[y/N] "
        answer = self._input(prompt).strip().lower()
        if answer not in {"y", "yes"}:
            self._logger.info("用户取消安装插件 PyPI 依赖")
            return PythonDependencyInstallResult(requirements=unique, installed=False)

        command = [sys.executable, "-m", "pip", "install", *unique]
        self._logger.info(f"正在安装插件 PyPI 依赖: {' '.join(unique)}")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            self._logger.error(f"插件 PyPI 依赖安装失败: {completed.stderr}")
            return PythonDependencyInstallResult(
                requirements=unique,
                installed=False,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        return PythonDependencyInstallResult(
            requirements=unique,
            installed=True,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
