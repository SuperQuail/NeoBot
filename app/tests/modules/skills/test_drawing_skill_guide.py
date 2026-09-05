"""DrawingSkill 新能力测试:process_image 工具、inspect_image 预留开关、指导内容。"""

from __future__ import annotations

import json

from neobot_app.skills.drawing_skill import DrawingSkill


def _tools(skill: DrawingSkill) -> dict[str, dict]:
    return {t["function"]["name"]: t["function"] for t in skill.get_tools()}


def test_process_image_tool_registered_when_service_available() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=object())
    tools = _tools(skill)
    assert "process_image" in tools
    fn = tools["process_image"]
    props = fn["parameters"]["properties"]
    assert props["operation"]["enum"] == [
        "resize", "crop", "to_png", "to_jpeg", "remove_background",
    ]
    assert "image" in fn["parameters"]["required"]
    assert "operation" in fn["parameters"]["required"]


def test_process_image_tool_hidden_without_service() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=None)
    tools = _tools(skill)
    assert "process_image" not in tools


def test_inspect_image_hidden_by_default() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=object())
    tools = _tools(skill)
    assert "inspect_image" not in tools
    assert "inspect_image" not in skill.instructions


def test_inspect_image_enabled_via_flag() -> None:
    skill = DrawingSkill(
        drawing_manager=object(),
        image_service=object(),
        vision_provider=object(),
        enable_image_inspect=True,
    )
    tools = _tools(skill)
    assert "inspect_image" in tools
    assert "inspect_image" in skill.instructions


async def test_process_image_execute_missing_args() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=object())
    result = json.loads(await skill.execute("process_image", {}))
    assert result["ok"] is False
    assert "image" in result["error"]


async def test_process_image_execute_passthrough() -> None:
    class _FakeService:
        async def process_image(self, **kwargs):
            self.called = kwargs
            return type("R", (), {
                "image_id": "tmp_abc",
                "source": "tmp",
                "file_path": "/tmp/tmp_abc.png",
                "original_width": 10,
                "original_height": 10,
            })()

    service = _FakeService()
    skill = DrawingSkill(drawing_manager=object(), image_service=service)
    result = json.loads(await skill.execute(
        "process_image",
        {"image": "gallery:1", "operation": "resize", "width": 20},
    ))
    assert result["ok"] is True
    assert result["image_id"] == "tmp_abc"
    assert service.called["operation"] == "resize"
    assert service.called["width"] == 20
    assert service.called["image"] == "gallery:1"


async def test_inspect_image_without_vision_returns_size(tmp_path) -> None:
    class _FakeService:
        def __init__(self, path):
            self.path = path

        async def _resolve_process_source(self, image: str):
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGB", (6, 4), "blue").save(buf, format="PNG")
            self.path.write_bytes(buf.getvalue())
            return self.path

    fake_path = tmp_path / "fake_inspect.png"
    skill = DrawingSkill(
        drawing_manager=object(),
        image_service=_FakeService(fake_path),
        vision_provider=None,
        enable_image_inspect=True,
    )
    result = json.loads(await skill.execute(
        "inspect_image", {"image": str(fake_path)}
    ))
    assert result["ok"] is False
    assert result["size"] == {"width": 6, "height": 4}
    assert "视觉模型未配置" in result["error"]


def test_instructions_cover_core_guidance() -> None:
    skill = DrawingSkill(drawing_manager=object(), image_service=object())
    instructions = skill.instructions
    # 角色立绘参考规则
    assert "角色立绘参考规则" in instructions
    assert "gallery_search" in instructions
    # 提示词编写规范
    assert "提示词编写规范" in instructions
    assert "只改" in instructions or "不变项" in instructions
    # 透明背景策略
    assert "透明背景策略" in instructions
    assert "remove_background" in instructions
    # 尺寸与后处理
    assert "process_image" in instructions
