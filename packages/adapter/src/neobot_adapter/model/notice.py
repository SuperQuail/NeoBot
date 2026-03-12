from neobot_adapter.model.gengeral import General
from neobot_adapter.model.basic import PostNoticeType
from enum import Enum
from pydantic import BaseModel
from typing import Optional


class Notice(General):
    """Notice 类型基类"""
    notice_type : Optional[PostNoticeType] = None

class PrivateMessageDelete(Notice):
    """私聊消息撤回"""
    user_id : Optional[int] = None #好友 QQ 号
    message_id : Optional[int] = None #被撤回的消息 ID

class GroupMessageDelete(Notice):
    """群消息撤回"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #消息发送者的 QQ 号
    operator_id : Optional[int] = None #操作者 QQ 号
    message_id : Optional[int] = None #被撤回的消息 ID

class GroupIncreaseSubType(Enum):
    """群成员增加类型枚举类"""
    invite = "invite" #邀请
    approve = "approve" #管理员同意

class GroupIncrease(Notice):
    """群成员增加"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被邀请/同意的 QQ 号
    operator_id : Optional[int] = None #操作者 QQ 号
    sub_type : Optional[GroupIncreaseSubType] = None #增加类型

class GroupDecreaseSubType(Enum):
    """群成员减少类型枚举类"""
    leave = "leave" #主动退群
    kick = "kick" #被踢
    kick_me = "kick_me" #自己被踢

class GroupDecrease(Notice):
    """群成员减少"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被踢/退群的 QQ 号
    operator_id : Optional[int] = None #操作者 QQ 号
    sub_type : Optional[GroupDecreaseSubType] = None #减少类型

class GroupAdminChangeSubType(Enum):
    """群管理员变动类型枚举类"""
    set = "set" #设置
    unset = "unset" #取消

class GroupAdminChange(Notice):
    """群管理员变动"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被操作的 QQ 号
    sub_type : Optional[GroupAdminChangeSubType] = None #变动类型

class File(BaseModel):
    """文件结构"""
    id : Optional[str] = None #文件 ID
    name : Optional[str] = None #文件名
    size : Optional[int] = None #文件大小
    busid : Optional[int] = None #文件上传的 Bucket ID

class GroupUpload(Notice):
    """群文件上传"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #上传者 QQ 号
    file : Optional[File] = None #上传的文件信息

class GroupBanSubType(Enum):
    """群禁言类型枚举类"""
    ban = "ban" #禁言
    lift_ban = "lift_ban" #解除

class GroupBan(Notice):
    """群禁言"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被禁言的 QQ 号，如果是全员禁言，则为 0
    operator_id : Optional[int] = None #操作者 QQ 号
    duration : Optional[int] = None #禁言时长，-1 表示全员禁言
    sub_type : Optional[GroupBanSubType] = None #禁言类型

class FriendAdd(Notice):
    """好友添加"""
    user_id : Optional[int] = None #添加者 QQ 号

class PokeSubType(Enum):
    """戳一戳类型枚举类"""
    poke = "poke" #戳一戳

class PrivatePoke(Notice):
    """私聊戳一戳"""
    sender_id : Optional[int] = None #发送者 QQ 号
    user_id : Optional[int] = None #戳一戳的 QQ 号
    target_id : Optional[int] = None #被戳的 QQ 号
    sub_type : Optional[PokeSubType] = None #戳一戳类型

class GroupPoke(Notice):
    """群戳一戳"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #戳一戳的 QQ 号
    target_id : Optional[int] = None #被戳的 QQ 号
    sub_type : Optional[PokeSubType] = None #戳一戳类型

class LuckyKingSubType(Enum):
    """群红包运气王类型枚举类"""
    lucky_king = "lucky_king" #运气王

class GroupLuckyKing(Notice):
    """群红包运气王"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #运气王的 QQ 号
    target_id : Optional[int] = None #红包发送者 QQ 号
    sub_type : Optional[LuckyKingSubType] = None #运气王类型

class GroupMemberHonorChangeSubType(Enum):
    """群成员荣誉变更类型枚举类"""
    honor = "honor"

class HonorType(Enum):
    """群成员荣誉类型枚举类"""
    talkative = "talkative" #龙王
    performer = "performer" #群聊之火
    emotion = "emotion" #快乐源泉

class GroupMemberHonorChange(Notice):
    """群成员荣誉变更"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被操作的 QQ 号
    sub_type : Optional[GroupMemberHonorChangeSubType] = None #荣誉类型
    honor_type : Optional[HonorType] = None

class GroupTitleChangeSubType(Enum):
    """群成员头衔变更类型枚举类"""
    title = "title"

class GroupTitleChange(Notice):
    """群成员头衔变更"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #被操作的 QQ 号
    sub_type : Optional[GroupTitleChangeSubType] = None #头衔类型
    title : Optional[str] = None #新头衔

class GroupCardUpdate(Notice):
    """群成员名片变更"""
    group_id : Optional[int] = None #群号
    user_id : Optional[int] = None #成员的 QQ 号
    card_new : Optional[str] = None #新名片
    card_old : Optional[str] = None #旧名片 当名片为空，两个值都是空字符串而不是昵称

class OfflineFile(BaseModel):
    """离线文件结构"""
    name : Optional[str] = None #文件名
    size : Optional[int] = None #文件大小
    url : Optional[str] = None #文件下载地址

class ReceiveOfflineFile(Notice):
    """接收离线文件"""
    user_id : Optional[int] = None #发送者 QQ 号
    file : Optional[OfflineFile] = None #发送的文件信息

class ClientStatusChange(Notice):
    """客户端状态变更"""
    client : Optional[str] = None #客户端信息
    online : Optional[bool] = None #是否在线

class EssentialMessageType(Enum):
    """精华消息类型枚举类"""
    add = "add" #新增
    delete = "delete" #删除

class EssenceMessage(Notice):
    """精华消息变更"""
    group_id : Optional[int] = None #群号
    sender_id : Optional[int] = None #发送者 QQ 号
    operator_id : Optional[int] = None #操作者 QQ 号
    message_id : Optional[int] = None #消息 ID
    sub_type : Optional[EssentialMessageType] = None #消息类型