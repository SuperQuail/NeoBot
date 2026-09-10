"""模型可用性判定策略。

加载配置时要回答一个问题：**某个模型角色缺配置，算不算致命？**

这个判定是策略，不是机制：有人要「缺 Key 就别启动」（严格部署、CI），
有人要「缺 Key 也先起来，让我进面板补」（日常使用）。把规则写死在
加载流程里，两种诉求只能二选一，而且是改源码才能换。

因此这里只放**纯判定**：输入一份发现清单，输出致命/降级两组，不碰注册表、
不写日志、不看配置对象。加载器负责收集与记录，调用方负责选择策略。

职责边界：
- ``ModelFinding``      —— 一条「某角色的模型缺了什么」的事实；
- ``ModelAvailabilityPolicy`` —— 「这些事实里哪些致命」的规则；
- 收集事实、记录日志、注册模型 —— 仍由 ``Config.register_models`` 负责。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

#: 缺配置时可安全降级的角色：这些功能没有独立开关或本身就是可选能力，
#: 缺 Key 时关掉该功能即可，模型仍能正常对话。
DEFAULT_DEGRADABLE_ROLES: frozenset[str] = frozenset({"vision_model", "tts_model"})


@dataclass(frozen=True, slots=True)
class ModelFinding:
    """一条模型配置缺失的事实。"""

    role: str
    key: str
    missing: tuple[str, ...]

    def describe(self) -> str:
        if self.key:
            prefix = f"模型 {self.key}（{self.role}）缺少: "
        else:
            prefix = f"{self.role}: "
        return prefix + "、".join(self.missing)


class FindingSeverity(StrEnum):
    FATAL = "fatal"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class AvailabilityReport:
    """判定结论：哪些缺失致命、哪些只降级。"""

    fatal: tuple[ModelFinding, ...] = ()
    degraded: tuple[ModelFinding, ...] = ()

    @property
    def has_fatal(self) -> bool:
        return bool(self.fatal)

    @property
    def has_degraded(self) -> bool:
        return bool(self.degraded)

    def fatal_message(self) -> str:
        """致命缺失的统一文案（无致命项时为空串）。"""
        if not self.fatal:
            return ""
        return (
            "配置校验失败，以下必需配置缺失（请补充对应平台的环境变量）：\n"
            + "\n".join(f"  - {item.describe()}" for item in self.fatal)
        )

    def degraded_messages(self) -> tuple[str, ...]:
        """降级项逐条文案，供调用方按自己的日志粒度输出。"""
        return tuple(item.describe() for item in self.degraded)


class ModelAvailabilityPolicy:
    """把缺失清单切分为「致命」与「降级」两组。

    ``degradable_roles`` 之外的任何角色缺配置都算致命 —— 默认保守，
    新增角色不会被无意放行。
    """

    def __init__(self, degradable_roles: Iterable[str] = DEFAULT_DEGRADABLE_ROLES) -> None:
        self._degradable = frozenset(str(role) for role in degradable_roles)

    @property
    def degradable_roles(self) -> frozenset[str]:
        return self._degradable

    def is_degradable(self, role: str) -> bool:
        return role in self._degradable

    def classify(self, findings: Iterable[ModelFinding]) -> AvailabilityReport:
        fatal: list[ModelFinding] = []
        degraded: list[ModelFinding] = []
        for finding in findings:
            if self.is_degradable(finding.role):
                degraded.append(finding)
            else:
                fatal.append(finding)
        return AvailabilityReport(fatal=tuple(fatal), degraded=tuple(degraded))


class DegradeEverythingPolicy(ModelAvailabilityPolicy):
    """任何缺失都只降级、绝不致命。

    用于「先把进程和面板起来，让人在面板里补配置」的运行模式：此时缺 Key
    只意味着对应功能不可用，不应该把整个进程带走。
    """

    def __init__(self) -> None:
        super().__init__(degradable_roles=())

    def is_degradable(self, role: str) -> bool:
        return True

    def classify(self, findings: Iterable[ModelFinding]) -> AvailabilityReport:
        return AvailabilityReport(degraded=tuple(findings))
