"""自定义异常体系"""


class ChatError(Exception):
    """所有 chat 相关异常的基类"""


class ProviderError(ChatError):
    """Provider 相关错误（API 调用失败等）"""


class NativeVisionUnsupportedError(ProviderError):
    """图片输入被模型明确拒绝，或当前 provider 无法无损传递图片。"""


class ToolError(ChatError):
    """工具执行错误"""


class GraphError(ChatError):
    """Graph 执行错误"""


class ValidationError(ChatError):
    """输入验证错误"""
