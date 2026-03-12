from neobot_adapter.model.response import BaseResponse
from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional, Dict, Any, List
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.file')



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





