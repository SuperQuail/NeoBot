from enum import Enum
from typing import Optional, Union, List, Literal, ClassVar

from neobot_adapter.model.basic import PostMessageType, PostMessageMessagesender, PostMessageTempSource, PostMessageSubType
from pydantic import BaseModel
from neobot_adapter.model.gengeral import General

#文档:https://docs.go-cqhttp.org/cqcode/#%E5%90%88%E5%B9%B6%E8%BD%AC%E5%8F%91%E6%B6%88%E6%81%AF%E8%8A%82%E7%82%B9

class Flag(Enum):
    """Flag枚举类"""
    ON = 1
    OFF = 0

class MessageType(Enum):
    """message包含的字段类型"""
    text = "text" #文本
    face = "face" #表情
    record = "record" #语音
    video = "video" #视频
    at = "at" #@
    rps = "rps" #猜拳
    dicd = "dice" #骰子
    shake = "shake" #窗口抖动
    anonymous = "anonymous" #匿名
    share = "share" #分享
    contact = "contact" #推荐好友/群
    location = "location" #位置
    music = "music" #音乐
    image = "image" #图片
    reply = "reply" #回复
    redbag = "redbag" #红包
    poke = "poke" #戳一戳
    gift = "gift" #礼物
    forward = "forward" #合并转发
    node = "node" #合并转发消息节点
    xml = "xml" # XML
    json = "json" #JSON
    cardimage = "cardimage" #大图片
    tts = "tts" #TTS

class music_type(Enum):
    """音乐类型枚举类"""
    qq = "qq" #QQ音乐
    netease = "163" #网易云音乐
    xiami = "xm" #虾米音乐
    custom = "custom" #自定义分享

class image_type(Enum):
    """图片类型枚举类"""
    flash = "flash" #闪照
    show = "show" #秀图

class image_show_id(Enum):
    """秀图ID枚举类"""
    common = 4000 #普通
    phantom = 4001 #幻影
    shake = 4002 #抖动
    birthday = 4003 #生日
    love_you = 4004 #爱你
    looking_for_friend = 4005 #征友

class image_subtype(Enum):
    """图片子类型枚举类"""
    common = 0 #正常图片
    emoji = 1 #表情包
    hot_image = 2 #热图
    meme_battle = 3 #斗图
    smart_image = 4 #智图
    sticker = 7 #贴图
    selfie = 8 #自拍
    ad = 9# 广告
    wait_test = 10 #测试
    hot_search =13 #热搜

class gift_id(Enum):
    """礼物ID枚举类"""
    sweet_wink = 0 #甜wink
    cola = 1 #可乐
    lucky_bracelet = 2 #幸运手链
    cappuccino = 3 #卡布奇诺
    cat_watch = 4 #猫咪手表
    plush_gloves = 5 #绒绒手套
    rain_bow_candy = 6 #彩虹糖
    strong = 7 #坚强
    confession_microphone = 8 #告白话筒
    hold_your_hand = 9 #牵手
    cute_cat = 10 #可爱猫咪
    mystery_mask = 11 #神秘面具
    i_am_super_busy = 12 #我超忙的
    love_mask = 13 #爱心口罩

