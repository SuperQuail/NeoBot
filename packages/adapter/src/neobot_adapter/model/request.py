from gengeral import General
from basic import PostRequestType
from enum import Enum
from typing import Optional

class Request(General):
    """请求上报"""
    request_type : Optional[PostRequestType] = None #请求类型

class FriendRequest(Request):
    """加好友请求"""
    user_id : Optional[int] = None #请求者 QQ 号
    comment : Optional[str] = None #请求信息
    flag : Optional[str] = None #请求标识符

class FastFriendRequestReply(Request):
    """快速回复加好友请求"""
    approve : Optional[bool] = None #是否通过
    remark : Optional[str] = None #备注

class GroupQuestSubType(Enum):
    """加群请求子类型枚举类"""
    add = "add" #加群
    invite = "invite" #邀请

class GroupRequest(Request):
    """加群请求"""
    sub_type : Optional[GroupQuestSubType] = None #请求子类型
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #请求者 QQ 号
    comment : Optional[str] = None #请求信息
    flag : Optional[str] = None #请求标识符

class FastGroupRequestReply(Request):
    """快速回复加群请求"""
    approve : Optional[bool] = None #是否通过
    reason : Optional[str] = None #拒绝理由，仅拒绝时有效