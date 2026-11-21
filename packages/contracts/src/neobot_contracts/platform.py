"""跨实现的平台身份常量。

QQ 官方机器人适配器与本体共享同一个 app_name 标记：本体在连接建立后调用
get_version_info 判定通道，适配器在实现里原样返回这个常量，避免两边各写一份
字符串后漂移。
"""

from __future__ import annotations

#: QQ 官方机器人适配器在 get_version_info.data.app_name 中上报的标识。
OFFICIAL_ADAPTER_APP_NAME = "NeoBot-QQOfficial"
