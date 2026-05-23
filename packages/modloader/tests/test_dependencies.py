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

    def test_failed_install_returns_error_result(self) -> None:
        installer = PythonDependencyInstaller(input_func=lambda prompt: "yes")
        completed = subprocess.CompletedProcess(["python"], 1, stdout="", stderr="boom")
        with patch("subprocess.run", return_value=completed):
            result = installer.confirm_and_install(["missing-package"])
        self.assertFalse(result.installed)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "boom")


if __name__ == "__main__":
    unittest.main()
