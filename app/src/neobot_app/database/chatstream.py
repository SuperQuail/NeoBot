"""聊天流管理模块"""

import asyncio
import logging
from typing import Any, Callable, List, Optional, Set
from dataclasses import dataclass
from contextlib import asynccontextmanager

from neobot_adapter import OneBotAdapter
from neobot_adapter.model.response import (
    FriendData,
    GroupData,
)
from neobot_adapter.model.message import PrivateMessage, GroupMessage

from neobot_app.message.queue import MessageQueue
from neobot_app.user_profiles import UserProfileService

logger = logging.getLogger(__name__)

# 配置常量
DEFAULT_CONCURRENT_LIMIT = 20  # 默认并发限制
DEFAULT_MAX_RETRIES = 3        # 默认最大重试次数
DEFAULT_RETRY_DELAY = 1.0      # 默认重试延迟（秒）
DEFAULT_TIMEOUT = 10           # 默认请求超时时间（秒）

@dataclass
class ChatStreamConfig:
    """聊天流配置"""
    concurrent_limit: int = DEFAULT_CONCURRENT_LIMIT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    timeout: int = DEFAULT_TIMEOUT


class ChatStreamManager:
    """聊天流管理器"""

    def __init__(
        self,
        adapter: OneBotAdapter,
        uow_factory: Callable,
        config: Optional[ChatStreamConfig] = None,
        group_message_queue: Optional[MessageQueue] = None,
        friend_message_queue: Optional[MessageQueue] = None,
    ):
        """初始化聊天流管理器"""
        self.adapter = adapter
        self._uow_factory = uow_factory
        self.config = config or ChatStreamConfig()
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._semaphore = asyncio.Semaphore(self.config.concurrent_limit)
        self._initialized = False

    async def initialize(self) -> None:
        """初始化聊天流

        1. 获取所有好友和群列表
        2. 并发获取历史消息并填充队列
        3. 收集所有用户ID并更新缺失的用户信息到数据库
        """
        if self._initialized:
            logger.warning("聊天流已初始化，跳过重复初始化")
            return

        logger.info("开始初始化聊天流...")

        # 延迟加载配置获取观察上限
        from neobot_app.config.instance import load_bot_config
        bot_cfg = load_bot_config()
        max_group_obs = bot_cfg.chat.max_group_chat_observations
        max_friend_obs = bot_cfg.chat.max_friend_chat_observations
        enable_group_startup_history_warmup = getattr(
            bot_cfg.chat,
            "enable_group_startup_history_warmup",
            False,
        )
        enable_friend_startup_history_warmup = getattr(
            bot_cfg.chat,
            "enable_friend_startup_history_warmup",
            False,
        )
        startup_history_group_whitelist = self._normalize_whitelist(
            getattr(bot_cfg.chat, "startup_history_group_whitelist", [])
        )
        startup_history_friend_whitelist = self._normalize_whitelist(
            getattr(bot_cfg.chat, "startup_history_friend_whitelist", [])
        )
        timestamp_interval_seconds = getattr(
            bot_cfg.chat,
            "message_timestamp_interval_seconds",
            300,
        )
        poke_weight = getattr(bot_cfg.chat, "poke_weight", 0.2)
        reaction_weight = getattr(bot_cfg.chat, "reaction_weight", 0.2)
        profile_service = UserProfileService(
            self.adapter,
            self._uow_factory,
            bot_cfg,
        )

        # 如果队列未通过构造函数注入，则自行创建
        if self._group_queue is None:
            self._group_queue = MessageQueue(
                max_size=max_group_obs,
                timestamp_interval_seconds=timestamp_interval_seconds,
                poke_weight=poke_weight,
                reaction_weight=reaction_weight,
                bot_account=bot_cfg.bot.account,
                reply_blacklist=set(bot_cfg.chat.reply_blacklist or []),
            )
        if self._friend_queue is None:
            self._friend_queue = MessageQueue(
                max_size=max_friend_obs,
                timestamp_interval_seconds=timestamp_interval_seconds,
                poke_weight=poke_weight,
                reaction_weight=reaction_weight,
                bot_account=bot_cfg.bot.account,
                reply_blacklist=set(bot_cfg.chat.reply_blacklist or []),
            )

        logger.info(f"群聊观察上限: {max_group_obs}, 私聊观察上限: {max_friend_obs}")

        try:
            # 获取群列表
            logger.info("正在获取群列表...")
            group_response = await self._retry_api_call(self.adapter.get_group_list)
            groups = group_response.data if group_response.data else []
            logger.info(f"获取到 {len(groups)} 个群")

            # 将群信息存入数据库
            if groups:
                logger.info("开始将群信息存入数据库...")
                async with self._uow_factory() as uow:
                    for group in groups:
                        try:
                            await self._insert_or_update_group_to_db(uow, group)
                        except Exception as e:
                            logger.error(f"存储群 {group.group_id} 信息时出错: {e}")
                    await uow.commit()
                logger.info(f"群信息存储完成，共处理 {len(groups)} 个群")

            if enable_group_startup_history_warmup:
                logger.warning("已开启群聊启动历史聊天记录预热，这可能存在风控风险")
                selected_groups = self._filter_entities_by_whitelist(
                    groups,
                    "group_id",
                    startup_history_group_whitelist,
                )
                logger.info(
                    "群聊启动历史消息白名单过滤完成: "
                    f"{len(selected_groups)}/{len(groups)}"
                )
                logger.info(
                    f"开始获取群历史消息，并发限制: {self.config.concurrent_limit}..."
                )
                group_tasks = [
                    self._process_group_history(group, max_group_obs)
                    for group in selected_groups
                ]
                group_results = await asyncio.gather(
                    *group_tasks, return_exceptions=True
                )
                self._log_task_results(group_results, "群历史消息")
            else:
                logger.info("群聊启动历史聊天记录预热未开启，跳过群历史消息拉取")

            if enable_friend_startup_history_warmup:
                logger.warning("已开启私聊启动历史聊天记录预热，这可能存在风控风险")
                logger.info("正在获取好友列表...")
                friend_response = await self._retry_api_call(self.adapter.get_friend_list)
                friends = friend_response.data if friend_response.data else []
                logger.info(f"获取到 {len(friends)} 个好友")
                selected_friends = self._filter_entities_by_whitelist(
                    friends,
                    "user_id",
                    startup_history_friend_whitelist,
                )
                logger.info(
                    "私聊启动历史消息白名单过滤完成: "
                    f"{len(selected_friends)}/{len(friends)}"
                )
                logger.info(
                    f"开始获取好友历史消息，并发限制: {self.config.concurrent_limit}..."
                )
                friend_tasks = [
                    self._process_friend_history(friend, max_friend_obs)
                    for friend in selected_friends
                ]
                friend_results = await asyncio.gather(
                    *friend_tasks, return_exceptions=True
                )
                self._log_task_results(friend_results, "好友历史消息")
            else:
                logger.info("私聊启动历史聊天记录预热未开启，跳过私聊历史消息拉取")

            # 收集所有用户ID并更新缺失的用户信息
            logger.info("开始收集用户ID并更新缺失的用户信息...")
            user_ids = await self._collect_user_ids_from_messages()
            await self._update_user_profiles(user_ids, profile_service)

            self._initialized = True
            logger.info("聊天流初始化完成")

        except Exception as e:
            logger.error(f"聊天流初始化失败: {e}", exc_info=True)
            raise

    async def update(self) -> None:
        """更新聊天流

        定期调用此函数来更新消息队列和用户信息
        """
        logger.info("开始更新聊天流...")
        await self.initialize()  # 目前重新初始化，后续可改为增量更新

    @asynccontextmanager
    async def _with_concurrency_limit(self):
        """并发限制上下文管理器"""
        async with self._semaphore:
            yield

    async def _retry_api_call(self, api_func, *args, **kwargs):
        """带重试机制和超时的API调用"""
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                async with self._with_concurrency_limit():
                    # 添加超时控制
                    return await asyncio.wait_for(
                        api_func(*args, **kwargs),
                        timeout=self.config.timeout
                    )
            except asyncio.TimeoutError:
                last_exception = TimeoutError(f"API调用超时，超时时间: {self.config.timeout}秒")
                logger.warning(f"API调用超时，第 {attempt + 1}/{self.config.max_retries} 次重试")
            except Exception as e:
                last_exception = e

            if attempt < self.config.max_retries - 1 and last_exception is not None:
                wait_time = self.config.retry_delay * (2 ** attempt)  # 指数退避
                logger.warning(
                    f"API调用失败，第 {attempt + 1}/{self.config.max_retries} 次重试，等待 {wait_time:.1f}秒: {last_exception}"
                )
                await asyncio.sleep(wait_time)

        logger.error(f"API调用失败，已达到最大重试次数 {self.config.max_retries}: {last_exception}")
        raise last_exception

    def _log_task_results(self, results: List[Any], task_name: str) -> None:
        """记录任务执行结果"""
        success_count = 0
        error_count = 0

        for result in results:
            if isinstance(result, Exception):
                error_count += 1
            else:
                success_count += 1

        logger.info(f"{task_name}处理完成: 成功 {success_count}, 失败 {error_count}")

        # 记录详细错误
        if error_count > 0:
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.debug(f"任务 {i} 失败: {result}")

    @staticmethod
    def _normalize_whitelist(values: Optional[List[str]]) -> Optional[Set[str]]:
        if not values:
            return None
        normalized = {
            str(value).strip()
            for value in values
            if str(value).strip()
        }
        return normalized or None

    @staticmethod
    def _filter_entities_by_whitelist(
        entities: List[Any],
        attr_name: str,
        whitelist: Optional[Set[str]],
    ) -> List[Any]:
        if whitelist is None:
            return entities
        return [
            entity
            for entity in entities
            if str(getattr(entity, attr_name, "")).strip() in whitelist
        ]

    async def _process_friend_history(self, friend: FriendData, max_observations: int) -> None:
        """处理单个好友的历史消息"""
        try:
            # 获取好友历史消息
            history_response = await self._retry_api_call(
                self.adapter.get_friend_msg_history,
                user_id=friend.user_id,
                count=max_observations,
                reverse_order=False  # 从最新开始
            )

            if not history_response.data or not history_response.data.messages:
                logger.debug(f"好友 {friend.user_id} 无历史消息")
                return

            # 将消息推入队列
            for msg_data in history_response.data.messages:
                logger.debug(f"消息数据类型: {type(msg_data)}, 内容: {msg_data}")
                if isinstance(msg_data, tuple):
                    logger.warning(f"消息数据是元组而不是对象: {msg_data}")
                    continue

                try:
                    self._friend_queue.push_history(str(friend.user_id), msg_data)
                except Exception as e:
                    logger.error(f"推送好友 {friend.user_id} 消息到队列时出错: {e}", exc_info=True)
                    continue

            processed_count = len(history_response.data.messages) - sum(1 for msg in history_response.data.messages if isinstance(msg, tuple))
            logger.debug(f"已处理好友 {friend.user_id} 的 {processed_count} 条历史消息（跳过 {len(history_response.data.messages) - processed_count} 条元组消息）")

        except Exception as e:
            logger.error(f"处理好友 {friend.user_id} 历史消息时出错: {e}", exc_info=True)

    async def _process_group_history(self, group: GroupData, max_observations: int) -> None:
        """处理单个群的历史消息"""
        try:
            # 获取群历史消息
            history_response = await self._retry_api_call(
                self.adapter.get_group_msg_history,
                group_id=group.group_id,
                count=max_observations,
                reverse_order=False  # 从最新开始
            )

            if not history_response.data or not history_response.data.messages:
                logger.debug(f"群 {group.group_id} 无历史消息")
                return

            # 将消息推入队列
            for msg_data in history_response.data.messages:
                logger.debug(f"消息数据类型: {type(msg_data)}, 内容: {msg_data}")
                if isinstance(msg_data, tuple):
                    logger.warning(f"消息数据是元组而不是对象: {msg_data}")
                    continue

                try:
                    self._group_queue.push_history(str(group.group_id), msg_data)
                except Exception as e:
                    logger.error(f"推送群 {group.group_id} 消息到队列时出错: {e}", exc_info=True)
                    continue

            processed_count = len(history_response.data.messages) - sum(1 for msg in history_response.data.messages if isinstance(msg, tuple))
            logger.debug(f"已处理群 {group.group_id} 的 {processed_count} 条历史消息（跳过 {len(history_response.data.messages) - processed_count} 条元组消息）")

        except Exception as e:
            logger.error(f"处理群 {group.group_id} 历史消息时出错: {e}", exc_info=True)

    async def _collect_user_ids_from_messages(self) -> Set[str]:
        """从所有消息队列中收集用户ID"""
        user_ids: Set[str] = set()

        # 从私聊队列收集
        if self._friend_queue:
            for key in self._friend_queue.get_all_keys():
                user_ids.add(key)

        # 从群聊队列收集
        if self._group_queue:
            for key in self._group_queue.get_all_keys():
                queue = self._group_queue[key]
                for msg in queue:
                    if isinstance(msg, GroupMessage):
                        user_ids.add(str(msg.user_id))

        return user_ids

    async def _update_user_profiles(
        self,
        user_ids: Set[str],
        profile_service: UserProfileService,
    ) -> None:
        """补齐并按配置刷新用户信息。"""
        if not user_ids:
            logger.info("消息队列中未发现需要更新的用户信息")
            return

        tasks = [
            profile_service.ensure_user_profile(user_id)
            for user_id in sorted(user_ids)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for user_id, result in zip(sorted(user_ids), results):
            if isinstance(result, Exception):
                logger.error(f"更新用户 {user_id} 信息失败: {result}")
            elif result is not None:
                success_count += 1

        logger.info(
            f"用户信息更新完成，成功处理 {success_count}/{len(user_ids)} 个用户信息"
        )

    async def _insert_or_update_group_to_db(self, uow, group: GroupData) -> None:
        """插入或更新群信息到 group_data 表"""
        try:
            await uow.profiles.upsert_group(
                group_id=str(group.group_id) if group.group_id else "",
                group_name=group.group_name or "",
                profile=group.group_memo or "",
                is_quite=False,
            )
            logger.debug(f"群 {group.group_id} 信息已存入数据库")
        except Exception as e:
            logger.error(f"插入或更新群 {group.group_id} 到数据库时出错: {e}")
