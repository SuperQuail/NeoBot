from pydantic import BaseModel
from . import basic
from typing import Optional

class General(BaseModel):
    """所有上报都将包含下面的有效通用数据"""
    time: Optional[int]  # 事件发生的unix时间戳
    self_id: Optional[int]  # 收到事件的机器人的QQ号
    post_type: Optional[basic.Post_Type]  # 上报类型
