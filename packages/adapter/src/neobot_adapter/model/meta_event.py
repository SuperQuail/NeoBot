from .gengeral import General
from .basic import Post_MetaEvent_Type, Status
from enum import Enum


class MetaEvent(General):
    """元事件结构"""
    meta_event_type: Post_MetaEvent_Type


class Heartbeat(MetaEvent):
    """心跳包结构"""
    status: Status
    interval: int  # 心跳间隔, 单位ms


class life_cycle_sub_type(Enum):
    """生命周期子类型枚举类"""
    enable = "enable"  # 启用
    disable = "disable"  # 禁用
    connect = "connect"  # 连接


class LifeCycle(MetaEvent):
    """生命周期结构"""
    sub_type: life_cycle_sub_type