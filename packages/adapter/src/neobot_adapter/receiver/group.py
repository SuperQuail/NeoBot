import os
import queue
import json
from neobot_adapter.utils.env import get_websocket_url
from neobot_adapter.utils.logger import get_module_logger
import asyncio
import threading
import websockets
from typing import Optional

logger = get_module_logger("adapter_receiver")

class GroupMessageReceiver:
    """群消息接收器"""

    def __init__(self , max_queue_size: int = 1000):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.message_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)

    def _run_thread_target(self):
        """线程目标函数：运行异步事件循环"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._listen())
        finally:
            self.loop.close()
            self.loop = None
            logger.info("群消息接收器已停止")
    
    def start(self)->None:
        """启动群消息接收器守护线程"""
        if self.thread and self.thread.is_alive():
            logger.error("意外的群消息接收器二次启动")
            return
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_thread_target, daemon=True)
        self.thread.start()
        logger.info(f"群消息接收器已启动，线程 ID:{self.thread.native_id}")

    def stop(self):
        """停止群消息接收器守护线程"""
        logger.info("正在停止群消息接收器线程")
        self._stop_event.set()
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close_connection(), self.loop)
        if self.thread:
            self.thread.join(timeout=5)

    def get_message(self,block: bool = True, timeout: Optional[float] = None):
        """获取一条群消息 (如果收到消息)"""
        try :
            return self.message_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            logger.debug("没有收到群消息")
            return None



    async def _listen(self):
        """监听"""
        request = {
            "action":"get_group_message",
            "params": {
                "no_cache":False
            }
        }
        while not self._stop_event.is_set():
            logger.info("正在尝试连接至框架websocket")
            try:
                async with websockets.connect(get_websocket_url()) as websocket:
                    logger.info("已连接至框架websocket")
                    while not self._stop_event.is_set():
                        try:
                            async for message in websocket:
                                data = json.loads(message)
                                if data:
                                    self.message_queue.put_nowait(data)
                                    logger.debug(f"收到群消息: {data},已加入队列")

                        except websockets.ConnectionClosed:
                            logger.info("已断开与框架websocket的连接,3秒后尝试重连")
                            break
                        except Exception as e:
                            logger.error(f"群消息接收异常:{e}")
            except Exception as e:
                logger.info("未连接到框架websocket,将在3秒后重试")
                logger.debug(f"异常信息:{e}")
                for _ in range(3):
                    if self._stop_event.wait(1):
                        return



    async def _close_connection(self):
        pass

os.environ["NEO_BOT_ADAPTER_HOST"] = "127.0.0.1"
os.environ["NEO_BOT_ADAPTER_PORT"] = "8091"
GroupMessageReceiver().start()
while True:
    try:
        #logger.info("正在等待群消息...")
        msg = GroupMessageReceiver().get_message(timeout=1.0)  # 每秒检查一次
        logger.debug(f"已收到群消息: {msg}")

    except KeyboardInterrupt as e:
        logger.error(f"退出测试")
        GroupMessageReceiver().stop()
        break