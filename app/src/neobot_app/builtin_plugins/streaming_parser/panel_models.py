"""订阅向导的公开输入输出，页面不另行定义一份业务校验。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetInput(Input):
    target: str = Field(min_length=1, max_length=256, title="直播间或账号链接")


class GroupInput(Input):
    group_id: int = Field(gt=0, title="接收通知的群")


class GroupSettingsInput(GroupInput):
    model_config = ConfigDict(extra="forbid", strict=True)


class GroupSettingsUpdateInput(GroupSettingsInput):
    card_style: Literal["random", "sakura", "neon", "minimal"] = Field(
        title="通知卡片风格"
    )
    ai_reply_live: bool = Field(title="开播后触发 AI 回复")
    ai_reply_live_end: bool = Field(title="下播后触发 AI 回复")
    default_push_live: bool = Field(title="新订阅默认发送开播通知")
    default_push_live_end: bool = Field(title="新订阅默认发送下播通知")


class GroupSettings(GroupSettingsUpdateInput):
    inherited: bool = Field(title="尚未保存群设置，使用插件默认值")


class CreateInput(GroupInput, TargetInput):
    pass


class ListInput(Input):
    group_id: int | None = Field(default=None, gt=0, title="接收通知的群")


class SubscriptionInput(GroupInput):
    room_id: int = Field(gt=0, title="直播间号")


class ToggleInput(SubscriptionInput):
    push_live: bool = Field(title="开播推送")
    push_live_end: bool = Field(title="下播推送")


class GroupChoice(BaseModel):
    group_id: int = Field(title="接收群号")
    name: str = Field(title="群名称")
    bot_id: str = Field(title="机器人账号")


class Groups(BaseModel):
    items: list[GroupChoice] = Field(title="可选接收群")


class Target(BaseModel):
    room_id: int = Field(title="直播间号")
    uid: int = Field(title="UP 主 UID")
    short_id: int = Field(title="直播间短号")
    name: str = Field(title="主播")
    avatar_url: str = Field(title="主播头像")
    url: str = Field(title="直播间链接")


class SubscriptionItem(BaseModel):
    group_id: int = Field(title="接收群号")
    room_id: int = Field(title="直播间号")
    uid: int = Field(default=0, title="UP 主 UID")
    short_id: int = Field(default=0, title="直播间短号")
    name: str = Field(default="", title="主播")
    avatar_url: str = Field(default="", title="主播头像")
    push_live: bool = Field(default=True, title="开播通知")
    push_live_end: bool = Field(default=True, title="下播通知")
    live_status: int | None = Field(default=None, title="直播状态")
    checked_at: datetime | None = Field(default=None, title="最近检查时间")


class SubscriptionList(BaseModel):
    items: list[SubscriptionItem] = Field(title="订阅列表")


class Created(BaseModel):
    created: bool = Field(title="已添加新订阅")
    item: SubscriptionItem = Field(title="当前订阅")


class Changed(BaseModel):
    item: SubscriptionItem = Field(title="当前订阅")


class Removed(BaseModel):
    removed: bool = Field(title="已取消监听")


class Preview(BaseModel):
    target: Target = Field(title="识别结果")
    style: str = Field(title="通知卡片风格")
    html: str = Field(title="通知预览")
    fallback_text: str = Field(title="通知文字")


class Health(BaseModel):
    running: bool = Field(title="轮询运行中")
    subscriptions: int = Field(title="订阅数量")
    watched_rooms: int = Field(title="监听的直播间数")
    checked_at: datetime | None = Field(title="最近检查时间")
    success_at: datetime | None = Field(title="最近检查成功时间")
    checked: int = Field(title="本轮检查成功数")
    failed: int = Field(title="本轮检查失败数")
    error: str = Field(title="最近异常")
    message: str = Field(title="监听状态说明")


class Ready(BaseModel):
    completed: bool = Field(title="监听检查已完成")
    reason: str = Field(title="检查说明")
