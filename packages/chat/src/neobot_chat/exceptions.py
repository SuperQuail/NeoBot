"""自定义异常体系"""


class ChatError(Exception):
    """所有 chat 相关异常的基类"""


class ProviderError(ChatError):
    """Provider 相关错误（API 调用失败等）"""


class ToolError(ChatError):
    """工具执行错误"""


class GraphError(ChatError):
    """Graph 执行错误"""


class ValidationError(ChatError):
    """输入验证错误"""
