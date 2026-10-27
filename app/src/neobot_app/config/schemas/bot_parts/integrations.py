"""外部集成段：联网搜索、B 站与语音识别配置。"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class WebSearchConfig:
    """联网搜索工具包配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用联网搜索工具包；关闭后搜索工具不会注册"},
    )
    preview_pages_limit: Optional[int] = field(
        default=30,
        metadata={"description": "单次搜索返回结果总数上限（含主查询+所有变体），默认 30"},
    )
    max_search_rounds: Optional[int] = field(
        default=5,
        metadata={"description": "单次会话最多搜索轮次，默认 5"},
    )
    variant_result_limit: Optional[int] = field(
        default=6,
        metadata={"description": "研究模式中每个变体查询返回的最大结果数，默认 6"},
    )
    engines: Optional[List[str]] = field(
        default_factory=lambda: ["bing", "duckduckgo"],
        metadata={
            "description": (
                "搜索引擎与回退顺序（fix(9)）。默认 [\"bing\", \"duckduckgo\"]；"
                "duckduckgo 始终作为最后兜底执行，排在浏览器通道之后。"
                "这两个引擎都无需申请 Key，所以出厂即可用"
            )
        },
    )
    browser_fallback: bool = field(
        default=True,
        metadata={
            "description": (
                "HTTP 引擎都失败后是否再用浏览器脚本化通道补救（默认开）。"
                "内容类失败（错配页）是身份/缓存问题，换浏览器比换站点有效。"
            )
        },
    )
    browser_timeout_seconds: Optional[float] = field(
        default=8.0,
        metadata={"description": "浏览器检索通道单次预算（秒），默认 8（实测单次约 1s）"},
    )
    engine_timeout_seconds: Optional[Dict[str, float]] = field(
        default=None,
        metadata={
            "description": (
                "按引擎覆盖单级预算（秒），例如 {\"duckduckgo\": 15}。"
                "不填时 duckduckgo 用 15s（部署实测它慢）。"
            )
        },
    )
    deepseek_enabled: bool = field(
        default=True,
        metadata={
            "description": (
                "是否允许 DeepSeek 搜索（默认开启）。auto 默认优先 DeepSeek；"
                "只有显式指定 engine=bing/duckduckgo、缺少 DeepSeek_APIKey、"
                "或本项为 false 时才走免费链路。Key 复用 env 的 DeepSeek_APIKey。"
            )
        },
    )
    deepseek_timeout_seconds: float = field(
        default=20.0,
        metadata={"description": "DeepSeek Search 单次请求超时（秒）"},
    )
    deepseek_quota_cooldown_seconds: int = field(
        default=300,
        metadata={"description": "DeepSeek 额度不足/Key 失效后隐藏多久（秒，默认 5 分钟）"},
    )


