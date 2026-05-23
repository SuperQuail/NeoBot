from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from neobot_modloader.dependencies import PythonDependencyInstaller


class FakeLogger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


class PythonDependencyInstallerTest(unittest.TestCase):
    def test_rejecting_prompt_does_not_install(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "n")
        with patch("subprocess.run") as run:
            result = installer.confirm_and_install(["requests>=2"])
        self.assertFalse(result.installed)
        run.assert_not_called()

    def test_accepting_prompt_runs_pip(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["python"], 0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install(["requests>=2", "requests>=2"])
        self.assertTrue(result.installed)
        self.assertEqual(result.requirements, ("requests>=2",))
        args = run.call_args.args[0]
        self.assertEqual(args[-1], "requests>=2")
        self.assertIn("pip", args)
        self.assertEqual(result.command, tuple(args))

    def test_failed_install_returns_error_result(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "yes")
        completed = subprocess.CompletedProcess(["python"], 1, stdout="", stderr="boom")
        with patch("subprocess.run", return_value=completed):
            result = installer.confirm_and_install(["missing-package"])
        self.assertFalse(result.installed)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "boom")

    def test_uses_uv_pip_when_python_has_no_pip(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["uv"], 0, stdout="ok", stderr="")

        with patch.object(installer, "_running_under_uv", return_value=False), patch.object(
            installer, "_python_has_pip", return_value=False
        ), patch("shutil.which", return_value="uv"), patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install(["pyfiglet"])

        self.assertTrue(result.installed)
        self.assertEqual(run.call_args.args[0], ["uv", "pip", "install", "pyfiglet"])

    def test_prefers_uv_pip_inside_uv_environment(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "y")
        completed = subprocess.CompletedProcess(["uv"], 0, stdout="ok", stderr="")

        with patch.object(installer, "_running_under_uv", return_value=True), patch.object(
            installer, "_python_has_pip", return_value=True
        ), patch("shutil.which", return_value="uv"), patch("subprocess.run", return_value=completed) as run:
            result = installer.confirm_and_install(["pyfiglet"])

        self.assertTrue(result.installed)
        self.assertEqual(run.call_args.args[0], ["uv", "pip", "install", "pyfiglet"])


if __name__ == "__main__":
    unittest.main()
