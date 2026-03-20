"""聊天流管理模块"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from contextlib import asynccontextmanager

from neobot_adapter import OneBotAdapter
from neobot_adapter.model.response import (
    FriendData,
    GroupData,
)
from neobot_adapter.model.message import PrivateMessage, GroupMessage

from neobot_app.database.sqlite import Database
from neobot_app.message.queue import MessageQueue

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
        config: Optional[ChatStreamConfig] = None,
        group_message_queue: Optional[MessageQueue] = None,
        friend_message_queue: Optional[MessageQueue] = None,
    ):
        """初始化聊天流管理器"""
        self.adapter = adapter
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

        # 如果队列未通过构造函数注入，则自行创建
        if self._group_queue is None:
            self._group_queue = MessageQueue(max_size=max_group_obs)
        if self._friend_queue is None:
            self._friend_queue = MessageQueue(max_size=max_friend_obs)

        logger.info(f"群聊观察上限: {max_group_obs}, 私聊观察上限: {max_friend_obs}")

        try:
            # 获取好友列表
            logger.info("正在获取好友列表...")
            friend_response = await self._retry_api_call(self.adapter.get_friend_list)
            friends = friend_response.data if friend_response.data else []
            logger.info(f"获取到 {len(friends)} 个好友")

            # 获取群列表
            logger.info("正在获取群列表...")
            group_response = await self._retry_api_call(self.adapter.get_group_list)
            groups = group_response.data if group_response.data else []
            logger.info(f"获取到 {len(groups)} 个群")

            # 将群信息存入数据库
            if groups:
                logger.info("开始将群信息存入数据库...")
                from neobot_app.database.sqlite import get_db
                db = get_db()

                for group in groups:
                    try:
                        self._insert_or_update_group_to_db(db, group)
                    except Exception as e:
                        logger.error(f"存储群 {group.group_id} 信息时出错: {e}")
                logger.info(f"群信息存储完成，共处理 {len(groups)} 个群")

            # 并发处理好友历史消息
            logger.info(f"开始获取好友历史消息，并发限制: {self.config.concurrent_limit}...")
            friend_tasks = [
                self._process_friend_history(friend, max_friend_obs)
                for friend in friends
            ]
            friend_results = await asyncio.gather(*friend_tasks, return_exceptions=True)
            self._log_task_results(friend_results, "好友历史消息")

            # 并发处理群历史消息
            logger.info(f"开始获取群历史消息，并发限制: {self.config.concurrent_limit}...")
            group_tasks = [
                self._process_group_history(group, max_group_obs)
                for group in groups
            ]
            group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
            self._log_task_results(group_results, "群历史消息")

            # 收集所有用户ID并更新缺失的用户信息
            logger.info("开始收集用户ID并更新缺失的用户信息...")
            user_ids = await self._collect_user_ids_from_messages()
            await self._update_missing_users(user_ids)

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
                    self._friend_queue.push(str(friend.user_id), msg_data)
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
                    self._group_queue.push(str(group.group_id), msg_data)
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

    async def _update_missing_users(self, user_ids: Set[str]) -> None:
        """更新缺失的用户信息到数据库"""
        from neobot_app.database.sqlite import get_db
        db = get_db()

        missing_users = []

        # 检查哪些用户不在数据库中
        for user_id in user_ids:
            if not self._user_exists_in_db(db, user_id):
                missing_users.append(user_id)

        if not missing_users:
            logger.info("所有用户都已存在于数据库中")
            return

        logger.info(f"发现 {len(missing_users)} 个缺失的用户，开始获取信息...")

        # 并发获取用户信息
        tasks = [self._get_stranger_info_and_store(user_id, db) for user_id in missing_users]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查结果
        success_count = 0
        for user_id, result in zip(missing_users, results):
            if isinstance(result, Exception):
                logger.error(f"获取用户 {user_id} 信息失败: {result}")
            else:
                success_count += 1

        logger.info(f"用户信息更新完成，成功获取 {success_count}/{len(missing_users)} 个用户信息")

    def _user_exists_in_db(self, db: Database, user_id: str) -> bool:
        """检查用户是否存在于 USER_DATA 表中"""
        try:
            cursor = db.execute("SELECT 1 FROM USER_DATA WHERE user_id = ? LIMIT 1", (user_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查用户 {user_id} 是否存在时出错: {e}")
            return False

    def _group_exists_in_db(self, db: Database, group_id: str) -> bool:
        """检查群是否存在于 GROUP_DATA 表中"""
        try:
            cursor = db.execute("SELECT 1 FROM GROUP_DATA WHERE group_id = ? LIMIT 1", (group_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查群 {group_id} 是否存在时出错: {e}")
            return False

    def _insert_user_to_db(self, db: Database, user_id: str, user_info: Dict[str, Any]) -> None:
        """插入用户信息到 USER_DATA 表"""
        try:
            db.execute(
                """INSERT OR IGNORE INTO USER_DATA
                   (user_id, nick_name, relation_ship, profile, birthday, sex, city, country, labs, remark, age, long_nick)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    user_info.get("nick_name", ""),
                    user_info.get("relation_ship", ""),
                    user_info.get("profile", ""),
                    user_info.get("birthday", ""),
                    user_info.get("sex", ""),
                    user_info.get("city", ""),
                    user_info.get("country", ""),
                    user_info.get("labs", ""),
                    user_info.get("remark", ""),
                    user_info.get("age", 0),
                    user_info.get("long_nick", ""),
                ),
            )
            db.commit()
            logger.info(f"用户 {user_id} 已插入数据库")
        except Exception as e:
            logger.error(f"插入用户 {user_id} 到数据库时出错: {e}")
            db.rollback()

    def _insert_or_update_group_to_db(self, db: Database, group: GroupData) -> None:
        """插入或更新群信息到 GROUP_DATA 表"""
        try:
            db.execute(
                """INSERT OR REPLACE INTO GROUP_DATA
                   (group_id, group_name, profile, is_quite)
                   VALUES (?, ?, ?, ?)""",
                (
                    str(group.group_id) if group.group_id else "",
                    group.group_name or "",
                    group.group_memo or "",
                    0,
                ),
            )
            db.commit()
            logger.debug(f"群 {group.group_id} 信息已存入数据库")
        except Exception as e:
            logger.error(f"插入或更新群 {group.group_id} 到数据库时出错: {e}")
            db.rollback()

    async def _get_stranger_info_and_store(self, user_id: str, db: Database) -> None:
        """获取陌生人信息并存储到数据库"""
        try:
            response = await self._retry_api_call(
                self.adapter.get_stranger_info,
                int(user_id),
            )
            if response.data:
                user_info = {
                    "nick_name": response.data.nickname or "",
                    "sex": response.data.sex.value if response.data.sex else "",
                    "age": response.data.age or 0,
                    "city": response.data.city or "",
                    "country": response.data.country or "",
                    "long_nick": response.data.long_nick or "",
                    "remark": response.data.remark or "",
                    "relation_ship": "",
                    "profile": "",
                    "birthday": "",
                    "labs": ",".join(response.data.labs) if response.data.labs else "",
                }
                if response.data.birthday_year and response.data.birthday_month and response.data.birthday_day:
                    user_info["birthday"] = f"{response.data.birthday_year}-{response.data.birthday_month}-{response.data.birthday_day}"

                self._insert_user_to_db(db, user_id, user_info)
            else:
                logger.warning(f"获取用户 {user_id} 信息返回空数据")
        except Exception as e:
            logger.error(f"获取用户 {user_id} 信息时出错: {e}", exc_info=True)
