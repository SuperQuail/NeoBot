"""dsh_router 插件配置（plugin.toml ``[config]`` 的 pydantic 镜像）。

打包默认值在 plugin.toml，运行期值在 ``plugins_data/dsh_router/config.toml``；
两者按「默认值打底、已存值覆盖」合并后由 modloader 交给本模型校验，
校验失败时整份回落默认值并记 ``config_error``。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

#: 允许的 cwd 模式。
MODES = ("read", "write")


class DshRouterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    workspaces: list[str] = []
    max_tasks_per_chat: int = 3
    task_stale_seconds: int = 900
    event_min_interval_seconds: int = 45
    auto_exit_idle_minutes: int = 30
    proposal_ttl_minutes: int = 10
    command_permission: int = 2

    @field_validator("workspaces")
    @classmethod
    def _clean_workspaces(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                raise ValueError("workspaces 里不能有空路径")
            cleaned.append(text)
        return cleaned

    @field_validator("max_tasks_per_chat")
    @classmethod
    def _positive_tasks(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_tasks_per_chat 必须 >= 1")
        return value

    @field_validator("event_min_interval_seconds")
    @classmethod
    def _non_negative_interval(cls, value: int) -> int:
        if value < 0:
            raise ValueError("event_min_interval_seconds 不能为负")
        return value

    @field_validator("command_permission")
    @classmethod
    def _valid_permission(cls, value: int) -> int:
        if value not in {0, 1, 2}:
            raise ValueError("command_permission 必须是 0、1 或 2")
        return value


__all__ = ["MODES", "DshRouterConfig"]
