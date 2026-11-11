"""统一的机器人 QQ 号提供者。

双通道（OneBot + 官方）下每条通道的机器人号不同，且官方通道的账号只能从
API（get_login_info / events.self_id）拿到、不能读 config。为了让业务侧
不关心「单通道还是双通道、官方还是 OneBot、self_id 有没有、config 填没填」，
所有取号/判自身发言的地方统一走这里：

    from neobot_app.bot_accounts import (
        bot_account_for_event, bot_account_for_message, bot_accounts,
        is_bot_message, looks_like_real_qq, primary_bot_account,
    )

实现侧只调用函数，不在本地再写 self_id/channel/config 的回退分支。函数可选的
config 参数只用于「直接构造组件、尚未 bootstrap 绑定」的单测/旧路径兜底；
生产运行时由 bind_bot_accounts 绑定，调用方不需要传。

绑定时机：bootstrap 每次构建运行时调用 bind_bot_accounts(config, detector)；
软重启会重新绑定，查询函数始终读最新绑定，不做缓存。
"""

from __future__ import annotations

from typing import Any

#: 真实 QQ 号的最长位数（官方 openid 的合成号是 13 位，不能当 QQ 号用）。
_MAX_QQ_DIGITS = 11
#: 真实 QQ 群号的最长位数（群号比 QQ 号多一位）。
_MAX_GROUP_DIGITS = 12
#: 官方合成号的最小位数：官方 openid 派生的 13 位数字（真实号最多 12 位）。
_SYNTHETIC_ID_MIN_DIGITS = 13


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class BotAccounts:
    """按「当前运行时」解析机器人 QQ 号；实现细节对调用方不可见。"""

    def __init__(self) -> None:
        self._config: Any = None
        self._detector: Any = None

    def bind(self, config: Any = None, detector: Any = None) -> None:
        self._config = config
        self._detector = detector

    # ── 内部解析 ────────────────────────────────────────────

    @staticmethod
    def _config_account(config: Any) -> int:
        bot = getattr(config, "bot", None)
        return _to_int(getattr(bot, "account", 0))

    def _detector_accounts(self) -> dict[str, int]:
        raw = getattr(self._detector, "accounts", None)
        if not isinstance(raw, dict):
            return {}
        accounts: dict[str, int] = {}
        for channel, value in raw.items():
            account = _to_int(value)
            if account:
                accounts[str(channel)] = account
        return accounts

    # ── 解析 ────────────────────────────────────────────────

    def primary(self, config: Any = None) -> int:
        """主账号：优先身份服务解析出的主账号（双待下 OneBot 优先），否则 config。"""
        profile = getattr(self._detector, "profile", None)
        account = _to_int(getattr(profile, "account", 0))
        if account:
            return account
        accounts = self._detector_accounts()
        for channel in ("onebot", "official"):
            if accounts.get(channel):
                return accounts[channel]
        return self._config_account(config if config is not None else self._config)

    def all(self, config: Any = None, accounts: Any = None) -> set[int]:
        """当前已知的全部机器人 QQ 号（双待下两个）。

        accounts 是运行时另带进来的已知号集合（如消息队列登记的账号）；
        调用方只在已有这类数据时传入，正常业务路径不需要关心。
        """
        resolved = set(self._detector_accounts().values())
        primary = self.primary(config)
        if primary:
            resolved.add(primary)
        configured = self._config_account(config if config is not None else self._config)
        if configured:
            resolved.add(configured)
        for value in accounts or ():
            account = _to_int(value)
            if account:
                resolved.add(account)
        return resolved

    def for_channel(self, channel: str | None, config: Any = None) -> int:
        """指定通道的机器人号；通道未知/尚未解析时回退主账号。"""
        account_for = getattr(self._detector, "account_for", None)
        if channel and callable(account_for):
            account = _to_int(account_for(channel))
            if account:
                return account
        return self.primary(config)

    def for_message(self, message: Any, config: Any = None) -> int:
        """这条消息对应的机器人号：消息级 self_id 优先，其次通道账号。"""
        self_id = _to_int(getattr(message, "self_id", None))
        if self_id:
            return self_id
        return self.for_channel(getattr(message, "neobot_channel", None), config)

    def for_event(self, event: Any, config: Any = None) -> int:
        """回复事件对应的机器人号：事件 bot_account 优先，其次事件通道账号。"""
        account = _to_int(getattr(event, "bot_account", 0))
        if account:
            return account
        return self.for_channel(getattr(event, "neobot_channel", None), config)

    # ── 判定 ────────────────────────────────────────────────

    def is_bot_message(
        self, message: Any, config: Any = None, accounts: Any = None
    ) -> bool:
        """这条消息是不是机器人自己发的（双待下两条通道各自算自己）。"""
        user_id = _to_int(getattr(message, "user_id", None))
        self_id = _to_int(getattr(message, "self_id", None))
        if self_id and user_id == self_id:
            return True
        return bool(user_id) and user_id in self.all(config, accounts)

    def is_bot_id(self, user_id: Any, channel: str | None = None, config: Any = None) -> bool:
        uid = _to_int(user_id)
        if not uid:
            return False
        if uid in self.all(config):
            return True
        return bool(channel) and uid == self.for_channel(channel, config)


