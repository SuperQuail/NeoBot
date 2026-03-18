from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional,Dict,Any
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.private')

async def send_like(user_id: int, times: int, timeout=5) -> response.SendLikeResponse:
    """
    点赞
    
    Args:
        user_id: 目标 qq 号
        times: 点赞次数
        timeout: 超时时间（秒）
        
    Returns:
        API 响应字典，包含 status、retcode、data 等字段。如果调用失败返回 None。
    """
    action = "send_like"
    params = {
        "user_id": user_id,
        "times": times
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.SendLikeResponse)
    return result


async def get_friend_list(timeout=5):
    """
    获取好友列表

    :param timeout:
    :return:
    """
    action = "get_friend_list"
    params = {}
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.GetFriendListResponse)
    return result

async def get_friends_with_category(timeout=5) -> response.CategoryFriendResponse :
    """
    获取好友列表，带分类

    :param timeout:
    :return:
    """
    action = "get_friends_with_category"
    params = {}
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.CategoryFriendResponse)
    return result


async def delete_friend(user_id: int, timeout=5) -> response.BaseResponse:
    """
    删除好友

    :param user_id:
    :param timeout:
    :return:
    """
    action = "delete_friend"
    params = {
        "user_id": user_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_friend_add_request(flag: str, approve: bool, remark: Optional[str] = None, timeout=5) -> response.BaseResponse:
    """
    处理加好友请求

    :param flag:
    :param approve:
    :param remark:
    :param timeout:
    :return:
    """
    action = "set_friend_add_request"
    params = {
        "flag": flag,
        "approve": approve,
        "remark": remark
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_friend_remark(user_id: int, remark: Optional[str], timeout=5) -> response.BaseResponse:
    """
    设置好友备注

    :param user_id:
    :param remark:
    :param timeout:
    :return:
    """
    action = "set_friend_remark"
    params = {
        "user_id": user_id,
        "remark": remark
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_stranger_info(user_id: int, timeout=5) -> response.StrangerInfoResponse:
    """
    获取陌生人信息

    :param user_id:
    :param timeout:
    :return:
    """
    action = "get_stranger_info"
    params = {
        "user_id": user_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.StrangerInfoResponse)
    return result

async def set_qq_avatar(file: str, timeout=5) -> response.BaseResponse:
    """
    设置 QQ 头像
    支持三种形式:
    file://d:/1.png
    http://baidu.com/xxxx/1.png
    base64://xxxxxxxx
    :param file:
    :param timeout:
    :return:
    """
    action = "set_qq_avatar"
    params = {
        "file": file
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async  def friend_poke(user_id: int, timeout=5) -> response.BaseResponse:
    """
    发送好友戳一戳

    :param user_id:
    :param timeout:
    :return:
    """
    action = "friend_poke"
    params = {
        "user_id": user_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_profile_like(start : int = 0, count : int = 20, timeout=5) -> response.ProfileLikeResponse:
    """
    获取群成员资料
    :param start: -1表示获取全部,此时非好友nick可能为空
    :param count: 一页的数量,最多30
    :param timeout:
    :return:
    """
    action = "get_profile_like"
    params = {
        "start": start,
        "count": count
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.ProfileLikeResponse)
    return result

async def get_profile_like_me(start : int = 0, count : int = 20, timeout=5) -> response.ProfileLikeMeResponse:
    """
    获取我收到的群资料
    :param start: -1表示获取全部,此时非好友nick可能为空
    :param count: 一页的数量,最多30
    :param timeout:
    """
    action = "get_profile_like_me"
    params = {
        "start": start,
        "count": count
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.ProfileLikeMeResponse)
    return result

async def get_robot_uin_range(timeout=5) -> response.RobotUinRangeResponse :
    """
    获取机器人QQ号范围
    :param timeout:
    :return:
    """
    action = "get_robot_uin_range"
    params = {}
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.RobotUinRangeResponse)
    return result

async def set_friend_category(user_id: int, category_id: int, timeout=5) -> response.BaseResponse:
    """
    设置好友分组
    :param user_id:
    :param category_id:
    :param timeout:
    :return:
    """
    action = "set_friend_category"
    params = {
        "user_id": user_id,
        "category_id": category_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_qq_avatar(user_id: Optional[int] , group_id: Optional[int] , timeout=5) -> response.QQAvatarResponse :
    """
    获取QQ头像
    :param user_id:
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_qq_avatar"
    params = {
        "user_id": user_id,
        "group_id": group_id
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.QQAvatarResponse)
    return result

async def get_doubt_friends_add_request(count: int = 50, timeout=5) -> response.BaseResponse:
    """
    获取被过滤的好友请求
    :param count:
    :param timeout:
    :return:
    """
    action = "get_doubt_friends_add_request"
    params = {
        "count": count
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def set_doubt_friends_add_request(flag: str, timeout=5) -> response.SetDoubtFriendsAddRequest:
    """
    处理被过滤的好友请求
    :param flag:
    :param timeout:
    :return:
    """
    action = "set_doubt_friends_add_request"
    params = {
        "flag": flag
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.SetDoubtFriendsAddRequest)
    return result

async def set_qq_profile(nickname : Optional[ str],personal_note : Optional[ str], timeout=5) -> response.SetQQProfileResponse:
    """
    设置QQ昵称和个性签名
    :param nickname:
    :param personal_note:
    :param timeout:
    :return:
    """
    action = "set_qq_profile"
    params = {
        "nickname": nickname,
        "personal_note": personal_note
    }
    result = await core.call_api(action, params, timeout)
    result = safe_parse_model(result, response.SetQQProfileResponse)
    return result


