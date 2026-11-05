"""线协议解析：合法字段、默认值与各类非法输入的错误码。"""

from __future__ import annotations

import pytest

from neobot_app.dsh_gateway.models import (
    MAX_ACKS_PER_SYNC,
    MAX_REPORTS_PER_SYNC,
    DaemonCommand,
    GatewayProtocolError,
    SyncRequest,
    SyncResponse,
    parse_sync_request,
)


def _valid_payload(**overrides):
    payload = {
        "v": 1,
        "daemon_id": "devbox-1",
        "seq": 3,
        "cursor": 2,
        "reports": [
            {
                "id": "r1",
                "kind": "task.event",
                "task_id": "t1",
                "payload": {"status": "running"},
                "created_at": 1.5,
            }
        ],
        "acks": ["c-9"],
        "health": {"sessions": 2},
    }
    payload.update(overrides)
    return payload


def test_parse_sync_request_happy_path():
    request = parse_sync_request(_valid_payload())

    assert isinstance(request, SyncRequest)
    assert request.v == 1
    assert request.daemon_id == "devbox-1"
    assert request.seq == 3
    assert request.cursor == 2
    assert request.acks == ["c-9"]
    assert request.health == {"sessions": 2}
    assert len(request.reports) == 1
    report = request.reports[0]
    assert (report.id, report.kind, report.task_id) == ("r1", "task.event", "t1")
    assert report.payload == {"status": "running"}
    assert report.created_at == 1.5


def test_parse_sync_request_applies_defaults():
    request = parse_sync_request({"daemon_id": "d", "seq": 0})

    assert request.v == 1
    assert request.cursor == 0
    assert request.acks == []
    assert request.reports == []
    assert request.health == {}


def test_parse_sync_request_accepts_null_optional_groups():
    request = parse_sync_request({"daemon_id": "d", "seq": 1, "acks": None, "reports": None, "health": None})

    assert request.acks == []
    assert request.reports == []
    assert request.health == {}


def test_parse_sync_request_strips_ack_ids():
    request = parse_sync_request({"daemon_id": "d", "seq": 1, "acks": [" c-1 ", "c-2"]})

    assert request.acks == ["c-1", "c-2"]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ([], "invalid_body"),
        ("not-an-object", "invalid_body"),
        ({"daemon_id": "d", "seq": 1, "v": 2}, "unsupported_version"),
        ({"daemon_id": "d", "seq": 1, "v": "1"}, "unsupported_version"),
        ({"seq": 1}, "invalid_daemon_id"),
        ({"daemon_id": "   ", "seq": 1}, "invalid_daemon_id"),
        ({"daemon_id": 42, "seq": 1}, "invalid_daemon_id"),
        ({"daemon_id": "d" * 129, "seq": 1}, "invalid_daemon_id"),
        ({"daemon_id": "d"}, "invalid_seq"),
        ({"daemon_id": "d", "seq": -1}, "invalid_seq"),
        ({"daemon_id": "d", "seq": True}, "invalid_seq"),
        ({"daemon_id": "d", "seq": "1"}, "invalid_seq"),
        ({"daemon_id": "d", "seq": 1, "cursor": -2}, "invalid_cursor"),
        ({"daemon_id": "d", "seq": 1, "cursor": "x"}, "invalid_cursor"),
        ({"daemon_id": "d", "seq": 1, "reports": "nope"}, "invalid_reports"),
        ({"daemon_id": "d", "seq": 1, "reports": [{"payload": {}}]}, "invalid_reports"),
        ({"daemon_id": "d", "seq": 1, "reports": [{"kind": "x", "payload": []}]}, "invalid_reports"),
        ({"daemon_id": "d", "seq": 1, "reports": [{"kind": "x", "created_at": "now"}]}, "invalid_reports"),
        ({"daemon_id": "d", "seq": 1, "health": []}, "invalid_health"),
        ({"daemon_id": "d", "seq": 1, "acks": "c-1"}, "invalid_acks"),
        ({"daemon_id": "d", "seq": 1, "acks": [""]}, "invalid_acks"),
        ({"daemon_id": "d", "seq": 1, "acks": ["   "]}, "invalid_acks"),
        ({"daemon_id": "d", "seq": 1, "acks": [1]}, "invalid_acks"),
        ({"daemon_id": "d", "seq": 1, "acks": ["c" * 129]}, "invalid_acks"),
    ],
)
def test_parse_sync_request_rejects_invalid_input(payload, code):
    with pytest.raises(GatewayProtocolError) as excinfo:
        parse_sync_request(payload)
    assert excinfo.value.code == code
    assert str(excinfo.value)


def test_parse_sync_request_limits_ack_batch():
    payload = _valid_payload(acks=[f"c-{index}" for index in range(MAX_ACKS_PER_SYNC + 1)])

    with pytest.raises(GatewayProtocolError) as excinfo:
        parse_sync_request(payload)

    assert excinfo.value.code == "invalid_acks"


def test_parse_sync_request_limits_report_batch():
    payload = _valid_payload(reports=[{"kind": "task.event"}] * (MAX_REPORTS_PER_SYNC + 1))

    with pytest.raises(GatewayProtocolError) as excinfo:
        parse_sync_request(payload)

    assert excinfo.value.code == "too_many_reports"


def test_protocol_error_serializes_code_and_message():
    error = GatewayProtocolError("invalid_seq", "seq 必须是整数")

    assert error.to_dict() == {"code": "invalid_seq", "message": "seq 必须是整数"}


def test_sync_response_serializes_commands():
    response = SyncResponse(
        daemon_id="d",
        cursor=7,
        commands=[
            DaemonCommand(id="c1", kind="task.dispatch", task_id="t1", payload={"x": 1}),
            DaemonCommand(id="c2", kind="task.cancel"),
        ],
    )

    assert response.to_dict() == {
        "v": 1,
        "daemon_id": "d",
        "cursor": 7,
        "commands": [
            {"id": "c1", "kind": "task.dispatch", "task_id": "t1", "payload": {"x": 1}},
            {"id": "c2", "kind": "task.cancel", "task_id": "", "payload": {}},
        ],
    }
