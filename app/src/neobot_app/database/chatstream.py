"""聊天流管理模块

负责初始化消息队列，获取历史消息，并维护用户信息数据库。
支持并发控制和重试机制。
"""

import asyncio
import logging
import time
from typing import List, Set, Dict, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
from contextlib import asynccontextmanager

# 导入 adapter 模块
from neobot_adapter.request.private import get_friend_list,get_stranger_info
from neobot_adapter.request.group import get_group_list
from neobot_adapter.request.message import (
    get_friend_msg_history,
    get_group_msg_history,
)
from neobot_adapter.model.response import (
    GetFriendListResponse,
    GetGroupListResponse,
    GetHistoryMsgListResponse,
    FriendData,
    GroupData,
    GetSignalMsgData,
    StrangerInfoResponse,
)
from neobot_adapter.model.message import PrivateMessage, GroupMessage

# 导入本地模块
# 注意：bot_config 在方法内部延迟导入以避免循环导入
from neobot_app.database.sqlite import Database

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

    def __init__(self, config: Optional[ChatStreamConfig] = None):
        """初始化聊天流管理器"""
        self.config = config or ChatStreamConfig()
        self._semaphore = asyncio.Semaphore(self.config.concurrent_limit)
        self._initialized = False

    async def initialize(self) -> None:
        """初始化聊天流

        1. 初始化消息队列
        2. 获取所有好友和群列表
        3. 并发获取历史消息并填充队列
        4. 收集所有用户ID并更新缺失的用户信息到数据库
        """
        if self._initialized:
            logger.warning("聊天流已初始化，跳过重复初始化")
            return

        logger.info("开始初始化聊天流...")

        # 初始化消息队列
        self._init_message_queues()

        # 获取配置（延迟导入以避免循环导入）
        from neobot_app.config.instance import bot_config
        max_group_obs = bot_config.chat.max_group_chat_observations
        max_friend_obs = bot_config.chat.max_friend_chat_observations

        logger.info(f"群聊观察上限: {max_group_obs}, 私聊观察上限: {max_friend_obs}")

        try:
            # 获取好友列表
            logger.info("正在获取好友列表...")
            friend_response = await self._retry_api_call(get_friend_list)
            friends = friend_response.data if friend_response.data else []
            logger.info(f"获取到 {len(friends)} 个好友")

            # 获取群列表
            logger.info("正在获取群列表...")
            group_response = await self._retry_api_call(get_group_list)
            groups = group_response.data if group_response.data else []
            logger.info(f"获取到 {len(groups)} 个群")

            # 将群信息存入数据库
            if groups:
                logger.info("开始将群信息存入数据库...")
                # 导入数据库实例（延迟导入以避免循环导入）
                from neobot_app.config.instance import db_instance
                db = db_instance

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

            logger.info("历史消息获取完成，开始收集用户ID...")

            # 收集所有用户ID
            user_ids = await self._collect_user_ids_from_messages()
            logger.info(f"共收集到 {len(user_ids)} 个用户ID")

            # 更新缺失的用户信息
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

    def _init_message_queues(self) -> None:
        """初始化消息队列"""
        # 导入 MessageQueue 类
        from neobot_app.message.queue import MessageQueue

        # 导入 instance 模块以修改其变量（延迟导入以避免循环导入）
        import neobot_app.config.instance as instance_module

        # 导入 bot_config
        from neobot_app.config.instance import bot_config

        # 注意：group_message_queue 和 friend_message_queue 是从 neobot_app.config.instance 导入的模块级变量
        # 我们需要修改原始模块中的变量，而不仅仅是本地引用
        if instance_module.group_message_queue is None:
            max_group_obs = bot_config.chat.max_group_chat_observations
            instance_module.group_message_queue = MessageQueue(max_size=max_group_obs)
            logger.info(f"群消息队列已初始化，最大大小: {max_group_obs}")

        if instance_module.friend_message_queue is None:
            max_friend_obs = bot_config.chat.max_friend_chat_observations
            instance_module.friend_message_queue = MessageQueue(max_size=max_friend_obs)
            logger.info(f"私聊消息队列已初始化，最大大小: {max_friend_obs}")

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
                get_friend_msg_history,
                user_id=friend.user_id,
                count=max_observations,
                reverse_order=False  # 从最新开始
            )

            if not history_response.data or not history_response.data.messages:
                logger.debug(f"好友 {friend.user_id} 无历史消息")
                return

            # 导入消息队列（延迟导入以避免循环导入）
            from neobot_app.config.instance import friend_message_queue

            # 将消息推入队列
            for msg_data in history_response.data.messages:
                # 调试：检查 msg_data 类型
                logger.debug(f"消息数据类型: {type(msg_data)}, 内容: {msg_data}")
                if isinstance(msg_data, tuple):
                    logger.warning(f"消息数据是元组而不是对象: {msg_data}")
                    continue

                # 使用队列的转换方法，直接传递 msg_data
                try:
                    friend_message_queue.push(str(friend.user_id), msg_data)
                except Exception as e:
                    logger.error(f"推送好友 {friend.user_id} 消息到队列时出错: {e}", exc_info=True)
                    continue

            # 由于我们可能跳过了一些消息，需要重新计算实际处理的数量
            processed_count = len(history_response.data.messages) - sum(1 for msg in history_response.data.messages if isinstance(msg, tuple))
            logger.debug(f"已处理好友 {friend.user_id} 的 {processed_count} 条历史消息（跳过 {len(history_response.data.messages) - processed_count} 条元组消息）")

        except Exception as e:
            logger.error(f"处理好友 {friend.user_id} 历史消息时出错: {e}", exc_info=True)

    async def _process_group_history(self, group: GroupData, max_observations: int) -> None:
        """处理单个群的历史消息"""
        try:
            # 获取群历史消息
            history_response = await self._retry_api_call(
                get_group_msg_history,
                group_id=group.group_id,
                count=max_observations,
                reverse_order=False  # 从最新开始
            )

            if not history_response.data or not history_response.data.messages:
                logger.debug(f"群 {group.group_id} 无历史消息")
                return

            # 导入消息队列（延迟导入以避免循环导入）
            from neobot_app.config.instance import group_message_queue

            # 将消息推入队列
            for msg_data in history_response.data.messages:
                # 调试：检查 msg_data 类型
                logger.debug(f"消息数据类型: {type(msg_data)}, 内容: {msg_data}")
                if isinstance(msg_data, tuple):
                    logger.warning(f"消息数据是元组而不是对象: {msg_data}")
                    continue

                # 使用队列的转换方法，直接传递 msg_data
                try:
                    group_message_queue.push(str(group.group_id), msg_data)
                except Exception as e:
                    logger.error(f"推送群 {group.group_id} 消息到队列时出错: {e}", exc_info=True)
                    continue

            # 由于我们可能跳过了一些消息，需要重新计算实际处理的数量
            processed_count = len(history_response.data.messages) - sum(1 for msg in history_response.data.messages if isinstance(msg, tuple))
            logger.debug(f"已处理群 {group.group_id} 的 {processed_count} 条历史消息（跳过 {len(history_response.data.messages) - processed_count} 条元组消息）")

        except Exception as e:
            logger.error(f"处理群 {group.group_id} 历史消息时出错: {e}", exc_info=True)

    async def _collect_user_ids_from_messages(self) -> Set[str]:
        """从所有消息队列中收集用户ID"""
        # 导入消息队列（延迟导入以避免循环导入）
        from neobot_app.config.instance import friend_message_queue, group_message_queue

        user_ids = set()

        # 从私聊队列收集
        for key in friend_message_queue.get_all_keys():
            # 私聊队列的 key 就是好友的 user_id
            user_ids.add(key)

        # 从群聊队列收集
        for key in group_message_queue.get_all_keys():
            # 需要遍历该群的所有消息，收集 user_id
            queue = group_message_queue[key]
            for msg in queue:
                if isinstance(msg, GroupMessage):
                    user_ids.add(str(msg.user_id))

        return user_ids

    async def _update_missing_users(self, user_ids: Set[str]) -> None:
        """更新缺失的用户信息到数据库"""
        # 导入数据库实例（延迟导入以避免循环导入）
        from neobot_app.config.instance import db_instance

        db = db_instance
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
            # 使用 INSERT OR REPLACE 来更新已存在的记录
            db.execute(
                """INSERT OR REPLACE INTO GROUP_DATA 
                   (group_id, group_name, profile, is_quite)
                   VALUES (?, ?, ?, ?)""",
                (
                    str(group.group_id) if group.group_id else "",
                    group.group_name or "",
                    group.group_memo or "",  # 使用群介绍作为 profile 字段
                    0,  # 默认 is_quite 为 0（false）
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
            response = await self._retry_api_call(get_stranger_info, int(user_id))
            if response.data:
                user_info = {
                    "nick_name": response.data.nickname or "",
                    "sex": response.data.sex.value if response.data.sex else "",
                    "age": response.data.age or 0,
                    "city": response.data.city or "",
                    "country": response.data.country or "",
                    "long_nick": response.data.long_nick or "",
                    "remark": response.data.remark or "",
                    "relation_ship": "",  # 接口没有这个字段
                    "profile": "",  # 接口没有这个字段
                    "birthday": "",  # 接口可能有生日字段，但需要从 birthday_year/month/day 组合
                    "labs": ",".join(response.data.labs) if response.data.labs else "",
                }
                # 如果有生日信息，组合成字符串
                if response.data.birthday_year and response.data.birthday_month and response.data.birthday_day:
                    user_info["birthday"] = f"{response.data.birthday_year}-{response.data.birthday_month}-{response.data.birthday_day}"

                self._insert_user_to_db(db, user_id, user_info)
            else:
                logger.warning(f"获取用户 {user_id} 信息返回空数据")
        except Exception as e:
            logger.error(f"获取用户 {user_id} 信息时出错: {e}", exc_info=True)


# 全局聊天流管理器实例
_chat_stream_manager: Optional[ChatStreamManager] = None

def init_chat_stream(config: Optional[ChatStreamConfig] = None) -> ChatStreamManager:
    """初始化聊天流管理器

    Args:
        config: 聊天流配置，如果为None则使用默认配置

    Returns:
        ChatStreamManager: 聊天流管理器实例
    """
    global _chat_stream_manager

    if _chat_stream_manager is None:
        _chat_stream_manager = ChatStreamManager(config)

    return _chat_stream_manager

def get_chat_stream_manager() -> ChatStreamManager:
    """获取聊天流管理器实例

    Returns:
        ChatStreamManager: 聊天流管理器实例
    """
    global _chat_stream_manager

    if _chat_stream_manager is None:
        # 使用默认配置创建实例
        _chat_stream_manager = ChatStreamManager()

    return _chat_stream_manager


# 向后兼容的快捷函数
async def initialize_chat_stream() -> None:
    """初始化聊天流（向后兼容）

    使用默认配置初始化聊天流
    """
    manager = get_chat_stream_manager()
    await manager.initialize()

async def update_chat_stream() -> None:
    """更新聊天流（向后兼容）

    定期调用此函数来更新消息队列和用户信息
    """
    manager = get_chat_stream_manager()
    await manager.update()


if __name__ == "__main__":
    # 测试代码
    import asyncio

    async def test():
        # 使用默认配置
        manager = init_chat_stream()
        await manager.initialize()

        # 导入消息队列（延迟导入以避免循环导入）
        from neobot_app.config.instance import group_message_queue, friend_message_queue

        print("聊天流初始化测试完成")
        print(f"群消息队列大小: {group_message_queue.size()}")
        print(f"私聊消息队列大小: {friend_message_queue.size()}")

        # 测试向后兼容函数
        await update_chat_stream()
        print("聊天流更新测试完成")

    asyncio.run(test())
