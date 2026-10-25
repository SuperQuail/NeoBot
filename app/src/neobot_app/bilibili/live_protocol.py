"""B站直播弹幕协议层：帧收发、Brotli/zlib 解压、事件映射。

帧格式与事件字段参考 blivedm（MIT，Copyright 2018 xfgryujk）：
https://github.com/xfgryujk/blivedm
本文件里的 protobuf 消息定义来自 blivedm/models/pb.py，做了去注解精简。
"""

import base64
import dataclasses
import json
import struct
import zlib
from collections import Counter
from typing import Annotated, Any

import brotli
from pure_protobuf.annotations import Field as PbField
from pure_protobuf.message import BaseMessage

from neobot_app.utils.logger import get_module_logger

#: 弹幕协议头：总长度 / 头长度 / 协议版本 / 操作码 / 序号（大端 16 字节）。
HEADER = struct.Struct(">IHHII")
HEADER_SIZE = HEADER.size
_MAX_DEPTH = 4

_LOGGER = get_module_logger("bilibili.live_protocol")
#: 解包失败计数（坏帧/解压失败）：坏帧不再静默，运行期可读取定位 CDN/协议问题。
_decode_failures: Counter[str] = Counter()


def decode_failures() -> dict[str, int]:
    """解包失败计数快照：frame（头/长度异常）、zlib、brotli、depth（嵌套过深）。"""
    return dict(_decode_failures)


def _count_failure(kind: str, detail: str) -> None:
    _decode_failures[kind] += 1
    _LOGGER.debug(f"B站直播弹幕包解析失败（{kind}）：{detail}，累计 {_decode_failures[kind]} 次")


class LiveAuthError(RuntimeError):
    """op=8 认证回复 code 非 0。"""


# ── 帧 ──


def encode_packet(op: int, body: bytes = b"", protover: int = 1) -> bytes:
    """组一个 B站弹幕包（16 字节头 + body）。"""
    payload = bytes(body or b"")
    return HEADER.pack(HEADER_SIZE + len(payload), HEADER_SIZE, int(protover), int(op), 1) + payload


def decode_packets(data: bytes) -> list[tuple[int, bytes]]:
    """拆弹幕包；protover=2 用 zlib、protover=3 用 Brotli 解开并递归拆内部包。"""
    return _decode_packets(bytes(data or b""), 0)


def _decode_packets(data: bytes, depth: int) -> list[tuple[int, bytes]]:
    if depth > _MAX_DEPTH:
        _count_failure("depth", f"嵌套超过 {_MAX_DEPTH} 层")
        return []
    packets: list[tuple[int, bytes]] = []
    offset = 0
    while offset + HEADER_SIZE <= len(data):
        try:
            total, header_len, protover, op, _seq = HEADER.unpack_from(data, offset)
        except struct.error as exc:
            _count_failure("frame", f"包头解不出（offset={offset}）：{exc}")
            break
        if header_len < HEADER_SIZE or total < header_len or offset + total > len(data):
            _count_failure(
                "frame",
                f"包长度异常（total={total} header_len={header_len} 剩余={len(data) - offset}）",
            )
            break
        body = data[offset + header_len : offset + total]
        if protover == 2:
            try:
                packets.extend(_decode_packets(zlib.decompress(body), depth + 1))
            except (zlib.error, ValueError) as exc:
                _count_failure("zlib", f"{type(exc).__name__}: {exc}")
        elif protover == 3:
            try:
                packets.extend(_decode_packets(brotli.decompress(body), depth + 1))
            except Exception as exc:
                _count_failure("brotli", f"{type(exc).__name__}: {exc}")
        else:
            packets.append((op, body))
        offset += total
    return packets


def check_auth_reply(body: bytes) -> None:
    """校验 op=8 认证回复；code 非 0 抛 LiveAuthError。"""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise LiveAuthError("认证回复不是合法 JSON") from exc
    code = _to_int(payload.get("code")) if isinstance(payload, dict) else -1
    if code != 0:
        raise LiveAuthError(f"弹幕服务器认证失败: code={code}")


# ── 事件 ──


@dataclasses.dataclass(frozen=True, slots=True)
class LiveEvent:
    """归一化后的直播事件；raw 保留原始 command/data 或 protobuf 字段。"""

    kind: str
    room_id: int = 0
    uid: int = 0
    name: str = ""
    text: str = ""
    value: int = 0
    ts: int = 0
    raw: dict[str, Any] = dataclasses.field(default_factory=dict)
    reply_mid: int = 0
    dmid: str = ""


