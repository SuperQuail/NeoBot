from neobot_adapter.model.response import BaseResponse
from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional, Dict, Any, List
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.message')

async def send_custom_private_msg(user_id: int,type : List[str], data: dict[str, Any], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param data:
    :param type:
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : type,
            "data" : data
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_custom_group_msg(group_id: int,type : List[str], data: dict[str, Any], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param data:
    :param type:
    :param timeout:
    :param group_id:
    :return:
    """
    action = "send_group_msg"
    param = {
        "user_id": group_id,
        "message": {
            "type" : type,
            "data" : data
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_msg(user_id: int, message: str, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param timeout:
    :param user_id:
    :param message:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "text",
            "data" : {
                "text": message
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_replay_msg(user_id: int, message: str, replay_id: Optional[int], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param replay_id:
    :param timeout:
    :param user_id:
    :param message:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "reply",
            "data" : {
                "id" : replay_id,
                "text": message
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result


async def send_private_image_msg(user_id: int,  file: Optional[str],summary: Optional[str] = None, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param summary:
    :param file:
    :param replay_id:
    :param timeout:
    :param user_id:
    :param message:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "image",
            "data" : {
                "file" : file,
                "summary": summary
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_text_with_image_msg(user_id: int,message : str,  file: Optional[str], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param file:
    :param timeout:
    :param user_id:
    :param message:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : ["text","image"],
            "data" : {
                "file" : file,
                "text": message
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_face_msg(user_id: int,id : int, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param id:
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "face",
            "data" : {
                "id" : id
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_record_msg(user_id: int,record : str, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param record:
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "record",
            "data" : {
                "file" : record
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_video_msg(user_id: int,video : str, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param video: 视频不能超过100M
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "video",
            "data" : {
                "file" : video
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_dice_msg(user_id: int,result : Optional[int] = -1, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊消息
    :param result: 只有拉格朗日支持,骰子点数
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    if result == -1:
        param = {
            "user_id": user_id,
            "message": {
                "type": "dice"
            }
        }
    else:
        param = {
            "user_id": user_id,
            "message": {
                "type" : "dice",
                "data" : {
                    "result" : result
                }
            }
        }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_rps_msg(user_id: int, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊猜拳消息
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "rps"
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_music_msg(user_id: int,music_type : str, music_id : int, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊猜拳消息
    :param music_id:
    :param music_type: 枚举值:"qq","163"(网易云),
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "music",
            "data" : {
                "type" : music_type,
                "id" : music_id
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_custom_music_msg(user_id: int,music_url : str, music : str,title : str,image : str, timeout=5) -> response.SendMsgResponse :
    """
    发送私聊猜拳消息
    :param image:
    :param title:
    :param music:
    :param music_url:
    :param timeout:
    :param user_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "user_id": user_id,
        "message": {
            "type" : "music",
            "data" : {
                "type" : "custom",
                "url" : music_url,
                "audio" : music,
                "title" : title,
                "image" : image,
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_private_forward_msg(user_id: int,messages : List[Dict[str,Any]], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊合并转发消息 TODO:暂时不支持
    :param messages:
    :param timeout:
    :param user_id:
    :return:
    """
    pass

async def send_group_msg(group_id: int,message : str, timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param group_id:
    :param message:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"text",
            "data":{
                "text":message
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result


async def send_group_replay_msg(group_id: int,message : str,replay_id : int, timeout=5) -> response.SendMsgResponse:
    """
    发送群回复消息
    :param replay_id:
    :param group_id:
    :param message:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"replay",
            "data":{
                "id":replay_id,
                "text":message
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_at_msg(group_id: int,qq : str, timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param qq: all表示@全体
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"at",
            "data":{
                "qq":qq
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_custom_at_msg(group_id: int,message : List[Dict[str,Any]], timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param message:
    "message": [
        {
            "type": "at",
            "data": {
                "qq": "1263753202"  // all 表示@全体
            }
        },
        {
            "type": "text",
            "data": {
                "text": "@你了"
            }
        }
    ]
    :param group_id:
    :param timeout:

    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": message
        }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result


async def send_group_image_msg(group_id: int,image :str,summary : str, timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param summary:
    :param image:
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"image",
            "data":{
                "file":image,
                "summary":summary
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_text_image_msg(group_id: int,message : List[Dict[str,Any]], timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param message:
    "message": [
    {
      "type": "text",
      "data": {
        "text": "HelloKitty"
      }
    },
    {
      "type": "image",
      "data": {
        "file": ""
      }
    }
  ]
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":["text","image"],
            "data":message
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_face_msg(group_id: int,id : int, timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param id:
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"face",
            "data":{
                "id":id
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_record_msg(group_id: int,file : str, timeout=5) -> response.SendMsgResponse:
    """
    发送群消息
    :param file:
    :param group_id:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"record",
            "data":{
                "file":file
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_video_msg(group_id: int,file : str,replay_id : int, timeout=5) -> response.SendMsgResponse:
    """
    发送群回复消息
    :param replay_id:
    :param group_id:
    :param file:
    :param timeout:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type":"video",
            "data":{
                "file":file
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_dice_msg(group_id: int,result : Optional[int] = -1, timeout=5) -> response.SendMsgResponse :
    """
    发送群聊骰子消息
    :param result: 只有拉格朗日支持,骰子点数
    :param timeout:
    :param group_id:
    :return:
    """
    action = "send_group_msg"
    if result == -1:
        param = {
            "group_id": group_id,
            "message": {
                "type": "dice"
            }
        }
    else:
        param = {
            "group_id": group_id,
            "message": {
                "type" : "dice",
                "data" : {
                    "result" : result
                }
            }
        }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_rps_msg(group_id: int, timeout=5) -> response.SendMsgResponse :
    """
    发送群聊猜拳消息
    :param timeout:
    :param group_id:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type" : "rps"
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_music_msg(group_id: int,music_type : str, music_id : int, timeout=5) -> response.SendMsgResponse :
    """
    发送群聊音乐消息
    :param music_id:
    :param music_type: 枚举值:"qq","163"(网易云),
    :param timeout:
    :param group_id:
    :return:
    """
    action = "send_group_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type" : "music",
            "data" : {
                "type" : music_type,
                "id" : music_id
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_custom_music_msg(group_id: int,music_url : str, music : str,title : str,image : str, timeout=5) -> response.SendMsgResponse :
    """
    发送群聊自定义音乐消息
    :param image:
    :param title:
    :param music:
    :param music_url:
    :param timeout:
    :param group_id:
    :return:
    """
    action = "send_private_msg"
    param = {
        "group_id": group_id,
        "message": {
            "type" : "music",
            "data" : {
                "type" : "custom",
                "url" : music_url,
                "audio" : music,
                "title" : title,
                "image" : image,
            }
        }
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def send_group_forward_msg(group_id: int,messages : List[Dict[str,Any]], timeout=5) -> response.SendMsgResponse :
    """
    发送私聊合并转发消息 TODO:暂时不支持
    :param messages:
    :param timeout:
    :param group_id:
    :return:
    """
    pass

async def _events(timeout=5) -> response.SendMsgResponse:
    """
    长连接(HTTP SEE)获取消息,用途未知
    :param timeout:
    :return:
    """
    result = await core.call_api("_events", {}, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def forward_friend_single_msg(message_id: int,user_id: int,timeout=5) -> response.SendMsgResponse:
    """
    发送好友转发消息
    :param message_id:
    :param user_id:
    :param timeout:
    :return:
    """
    action = "forward_friend_single_msg"
    param = {
        "message_id": message_id,
        "user_id": user_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def forward_group_single_msg(message_id: int,group_id: int,timeout=5) -> response.SendMsgResponse:
    """
    发送好友转发消息
    :param message_id:
    :param group_id:
    :param timeout:
    :return:
    """
    action = "forward_group_single_msg"
    param = {
        "message_id": message_id,
        "user_id": group_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def get_message(message_id: int,timeout=5) -> response.GetSignalMsgResponse:
    """
    获取消息
    :param message_id:
    :param timeout:
    :return:
    """
    action = "get_message"
    param = {
        "message_id": message_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetSignalMsgResponse)
    return result

async def delete_msg(message_id: int,timeout=5) -> response.BaseResponse:
    """
    撤回消息
    :param message_id:
    :param timeout:
    :return:
    """
    action = "delete_msg"
    param = {
        "message_id": message_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result







