"""未配置生图模型时的降级（issue #82）。

出厂默认是「creator 开着（图库 / 表情包要用）+ models.assignments.creator_image_models 为空」。
以前 CreatorImageService 在**构造期**直接抛 `ValueError: 至少需要一个生图模型注册名`，
于是全新部署根本起不来。现在只有绘图入口不可用：图库 / 表情包 / 图片解析照常，
draw 工具不再暴露，调用时给出可读错误。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from neobot_app.drawing import CreatorImageService, DrawServiceConfig
from neobot_app.skills.drawing_skill import DrawingSkill


def _service(tmp_path: Path) -> CreatorImageService:
    """按「没有生图模型」的实际形态构造：model_names 为空。"""
    return CreatorImageService(
        uow_factory=SimpleNamespace(),
        adapter=SimpleNamespace(),
        config=DrawServiceConfig(),
        data_dir=tmp_path,
        model_names=None,
    )


def test_service_constructs_without_image_models(tmp_path: Path) -> None:
    service = _service(tmp_path)

    assert service.model_names == ()
    assert service.available_models() == []
    # 图库目录照常准备：gallery / emoji / 图片解析都不依赖生图模型
    assert (tmp_path / "creator" / "gallery").is_dir()
    assert (tmp_path / "creator" / "tmp").is_dir()


async def test_drawing_entry_explains_missing_model(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="creator_image_models"):
        service.resolve_model_name(None)
    with pytest.raises(ValueError, match="creator_image_models"):
        await service.generate_image(prompt="一只猫")


def test_bootstrap_builder_tolerates_empty_image_models() -> None:
    """回归 issue #82：默认配置（creator 开 + 生图模型为空）在 bootstrap 里不再炸。"""
    from neobot_contracts.ports.logging import NullLogger

    from neobot_app.bootstrap._runtime import build_creator_image_service

    config = SimpleNamespace(
        agent=SimpleNamespace(creator=None),
        models=SimpleNamespace(creator_image_model_names=[]),
    )
    service = build_creator_image_service(
        uow_factory=SimpleNamespace(),
        adapter=SimpleNamespace(),
        config=config,
        emoji_service=None,
        vision_provider=None,
        file_server=None,
        image_pool=None,
        logger_factory=SimpleNamespace(get_logger=lambda _name: NullLogger()),
    )

    assert service.model_names == ()


class _FakeImageService:
    def __init__(self, models: list[dict]) -> None:
        self._models = models

    def available_models(self) -> list[dict]:
        return self._models


def _tool_names(skill: DrawingSkill) -> set[str]:
    return {tool["function"]["name"] for tool in skill.get_tools()}


def test_draw_tool_hidden_without_image_model() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=_FakeImageService([]))
    tools = _tool_names(skill)

    assert "draw" not in tools, "没有生图模型时不该暴露一个必然失败的工具"
    assert "check_draw_status" in tools, "其余绘图周边工具不受影响"
    assert "draw 工具不可用" in skill.instructions, "操作说明要讲清为什么没有 draw"


def test_draw_tool_present_with_image_model() -> None:
    skill = DrawingSkill(
        drawing_manager=object(),
        image_service=_FakeImageService([{"name": "some-model", "default": True}]),
    )

    assert "draw" in _tool_names(skill)
    assert "draw 工具不可用" not in skill.instructions
