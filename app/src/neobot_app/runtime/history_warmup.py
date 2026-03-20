"""HistoryWarmupService — 启动时拉取历史消息填充队列

从 ChatStreamManager 中拆出的历史消息预热逻辑
"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger


class HistoryWarmupService:
    """启动时从适配器拉取历史消息，填充消息队列"""

    def __init__(
        self,
        adapter: Any,
        *,
        concurrent_limit: int = 20,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 10,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._concurrent_limit = concurrent_limit
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout
        self._logger = logger or NullLogger()
        self._semaphore = asyncio.Semaphore(concurrent_limit)

    async def warmup(
        self,
        group_queue: Any,
        friend_queue: Any,
        max_group_obs: int = 100,
        max_friend_obs: int = 100,
    ) -> None:
        """拉取历史消息并填充队列"""
        self._logger.info("开始历史消息预热...")

        # 获取好友列表
        friend_response = await self._retry_api_call(self._adapter.get_friend_list)
        friends = friend_response.data if friend_response.data else []
        self._logger.info(f"获取到 {len(friends)} 个好友")

        # 获取群列表
        group_response = await self._retry_api_call(self._adapter.get_group_list)
        groups = group_response.data if group_response.data else []
        self._logger.info(f"获取到 {len(groups)} 个群")

        # 并发处理好友历史消息
        friend_tasks = [
            self._process_friend_history(friend, friend_queue, max_friend_obs)
            for friend in friends
        ]
        friend_results = await asyncio.gather(*friend_tasks, return_exceptions=True)
        self._log_results(friend_results, "好友历史消息")

        # 并发处理群历史消息
        group_tasks = [
            self._process_group_history(group, group_queue, max_group_obs)
            for group in groups
        ]
        group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
        self._log_results(group_results, "群历史消息")

        self._logger.info("历史消息预热完成")

    async def _process_friend_history(self, friend: Any, queue: Any, max_obs: int) -> None:
        history = await self._retry_api_call(
            self._adapter.get_friend_msg_history,
            user_id=friend.user_id,
            count=max_obs,
            reverse_order=False,
        )
        if not history.data or not history.data.messages:
            return
        for msg in history.data.messages:
            if isinstance(msg, tuple):
                continue
            try:
                queue.push(str(friend.user_id), msg)
            except Exception as e:
                self._logger.error(f"推送好友 {friend.user_id} 消息失败: {e}")

    async def _process_group_history(self, group: Any, queue: Any, max_obs: int) -> None:
        history = await self._retry_api_call(
            self._adapter.get_group_msg_history,
            group_id=group.group_id,
            count=max_obs,
            reverse_order=False,
        )
        if not history.data or not history.data.messages:
            return
        for msg in history.data.messages:
            if isinstance(msg, tuple):
                continue
            try:
                queue.push(str(group.group_id), msg)
            except Exception as e:
                self._logger.error(f"推送群 {group.group_id} 消息失败: {e}")

    async def _retry_api_call(self, api_func, *args, **kwargs):
        last_exc = None
        for attempt in range(self._max_retries):
            try:
                async with self._semaphore:
                    return await asyncio.wait_for(
                        api_func(*args, **kwargs),
                        timeout=self._timeout,
                    )
            except asyncio.TimeoutError:
                last_exc = TimeoutError(f"API调用超时 ({self._timeout}s)")
            except Exception as e:
                last_exc = e
            if attempt < self._max_retries - 1:
                wait = self._retry_delay * (2 ** attempt)
                self._logger.warning(f"API调用失败，重试 {attempt + 1}/{self._max_retries}，等待 {wait:.1f}s")
                await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _log_results(self, results: list, task_name: str) -> None:
        ok = sum(1 for r in results if not isinstance(r, Exception))
        err = len(results) - ok
        self._logger.info(f"{task_name}处理完成: 成功 {ok}, 失败 {err}")
