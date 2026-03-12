from neobot_adapter.model.response import BaseResponse
from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional, Dict, Any, List
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.file')

async def get_file(file : str , download : bool = True , timeout=5) -> response.GetMessageFileResponse:
    """
    获取文件
    :param file:
    :param download:
    :param timeout:
    :return:
    """
    action = "get_file"
    param = {
        "file": file,
        "download": download
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetMessageFileResponse)
    return result

async def get_image(file : str , timeout=5) -> response.GetMessageFileResponse:
    """
    获取图片
    :param file:
    :param timeout:
    :return:
    """
    action = "get_image"
    param = {
        "file": file
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetMessageFileResponse)
    return result

async def get_record(file : str ,out_format : str = "mp3", timeout=5) -> response.GetRecordResponse:
    """
    获取语音
    :param file:
    :param out_format
    :param timeout:
    :return:
    """
    action = "get_record"
    param = {
        "file": file,
        "out_format": out_format
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetRecordResponse)
    return result

async def set_msg_emoji_like(message_id: int,emoji_id : int, timeout=5) -> response.BaseResponse:
    """
    设置消息emoji回复
    :param message_id:
    :param emoji_id: 12951 是祝
    :param timeout:
    :return:
    """
    action = "set_msg_emoji_like"
    param = {
        "message_id": message_id,
        "emoji_id": emoji_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def unset_msg_emoji_like(message_id: int,emoji_id : int,timeout=5) -> response.BaseResponse:
    """
    取消消息emoji回复
    :param message_id:
    :param timeout:
    :param emoji_id
    :return:
    """
    action = "unset_msg_emoji_like"
    param = {
        "message_id": message_id,
        "emoji_id": emoji_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_friend_msg_history(user_id : int, message_seq : Optional[int] = 0,count : Optional[int] = 20,reverse_order : Optional[bool] = False, timeout=5) -> response.GetHistoryMsgListResponse :
    """
    获取好友消息历史
    :param user_id:
    :param message_seq: 0表示从最新开始
    :param count:
    :param reverse_order:
    :param timeout:
    :return:
    """
    action = "get_friend_msg_history"
    param = {
        "user_id": user_id,
        "message_seq": message_seq,
        "count": count,
        "reverseOrder": reverse_order
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetHistoryMsgListResponse)
    return result

async def get_group_msg_history(group_id : int, message_seq : Optional[int] = 0,count : Optional[int] = 20,reverse_order : Optional[bool] = False, timeout=5) -> response.GetHistoryMsgListResponse :
    """
    获取群消息历史
    :param group_id:
    :param message_seq: 0表示从最新开始
    :param count:
    :param reverse_order:
    :param timeout:
    :return:
    """
    action = "get_group_msg_history"
    param = {
        "group_id": group_id,
        "message_seq": message_seq,
        "count": count,
        "reverseOrder": reverse_order
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetHistoryMsgListResponse)
    return result

async def get_forward_msg(message_id : int, timeout=5) -> response.GetHistoryMsgListResponse:
    """
    获取合并转发消息
    :param message_id:
    :param timeout:
    :return:
    """
    action = "get_forward_msg"
    param = {
        "message_id": message_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetHistoryMsgListResponse)
    return result

async def mark_msg_as_read(message_id : int, timeout=5) -> response.BaseResponse:
    """
    标记消息为已读
    :param message_id:
    :param timeout:
    :return:
    """
    action = "mark_msg_as_read"
    param = {
        "message_id": message_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def voice_msg_to_text(message_id : int, timeout=5) -> response.VoiceMsgToTextResponse:
    """
    语音转文字
    :param message_id:
    :param timeout:
    :return:
    """
    action = "voice_msg_to_text"
    param = {
        "message_id": message_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.VoiceMsgToTextResponse)
    return result

async def send_group_ai_record(character : str , group_id : int ,text : str,chat_type : int = 1, timeout=5) -> response.SendMsgResponse:
    """
    发送群AI语音
    :param character:
    :param group_id:
    :param text:
    :param chat_type: 1或2
    :param timeout:
    :return:
    """
    action = "send_group_ai_record"
    param = {
        "character": character,
        "group_id": group_id,
        "text": text,
        "chat_type": chat_type
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.SendMsgResponse)
    return result

async def get_ai_characters(group_id : int,chat_type : int = 1, timeout=5) -> response.GetAIVoiceResponse:
    """
    获取群AI语音角色
    :param group_id:
    :param chat_type: 1或2
    :param timeout:
    :return:
    """
    action = "get_ai_characters"
    param = {
        "group_id": group_id,
        "chat_type": chat_type
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetAIVoiceResponse)
    return result

async def upload_group_file(group_id : int,file : str,name : Optional[str],folder : Optional[str], timeout=5) -> response.UpLoadFileResponse:
    """
    上传群文件
    :param group_id:
    :param file:
    :param name:
    :param folder:
    :param timeout:
    :return:
    """
    action = "upload_group_file"
    param = {
        "group_id": group_id,
        "file": file,
        "name": name,
        "folder": folder
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.UpLoadFileResponse)
    return result

async def set_group_file_forever(group_id : int,file_id : str,timeout=5) -> response.BaseResponse:
    """
    设置群文件永久
    :param group_id:
    :param file_id:
    :param timeout:
    :return:
    """
    action = "set_group_file_forever"
    param = {
        "group_id": group_id,
        "file_id": file_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def delete_group_file(group_id : int,file_id : str,timeout=5) -> response.BaseResponse:
    """
    删除群文件
    :param group_id:
    :param file_id:
    :param timeout:
    :return:
    """
    action = "delete_group_file"
    param = {
        "group_id": group_id,
        "file_id": file_id,
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def move_group_file(group_id : int,file_id : str,parent_directory : str,target_directory :  str ,timeout=5) -> response.BaseResponse:
    """
    移动群文件
    :param group_id:
    :param file_id:
    :param parent_directory:
    :param target_directory:
    :param timeout:
    :return:
    """
    action = "move_group_file"
    param = {
        "group_id": group_id,
        "file_id": file_id,
        "parent_directory": parent_directory,
        "target_directory": target_directory
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def create_group_file_folder(group_id : int,name : str,timeout=5) -> response.CreateGroupFileFolderResponse:
    """
    创建群文件目录
    :param group_id:
    :param name:
    :param timeout:
    :return:
    """
    action = "create_group_file_folder"
    param = {
        "group_id": group_id,
        "name": name
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.CreateGroupFileFolderResponse)
    return result

async def delete_froup_folder(group_id : int,folder_id : str,timeout=5) -> response.BaseResponse:
    """
    删除群文件目录
    :param group_id:
    :param folder_id:
    :param timeout:
    :return:
    """
    action = "delete_froup_folder"
    param = {
        "group_id": group_id,
        "folder_id": folder_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_file_system_info(group_id : int,timeout=5) -> response.GetGroupFileSystemInfoResponse:
    """
    获取群文件系统信息
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_file_system_info"
    param = {
        "group_id": group_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetGroupFileSystemInfoResponse)
    return result

async def get_group_root_files(group_id : int,timeout=5) -> response.GetGroupFilesListResponse:
    """
    获取群根目录文件
    :param group_id:
    :param timeout:
    :return:
    """
    action = "get_group_root_files"
    param = {
        "group_id": group_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetGroupFilesListResponse)
    return result

async def get_group_files_by_folder(group_id : int,folder_id : str,timeout=5) -> response.GetGroupFilesListResponse:
    """
    获取群子目录文件
    :param group_id:
    :param folder_id:
    :param timeout:
    :return:
    """
    action = "get_group_files_by_folder"
    param = {
        "group_id": group_id,
        "folder_id": folder_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetGroupFilesListResponse)
    return result

async def rename_group_file_folder(group_id : int ,folder_id : str,new_folder_name : str,timeout=5) -> response.BaseResponse:
    """
    重命名群文件目录
    :param group_id:
    :param folder_id:
    :param new_folder_name:
    :param timeout:
    :return:
    """
    action = "rename_group_file_folder"
    param = {
        "group_id": group_id,
        "folder_id": folder_id,
        "new_folder_name": new_folder_name
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_group_file_url(group_id : int,file_id : str,timeout=5) -> response.GetFileURLResponse:
    """
    获取群文件URL
    :param group_id:
    :param file_id:
    :param timeout:
    :return:
    """
    action = "get_group_file_url"
    param = {
        "group_id": group_id,
        "file_id": file_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetFileURLResponse)
    return result

async def get_private_file_url(file_id : str,timeout=5) -> response.GetFileURLResponse:
    """
    获取私聊文件URL
    :param file_id:
    :param timeout:
    :return:
    """
    action = "get_private_file_url"
    param = {
        "file_id": file_id
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetFileURLResponse)
    return result

async def upload_private_file(user_id : int,file : str,name : Optional[str],timeout=5) -> response.UpLoadFileResponse:
    """
    上传私聊文件
    :param user_id:
    :param file:
    :param name:
    :param timeout:
    :return:
    """
    action = "upload_private_file"
    param = {
        "user_id": user_id,
        "file": file,
        "name": name
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.UpLoadFileResponse)
    return result

async def upload_flash_file():
    """
    上传闪传文件,暂不支持
    :return:
    """
    pass

async def download_flash_file():
    """
    下载闪传文件,暂不支持
    :return:
    """
    pass

async def get_flash_file_info():
    """
    获取闪传文件信息,暂不支持
    :return:
    """
    pass

async def download_file(url : Optional[str] = None,base64 : Optional[str] = None,name : Optional[str] = None ,headers : List[ dict[str,Any]] = None,timeout : Optional[int] = None) -> response.BaseResponse:
    """
    下载文件到缓存
    :param url:
    :param base64:
    :param name:
    :param headers:
    :param timeout:
    :return:
    """
    action = "download_file"
    param = {
        "url": url,
        "base64": base64,
        "name": name,
        "headers": headers
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result





