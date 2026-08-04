"""UserProfileSkill 测试 — 用户资料查询与头像解析（依赖注入 Fake 服务）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.user_profile import UserProfileSkill


class FakeProfileService:
    """记录 get_user/update_user_avatar_analysis 调用的假资料服务。"""

    def __init__(self, profile: Any = None) -> None:
        self._profile = profile
        self.get_calls: list[str] = []
        self.update_calls: list[tuple[str, str]] = []

    async def get_user(self, user_id: str) -> Any:
        self.get_calls.append(user_id)
        return self._profile

    async def update_user_avatar_analysis(self, user_id: str, analysis: str) -> None:
        self.update_calls.append((user_id, analysis))


class FakeAdapter:
    """记录 call_api 调用并可配置返回/异常的假适配器。"""

    def __init__(self, avatar_result: Any = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._avatar_result = avatar_result
        self._error = error

    async def call_api(self, api: str, params: dict) -> Any:
        self.calls.append((api, params))
        if self._error is not None:
            raise self._error
        return self._avatar_result


class FakeVisionProvider:
    """记录 chat 调用并可配置返回文本的假视觉模型。"""

    def __init__(self, analysis: Any = "可爱的卡通猫头像") -> None:
        self.calls: list[list[dict]] = []
        self._analysis = analysis

    async def chat(self, messages: list[dict]) -> Any:
        self.calls.append(messages)
        return self._analysis


def _parse(text: str) -> dict:
    return json.loads(text)


def _full_profile():
    return SimpleNamespace(
        nick_name="小明",
        remark="老同学",
        profile="爱猫",
        avatar_analysis="卡通猫",
        sex="男",
        age=18,
        city="上海",
        country="中国",
        long_nick="小明的长签名",
        birthday="2008-01-01",
        favorability=42,
        relation_ship="friend",
        known_gender="male",
        labs=["猫", "动画"],
    )


async def test_read_user_info_returns_full_fields():
    """正常路径：读取已有资料应返回全部字段且用户查询参数被传递。"""
    service = FakeProfileService(profile=_full_profile())
    skill = UserProfileSkill(profile_service=service)

    result = _parse(await skill.execute("read_user_info", {"user_id": "123456"}))

    assert result["ok"] is True
    assert service.get_calls == ["123456"]
    assert result["info"]["nick_name"] == "小明"
    assert result["info"]["remark"] == "老同学"
    assert result["info"]["avatar_analysis"] == "卡通猫"
    assert result["info"]["favorability"] == 42


async def test_read_user_info_missing_user_id_rejected():
    """异常路径：缺少 user_id 时应拒绝且不查询服务。"""
    service = FakeProfileService()
    skill = UserProfileSkill(profile_service=service)

    result = _parse(await skill.execute("read_user_info", {}))

    assert result["ok"] is False
    assert "缺少 user_id" in result["error"]
    assert service.get_calls == []


async def test_read_user_info_no_profile_returns_none():
    """边界：用户无资料时应返回 ok 且 info 为 None。"""
    skill = UserProfileSkill(profile_service=FakeProfileService(profile=None))

    result = _parse(await skill.execute("read_user_info", {"user_id": "999"}))

    assert result["ok"] is True
    assert result["info"] is None


async def test_read_user_info_service_error_reported():
    """异常路径：服务抛异常时应返回错误信息而非崩溃。"""
    service = FakeProfileService()

    async def _boom(user_id):
        raise RuntimeError("db down")

    service.get_user = _boom
    skill = UserProfileSkill(profile_service=service)

    result = _parse(await skill.execute("read_user_info", {"user_id": "1"}))

    assert result["ok"] is False
    assert "db down" in result["error"]


async def test_read_user_info_missing_service_rejected():
    """异常路径：profile_service 未配置时应返回配置错误。"""
    skill = UserProfileSkill()

    result = _parse(await skill.execute("read_user_info", {"user_id": "1"}))

    assert result["ok"] is False
    assert "profile_service 未配置" in result["error"]


async def test_analyze_avatar_success_updates_profile():
    """正常路径：获取头像 URL 并解析后应把结果写入资料表（含 user_id）。"""
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"data": {"url": "http://avatar.qq.com/x.png"}})
    vision = FakeVisionProvider(analysis="黑色猫耳头像")
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=vision)

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456"}))

    assert result["ok"] is True
    assert result["avatar_analysis"] == "黑色猫耳头像"
    assert adapter.calls == [("get_qq_avatar", {"user_id": 123456})]
    assert service.update_calls == [("123456", "黑色猫耳头像")]
    assert vision.calls[0][0]["content"][1]["source"]["url"] == "http://avatar.qq.com/x.png"


async def test_analyze_avatar_passes_group_id():
    """正常路径：提供 group_id 时应一并传给 get_qq_avatar 接口。"""
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"url": "http://avatar.qq.com/x.png"})
    vision = FakeVisionProvider()
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=vision)

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456", "group_id": "888"}))

    assert result["ok"] is True
    assert adapter.calls == [("get_qq_avatar", {"user_id": 123456, "group_id": 888})]


async def test_analyze_avatar_missing_url_rejected():
    """异常路径：无法获取头像 URL（返回空）时应提示无法获取。"""
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"data": {}})
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=FakeVisionProvider())

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456"}))

    assert result["ok"] is False
    assert "无法获取用户" in result["error"]
    assert service.update_calls == []


async def test_analyze_avatar_adapter_error_reports_no_url():
    """异常路径：adapter 调用失败时不应崩溃，应提示无法获取头像 URL。"""
    service = FakeProfileService()
    adapter = FakeAdapter(error=RuntimeError("api timeout"))
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=FakeVisionProvider())

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456"}))

    assert result["ok"] is False
    assert "无法获取用户" in result["error"]


async def test_analyze_avatar_non_numeric_user_id_rejected():
    """异常路径：user_id 非数字导致 int() 失败时应返回无法获取 URL 而非崩溃。"""
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"data": {"url": "http://x/y.png"}})
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=FakeVisionProvider())

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "abc"}))

    assert result["ok"] is False
    assert "无法获取用户" in result["error"]


async def test_analyze_avatar_empty_analysis_rejected():
    """异常路径：解析返回空文本时不应写库并应报错。"""
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"data": {"url": "http://x/y.png"}})
    vision = FakeVisionProvider(analysis="   ")
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=vision)

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456"}))

    assert result["ok"] is False
    assert "头像解析返回空文本" in result["error"]
    assert service.update_calls == []


async def test_analyze_avatar_analysis_truncated_to_2000():
    """边界：解析结果超过 2000 字符时返回内容应被截断，但写库保留全文。"""
    long_text = "喵" * 5000
    service = FakeProfileService()
    adapter = FakeAdapter(avatar_result={"data": {"url": "http://x/y.png"}})
    vision = FakeVisionProvider(analysis=long_text)
    skill = UserProfileSkill(profile_service=service, adapter=adapter, image_parse_provider=vision)

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "123456"}))

    assert result["ok"] is True
    assert len(result["avatar_analysis"]) == 2000
    assert service.update_calls[0][1] == long_text


async def test_analyze_avatar_partial_config_rejected():
    """异常路径：adapter/image_parse_provider 缺失其一时应返回配置错误。"""
    skill = UserProfileSkill(profile_service=FakeProfileService(), adapter=FakeAdapter())

    result = _parse(await skill.execute("analyze_user_avatar", {"user_id": "1"}))

    assert result["ok"] is False
    assert "avatar 解析服务未完整配置" in result["error"]


async def test_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = UserProfileSkill()

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown user_profile tool" in result["error"]


def test_tools_expose_analyze_only_when_fully_configured():
    """正常路径：analyze_user_avatar 工具仅在三个依赖齐全时暴露。"""
    partial = UserProfileSkill(profile_service=FakeProfileService()).get_tools()
    full = UserProfileSkill(
        profile_service=FakeProfileService(),
        adapter=FakeAdapter(),
        image_parse_provider=FakeVisionProvider(),
    ).get_tools()

    names = {t["function"]["name"] for t in full}
    assert names == {"read_user_info", "analyze_user_avatar"}
    assert {t["function"]["name"] for t in partial} == {"read_user_info"}
