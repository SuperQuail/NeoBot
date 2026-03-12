from pydantic import BaseModel
from typing import Optional, List, Dict, Any,Union

from neobot_adapter.model.basic import Sex


class BaseResponse(BaseModel):
    """基础响应模型"""
    status: Optional[str] = None
    retcode: Optional[int] = None
    message: Optional[str] = None # 信息
    wording: Optional[str] = None # 提示
    data: Optional[Any] = None

class NullDataResponse(BaseResponse):
    """空数据响应模型"""
    data: Optional[Any] = None

class SendLikeResponse(BaseResponse):
    """点赞响应模型"""
    data: Optional[None] = None
    echo: Optional[str] = None

class FriendData(BaseModel):
    """数据模型"""
    user_id: int = 0 # QQ 号
    nickname: str = '' # 昵称
    remark: Optional[str] = None # 备注
    sex: Optional[Sex] = None
    birthday_year: Optional[int] = None
    birthday_month: Optional[int] = None
    birthday_day: Optional[int] = None
    age : Optional[int] = None
    qid: Optional[str] = None
    long_nick: Optional[str] = None #个性签名

class GetFriendListResponse(BaseResponse):
    """获取好友列表响应模型"""
    data : Optional[List[FriendData]] = None

class BuddyData(FriendData):
    """列表中的好友模型"""
    level : Optional[int] = None
    longNick : Optional[str] = None
    eMail : Optional[str] = None
    uid : Optional[str] = None
    categoryId : Optional[int] = None
    richTime : Optional[int] = None

class CategoryFriendData(BaseModel):
    categoryId : int = 0
    categorySortId : int = 0
    categoryName : str = ''
    categoryMbCount : int = 0
    onlineCount : int = 0
    buddyList : Optional[List[BuddyData]] = None

class CategoryFriendResponse(BaseResponse):
    """获取好友列表响应模型"""
    data : List[CategoryFriendData] = []

class StrangerInfoData(FriendData):
    city : Optional[str] = None
    country : Optional[str] = None
    labs : Optional[List[ str]] = None

class StrangerInfoResponse(BaseResponse):
    """获取陌生人信息响应模型"""
    data : Optional[StrangerInfoData] = None

class Users(BaseModel):
    uid : Optional[str] = None
    src : Optional[int] = None
    latestTime : Optional[int] = None
    count : Optional[int] = None
    giftCount : Optional[int] = None
    customId : Optional[int] = None
    lastCharged : Optional[int] = None
    bAvailableCnt : Optional[int] = None
    bTodayVotedCnt : Optional[int] = None
    nick : Optional[str] = None
    gender : Optional[int] = None
    age : Optional[int] = None
    isFriend : Optional[bool] = None
    isVip : Optional[bool] = None
    isSvip : Optional[bool] = None
    uin : Optional[int] = None

class ProfileLikeData(BaseModel):
    """群成员资料模型"""
    users : Optional[List[Users]] = None
    nextStart : Optional[int] = None

class ProfileLikeResponse(BaseResponse):
    """获取群成员资料响应模型"""
    data : Optional[ProfileLikeData] = None

class ProfileLikeMeResponse(BaseResponse):
    """获取群成员资料响应模型"""
    data : Optional[ProfileLikeData] = None

class RobotUinRangeData(BaseModel):
    """机器人 QQ 号范围模型"""
    minUin : Optional[int] = None
    maxUin : Optional[int] = None

class RobotUinRangeResponse(BaseResponse):
    """获取机器人 QQ 号范围响应模型"""
    data : Optional[List[RobotUinRangeData]] = None

class URLData(BaseModel):
    """URL 模型"""
    url : Optional[str] = None

class QQAvatarResponse(BaseResponse):
    """设置 QQ 头像响应模型"""
    data : Optional[URLData] = None

class DoubtFriendsAddRequestData(BaseModel):
    """好友添加请求模型"""
    flag : Optional[str] = None
    uin : Optional[str] = None
    nick : Optional[str] = None
    source : Optional[str] = None
    msg : Optional[str] = None
    group_code : Optional[str] = None
    time : Optional[str] = None
    type : Optional[str] = None

