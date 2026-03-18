"""
消息队列管理模块

根据唯一的关键字（群号/私聊好友QQ号）维护固定长度的队列，
支持自动消息类型转换和快速查找功能。
"""

from collections import deque
from typing import Dict, Deque, Any, Optional, Union, List, Iterator, TypeVar, Generic
import copy
from dataclasses import dataclass, field
from enum import Enum

from neobot_adapter.model.response import GetSignalMsgResponse, GetSignalMsgData
from neobot_adapter.model.message import PrivateMessage, GroupMessage, MessageTypeEnum
from neobot_adapter.model.basic import PostMessageSubType, PostMessageMessagesender
from neobot_adapter.utils.parse import safe_parse_model

T = TypeVar('T', bound=Union[PrivateMessage, GroupMessage])
MessageType = Union[PrivateMessage, GroupMessage, GetSignalMsgResponse, GetSignalMsgData]


class MessageQueueType(Enum):
    """消息队列类型枚举"""
    PRIVATE = "private"
    GROUP = "group"


@dataclass
class QueueStats:
    """队列统计信息"""
    total_messages: int = 0
    oldest_message_id: Optional[int] = None
    newest_message_id: Optional[int] = None
    dropped_messages: int = 0


class MessageQueue:
    """
    消息队列类

    根据关键字维护固定长度的消息队列，支持自动类型转换和快速访问。

    Attributes:
        max_size: 每个队列的最大容量
        _queues: 关键字到队列的映射字典
        _stats: 队列统计信息字典
    """

    def __init__(self, max_size: int = 100):
        """
        初始化消息队列

        Args:
            max_size: 每个队列的最大容量，默认为1000
        """
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")

        self.max_size = max_size
        self._queues: Dict[str, Deque[Union[PrivateMessage, GroupMessage]]] = {}
        self._stats: Dict[str, QueueStats] = {}

    def _convert_message(self, message: MessageType) -> Union[PrivateMessage, GroupMessage]:
        """
        将输入消息转换为标准消息格式

        Args:
            message: 输入消息，可以是 GetSignalMsgResponse、GetSignalMsgData、
                    PrivateMessage 或 GroupMessage

        Returns:
            转换后的 PrivateMessage 或 GroupMessage

        Raises:
            TypeError: 当消息类型不支持时
        """
        if isinstance(message, (PrivateMessage, GroupMessage)):
            return message

        # 处理 GetSignalMsgResponse 和 GetSignalMsgData
        if isinstance(message, GetSignalMsgResponse):
            if not message.data:
                raise ValueError("GetSignalMsgResponse.data is None")
            msg_data = message.data
        elif isinstance(message, GetSignalMsgData):
            msg_data = message
        else:
            raise TypeError(f"Unsupported message type: {type(message)}")

        # 将 msg_data 转换为字典，然后使用 safe_parse_model 进行解析
        # 这样可以自动处理类型转换
        data_dict = msg_data.model_dump()

        # 转换 sender 字段（MessageSender -> PostMessageMessagesender）
        if 'sender' in data_dict and data_dict['sender']:
            sender_dict = data_dict['sender']
            if isinstance(sender_dict, dict):
                # 复制字段，PostMessageMessagesender 可能期望不同的字段
                # 但大多数字段应该是兼容的
                pass  # safe_parse_model 会处理转换

        # 根据数据判断是私聊还是群聊消息
        if msg_data.group_id is not None:
            # 群聊消息
            return safe_parse_model(data_dict, GroupMessage)
        else:
            # 私聊消息
            return safe_parse_model(data_dict, PrivateMessage)

    def _get_or_create_queue(self, key: str) -> Deque[Union[PrivateMessage, GroupMessage]]:
        """获取或创建指定关键字的队列"""
        if key not in self._queues:
            self._queues[key] = deque(maxlen=self.max_size)
            self._stats[key] = QueueStats()
        return self._queues[key]

    def _get_or_create_stats(self, key: str) -> QueueStats:
        """获取或创建指定关键字的统计信息"""
        if key not in self._stats:
            self._stats[key] = QueueStats()
        return self._stats[key]

    def push(self, key: str, message: MessageType) -> None:
        """
        向指定关键字的队列中添加消息

        Args:
            key: 队列关键字（群号或QQ号）
            message: 要添加的消息

        Raises:
            TypeError: 当消息类型不支持时
            ValueError: 当消息数据无效时
        """
        # 转换消息格式
        converted_message = self._convert_message(message)

        # 获取队列和统计信息
        queue = self._get_or_create_queue(key)
        stats = self._get_or_create_stats(key)

        # 记录将被丢弃的消息信息
        if len(queue) == self.max_size and self.max_size > 0:
            dropped_msg = queue[0]
            stats.dropped_messages += 1
            stats.oldest_message_id = queue[1].message_id if len(queue) > 1 else None
        else:
            if stats.oldest_message_id is None:
                stats.oldest_message_id = converted_message.message_id

        # 添加消息到队列
        queue.append(converted_message)

        # 更新统计信息
        stats.total_messages += 1
        stats.newest_message_id = converted_message.message_id

        # 如果队列未满，更新最旧消息ID
        if len(queue) < self.max_size and stats.oldest_message_id is None:
            stats.oldest_message_id = converted_message.message_id

    def get(self, key: str, index: int = -1) -> Optional[Union[PrivateMessage, GroupMessage]]:
        """
        获取指定关键字队列中的消息

        Args:
            key: 队列关键字
            index: 消息索引，-1表示最新的消息，0表示最旧的消息

        Returns:
            指定索引的消息，如果不存在则返回None
        """
        if key not in self._queues:
            return None

        queue = self._queues[key]
        if not queue:
            return None

        try:
            if index < 0:
                # 负索引从队尾开始计算
                return queue[index]
            else:
                # 正索引从队头开始计算
                return queue[index]
        except IndexError:
            return None

    def find_by_message_id(self, key: str, message_id: int) -> Optional[Union[PrivateMessage, GroupMessage]]:
        """
        根据消息ID在指定队列中查找消息

        Args:
            key: 队列关键字
            message_id: 消息ID

        Returns:
            找到的消息，如果不存在则返回None
        """
        if key not in self._queues:
            return None

        # 从最新消息开始向前搜索（更可能找到最近的消息）
        for msg in reversed(self._queues[key]):
            if msg.message_id == message_id:
                return msg

        return None

    def find_by_position(self, key: str, position: int) -> Optional[Union[PrivateMessage, GroupMessage]]:
        """
        根据位置索引查找消息（0为最旧，-1为最新）

        Args:
            key: 队列关键字
            position: 位置索引

        Returns:
            指定位置的消息，如果不存在则返回None
        """
        return self.get(key, position)

    def size(self, key: Optional[str] = None) -> int:
        """
        获取队列大小

        Args:
            key: 队列关键字，如果为None则返回所有队列的总大小

        Returns:
            队列大小
        """
        if key is None:
            return sum(len(queue) for queue in self._queues.values())

        if key not in self._queues:
            return 0

        return len(self._queues[key])

    def get_all_keys(self) -> List[str]:
        """
        获取所有队列关键字

        Returns:
            所有队列关键字的列表
        """
        return list(self._queues.keys())

    def clear(self, key: Optional[str] = None) -> None:
        """
        清空队列

        Args:
            key: 队列关键字，如果为None则清空所有队列
        """
        if key is None:
            self._queues.clear()
            self._stats.clear()
        elif key in self._queues:
            self._queues.pop(key)
            self._stats.pop(key, None)

    def iterate_from_oldest(self, key: str) -> Iterator[Union[PrivateMessage, GroupMessage]]:
        """
        从最旧到最新遍历指定队列的消息

        Args:
            key: 队列关键字

        Yields:
            队列中的消息（从最旧到最新）

        Raises:
            KeyError: 当指定关键字不存在时
        """
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")

        yield from self._queues[key]

    def iterate_from_newest(self, key: str) -> Iterator[Union[PrivateMessage, GroupMessage]]:
        """
        从最新到最旧遍历指定队列的消息

        Args:
            key: 队列关键字

        Yields:
            队列中的消息（从最新到最旧）

        Raises:
            KeyError: 当指定关键字不存在时
        """
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")

        yield from reversed(self._queues[key])

    def get_stats(self, key: str) -> Optional[QueueStats]:
        """
        获取队列统计信息

        Args:
            key: 队列关键字

        Returns:
            队列统计信息，如果队列不存在则返回None
        """
        return self._stats.get(key)

    def clone(self, key: Optional[str] = None) -> 'MessageQueue':
        """
        深克隆消息队列

        Args:
            key: 队列关键字，如果为None则克隆整个消息队列管理器

        Returns:
            克隆后的消息队列实例
        """
        cloned = MessageQueue(max_size=self.max_size)

        if key is None:
            # 克隆所有队列
            for k, queue in self._queues.items():
                cloned._queues[k] = deque((copy.deepcopy(msg) for msg in queue), maxlen=self.max_size)
                cloned._stats[k] = copy.deepcopy(self._stats.get(k, QueueStats()))
        elif key in self._queues:
            # 只克隆指定队列
            cloned._queues[key] = deque((copy.deepcopy(msg) for msg in self._queues[key]), maxlen=self.max_size)
            cloned._stats[key] = copy.deepcopy(self._stats.get(key, QueueStats()))

        return cloned

    def __len__(self) -> int:
        """返回所有队列的总消息数"""
        return self.size()

    def __contains__(self, key: str) -> bool:
        """检查指定关键字是否存在队列"""
        return key in self._queues

    def __getitem__(self, key: str) -> Deque[Union[PrivateMessage, GroupMessage]]:
        """获取指定关键字的队列"""
        if key not in self._queues:
            raise KeyError(f"Queue with key '{key}' does not exist")
        return self._queues[key]

    def __repr__(self) -> str:
        return f"MessageQueue(max_size={self.max_size}, queues={len(self._queues)})"


# 快捷函数
def create_message_queue(max_size: int = 1000) -> MessageQueue:
    """
    创建消息队列实例的快捷函数

    Args:
        max_size: 队列最大容量

    Returns:
        消息队列实例
    """
    return MessageQueue(max_size=max_size)