# protobuf 定义 vendor 自 blivedm/models/pb.py
# （MIT，Copyright 2018 xfgryujk）：SEND_GIFT_V2 / INTERACT_WORD_V2。


@dataclasses.dataclass
class InteractWordV2UserBaseInfo(BaseMessage):
    face: Annotated[str, PbField(2)] = ""


@dataclasses.dataclass
class InteractWordV2UserInfo(BaseMessage):
    base: Annotated[InteractWordV2UserBaseInfo, PbField(2)] = dataclasses.field(
        default_factory=InteractWordV2UserBaseInfo
    )


@dataclasses.dataclass
class InteractWordV2(BaseMessage):
    uid: Annotated[int, PbField(1)] = 0
    uname: Annotated[str, PbField(2)] = ""
    msg_type: Annotated[int, PbField(5)] = 0
    timestamp: Annotated[int, PbField(7)] = 0
    uinfo: Annotated[InteractWordV2UserInfo, PbField(22)] = dataclasses.field(default_factory=InteractWordV2UserInfo)


@dataclasses.dataclass
class SendGiftV2MedalInfo(BaseMessage):
    target_id: Annotated[int, PbField(1)] = 0
    anchor_roomid: Annotated[int, PbField(4)] = 0
    medal_level: Annotated[int, PbField(5)] = 0
    medal_name: Annotated[str, PbField(6)] = ""


@dataclasses.dataclass
class SendGiftV2BlindGift(BaseMessage):
    original_gift_name: Annotated[str, PbField(3)] = ""
    original_gift_price: Annotated[int, PbField(6)] = 0


@dataclasses.dataclass
class SendGiftV2GiftMaterialSnapShot(BaseMessage):
    img_basic: Annotated[str, PbField(1)] = ""


@dataclasses.dataclass
class SendGiftV2GiftItem(BaseMessage):
    gift_id: Annotated[int, PbField(1)] = 0
    gift_name: Annotated[str, PbField(2)] = ""
    num: Annotated[int, PbField(3)] = 0
    gift_type: Annotated[int, PbField(4)] = 0
    price: Annotated[int, PbField(5)] = 0
    total_coin: Annotated[int, PbField(7)] = 0
    coin_type: Annotated[str, PbField(8)] = ""
    tid: Annotated[str, PbField(9)] = ""
    timestamp: Annotated[int, PbField(10)] = 0
    rnd: Annotated[str, PbField(12)] = ""
    action: Annotated[str, PbField(18)] = ""
    gift_info: Annotated[SendGiftV2GiftMaterialSnapShot, PbField(35)] = dataclasses.field(
        default_factory=SendGiftV2GiftMaterialSnapShot
    )


@dataclasses.dataclass
class SendGiftBroadcast(BaseMessage):
    uid: Annotated[int, PbField(1)] = 0
    uname: Annotated[str, PbField(2)] = ""
    face: Annotated[str, PbField(3)] = ""
    guard_level: Annotated[int, PbField(5)] = 0
    medal_info: Annotated[SendGiftV2MedalInfo, PbField(8)] = dataclasses.field(default_factory=SendGiftV2MedalInfo)
    blind_gift: Annotated[SendGiftV2BlindGift, PbField(9)] = dataclasses.field(default_factory=SendGiftV2BlindGift)
    gift_list: Annotated[list[SendGiftV2GiftItem], PbField(10)] = dataclasses.field(default_factory=list)


_INTERACT_KINDS = {
    1: "enter",
    2: "follow",
    3: "share",
    4: "follow",
    5: "follow",
    6: "like",
}
_INTERACT_KINDS_SET = frozenset({"enter", "follow", "share", "like", "interact"})


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_seconds(value: Any) -> int:
    """统一成秒；B站弹幕时间戳是毫秒。"""
    ts = _to_int(value)
    return ts // 1000 if ts > 10**12 else ts


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_int(source: dict[str, Any], key: str, default: int = 0) -> int:
    return _to_int(source.get(key, default))


def _get_str(source: dict[str, Any], key: str, default: str = "") -> str:
    value = source.get(key, default)
    return str(value) if value is not None else default


def _command(payload: dict[str, Any]) -> str:
    cmd = payload.get("cmd")
    return cmd.split(":", 1)[0] if isinstance(cmd, str) else ""


