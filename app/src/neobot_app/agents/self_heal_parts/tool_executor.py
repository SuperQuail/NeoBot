"""自修复工具执行器：组合各工具分组的入口类。"""

from __future__ import annotations

from neobot_chat.schema.protocol import ToolExecutor

from .file_report_tools import SelfHealToolFileReportMixin
from .sandbox_tools import SelfHealToolSandboxMixin
from .source_tools import SelfHealToolSourceMixin
from .tool_core import SelfHealToolCoreMixin
from .tool_definitions import SelfHealToolDefinitionsMixin


class SelfHealToolExecutor(
    SelfHealToolDefinitionsMixin,
    SelfHealToolCoreMixin,
    SelfHealToolSourceMixin,
    SelfHealToolFileReportMixin,
    SelfHealToolSandboxMixin,
    ToolExecutor,
):
    """自修复 Agent 可用的工具集。

    读取类工具：
      - read_errors          : sink 捕获的错误快照
      - read_log_tail        : neobot.log 文件尾部
      - read_source_code     : 读取 Bot 源码文件（白名单）
      - search_source_code   : 在 app/packages 中按正则搜索
      - list_files / read_file / write_debug_report / list_debug_reports /
        read_debug_report : 沙箱文件读写（调试报告存放在沙箱内）
      - run_python / parse_image : 诊断辅助工具

    修复钩子（安全子集）：
      - clear_drawing_cooldown
      - trigger_image_cleanup

    Web：
      - search_web            : WebSearchExecutor（研究模式）
      - read_search_result    : 读取已索引页面
      - search_status         : 网页搜索会话状态

    收尾：
      - submit_resolution      : 提交诊断结论（对应 submit_solution）
    """
