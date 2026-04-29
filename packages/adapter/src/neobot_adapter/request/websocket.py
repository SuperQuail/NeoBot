from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from neobot_adapter.receiver.core import AdapterCore
from neobot_adapter.model.basic import *


class WebSocketAPI:
    """
    WebSocket API 客户端，用于通过 AdapterCore 调用 OneBot 协议 API

    该类封装了 AdapterCore 实例，提供了类型安全的 API 调用方法
    """

    def __init__(self, core: AdapterCore):
        """
        初始化 WebSocketAPI 客户端

        Args:
            core: AdapterCore 实例，用于底层的 WebSocket 通信
        """
        self._core = core

    def _convert_params(self, params: Union[Dict[str, Any], BaseModel]) -> Dict[str, Any]:
        """
        将参数转换为字典格式

        Args:
            params: 参数字典或 Pydantic 模型实例

        Returns:
            参数字典

        Raises:
            TypeError: 如果 params 不是字典或 BaseModel 实例
        """
        if isinstance(params, dict):
            return params
        elif isinstance(params, BaseModel):
            # 使用 dict() 方法，排除未设置的字段（exclude_unset=True）
            return params.dict(exclude_unset=True)
        else:
            raise TypeError(f"参数必须是字典或 Pydantic 模型，实际类型: {type(params)}")

    async def call_api(
        self,
        action: str,
        params: Union[Dict[str, Any], BaseModel],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        异步调用 API

        Args:
            action: API 动作名称，例如 'send_group_msg'
            params: 参数字典或 Pydantic 模型实例
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params_dict = self._convert_params(params)
        return await self._core.call_api(action, params_dict, timeout, websocket)

    def call_api_sync(
        self,
        action: str,
        params: Union[Dict[str, Any], BaseModel],
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        同步调用 API

        Args:
            action: API 动作名称，例如 'send_group_msg'
            params: 参数字典或 Pydantic 模型实例
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params_dict = self._convert_params(params)
        return self._core.call_api_sync(action, params_dict, timeout, websocket)

    async def send_message(self, data: Union[Dict[str, Any], BaseModel], websocket: Any = None) -> bool:
        """
        异步发送原始消息

        Args:
            data: 要发送的数据字典或 Pydantic 模型实例
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            是否成功发送
        """
        if isinstance(data, dict):
            data_dict = data
        elif isinstance(data, BaseModel):
            data_dict = data.dict(exclude_unset=True)
        else:
            raise TypeError(f"数据必须是字典或 Pydantic 模型，实际类型: {type(data)}")

        await self._core.send_message(data_dict, websocket)
        return True

    def send_message_sync(self, data: Union[Dict[str, Any], BaseModel], websocket: Any = None, timeout: float = 5.0) -> bool:
        """
        同步发送原始消息

        Args:
            data: 要发送的数据字典或 Pydantic 模型实例
            websocket: 可选，指定使用的 WebSocket 连接
            timeout: 超时时间（秒）

        Returns:
            是否成功发送
        """
        if isinstance(data, dict):
            data_dict = data
        elif isinstance(data, BaseModel):
            data_dict = data.dict(exclude_unset=True)
        else:
            raise TypeError(f"数据必须是字典或 Pydantic 模型，实际类型: {type(data)}")

        return self._core.send_message_sync(data_dict, websocket, timeout)

    # 以下是一些常用 API 的便捷方法，可以根据需要扩展

    async def send_private_msg(
        self,
        user_id: int,
        message: str,
        auto_escape: bool = False,
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送私聊消息

        Args:
            user_id: 对方 QQ 号
            message: 要发送的内容
            auto_escape: 消息内容是否作为纯文本发送（即不解析 CQ 码），默认 False
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params = {
            "user_id": user_id,
            "message": message,
            "auto_escape": auto_escape,
        }
        return await self.call_api("send_private_msg", params, timeout, websocket)

    def send_private_msg_sync(
        self,
        user_id: int,
        message: str,
        auto_escape: bool = False,
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        同步发送私聊消息

        Args:
            user_id: 对方 QQ 号
            message: 要发送的内容
            auto_escape: 消息内容是否作为纯文本发送（即不解析 CQ 码），默认 False
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params = {
            "user_id": user_id,
            "message": message,
            "auto_escape": auto_escape,
        }
        return self.call_api_sync("send_private_msg", params, timeout, websocket)

    async def send_group_msg(
        self,
        group_id: int,
        message: str,
        auto_escape: bool = False,
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送群聊消息

        Args:
            group_id: 群号
            message: 要发送的内容
            auto_escape: 消息内容是否作为纯文本发送（即不解析 CQ 码），默认 False
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params = {
            "group_id": group_id,
            "message": message,
            "auto_escape": auto_escape,
        }
        return await self.call_api("send_group_msg", params, timeout, websocket)

    def send_group_msg_sync(
        self,
        group_id: int,
        message: str,
        auto_escape: bool = False,
        timeout: float = 5.0,
        websocket: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        同步发送群聊消息

        Args:
            group_id: 群号
            message: 要发送的内容
            auto_escape: 消息内容是否作为纯文本发送（即不解析 CQ 码），默认 False
            timeout: 超时时间（秒）
            websocket: 可选，指定使用的 WebSocket 连接

        Returns:
            API 响应数据字典，如果调用失败则返回 None
        """
        params = {
            "group_id": group_id,
            "message": message,
            "auto_escape": auto_escape,
        }
        return self.call_api_sync("send_group_msg", params, timeout, websocket)




