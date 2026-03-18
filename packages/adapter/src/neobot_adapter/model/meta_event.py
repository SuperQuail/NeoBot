from .gengeral import General
from .basic import PostMetaEventType, Status
from enum import Enum
from typing import Optional


class MetaEvent(General):
    """元事件结构"""
    meta_event_type: Optional[PostMetaEventType] = None


class Heartbeat(MetaEvent):
    """心跳包结构"""
    status: Optional[Status] = None
    interval: Optional[int] = None  # 心跳间隔，单位 ms


class LifeCycleSubType(Enum):
    """生命周期子类型枚举类"""
    enable = "enable"  # 启用
    disable = "disable"  # 禁用
    connect = "connect"  # 连接


class LifeCycle(MetaEvent):
    """生命周期结构"""
    sub_type: Optional[LifeCycleSubType] = None