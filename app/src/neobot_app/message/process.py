from enum import Enum

from neobot_adapter.model import notice
from neobot_adapter.model.response import GetSignalMsgResponse, GetSignalMsgData
from neobot_adapter.model.message import GroupMessage,PrivateMessage
from neobot_adapter.model.notice import (
    Notice, PrivateMessageDelete, GroupMessageDelete, GroupIncrease, GroupDecrease,
    GroupAdminChange, GroupUpload, GroupBan, FriendAdd, PrivatePoke, GroupPoke,
    GroupLuckyKing, GroupMemberHonorChange, GroupTitleChange, GroupCardUpdate,
    ReceiveOfflineFile, ClientStatusChange, EssenceMessage
)
from neobot_adapter.request import private
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger(__name__)


async def history_message_to_text(message: GetSignalMsgResponse | GetSignalMsgData) -> str:
    """
    将 message 对象转换为对应字符串
    :param message: GetSignalMsgResponse 或 GetSignalMsgData 对象
    :return:
    """
    # 自动判断类型并提取消息数据
    if isinstance(message, GetSignalMsgResponse):
        msg_data = message.data
    elif isinstance(message, GetSignalMsgData):
        msg_data = message
    else:
        raise TypeError(f"Unsupported message type: {type(message)}")
    
    if msg_data.user_id is None:
        name = "未知用户"
    else:
        info = await private.get_stranger_info(msg_data.user_id)
        name = info.data.nickname if info.data else f"QQ:{msg_data.user_id}"
    message_str = str(name) + ": "
    if not msg_data.message:
        return message_str
    for item in msg_data.message:
        # 获取消息段类型（所有消息段都有 type 属性）
        msg_type = getattr(item, 'type', None)
        # 如果是枚举类型，获取其值
        if isinstance(msg_type, Enum):
            msg_type = msg_type.value

        # 检查类型是否存在
        if msg_type is None:
            message_str += "[未知类型]"
            continue

        # 检查数据是否存在
        if item.data is None:
            message_str += "[无数据]"
            continue
        
        # 调试输出：红包消息
        if msg_type == "redbag":
            import logging
            logging.debug(f"DEBUG: 检测到红包消息段 - type={msg_type}, data={item.data}, title={getattr(item.data, 'title', None)}")

        if msg_type == "text":
            message_str += item.data.text or ""
        elif msg_type == "face":
            message_str += f"表情 [{item.data.id}]"
        elif msg_type == "record":
            message_str += f"语音消息 [{item.data.file or item.data.url or '未知'}]"
        elif msg_type == "video":
            message_str += f"视频消息 [{item.data.file or item.data.url or '未知'}]"
        elif msg_type == "at":
            message_str += f"@{(item.data.name or '某人')}(QQ:{item.data.qq or '未知'})"
        elif msg_type == "image":
            message_str += f"图片 [{item.data.file or item.data.url or '未知'}]"
        elif msg_type == "share":
            message_str += f"分享 [{item.data.title or item.data.url or '未知链接'}]"
        elif msg_type == "reply":
            message_str += f"回复 [消息 ID:{item.data.id}]"
        elif msg_type == "redbag":
            # 红包消息 - 增强容错性
            if item.data:
                title = getattr(item.data, 'title', None) or '恭喜发财，大吉大利'
                message_str += f"红包 [{title}]"
            else:
                message_str += "红包 [恭喜发财，大吉大利]"
        elif msg_type == "poke":
            message_str += f"戳一戳 [QQ:{item.data.qq}]"
        elif msg_type == "gift":
            message_str += f"礼物 [QQ:{item.data.qq}, ID:{item.data.id}]"
        elif msg_type == "forward":
            message_str += f"合并转发 [ID:{item.data.id}]"
        elif msg_type == "node":
            message_str += f"转发节点 [ID:{item.data.id}, 名称:{item.data.name}]"
        elif msg_type == "xml":
            message_str += f"XML 消息 [{item.data.data or 'XML 内容'}]"
        elif msg_type == "json":
            message_str += f"JSON 消息 [{item.data.data or 'JSON 内容'}]"
        elif msg_type == "cardimage":
            message_str += f"卡片图片 [{item.data.file or item.data.url or '未知'}]"
        elif msg_type == "tts":
            message_str += f"TTS [{item.data.text or '语音内容'}]"
        elif msg_type == "rps":
            message_str += "猜拳"
        elif msg_type == "dice":
            message_str += "骰子"
        elif msg_type == "shake":
            message_str += "窗口抖动"
        elif msg_type == "anonymous":
            message_str += "匿名消息"
        elif msg_type == "contact":
            message_str += f"推荐联系人/群 [ID:{item.data.id}]"
        elif msg_type == "location":
            message_str += f"位置 [{item.data.title or '未知位置'}]"
        elif msg_type == "music":
            message_str += f"音乐 [{item.data.title or item.data.type or '未知音乐'}]"
        else:
            # 未知类型，尝试显示基本信息
            message_str += f"未知消息类型 [{msg_type}]"

    return message_str

