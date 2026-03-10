from gengeral import General
from neobot_adapter.model.basic import Post_Notice_Type
from enum import Enum
from pydantic import BaseModel


class Notice(General):
    """Notice类型基类"""
    notice_type : Post_Notice_Type

class PrivateMessageDelete(Notice):
    """私聊消息撤回"""
    user_id : int #好友QQ号
    message_id : int #被撤回的消息ID

class GroupMessageDelete(Notice):
    """群消息撤回"""
    group_id : int #群号
    user_id : int #消息发送者的QQ号
    operator_id : int #操作者QQ号
    message_id : int #被撤回的消息ID

class group_increase_sub_type(Enum):
    """群成员增加类型枚举类"""
    invite = "invite" #邀请
    approve = "approve" #管理员同意

class GroupIncrease(Notice):
    """群成员增加"""
    group_id : int #群号
    user_id : int #被邀请/同意的QQ号
    operator_id : int #操作者QQ号
    sub_type : group_increase_sub_type #增加类型

class group_decrease_sub_type(Enum):
    """群成员减少类型枚举类"""
    leave = "leave" #主动退群
    kick = "kick" #被踢
    kick_me = "kick_me" #自己被踢

class GroupDecrease(Notice):
    """群成员减少"""
    group_id : int #群号
    user_id : int #被踢/退群的QQ号
    operator_id : int #操作者QQ号
    sub_type : group_decrease_sub_type #减少类型

class group_admin_change_sub_type(Enum):
    """群管理员变动类型枚举类"""
    set = "set" #设置
    unset = "unset" #取消

class GroupAdminChange(Notice):
    """群管理员变动"""
    group_id : int #群号
    user_id : int #被操作的QQ号
    sub_type : group_admin_change_sub_type #变动类型

class file(BaseModel):
    """文件结构"""
    id : str #文件ID
    name : str #文件名
    size : int #文件大小
    busid : int #文件上传的Bucket ID

class GroupUpload(Notice):
    """群文件上传"""
    group_id : int #群号
    user_id : int #上传者QQ号
    file : file #上传的文件信息

class group_ban_sub_type(Enum):
    """群禁言类型枚举类"""
    ban = "ban" #禁言
    lift_ban = "lift_ban" #解除

class GroupBan(Notice):
    """群禁言"""
    group_id : int #群号
    user_id : int #被禁言的QQ号, 如果是全员禁言, 则为0
    operator_id : int #操作者QQ号
    duration : int #禁言时长,-1表示全员禁言
    sub_type : group_ban_sub_type #禁言类型

class FriendAdd(Notice):
    """好友添加"""
    user_id : int #添加者QQ号

class poke_sub_type(Enum):
    """戳一戳类型枚举类"""
    poke = "poke" #戳一戳

class PrivatePoke(Notice):
    """私聊戳一戳"""
    sender_id : int #发送者QQ号
    user_id : int #戳一戳的QQ号
    target_id : int #被戳的QQ号
    sub_type : poke_sub_type #戳一戳类型

class GroupPoke(Notice):
    """群戳一戳"""
    group_id : int #群号
    user_id : int #戳一戳的QQ号
    target_id : int #被戳的QQ号
    sub_type : poke_sub_type #戳一戳类型

class lucky_king_sub_type(Enum):
    """群红包运气王类型枚举类"""
    lucky_king = "lucky_king" #运气王

class GroupLuckyKing(Notice):
    """群红包运气王"""
    group_id : int #群号
    user_id : int #运气王的QQ号
    target_id : int #红包发送者QQ号
    sub_type : lucky_king_sub_type #运气王类型

class group_member_honor_change_sub_type(Enum):
    """群成员荣誉变更类型枚举类"""
    honor = "honor"

class honor_type(Enum):
    """群成员荣誉类型枚举类"""
    talkative = "talkative" #龙王
    performer = "performer" #群聊之火
    emotion = "emotion" #快乐源泉

class GroupMemberHonorChange(Notice):
    """群成员荣誉变更"""
    group_id : int #群号
    user_id : int #被操作的QQ号
    sub_type : group_member_honor_change_sub_type #荣誉类型
    honor_type : honor_type

class group_title_change_sub_type(Enum):
    """群成员头衔变更类型枚举类"""
    title = "title"

class GroupTitleChange(Notice):
    """群成员头衔变更"""
    group_id : int #群号
    user_id : int #被操作的QQ号
    sub_type : group_title_change_sub_type #头衔类型
    title : str #新头衔

class GroupCardUpdate(Notice):
    """群成员名片变更"""
    group_id : int #群号
    user_id : int #成员的QQ号
    card_new : str #新名片
    card_old : str #旧名片 当名片为空,两个值都是空字符串而不是昵称

class offline_file(BaseModel):
    """离线文件结构"""
    name : str #文件名
    size : int #文件大小
    url : str #文件下载地址

class ReceiveOfflineFile(Notice):
    """接收离线文件"""
    user_id : int #发送者QQ号
    file : offline_file #发送的文件信息

class ClientStatusChange(Notice):
    """客户端状态变更"""
    client : str #客户端信息
    online : bool #是否在线

class essential_message_type(Enum):
    """精华消息类型枚举类"""
    add = "add" #新增
    delete = "delete" #删除

class EssenceMessage(Notice):
    """精华消息变更"""
    group_id : int #群号
    sender_id : int #发送者QQ号
    operator_id : int #操作者QQ号
    message_id : int #消息ID
    sub_type : essential_message_type #消息类型