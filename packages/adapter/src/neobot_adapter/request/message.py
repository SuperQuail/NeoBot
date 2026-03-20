"""消息相关 API"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from neobot_adapter.model import response
from neobot_adapter.receiver.core import AdapterCore
from neobot_adapter.request._proxy import core_proxy as core
from neobot_adapter.utils.parse import safe_parse_model


async def send_custom_private_msg(
    user_id: int,
    type: List[str],
    data: dict[str, Any],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送自定义私聊消息"""
    param = {"user_id": user_id, "message": {"type": type, "data": data}}
    result = await core.call_api("send_private_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_custom_group_msg(
    group_id: int,
    type: List[str],
    data: dict[str, Any],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送自定义群聊消息"""
    param = {"user_id": group_id, "message": {"type": type, "data": data}}
    result = await core.call_api("send_group_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_private_msg(
    user_id: int,
    message: str,
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送私聊消息"""
    param = {"user_id": user_id, "message": {"type": "text", "data": {"text": message}}}
    result = await core.call_api("send_private_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_private_replay_msg(
    user_id: int,
    message: str,
    replay_id: Optional[int],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送私聊回复消息"""
    msg = [
        {"type": "reply", "data": {"id": str(replay_id)}},
        {"type": "text", "data": {"text": message}},
    ]
    param = {"user_id": user_id, "message": msg}
    result = await core.call_api("send_private_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_group_msg(
    group_id: int,
    message: str,
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送群聊消息"""
    param = {"group_id": group_id, "message": {"type": "text", "data": {"text": message}}}
    result = await core.call_api("send_group_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_group_replay_msg(
    group_id: int,
    message: str,
    replay_id: Optional[int],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送群聊回复消息"""
    msg = [
        {"type": "reply", "data": {"id": str(replay_id)}},
        {"type": "text", "data": {"text": message}},
    ]
    param = {"group_id": group_id, "message": msg}
    result = await core.call_api("send_group_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_group_forward_msg(
    group_id: int,
    messages: List[Dict[str, Any]],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送群聊合并转发消息"""
    param = {"group_id": group_id, "messages": messages}
    result = await core.call_api("send_group_forward_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def send_private_forward_msg(
    user_id: int,
    messages: List[Dict[str, Any]],
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送私聊合并转发消息"""
    param = {"user_id": user_id, "messages": messages}
    result = await core.call_api("send_private_forward_msg", param, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def delete_msg(
    message_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """撤回消息"""
    result = await core.call_api("delete_msg", {"message_id": message_id}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def get_msg(
    message_id: int,
    timeout: float = 5,
) -> response.GetSignalMsgResponse:
    """获取消息"""
    result = await core.call_api("get_msg", {"message_id": message_id}, timeout)
    return safe_parse_model(result, response.GetSignalMsgResponse)


async def get_friend_msg_history(
    user_id: int,
    message_seq: int = 0,
    count: int = 20,
    reverse_order: bool = False,
    timeout: float = 5,
) -> response.GetHistoryMsgListResponse:
    """获取好友历史消息"""
    params = {
        "user_id": user_id,
        "message_seq": message_seq,
        "count": count,
        "reverseOrder": reverse_order,
    }
    result = await core.call_api("get_friend_msg_history", params, timeout)
    return safe_parse_model(result, response.GetHistoryMsgListResponse)


async def get_group_msg_history(
    group_id: int,
    message_seq: int = 0,
    count: int = 20,
    reverse_order: bool = False,
    timeout: float = 5,
) -> response.GetHistoryMsgListResponse:
    """获取群历史消息"""
    params = {
        "group_id": group_id,
        "message_seq": message_seq,
        "count": count,
        "reverseOrder": reverse_order,
    }
    result = await core.call_api("get_group_msg_history", params, timeout)
    return safe_parse_model(result, response.GetHistoryMsgListResponse)


async def mark_msg_as_read(
    message_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """标记消息已读"""
    result = await core.call_api("mark_msg_as_read", {"message_id": message_id}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def mark_group_msg_as_read(
    group_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """标记群消息已读"""
    result = await core.call_api("mark_group_msg_as_read", {"group_id": group_id}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def mark_private_msg_as_read(
    user_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """标记私聊消息已读"""
    result = await core.call_api("mark_private_msg_as_read", {"user_id": user_id}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def mark_all_as_read(
    timeout: float = 5,
) -> response.BaseResponse:
    """标记所有消息已读"""
    result = await core.call_api("_mark_all_as_read", {}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def get_image(
    file: str,
    timeout: float = 5,
) -> response.BaseResponse:
    """获取图片"""
    result = await core.call_api("get_image", {"file": file}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def get_record(
    file: str,
    out_format: str = "mp3",
    timeout: float = 5,
) -> response.BaseResponse:
    """获取语音"""
    result = await core.call_api("get_record", {"file": file, "out_format": out_format}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def can_send_image(
    timeout: float = 5,
) -> response.BaseResponse:
    """检查是否可以发送图片"""
    result = await core.call_api("can_send_image", {}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def can_send_record(
    timeout: float = 5,
) -> response.BaseResponse:
    """检查是否可以发送语音"""
    result = await core.call_api("can_send_record", {}, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def set_msg_emoji_like(
    message_id: int,
    emoji_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """设置消息表情回应"""
    params = {"message_id": message_id, "emoji_id": emoji_id}
    result = await core.call_api("set_msg_emoji_like", params, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def get_emoji_like(
    message_id: int,
    emoji_id: int,
    emoji_type: Optional[str] = None,
    count: Optional[int] = None,
    timeout: float = 5,
) -> response.GetEmojiLikeResponse:
    """获取消息表情回应"""
    params: Dict[str, Any] = {"message_id": message_id, "emojiId": emoji_id}
    if emoji_type is not None:
        params["emojiType"] = emoji_type
    if count is not None:
        params["count"] = count
    result = await core.call_api("fetch_emoji_like", params, timeout)
    return safe_parse_model(result, response.GetEmojiLikeResponse)


async def forward_friend_single_msg(
    message_id: int,
    user_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """转发单条消息给好友"""
    params = {"message_id": message_id, "user_id": user_id}
    result = await core.call_api("forward_friend_single_msg", params, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def forward_group_single_msg(
    message_id: int,
    group_id: int,
    timeout: float = 5,
) -> response.BaseResponse:
    """转发单条消息到群"""
    params = {"message_id": message_id, "group_id": group_id}
    result = await core.call_api("forward_group_single_msg", params, timeout)
    return safe_parse_model(result, response.BaseResponse)


async def send_group_ai_record(
    character: str,
    group_id: int,
    text: str,
    chat_type: int = 1,
    timeout: float = 5,
) -> response.SendMsgResponse:
    """发送群AI语音"""
    params = {
        "character": character,
        "group_id": group_id,
        "text": text,
        "chat_type": chat_type,
    }
    result = await core.call_api("send_group_ai_record", params, timeout)
    return safe_parse_model(result, response.SendMsgResponse)


async def get_ai_characters(
    group_id: int,
    chat_type: int = 1,
    timeout: float = 5,
) -> response.GetAIVoiceResponse:
    """获取群AI语音角色"""
    params = {"group_id": group_id, "chat_type": chat_type}
    result = await core.call_api("get_ai_characters", params, timeout)
    return safe_parse_model(result, response.GetAIVoiceResponse)
