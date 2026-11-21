"""身份映射后的档案合并：一律以 openid 为主键，QQ号/群号内容并入且排在前面。

触发点：管理员执行 /linkqq、/linkgroup 成功之后（命令层调用本模块）。
合并范围：长期档案 user_profile/user_summary、group_profile/group_summary，以及
user_data/group_data 资料行；聊天记录、memories 等按会话存储的数据不动。

合并规则：
- 只存在于 QQ号/群号一侧的条目直接移动到 openid 主键；
- 两侧都有时，文本内容按「QQ号版本 + 空行 + openid版本」拼接；
- 资料行：profile 文本按同样顺序拼接；nick_name/remark 等字段优先保留 openid
  非空值、缺失才取 QQ号版本；好感度取两者较大值（避免合并把分数清零）；
- 合并成功后删除源行，之后只存在 openid 一份。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.user_identity import canonical_group_id, canonical_user_id

_USER_ARCHIVE_TABLES = ("user_profile", "user_summary")
_GROUP_ARCHIVE_TABLES = ("group_profile", "group_summary")
_USER_TEXT_FIELDS = (
    "nick_name",
    "relation_ship",
    "profile",
    "known_gender",
    "birthday",
    "sex",
    "city",
    "country",
    "labs",
    "remark",
    "avatar_analysis",
    "long_nick",
)
_USER_OTHER_FIELDS = (
    "age",
    "fetched_at",
    "avatar_path",
    "avatar_fetched_at",
    "avatar_fail_count",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _merged_text(primary: Any, secondary: Any) -> str:
    """QQ号/群号版本在前，openid 版本在后；一侧为空时直接用另一侧。"""
    first, second = _text(primary), _text(secondary)
    if first and second:
        return f"{first}\n\n{second}"
    return first or second


def _merged_tags(primary: Any, secondary: Any) -> list[str]:
    return list(dict.fromkeys([*(primary or []), *(secondary or [])]))


def _latest(first: datetime | None, second: datetime | None) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if first >= second else second


def _prefer(primary: Any, secondary: Any) -> Any:
    return primary if primary not in (None, "") else secondary


class IdentityMergeService:
    """把 QQ号/群号一侧的资料与档案并入 openid 主键。"""

    def __init__(self, *, uow_factory: Any, logger: Logger | None = None) -> None:
        self._uow_factory = uow_factory
        self._logger = logger or NullLogger()

    async def merge_user(
        self, *, openid: Any, qq: Any, channel: str | None = None
    ) -> dict[str, Any]:
        target = canonical_user_id(openid, channel) or _text(openid)
        source = _text(qq)
        if not target or not source or target == source:
            return {"merged": False, "archives": 0, "profile": False}
        async with self._uow_factory() as uow:
            archives = 0
            for table in _USER_ARCHIVE_TABLES:
                if await self._merge_archive(uow, table, target, source):
                    archives += 1
            profile = await self._merge_user_profile(uow, target, source)
            await uow.commit()
        self._logger.info(
            "已合并用户身份档案", target=target, source=source, archives=archives, profile=profile
        )
        return {"merged": bool(archives or profile), "archives": archives, "profile": profile}

    async def merge_group(
        self, *, openid: Any, number: Any, channel: str | None = None
    ) -> dict[str, Any]:
        target = canonical_group_id(openid, channel) or _text(openid)
        source = _text(number)
        if not target or not source or target == source:
            return {"merged": False, "archives": 0, "group": False}
        async with self._uow_factory() as uow:
            archives = 0
            for table in _GROUP_ARCHIVE_TABLES:
                if await self._merge_archive(uow, table, target, source):
                    archives += 1
            group = await self._merge_group_profile(uow, target, source)
            await uow.commit()
        self._logger.info(
            "已合并群身份档案", target=target, source=source, archives=archives, group=group
        )
        return {"merged": bool(archives or group), "archives": archives, "group": group}

    @staticmethod
    async def _merge_archive(uow: Any, table: str, target: str, source: str) -> bool:
        source_item = await uow.archive.get(table, source)
        if source_item is None:
            return False
        target_item = await uow.archive.get(table, target)
        if target_item is None:
            value, tags = source_item.value, list(source_item.tags or [])
        else:
            value = _merged_text(source_item.value, target_item.value)
            tags = _merged_tags(source_item.tags, target_item.tags)
        await uow.archive.set(table, target, value, tags)
        await uow.archive.delete(table, source)
        return True

    async def _merge_user_profile(self, uow: Any, target: str, source: str) -> bool:
        source_row = await uow.profiles.get_user(source)
        if source_row is None:
            return False
        target_row = await uow.profiles.get_user(target)
        if target_row is None:
            await uow.profiles.upsert_user(target, **self._user_columns(source_row))
        else:
            await uow.profiles.upsert_user(
                target, **self._merged_user_columns(source_row, target_row)
            )
        await uow.profiles.delete_user(source)
        return True

    @staticmethod
    def _user_columns(row: Any) -> dict[str, Any]:
        values = {name: getattr(row, name, None) for name in _USER_TEXT_FIELDS}
        values["favorability"] = int(getattr(row, "favorability", 0) or 0)
        for name in _USER_OTHER_FIELDS:
            values[name] = getattr(row, name, None)
        return values

    @classmethod
    def _merged_user_columns(cls, source_row: Any, target_row: Any) -> dict[str, Any]:
        source = cls._user_columns(source_row)
        target_values = cls._user_columns(target_row)
        fields: dict[str, Any] = {}
        for name in _USER_TEXT_FIELDS:
            if name == "profile":
                fields[name] = _merged_text(source[name], target_values[name])
            else:
                fields[name] = _prefer(target_values[name], source[name])
        fields["favorability"] = max(source["favorability"], target_values["favorability"])
        fields["age"] = _prefer(target_values["age"], source["age"])
        fields["fetched_at"] = _latest(target_values["fetched_at"], source["fetched_at"])
        fields["avatar_path"] = _prefer(target_values["avatar_path"], source["avatar_path"])
        fields["avatar_fetched_at"] = _latest(
            target_values["avatar_fetched_at"], source["avatar_fetched_at"]
        )
        fields["avatar_fail_count"] = max(
            int(target_values["avatar_fail_count"] or 0),
            int(source["avatar_fail_count"] or 0),
        )
        return fields

    async def _merge_group_profile(self, uow: Any, target: str, source: str) -> bool:
        source_row = await uow.profiles.get_group(source)
        if source_row is None:
            return False
        target_row = await uow.profiles.get_group(target)
        if target_row is None:
            await uow.profiles.upsert_group(
                target,
                group_name=getattr(source_row, "group_name", None),
                profile=getattr(source_row, "profile", None),
                is_quite=bool(getattr(source_row, "is_quite", False)),
            )
        else:
            await uow.profiles.upsert_group(
                target,
                group_name=_prefer(
                    getattr(target_row, "group_name", None),
                    getattr(source_row, "group_name", None),
                ),
                profile=_merged_text(
                    getattr(source_row, "profile", None), getattr(target_row, "profile", None)
                ),
                is_quite=bool(getattr(target_row, "is_quite", False)),
            )
        await uow.profiles.delete_group(source)
        return True


_service: IdentityMergeService | None = None


def bind_identity_merge(service: IdentityMergeService | None) -> None:
    """bootstrap 装配后注入；测试/未装配时为 None，link 命令跳过合并。"""
    global _service
    _service = service


def get_identity_merge() -> IdentityMergeService | None:
    return _service
