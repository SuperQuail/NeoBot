import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ApiPlatformConfig:
    """API 平台访问配置。"""

    name: str
    url: Optional[str] = None
    api_key: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        """URL 与 Key 都存在时返回 True。"""
        return bool(self.url and self.api_key)


@dataclass
class EnvConfig:
    """环境变量配置。"""

    PLATFORM_NAME_ALIASES = {
        "siliconflow": "SiliconFlow",
        "硅基流动": "SiliconFlow",
        "deepseek": "DeepSeek",
    }


    deepseek_url: str = field(
        default="https://api.deepseek.com",
        metadata={
            "env_key": "DeepSeek_URL",
            "description": "DeepSeek 平台 API URL",
            "comment_lines": [
                "提示：由于参数接受格式问题，使用 DeepSeek 官方源时请将平台名填写为 DeepSeek，以保证使用时不出错",
                "支持自定义平台名，任意名字配合 _URL 与 _APIKey 都可以被读取",
            ],
        },
    )
    deepseek_api_key: str = field(
        default="",
        metadata={
            "env_key": "DeepSeek_APIKey",
            "description": "DeepSeek 平台 API Key",
            "comment_lines": [
                "提示：由于参数接受格式问题，使用 DeepSeek 官方源时请将平台名填写为 DeepSeek，以保证使用时不出错",
                "支持自定义平台名，任意名字配合 _URL 与 _APIKey 都可以被读取",
            ],
        },
    )
    siliconflow_url: str = field(
        default="https://api.siliconflow.cn/v1",
        metadata={
            "env_key": "SiliconFlow_URL",
            "description": "硅基流动平台 API URL",
            "comment_lines": [
                "使用硅基流动平台时请将模型供应商填写为 SiliconFlow",
                "支持自定义平台名，任意名字配合 _URL 与 _APIKey 都可以被读取",
            ],
        },
    )
    siliconflow_api_key: str = field(
        default="",
        metadata={
            "env_key": "SiliconFlow_APIKey",
            "description": "硅基流动平台 API Key",
            "comment_lines": [
                "使用硅基流动平台时请将模型供应商填写为 SiliconFlow",
                "支持自定义平台名，任意名字配合 _URL 与 _APIKey 都可以被读取",
            ],
        },
    )
    huoshan_api_key: str = field(
        default="",
        metadata={
            "env_key": "HuoShan_APIKey",
            "description": "火山引擎 TTS Access Token（旧版控制台），在火山引擎语音技术控制台获取",
            "comment_lines": [
                "火山引擎语音技术控制台显示的 Access Token，对应 HTTP Header 中的 X-Api-Access-Key",
                "新版控制台可将 Access Token 填入此字段作为 X-Api-Key 使用",
            ],
        },
    )
    huoshan_app_id: str = field(
        default="",
        metadata={
            "env_key": "HuoShan_AppId",
            "description": "火山引擎 TTS App ID（旧版控制台），配合 Access Token 使用",
            "comment_lines": [
                "旧版控制台需要同时填写 App ID 和 Access Token，新版控制台只需 Access Token",
            ],
        },
    )

    @staticmethod
    def _get_env_value(env_key: str) -> Optional[str]:
        target = env_key.casefold()
        for key, value in os.environ.items():
            if key.casefold() == target:
                return value
        return None

    @classmethod
    def _normalize_platform_name(cls, platform_name: str) -> str:
        stripped = platform_name.strip()
        if not stripped:
            raise ValueError("platform_name 不能为空")
        return cls.PLATFORM_NAME_ALIASES.get(stripped.casefold(), stripped)

    @classmethod
    def get_api_platform_config(cls, platform_name: str) -> ApiPlatformConfig:
        """根据平台名读取 `<平台名>_URL` 与 `<平台名>_APIKey`。"""
        normalized_name = cls._normalize_platform_name(platform_name)

        return ApiPlatformConfig(
            name=normalized_name,
            url=cls._get_env_value(f"{normalized_name}_URL"),
            api_key=cls._get_env_value(f"{normalized_name}_APIKey"),
        )

    @classmethod
    def get_api_platform_url(cls, platform_name: str) -> Optional[str]:
        """根据平台名读取 URL。"""
        return cls.get_api_platform_config(platform_name).url

    @classmethod
    def get_api_platform_key(cls, platform_name: str) -> Optional[str]:
        """根据平台名读取 API Key。"""
        return cls.get_api_platform_config(platform_name).api_key