def is_mirror(source: Any) -> bool:
    """镜像消息：cmd 带 _MIRROR 后缀，或 data.is_mirror 为真。"""
    if isinstance(source, str):
        return source.endswith("_MIRROR")
    if not isinstance(source, dict):
        return False
    return _command(source).endswith("_MIRROR") or bool(_as_dict(source.get("data")).get("is_mirror"))


def parse_event(payload: Any, room_id: int = 0) -> LiveEvent | None:
    """把一条 op=5 业务消息映射成 LiveEvent；未知 cmd/镜像/结构异常返回 None。"""
    if not isinstance(payload, dict) or is_mirror(payload):
        return None
    cmd = _command(payload)
    if not cmd:
        return None
    data = _as_dict(payload.get("data"))
    if cmd == "DANMU_MSG":
        return _parse_danmaku(payload, room_id)
    if cmd == "SEND_GIFT":
        return _parse_gift(payload, data, room_id)
    if cmd == "SEND_GIFT_V2":
        events = _parse_gift_v2(data, room_id)
        return events[0] if events else None
    if cmd == "GUARD_BUY":
        return _parse_guard_buy(payload, data, room_id)
    if cmd == "USER_TOAST_MSG_V2":
        return _parse_user_toast(payload, data, room_id)
    if cmd == "SUPER_CHAT_MESSAGE":
        return _parse_super_chat(payload, data, room_id)
    if cmd == "SUPER_CHAT_MESSAGE_DELETE":
        return _parse_super_chat_delete(payload, data, room_id)
    if cmd == "INTERACT_WORD_V2":
        return _parse_interact_v2(payload, data, room_id)
    if cmd == "LIVE":
        return LiveEvent("live_start", room_id, text=_get_str(data, "live_time"), raw=payload)
    if cmd == "PREPARING":
        return LiveEvent("live_end", room_id, raw=payload)
    if cmd == "WATCHED_CHANGE":
        return LiveEvent(
            "watched_change",
            room_id,
            text=_get_str(data, "text_small"),
            value=_get_int(data, "num"),
            raw=payload,
        )
    if cmd == "ENTRY_EFFECT":
        return _parse_entry_effect(payload, data, room_id)
    return None


def parse_events(payload: Any, room_id: int = 0) -> list[LiveEvent]:
    """把一条业务消息展开成事件列表（SEND_GIFT_V2 一条可含多件礼物）。"""
    if not isinstance(payload, dict) or is_mirror(payload):
        return []
    if _command(payload) == "SEND_GIFT_V2":
        return _parse_gift_v2(_as_dict(payload.get("data")), room_id)
    event = parse_event(payload, room_id)
    return [event] if event is not None else []


def parse_danmu_message(payload: Any) -> dict[str, Any] | None:
    """兼容旧接口：只取 DANMU_MSG 的 uid/name/text。"""
    if not isinstance(payload, dict) or _command(payload) != "DANMU_MSG" or is_mirror(payload):
        return None
    event = parse_event(payload)
    if event is None or event.kind != "danmaku":
        return None
    return {"uid": event.uid, "name": event.name, "text": event.text}


def event_key(event: LiveEvent) -> str:
    """可去重事件的稳定键；返回空串表示该事件不去重。"""
    raw = event.raw if isinstance(event.raw, dict) else {}
    data = _as_dict(raw.get("data")) or raw
    if event.kind == "gift":
        gift = _as_dict(data.get("gift")) or data
        token = _get_str(gift, "tid") or _get_str(gift, "rnd")
        return f"gift:{event.room_id}:{event.uid}:{token}" if token else ""
    if event.kind == "super_chat":
        sid = _get_int(data, "id")
        return f"sc:{event.room_id}:{sid}" if sid else ""
    if event.kind == "super_chat_delete":
        ids = data.get("ids")
        if not isinstance(ids, list) or not ids:
            return ""
        return f"sc-delete:{event.room_id}:{','.join(str(_to_int(item)) for item in ids)}"
    if event.kind == "guard":
        guard = _as_dict(data.get("guard_info")) or data
        start = _get_int(guard, "start_time")
        if not start:
            return ""
        return f"guard:{event.room_id}:{event.uid}:{_get_int(guard, 'guard_level')}:{start}"
    if event.kind in _INTERACT_KINDS_SET:
        return f"{event.kind}:{event.room_id}:{event.uid}:{event.ts}:{_get_int(data, 'msg_type')}"
    return ""