class DoubtFriendsAddRequest(BaseModel):
    """好友添加请求模型"""
    data : Optional[List[DoubtFriendsAddRequestData]] = None

class SetDoubtFriendsAddRequest(BaseResponse):
    """处理好友添加请求响应模型"""
    data : Optional[None] = None

class SetQQProfileResponse(BaseResponse):
    """设置 QQ 资料响应模型"""
    data : Optional[None] = None

class GroupData(BaseModel):
    """群组模型"""
    group_id : Optional[int] = None
    group_name : Optional[str] = None
    group_memo : Optional[str] = None # 群介绍
    group_create_time : Optional[int] = None
    member_count : Optional[int] = None
    member_count : Optional[int] = None
    max_member_count : Optional[int] = None
    remark_name : Optional[str] = None # 群备注
    avatar_url : Optional[str] = None
    owner_id : Optional[int] = None
    is_top : Optional[bool] = None # 是否置顶
    shut_up_all_timestamp : Optional[int] = None # 全员禁言剩余时间
    shut_up_me_timestamp : Optional[int] = None # 我被禁言剩余时间

class GetGroupListResponse(BaseResponse):
    """获取群组列表响应模型"""
    data : Optional[List[GroupData]] = None

class GroupInfoData(GroupData):
    """群组模型"""
    is_freeze : Optional[bool] = None # 是否被冻结
    active_member_count : Optional[int] = None # 活跃群成员数

class GetGroupInfoResponse(BaseResponse):
    """获取群组信息响应模型"""
    data : Optional[GroupInfoData] = None

class GroupMemberData(BaseModel):
    """群组成员模型"""
    group_id : Optional[int] = None
    user_id : Optional[int] = None
    nickname : Optional[str] = None
    card : Optional[str] = None
    card_or_nickname : Optional[str] = None
    sex : Optional[Sex] = None
    age : Optional[int] = None
    area : Optional[str] = None
    level : Optional[str] = None
    qq_level : Optional[int] = None
    join_time : Optional[int] = None
    last_sent_time : Optional[int] = None
    title_expire_time : Optional[int] = None
    unfriendly : Optional[bool] = None
    card_changeable : Optional[bool] = None # 是否允许修改群名片
    is_robot : Optional[bool] = None # 是否是机器人
    role : Optional[str] = None #owner / admin / member
    title : Optional[str] = None # 群头衔

class GetGroupMemberListResponse(BaseResponse):
    """获取群组成员列表响应模型"""
    data : Optional[List[GroupMemberData]] = None


class GetGroupMemberInfoResponse(BaseResponse):
    """获取群组成员信息响应模型"""
    data : Optional[GroupMemberData] = None

class InvitedRequestsData(BaseModel):
    """群组邀请请求模型"""
    request_id : Optional[int] = None
    group_id : Optional[int] = None
    group_name : Optional[str] = None
    invitor_nick : Optional[str] = None
    invitor_uin : Optional[int] = None
    checked : Optional[bool] = None
    actor : Optional[int] = None

class JoinRequestsData(BaseModel):
    """群组入群请求模型"""
    request_id : Optional[int] = None
    requester_uin : Optional[int] = None
    requester_nick : Optional[str] = None
    message : Optional[str] = None
    group_id : Optional[int] = None
    checked : Optional[bool] = None
    actor : Optional[int] = None

class GetGroupSystemMsgResponse(BaseResponse):
    """获取群组系统消息响应模型"""
    data : Optional[Dict[str, List[Union[InvitedRequestsData, JoinRequestsData]]]] = None

class TalkativeData(BaseModel):
    """当前群组龙王模型"""
    user_id : Optional[int] = None
    avatar : Optional[str] = None
    nickname : Optional[str] = None
    day_count : Optional[int] = None
    description : Optional[str] = None

class PerformerData(BaseModel):
    """群组群聊之火模型"""
    user_id : Optional[int] = None
    nickname : Optional[str] = None
    avatar : Optional[str] = None
    description : Optional[str] = None