async def event_message__to_text(message: PrivateMessage|GroupMessage) -> str:
    """
    将事件消息对象转换为对应字符串
    :param message: PrivateMessage 或 GroupMessage 对象
    :return: 格式化的消息字符串
    """
    message_str=""
    # 获取发送者名称
    if message.sender and message.sender.nickname:
        name = message.sender.nickname
    elif message.sender and message.sender.card:
        name = message.sender.card
    elif message.user_id:
        name = f"QQ:{message.user_id}"
    else:
        name = "未知用户"

        message_str = str(name) + ": "

    # 首先尝试使用结构化的 message 字段
    if message.message:
        for item in message.message:
            # 获取消息段类型（所有消息段都有 type 属性）
            msg_type = getattr(item, 'type', None)
            # 如果是枚举类型，获取其值
            if isinstance(msg_type, Enum):
                msg_type = msg_type.value

            # 检查类型是否存在
            if msg_type is None:
                message_str += "[未知类型]"
                continue

            # 检查数据是否存在
            if item.data is None:
                message_str += "[无数据]"
                continue

            if msg_type == "text":
                message_str += item.data.text or ""
            elif msg_type == "face":
                message_str += f"表情 [{item.data.id}]"
            elif msg_type == "record":
                message_str += f"语音消息 [{item.data.file or item.data.url or '未知'}]"
            elif msg_type == "video":
                message_str += f"视频消息 [{item.data.file or item.data.url or '未知'}]"
            elif msg_type == "at":
                message_str += f"@{(item.data.name or '某人')}(QQ:{item.data.qq or '未知'})"
            elif msg_type == "image":
                message_str += f"图片 [{item.data.file or item.data.url or '未知'}]"
            elif msg_type == "share":
                message_str += f"分享 [{item.data.title or item.data.url or '未知链接'}]"
            elif msg_type == "reply":
                message_str += f"回复 [消息 ID:{item.data.id}]"
            elif msg_type == "poke":
                message_str += f"戳一戳 [QQ:{item.data.qq}]"
            elif msg_type == "gift":
                message_str += f"礼物 [QQ:{item.data.qq}, ID:{item.data.id}]"
            elif msg_type == "forward":
                message_str += f"合并转发 [ID:{item.data.id}]"
            elif msg_type == "node":
                message_str += f"转发节点 [ID:{item.data.id}, 名称:{item.data.name}]"
            elif msg_type == "xml":
                message_str += f"XML 消息 [{item.data.data or 'XML 内容'}]"
            elif msg_type == "json":
                message_str += f"JSON 消息 [{item.data.data or 'JSON 内容'}]"
            elif msg_type == "cardimage":
                message_str += f"卡片图片 [{item.data.file or item.data.url or '未知'}]"
            elif msg_type == "tts":
                message_str += f"TTS [{item.data.text or '语音内容'}]"
            elif msg_type == "rps":
                message_str += "猜拳"
            elif msg_type == "dice":
                message_str += "骰子"
            elif msg_type == "shake":
                message_str += "窗口抖动"
            elif msg_type == "anonymous":
                message_str += "匿名消息"
            elif msg_type == "contact":
                message_str += f"推荐联系人/群 [ID:{item.data.id}]"
            elif msg_type == "location":
                message_str += f"位置 [{item.data.title or '未知位置'}]"
            elif msg_type == "music":
                message_str += f"音乐 [{item.data.title or item.data.type or '未知音乐'}]"
            else:
                # 未知类型，尝试显示基本信息
                message_str += f"未知消息类型 [{msg_type}]"
        return message_str

    # 如果结构化的 message 为空，尝试使用 raw_message
    elif message.raw_message:
        # 解析 CQ 码
        return str(name) + ": " + _parse_cq_code(message.raw_message)

    # 如果都没有，返回无消息内容
    else:
        return str(name) + ": [无消息内容]"


