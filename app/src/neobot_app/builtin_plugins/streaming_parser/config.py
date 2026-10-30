"""插件配置模型（字段与 plugin.toml 的 [config] 一一对应）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StreamConfig(BaseModel):
    """流媒体解析插件配置。"""

    # 轮询间隔（秒）。B 站开播检测的延迟上限基本等于该值。
    poll_interval_seconds: int = Field(
        default=60, ge=15, le=3600, title="检查间隔（秒）"
    )
    # 单次 HTTP 请求超时（秒）。
    request_timeout: float = Field(default=10.0, gt=0, le=60, title="请求超时（秒）")
    # B 站 Cookie 串，留空表示匿名请求。
    cookie: str = Field(default="", title="B 站 Cookie")
    # 自定义 User-Agent，留空用内置默认值。
    user_agent: str = Field(default="", title="浏览器标识（User-Agent）")
    # 并发轮询的房间数上限（避免一次性打爆接口）。
    poll_concurrency: int = Field(default=4, ge=1, le=16, title="同时检查的直播间数")
    # 默认卡片风格：random 表示每次随机挑一个，也可写死某个风格名。
    default_card_style: str = Field(default="random", title="默认通知卡片风格")
    # 新订阅的房间是否默认推送开播 / 下播。
    # 默认两个都开：/监听 一个直播间就自动建好上播与下播两条推送，
    # 不想要的可以用 /开播推送、/下播推送 单独关，或在这里改默认值。
    default_push_live: bool = Field(default=True, title="默认发送开播通知")
    default_push_live_end: bool = Field(default=True, title="默认发送下播通知")
    # 新群默认是否在推送卡片后触发一次 AI 回复（可按群用命令覆盖）。
    default_ai_reply_live: bool = Field(default=True, title="开播后触发 AI 回复")
    default_ai_reply_live_end: bool = Field(default=False, title="下播后触发 AI 回复")
    # 开播状态总览图最多显示多少个主播。
    overview_max_hosts: int = Field(
        default=30, ge=1, le=100, title="总览最多显示的主播数"
    )
    # 头像/封面本地缓存保留天数。
    asset_cache_days: int = Field(default=14, ge=0, le=365, title="图片缓存天数")
    # 渲染超时（秒）。
    render_timeout: float = Field(
        default=30.0, gt=0, le=120, title="卡片渲染超时（秒）"
    )
    # 卡片渲染缩放倍数（2 表示 2x 高清图）。
    render_scale: float = Field(default=2.0, ge=1.0, le=4.0, title="卡片清晰度倍数")