class GroupHonorInfoData(BaseModel):
    """群组荣耀信息模型"""
    group_id : Optional[int] = None
    current_talkative : Optional[TalkativeData] = None
    talkative_list : Optional[List[TalkativeData]] = None
    performer_list : Optional[List[PerformerData]] = None
    legend_list : Optional[List[str]] = None
    emotion_list : Optional[List[str]] = None
    strong_newbie_list : Optional[List[str]] = None

class GetGroupHonorInfoResponse(BaseResponse):
    """获取群组荣耀信息响应模型"""
    data : Optional[GroupHonorInfoData] = None

class EssenceMsgData(BaseModel):
    """群组精华消息模型"""
    sender_id : Optional[int] = None
    sender_nick : Optional[str] = None
    sender_time : Optional[int] = None
    operator_id : Optional[int] = None
    operator_nick : Optional[str] = None
    operator_time : Optional[int] = None
    message_id : Optional[int] = None

class GetEssenceMsgListResponse(BaseResponse):
    """获取群组精华消息列表响应模型"""
    data : Optional[List[EssenceMsgData]] = None

class GroupAtAllRemain(BaseModel):
    """群组@全体成员剩余次数模型"""
    can_at_all : Optional[bool] = None
    remain_at_all_count_for_group : Optional[int] = None # 群组@全体成员剩余次数
    remain_at_all_count_for_uin : Optional[int] = None # 个人@全体成员剩余次数

class GetGroupAtAllRemainResponse(BaseResponse):
    """获取群组@全体成员剩余次数响应模型"""
    data : Optional[GroupAtAllRemain] = None

class Images(BaseModel):
    """图片模型"""
    height : Optional[str] = None
    width : Optional[str] = None
    id : Optional[str] = None #图片 ID，图片 URL 为 https://gdynamic.qpic.cn/gdynamic/(id)/0

class ImagesURLType(BaseModel):
    """图片模型"""
    height : Optional[str] = None
    width : Optional[str] = None
    url : Optional[str] = None #图片 ID，图片 URL 为 https://gdynamic.qpic.cn/gdynamic/(id)/0

class message(BaseModel):
    """消息模型"""
    text : Optional[str] = None
    images : Optional[List[Images]] = None

class GroupNoticeData(BaseModel):
    """群组公告模型"""
    notice_id : Optional[str] = None
    sender_id : Optional[int] = None
    publisher_time : Optional[int] = None
    message : Optional[message] = None

class GetGroupNoticeResponse(BaseResponse):
    """获取群组公告响应模型"""
    data : Optional[List[GroupNoticeData]] = None

class UploadGroupAlbumData(BaseModel):
    """上传群组相册模型"""
    success_count : Optional[int] = None
    fail_count : Optional[int] = None
    fail_indexes : Optional[List[str]] = None

class GetUploadGroupAlbumResponse(BaseResponse):
    """上传群组相册响应模型"""
    data : Optional[UploadGroupAlbumData] = None

class AlbumPhotoUrl(BaseModel):
    """群组相册图片模型"""
    spec : Optional[int] = None
    url : ImagesURLType = ImagesURLType()

class AlbumCoverImageData(BaseModel):
    """群组相册封面图片模型"""
    name : Optional[str] = None
    sloc : Optional[str] = None
    lloc : Optional[str] = None
    photo_url : Optional[AlbumPhotoUrl] = None
    default_url : ImagesURLType = ImagesURLType()
    is_gif : Optional[bool] = None
    has_raw : Optional[bool] = None



class AlbumCoverData(BaseModel):
    """群组相册封面模型"""
    type : Optional[int] = None
    image : Optional[AlbumCoverImageData] = None
    video : Optional[None] = None
    video : Optional[None] = None
    desc : Optional[str] = None
    lbs : Optional[None] = None
    uploader : Optional[str] = None
    batch_id : Optional[str] = None
    upload_time : Optional[str] = None
    upload_order : Optional[int] = None
    like : Optional[None] = None
    comment : Optional[None] = None
    upload_user : Optional[str] = None
    ext : Optional[List[str]] = None
    shoot_time : Optional[str] = None
    link_id : Optional[str] = None
    op_mask : Optional[List[str]] = None
    lbs_source : Optional[int] = None

