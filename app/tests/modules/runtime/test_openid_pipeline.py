"""runtime 管线 openid 字符串化：不 int() openid，展示完整 openid。

覆盖：后台回复通道推断（openid → official）、凭据签发对 openid 的安全处理、
notice 用户名解析兜底展示完整 openid。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_contracts.ports.logging import NullLogger

from neobot_app.reply.orchestrator_parts.lifecycle_shutdown import LifecycleShutdownMixin
from neobot_app.runtime.pipeline_parts.credential import _PipelineCredentialMixin
from neobot_app.runtime.pipeline_parts.notice import _PipelineNoticeMixin

OPENID = "openid_user_abcdef1234567890"


class _ChannelStub(LifecycleShutdownMixin):
    def __init__(self, adapter) -> None:
        self._adapter = adapter


def test_background_channel_treats_openid_as_official() -> None:
    adapter = SimpleNamespace(active_channels=("onebot", "official"), channels_for_conversation=lambda conv: ())
    stub = _ChannelStub(adapter)

    channel = stub._background_reply_channel("group", "openid_group_xyz", None)

    assert channel == "official"


def test_background_channel_keeps_real_group_as_onebot() -> None:
    adapter = SimpleNamespace(active_channels=("onebot", "official"), channels_for_conversation=lambda conv: ())
    stub = _ChannelStub(adapter)

    assert stub._background_reply_channel("group", "123456789", None) == "onebot"


class _CredentialStub(_PipelineCredentialMixin):
    def __init__(self) -> None:
        self._credential_manager = SimpleNamespace(
            has_pending_or_active=lambda chat_flow=None: False,
            try_issue=lambda **kwargs: (_ for _ in ()).throw(AssertionError("不应签发")),
        )
        self._logger = NullLogger()
        self._bot_account_id = lambda message: 10001

    def _maybe_cleanup_credentials(self) -> None:
        pass


async def test_credential_issuer_openid_does_not_int_crash() -> None:
    """openid 用户不触发 int() 崩溃；未绑定 trusted QQ 时直接放行（无签发权限）。"""
    stub = _CredentialStub()
    message = SimpleNamespace(user_id=OPENID, neobot_channel="official")

    issued = await stub._try_issue_credential(
        message, kind="group", queue_key="openid_group_xyz", queue=SimpleNamespace()
    )

    assert issued is False


class _NoticeStub(_PipelineNoticeMixin):
    def __init__(self) -> None:
        self._profile_service = None
        self._logger = NullLogger()
        self.adapter = None

    def _get_dependency_timeout_seconds(self) -> float:
        return 0.05


async def test_notice_resolve_name_shows_full_openid() -> None:
    stub = _NoticeStub()

    name = await stub._resolve_name(OPENID)

    assert name == f"openid:{OPENID}"
