"""热重载消费者注册表。

配置重载要解决的编排问题是：**改完之后，谁需要重新读配置并让改动生效？**

原做法是在重载入口里逐个判断「哪项变了 → 硬编码地重建哪个组件」：
新增一个持有配置快照的组件，就得回头改重载入口，而且改漏了不会报错，
只会表现为「配置改了没生效」。这违反开闭原则 —— 对扩展不封闭。

这里改成注册制：
- 组件自己实现 ``ConfigConsumer``（声明关心哪些配置前缀 + 自己负责生效）；
- 组合根把它们注册进来；
- 重载时注册表只调用「声明关心的前缀确实变了的」那些组件。

于是「新增一个可热重载子系统」= 新增一次注册，重载编排代码零改动。

职责边界：本模块只管**编排**（谁被调用、按什么顺序、失败怎么收场），
不关心任何具体组件，也不决定「某项配置是否需要重启」——
那是 ``config.hot_reload`` 的分类职责。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol, runtime_checkable

from neobot_contracts.ports.logging import Logger, NullLogger


@runtime_checkable
class ConfigConsumer(Protocol):
    """能吃新配置并让自己生效的组件。"""

    @property
    def name(self) -> str:
        """日志与结果里展示的组件名。"""
        ...

    @property
    def config_paths(self) -> tuple[str, ...]:
        """关心的配置路径前缀（如 ``("adapter", "models")``）。"""
        ...

    @property
    def hot_reload_policies(self) -> tuple[Any, ...]:
        """该组件对自身配置项生效方式的声明（``config.hot_reload.HotReloadRule``）。

        组件最清楚自己能不能在运行期生效，因此由它声明，注册时写进分类表；
        分类表本身不必认识任何具体组件。
        """
        ...

    async def apply_config(self, config: Any) -> None:
        """用新配置让自己生效；实现方自行处理内部失败与回滚。"""
        ...


@dataclass(frozen=True, slots=True)
class ReloadOutcome:
    """单个消费者的生效结果。"""

    name: str
    applied: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "applied": self.applied}
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True, slots=True)
class HotReloadReport:
    """一次热重载的完整结论。"""

    changed_paths: tuple[str, ...] = ()
    outcomes: tuple[ReloadOutcome, ...] = ()

    @property
    def applied(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.outcomes if item.applied)

    @property
    def failed(self) -> tuple[ReloadOutcome, ...]:
        return tuple(item for item in self.outcomes if item.error)

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    def summary(self) -> str:
        if not self.outcomes:
            return "没有组件声明关心本次改动的配置项"
        text = f"已让 {self.applied_count} 个组件按新配置生效"
        if self.failed_count:
            text += f"，{self.failed_count} 个失败"
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_paths": list(self.changed_paths),
            "applied": [item.to_dict() for item in self.outcomes if item.applied],
            "failed": [item.to_dict() for item in self.failed],
            "applied_count": self.applied_count,
            "failed_count": self.failed_count,
        }


class HotReloadRegistry:
    """按声明把配置改动分发给关心它的组件。

    顺序语义：按注册顺序调用，先注册先生效。装配方据此表达依赖
    （例如「适配器先重连，再重建 Provider」），注册表本身不猜测顺序。
    """

    def __init__(
        self,
        consumers: Iterable[ConfigConsumer] = (),
        *,
        logger: Logger | None = None,
    ) -> None:
        self._consumers: list[ConfigConsumer] = []
        self._logger = logger or NullLogger()
        for consumer in consumers:
            self.register(consumer)

    @property
    def consumers(self) -> tuple[ConfigConsumer, ...]:
        return tuple(self._consumers)

    def register(self, consumer: ConfigConsumer) -> None:
        """注册一个消费者；同名重复注册会被忽略（幂等）。

        注册的同时把消费者声明的生效方式写进配置分类表 —— 分类表据此知道
        「这项改动其实可以在运行期生效」，而不是继续按保守假设报「需重启」。
        """
        if not isinstance(consumer, ConfigConsumer):
            raise TypeError(
                "热重载消费者必须实现 name / config_paths / hot_reload_policies "
                f"/ apply_config: {consumer!r}"
            )
        if any(existing.name == consumer.name for existing in self._consumers):
            self._logger.warning(f"热重载消费者已注册，跳过重复注册: {consumer.name}")
            return
        self._consumers.append(consumer)
        policies = tuple(getattr(consumer, "hot_reload_policies", ()) or ())
        if policies:
            from neobot_app.config.hot_reload import register_rules

            register_rules(policies)

    def consumers_for(self, changed_paths: Iterable[str]) -> tuple[ConfigConsumer, ...]:
        """返回声明关心任一改动路径的消费者（按注册顺序）。"""
        paths = [str(path) for path in changed_paths if str(path)]
        if not paths:
            return ()
        selected: list[ConfigConsumer] = []
        for consumer in self._consumers:
            prefixes = tuple(str(item) for item in consumer.config_paths)
            if any(self._matches(path, prefixes) for path in paths):
                selected.append(consumer)
        return tuple(selected)

    @staticmethod
    def _matches(path: str, prefixes: tuple[str, ...]) -> bool:
        """路径命中判定：按「点分前缀」匹配，避免 ``adapter`` 命中 ``adapter_x``。"""
        for prefix in prefixes:
            if not prefix:
                continue
            if path == prefix or path.startswith(f"{prefix}."):
                return True
        return False

    async def apply(self, config: Any, changed_paths: Iterable[str]) -> HotReloadReport:
        """把改动分发给关心的消费者，单个失败不影响其余组件。"""
        paths = tuple(str(path) for path in changed_paths if str(path))
        selected = self.consumers_for(paths)
        outcomes: list[ReloadOutcome] = []
        for consumer in selected:
            try:
                await consumer.apply_config(config)
            except Exception as exc:
                self._logger.error(
                    f"热重载组件失败，其余组件继续: {consumer.name}",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                outcomes.append(
                    ReloadOutcome(
                        name=consumer.name,
                        applied=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
            else:
                self._logger.info(f"热重载组件已按新配置生效: {consumer.name}")
                outcomes.append(ReloadOutcome(name=consumer.name, applied=True))
        return HotReloadReport(changed_paths=paths, outcomes=tuple(outcomes))