class AlbumCreatorData(BaseModel):
    uid : Optional[str] = None
    nick : Optional[str] = None
    yellow_info : Optional[None] = None
    star_info : Optional[None] = None
    is_sweet : Optional[bool] = None
    is_special : Optional[bool] = None
    is_super_like : Optional[bool] = None
    custom_id : Optional[str] = None
    poly_id : Optional[str] = None
    portrait : Optional[str] = None
    can_follow : Optional[int] = None
    isfollowed : Optional[int] = None
    uin : Optional[str] = None
    ditto_uin : Optional[str] = None

class AlbumData(BaseModel):
    album_id : Optional[str] = None
    owner : Optional[str] = None
    name : Optional[str] = None
    desc : Optional[str] = None
    create_time : Optional[str] = None
    modify_time : Optional[str] = None
    last_upload_time : Optional[str] = None
    upload_number : Optional[str] = None
    cover : Optional[AlbumCoverData] = None
    creator : Optional[AlbumCreatorData] = None
    top_flag : Optional[str] = None
    busi_type : Optional[int] = None
    status : Optional[int] = None
    permission : Optional[None] = None
    allow_share : Optional[bool] = None
    is_subscribe : Optional[bool] = None
    bitmap : Optional[str] = None
    is_share_album : Optional[bool] = None
    share_album : Optional[None] = None
    qz_album_type : Optional[int] = None
    family_album : Optional[None] = None
    lover_album : Optional[None] = None
    cover_type : Optional[int] = None
    travel_album : Optional[None] = None
    visitor_info : Optional[None] = None
    default_desc : Optional[str] = None
    op_info : Optional[None] = None
    active_album : Optional[None] = None
    memory_info : Optional[None] = None
    sort_type : Optional[int] = None

class GetGroupAlbumResponse(BaseResponse):
    """获取群组相册响应模型"""
    data : Optional[List[AlbumData]] = None

class CreateGroupAlbumResponse(BaseModel):
    """创建群组相册模型"""
    album_id : Optional[str] = None

class SendPrivateMsgData(BaseModel):
    """发送私聊消息模型"""
    message_id : Optional[int] = None

class SendMsgResponse(BaseResponse):
    """发送私聊消息响应模型"""
    data : Optional[SendPrivateMsgData] = None

class MessageSender(BaseModel):
    """消息发送者模型"""
    user_id : Optional[int] = None
    nickname : Optional[str] = None
    card : Optional[str] = None
    role : Optional[str] = None
    title : Optional[str] = None

class BasicMessageData(BaseModel):
    """文本消息模型"""
    text : Optional[str] = None
    file : Optional[str] = None
    subtype : Optional[int] = None
    url : Optional[str] = None
    file_size : Optional[int] = None
    data : Optional[str] = None
    id : Optional[str] = None
    path : Optional[str] = None
    result : Optional[str] = None
    file_id : Optional[str] = None

class MessageData(BaseModel):
    """消息模型"""
    type : Optional[str] = None
    data : Optional[BasicMessageData] = None

class GetSignalMsgData(BaseModel):
    """获取消息模型"""
    self_id : Optional[int] = None
    user_id : Optional[int] = None
    time : Optional[int] = None
    message_id : Optional[int] = None
    real_id : Optional[int] = None
    message_seq : Optional[int] = None
    message_type : Optional[str] = None
    sender : Optional[MessageSender] = None
    raw_message : Optional[str] = None
    font : Optional[int] = None
    sub_type : Optional[str] = None
    message : Optional[List[MessageData]] = None
    message_format : Optional[str] = None
    post_type : Optional[str] = None
    group_id : Optional[int] = None

class GetSignalMsgResponse(BaseResponse):
    """获取消息响应模型"""
    data : Optional[GetSignalMsgData] = None

class GetMessageFileData(BaseModel):
    """获取消息文件模型"""
    file : Optional[str] = None
    url : Optional[str] = None
    file_size : Optional[str] = None
    file_name : Optional[str] = None

class GetMessageFileResponse(BaseResponse):
    """获取消息文件响应模型"""
    data : Optional[GetMessageFileData] = None

