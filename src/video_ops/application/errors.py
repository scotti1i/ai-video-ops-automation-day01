"""可直接映射成用户可执行提示的业务错误。"""


class ApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class PlatformError(ApplicationError):
    def __init__(
        self,
        operation: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        raw_ref: str | None = None,
    ):
        super().__init__(code, message, retryable=retryable)
        self.operation = operation
        self.raw_ref = raw_ref
