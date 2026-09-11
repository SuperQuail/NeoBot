"""网页面板管理接口（提示词 / 聊天流 / 定时任务）的 HTTP 集成测试。

用真实 aiohttp 服务 + httpx 驱动，服务用轻量替身注入：提示词用真实 PromptStore、
聊天流用真实 ChatFlowRegistry、定时任务写路径用替身 reminder skill（真实实现见
app/tests/modules/skills/test_reminder_skill.py）。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_app.prompt.store import PromptStore, sync_default_prompts
from neobot_app.reply.flow_registry import ChatFlowRegistry

from test_dashboard_api import (
    PASSWORD,
    _FakeAdapter,
    _FakeControl,
    _NullLogger,
    _free_port,
    _login,
)


class _Services:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, name, default=None):
        return self._mapping.get(name, default)


class _ReminderSkill:
    """reminder skill 替身:记录调用并回放可配置结果。"""

    name = "reminder"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.result: dict = {"ok": True, "status": "created"}

    async def execute(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return json.dumps(self.result, ensure_ascii=False)


class _SkillManager:
    def __init__(self, skill) -> None:
        self._skill = skill

    def all_skills(self):
        return [self._skill] if self._skill is not None else []


class _ScheduledTaskManager:
    def __init__(self, tasks: list[dict] | None = None) -> None:
        self.tasks = list(tasks or [])
        self.calls: list[dict] = []

    async def list_managed_tasks(self, *, include_disabled=True, limit=200):
        self.calls.append({"include_disabled": include_disabled, "limit": limit})
        return list(self.tasks)


def _flow_registry() -> ChatFlowRegistry:
    registry = ChatFlowRegistry()
    registry.record_prompt(
        "group:888",
        system_prompt="<你是谁>\n你的名字是弥音",
        model="deepseek-chat",
        conversation_kind="group",
        conversation_id="888",
    )
    registry.record_request(
        "group:888",
        messages=[
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "function": {"name": "send_reply", "arguments": '{"text":"hi"}'}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "已发送 1 条消息"},
        ],
        model="deepseek-chat",
        iteration=2,
    )
    registry.set_active("group:888", True)
    registry.register_task_provider(
        "scheduled_task", lambda key: {"scheduled_task_notifications_pending": 1}
    )
    return registry


async def _start_management_panel(tmp_path: Path, *, services=None):
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)

    server = DashboardServer(
        plugin_name="dashboard",
        config=__import__(
            "neobot_app.builtin_plugins.dashboard.config", fromlist=["DashboardConfig"]
        ).DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=_FakeControl(tmp_path / "plugins_data"),
        services=services,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}"


@pytest.fixture()
async def managed_panel(tmp_path: Path):
    sync_default_prompts(tmp_path)
    store = PromptStore(tmp_path)
    registry = _flow_registry()
    skill = _ReminderSkill()
    scheduled = _ScheduledTaskManager(
        [
            {
                "task_id": "t-1",
                "title": "喝水提醒",
                "detail": "每小时",
                "recurrence": "daily",
                "state": "active",
                "enabled": True,
                "next_run": "2026-01-01 09:00",
                "bindings": [{"kind": "group", "id": "888"}],
                "one_shot_notification": True,
            }
        ]
    )
    services = _Services(
        {
            "prompt_store": store,
            "chat_flow_registry": registry,
            "scheduled_task_manager": scheduled,
            "skill_manager": _SkillManager(skill),
        }
    )
    server, base = await _start_management_panel(tmp_path, services=services)
    try:
        yield {
            "base": base,
            "store": store,
            "registry": registry,
            "skill": skill,
            "scheduled": scheduled,
            "tmp": tmp_path,
        }
    finally:
        await server.stop()


# ── 提示词 ────────────────────────────────────────────────────────


async def test_prompts_endpoint_requires_login(managed_panel) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(managed_panel["base"] + "/api/prompts")

    assert response.status_code == 401
    assert response.json()["ok"] is False


async def test_prompts_endpoint_lists_sections(managed_panel) -> None:
    token, _ = await _login(managed_panel["base"])
    async with httpx.AsyncClient() as client:
        response = await client.get(
            managed_panel["base"] + "/api/prompts", headers={"X-Token": token}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    names = {item["name"] for item in payload["sections"]}
    assert {"group_chat", "friend_chat", "current_time", "problem_solver"} <= names
    assert payload["editable"] is True


async def test_prompts_preview_renders_with_simulated_values(managed_panel) -> None:
    """预览是纯计算接口：渲染模拟取值并报告未解析的占位符。"""
    token, csrf = await _login(managed_panel["base"])
    base = managed_panel["base"]
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        without_csrf = await client.post(
            base + "/api/prompts/preview",
            headers={"X-Token": token},
            json={"template": "你好{bot_name}"},
        )
        response = await client.post(
            base + "/api/prompts/preview",
            headers=headers,
            json={"template": "你好{bot_name},群:{group_name},未知:{nope}"},
        )
        by_section = await client.post(
            base + "/api/prompts/preview",
            headers=headers,
            json={"section": "current_time", "path": "template"},
        )

    assert without_csrf.status_code == 403
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["rendered"] == "你好小助手,群:示例群聊,未知:{nope}"
    assert payload["unresolved"] == ["nope"]
    assert "bot_name" in payload["values"]

    assert by_section.status_code == 200
    assert "<当前时间>" in by_section.json()["rendered"]


async def test_prompts_save_requires_manage_and_writes_custom_file(managed_panel) -> None:
    token, csrf = await _login(managed_panel["base"])
    base = managed_panel["base"]

    async with httpx.AsyncClient() as client:
        denied = await client.post(
            base + "/api/prompts/save",
            headers={"X-Token": token},
            json={"section": "group_chat", "path": "template", "value": "x"},
        )
        saved = await client.post(
            base + "/api/prompts/save",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"section": "group_chat", "path": "template", "value": "自定义群聊提示词"},
        )

    assert denied.status_code == 403
    assert saved.status_code == 200, saved.text
    assert saved.json()["ok"] is True
    store = managed_panel["store"]
    assert store.template("group_chat") == "自定义群聊提示词"


async def test_prompts_reset_restores_default(managed_panel) -> None:
    token, csrf = await _login(managed_panel["base"])
    base = managed_panel["base"]
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        await client.post(
            base + "/api/prompts/save",
            headers=headers,
            json={"section": "group_chat", "path": "template", "value": "临时"},
        )
        reset = await client.post(
            base + "/api/prompts/reset",
            headers=headers,
            json={"section": "group_chat", "path": "template"},
        )

    assert reset.status_code == 200
    assert reset.json()["removed"] is True
    assert managed_panel["store"].template("group_chat").startswith("<你是谁>")


async def test_prompts_preview_unknown_section_returns_404(managed_panel) -> None:
    token, csrf = await _login(managed_panel["base"])
    async with httpx.AsyncClient() as client:
        response = await client.post(
            managed_panel["base"] + "/api/prompts/preview",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"section": "nope", "path": "template"},
        )

    assert response.status_code == 404


# ── 聊天流 ────────────────────────────────────────────────────────


async def test_chat_flows_lists_and_shows_detail(managed_panel) -> None:
    token, _ = await _login(managed_panel["base"])
    base = managed_panel["base"]
    headers = {"X-Token": token}

    async with httpx.AsyncClient() as client:
        listing = await client.get(base + "/api/chat-flows", headers=headers)
        detail = await client.get(
            base + "/api/chat-flows/detail", headers=headers, params={"key": "group:888"}
        )
        missing = await client.get(
            base + "/api/chat-flows/detail", headers=headers, params={"key": "group:1"}
        )

    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["pipeline_key"] == "group:888"
    assert items[0]["active"] is True
    assert items[0]["model"] == "deepseek-chat"

    assert detail.status_code == 200
    payload = detail.json()
    assert "你的名字是弥音" in payload["system_prompt"]
    roles = [message["role"] for message in payload["messages"]]
    assert roles == ["system", "assistant", "tool"]
    assert payload["messages"][1]["tool_calls"][0]["name"] == "send_reply"
    assert payload["background_tasks"] == {"scheduled_task_notifications_pending": 1}

    assert missing.status_code == 404


async def test_chat_flows_detail_requires_key(managed_panel) -> None:
    token, _ = await _login(managed_panel["base"])
    async with httpx.AsyncClient() as client:
        response = await client.get(
            managed_panel["base"] + "/api/chat-flows/detail", headers={"X-Token": token}
        )

    assert response.status_code == 400


# ── 定时任务 ──────────────────────────────────────────────────────


async def test_scheduled_tasks_listing_includes_disabled_flag(managed_panel) -> None:
    token, _ = await _login(managed_panel["base"])
    async with httpx.AsyncClient() as client:
        response = await client.get(
            managed_panel["base"] + "/api/scheduled-tasks",
            headers={"X-Token": token},
            params={"include_disabled": "0", "limit": "50"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["tasks"][0]["task_id"] == "t-1"
    assert managed_panel["scheduled"].calls[-1] == {
        "include_disabled": False,
        "limit": 50,
    }


async def test_scheduled_tasks_action_dispatches_to_reminder_skill(managed_panel) -> None:
    token, csrf = await _login(managed_panel["base"])
    base = managed_panel["base"]

    async with httpx.AsyncClient() as client:
        denied = await client.post(
            base + "/api/scheduled-tasks/action",
            headers={"X-Token": token},
            json={"action": "delete", "task_uuid": "t-1"},
        )
        created = await client.post(
            base + "/api/scheduled-tasks/action",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "action": "create",
                "title": "喝水提醒",
                "recurrence": "daily",
                "start_at": "2026-01-01T09:00",
                "end_at": "2026-01-01T09:10",
                "bindings": [{"kind": "group", "id": "888"}],
                "ignored_field": "会被丢弃",
            },
        )

    assert denied.status_code == 403
    assert created.status_code == 200, created.text
    assert created.json()["message"] == "定时任务已创建"
    tool, args = managed_panel["skill"].calls[-1]
    assert tool == "create_scheduled_task"
    assert args["title"] == "喝水提醒"
    assert "ignored_field" not in args


async def test_scheduled_tasks_action_validates_and_maps_errors(managed_panel) -> None:
    token, csrf = await _login(managed_panel["base"])
    base = managed_panel["base"]
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        unknown = await client.post(
            base + "/api/scheduled-tasks/action",
            headers=headers,
            json={"action": "nope"},
        )
        no_uuid = await client.post(
            base + "/api/scheduled-tasks/action",
            headers=headers,
            json={"action": "delete"},
        )
        managed_panel["skill"].result = {"ok": False, "error": "重复定时任务数量已达上限: 15"}
        rejected = await client.post(
            base + "/api/scheduled-tasks/action",
            headers=headers,
            json={
                "action": "create",
                "title": "t",
                "recurrence": "daily",
                "start_at": "2026-01-01T09:00",
                "end_at": "2026-01-01T09:10",
                "bindings": [{"kind": "group", "id": "888"}],
            },
        )

    assert unknown.status_code == 400
    assert no_uuid.status_code == 400
    assert rejected.status_code == 400
    assert "上限" in rejected.json()["error"]


async def test_management_endpoints_report_missing_services(tmp_path: Path) -> None:
    """服务缺失时给出 503 而不是 500，面板可提示「未启用」。"""
    server, base = await _start_management_panel(tmp_path, services=_Services({}))
    try:
        token, _ = await _login(base)
        async with httpx.AsyncClient() as client:
            prompts = await client.get(base + "/api/prompts", headers={"X-Token": token})
            flows = await client.get(base + "/api/chat-flows", headers={"X-Token": token})
            tasks = await client.get(
                base + "/api/scheduled-tasks", headers={"X-Token": token}
            )
    finally:
        await server.stop()

    assert prompts.status_code == 503
    assert flows.status_code == 503
    assert tasks.status_code == 200
    assert tasks.json()["available"] is False