class Message(BaseModel):
    """消息结构"""
    class face(BaseModel):
        """表情结构 - 收/发"""
        type: Literal[MessageType.face] = MessageType.face
        class data(BaseModel):
            """表情数据结构"""
            id: Optional[int] = None

    class record(BaseModel):
        """语音结构 - 收/发"""
        type: Literal[MessageType.record] = MessageType.record
        class data(BaseModel):
            """语音数据结构"""
            file: Optional[str] = None #文件 URL
            magic: Optional[Flag] = 0 #启用变声
            url:  Optional[str] = None #文件 URL
            cache: Optional[Flag] = Flag.ON #是否启用缓存
            proxy: Optional[Flag] = Flag.ON #是否启用代理
            timeout: Optional[int] = None #请求超时时间

    class video(BaseModel):
        """视频结构 - 收/发 - 发送依赖 ffmpeg"""
        type: Literal[MessageType.video] = MessageType.video
        class data(BaseModel):
            """视频数据结构"""
            file: Optional[str] = None #文件 URL
            cover: Optional[str] = None #封面 URL
            c : Optional[int] = None #下载线程数 2/3 ,发送依赖 ffmpeg

    class at(BaseModel):
        """@结构 - 收/发"""
        type: Literal[MessageType.at] = MessageType.at
        class data(BaseModel):
            """@数据结构"""
            qq: Optional[int] = None
            name: Optional[str] = None

    class rps(BaseModel):
        """猜拳结构 - 不支持"""
        type: Literal[MessageType.rps] = MessageType.rps
        class data(BaseModel):
            """猜拳数据结构"""
            pass

    class dice(BaseModel):
        """骰子结构 - 不支持"""
        # type: Literal[MessageType.dice] = MessageType.dice
        # class data(BaseModel):
        #     """骰子数据结构"""
        #     pass

    class shake(BaseModel):
        """窗口抖动结构 - 不支持 - 发"""
        # type: Literal[MessageType.shake] = MessageType.shake
        # class data(BaseModel):
        #     """窗口抖动数据结构"""
        #     pass

    class anonymous(BaseModel):
        """匿名发消息结构 - 发"""
        type: Literal[MessageType.anonymous] = MessageType.anonymous
        class data(BaseModel):
            """匿名数据结构"""
            ignore: Optional[Flag] = Flag.OFF #无法匿名时是否继续发送

    class share(BaseModel):
        """链接分享结构 - 收/发"""
        type: Literal[MessageType.share] = MessageType.share
        class data(BaseModel):
            """分享数据结构"""
            url: str = '' #分享 URL
            title: Optional[str] = None #标题

    class contact(BaseModel):
        """推荐好友/群结构 - 不支持 - 收/发"""
        type: Literal[MessageType.contact] = MessageType.contact
        class data(BaseModel):
            """推荐好友/群数据结构"""
            id : Optional[int] = None

    class location(BaseModel):
        """位置结构 - 收/发 - 不支持"""
        type: Literal[MessageType.location] = MessageType.location
        class data(BaseModel):
            """位置数据结构"""
            lat: Optional[float] = None #纬度
            lon: Optional[float] = None #经度
            title: Optional[str] = None #标题
            content: Optional[str] = None #内容

    class music(BaseModel):
        """音乐分享/音乐自定义分享结构 - 发"""
        type: Literal[MessageType.music] = MessageType.music
        class data(BaseModel):
            """音乐数据结构"""
            type: Optional[music_type] = None #音乐来源
            """ID 分享"""
            id: Optional[int] = None #音乐 ID
            """URL 分享"""
            url: Optional[str] = None #跳转 URL
            audio: Optional[str] = None #音频 URL
            title: Optional[str] = None #标题
            content: Optional[str] = None #内容
            image: Optional[str] = None #图片 URL

    class image(BaseModel):
        """图片结构 - 收/发"""
        type: Literal[MessageType.image] = MessageType.image
        class data(BaseModel):
            """图片数据结构"""
            file:Optional[str] = None #图片文件名
            type:Optional[image_type] = None #图片类型
            subType:Optional[image_subtype] = None #图片子类型，只出现在群聊
            url: Optional[str] = None #图片 URL
            cache: Optional[Flag] = Flag.ON
            id : Optional[int] = None #秀图图片 ID
            c : Optional[int] = None #下载线程数 2/3
        # 发送时，file参数支持：
        #
        # 绝对路径，例如
        # File: // / C:\\Users\Alice\Pictures\1.png，格式使用file
        # URI
        # 网络URL，例如
        # https: // www.baidu.com / img / PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png
        # Base64编码，例如
        # base64: // iVBORw0KGgoAAAANSUhEUgAAABQAAAAVCAIAAADJt1n / AAAAKElEQVQ4EWPk5 + RmIBcwkasRpG9UM4mhNxpgowFGMARGEwnBIEJVAAAdBgBNAZf + QAAAAABJRU5ErkJggg ==
        # 图片最大不能超过30MB
        # PNG格式不会被压缩, JPG可能不会二次压缩, GIF非动图转成PNG
        # GIF动图原样发送(总帧数最大300张, 超过无法发出, 无论循不循环)

    class reply(BaseModel):
        """回复结构 - 收/发"""
        type: Literal[MessageType.reply] = MessageType.reply
        class data(BaseModel):
            """回复数据结构"""
            id: Optional[int] = None #回复消息 ID，必须为本群 ID
            text: Optional[str] = None #自定义回复内容，优先级比 id 引用高
            qq: Optional[int] = None #自定义回复时的自定义 QQ
            time: Optional[int] = None #自定义回复时的自定义时间，UNIX 时间格式
            seq: Optional[int] = None #起始消息序号，可通过 get_msg 获得

    class redbag(BaseModel):
        """红包结构 - 收"""
        type: Literal[MessageType.redbag] = MessageType.redbag
        class data(BaseModel):
            """红包数据结构"""
            title : Optional[str] = None #祝福语/口令

    class poke(BaseModel):
        """戳一戳结构 - 发 - 仅群聊"""
        type: Literal[MessageType.poke] = MessageType.poke
        class data(BaseModel):
            """戳一戳数据结构"""
            qq: Optional[int] = None #戳的 QQ 号

    class gift(BaseModel):
        """礼物结构 - 发"""
        type: Literal[MessageType.gift] = MessageType.gift
        class data(BaseModel):
            """礼物数据结构"""
            qq: Optional[int] = None #赠送的 QQ 号
            id: Optional[gift_id] = None #礼物 ID

    class forward(BaseModel):
        """合并转发结构 - 收"""
        type: Literal[MessageType.forward] = MessageType.forward
        class data(BaseModel):
            """合并转发数据结构"""
            id: Optional[str] = None #合并转发 id，需要通过/get_forward_msg API 获取转发的具体内容

    class node(BaseModel):
        """合并转发消息节点结构 - 发"""
        type: Literal[MessageType.node] = MessageType.node
        class data(BaseModel):
            """合并转发消息节点数据结构"""
            id: Optional[int] = None #转发消息 ID
            name: Optional[ str] = None #发送者显示昵称
            uin: Optional[int] = None #发送者 QQ
            content: Optional['Message'] = None #用于自定义消息，不支持转发套娃
            seq : Optional['Message'] = None #用于自定义消息
        """
        特殊说明: 需要使用单独的API /send_group_forward_msg 发送, 
        并且由于消息段较为复杂, 仅支持Array形式入参。 如果引用消息和自定义消息同时出现,
        实际查看顺序将取消息段顺序. 
        另外按 Onebot v11 文档说明, data 应全为字符串, 但由于需要接收message 类型的消息, 所以
        仅限此Type的content字段 支持Array套娃
        """

    class xml(BaseModel):
        """XML 结构 - 收/发"""
        type: Literal[MessageType.xml] = MessageType.xml
        class data(BaseModel):
            data : Optional[str] = None #XML 内容
            resid : Optional[str] = None #可能为空，或空字符串

    class json(BaseModel):
        """JSON 结构 - 收/发"""
        type: Literal[MessageType.json] = MessageType.json
        class data(BaseModel):
            data : Optional[str] = None #JSON 内容
            resid : Optional[int] = None #默认不填为 0, 走小程序通道，填了走富文本通道发送
            """json中的字符串需要进行转义 :
            ","=> &#44;
            "&"=> &amp;
            "["=> &#91;
            "]"=> &#93;"""

    class cardimage(BaseModel):
        """xml 大图片结构 - 发"""
        type: Literal[MessageType.cardimage] = MessageType.cardimage
        class data(BaseModel):
            file: Optional[str] = None #与 image 的 file 字段对齐，支持程度也相同
            minwidth : Optional[int] = None #默认不填为 400, 最小 width
            minheight : Optional[int] = None #默认不填为 400, 最小 height
            maxwidth : Optional[int] = None #默认不填为 500, 最大 width
            maxheight : Optional[int] = None #默认不填为 1000, 最大 height
            source : Optional[str] = None #分享来源的名称，可以留空
            icon : Optional[str] = None #分享来源的 icon 图标 url，可以留空

    class tts(BaseModel):
        """TTS 结构 - 发"""
        type: Literal[MessageType.tts] = MessageType.tts
        class data(BaseModel):
            text: Optional[str] = None #TTS 内容，音源与账号性别设置有关


    Segment: ClassVar = Union['face', 'text', 'image', 'reply', 'redbag', 'poke', 'gift', 'forward', 'node', 'xml', 'json', 'cardimage', 'tts']
    message: ClassVar = List[Segment]

