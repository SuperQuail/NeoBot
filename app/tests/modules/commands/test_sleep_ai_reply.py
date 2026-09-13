"""spec(5) §4.1：/sleep /awake 交 AI 回复（R1-R4 / A1-A7）。

- 状态确实变更且管线可用 → 按次置 ctx.sync_reply，结果作为 background 交主管线；
- 无状态变更（时长非法 / 超上限 / 缺参数 / 未睡眠时 awake / 服务缺失）→ 直接回文本，
  连模型注册表都不探测（零模型调用）；
- 管线不可用（待机中 / 主模型未注册）→ 回固定文案，用户一定有反馈。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.commands.service import CommandService
from neobot_app.prompt.store import PromptStore
from neobot_app.runtime.sleep_service import (
    DEFAULT_SLEEP_CMD_PROMPT,
    SleepService,
    safe_format,
)

BOT = 88888
SUPER = 10000
SUB = 30000
NOBODY = 40000

#: 旧固定文案（管线不可用时必须原样保留）
OLD_SLEEP_TEXT = "好的,我去睡觉了"
OLD_AWAKE_TEXT = "我被叫醒了。"


class ModelRegistrySpy:
    """替身模型注册表：记录 names 被读取的次数（读取 = 探测过管线）。"""

    def __init__(self, names: tuple[str, ...] = ("main-model",)) -> None:
        self._names = names
        self.reads = 0

    @property
    def names(self) -> tuple[str, ...]:
        self.reads += 1
        return self._names


class StandbyStub:
    def __init__(self, standby: bool = False) -> None:
        self._standby = standby

    def is_standby(self) -> bool:
        return self._standby


def _config():
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[SUB])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


def _message(text: str, *, user_id: int = SUB, at_qqs: list[int] | None = None):
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs if at_qqs is not None else [BOT]:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


def _recorder(sink: list[str]):
    async def _send(kind, conv, text, at_user_id):
        sink.append(text)

    return _send


def _service(
    *,
    sleep_service: Any = None,
    standby: Any = None,
    sent: list[str] | None = None,
    register_builtins: bool = True,
) -> CommandService:
    return CommandService(
        config=_config(),
        adapter=SimpleNamespace(send=lambda conv, segments: None),
        send_callback=_recorder([] if sent is None else sent),
        sleep_service=sleep_service,
        standby_service=standby,
        register_builtins=register_builtins,
    )


@pytest.fixture()
def registry(monkeypatch: pytest.MonkeyPatch) -> ModelRegistrySpy:
    """把模型注册表换成可计数的替身（默认有主模型，即管线可用）。"""
    import neobot_chat

    spy = ModelRegistrySpy()
    monkeypatch.setattr(neobot_chat, "get_model_registry", lambda: spy)
    return spy


# ── A1 / A2：状态变更 → 交管线 ──


async def test_sleep_with_change_goes_to_pipeline(registry: ModelRegistrySpy) -> None:
    """A1：/sleep 1h（合法时长 + 管线可用）→ 不出现固定文案，交管线生成回复。"""
    sleep_service = SleepService()
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 1h"), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert result.background is not None
    assert "你刚刚答应去睡觉" in result.background
    assert "1 小时" in result.background
    assert OLD_SLEEP_TEXT not in result.background
    assert sent == []  # 走管线的分支不再发文本
    assert registry.reads >= 1
    assert sleep_service.is_sleeping()


async def test_awake_with_change_goes_to_pipeline(registry: ModelRegistrySpy) -> None:
    """A2：/awake（在睡眠）→ 由模型回复，且睡眠确实结束。"""
    sleep_service = SleepService()
    sleep_service.sleep(600)
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/awake"), kind="group", queue_key="42"
    )

    assert result.background is not None
    assert "你刚被叫醒了" in result.background
    assert OLD_AWAKE_TEXT not in result.background
    assert sent == []
    assert not sleep_service.is_sleeping()


# ── 无状态变更也交 agent（用户 2026-09-13 要求：除纯工具命令外都以 agent 互动为主）──


@pytest.mark.parametrize("text", ["/sleep 2x", "/sleep 99h", "/sleep", "/awake"])
async def test_no_state_change_also_goes_to_agent(
    registry: ModelRegistrySpy, text: str
) -> None:
    """时长非法 / 缺参数 / 未睡眠时 awake 也要交主 Agent 组织回复，而不是回固定提示。"""
    sleep_service = SleepService()
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message(text), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert result.background is not None, "能调模型就必须交管线，不得直接回固定提示"
    assert sent == [], "走管线的分支不再自行发文本"
    assert registry.reads >= 1, "必须先探测管线可用性"
    assert "不要复述本条状态说明" in result.background
    assert not sleep_service.is_sleeping()


async def test_no_state_change_still_explains_the_facts(
    registry: ModelRegistrySpy,
) -> None:
    """交给 agent 的内容必须带**事实**，否则模型无从回答（时长非法 / 缺参数 / 未睡眠）。"""
    sleep_service = SleepService()
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=[]
    )

    bad = await service.handle_message(
        _message("/sleep 2x"), kind="group", queue_key="42"
    )
    assert bad.background is not None and "时长不合法" in bad.background

    missing = await service.handle_message(
        _message("/sleep"), kind="group", queue_key="42"
    )
    assert missing.background is not None and "没有给出时长" in missing.background

    awake = await service.handle_message(
        _message("/awake"), kind="group", queue_key="42"
    )
    assert awake.background is not None and "并没有在睡觉" in awake.background


async def test_sleep_without_service_goes_to_agent(registry: ModelRegistrySpy) -> None:
    """睡眠服务缺失：同样交 agent 自然告知，而不是直接回固定文案。"""
    sent: list[str] = []
    service = _service(sleep_service=None, standby=StandbyStub(False), sent=sent)

    result = await service.handle_message(
        _message("/sleep 1h"), kind="group", queue_key="42"
    )

    assert result.background is not None
    assert "睡眠功能当前不可用" in result.background
    assert sent == []


async def test_no_state_change_degrades_to_fixed_text_without_pipeline() -> None:
    """管线不可用时（待机中）无状态变更的分支仍必须回固定文案，保证用户有反馈。"""
    sleep_service = SleepService()
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(True), sent=sent
    )

    no_args = await service.handle_message(
        _message("/sleep"), kind="group", queue_key="42"
    )
    assert no_args.background is None
    assert sent and "请提供睡眠时长" in sent[0]

    not_sleeping = await service.handle_message(
        _message("/awake"), kind="group", queue_key="42"
    )
    assert not_sleeping.background is None
    assert sent[-1] == "我没有在睡觉呀。"


# ── A6：管线不可用 → 固定文案 ──


async def test_standby_degrades_to_fixed_text(registry: ModelRegistrySpy) -> None:
    """A6：待机中 → 固定文案，命令不报错、用户一定有反馈。"""
    sleep_service = SleepService()
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(True), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 1h"), kind="group", queue_key="42"
    )

    assert result.background is None
    assert sent and OLD_SLEEP_TEXT in sent[0]
    assert sleep_service.is_sleeping()


async def test_missing_model_degrades_to_fixed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A6：主模型未注册 → /sleep 与 /awake 都回固定文案。"""
    import neobot_chat

    monkeypatch.setattr(
        neobot_chat, "get_model_registry", lambda: ModelRegistrySpy(names=())
    )
    sleep_service = SleepService()
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 30m"), kind="group", queue_key="42"
    )
    assert result.background is None
    assert sent and OLD_SLEEP_TEXT in sent[0]
    assert sleep_service.is_sleeping()

    result = await service.handle_message(
        _message("/awake"), kind="group", queue_key="42"
    )
    assert result.background is None
    assert sent[-1] == OLD_AWAKE_TEXT
    assert not sleep_service.is_sleeping()


