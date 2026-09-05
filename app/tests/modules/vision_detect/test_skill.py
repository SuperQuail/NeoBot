"""VisionDetectSkill 单元测试。"""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image

from neobot_app.skills.base import SkillManager
from neobot_app.skills.vision_detect_skill import VisionDetectSkill


class _FakeService:
    """伪造 VisionDetectService。"""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.calls: list[dict] = []

    @property
    def available(self) -> bool:
        return self._available

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "miyin_yolo_320",
                "name": "弥音形象检测",
                "description": "检测弥音形象",
                "classes": ["弥音(面部识别)"],
                "conf": 0.35,
                "imgsz": 320,
                "file": "miyin_yolo_320.onnx",
            }
        ]

    async def detect_bytes_async(
        self,
        image_bytes: bytes,
        model_ids: list[str] | None = None,
        min_conf: float | None = None,
        mode: str = "filter",
    ) -> dict[str, Any]:
        self.calls.append({"bytes": image_bytes, "model_ids": model_ids, "min_conf": min_conf, "mode": mode})
        return {"ok": True, "mode": mode, "results": [], "summary": "未检测到任何目标"}


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _make_skill(service: _FakeService) -> VisionDetectSkill:
    return VisionDetectSkill(service=service, adapter=None, group_message_queue=None, friend_message_queue=None)


def _tools(skill: VisionDetectSkill) -> dict[str, dict]:
    return {tool["function"]["name"]: tool["function"] for tool in skill.get_tools()}


def test_no_models_hides_tool() -> None:
    skill = _make_skill(_FakeService(available=False))
    assert skill.get_tools() == []


def test_tool_def_has_list_models_and_detect() -> None:
    skill = _make_skill(_FakeService())
    tools = _tools(skill)
    assert "list_models" in tools
    assert "detect" in tools
    detect = tools["detect"]
    # detect 的 model 必须必填,不做全量检测;enum 不烘焙(以 list_models 实时为准)
    assert "model" in detect["parameters"]["required"]
    assert "enum" not in detect["parameters"]["properties"]["model"]
    assert "先调用 list_models" in detect["description"]


def test_register_into_skill_manager_prefixes_tools() -> None:
    mgr = SkillManager()
    mgr.register(_make_skill(_FakeService()))
    names = [tool["function"]["name"] for tool in mgr.get_tools()]
    assert "vision_detect__detect" in names
    assert "vision_detect__list_models" in names


async def test_list_models_returns_model_catalog() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(await skill.execute("list_models", {}))
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["models"][0]["id"] == "miyin_yolo_320"
    assert "检测弥音形象" in result["models"][0]["description"]
    assert result["models"][0]["classes"] == ["弥音(面部识别)"]


async def test_execute_detect_requires_model() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute("detect", {"image_base64": base64.b64encode(_png_bytes()).decode()})
    )
    assert result["ok"] is False
    assert "model" in result["error"]
    assert service.calls == []  # 未指定模型不得触发检测


async def test_execute_detect_with_model() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute(
            "detect",
            {
                "image_base64": base64.b64encode(_png_bytes()).decode(),
                "model": "miyin_yolo_320",
            },
        )
    )
    assert result["ok"] is True
    assert len(service.calls) == 1
    assert service.calls[0]["model_ids"] == ["miyin_yolo_320"]
    assert service.calls[0]["mode"] == "filter"


async def test_execute_mode_and_min_conf_passthrough() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    await skill.execute(
        "detect",
        {
            "image_base64": base64.b64encode(_png_bytes()).decode(),
            "model": "miyin_yolo_320",
            "mode": "all",
            "min_conf": 0.5,
        },
    )
    assert service.calls[0]["mode"] == "all"
    assert service.calls[0]["min_conf"] == 0.5


async def test_execute_model_non_string_rejected() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute(
            "detect",
            {
                "image_base64": base64.b64encode(_png_bytes()).decode(),
                "model": ["miyin_yolo_320"],
            },
        )
    )
    assert result["ok"] is False
    assert "model" in result["error"]
    assert service.calls == []


async def test_execute_invalid_mode_returns_error() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute(
            "detect",
            {"image_base64": base64.b64encode(_png_bytes()).decode(), "model": "miyin_yolo_320", "mode": "xxx"},
        )
    )
    assert result["ok"] is False
    assert "mode" in result["error"]
    assert service.calls == []


async def test_execute_invalid_min_conf_type() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute(
            "detect",
            {"image_base64": base64.b64encode(_png_bytes()).decode(), "model": "miyin_yolo_320", "min_conf": "高"},
        )
    )
    assert result["ok"] is False
    assert "min_conf" in result["error"]


async def test_execute_min_conf_bool_rejected() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    result = json.loads(
        await skill.execute(
            "detect",
            {"image_base64": base64.b64encode(_png_bytes()).decode(), "model": "miyin_yolo_320", "min_conf": True},
        )
    )
    assert result["ok"] is False
    assert "min_conf" in result["error"]


async def test_execute_min_conf_out_of_range_rejected() -> None:
    import base64

    service = _FakeService()
    skill = _make_skill(service)
    for bad in (-0.5, 1.5):
        result = json.loads(
            await skill.execute(
                "detect",
                {"image_base64": base64.b64encode(_png_bytes()).decode(), "model": "miyin_yolo_320", "min_conf": bad},
            )
        )
        assert result["ok"] is False
        assert "0.0 到 1.0" in result["error"]


async def test_execute_missing_image_source_returns_error() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(await skill.execute("detect", {"model": "miyin_yolo_320"}))
    assert result["ok"] is False
    assert "图片来源" in result["error"]


async def test_execute_msg_number_requires_pipeline_key() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(await skill.execute("detect", {"model": "miyin_yolo_320", "msg_number": 5}))
    assert result["ok"] is False
    assert "pipeline_key" in result["error"]


async def test_execute_bad_image_index_returns_friendly_error() -> None:
    import base64

    skill = _make_skill(_FakeService())
    result = json.loads(
        await skill.execute(
            "detect",
            {"image_base64": base64.b64encode(_png_bytes()).decode(), "model": "miyin_yolo_320", "image_index": "abc"},
        )
    )
    assert result["ok"] is False
    assert "image_index" in result["error"]


async def test_execute_bad_msg_number_returns_friendly_error() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(
        await skill.execute("detect", {"model": "miyin_yolo_320", "msg_number": "abc", "pipeline_key": "group:1"})
    )
    assert result["ok"] is False
    assert "msg_number" in result["error"]


async def test_execute_unknown_tool() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(await skill.execute("nope", {}))
    assert result["ok"] is False
    assert "unknown vision_detect tool" in result["error"]


async def test_execute_bad_base64() -> None:
    skill = _make_skill(_FakeService())
    result = json.loads(
        await skill.execute("detect", {"model": "miyin_yolo_320", "image_base64": "!!not-base64!!"})
    )
    assert result["ok"] is False


async def test_instructions_mention_list_models_and_mode() -> None:
    skill = _make_skill(_FakeService())
    assert "## list_models" in skill.instructions
    assert "## detect" in skill.instructions
    assert "msg_number" in skill.instructions
    assert "filter" in skill.instructions
