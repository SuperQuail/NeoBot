"""计费段：按模型绑定的计价脚本全局策略。"""

from dataclasses import dataclass, field


@dataclass
class Billing:
    """消耗计费配置（spec(4) Part A）。

    计价脚本**按模型条目绑定**（models.registry[].billing_script）；本段只放全局执行
    策略，默认关闭 = 全部模型走既有固定计费公式。
    """

    enabled: bool = field(
        default=False,
        metadata={
            "description": "是否启用按模型绑定的计价脚本。关闭时全部模型走既有固定计费公式"
            "（零额外开销、零风险）；开启后仅对填写了 billing_script 的模型生效"
        },
    )
    timeout_ms: int = field(
        default=200,
        metadata={
            "description": "单次脚本求值超时（毫秒）。超时即放弃脚本结果、改用固定计费并告警；"
            "过大会直接阻塞回复管线"
        },
    )
    reload_on_change: bool = field(
        default=True,
        metadata={
            "description": "计费脚本文件的修改时间（纳秒）或大小变化时自动重载，无需重启进程"
        },
    )
    record_detail: bool = field(
        default=True,
        metadata={
            "description": "是否把脚本返回的分项（components / note）写入 cost_detail 列；"
            "关闭只存金额，节省空间"
        },
    )