# ── A7：重复 /sleep ──


async def test_repeat_sleep_reports_remaining_and_resets(
    registry: ModelRegistrySpy,
) -> None:
    """A7：已在睡眠时 /sleep 30m → 提示剩余时长 + 「已按新时长重置」，剩余确为 30m。"""
    sleep_service = SleepService()
    sleep_service.sleep(7200)
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 30m"), kind="group", queue_key="42"
    )

    assert result.background is not None
    assert "已在睡眠中（剩余 2 小时）" in result.background
    assert "已按新时长重置" in result.background
    assert "你刚刚答应去睡觉" in result.background
    assert 1795 <= sleep_service.remaining_seconds() <= 1800


async def test_repeat_sleep_without_pipeline_keeps_notice() -> None:
    """A7 降级：管线不可用时重复 /sleep 也要给出同样的明确提示。"""
    sleep_service = SleepService()
    sleep_service.sleep(7200)
    sent: list[str] = []
    service = _service(sleep_service=sleep_service, standby=None, sent=sent)

    result = await service.handle_message(
        _message("/sleep 30m"), kind="group", queue_key="42"
    )

    assert result.background is None
    assert "已在睡眠中（剩余 2 小时）" in sent[0]
    assert "已按新时长重置" in sent[0]
    assert 1795 <= sleep_service.remaining_seconds() <= 1800


