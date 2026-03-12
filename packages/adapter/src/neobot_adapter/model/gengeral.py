from pydantic import BaseModel
from . import basic
from typing import Optional

class General(BaseModel):
    """所有上报都将包含下面的有效通用数据"""
    time: Optional[int] = None  # 事件发生的 unix 时间戳
    self_id: Optional[int] = None  # 收到事件的机器人的 QQ 号
    post_type: Optional[basic.PostType] = None  # 上报类型
