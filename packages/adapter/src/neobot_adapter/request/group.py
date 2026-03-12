from neobot_adapter.model.response import BaseResponse
from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional, Dict, Any, List
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.group')

async def get_group_list(no_cache : Optional[bool] = False,timeout=5) -> response.GetGroupListResponse:
    """
    获取群列表
    :param no_cache:
    :param timeout:
    :return:
    """
    action = "get_group_list"
    params = {
        "no_cache": no_cache
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupListResponse)
    return result

async def get_group_info(group_id : int , timeout=5) -> response.GetGroupInfoResponse:
    """
    获取群信息
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_info"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupInfoResponse)
    return result

async def get_group_member_list(group_id : int, no_cache : Optional[bool] = False,timeout=5) -> response.GetGroupListResponse :
    """
    获取群成员列表
    :param group_id:
    :param no_cache:
    :param timeout:
    :return:
    """
    action = "get_group_member_list"
    params = {
        "group_id": group_id,
        "no_cache": no_cache
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupListResponse)
    return result

async def get_group_member_info(group_id : int, user_id : int, no_cache : Optional[bool] = False,timeout=5) -> response.GetGroupMemberInfoResponse:
    """
    获取群成员信息
    :param group_id:
    :param user_id:
    :param no_cache:
    :param timeout:
    :return:
    """
    action = "get_group_member_info"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "no_cache": no_cache
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupMemberInfoResponse)
    return result

async def group_poke(group_id : int, user_id : int, timeout=5) -> response.BaseResponse:
    """
    发送群戳一戳
    :param group_id:
    :param user_id:
    :param timeout:
    :return:
    """
    action = "group_poke"
    params = {
        "group_id": group_id,
        "user_id": user_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_system_msg(timeout=5) -> response.GetGroupSystemMsgResponse:
    """
    获取群系统消息
    :param timeout:
    :return:
    """
    action = "get_group_system_msg"
    params = {}
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupSystemMsgResponse)
    return result

async def set_group_add_request(flag : str , approve : Optional[bool] = True, reason : Optional[str] = None, timeout=5) -> response.NullDataResponse:
    """
    处理加群请求
    :param flag:
    :param approve:
    :param reason:
    :param timeout:
    :return:
    """
    action = "set_group_add_request"
    params = {
        "flag": flag,
        "approve": approve,
        "reason": reason
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.NullDataResponse)
    return result

async def set_group_leave(group_id : int , timeout=5) -> response.BaseResponse :
    """
    退出群
    :param group_id:
    :param timeout:
    :return:
    """
    action = "set_group_leave"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_admin(group_id : int , user_id : int , enable : bool , timeout=5) -> response.BaseResponse:
    """
    设置群管理员
    :param group_id:
    :param user_id:
    :param enable:
    :param timeout:
    :return:
    """
    action = "set_group_admin"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "enable": enable
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_card(group_id : int , user_id : int , card : str , timeout=5) -> response.BaseResponse:
    """
    设置群名片
    :param group_id:
    :param user_id:
    :param card:
    :param timeout:
    :return:
    """
    action = "set_group_card"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "card": card
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_ban(group_id : int , user_id : int , duration : int , timeout=5) -> response.BaseResponse:
    """
    设置群禁言
    :param group_id:
    :param user_id:
    :param duration:
    :param timeout:
    :return:
    """
    action = "set_group_ban"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "duration": duration
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_whole_ban(group_id : int , enable : bool = True , timeout=5) -> response.BaseResponse:
    """
    设置群全员禁言
    :param group_id:
    :param enable:
    :param timeout:
    :return:
    """
    action = "set_group_whole_ban"
    params = {
        "group_id": group_id,
        "enable": enable
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_shut_list(group_id : int , timeout=5) -> response.BaseResponse :
    """
    获取群禁言列表
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_shut_list"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_name(group_id : int , group_name : str , timeout=5) -> response.BaseResponse:
    """
    设置群名称
    :param group_id:
    :param group_name:
    :param timeout:
    :return:
    """
    action = "set_group_name"
    params = {
        "group_id": group_id,
        "group_name": group_name
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def batch_delete_group_member(group_id : int , user_id_list : List[int] , timeout=5) -> response.NullDataResponse:
    """
    批量删除群成员
    :param group_id:
    :param user_id_list:
    :param timeout:
    :return:
    """
    action = "batch_delete_group_member"
    params = {
        "group_id": group_id,
        "user_id_list": user_id_list
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.NullDataResponse)
    return result

async def set_group_kick(group_id : int , user_id : int , reject_add_request : bool = False , timeout=5) -> response.BaseResponse:
    """
    设置群成员移出群聊
    :param group_id:
    :param user_id:
    :param reject_add_request:
    :param timeout:
    :return:
    """
    action = "set_group_kick"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "reject_add_request": reject_add_request
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_special_title(group_id : int , user_id : int , special_title : str , timeout=5) -> response.BaseResponse:
    """
    设置群成员特殊头衔
    :param group_id:
    :param user_id:
    :param special_title:
    :param timeout:
    :return:
    """
    action = "set_group_special_title"
    params = {
        "group_id": group_id,
        "user_id": user_id,
        "special_title": special_title
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_honor_info(group_id : int , type : str , timeout=5) -> response.GetGroupHonorInfoResponse:
    """
    获取群成员荣誉信息
    :param group_id:
    :param type: 可传入 talkative、performer、legend、strong_newbie、emotion 以分别获取单个类型的群荣誉数据, 或传入 all 获取所有数据
    :param timeout:
    :return:
    """
    action = "get_group_honor_info"
    params = {
        "group_id": group_id,
        "type": type
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupHonorInfoResponse)
    return result

async def get_essence_msg_list(group_id : int , timeout=5) -> response.GetEssenceMsgListResponse:
    """
    获取群精华消息列表
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_essence_msg_list"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetEssenceMsgListResponse)
    return result

async def set_essence_msg(message_id : int , timeout=5) -> response.BaseResponse:
    """
    设置群精华消息
    :param message_id:
    :param timeout:
    :return:
    """
    action = "set_essence_msg"
    params = {
        "message_id": message_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def delete_essence_msg(message_id : int , timeout=5) -> response.BaseResponse:
    """
    取消群精华消息
    :param message_id:
    :param timeout:
    :return:
    """
    action = "delete_essence_msg"
    params = {
        "message_id": message_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def _send_group_notice(
        group_id : int ,
        content : str ,
        image : Optional[str] = "" ,
        pinned : Optional[bool] = False,
        confirm_required : Optional[bool] = False,
        timeout=5) -> response.BaseResponse:
    action = "_send_group_notice"
    params = {
        "group_id": group_id,
        "content": content,
        "image": image,
        "pinned": pinned,
        "confirm_required": confirm_required
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def _get_group_notice(group_id : int , timeout=5) -> response.GetGroupNoticeResponse:
    """
    获取群公告
    :param group_id:
    :param timeout:
    :return:
    """
    action = "_get_group_notice"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupNoticeResponse)
    return result

async def send_group_sign(group_id : int , timeout=5) -> response.BaseResponse:
    """
    群打卡
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_sign"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_msg_mask(group_id : int , mask : int , timeout=5) -> response.BaseResponse:
    """
    设置群消息屏蔽
    :param group_id:
    :param mask: #1 接收并提醒，2 收进群助手，3 屏蔽，4 接收不提醒
    :param timeout:
    :return:
    """
    action = "set_group_msg_mask"
    params = {
        "group_id": group_id,
        "mask": mask
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_group_remark(group_id : int , remark : str , timeout=5) -> response.BaseResponse:
    """
    设置群备注
    :param group_id:
    :param remark:
    :param timeout:
    :return:
    """
    action = "set_group_remark"
    params = {
        "group_id": group_id,
        "remark": remark
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_ignore_add_request(group_id : int , timeout=5) -> response.BaseResponse:
    """
    获取群加群请求
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_ignore_add_request"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def upload_group_album(group_id : int ,album_id : str, image : str , timeout=5) -> response.GetUploadGroupAlbumResponse:
    """
    上传群相册图片
    :param group_id:
    :param album_id:
    :param image:
    :param timeout:
    :return:
    """
    action = "upload_group_album"
    params = {
        "group_id": group_id,
        "album_id": album_id,
        "image": image
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetUploadGroupAlbumResponse)
    return result

async def get_group_album_list(group_id : int , timeout=5) -> response.GetGroupAlbumResponse:
    """
    获取群相册列表
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_album_list"
    params = {
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetGroupAlbumResponse)
    return result

async def create_group_album(group_id : int , name : str , timeout=5) -> response.CreateGroupAlbumResponse:
    """
    创建群相册
    :param group_id:
    :param name:
    :param timeout:
    :return:
    """
    action = "create_group_album"
    params = {
        "group_id": group_id,
        "name": name
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.CreateGroupAlbumResponse)
    return result

async def delete_group_album(group_id : int , album_id : str , timeout=5) -> response.BaseResponse:
    """
    删除群相册
    :param group_id:
    :param album_id:
    :param timeout:
    :return:
    """
    action = "delete_group_album"
    params = {
        "group_id": group_id,
        "album_id": album_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def _delete_group_notice(group_id : int , notice_id : str , timeout=5) -> response.BaseResponse:
    """
    删除群公告
    :param group_id:
    :param notice_id:
    :param timeout:
    :return:
    """
    action = "_delete_group_notice"
    params = {
        "group_id": group_id,
        "notice_id": notice_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result






