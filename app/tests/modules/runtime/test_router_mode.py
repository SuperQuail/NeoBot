"""Router 模式登记处：启用/关闭、任务表 provider 与异常兜底。"""

from __future__ import annotations

from neobot_app.runtime.router_mode import RouterModeService


def test_inactive_by_default():
    service = RouterModeService()

    assert service.is_active("group:123") is False
    assert service.build_context("group:123") is None


def test_activate_and_deactivate_round_trip():
    service = RouterModeService()

    session = service.activate(
        "group:123", owner_user_id=10001, task_ids=["t-1", "t-2"], reason="user-confirmed"
    )

    assert session.pipeline_key == "group:123"
    assert session.owner_user_id == 10001
    assert session.task_ids == ("t-1", "t-2")
    assert service.is_active("group:123") is True
    assert service.is_active("group:456") is False
    assert service.session("group:123") is session

    assert service.deactivate("group:123") is True
    assert service.is_active("group:123") is False
    assert service.deactivate("group:123") is False


def test_activate_requires_pipeline_key():
    service = RouterModeService()

    try:
        service.activate("   ")
    except ValueError as exc:
        assert "pipeline_key" in str(exc)
    else:  # pragma: no cover - 防御性分支
        raise AssertionError("空 pipeline_key 应该被拒绝")


def test_context_provider_only_called_when_active():
    service = RouterModeService()
    calls: list[str] = []

    def provider(key: str) -> str:
        calls.append(key)
        return "#1 running"

    service.set_context_provider(provider)

    assert service.build_context("group:123") is None
    assert calls == []

    service.activate("group:123")
    assert service.build_context("group:123") == "#1 running"
    assert calls == ["group:123"]


def test_context_provider_failure_or_blank_is_ignored():
    service = RouterModeService()
    service.activate("group:123")

    def broken(_key: str) -> str:
        raise RuntimeError("plugin gone")

    service.set_context_provider(broken)
    assert service.build_context("group:123") is None

    service.set_context_provider(lambda _key: "   ")
    assert service.build_context("group:123") is None

    service.set_context_provider(None)
    assert service.build_context("group:123") is None


def test_snapshot_and_clear():
    service = RouterModeService()
    service.activate("private:42", task_ids=["t-1"])
    service.activate("group:7")

    snapshot = service.snapshot()
    assert {item["pipeline_key"] for item in snapshot} == {"private:42", "group:7"}

    service.clear()
    assert service.snapshot() == []


def test_required_skills_are_registered_and_cleared():
    service = RouterModeService()

    assert service.required_skills() == ()
    service.set_required_skills(["dsh_router", " ", ""])
    assert service.required_skills() == ("dsh_router",)

    service.set_required_skills(None)
    assert service.required_skills() == ()
