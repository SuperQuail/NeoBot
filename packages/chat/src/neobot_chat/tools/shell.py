"""持久化 Shell 会话管理"""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path
from typing import Any


class PersistentShell:
    """持久化 Shell 进程，保持工作目录和环境变量状态"""

    def __init__(self, cwd: Path, timeout: int = 30, output: Any | None = None):
        self.cwd = cwd
        self.timeout = timeout
        self.output = output
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._is_windows = platform.system() == "Windows"

    async def start(self) -> None:
        """启动 shell 进程"""
        if self._process and self._process.returncode is None:
            return

        shell_cmd = "cmd.exe" if self._is_windows else "/bin/bash"
        self._process = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.cwd),
        )

    async def execute(self, command: str) -> str:
        """在持久 shell 中执行命令"""
        async with self._lock:
            await self.start()

            if not self._process or not self._process.stdin or not self._process.stdout:
                return "Error: Shell process not available"

            # 使用唯一标记来分隔命令输出
            marker = f"__CMD_END_{id(command)}__"
            if self._is_windows:
                full_command = f"{command}\necho {marker}\n"
            else:
                full_command = f"{command}\necho {marker}\n"

            try:
                self._process.stdin.write(full_command.encode())
                await self._process.stdin.drain()

                output_lines = []
                while True:
                    line = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=self.timeout
                    )
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if decoded == marker:
                        break
                    output_lines.append(decoded)

                result = "\n".join(output_lines) or "(no output)"
                self._write_output(result, channel="stdout", command=command)
                return result

            except asyncio.TimeoutError:
                await self.close()
                result = f"Error: Command timed out after {self.timeout}s"
                self._write_output(result, channel="stderr", command=command)
                return result
            except Exception as e:
                await self.close()
                result = f"Error: {type(e).__name__}: {e}"
                self._write_output(result, channel="stderr", command=command)
                return result

    def _write_output(self, text: str, *, channel: str, command: str) -> None:
        write = getattr(self.output, "write", None)
        error = getattr(self.output, "error", None)
        if channel == "stderr" and callable(error):
            error(text, source="tool.shell", command=command)
        elif callable(write):
            write(text, source="tool.shell", channel=channel, command=command)

    async def close(self) -> None:
        """关闭 shell 进程"""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
        self._process = None
