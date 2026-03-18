"""持久化 Shell 会话管理"""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path


class PersistentShell:
    """持久化 Shell 进程，保持工作目录和环境变量状态"""

    def __init__(self, cwd: Path, timeout: int = 30):
        self.cwd = cwd
        self.timeout = timeout
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

                return "\n".join(output_lines) or "(no output)"

            except asyncio.TimeoutError:
                await self.close()
                return f"Error: Command timed out after {self.timeout}s"
            except Exception as e:
                await self.close()
                return f"Error: {type(e).__name__}: {e}"

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
