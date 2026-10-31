"""沙箱维护 Agent 的单轮协程（独立 Agent + 常驻技能）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .maintenance_schedule import DEFAULT_MAINTENANCE_INTERVAL_SECONDS, MAINTENANCE_RESIDENT_SKILLS, _MAINTENANCE_RETRY_STATUSES, plan_maintenance_run


def _make_maintenance_coro(
    *,
    provider: Any,
    skill_manager: Any,
    sandbox_components: dict[str, Any],
    data_dir: Path,
    admin_id: str,
    logger: Any,
    prompt_store: Any = None,
    engine: Any = None,
    interval_seconds: int = DEFAULT_MAINTENANCE_INTERVAL_SECONDS,
):
    """创建沙箱维护 AI Agent 后台循环协程。不经过聊天流，直接调用 AI。

    调度以数据库里的运行记录为准：进程重启不再无条件重跑一次，
    而是看「距上次成功维护是否已到 interval_seconds」；上次失败/中断则立即补跑。
    """
    from neobot_chat.runtime.agent import Agent

    from neobot_app.prompt.store import get_template_value

    maintenance_prompt = get_template_value(
        prompt_store, "maintenance", "system_prompt"
    )

    from neobot_app.skills.agent_toolset import LiveToolset, SkillToolsetExecutor

    # 常驻精简集 + skills__load_tools 按需加载：维护 Agent 每轮都重算工具集。
    toolset = LiveToolset(
        executor=SkillToolsetExecutor(
            skill_manager, resident=MAINTENANCE_RESIDENT_SKILLS
        )
    )

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from neobot_storage.models import MaintenanceRunRecord
    from neobot_storage.repositories.maintenance import (
        SqlAlchemyMaintenanceRunRepository,
    )

    from neobot_app.time_context import now_utc

    session_factory = (
        async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None
    )
    interval = max(60, int(interval_seconds))

    def _stored(value: datetime | None) -> datetime | None:
        """时间列一律存无时区 UTC。"""
        return None if value is None else value.astimezone(timezone.utc).replace(tzinfo=None)

    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # 列里是无时区 UTC，不能按本地时区解读
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    async def _history() -> tuple[datetime | None, str | None]:
        """(最近一次成功维护时间, 最近一次尝试的状态)；读不到时返回 (None, None)。"""
        if session_factory is None:
            return None, None
        try:
            async with session_factory() as session:
                repo = SqlAlchemyMaintenanceRunRepository(session)
                success = await repo.last_finished_success()
                attempt = await repo.last_attempt()
                return (
                    success.started_at if success is not None else None,
                    attempt.status if attempt is not None else None,
                )
        except Exception as exc:  # 数据库不可用不应让维护永久停摆
            logger.warning(f"沙箱维护：读取运行记录失败，按到期处理: {exc}")
            return None, None

    async def _begin(trigger: str) -> int | None:
        if session_factory is None:
            return None
        try:
            async with session_factory() as session:
                record = MaintenanceRunRecord(
                    started_at=_stored(now_utc()),
                    status="running",
                    trigger=trigger,
                    tool_calls=0,
                )
                await SqlAlchemyMaintenanceRunRepository(session).add(record)
                await session.commit()
                return record.id
        except Exception as exc:
            logger.warning(f"沙箱维护：写入运行记录失败: {exc}")
            return None

    async def _finish(
        run_id: int | None,
        *,
        status: str,
        tool_calls: int = 0,
        summary: str | None = None,
        error: str | None = None,
    ) -> None:
        if session_factory is None or run_id is None:
            return
        try:
            async with session_factory() as session:
                await SqlAlchemyMaintenanceRunRepository(session).finish(
                    run_id,
                    status=status,
                    finished_at=_stored(now_utc()),
                    tool_calls=tool_calls,
                    summary=summary,
                    error=error,
                )
                await session.commit()
        except Exception as exc:
            logger.warning(f"沙箱维护：结算运行记录失败: {exc}")

    async def _record_skip(trigger: str, reason: str) -> None:
        if session_factory is None:
            return
        try:
            async with session_factory() as session:
                stamp = _stored(now_utc())
                await SqlAlchemyMaintenanceRunRepository(session).add(
                    MaintenanceRunRecord(
                        started_at=stamp,
                        finished_at=stamp,
                        status="skipped",
                        trigger=trigger,
                        tool_calls=0,
                        skipped_reason=reason[:500],
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.warning(f"沙箱维护：写入跳过记录失败: {exc}")

    async def _loop() -> None:
        await asyncio.sleep(60)
        first_pass = True
        while True:
            trigger = "startup" if first_pass else "interval"
            first_pass = False

            last_success, last_status = await _history()
            if last_status in _MAINTENANCE_RETRY_STATUSES:
                logger.info(f"沙箱维护：上次记录状态为 {last_status}，立即补跑一次")
            plan = plan_maintenance_run(
                last_success=last_success,
                last_status=last_status,
                interval_seconds=interval,
                now=now_utc(),
            )
            if not plan.due:
                await _record_skip(trigger, plan.reason)
                try:
                    # 分片上界避免长时间休眠拖延配置变更/关闭
                    await asyncio.sleep(min(max(plan.wait_seconds, 60.0), 1800.0))
                except asyncio.CancelledError:
                    raise
                continue

            agent: Agent | None = None
            run_id: int | None = None
            tool_count = 0
            try:
                logger.info("沙箱维护 Agent 开始执行")
                run_id = await _begin(trigger)
                agent = Agent(
                    provider=provider,
                    toolset=toolset,
                    system_prompt=maintenance_prompt,
                    max_iterations=30,
                    command_timeout=120,
                )
                state = {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "请执行一次完整的沙箱维护清理。\n"
                                "按系统提示中的维护流程逐步操作，完成每步后汇报结果。"
                            ),
                        },
                    ],
                }
                result = await agent.invoke(state)
                msgs = result.get("messages", [])
                tool_count = sum(1 for m in msgs if m.get("role") == "tool")
                assist_msgs = [m for m in msgs if m.get("role") == "assistant" and m.get("content")]
                last_content = assist_msgs[-1].get("content", "")[:200] if assist_msgs else "(无文本输出)"
                logger.info(
                    f"沙箱维护完成: {tool_count} 次工具调用, "
                    f"最后输出: {last_content}"
                )
                await _finish(
                    run_id, status="success", tool_calls=tool_count, summary=last_content
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"沙箱维护 Agent 异常: {exc}")
                await _finish(run_id, status="failed", tool_calls=tool_count, error=str(exc))
            finally:
                if agent is not None:
                    try:
                        await agent.close()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(f"沙箱维护 Agent 关闭异常: {exc}")
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

    return _loop()
