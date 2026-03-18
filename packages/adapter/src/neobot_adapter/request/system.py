from neobot_adapter.model.response import BaseResponse
from neobot_adapter.receiver.core import get_core,initialize_core
from typing import Optional, Dict, Any, List
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import response
from neobot_adapter.utils.parse import safe_parse_model

initialize_core()
core = get_core()
logger = get_module_logger('request.system')

async def get_login_info(timeout=5) -> response.GetLoginInfoResponse :
    """
    获取登录号信息
    :return:
    """
    action = "get_login_info"
    param = {}
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetLoginInfoResponse)
    return result

async def get_version_info(timeout=5) -> response.GetVersionResponse :
    """
    获取版本信息
    :return:
    """
    action = "get_version_info"
    param = {}
    result = await core.call_api(action, param,timeout)
    result = safe_parse_model(result, response.GetVersionResponse)
    return result

async def get_status(timeout=5) -> response.BaseResponse:
    """
    获取当前网络状态
    :return:
    """
    action = "get_status"
    param = {}
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def clean_cache(timeout=5) -> response.BaseResponse:
    """
    清理缓存, LLOneBot 5.0+ 之后失效
    :return:
    """
    action = "clean_cache"
    param = {}
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result

async def get_cookies(domain : str = None, timeout=5) -> response.GetCookiesResponse:
    """
    获取cookies
    :param domain:
    :param timeout:
    :return:
    """
    action = "get_cookies"
    param = {
        "domain" : domain
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.GetCookiesResponse)
    return result

async def set_online_status(status : int = 10,ext_status : Optional[int] = 0,battery_status : Optional[int] = 0, timeout=5) -> response.BaseResponse:
    """
    设置在线状态
    :param status:
    10:在线
    30:离开
    40:隐身
    50:忙碌
    60:Q我吧
    70:请勿打扰
    :param ext_status:
    :param battery_status:
    :param timeout:
    :return:
    """
    action = "set_online_status"
    param = {
        "status" : status,
        "ext_status" : ext_status,
        "battery_status" : battery_status
    }
    result = await core.call_api(action, param, timeout)
    result = safe_parse_model(result, response.BaseResponse)
    return result



