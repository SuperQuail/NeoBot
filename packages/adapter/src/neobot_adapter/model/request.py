from gengeral import General
from basic import Post_Request_Type
from enum import Enum
from typing import Optional

class Request(General):
    """请求上报"""
    request_type : Optional[Post_Request_Type] #请求类型

class FriendRequest(Request):
    """加好友请求"""
    user_id : Optional[int] #请求者QQ号
    comment : Optional[str] #请求信息
    flag : Optional[str] #请求标识符

class FastFriendRequestReply(Request):
    """快速回复加好友请求"""
    approve : Optional[bool] #是否通过
    remark : Optional[str] #备注

class group_quest_sub_type(Enum):
    """加群请求子类型枚举类"""
    add = "add" #加群
    invite = "invite" #邀请

class GroupRequest(Request):
    """加群请求"""
    sub_type : Optional[group_quest_sub_type] #请求子类型
    group_id : Optional[int] #群号
    user_id : Optional[int] #请求者QQ号
    comment : Optional[str] #请求信息
    flag : Optional[str] #请求标识符

class FastGroupRequestReply(Request):
    """快速回复加群请求"""
    approve : Optional[bool] #是否通过
    reason : Optional[str] #拒绝理由,仅拒绝时有效