from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Sequence

from neobot_contracts.ports.logging import Logger, NullLogger

#: pip 安装超时（秒）：避免插件依赖安装无限期挂住调用方
INSTALL_TIMEOUT_SECONDS = 600


def _is_valid_requirement(item: str) -> bool:
    """插件声明的依赖条目必须是普通需求串，不能是 pip 选项。

    历史上这些字符串会被直接拼进 ``pip install`` 的 argv，于是
    ``--index-url=https://evil/simple``、``-r other.txt`` 这类条目会被 pip
    当成选项解析（依赖混淆 / 任意包源 / 读任意文件）。这里做结构性拦截：
    拒绝以 ``-`` 开头、含空白或首尾有空白的条目。
    """
    if not item or item != item.strip():
        return False
    if item.startswith("-"):
        return False
    return not any(char.isspace() for char in item)


@dataclass(frozen=True, slots=True)
class PythonDependencyInstallResult:
    requirements: tuple[str, ...]
    installed: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    command: tuple[str, ...] = ()


class PythonDependencyInstaller:
    def __init__(self, *, logger: Logger | None = None, input_func: Callable[[str], str] | None = None) -> None:
        self._logger = logger or NullLogger()
        self._input = input_func or input

    # ── 对外入口 ────────────────────────────────────────────────────

    async def confirm_and_install(
        self, requirements: Sequence[str]
    ) -> PythonDependencyInstallResult:
        """异步入口：等待用户确认并安装。

        整个流程（等输入、探测 pip、执行 pip）都在工作线程完成——调用方位于
        事件循环中（面板安装/热重载插件），同步的 ``input()`` 与
        ``subprocess.run`` 会把整个 Bot 卡住。
        """
        return await asyncio.to_thread(self._install_flow, tuple(requirements))

    def confirm_and_install_sync(
        self, requirements: Sequence[str]
    ) -> PythonDependencyInstallResult:
        """同步入口：**仅供启动装配期使用**。

        启动路径（``PluginRuntime.load_all``）本身是同步装配代码，调用点还没有
        需要并发服务的任务；无交互终端时会直接跳过（不再抛 EOFError 冲掉启动）。
        线上运行期请使用 ``confirm_and_install``，不要用本方法阻塞事件循环。
        """
        return self._install_flow(tuple(requirements))

    # ── 实现 ────────────────────────────────────────────────────────

    def _install_flow(
        self, requirements: Sequence[str]
    ) -> PythonDependencyInstallResult:
        unique = tuple(dict.fromkeys(str(item).strip() for item in requirements if str(item).strip()))
        if not unique:
            return PythonDependencyInstallResult(requirements=(), installed=False)

        invalid = tuple(item for item in unique if not _is_valid_requirement(item))
        if invalid:
            self._logger.error(f"插件依赖条目非法，已拒绝安装: {', '.join(invalid)}")
            return PythonDependencyInstallResult(
                requirements=unique,
                installed=False,
                stderr="非法的依赖条目：不接受 pip 选项、含空白的字符串",
            )

        if not self._interactive():
            self._logger.warning(
                "当前环境没有可交互终端，跳过插件 PyPI 依赖安装"
                f"（缺失: {', '.join(unique)}）"
            )
            return PythonDependencyInstallResult(
                requirements=unique,
                installed=False,
                stderr="no interactive terminal",
            )

        prompt = "检测到插件需要安装以下 PyPI 依赖：\n"
        prompt += "\n".join(f"  - {requirement}" for requirement in unique)
        prompt += "\n是否使用当前 Python 环境自动安装？[y/N] "
        answer = self._input(prompt).strip().lower()
        if answer not in {"y", "yes"}:
            self._logger.info("用户取消安装插件 PyPI 依赖")
            return PythonDependencyInstallResult(requirements=unique, installed=False)

        command = self._install_command(unique)
        self._logger.info(f"正在安装插件 PyPI 依赖: {' '.join(unique)}")
        self._logger.info(f"安装命令: {' '.join(command)}")
        try:
            completed = self._run_command(command)
        except subprocess.TimeoutExpired:
            self._logger.error(
                f"插件 PyPI 依赖安装超时（>{INSTALL_TIMEOUT_SECONDS}s），已放弃"
            )
            return PythonDependencyInstallResult(
                requirements=unique,
                installed=False,
                stderr=f"安装超时（>{INSTALL_TIMEOUT_SECONDS}s）",
                command=tuple(command),
            )
        if completed.returncode != 0:
            self._logger.error(f"插件 PyPI 依赖安装失败: {completed.stderr}")
            return PythonDependencyInstallResult(
                requirements=unique,
                installed=False,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                command=tuple(command),
            )
        return PythonDependencyInstallResult(
            requirements=unique,
            installed=True,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            command=tuple(command),
        )

    def _interactive(self) -> bool:
        """是否可以安全地向用户提问（无 tty 时提问会抛 EOFError 或永久阻塞）。"""
        try:
            return bool(sys.stdin is not None and sys.stdin.isatty())
        except Exception:
            return False

    def _run_command(self, command: list[str]) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )

    def _install_command(self, requirements: tuple[str, ...]) -> list[str]:
        if self._running_under_uv() and shutil.which("uv") is not None:
            return ["uv", "pip", "install", *requirements]
        if self._python_has_pip():
            return [sys.executable, "-m", "pip", "install", *requirements]
        if shutil.which("uv") is not None:
            return ["uv", "pip", "install", *requirements]
        return [sys.executable, "-m", "pip", "install", *requirements]

    def _running_under_uv(self) -> bool:
        executable = os.path.basename(sys.executable).casefold()
        return "UV" in os.environ or "uv" in os.environ.get("VIRTUAL_ENV", "").casefold() or executable.startswith("uv")

    def _python_has_pip(self) -> bool:
        # 探测失败（无 pip / 超时 / 无法启动）都按「没有 pip」处理：
        # 这个探测本身不该把异常抛给插件加载流程。
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0
