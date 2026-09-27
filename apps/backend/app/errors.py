class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False,
                 details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