_singleton = BotAccounts()


def bind_bot_accounts(config: Any = None, detector: Any = None) -> None:
    """绑定当前运行时的配置与身份服务（bootstrap 每次构建调用一次）。"""
    _singleton.bind(config, detector)


def get_bot_accounts() -> BotAccounts:
    """给插件宿主服务注册用的提供者对象。"""
    return _singleton


def primary_bot_account(config: Any = None) -> int:
    return _singleton.primary(config)


def bot_accounts(config: Any = None, accounts: Any = None) -> set[int]:
    return _singleton.all(config, accounts)


def bot_account_for_channel(channel: str | None, config: Any = None) -> int:
    return _singleton.for_channel(channel, config)


def bot_account_for_message(message: Any, config: Any = None) -> int:
    return _singleton.for_message(message, config)


def bot_account_for_event(event: Any, config: Any = None) -> int:
    return _singleton.for_event(event, config)


def is_bot_message(message: Any, config: Any = None, accounts: Any = None) -> bool:
    return _singleton.is_bot_message(message, config, accounts)


def is_bot_id(user_id: Any, channel: str | None = None, config: Any = None) -> bool:
    return _singleton.is_bot_id(user_id, channel, config)


def id_label(value: Any) -> str:
    """用户 ID 的展示前缀：真实 QQ 号用 QQ，官方合成 ID 用 ID（群用 group_label）。"""
    return "QQ" if looks_like_real_qq(value) else "ID"


def display_user_id(value: Any) -> str:
    """把用户 ID 渲染成易读标签（QQ:123 / ID:9000…）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    return f"{id_label(text)}:{text}"


def is_synthetic_id(value: Any) -> bool:
    """是否是官方通道的合成 ID（13 位及以上纯数字，不是真实 QQ 号/群号）。

    真实 QQ 号最多 11 位、群号最多 12 位；合成号来自官方 openid 派生，13 位起。
    """
    text = str(value or "").strip()
    return text.isdigit() and len(text) >= _SYNTHETIC_ID_MIN_DIGITS


def looks_like_real_qq(value: Any, *, min_digits: int = 1) -> bool:
    """是否是真实 QQ 号规模的数字（默认 1~11 位；官方合成号/非数字不算）。

    官方通道只给 openid，内部合成号是 13 位（9.xT）；把合成号拿去请求
    qlogo 头像/资料接口必然失败，这里统一判定，调用方不再各自写位数逻辑。
    min_digits 供 /linkqq 这类输入校验收紧下界（真实 QQ 号 5 位起）。
    """
    text = str(value or "").strip()
    if not text.isdigit():
        return False
    return min_digits <= len(text) <= _MAX_QQ_DIGITS


def looks_like_real_group_number(value: Any, *, min_digits: int = 1) -> bool:
    """是否是真实 QQ 群号规模的数字（默认 1~12 位；官方合成号/非数字不算）。"""
    text = str(value or "").strip()
    if not text.isdigit():
        return False
    return min_digits <= len(text) <= _MAX_GROUP_DIGITS


def infer_channel(value: Any, *, kind: str | None = None) -> str:
    """按本地 ID 规模推断通道：真实号规模 → onebot，其余（合成号/非数字）→ official。

    kind="group" 时按群号上限判断，避免把 12 位真实群号误判成官方合成群。
    显式通道优先由调用方自己传入，这里只做规模推断，不做通道回退。
    """
    if str(kind or "").strip().casefold() == "group":
        return "onebot" if looks_like_real_group_number(value) else "official"
    return "onebot" if looks_like_real_qq(value) else "official"


def group_label(value: Any) -> str:
    """群 ID 的展示前缀：真实 QQ 群号用 群号，官方合成 ID 用 群 ID。"""
    return "群号" if looks_like_real_group_number(value) else "群 ID"


def display_group_id(value: Any) -> str:
    """把群 ID 渲染成易读标签（群号:123456 / 群 ID:9000…）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    return f"{group_label(text)}:{text}"


__all__ = [
    "BotAccounts",
    "bind_bot_accounts",
    "bot_account_for_channel",
    "bot_account_for_event",
    "bot_account_for_message",
    "bot_accounts",
    "display_group_id",
    "display_user_id",
    "get_bot_accounts",
    "group_label",
    "id_label",
    "infer_channel",
    "is_bot_id",
    "is_bot_message",
    "is_synthetic_id",
    "looks_like_real_group_number",
    "looks_like_real_qq",
    "primary_bot_account",
]
