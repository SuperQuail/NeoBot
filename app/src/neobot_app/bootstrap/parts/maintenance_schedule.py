"""沙箱维护的调度计划（纯函数，供启动期与维护协程共用）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


# 沙箱维护 Agent 的常驻技能：它每次运行要发 16~23 次模型调用，
# 常驻全部技能（173 个工具 / 71K 字符）是纯固定开销；其余能力用 skills__load_tools 按需加载。
MAINTENANCE_RESIDENT_SKILLS = frozenset(
    {"archive", "file_storage", "sandbox_maintenance", "sandbox_manager"}
)

# 沙箱维护调度默认间隔（可被 agent.sandbox.maintenance.interval_seconds 覆盖）。
DEFAULT_MAINTENANCE_INTERVAL_SECONDS = 10800


@dataclass(frozen=True)
class MaintenancePlan:
    """本轮沙箱维护的调度决定。"""

    due: bool
    wait_seconds: float
    reason: str


def plan_maintenance_run(
    *,
    last_success: datetime | None,
    last_status: str | None,
    interval_seconds: int,
    now: datetime,
) -> MaintenancePlan:
    """按数据库里的历史决定本轮是否需要跑沙箱维护。

    - 上一次没能正常结束（failed / running，后者多为进程中断）→ 立即补跑；
    - 从未成功过 → 跑；
    - 距上次成功已超过间隔 → 跑；
    - 否则跳过，并给出需等待的秒数。

    时间列按无时区 UTC 解读（与写入时的归一化保持一致）。
    """
    if last_status in _MAINTENANCE_RETRY_STATUSES:
        return MaintenancePlan(True, 0.0, "")
    if last_success is None:
        return MaintenancePlan(True, 0.0, "")
    stamp = last_success if last_success.tzinfo else last_success.replace(tzinfo=timezone.utc)
    elapsed = (now - stamp).total_seconds()
    if elapsed >= interval_seconds:
        return MaintenancePlan(True, 0.0, "")
    remaining = interval_seconds - elapsed
    reason = (
        f"距上次成功维护仅 {int(elapsed)} 秒（配置间隔 {interval_seconds} 秒），"
        f"约 {int(remaining)} 秒后到期"
    )
    return MaintenancePlan(False, remaining, reason)
# 这些状态说明上一次维护没有正常完成，启动后应立即补跑一次。
_MAINTENANCE_RETRY_STATUSES = frozenset({"failed", "running"})