async def notice_to_text(notice_data: Notice) -> str:
    """
    将 notice 对象转换为对应字符串
    :param notice_data: Notice 或其子类对象
    :return: 格式化的通知字符串
    """
    # 根据 notice_data 类型生成不同的描述
    if isinstance(notice_data, PrivateMessageDelete):
        return f"私聊消息撤回: 用户 {notice_data.user_id or '未知'} 撤回了消息 {notice_data.message_id or '未知'}"
    elif isinstance(notice_data, GroupMessageDelete):
        return f"群消息撤回: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 的消息 {notice_data.message_id or '未知'} 被 {notice_data.operator_id or '未知'} 撤回"
    elif isinstance(notice_data, GroupIncrease):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"群成员增加: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 通过 {sub_type} 加入，操作者 {notice_data.operator_id or '未知'}"
    elif isinstance(notice_data, GroupDecrease):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"群成员减少: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 通过 {sub_type} 离开，操作者 {notice_data.operator_id or '未知'}"
    elif isinstance(notice_data, GroupAdminChange):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"群管理员变动: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 被 {sub_type} 管理员权限"
    elif isinstance(notice_data, GroupUpload):
        file_info = f"文件 {notice_data.file.name if notice_data.file and notice_data.file.name else '未知'}" if notice_data.file else "未知文件"
        return f"群文件上传: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 上传了 {file_info}"
    elif isinstance(notice_data, GroupBan):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        duration = notice_data.duration if notice_data.duration is not None else '未知'
        target = f"用户 {notice_data.user_id}" if notice_data.user_id != 0 else "全体成员"
        return f"群禁言: 群 {notice_data.group_id or '未知'} 中 {target} 被 {notice_data.operator_id or '未知'} {sub_type} 禁言，时长 {duration} 秒"
    elif isinstance(notice_data, FriendAdd):
        return f"好友添加: 用户 {notice_data.user_id or '未知'} 添加为好友"
    elif isinstance(notice_data, PrivatePoke):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"私聊戳一戳: 用户 {notice_data.sender_id or '未知'} 戳了 {notice_data.target_id or '未知'} ({sub_type})"
    elif isinstance(notice_data, GroupPoke):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"群戳一戳: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 戳了 {notice_data.target_id or '未知'} ({sub_type})"
    elif isinstance(notice_data, GroupLuckyKing):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        return f"群红包运气王: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 成为了用户 {notice_data.target_id or '未知'} 发送的红包运气王 ({sub_type})"
    elif isinstance(notice_data, GroupMemberHonorChange):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        honor_type = getattr(notice_data.honor_type, 'value', '未知') if notice_data.honor_type else '未知'
        return f"群成员荣誉变更: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 的荣誉类型 {honor_type} 发生变更 ({sub_type})"
    elif isinstance(notice_data, GroupTitleChange):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        title = notice_data.title or '未知'
        return f"群成员头衔变更: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 的头衔变更为 '{title}' ({sub_type})"
    elif isinstance(notice_data, GroupCardUpdate):
        card_new = notice_data.card_new or '未知'
        card_old = notice_data.card_old or '未知'
        return f"群成员名片变更: 群 {notice_data.group_id or '未知'} 中用户 {notice_data.user_id or '未知'} 的名片从 '{card_old}' 变更为 '{card_new}'"
    elif isinstance(notice_data, ReceiveOfflineFile):
        file_info = f"文件 {notice_data.file.name if notice_data.file and notice_data.file.name else '未知'}" if notice_data.file else "未知文件"
        return f"接收离线文件: 用户 {notice_data.user_id or '未知'} 发送了 {file_info}"
    elif isinstance(notice_data, ClientStatusChange):
        online_status = "上线" if notice_data.online else "离线" if notice_data.online is False else "未知"
        return f"客户端状态变更: 客户端 {notice_data.client or '未知'} 状态变更为 {online_status}"
    elif isinstance(notice_data, EssenceMessage):
        sub_type = getattr(notice_data.sub_type, 'value', '未知') if notice_data.sub_type else '未知'
        # 根据操作类型设置中文描述
        if sub_type == 'add':
            operation = '加入'
        elif sub_type == 'delete':
            operation = '移出'
        else:
            operation = sub_type
        return f"精华消息变更：群 {notice_data.group_id or '未知'} 中消息 {notice_data.message_id or '未知'} 被 {notice_data.operator_id or '未知'} {operation} 精华，发送者 {notice_data.sender_id or '未知'}"
    else:
        # 未知通知类型
        notice_type = getattr(notice_data.notice_type, 'value', '未知') if notice_data.notice_type else '未知'
        return f"未知通知类型 [{notice_type}]"

