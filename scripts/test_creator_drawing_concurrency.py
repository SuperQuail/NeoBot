"""Concurrent creator drawing smoke test using the current config and API.

The script submits background drawing jobs through BackgroundDrawingManager,
then verifies completed images reached the notification path.  It is intended
for diagnosing cases where the image API succeeds but NeoBot treats the result
as failed or loses the completion notification.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for src in [
    ROOT / "app" / "src",
    ROOT / "packages" / "adapter" / "src",
    ROOT / "packages" / "chat" / "src",
    ROOT / "packages" / "contracts" / "src",
    ROOT / "packages" / "memory" / "src",
    ROOT / "packages" / "modloader" / "src",
    ROOT / "packages" / "storage" / "src",
]:
    sys.path.insert(0, str(src))


from neobot_storage import run_migrations, sqlite_url
from neobot_app.agents.creator import (
    BackgroundDrawingManager,
    CreatorAgentConfig,
    CreatorImageService,
)
from neobot_app.assembly.storage import build_storage
from neobot_app.config.instance import load_bot_config
from neobot_app.runtime.notifications import BackgroundNotificationHub


@dataclass
class CapturedNotification:
    kind: str
    conversation_id: str
    content: str
    manager_name: str
    reasons: list[str]


class DummyAdapter:
    async def send(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}

    async def call_api(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}


class CapturingOrchestrator:
    def __init__(self) -> None:
        self._active_pipelines: dict[str, asyncio.Task[None]] = {}
        self.notifications: list[CapturedNotification] = []

    def start_background_reply(
        self,
        *,
        kind: str,
        conversation_id: str,
        content: str,
        manager_name: str = "background_drawing",
        reasons: list[str] | None = None,
    ) -> object:
        self.notifications.append(
            CapturedNotification(
                kind=kind,
                conversation_id=str(conversation_id),
                content=content,
                manager_name=manager_name,
                reasons=list(reasons or []),
            )
        )
        return object()


async def _run(count: int, prompt: str, timeout: float) -> int:
    config = load_bot_config()
    creator_config = CreatorAgentConfig.from_schema(config.agent.creator)

    work_dir = ROOT / ".changes" / "creator_drawing_concurrency"
    work_dir.mkdir(parents=True, exist_ok=True)
    db_url = sqlite_url(work_dir / "test.sqlite3")
    run_migrations(db_url)
    engine, uow_factory = build_storage(db_url)

    hub = BackgroundNotificationHub()
    orchestrator = CapturingOrchestrator()
    hub.set_orchestrator(orchestrator)

    service = CreatorImageService(
        uow_factory=uow_factory,
        adapter=DummyAdapter(),  # type: ignore[arg-type]
        config=creator_config,
        data_dir=work_dir / "data",
    )
    manager = BackgroundDrawingManager(
        image_service=service,
        config=creator_config,
        notification_hub=hub,
    )
    manager.set_orchestrator(orchestrator)

    try:
        submit_results = await asyncio.gather(
            *[
                manager.submit(
                    pipeline_key=f"group:test-{idx}",
                    conversation_kind="group",
                    conversation_id=f"900{idx:03d}",
                    prompt=f"{prompt} #{idx + 1}",
                    requester=f"并发测试{idx + 1}",
                    requirements=prompt,
                )
                for idx in range(count)
            ],
            return_exceptions=True,
        )

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            tasks = list(manager._tasks.values())  # noqa: SLF001 - diagnostic script
            if len(tasks) >= count and all(task.status != "drawing" for task in tasks):
                break
            await asyncio.sleep(2.0)

        tasks = list(manager._tasks.values())  # noqa: SLF001 - diagnostic script
        completed = [task for task in tasks if task.status == "completed"]
        failed = [task for task in tasks if task.status == "failed"]
        drawing = [task for task in tasks if task.status == "drawing"]
        notified_image_ids = {
            task.image_id
            for task in completed
            if task.image_id
            and any(task.image_id in item.content for item in orchestrator.notifications)
        }
        missing_notifications = [
            task.image_id
            for task in completed
            if task.image_id and task.image_id not in notified_image_ids
        ]

        print(f"submitted={len(submit_results)} tasks={len(tasks)}")
        print(
            "completed={completed} failed={failed} drawing={drawing} notifications={notifications}".format(
                completed=len(completed),
                failed=len(failed),
                drawing=len(drawing),
                notifications=len(orchestrator.notifications),
            )
        )
        for idx, result in enumerate(submit_results, start=1):
            if isinstance(result, Exception):
                print(f"submit[{idx}]=EXCEPTION {type(result).__name__}: {result}")
            else:
                print(f"submit[{idx}]={result}")
        for task in failed:
            print(f"failed task_id={task.task_id} pipeline={task.pipeline_key} error={task.error}")
        if missing_notifications:
            print(f"missing_notifications={missing_notifications}")

        return 0 if len(completed) == count and not missing_notifications else 1
    finally:
        await manager.shutdown()
        await service.close()
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument(
        "--prompt",
        default="A small friendly robot holding a neon sign that says NeoBot, clean digital illustration",
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    return asyncio.run(_run(args.count, args.prompt, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
