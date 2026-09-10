"""核心服务创建（DB、适配器、记忆、用户画像、意愿、提示词、表情包、TTS 等）"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository
from neobot_app.assembly.adapter import build_adapter
from neobot_app.assembly.memory import (
    build_archive_memory_service,
    build_image_analysis_service,
)
from neobot_app.audio import TTSService, VolcengineTTSService
from neobot_app.bot_detect import BotDetector
from neobot_app.config.schemas.env import EnvConfig
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import DATA_DIR
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.emoji.service import EmojiService
from neobot_app.image import ImageParseService
from neobot_app.observability.debug import DEFAULT_RETENTION_DAYS, DebugRecorder
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService
from neobot_app.core.file_server import FileServer
from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService


def build_debug_recorder(*, config: BotConfigSchema, logger: Any) -> Any:
    debug_cfg = getattr(config, "debug", None)
    if not getattr(debug_cfg, "enabled", False):
        return None
    return DebugRecorder(
        DATA_DIR / "debug" / "log",
        logger=logger,
        retention_days=int(
            getattr(debug_cfg, "retention_days", DEFAULT_RETENTION_DAYS)
        ),
    )


def build_context_recorder(*, config: BotConfigSchema, logger: Any) -> Any:
    """构建聊天上下文记录器(debug 模式):记录每次模型调用的完整上下文,保留最近 100 轮。"""
    if not getattr(getattr(config, "debug", None), "enabled", False):
        return None
    from neobot_app.observability.context_recorder import ContextRecorder

    return ContextRecorder(
        DATA_DIR / "debug" / "context",
        max_files=100,
        logger=logger,
    )


def build_message_queues(*, config: BotConfigSchema) -> tuple[Any, Any]:
    from neobot_app.message.queue import MessageQueue

    timestamp_interval_seconds = getattr(
        config.chat, "message_timestamp_interval_seconds", 300
    )
    poke_weight = getattr(config.chat, "poke_weight", 0.2)
    reaction_weight = getattr(config.chat, "reaction_weight", 0.2)
    forward_weight = getattr(config.chat, "forward_message_queue_weight", 2)
    bot_account = config.bot.account
    reply_blacklist = set(config.chat.reply_blacklist or [])

    group_queue = MessageQueue(
        max_size=config.chat.max_group_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
        bot_account=bot_account,
        reply_blacklist=reply_blacklist,
    )
    friend_queue = MessageQueue(
        max_size=config.chat.max_friend_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
        bot_account=bot_account,
        reply_blacklist=reply_blacklist,
    )
    return group_queue, friend_queue


def build_adapter_service(
    *, config: BotConfigSchema, logger: Any, debug_recorder: Any
) -> Any:
    return build_adapter(
        config=config,
        logger=logger,
        packet_callback=debug_recorder.record_packet if debug_recorder is not None else None,
    )


def build_memory_services(
    *,
    db_url: str,
    data_dir: Path,
    adapter: Any,
    config: BotConfigSchema,
    logger_factory: Any,
    clock: Any,
    group_queue: Any,
    friend_queue: Any,
    uow_factory: Any,
    prompt_store: Any = None,
) -> dict[str, Any]:
    """创建记忆、聊天流、用户画像、意愿等服务。"""
    memory = MemoryService(
        repository=InMemoryMemoryRepository(),
        logger=logger_factory.get_logger("memory"),
        clock=clock,
    )
    chat_stream = ChatStreamManager(
        adapter=adapter,
        uow_factory=uow_factory,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
    )
    archive_memory_service = build_archive_memory_service(
        uow_factory=uow_factory,
        logger=logger_factory.get_logger("app.archive_memory"),
    )
    profile_service = UserProfileService(
        adapter=adapter,
        uow_factory=uow_factory,
        config=config,
        logger=logger_factory.get_logger("app.user_profiles"),
        archive_memory_service=archive_memory_service,
    )
    bot_detector = BotDetector(adapter)
    willing_service = WillingService(
        config=config,
        logger=logger_factory.get_logger("app.willing"),
        bot_detector=bot_detector,
    )

    adaptive_prompt_enabled = (
        getattr(getattr(config.agent, "memory", None), "adaptive_prompt_enabled", True)
    )
    prompt_builder = PromptBuilder(
        config=config,
        profile_service=profile_service,
        logger=logger_factory.get_logger("app.prompt"),
        archive_memory_service=archive_memory_service,
        adaptive_prompt_path=(
            data_dir / "自适应提示词.txt" if adaptive_prompt_enabled else None
        ),
        uow_factory=uow_factory,
        prompt_store=prompt_store,
    )
    return {
        "memory": memory,
        "chat_stream": chat_stream,
        "archive_memory_service": archive_memory_service,
        "profile_service": profile_service,
        "bot_detector": bot_detector,
        "willing_service": willing_service,
        "prompt_builder": prompt_builder,
    }


def build_emoji_service(
    *,
    config: BotConfigSchema,
    data_dir: Path,
    uow_factory: Any,
    vision_provider: Any,
    logger_factory: Any,
) -> EmojiService:
    emoji_page_size = getattr(getattr(config, "chat", None), "emoji_page_size", 50) or 50
    return EmojiService(
        data_dir=data_dir,
        uow_factory=uow_factory,
        vision_provider=vision_provider,
        page_size=emoji_page_size,
        logger=logger_factory.get_logger("app.emoji"),
    )


def resolve_tts_model_name(config: BotConfigSchema) -> str:
    """TTS 引用的模型 key（找不到时回退到旧角色名）。"""
    assignments = getattr(getattr(config, "models", None), "assignments", None)
    key = str(getattr(assignments, "tts_model", "") or "").strip() if assignments else ""
    models = getattr(config, "models", None)
    if key and models is not None and hasattr(models, "get") and models.get(key) is not None:
        return key
    return "tts_model"


def build_tts_service(*, config: BotConfigSchema, logger_factory: Any) -> Any:
    if not config.tts.enabled:
        return None

    provider = config.tts.tts_provider.strip().casefold()
    tts_logger = logger_factory.get_logger("app.tts")

    if provider == "volcengine":
        api_config = EnvConfig.get_api_platform_config("HuoShan")
        api_key = api_config.api_key
        if not api_key:
            tts_logger.error("火山引擎 TTS 缺少 HuoShan_APIKey 环境变量，TTS 已禁用")
            return None
        app_id = EnvConfig._get_env_value("HuoShan_AppId") or ""
        tts_logger.info(
            f"TTS 提供商: 火山引擎 (Volcengine) - {'旧版控制台鉴权' if app_id else '新版控制台鉴权'}"
        )
        return VolcengineTTSService(
            config=config.tts,
            api_key=api_key,
            app_id=app_id,
            logger=tts_logger,
        )

    if provider != "siliconflow":
        tts_logger.warning(f"未知的 tts_provider '{provider}'，回退到硅基流动 TTS")
    from neobot_chat import get_model_registry
    tts_model_name = resolve_tts_model_name(config)
    if tts_model_name not in get_model_registry().names:
        tts_logger.error(
            f"TTS 模型未注册（{tts_model_name}：检查 [models.assignments].tts_model 与平台 APIKey），TTS 已禁用"
        )
        return None
    tts_logger.info(f"TTS 提供商: 硅基流动 (SiliconFlow)，模型 {tts_model_name}")
    return TTSService(config=config.tts, logger=tts_logger, model_name=tts_model_name)


def build_image_parse_service(
    *,
    vision_provider: Any,
    adapter: Any,
    uow_factory: Any,
    logger_factory: Any,
    native_vision_provider: Any = None,
) -> ImageParseService:
    image_analysis_service = build_image_analysis_service(
        uow_factory=uow_factory,
        logger=logger_factory.get_logger("app.image_analysis"),
    )
    return ImageParseService(
        vision_provider=vision_provider,
        image_analysis_service=image_analysis_service,
        adapter=adapter,
        logger=logger_factory.get_logger("app.image_parse"),
        native_vision_provider=native_vision_provider,
    )


def _resolve_under_data_dir(raw: str, data_dir: Path) -> Path:
    """解析相对 data 目录的路径;容忍已包含 data 根的 './data/xxx' 写法。"""
    path = Path(raw)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] in ("data", "Data", "DATA"):
        path = Path(*parts[1:])
    return data_dir / path


def resolve_vision_detect_paths(*, config: Any, data_dir: Path) -> tuple[Path, Path]:
    """解析视觉检测配置中的相对路径(data 目录下的相对路径)。"""
    cfg = getattr(getattr(config, "agent", None), "vision_detect", None)
    models_dir = Path(cfg.models_dir) if cfg else Path("./vision_detect/models")
    index_file = Path(cfg.index_file) if cfg else Path("./vision_detect/models.toml")
    return (
        _resolve_under_data_dir(str(models_dir), data_dir),
        _resolve_under_data_dir(str(index_file), data_dir),
    )


def build_vision_detect_service(
    *,
    config: Any,
    data_dir: Path,
    logger_factory: Any,
) -> Any:
    """创建本地视觉检测服务(YOLO)。

    双推理栈:.onnx 走 onnxruntime(默认);onnxruntime 不可用(如虚拟机
    未透传 CPU 指令集导致 DLL 加载失败)时,.pt 模型走 PyTorch/ultralytics。
    两者均未就绪时返回服务但 skill 不注册,bot 可正常运行。
    """
    cfg = getattr(getattr(config, "agent", None), "vision_detect", None)
    if cfg is None or not cfg.enabled:
        return None
    from neobot_app.vision_detect.service import VisionDetectService

    logger = logger_factory.get_logger("app.vision_detect")
    models_dir, index_file = resolve_vision_detect_paths(config=config, data_dir=data_dir)
    service = VisionDetectService(
        models_dir,
        index_file,
        default_conf=cfg.default_conf,
        default_iou=cfg.default_iou,
        imgsz=cfg.imgsz,
        auto_refresh=cfg.auto_refresh,
        logger=logger,
    )
    if not service.onnx_available:
        if service.torch_available:
            logger.warning("onnxruntime 不可用,已切换 PyTorch 备选推理栈(.pt 模型)")
        else:
            logger.warning(
                "onnxruntime 不可用且 PyTorch 未安装:本地视觉检测暂不可用。"
                "onnx 环境无需处理;不可用环境请运行 `neobot init` 安装 ultralytics "
                "备选推理栈,并将 .pt 模型放入模型目录"
            )
        return service
    try:
        report = service.refresh()
        logger.info(f"视觉检测模型库: {report.summary()}")
    except Exception as exc:
        logger.warning(f"视觉检测模型库初始化扫描失败: {exc}")
    return service


def build_archive_summary_service(
    *,
    config: BotConfigSchema,
    archive_memory_service: Any,
    provider: Any,
    fallback_provider: Any,
    logger_factory: Any,
    skill_manager: Any,
    freeze_service: Any = None,
) -> ArchiveMemoryAutoSummaryService:
    from neobot_app.bootstrap._providers import build_optional_agent_provider

    # 必须用 get_skill_tools 取"带 skill 前缀"的定义(archive_crud__save_archive 等),
    # 否则工具名缺少前缀,skill_manager.execute 无法路由,模型每次调用都失败。
    summary_tool_defs: list[dict] = []
    summary_tool_defs.extend(skill_manager.get_skill_tools("archive_crud"))
    summary_tool_defs.extend(skill_manager.get_skill_tools("favorability"))

    async def _summary_tool_executor(tool_name: str, args: dict) -> str:
        return await skill_manager.execute(tool_name, args)

    return ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive_memory_service,
        provider=build_optional_agent_provider(
            config=config,
            agent_name="archive_summary",
            fallback_provider=fallback_provider,
            logger=logger_factory.get_logger("app.provider"),
        ),
        config=config,
        item_archive_config=getattr(
            getattr(getattr(config, "agent", None), "memory", None), "item_archive", None
        ),
        logger=logger_factory.get_logger("app.archive_summary"),
        tool_definitions=summary_tool_defs,
        tool_executor=_summary_tool_executor,
        freeze_service=freeze_service,
    )


def build_file_server(*, config: BotConfigSchema, data_dir: Path) -> FileServer:
    return FileServer(
        data_dir,
        port=config.file_server.port,
        host=config.file_server.host,
        public_url=config.file_server.public_url,
        enabled=config.file_server.enabled,
    )
