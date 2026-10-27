"""语音合成段：TTS 参考音频、火山引擎音色与 TTS 总配置。"""

from dataclasses import dataclass, field


@dataclass
class TTSReferenceVoice:
    """TTS 参考音频上传配置（仅硅基流动TTS）。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用参考音频上传"},
    )
    audio_file: str = field(
        default="./data/tts/reference.mp3",
        metadata={"description": "参考音频文件路径"},
    )
    custom_name: str = field(
        default="neo-default-voice",
        metadata={"description": "上传到平台后的声音名称"},
    )
    reference_text: str = field(
        default="慢工出细活，再给我两分钟，你马上就能见识到超梦分析的厉害了",
        metadata={"description": "参考音频对应文本"},
    )
    disable_tts_on_upload_failure: bool = field(
        default=True,
        metadata={"description": "参考音频上传失败时是否自动禁用TTS"},
    )


@dataclass
class HuoShanTTS:
    """火山引擎 TTS 配置。"""

    speaker_id: str = field(
        default="zh_female_shuangkuaisisi_moon_bigtts",
        metadata={"description": "发音人音色ID，见火山引擎音色列表"},
    )
    resource_id: str = field(
        default="seed-icl-2.0",
        metadata={"description": "API资源ID，决定模型版本与计费：seed-icl-2.0（声音复刻2.0） / seed-icl-1.0（声音复刻1.0） / seed-tts-2.0（语音合成2.0） / seed-tts-1.0（语音合成1.0）"},
    )
    model: str = field(
        default="seed-tts-2.0-expressive",
        metadata={
            "description": "模型版本：seed-tts-2.0-expressive（表现力强） / seed-tts-2.0-standard（更稳定） / seed-tts-1.1（音质提升）"
        },
    )
    format: str = field(
        default="mp3",
        metadata={"description": "音频编码格式：mp3 / ogg_opus / pcm"},
    )
    sample_rate: int = field(
        default=24000,
        metadata={"description": "音频采样率：8000/16000/22050/24000/32000/44100/48000"},
    )
    uid: str = field(
        default="neo-bot-user",
        metadata={"description": "用户标识uid，用于火山引擎侧请求追踪，自定义即可，不明白可以不改"},
    )


@dataclass
class TTS:
    """TTS 功能配置。"""

    enabled: bool = field(
        default=False,
        metadata={
            "description": "是否启用TTS功能；**默认关闭**：TTS 需要单独的语音模型与平台 Key，"
            "新用户先不启用，需要时在模型库里加好语音模型再打开"
        },
    )
    tts_provider: str = field(
        default="siliconflow",
        metadata={
            "description": "TTS提供商：siliconflow（硅基流动，默认） / volcengine（火山引擎）"
        },
    )
    response_format: str = field(
        default="mp3",
        metadata={"description": "TTS输出格式"},
    )
    stream: bool = field(
        default=True,
        metadata={"description": "是否使用流式语音生成（仅硅基流动TTS）"},
    )
    output_dir: str = field(
        default="./data/tts",
        metadata={"description": "生成语音文件保存目录"},
    )
    reference_voice: TTSReferenceVoice = field(default_factory=TTSReferenceVoice)
    huoshan: HuoShanTTS = field(default_factory=HuoShanTTS)
