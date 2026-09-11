"""绘图模型选择：取值收敛为枚举，未知取值在提交前就被拒绝。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.drawing_skill import DrawingSkill


class _FakeImageService:
    def __init__(self, models: list[dict[str, Any]]) -> None:
        self._models = models

    def available_models(self) -> list[dict[str, Any]]:
        return self._models


class _FakeManager:
    def __init__(self, models: list[dict[str, Any]]) -> None:
        self.submitted: list[dict[str, Any]] = []
        self.models = models
        self._service = _FakeImageService(models)

    def resolve_model_name(self, selector: str | None) -> str:
        names = [str(item["name"]) for item in self.models]
        raw = str(selector or "").strip()
        if not raw:
            return names[0] if names else ""
        if raw in names:
            return raw
        raise ValueError(f"未知生图模型选择 {selector!r}；可用: {'、'.join(names)}")

    async def submit(self, **kwargs: Any) -> str:
        self.submitted.append(kwargs)
        return json.dumps(
            {"ok": True, "status": "drawing", "task_id": "draw_1", "model": kwargs.get("model")},
            ensure_ascii=False,
        )


MODELS = [
    {"name": "gpt-image-2-vip", "index": 0, "description": "创作者Agent生图模型",
     "provider": "GPTGOD", "model_name": "gpt-image-2-vip", "default": True},
    {"name": "gpt-image-2.5-flare", "index": 1, "description": "备选生图模型(GPT-image-2.5)",
     "provider": "sailapi", "model_name": "gpt-image-2.5-flare", "default": False},
]


def _skill(models: list[dict[str, Any]] | None = None) -> tuple[DrawingSkill, _FakeManager]:
    manager = _FakeManager(models if models is not None else MODELS)
    skill = DrawingSkill(drawing_manager=manager)
    skill._image_service = manager._service
    return skill, manager


def test_provider_property_becomes_enum_when_multiple_models():
    """多模型时必须给枚举，避免模型把序号/供应商/描述混着传。"""
    skill, _ = _skill()
    provider = skill._provider_property()

    assert provider is not None
    assert provider["type"] == "string"
    assert provider["enum"] == ["gpt-image-2-vip", "gpt-image-2.5-flare"]
    assert "GPTGOD" in provider["description"]


def test_provider_property_absent_with_single_model():
    skill, _ = _skill(models=[MODELS[0]])
    assert skill._provider_property() is None


async def test_unknown_provider_rejected_before_submit():
    """未知模型取值必须当场报错并列出可用取值，不能白跑一次任务再失败。"""
    skill, manager = _skill()

    result = json.loads(
        await skill.execute("draw", {"prompt": "一只猫", "provider": "不存在的模型"})
    )

    assert result["ok"] is False
    assert "未知生图模型选择" in result["error"]
    assert [item["name"] for item in result["available_models"]] == [
        "gpt-image-2-vip",
        "gpt-image-2.5-flare",
    ]
    assert manager.submitted == []


async def test_known_provider_is_resolved_and_forwarded():
    skill, manager = _skill()

    result = json.loads(
        await skill.execute("draw", {"prompt": "一只猫", "provider": "gpt-image-2.5-flare"})
    )

    assert result["ok"] is True
    assert manager.submitted[0]["model"] == "gpt-image-2.5-flare"


async def test_missing_provider_uses_default_model():
    skill, manager = _skill()

    await skill.execute("draw", {"prompt": "一只猫"})

    assert manager.submitted[0]["model"] is None
