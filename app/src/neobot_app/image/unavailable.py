"""拉不到的聊天图片：进程内登记表 + 过期文案。

为什么需要它
------------
带消息预热时队列里会灌入大量历史消息（`chat.enable_group_startup_history_warmup` /
`enable_friend_startup_history_warmup` / `chat.private_chat_dynamic_warmup`）。其中一部分图片的
设备侧聊天记录已经被清理（或图片过久被服务器回收），URL 直下与 OneBot `get_image` 两条路
都拿不到字节 —— 而且**永远不会**拿到。

原生视觉的默认加载（`ReplyVisionContext.refresh_defaults`）把「正文里显示过的最近 N 张图」
当作候选，每轮模型调用前都跑一次；只有**成功**加载的图片才进缓存，失败的下轮必然重来。
于是同一张拉不到的图会被反复拉：单张要烧满一个 30 秒窗口，默认一次 4 张，最坏一轮就是
120 秒级的纯等待 —— 正好等于群聊静默熔断阈值（`chat.group_agent_silent_timeout_seconds`
默认 120），用户侧表现为「Bot 收到消息后长时间不说话」。

登记表把「这张图拉不到」记在**本次运行**里：命中后直接失败返回，一个网络请求都不发。
进程重启即清空（设备侧补回历史记录后，重启一次就能重新尝试）。

引用键
------
优先 OneBot `file`（历史消息里稳定），其次 `url`，兜底 `message_id:image_index`。
内联内容（`base64://` / `data:`）不算引用：它们不依赖网络，也不存在「过期」。
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional

#: 独立成句的过期说明（工具结果用）
EXPIRED_NOTICE = "图片已过期，无法获取（可能原因：清理过历史聊天记录 / 时间太久）"
#: 塞进 `[图片：…]` 占位文本的形式（正文 / 聊天记录用）
EXPIRED_INLINE = "已过期，无法获取（可能原因：清理过历史聊天记录 / 时间太久）"
#: 过期判定标记：调用方拿到的错误串里含它就按「已过期」渲染
EXPIRED_MARK = "图片已过期"
#: 登记表容量（LRU 淘汰）。只是缓存，不做持久化，写满就挤掉最久未命中的。
DEFAULT_CAPACITY = 512
#: 描述回显的前缀（库里有这张图的解析记录时追加）
DESCRIPTION_PREFIX = "；历史记录里留下过它的描述："

#: 内联引用前缀：不依赖网络，不参与登记
_INLINE_PREFIXES = ("base64://", "data:")

#: 「引用键 -> 描述」查询钩子（bootstrap 注入，见 `install_description_lookup`）
DescriptionLookup = Callable[[str], Awaitable[Optional[str]]]
_lookup: Optional[DescriptionLookup] = None


def install_description_lookup(lookup: Optional[DescriptionLookup]) -> None:
    """安装「引用键 -> 已解析描述」查询（由 bootstrap 接上 images 表）。

    查不到、没安装、或查询抛异常都只当「没有描述」：过期说明本身不受影响。
    """
    global _lookup
    _lookup = lookup


def ref_digest(key: Optional[str]) -> Optional[str]:
    """引用键的稳定摘要：库里只存摘要，临时 URL / file id 不原样落盘。"""
    text = str(key or "").strip()
    if not text:
        return None
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:32]


async def describe(key: Optional[str]) -> Optional[str]:
    """查这张图以前留下的文字描述；没有则返回 None。"""
    digest = ref_digest(key)
    if digest is None or _lookup is None:
        return None
    try:
        text = await _lookup(digest)
    except Exception:
        return None
    text = str(text or "").strip()
    return text or None


def image_ref_key(
    seg_data: Any,
    *,
    message_id: Any = None,
    image_index: Any = None,
) -> Optional[str]:
    """推导图片引用的稳定键；推不出来返回 None（调用方据此跳过登记）。"""
    if isinstance(seg_data, dict):
        for field in ("file", "url"):
            value = str(seg_data.get(field) or "").strip()
            if value and not value.startswith(_INLINE_PREFIXES):
                return f"{field}:{value}"
    if message_id is None:
        return None
    try:
        index = int(image_index or 0)
    except (TypeError, ValueError):
        index = 0
    return f"msg:{message_id}:{index}"


def is_expiry_failure(exc: BaseException) -> bool:
    """异常是否代表「这张图没了」：超时，或 403/404/410。

    只认这两类：网络抖动、鉴权失败、5xx 都可能是瞬时故障，登记了反而会把好图一并废掉。
    """
    if isinstance(exc, TimeoutError):
        return True
    if "Timeout" in type(exc).__name__:  # httpx.TimeoutException 及其子类
        return True
    return getattr(getattr(exc, "response", None), "status_code", None) in (403, 404, 410)


def is_expired_message(text: Any) -> bool:
    """错误串是否代表「图片已过期」（调用方据此换成不带原始引用的文案）。"""
    return EXPIRED_MARK in str(text or "")


def clean_expired_text(text: Any) -> str:
    """把可能夹带原始 file/URL 的错误串收敛成过期说明（+ 库里留过的描述）。

    诊断串是给日志用的，可能含临时 URL、file id 甚至内联 base64；而工具结果与
    模型上下文只该看到「过期」这件事本身。
    """
    raw = str(text or "")
    index = raw.find(DESCRIPTION_PREFIX)
    suffix = raw[index:] if index >= 0 else ""
    return f"{EXPIRED_NOTICE}{suffix}"


def expired_inline_text(description: Optional[str] = None) -> str:
    """`[图片：…]` 里的过期文案；有旧描述时一并带上。"""
    text = EXPIRED_INLINE
    if description:
        text = f"{text}{DESCRIPTION_PREFIX}{description}"
    return text


class ImageUnavailableRegistry:
    """进程内的「拉不到的图片」登记表（LRU，容量有限）。

    只做两件事：`mark` 记下某个引用已不可用，`notice` 命中时给出过期说明。
    不落盘、不跨进程：`本次记录` 的语义就是「这次运行里不再拉」。
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._entries: "OrderedDict[str, str]" = OrderedDict()
        self._capacity = max(1, int(capacity))

    def mark(self, key: Optional[str], notice: str = EXPIRED_NOTICE) -> None:
        """登记一个不可用引用；key 为空时什么都不做。"""
        if not key:
            return
        self._entries[key] = notice
        self._entries.move_to_end(key)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def notice(self, key: Optional[str]) -> Optional[str]:
        """命中返回过期说明并计一次命中；未登记返回 None。"""
        if not key:
            return None
        notice = self._entries.get(key)
        if notice is None:
            return None
        self._entries.move_to_end(key)
        return notice

    def is_marked(self, key: Optional[str]) -> bool:
        return bool(key) and key in self._entries

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


#: 进程级登记表：所有取图入口共用同一份「拉不到」的记忆。
REGISTRY = ImageUnavailableRegistry()
