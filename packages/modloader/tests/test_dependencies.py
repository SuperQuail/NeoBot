from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from neobot_modloader.dependencies import PythonDependencyInstaller


class FakeLogger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def _interactive(installer: PythonDependencyInstaller):
    """让安装流程认为当前有交互终端（单测里 stdin 不是 tty）。"""
    return patch.object(installer, "_interactive", return_value=True)


class PythonDependencyInstallerTest(unittest.TestCase):
    """同步入口（启动装配期使用）。"""

    def test_rejecting_prompt_does_not_install(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "n")
        with _interactive(installer), patch("subprocess.run") as run:
            result = installer.confirm_and_install_sync(["requests>=2"])
        self.assertFalse(result.installed)
        run.assert_not_called()

    def test_accepting_prompt_runs_pip(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["python"], 0, stdout="ok", stderr="")
        with _interactive(installer), patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install_sync(["requests>=2", "requests>=2"])
        self.assertTrue(result.installed)
        self.assertEqual(result.requirements, ("requests>=2",))
        args = run.call_args.args[0]
        self.assertEqual(args[-1], "requests>=2")
        self.assertIn("pip", args)
        self.assertEqual(result.command, tuple(args))

    def test_failed_install_returns_error_result(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "yes")
        completed = subprocess.CompletedProcess(["python"], 1, stdout="", stderr="boom")
        with _interactive(installer), patch("subprocess.run", return_value=completed):
            result = installer.confirm_and_install_sync(["missing-package"])
        self.assertFalse(result.installed)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "boom")

    def test_uses_uv_pip_when_python_has_no_pip(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["uv"], 0, stdout="ok", stderr="")

        with _interactive(installer), patch.object(
            installer, "_running_under_uv", return_value=False
        ), patch.object(
            installer, "_python_has_pip", return_value=False
        ), patch("shutil.which", return_value="uv"), patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install_sync(["pyfiglet"])

        self.assertTrue(result.installed)
        self.assertEqual(run.call_args.args[0], ["uv", "pip", "install", "pyfiglet"])

    def test_prefers_uv_pip_inside_uv_environment(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["uv"], 0, stdout="ok", stderr="")

        with _interactive(installer), patch.object(
            installer, "_running_under_uv", return_value=True
        ), patch.object(
            installer, "_python_has_pip", return_value=True
        ), patch("shutil.which", return_value="uv"), patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install_sync(["pyfiglet"])

        self.assertTrue(result.installed)
        self.assertEqual(run.call_args.args[0], ["uv", "pip", "install", "pyfiglet"])


class PythonDependencyInstallerSafetyTest(unittest.TestCase):
    """依赖串校验 / 无终端跳过 / 子进程超时。"""

    def test_rejects_pip_option_injection(self) -> None:
        """plugin.toml 里的依赖串不能变成 pip 选项（依赖混淆）。"""
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        with _interactive(installer), patch("subprocess.run") as run:
            result = installer.confirm_and_install_sync(
                ["--index-url=https://evil.example/simple", "requests>=2"]
            )

        self.assertFalse(result.installed)
        run.assert_not_called()
        self.assertIn("非法", result.stderr)

    def test_rejects_requirement_with_whitespace(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        with _interactive(installer), patch("subprocess.run") as run:
            result = installer.confirm_and_install_sync(["requests ; rm -rf /"])

        self.assertFalse(result.installed)
        run.assert_not_called()

    def test_skips_without_interactive_terminal(self) -> None:
        """无 tty（systemd/Docker/面板触发）时不再 input()，避免 EOFError 冲掉启动。"""
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        with patch.object(installer, "_interactive", return_value=False), patch(
            "subprocess.run"
        ) as run:
            result = installer.confirm_and_install_sync(["requests>=2"])

        self.assertFalse(result.installed)
        run.assert_not_called()
        self.assertEqual(result.stderr, "no interactive terminal")

    def test_install_command_has_timeout(self) -> None:
        from neobot_modloader.dependencies import INSTALL_TIMEOUT_SECONDS

        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["python"], 0, stdout="ok", stderr="")
        with _interactive(installer), patch("subprocess.run", return_value=completed) as run:
            installer.confirm_and_install_sync(["requests>=2"])

        self.assertEqual(run.call_args.kwargs.get("timeout"), INSTALL_TIMEOUT_SECONDS)

    def test_install_timeout_returns_failure(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        with _interactive(installer), patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=1),
        ):
            result = installer.confirm_and_install_sync(["requests>=2"])

        self.assertFalse(result.installed)
        self.assertIn("超时", result.stderr)


class PythonDependencyInstallerAsyncTest(unittest.IsolatedAsyncioTestCase):
    """异步入口（运行期：面板安装/热重载）。"""

    async def test_async_entry_installs(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["python"], 0, stdout="ok", stderr="")
        with _interactive(installer), patch("subprocess.run", return_value=completed):
            result = await installer.confirm_and_install(["requests>=2"])

        self.assertTrue(result.installed)

    async def test_async_entry_rejects_invalid_requirement(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        with _interactive(installer), patch("subprocess.run") as run:
            result = await installer.confirm_and_install(["-e", "."])

        self.assertFalse(result.installed)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
