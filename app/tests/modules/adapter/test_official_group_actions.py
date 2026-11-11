"""官方群管理 action：禁言/踢人/入群审批映射到官方接口。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.official import actions
from neobot_adapter.official.send import OfficialApiError


class _Identity:
    def openid(self, synthetic: int, kind: str) -> str | None:
        return {
            ("group", 8001): "group-openid",
            ("user", 9001): "member-openid",
        }.get((kind, synthetic))


class _Api:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request(self, method: str, path: str, *, body=None, timeout: float = 10.0):
        self.calls.append({"method": method, "path": path, "body": body})
        if path.endswith("/batch_remove_members"):
            return {"code": 0, "data": {"remove_members_result": "success"}}
        return {"code": 0, "data": {}}


def _adapter() -> SimpleNamespace:
    return SimpleNamespace(identity=_Identity(), api=_Api())


async def test_set_group_ban_adds_member_mute() -> None:
    adapter = _adapter()
    result = await actions.dispatch(
        adapter, "set_group_ban", {"group_id": 8001, "user_id": 9001, "duration": 600}
    )

    assert result["status"] == "ok"
    call = adapter.api.calls[0]
    assert call["path"] == "/v2/groups/group-openid/restrict_chat_setting"
    member = call["body"]["members"][0]
    assert member["op"] == "add"
    assert member["member_openid"] == "member-openid"
    assert member["mute_expire_at"]


async def test_set_group_ban_zero_cancels_mute() -> None:
    adapter = _adapter()
    await actions.dispatch(adapter, "set_group_ban", {"group_id": 8001, "user_id": 9001, "duration": 0})

    member = adapter.api.calls[0]["body"]["members"][0]
    assert member == {"op": "del", "member_openid": "member-openid", "mute_expire_at": ""}


async def test_set_group_kick_uses_batch_remove() -> None:
    adapter = _adapter()
    result = await actions.dispatch(
        adapter,
        "set_group_kick",
        {"group_id": 8001, "user_id": 9001, "reject_add_request": True},
    )

    assert result["status"] == "ok"
    assert adapter.api.calls[0]["path"] == "/v2/groups/group-openid/batch_remove_members"
    assert adapter.api.calls[0]["body"] == {
        "member_openids": ["member-openid"],
        "add_to_member_blacklist": True,
    }


async def test_batch_remove_permission_error_is_failed() -> None:
    adapter = _adapter()

    async def deny(*args, **kwargs):
        raise OfficialApiError("无权限", code=11253, status=403)

    adapter.api.request = deny
    result = await actions.dispatch(adapter, "set_group_kick", {"group_id": 8001, "user_id": 9001})

    assert result["status"] == "failed"
    assert "11253" in result["message"]


async def test_set_group_add_request_maps_approval() -> None:
    adapter = _adapter()
    result = await actions.dispatch(
        adapter,
        "set_group_add_request",
        {"group_id": 8001, "user_id": 9001, "flag": "req-1", "approve": False, "reason": "拒绝"},
    )

    assert result["status"] == "ok"
    call = adapter.api.calls[0]
    assert call["path"] == "/v2/groups/group-openid/approval_join_request/member-openid"
    assert call["body"] == {"op": "decline", "join_request_id": "req-1", "reject_reason": "拒绝"}


async def test_unknown_group_management_fails_explicitly() -> None:
    adapter = _adapter()
    result = await actions.dispatch(adapter, "set_group_leave", {"group_id": 8001})
    assert result["status"] == "failed"
    assert "没有主动退群接口" in result["message"]
