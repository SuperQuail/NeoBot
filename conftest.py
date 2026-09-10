"""仓库级 pytest 配置。

本机开启系统代理（Clash 等）时，`urllib.request.getproxies()` 会返回系统代理，
httpx 默认 `trust_env=True` 会把它应用到**所有**地址——包括测试里刚启动的
127.0.0.1 本地服务，导致请求被代理转发并返回 502。测试一律绕过代理。
"""

from __future__ import annotations

import os

# NO_PROXY=* 会让 urllib/httpx 完全忽略系统与环境代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for _name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(_name, None)