@dataclass
class Bilibili:
    """B 站功能配置（默认开启；未登录等同关闭）。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "B站功能总开关；未登录时自动休眠，等同于关闭"},
    )
    poll_interval_seconds: int = field(
        default=1800,
        metadata={"description": "评论/私信轮询间隔（秒），默认 1800（30 分钟）"},
    )
    comment_reply_enabled: bool = field(
        default=False,
        metadata={"description": "是否自动回复B站评论/@（默认关闭，避免不可控的回复与 API 费用）"},
    )
    private_message_enabled: bool = field(
        default=False,
        metadata={"description": "是否自动回复B站私信（默认关闭）"},
    )
    login_timeout_seconds: int = field(
        default=180,
        metadata={"description": "二维码登录等待超时（秒）"},
    )
    max_replies_per_poll: int = field(
        default=50,
        metadata={"description": "每轮最多回复多少条（积压会进入回复池，下一轮继续）"},
    )
    reply_cooldown_seconds: float = field(
        default=60.0,
        metadata={"description": "同一会话两次回复之间的最小间隔（秒）"},
    )
    dynamic_diary_enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 B 站动态日记（每日摘要并发布，默认关闭）"},
    )
    dynamic_diary_time: str = field(
        default="22:30",
        metadata={"description": "每日动态日记的 summary 启动时间 HH:MM；summary 完成后等待 30 分钟再生成日记"},
    )
    dynamic_diary_requirement: str = field(
        default="",
        metadata={
            "description": "额外日记要求；留空使用默认 COT/隐私规则。支持多行，写入日记 agent 的 <日记要求>"
        },
    )
    cookie_file: str = field(
        default="data/bilibili/cookies.json",
        metadata={"description": "B站登录 cookie 保存路径（相对数据目录）"},
    )
    live_interaction_cooldown_seconds: float = field(
        default=5.0,
        metadata={"description": "直播间自动回复同房间冷却（秒）；所有弹幕都会触发回复，节流只靠这一项"},
    )
    live_interaction_max_reply_chars: int = field(
        default=20,
        metadata={"description": "直播间弹幕回复最大字符数"},
    )
    live_interaction_at_only: bool = field(
        default=True,
        metadata={"description": "已废弃：现在所有非空弹幕都会触发回复，节流由 live_interaction_cooldown_seconds 控制"},
    )
    live_interaction_mention_names: Optional[List[str]] = field(
        default_factory=list,
        metadata={
            "description": (
                "直播间 @ 识别额外名单（B站昵称/曾用名等）；会自动加入 B站登录账号 uname，"
                "用于把含 @ 的弹幕识别为对 bot 的提及。"
            )
        },
    )
    live_interaction_asr_enabled: bool = field(
        default=False,
        metadata={
            "description": (
                "直播间自动 ASR 上下文默认值（默认关闭）。大部分情况下效果不好，"
                "尤其是带有较大 BGM、多人说话或音质较差的场景；建议按需用 /直播ASR 单独打开。"
            )
        },
    )
    live_interaction_auto_look_enabled: bool = field(
        default=False,
        metadata={
            "description": "是否定时主动看一眼直播间画面并发一条弹幕（默认关闭）"
        },
    )
    live_interaction_auto_look_interval_minutes: int = field(
        default=30,
        metadata={"description": "主动观察间隔（分钟，最小 5）"},
    )
    live_interaction_summary_every: int = field(
        default=200,
        metadata={
            "description": "直播间弹幕自动总结间隔（条）；每累计这么多条自动压缩到 group_summary（key 带 bilibili_live:room: 前缀），0 关闭"
        },
    )
    live_interaction_screenshot_replies: bool = field(
        default=False,
        metadata={
            "description": "是否把每条自动回复时的直播画面截图保存到数据目录（默认关闭）"
        },
    )
    live_interaction_reply_chance: float = field(
        default=0.15,
        metadata={
            "description": (
                "直播间普通弹幕的基础回复概率（0-1）；被@/叫名字仍按 at_mention_guaranteed_reply 必回。"
                "默认 0.15，最终概率还会乘群聊/会话/用户意愿系数。"
            )
        },
    )
    live_event_notify_targets: Optional[List[str]] = field(
        default_factory=list,
        metadata={
            "description": (
                "直播事件推送到 QQ 的目标列表，格式 group:群号 / private:QQ号；"
                "留空表示不推送。默认只推礼物/SC/上舰。"
            )
        },
    )
    live_event_notify_kinds: Optional[List[str]] = field(
        default_factory=lambda: ["gift", "super_chat", "guard"],
        metadata={"description": "允许推送到 QQ 的直播事件类型：gift/super_chat/guard/enter/danmaku"},
    )


@dataclass
class ASR:
    """语音识别配置（硅基流动 OpenAI 兼容接口）。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用外部 ASR（默认开启；实际调用受各功能开关控制）"},
    )
    provider: str = field(
        default="siliconflow",
        metadata={"description": "ASR 供应商：siliconflow / openai_compatible"},
    )
    model: str = field(
        default="XingChenAGI/XingChenASR-V3.2-Ultra",
        metadata={"description": "ASR 模型 ID（硅基流动免费模型）"},
    )
    base_url: str = field(
        default="",
        metadata={"description": "API Base URL；留空使用 env 的 SiliconFlow_URL"},
    )
    api_key: str = field(
        default="",
        metadata={"description": "API Key；留空使用 env 的 SiliconFlow_APIKey"},
    )
    language: str = field(
        default="zh",
        metadata={"description": "识别语言提示"},
    )
    timeout_seconds: int = field(
        default=120,
        metadata={"description": "单次转写超时（秒）"},
    )
    max_audio_mb: int = field(
        default=50,
        metadata={"description": "上传音频大小上限（MB，供应商限制 50MB/1 小时）"},
    )