class GetRecordData(BaseModel):
    """获取录音模型"""
    file : Optional[str] = None
    base64 : Optional[str] = None
    file_size : Optional[str] = None
    file_name : Optional[str] = None

class GetRecordResponse(BaseResponse):
    """获取录音响应模型"""
    data : Optional[GetRecordData] = None

class GetHistoryMsgListResponse(BaseResponse):
    """获取好友消息列表响应模型"""
    data : Optional[List[GetSignalMsgData]] = None

class TextData(BaseModel):
    """文本消息模型"""
    text : Optional[str] = None

class VoiceMsgToTextResponse(BaseModel):
    """语音消息转文字模型"""
    text : Optional[TextData] = None

class AIVoiceCharacterData(BaseModel):
    """AI 语音模型"""
    character_id : Optional[str] = None
    character_name : Optional[str] = None
    preview_url : Optional[str] = None

class AICharacterData(BaseModel):
    type : Optional[str] = None
    data : Optional[List[AIVoiceCharacterData]] = None

class GetAIVoiceResponse(BaseResponse):
    """AI 语音响应模型"""
    data : Optional[AICharacterData] = None

class UpLoadFileData(BaseModel):
    """上传文件模型"""
    file_id : Optional[str] = None

class UpLoadFileResponse(BaseResponse):
    """上传文件响应模型"""
    data : Optional[UpLoadFileData] = None

class CreateGroupFileFolderData(BaseModel):
    """创建群组文件目录模型"""
    file_id : Optional[str] = None

class CreateGroupFileFolderResponse(BaseResponse):
    """创建群组文件目录响应模型"""
    data : Optional[CreateGroupFileFolderData] = None

class GroupFileSystemInfoData(BaseModel):
    """群组文件系统信息模型"""
    file_count : Optional[int] = None
    limit_count : Optional[int] = None
    used_space : Optional[int] = None
    total_space : Optional[int] = None

class GetGroupFileSystemInfoResponse(BaseResponse):
    """获取群组文件系统信息响应模型"""
    data : Optional[GroupFileSystemInfoData] = None

class GroupFileData(BaseModel):
    """群组文件模型"""
    group_id : Optional[int] = None
    file_id : Optional[str] = None
    file_name : Optional[str] = None
    busid : Optional[int] = None
    file_size : Optional[int] = None
    upload_time : Optional[int] = None
    dead_time : Optional[int] = None #过期时间，为 0 永久文件
    modify_time : Optional[int] = None #最后修改时间
    download_times : Optional[int] = None
    uploader : Optional[int] = None
    uploader_name : Optional[str] = None

class GroupFoldersData(BaseModel):
    """群组文件目录模型"""
    group_id : Optional[int] = None
    folder_id : Optional[str] = None
    folder_name : Optional[str] = None
    creat_time : Optional[int] = None
    creator : Optional[int] = None
    creator_name : Optional[str] = None
    total_file_count : Optional[int] = None

class GetGroupRootFilesData(BaseResponse):
    """获取群组根目录文件列表响应模型"""
    files : Optional[List[GroupFileData]] = None
    folders : Optional[List[GroupFoldersData]] = None

class GetGroupFilesListResponse(BaseResponse):
    """获取群组根目录文件列表响应模型"""
    data : Optional[GetGroupRootFilesData] = None

class GetFileURLResponse(BaseModel):
    """群组文件 URL 模型"""
    data : Optional[URLData] = None

class LoginInfoData(BaseModel):
    """登录信息模型"""
    user_id : Optional[int] = None
    nickname : Optional[str] = None

class GetLoginInfoResponse(BaseResponse):
    """登录信息响应模型"""
    data : Optional[LoginInfoData] = None

class VersionData(BaseModel):
    """版本信息模型"""
    app_name : Optional[str] = None
    app_version : Optional[str] = None
    protocol_version : Optional[str] = None

class GetVersionResponse(BaseResponse):
    """版本信息响应模型"""
    data : Optional[VersionData] = None

class CookieData(BaseModel):
    """Cookie 模型"""
    cookies : Optional[str] = None
    bkn : Optional[str] = None

class GetCookiesResponse(BaseResponse):
    """Cookie 响应模型"""
    data : Optional[CookieData] = None





