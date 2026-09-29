"""自定义异常体系"""


class ChatError(Exception):
    """所有 chat 相关异常的基类"""


class ProviderError(ChatError):
    """Provider 相关错误（API 调用失败等）"""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        original: BaseException | None = None,
        iteration: int = 0,
        stream_started: bool = False,
    ) -> None:
        """记录「哪一次调用、哪个 provider、是否已经产出流式内容」。

        Agent 把 provider 异常包装后上抛（不再降级成 assistant 文本），调用方据此
        决定降级文案：`stream_started=True` 时用户可能已收到半截输出，不能重放请求。
        """
        super().__init__(message)
        self.provider = provider
        self.original = original
        self.iteration = iteration
        self.stream_started = stream_started

    @property
    def original_name(self) -> str:
        """原始异常类型名（用于日志与降级文案）。"""
        return type(self.original).__name__ if self.original is not None else ""

    def __str__(self) -> str:
        base = super().__str__()
        if self.provider or self.original_name:
            return f"{base} (provider={self.provider or '?'}, cause={self.original_name or '?'})"
        return base


class NativeVisionUnsupportedError(ProviderError):
    """图片输入被模型明确拒绝，或当前 provider 无法无损传递图片。"""


class ToolError(ChatError):
    """工具执行错误"""


class GraphError(ChatError):
    """Graph 执行错误"""


class ValidationError(ChatError):
    """输入验证错误"""
