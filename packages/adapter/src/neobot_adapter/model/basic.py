from pydantic import BaseModel
from typing import Optional
from enum import Enum

class PostType(Enum):
    """一个枚举, 传输使用字符串, 表示上报类型"""
    message = "message" #消息, 例如, 群聊消息
    message_sent = "message_sent" #消息发送，例如，bot发送在群里的消息
    request = "request" #请求, 例如, 好友申请
    notice = "notice_data" #通知, 例如, 群成员增加
    meta_event = "meta_event" #元事件, 例如心跳包

class PostMessageType(Enum):
    """一个枚举, 传输使用字符串, 表示消息类型"""
    private = "private" #私聊
    group = "group" #群聊

class PostMessageSubType(Enum):
    """一个枚举, 传输使用字符串, 表示消息子类型"""
    friend = "friend" #好友
    normal = "normal" #群聊
    anonymous = "anonymous" #匿名
    group_self = "group_self" #群中自身发送
    group = "group" #群临时对话
    notice = "notice_data" #系统提示

class PostMessageTempSource(Enum):
    """一个枚举, 传输使用 int32"""
    group = 0 #群聊
    qq_ask = 1 #QQ咨询
    search = 2 #查找
    qq_film = 3 #QQ电影
    hot_chat = 4 #热聊
    vercify_message = 6 #验证消息
    multiple_chat = 7 #多人聊天
    date = 8 #约会
    contacts = 9 #通讯录

class PostRequestType(Enum):
    """一个枚举, 传输使用字符串, 表示请求类型."""
    friend = "friend" #好友请求
    group = "group" #群请求

class PostNoticeType(Enum):
    """一个枚举, 传输使用字符串, 表示通知类型"""
    group_upload = "group_upload" #群文件上传
    group_admin = "group_admin" #群管理员变动
    group_decrease = "group_decrease" #群成员减少
    group_increase = "group_increase" #群成员增加
    group_ban = "group_ban" #群成员禁言
    friend_add = "friend_add" #好友添加
    group_recall = "group_recall" #群消息撤回
    friend_recall = "friend_recall" #好友消息撤回
    group_card = "group_card" #群名片更新
    offline_file = "OfflineFile" #离线文件上传
    client_status = "client_status" #客户端状态变更
    essence = "essence" #精华消息
    notify = "notify" #系统通知

class PostNoticeNotifySubType(Enum):
    """一个枚举, 传输使用字符串, 描述通知子类型"""
    honor = "honor" #群荣誉变更
    poke = "poke" #戳一戳
    lucky_king = "lucky_king" #群红包幸运王
    title = "title" #群成员头衔变更

class PostMetaEventType(Enum):
    """一个枚举, 传输使用字符串, 表示元事件类型"""
    lifecycle = "lifecycle" #生命周期
    heartbeat = "heartbeat" #心跳包

class StatusStatistics(BaseModel):
    """一个数据结构，是心跳包的 status 字段的 stat 字段"""
    packet_received: Optional[int] = None #收包数
    packet_sent: Optional[int] = None #发包数
    packet_lost: Optional[int] = None #丢包数
    message_received: Optional[int] = None #接收到的消息数
    message_sent: Optional[int] = None #发送的消息数
    disconnect_times: Optional[int] = None #连接断开次数
    lost_times: Optional[int] = None #连接丢失次数
    last_message_time: Optional[int] = None #最后一次消息时间

class Status(BaseModel):
    """一个数据结构，在心跳包上报中作为成员使用"""
    app_initialized: Optional[bool] = None #程序是否初始化完毕
    app_enabled: Optional[bool] = None #程序是否可用
    plugins_good: Optional[bool] = None #插件正常
    app_good: Optional[bool] = None #程序正常
    online: Optional[bool] = None #是否在线
    stat: Optional[StatusStatistics] = None #统计信息

class PostMetaEventLifecycleType(Enum):
    """一个枚举, 传输使用字符串, 表示生命周期上报的子类型"""
    enable = "enable" #启用
    disable = "disable" #禁用
    connect = "connect" #连接

class Sex(Enum):
    male = "male" #男
    female = "female" #女
    unknown = "unknown" #未知

class Role(Enum):
    owner = "owner" #群主
    admin = "admin" #管理员
    member = "member" #群成员

class PostMessageMessagesender(BaseModel):
    """表示消息发送者的信息"""
    user_id: Optional[int] = None #发送者 QQ 号
    nickname: Optional[str] = None #昵称
    sex: Optional[Sex] = None #性别
    age: Optional[int] = None #年龄
    """当私聊类型为群临时会话时的额外字段:"""
    group_id: Optional[int] = None #临时群消息来源群号
    """如果是群聊:"""
    card: Optional[str] = None #群名片/备注
    area: Optional[str] = None #地区
    level: Optional[str] = None #成员等级
    role: Optional[Role] = None #角色
    title: Optional[str] = None #专属头衔
    """该消息在 "message" 上报中被使用"""