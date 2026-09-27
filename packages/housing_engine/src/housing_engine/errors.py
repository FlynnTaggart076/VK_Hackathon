"""Safe engine errors mapped to jobs or HTTP by the backend adapter."""


class EngineError(Exception):
    CODES = frozenset({
        "OCR_TIMEOUT", "CORRUPT_DOCUMENT", "ENCRYPTED_PDF", "RESOURCE_LIMIT",
        "INVALID_BILL", "INCOMPARABLE_RECEIPTS", "KNOWLEDGE_INVALID",
        "INTERNAL_ENGINE_ERROR",
    })

    def __init__(self, code: str, message: str, retryable: bool = False):
        if code not in self.CODES:
            raise ValueError("Unknown engine error code")
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)
