"""网络地址工具。"""

from __future__ import annotations

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})


def is_loopback_host(host: str) -> bool:
    """判断监听地址是否仅限本机。

    用于「未配置鉴权 token 却对外监听」的启动告警：这类配置下同网段的任何
    主机都能连入并注入伪造事件。
    """
    normalized = str(host or "").strip().casefold()
    if normalized in _LOOPBACK_HOSTS:
        return True
    return normalized.startswith("127.")
