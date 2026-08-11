"""凭据管线级集成测试:真实事件流入 → 签发 → 风险操作执行。"""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace


from neobot_app.commands.permissions import PermissionManager
from neobot_app.credentials.service import CredentialManager
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.skills.group_management import GroupManagementSkill

SUPER = 10000
NORMAL = 99999


def _config():
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[])
    bot = SimpleNamespace(account=88888)
    return SimpleNamespace(chat=chat, bot=bot)


def _group_event(text: str, *, user_id: int, message_id: int = 1) -> dict:
    return {
        "post_type": "message",
        "message_type": "group",
        "message_id": message_id,
        "user_id": user_id,
        "group_id": 123,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _build_pipeline(credential_manager) -> EventPipeline:
    from neobot_app.message.queue import MessageQueue

    pipeline = object.__new__(EventPipeline)
    pipeline._group_queue = MessageQueue()
    pipeline._friend_queue = MessageQueue()
    pipeline.adapter = SimpleNamespace(
        send=lambda conv, segments: None,
    )
    pipeline._profile_service = None
    pipeline._image_parse_service = None
    pipeline._archive_summary_service = None
    pipeline._config = _config()
    pipeline._reply_orchestrator = None
    pipeline._reply_block_registry = None
    pipeline._command_service = None
    pipeline._credential_manager = credential_manager
    pipeline._willing_service = None
    pipeline._inbound_pipeline = None
    pipeline._logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
    )
    pipeline._recent_message_ids = deque(maxlen=64)
    pipeline._recent_message_ids_lock = asyncio.Lock()
    pipeline._replying_queues = set()
    pipeline._post_reply_willing = {}
    pipeline._pending_image_willing = {}
    pipeline._background_tasks = set()
    pipeline._stopping = False
    pipeline._last_credential_cleanup = 0.0
    return pipeline


async def test_end_to_end_issue_and_kick() -> None:
    """完整链路:申请 → 超管群内发码 → 签发 → 踢人成功。"""
    manager = CredentialManager(PermissionManager(_config()))
    # 1. 申请凭据(模拟 credential__request)
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=88888,
        cred_type="one_time",
    )
    assert credential.status == "pending"

    # 2. 超管在群内发送凭据文本(真实事件,文本带"发送者: "前缀格式也应命中)
    pipeline = _build_pipeline(manager)
    event = _group_event(f"  {credential.code}  ", user_id=SUPER)
    # 模拟 event_message__to_text 的行为:真实消息带发送者前缀
    # 此处直接调用 _try_issue_credential 验证纯文本匹配
    message = _parse_group_message(event)
    handled = await pipeline._try_issue_credential(
        message, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled is True
    assert credential.status == "active"
    assert credential.issuer_id == SUPER

    # 3. 踢人(凭据消费)
    adapter = _FakeAdapter()
    skill = GroupManagementSkill(adapter=adapter, credential_manager=manager)
    result = await skill.execute(
        "manage_group",
        {"action": "kick", "group_id": 123, "user_id": NORMAL},
    )
    assert result is not None and '"ok": true' in result
    assert adapter.calls[0][0] == "set_group_kick"


async def test_issue_matches_pure_text_segment() -> None:
    """签发匹配使用纯文本段(修复 P0:event_message__to_text 的'发送者: '前缀不应进入匹配)。"""
    manager = CredentialManager(PermissionManager(_config()))
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=88888, cred_type="one_time"
    )
    pipeline = _build_pipeline(manager)
    # 真实管线:消息 text 段就是凭据文本(前缀是 event_message__to_text 渲染时拼接)
    message = _parse_group_message(_group_event(f"  {credential.code}  ", user_id=SUPER))
    handled = await pipeline._try_issue_credential(
        message, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled is True
    assert credential.status == "active"
    # 确认 _credential_message_text 提取结果不含"昵称: "前缀格式
    from neobot_app.runtime.event_pipeline import _credential_message_text

    assert _credential_message_text(message).strip() == credential.code


async def test_issue_rejects_normal_user() -> None:
    manager = CredentialManager(PermissionManager(_config()))
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=88888, cred_type="one_time"
    )
    pipeline = _build_pipeline(manager)
    sent: list = []
    pipeline.adapter = SimpleNamespace(send=lambda conv, segments: sent.append(segments))
    message = _parse_group_message(_group_event(credential.code, user_id=NORMAL))
    handled = await pipeline._try_issue_credential(
        message, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled is True
    assert credential.status == "pending"  # 未签发
    assert sent, "应发送权限不足提示"


async def test_issue_rejects_bot_self() -> None:
    manager = CredentialManager(PermissionManager(_config()))
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=88888, cred_type="one_time"
    )
    pipeline = _build_pipeline(manager)
    message = _parse_group_message(_group_event(credential.code, user_id=88888))  # bot 自己
    handled = await pipeline._try_issue_credential(
        message, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled is False  # bot 自我签发被拒绝
    assert credential.status == "pending"


async def test_requeued_code_does_not_retrigger() -> None:
    manager = CredentialManager(PermissionManager(_config()))
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=88888, cred_type="one_time"
    )
    pipeline = _build_pipeline(manager)
    sent: list = []

    class _Adapter:
        async def send(self, conv, segments):
            sent.append(segments)

    pipeline.adapter = _Adapter()
    # 首次签发
    message = _parse_group_message(_group_event(credential.code, user_id=SUPER))
    handled = await pipeline._try_issue_credential(
        message, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled is True
    assert credential.status == "active"
    # 普通用户重发:应被权限校验拒绝,不触发"凭据已确认"成功提示
    sent.clear()
    message2 = _parse_group_message(_group_event(credential.code, user_id=NORMAL))
    handled2 = await pipeline._try_issue_credential(
        message2, kind="group", queue_key="123", queue=pipeline._group_queue
    )
    assert handled2 is True
    assert sent, "重发应收到权限不足提示"
    assert "没有权限" in sent[0][0]["data"]["text"] or "权限" in str(sent)


def _parse_group_message(event: dict):
    from neobot_adapter.model.message import GroupMessage
    from neobot_adapter.utils.parse import safe_parse_model

    return safe_parse_model(event, GroupMessage)


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_api(self, api: str, params: dict) -> str:
        self.calls.append((api, params))
        return f"ok:{api}"
