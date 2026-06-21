"""B站交互模块 — 评论/私信监控、提示词组装、Event Bridge。

与 QQ 通道并行运行，共享记忆系统和 ReplyOrchestrator 回复管线。
"""

from __future__ import annotations

from loguru import logger
from dataclasses import dataclass
from typing import Optional



@dataclass
class BilibiliModule:
    """B站模块容器，持有所有 B站组件的引用。"""

    client: "BilibiliClient"
    cookie_provider: "BilibiliCookieProvider"
    private_monitor: "BilibiliPrivateMonitor"
    comment_monitor: "BilibiliCommentMonitor"
    event_bridge: "BilibiliEventBridge"


def build_bilibili_module(
    config,
    *,
    browser_data_dir: str = "",
    logger_factory=None,
    orchestrator=None,
    prompt_builder=None,
) -> Optional[BilibiliModule]:
    """一站式构建 B站模块。

    如果 cookie 提取失败则返回 None，调用方应将 config.bilibili.enabled 设为 False。
    """
    from .cookie_provider import BilibiliCookieProvider
    from .client import BilibiliClient
    from .private_monitor import BilibiliPrivateMonitor
    from .comment_monitor import BilibiliCommentMonitor
    from .event_bridge import BilibiliEventBridge

    provider = BilibiliCookieProvider(browser_data_dir)
    sd, jct = provider.load_credentials()
    if not sd or not jct:
        logger.warning("B站模块: 未提取到 B站 cookie")
        return None

    uid = provider.load_dedeuserid() or 0
    client = BilibiliClient(sd, jct, uid)
    if not client.verify_auth():
        logger.warning("B站模块: cookie 已失效")
        return None

    logger.info("B站模块: 认证成功 (UID={})", uid)

    bridge = BilibiliEventBridge(
        orchestrator=orchestrator,
        prompt_builder=prompt_builder,
        client=client,
        config=config,
    )

    private_monitor = BilibiliPrivateMonitor(
        client=client,
        config=config,
        bridge=bridge,
    )

    comment_monitor = BilibiliCommentMonitor(
        client=client,
        config=config,
        bridge=bridge,
    )

    return BilibiliModule(
        client=client,
        cookie_provider=provider,
        private_monitor=private_monitor,
        comment_monitor=comment_monitor,
        event_bridge=bridge,
    )
