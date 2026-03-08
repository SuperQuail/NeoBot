from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EnvConfig:
    """环境变量配置"""
    # Adapter 配置
    NEO_BOT_ADAPTER_HOST: str = field(
        default='127.0.0.1',
        metadata={'description':'Adapter 监听地址'}
    )
    NEO_BOT_ADAPTER_PORT: int = field(
        default=8080,
        metadata={'description':'Adapter 监听端口'}
    )