def _parse_danmaku(payload: dict[str, Any], room_id: int) -> LiveEvent | None:
    info = payload.get("info")
    try:
        text = str(info[1]).strip()  # type: ignore[index]
        uid = int(info[2][0])  # type: ignore[index]
        name = str(info[2][1])  # type: ignore[index]
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    if not text:
        return None
    try:
        ts = _to_seconds(info[0][4])  # type: ignore[index]
    except (IndexError, KeyError, TypeError, ValueError):
        ts = 0
    reply_mid = 0
    dmid = ""
    try:
        extra = json.loads((info[0][15] or {}).get("extra") or "{}")  # type: ignore[index]
        reply_mid = _to_int(extra.get("reply_mid"))
        dmid = str(extra.get("id_str") or "")
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    return LiveEvent(
        "danmaku", room_id, uid, name, text, 0, ts, payload,
        reply_mid=reply_mid, dmid=dmid,
    )


def _parse_gift(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    if not data:
        return None
    return LiveEvent(
        "gift",
        room_id,
        _get_int(data, "uid"),
        _get_str(data, "uname"),
        _get_str(data, "giftName") or _get_str(data, "gift_name"),
        _get_int(data, "total_coin"),
        _to_seconds(data.get("timestamp")),
        payload,
    )


def _load_proto(cls: Any, data: dict[str, Any]) -> Any | None:
    pb = data.get("pb")
    if not isinstance(pb, str) or not pb:
        return None
    try:
        return cls.loads(base64.b64decode(pb))
    except Exception:
        return None


def _parse_gift_v2(data: dict[str, Any], room_id: int) -> list[LiveEvent]:
    proto = _load_proto(SendGiftBroadcast, data)
    if proto is None:
        return []
    base = dataclasses.asdict(proto)
    gifts = base.pop("gift_list", [])
    events: list[LiveEvent] = []
    for gift in gifts:
        if not isinstance(gift, dict):
            continue
        events.append(
            LiveEvent(
                "gift",
                room_id,
                _to_int(proto.uid),
                str(proto.uname or ""),
                str(gift.get("gift_name") or ""),
                _to_int(gift.get("total_coin")),
                _to_seconds(gift.get("timestamp")),
                {**base, "gift": gift},
            )
        )
    return events


def _parse_guard_buy(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    if not data:
        return None
    return LiveEvent(
        "guard",
        room_id,
        _get_int(data, "uid"),
        _get_str(data, "username"),
        _get_str(data, "gift_name"),
        _get_int(data, "price"),
        _to_seconds(data.get("start_time")),
        payload,
    )


def _parse_user_toast(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    if not data:
        return None
    sender = _as_dict(data.get("sender_uinfo"))
    guard = _as_dict(data.get("guard_info"))
    pay = _as_dict(data.get("pay_info"))
    return LiveEvent(
        "guard",
        room_id,
        _get_int(sender, "uid") or _get_int(data, "uid"),
        _get_str(_as_dict(sender.get("base")), "name") or _get_str(data, "username"),
        _get_str(data, "toast_msg"),
        _get_int(pay, "price"),
        _to_seconds(guard.get("start_time")),
        payload,
    )


def _parse_super_chat(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    if not data:
        return None
    user = _as_dict(data.get("user_info"))
    return LiveEvent(
        "super_chat",
        room_id,
        _get_int(data, "uid"),
        _get_str(user, "uname"),
        _get_str(data, "message"),
        _get_int(data, "price"),
        _to_seconds(data.get("start_time")),
        payload,
    )


def _parse_super_chat_delete(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        return None
    values = [_to_int(item) for item in ids]
    return LiveEvent(
        "super_chat_delete", room_id, text=",".join(str(item) for item in values), value=values[0], raw=payload
    )


def _parse_interact_v2(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    proto = _load_proto(InteractWordV2, data)
    if proto is None:
        return None
    kind = _INTERACT_KINDS.get(proto.msg_type, "interact")
    return LiveEvent(
        kind,
        room_id,
        _to_int(proto.uid),
        str(proto.uname or ""),
        "",
        0,
        _to_seconds(proto.timestamp),
        dataclasses.asdict(proto),
    )


def _parse_entry_effect(payload: dict[str, Any], data: dict[str, Any], room_id: int) -> LiveEvent | None:
    if not data:
        return None
    base = _as_dict(_as_dict(data.get("uinfo")).get("base"))
    return LiveEvent(
        "entry_effect",
        room_id,
        _get_int(data, "uid"),
        _get_str(base, "name"),
        _get_str(data, "copy_writing"),
        0,
        0,
        payload,
    )
