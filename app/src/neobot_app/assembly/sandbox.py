"""Local adapter sandbox composition helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from neobot_adapter.local.store import InMemorySandboxDataStore


class JsonSandboxDataStore(InMemorySandboxDataStore):
    """JSON-backed sandbox store for local adapter mode."""

    def __init__(
        self,
        path: Path,
        *,
        bot_user_id: int = 0,
        bot_name: str = "Neo Bot",
    ) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        super().__init__(bot_user_id=bot_user_id, bot_name=bot_name)
        self._load_from_disk()

    @property
    def path(self) -> Path:
        return self._path

    async def flush(self) -> None:
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            tmp_path.write_text(
                json.dumps(self.export_state_sync(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            state = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(state, dict):
            self.load_state_sync(state)


def build_json_sandbox_store(
    *,
    data_dir: Path,
    bot_user_id: int,
    bot_name: str,
) -> JsonSandboxDataStore:
    return JsonSandboxDataStore(
        data_dir / "local_adapter" / "sandbox.json",
        bot_user_id=bot_user_id,
        bot_name=bot_name,
    )