Message.model_rebuild()

class MessageTypeEnum(Enum):
    """一个枚举，描述消息类型"""
    private = "private" #私聊消息
    group = "group" #群聊消息

class MessageSubType(Enum):
    """一个枚举，描述消息子类型"""
    group = "group" #群消息
    public = "public" #公开消息

class GeneralMessage(General):
    """上报消息数据结构"""
    message_type : Optional[MessageTypeEnum] = None #消息类型
    sub_type : Optional[PostMessageSubType] = None #消息子类型
    message_id : Optional[int] = None #消息 ID
    user_id : Optional[int] = None #发送者 QQ 号
    message : Optional[Message] = None #消息内容
    raw_message : Optional[str] = None #原始消息内容
    font : Optional[int] = None #字体
    sender : Optional[PostMessageMessagesender] = None

class PrivateMessage(GeneralMessage):
    """私聊消息数据结构"""
    target_id : Optional[int] = None #接收者 QQ 号
    temp_source : Optional[PostMessageTempSource] = None

class FastPrivateReplay(PrivateMessage):
    reply: Optional[Message] = None #回复内容
    auto_escape: Optional[bool] = True #是否自动转换 CQ 码，只在 replay 为字符串时起效

class Anonymous(BaseModel):
    """匿名信息结构"""
    id : Optional[int] = None #匿名用户 ID
    name : Optional[str] = None #匿名用户名称
    flag : Optional[str] = None #匿名用户 flag，用于调用禁言 API

class GroupMessage(GeneralMessage):
    """群消息数据结构"""
    group_id : Optional[int] = None #群号

class FastGroupReplay(GroupMessage):
    reply: Optional[Message] = None #回复内容
    auto_escape: Optional[bool] = True #是否自动转换 CQ 码，只在 replay 为字符串时起效
    at_sender: Optional[bool] = False #是否 at 发送者
    delete : Optional[bool] = False #是否撤回消息
    kick : Optional[bool] = False #是否踢出群
    ban : Optional[bool] = False #是否禁言 (对匿名用户同样有效)
    ban_duration : Optional[int] = 60 #禁言时长，单位秒
