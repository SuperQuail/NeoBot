"""内容创作段：图库、表情包、后台绘图、视觉检测与头像存储配置。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GalleryConfig:
    """图库配置。"""

    capacity: Optional[int] = field(
        default=10,
        metadata={"description": "图库容量上限；为0时禁用图库管理工具"},
    )
    page_size: Optional[int] = field(
        default=50,
        metadata={"description": "图库列表每页显示数量；图片总数超过此值时分页展示"},
    )


@dataclass
class CreatorEmojiConfig:
    """表情包管理配置。"""

    allow_add: Optional[bool] = field(
        default=True,
        metadata={"description": "是否允许 Creator Agent 增加表情包（默认允许）"},
    )
    allow_delete: Optional[bool] = field(
        default=True,
        metadata={"description": "是否允许 Creator Agent 删除表情包（默认允许）"},
    )
    page_size: int = field(
        default=50,
        metadata={"description": "表情包列表每页显示数量；总数超过此值时分页展示"},
    )


@dataclass
class BackgroundDrawConfig:
    """后台绘图配置。"""

    background_enabled: Optional[bool] = field(
        default=True,
        metadata={"description": "是否启用后台绘图；关闭则回退到同步阻塞模式"},
    )
    cooldown_seconds: Optional[int] = field(
        default=60,
        metadata={"description": "绘图冷却秒数；同一管线上次绘图开始后此时间内不可再次提交"},
    )
    notification_retry_seconds: Optional[int] = field(
        default=30,
        metadata={"description": "绘图完成后通知主Agent，若无回应此秒数后重试"},
    )
    max_retries: Optional[int] = field(
        default=1,
        metadata={"description": "通知最大重试次数（不含首次）；默认1表示首次通知后重试1次"},
    )
    startup_grace_seconds: Optional[float] = field(
        default=3.0,
        metadata={"description": "后台绘图启动宽限期（秒）；此时间内若API报错则立即返回失败并取消冷却"},
    )
    max_tasks_per_pipeline: Optional[int] = field(
        default=20,
        metadata={"description": "每个聊天流最多保留的后台绘图任务数；超出后自动销毁最旧的非活跃任务"},
    )


@dataclass
class ImageCreationConfig:
    """图像创作配置（生图、图库、表情包）。"""

    enabled: bool = field(
        default=True,
        metadata={
            "description": "是否启用图像创作功能（图库 / 表情包增删 / AI 绘图）；"
            "默认开启：表情包管理开箱可用，AI 绘图另需分配 creator_image_models"
        },
    )
    gallery: GalleryConfig = field(default_factory=GalleryConfig)
    emoji: CreatorEmojiConfig = field(default_factory=CreatorEmojiConfig)
    drawing: BackgroundDrawConfig = field(default_factory=BackgroundDrawConfig)
    image_inspect_enabled: bool = field(
        default=False,
        metadata={
            "description": "是否启用生图检查工具 inspect_image（需视觉模型支持）；"
            "关闭时工具不注册不注入提示词，开启后动态注入"
        },
    )


@dataclass
class VisionDetect:
    """本地视觉检测(ONNX/YOLO)配置。

    模型文件放入 models_dir 目录(每个 .onnx 一个模型),程序自动维护
    index_file 索引骨架(models.toml),用户只需在索引中填写每个模型的
    id/name/description,AI 即可依据 description 主动选择模型。
    运行 `neobot init` 可随时重新扫描模型目录。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用本地视觉检测服务；关闭后 skill 不注册"},
    )
    models_dir: str = field(
        default="./data/vision_detect/models",
        metadata={"description": "ONNX 模型文件目录（相对 data 目录）"},
    )
    index_file: str = field(
        default="./data/vision_detect/models.toml",
        metadata={"description": "模型索引文件（相对 data 目录，程序自动生成骨架）"},
    )
    default_conf: float = field(
        default=0.35,
        metadata={"description": "默认置信度阈值（0.0-1.0），仅作为 models.toml [library] 段首次生成的初始值；运行期以 models.toml 中的配置为准"},
    )
    default_iou: float = field(
        default=0.45,
        metadata={"description": "默认 NMS IoU 阈值，仅作为 models.toml [library] 段首次生成的初始值"},
    )
    imgsz: int = field(
        default=0,
        metadata={"description": "默认输入尺寸（0 = 从模型自动推断），仅作为 models.toml [library] 段首次生成的初始值"},
    )
    auto_refresh: bool = field(
        default=True,
        metadata={"description": "每次调用前检查模型目录/索引变化并热重载"},
    )


@dataclass
class AvatarsConfig:
    """本体级用户头像存储（spec(5) §4.9 / R33–R37）。"""

    enabled: bool = field(
        default=True,
        metadata={
            "description": "是否启用用户头像的本地存储与惰性刷新；关闭后不做过期判定、"
            "不发起下载，已有头像仍可被卡片读取",
        },
    )
    refresh_days: int = field(
        default=7,
        metadata={
            "description": "头像过期天数：用户再次出现在聊天流且距上次获取超过该天数"
            "才重新获取；未过期零网络开销",
        },
    )
    fail_cooldown_seconds: int = field(
        default=600,
        metadata={
            "description": "下载失败后的冷却秒数：冷却期内该用户再次发言不重试，"
            "避免把一次失败放大成网络风暴",
        },
    )
    max_concurrent: int = field(
        default=2,
        metadata={
            "description": "头像下载的全局并发上限；超限的触发直接丢弃，该用户下次出现时自然重试",
        },
    )
    max_bytes: int = field(
        default=524288,
        metadata={
            "description": "单张头像的字节上限（默认 512 KiB）；超出不落盘并按获取失败处理",
        },
    )
    keep_days: int = field(
        default=90,
        metadata={
            "description": "长期未活跃用户的头像保留天数；超期清理文件并清空对应表字段",
        },
    )