async def _notice(event: dict) :
        # 根据 notice_type、sub_type 和事件字段判断具体的 notice类型并解析
        notice_type = event.get('notice_type', '')
        sub_type = event.get('sub_type', '')
        message_type = event.get('message_type', '')  # private 或 group
        group_id = event.get('group_id')  # 检查是否有群号

        # 尝试解析为对应的 notice类型
        parsed_notice = None

        # 私聊消息撤回
        if notice_type == 'private_message_delete' or (notice_type == 'friend_recall'):
            parsed_notice = safe_parse_model(event, notice.PrivateMessageDelete)
        # 群消息撤回
        elif notice_type == 'group_message_delete' or (notice_type == 'group_recall'):
            parsed_notice = safe_parse_model(event, notice.GroupMessageDelete)
        # 群成员增加
        elif notice_type == 'group_increase':
            parsed_notice = safe_parse_model(event, notice.GroupIncrease)
        # 群成员减少
        elif notice_type == 'group_decrease':
            parsed_notice = safe_parse_model(event, notice.GroupDecrease)
        # 群管理员变动
        elif notice_type == 'group_admin_change' or (notice_type == 'group_admin'):
            parsed_notice = safe_parse_model(event, notice.GroupAdminChange)
        # 群文件上传
        elif notice_type == 'group_upload':
            parsed_notice = safe_parse_model(event, notice.GroupUpload)
        # 群禁言
        elif notice_type == 'group_ban':
            parsed_notice = safe_parse_model(event, notice.GroupBan)
        # 好友添加
        elif notice_type == 'friend_add':
            parsed_notice = safe_parse_model(event, notice.FriendAdd)
        # 戳一戳 - 根据 group_id 判断私聊还是群聊（更可靠）
        elif notice_type == 'notify' and sub_type == 'poke':
            if group_id is not None:  # 有群号就是群戳一戳
                parsed_notice = safe_parse_model(event, notice.GroupPoke)
            else:  # 否则是私聊戳一戳
                parsed_notice = safe_parse_model(event, notice.PrivatePoke)
        # 群成员荣誉变更
        elif notice_type == 'notify' and sub_type == 'honor':
            parsed_notice = safe_parse_model(event, notice.GroupMemberHonorChange)
        # 群成员头衔变更
        elif notice_type == 'notify' and sub_type == 'title':
            parsed_notice = safe_parse_model(event, notice.GroupTitleChange)
        # 群成员名片变更
        elif notice_type == 'group_card_update' or (notice_type == 'group_card'):
            parsed_notice = safe_parse_model(event, notice.GroupCardUpdate)
        # 接收离线文件
        elif notice_type == 'receive_offline_file' or (notice_type == 'offline_file'):
            parsed_notice = safe_parse_model(event, notice.ReceiveOfflineFile)
        # 客户端状态变更
        elif notice_type == 'client_status_change' or (notice_type == 'client_status'):
            parsed_notice = safe_parse_model(event, notice.ClientStatusChange)
        # 精华消息变更
        elif notice_type == 'essence_message' or (notice_type == 'essence'):
            parsed_notice = safe_parse_model(event, notice.EssenceMessage)
        else:
            logger.warning(
                f"未知通知类型：notice_type={notice_type}, sub_type={sub_type}, message_type={message_type}, group_id={group_id}")
        return parsed_notice


