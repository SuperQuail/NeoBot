"""双通道身份：逐通道 BotProfile/账号、dual 不回写配置、消息级自我识别。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import neobot_adapter.request.private as private_module
from neobot_adapter.model.message import GroupMessage, MessageSegment, PrivateMessage
from neobot_app.bot_detect import BotDetector
from neobot_app.commands.service import CommandService
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.queue import MessageQueue, is_bot_message
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.willing.service import WillingService
from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME

ONEBOT_ACCOUNT = 10001
OFFICIAL_ACCOUNT = 20002
USER_ACCOUNT = 30003

_OFFICIAL_VERSION = {
    "status": "ok",
    "retcode": 0,
    "data": {"app_name": OFFICIAL_ADAPTER_APP_NAME},
}
_ONEBOT_VERSION = {"status": "ok", "retcode": 0, "data": {"app_name": "NapCat.Onebot"}}


def _login(account: int, nickname: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "retcode": 0,
        "data": {"user_id": account, "nickname": nickname},
    }


class _DualAdapter:
    """双通道假适配器：active/connected 通道可配，按 (action, channel) 返回脚本响应。"""

    def __init__(
        self,
        *,
        active_channels: tuple[str, ...] = ("onebot", "official"),
        connected_channels: tuple[str, ...] = ("onebot", "official"),
        connected: bool = True,
    ) -> None:
        self.active_channels = active_channels
        self.connected_channels = connected_channels
        self.connected = connected
        self.calls: list[tuple[str, str | None]] = []
        self.responses: dict[tuple[str, str], Any] = {
            ("get_version_info", "onebot"): _ONEBOT_VERSION,
            ("get_login_info", "onebot"): _login(ONEBOT_ACCOUNT, "Neo-OneBot"),
            ("get_version_info", "official"): _OFFICIAL_VERSION,
            ("get_login_info", "official"): _login(OFFICIAL_ACCOUNT, "Neo-Official"),
        }

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
        channel: str | None = None,
    ) -> Any:
        self.calls.append((action, channel))
        return self.responses.get((action, channel or ""))


@pytest.fixture(autouse=True)
def _stub_uin_range(monkeypatch) -> None:
    """身份判定末尾会刷新 UIN 段；单测里断开真实的 OneBot 请求代理。"""

    async def _unavailable():
        raise RuntimeError("OneBot 未连接")

    monkeypatch.setattr(private_module, "get_robot_uin_range", _unavailable)


def _config(mode: str = "dual", *, account: int = 0, official_mode: str = "auto") -> BotConfig:
    config = BotConfig()
    config.bot.account = account
    config.bot.official_mode = official_mode
    config.adapter.mode = mode
    return config


def _group(
    message_id: int,
    *,
    user_id: int,
    self_id: int | None = ONEBOT_ACCOUNT,
    at: int | None = None,
    text: str = "在吗",
    channel: str | None = None,
    group_id: int = 42,
) -> GroupMessage:
    segments = []
    if at is not None:
        segments.append(MessageSegment(type="at", data={"qq": str(at)}))
    segments.append(MessageSegment(type="text", data={"text": text}))
    return GroupMessage(
        message_id=message_id,
        user_id=user_id,
        group_id=group_id,
        self_id=self_id,
        message=segments,
        raw_message=text,
        neobot_channel=channel,
    )


async def _detect(
    adapter: Any,
    config: BotConfig,
    *,
    group: Any = None,
    friend: Any = None,
):
    detector = BotDetector(adapter)
    detector.bind(config, group_queue=group, friend_queue=friend)
    return detector, await detector.resolve_identity()


async def test_dual_resolves_each_channel_profile_and_account() -> None:
    """两个已连接通道各取一次 version/login，按通道存 profile/账号；主档 onebot 优先。"""
    adapter = _DualAdapter()
    group, friend = MessageQueue(), MessageQueue()
    config = _config()
    detector, primary = await _detect(adapter, config, group=group, friend=friend)

    profiles = detector.profiles
    assert set(profiles) == {"onebot", "official"}
    assert profiles["onebot"].kind == "unofficial"
    assert profiles["official"].kind == "official"
    assert profiles["official"].nickname == "Neo-Official"
    assert detector.accounts == {"onebot": ONEBOT_ACCOUNT, "official": OFFICIAL_ACCOUNT}
    assert detector.account_for("onebot") == ONEBOT_ACCOUNT
    assert detector.account_for("official") == OFFICIAL_ACCOUNT
    assert detector.account_for("missing") == 0
    assert detector.profile_for("missing").kind == "unknown"

    assert primary.channel == "onebot"
    assert primary.account == ONEBOT_ACCOUNT
    assert detector.profile is profiles["onebot"]

    # 账号只留在 detector 与队列：dual 模式绝不回写 config.bot.account
    assert config.bot.account == 0
    assert group.bot_accounts == {ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT}
    assert friend.bot_accounts == {ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT}
    assert group.bot_account == ONEBOT_ACCOUNT
    assert friend.bot_account == ONEBOT_ACCOUNT


async def test_dual_channel_api_called_with_explicit_channel() -> None:
    """每个通道都用显式 channel 调 get_version_info / get_login_info。"""
    adapter = _DualAdapter()
    await _detect(adapter, _config())

    assert adapter.calls.count(("get_version_info", "onebot")) == 1
    assert adapter.calls.count(("get_version_info", "official")) == 1
    assert adapter.calls.count(("get_login_info", "onebot")) == 1
    assert adapter.calls.count(("get_login_info", "official")) == 1


async def test_dual_never_writes_configured_account_to_config() -> None:
    """dual 下两个号都来自 API：旧配置账号既不生效也不被改写。"""
    adapter = _DualAdapter()
    config = _config(account=999)
    detector, _ = await _detect(adapter, config)

    assert config.bot.account == 999
    assert detector.accounts == {"onebot": ONEBOT_ACCOUNT, "official": OFFICIAL_ACCOUNT}
    assert detector.account_for("onebot") == ONEBOT_ACCOUNT
    assert detector.account_for("official") == OFFICIAL_ACCOUNT


async def test_dual_ignores_stale_mode_from_config_adapter_section() -> None:
    """模式仍为 onebot 但门面已启用两个通道（切换中）时不回写配置。"""
    adapter = _DualAdapter()
    config = _config("onebot")
    detector, _ = await _detect(adapter, config)

    assert config.bot.account == 0
    assert detector.accounts == {"onebot": ONEBOT_ACCOUNT, "official": OFFICIAL_ACCOUNT}


async def test_single_channel_keeps_config_backfill_and_queue_sync() -> None:
    """单通道门面保持旧行为：account=0 时把 API 账号回填运行期配置并同步队列。"""
    adapter = _DualAdapter(active_channels=("official",), connected_channels=("official",))
    group, friend = MessageQueue(), MessageQueue()
    config = _config("official")
    detector, primary = await _detect(adapter, config, group=group, friend=friend)

    assert primary.channel == "official"
    assert primary.account == OFFICIAL_ACCOUNT
    assert config.bot.account == OFFICIAL_ACCOUNT
    assert group.bot_account == OFFICIAL_ACCOUNT
    assert group.bot_accounts == {OFFICIAL_ACCOUNT}
    assert friend.bot_accounts == {OFFICIAL_ACCOUNT}


async def test_official_mode_is_forced_for_every_channel() -> None:
    """official_mode 强制值对每个通道都生效。"""
    detector, _ = await _detect(_DualAdapter(), _config(official_mode="official"))

    for profile in detector.profiles.values():
        assert profile.kind == "official"
        assert profile.source == "forced"


async def test_only_connected_channels_are_resolved() -> None:
    """官方未连接时只判定 onebot，另一通道保持 unknown（不 KeyError）。"""
    adapter = _DualAdapter(connected_channels=("onebot",))
    detector, _ = await _detect(adapter, _config())

    assert set(detector.profiles) == {"onebot"}
    assert detector.profile_for("official").kind == "unknown"
    assert [channel for _, channel in adapter.calls] == ["onebot", "onebot"]


async def test_mode_switch_to_single_channel_drops_disabled_profile() -> None:
    """dual 切回单通道后旧通道结论作废，只有当前账号回填配置。"""
    adapter = _DualAdapter()
    config = _config()
    detector, _ = await _detect(adapter, config)
    assert set(detector.profiles) == {"onebot", "official"}

    adapter.active_channels = ("onebot",)
    adapter.connected_channels = ("onebot",)
    config.adapter.mode = "onebot"
    profile = await detector.resolve_identity()

    assert set(detector.profiles) == {"onebot"}
    assert profile.account == ONEBOT_ACCOUNT
    assert config.bot.account == ONEBOT_ACCOUNT


async def test_channel_api_failure_keeps_previous_profile() -> None:
    """显式通道不可用（failed）时保持该通道既有结论，不把状态清空。"""
    adapter = _DualAdapter()
    detector, _ = await _detect(adapter, _config())

    adapter.responses[("get_version_info", "official")] = {
        "status": "failed",
        "retcode": -1,
        "message": "official 未连接",
    }
    await detector.resolve_identity()

    assert detector.profile_for("official").kind == "official"
    assert detector.account_for("official") == OFFICIAL_ACCOUNT


def test_queue_bot_accounts_default_from_bot_account() -> None:
    """队列构造时 bot_accounts 默认由 bot_account 得到；显式集合覆盖两种通道账号。"""
    assert MessageQueue(bot_account=ONEBOT_ACCOUNT).bot_accounts == {ONEBOT_ACCOUNT}
    queue = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    assert queue.bot_accounts == {ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT}
    assert queue.clone().bot_accounts == {ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT}


def test_queue_self_id_message_is_not_a_user_message() -> None:
    """消息级 self 判定：self_id 回显优先，其次是 bot_accounts；普通用户仍按用户计权。"""
    queue = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    from_user = _group(1, user_id=USER_ACCOUNT)
    from_other_bot = _group(2, user_id=OFFICIAL_ACCOUNT)
    self_echo = _group(3, user_id=ONEBOT_ACCOUNT, self_id=ONEBOT_ACCOUNT)

    assert queue._compute_message_weight(from_user) == 1.0
    assert queue._compute_message_weight(from_other_bot) == queue.self_sent_weight
    assert queue._compute_message_weight(self_echo) == queue.self_sent_weight
    assert is_bot_message(from_user, queue.bot_accounts) is False
    assert is_bot_message(from_other_bot, queue.bot_accounts) is True
    # 账号解析前（集合为空）也能靠消息级 self_id 认出自身回显
    assert is_bot_message(self_echo, ()) is True


def test_queue_at_mention_matches_either_bot() -> None:
    """at 任一 bot 都触发强制回复；@普通用户不算。"""
    queue = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    queue.push("42", _group(10, user_id=USER_ACCOUNT, at=OFFICIAL_ACCOUNT))
    assert "<最新消息为@你的内容" in queue.to_text("42")

    other = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    other.push("42", _group(11, user_id=USER_ACCOUNT, at=USER_ACCOUNT))
    assert "<最新消息为@你的内容" not in other.to_text("42")


def test_role_messages_treat_both_bots_as_assistant() -> None:
    """双通道下任一 bot 的发言都渲染成 assistant，用户消息仍是 user。"""
    queue = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    queue.push("42", _group(20, user_id=OFFICIAL_ACCOUNT, text="官方这边"))
    queue.push("42", _group(21, user_id=USER_ACCOUNT, text="用户消息"))

    messages = build_role_messages(queue, "42", bot_account=0)

    roles = [message["role"] for message in messages]
    assert roles.count("assistant") == 1
    assert roles[-1] == "user"


def test_pipeline_bot_self_prefers_message_self_id() -> None:
    """事件管线按消息级身份过滤：任一 bot 的发言与 self_id 回显都不当用户。"""
    pipeline = object.__new__(EventPipeline)
    pipeline._config = _config()
    group_queue = MessageQueue(
        bot_account=ONEBOT_ACCOUNT,
        bot_accounts={ONEBOT_ACCOUNT, OFFICIAL_ACCOUNT},
    )
    pipeline._group_queue = group_queue
    pipeline._friend_queue = group_queue

    assert pipeline._is_bot_self(_group(30, user_id=OFFICIAL_ACCOUNT)) is True
    assert pipeline._is_bot_self(_group(31, user_id=USER_ACCOUNT)) is False
    # 自身回显：user_id == self_id，即便不在 bot_accounts 也算自己
    echo = _group(32, user_id=USER_ACCOUNT, self_id=USER_ACCOUNT)
    assert pipeline._is_bot_self(echo) is True


def test_command_service_bot_account_uses_message_self_id() -> None:
    """命令系统的 @bot 判定按消息 self_id，不依赖 config.bot.account。"""
    service = object.__new__(CommandService)
    service._config = _config()

    assert service._bot_account(_group(40, user_id=USER_ACCOUNT, self_id=OFFICIAL_ACCOUNT)) == OFFICIAL_ACCOUNT
    assert service._bot_account(None) == 0


def test_willing_official_platform_uses_message_channel() -> None:
    """官方性按消息通道查 detector.profile_for；无通道回退主档。"""
    service = object.__new__(WillingService)
    service._config = _config()
    service._bot_detector = SimpleNamespace(
        profile=SimpleNamespace(kind="unofficial"),
        profile_for=lambda channel: {
            "onebot": SimpleNamespace(kind="unofficial"),
            "official": SimpleNamespace(kind="official"),
        }.get(channel, SimpleNamespace(kind="unknown")),
    )

    assert service._is_official_platform(_group(50, user_id=USER_ACCOUNT, channel="official")) is True
    assert service._is_official_platform(_group(51, user_id=USER_ACCOUNT, channel="onebot")) is False
    assert service._is_official_platform(_group(52, user_id=USER_ACCOUNT)) is False


def test_willing_mentioned_bot_prefers_message_self_id() -> None:
    """@ 判定优先用消息 self_id，配置里的旧账号不参与。"""
    service = object.__new__(WillingService)
    service._config = _config(account=999)
    service._bot_detector = None

    message = _group(60, user_id=USER_ACCOUNT, self_id=OFFICIAL_ACCOUNT, at=OFFICIAL_ACCOUNT)
    assert service._mentioned_bot(message) is True

    plain = PrivateMessage(
        message_id=61,
        user_id=USER_ACCOUNT,
        self_id=OFFICIAL_ACCOUNT,
        message=[MessageSegment(type="text", data={"text": "你好"})],
        raw_message="你好",
    )
    assert service._mentioned_bot(plain) is False