# ── A4：提示词可自定义 + 占位符容错 ──


def test_safe_format_keeps_unknown_and_tolerates_missing() -> None:
    assert safe_format("a {x} {y}", x=1) == "a 1 {y}"  # 未知占位符原样保留
    assert safe_format("没有占位符", x=1) == "没有占位符"  # 缺占位符不报错
    assert safe_format("字面量 {{x}}", x=1) == "字面量 {x}"  # 双层花括号转义
    assert safe_format("畸形 {a{b}", x=1) == "畸形 {a{b}"  # 畸形花括号不报错
    assert safe_format("值含花括号 {x}", x="{y}") == "值含花括号 {y}"
    assert safe_format("{x} 与 {{x}}", x=1) == "1 与 {x}"  # 占位符与转义并存


def test_sleep_prompt_fills_known_placeholders() -> None:
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    prompt = sleep_service.sleep_prompt(3600)
    assert "1 小时" in prompt
    assert "{duration}" not in prompt
    assert "{wake_at}" not in prompt
    assert "{duration}" in DEFAULT_SLEEP_CMD_PROMPT


async def test_custom_templates_drive_replies(
    tmp_path, registry: ModelRegistrySpy
) -> None:
    """A4：改 [sleep_cmd] / [awake_cmd] 后回复随模板变化；未知占位符不报错。"""
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text(
        "[sleep_cmd]\n"
        "template = '''去睡吧，{duration}，未知 {who} 原样保留'''\n"
        "[awake_cmd]\n"
        "template = '''醒啦，睡了 {elapsed}'''\n",
        encoding="utf-8",
    )
    store = PromptStore(tmp_path)
    sleep_service = SleepService(prompt_store=store)
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 1h"), kind="group", queue_key="42"
    )
    assert result.background is not None
    assert "去睡吧，1 小时，未知 {who} 原样保留" in result.background

    result = await service.handle_message(
        _message("/awake"), kind="group", queue_key="42"
    )
    assert result.background is not None
    assert "醒啦，睡了" in result.background


async def test_template_without_placeholders_is_fine(
    tmp_path, registry: ModelRegistrySpy
) -> None:
    """A4：模板里缺少占位符不报错。"""
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text(
        "[sleep_cmd]\ntemplate = '''我就去睡了'''\n", encoding="utf-8"
    )
    sleep_service = SleepService(prompt_store=PromptStore(tmp_path))
    sent: list[str] = []
    service = _service(
        sleep_service=sleep_service, standby=StandbyStub(False), sent=sent
    )

    result = await service.handle_message(
        _message("/sleep 1h"), kind="group", queue_key="42"
    )

    assert result.background is not None
    assert "我就去睡了" in result.background