def _parse_cq_code(cq_string: str) -> str:
    """
    解析 CQ 码字符串为可读文本
    :param cq_string: CQ 码字符串
    :return: 解析后的文本
    """
    import re
    
    result = ""
    # CQ 码格式：[CQ:type,param1=value1,param2=value2,...]
    pattern = r'\[CQ:([^,\]]+)(?:,([^\]]*))?\]'
    
    pos = 0
    for match in re.finditer(pattern, cq_string):
        # 添加 CQ 码之前的普通文本
        if match.start() > pos:
            result += cq_string[pos:match.start()]
        
        cq_type = match.group(1)
        params_str = match.group(2) or ""
        
        # 解析参数
        params = {}
        if params_str:
            param_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)=([^,]+)'
            for param_match in re.finditer(param_pattern, params_str):
                key = param_match.group(1)
                value = param_match.group(2)
                params[key] = value
        
        # 根据类型转换
        if cq_type == "text":
            result += params.get('text', '')
        elif cq_type == "at":
            qq = params.get('qq', '未知')
            name = params.get('name', '')
            if qq == 'all':
                result += "@全体成员"
            else:
                result += f"@{name}(QQ:{qq})"
        elif cq_type == "face":
            face_id = params.get('id', '未知')
            result += f"表情 [{face_id}]"
        elif cq_type == "image":
            file_url = params.get('file', params.get('url', '未知'))
            result += f"图片 [{file_url}]"
        elif cq_type == "record":
            file_url = params.get('file', params.get('url', '未知'))
            result += f"语音 [{file_url}]"
        elif cq_type == "video":
            file_url = params.get('file', params.get('url', '未知'))
            result += f"视频 [{file_url}]"
        elif cq_type == "share":
            url = params.get('url', '未知链接')
            title = params.get('title', '')
            result += f"分享 [{title or url}]"
        elif cq_type == "reply":
            msg_id = params.get('id', '未知')
            result += f"回复 [消息 ID:{msg_id}]"
        elif cq_type == "redbag":
            title = params.get('title', '恭喜发财，大吉大利')
            result += f"红包 [{title}]"
        elif cq_type == "poke":
            qq = params.get('qq', '未知')
            result += f"戳一戳 [QQ:{qq}]"
        elif cq_type == "gift":
            qq = params.get('qq', '未知')
            gift_id = params.get('id', '未知')
            result += f"礼物 [QQ:{qq}, ID:{gift_id}]"
        else:
            # 未知类型，显示原始 CQ 码信息
            result += f"[CQ:{cq_type}]"
        
        pos = match.end()
    
    # 添加剩余的普通文本
    if pos < len(cq_string):
        result += cq_string[pos:]
    
    return result


