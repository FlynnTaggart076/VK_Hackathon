"""Housing engine v1 contract. Processing functions are scheduled for E1-E3."""

from datetime import datetime

from .dto import (
    AnswerResult, BillData, CompareRequest, ComparisonResult, DocumentInput,
    DraftRequest, DraftResult, ExplainRequest, ExtractionConfig, ExtractionResult,
    KnowledgeBundle, QuestionRequest, ReceiptExplanation, ValidationResult,
)

__version__ = "0.1.0"


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


def _not_implemented() -> None:
    raise NotImplementedError("housing_engine processing starts in E1; E0 publishes DTO only")


def extract_receipt(document: DocumentInput, config: ExtractionConfig) -> ExtractionResult:
    _not_implemented()


def validate_bill(bill: BillData) -> ValidationResult:
    _not_implemented()


def explain_receipt(request: ExplainRequest, knowledge: KnowledgeBundle) -> ReceiptExplanation:
    _not_implemented()


def compare_receipts(request: CompareRequest, knowledge: KnowledgeBundle) -> ComparisonResult:
    _not_implemented()


def answer_question(request: QuestionRequest, knowledge: KnowledgeBundle) -> AnswerResult:
    _not_implemented()


def compose_draft(request: DraftRequest, knowledge: KnowledgeBundle) -> DraftResult:
    _not_implemented()


def load_knowledge(path: str, now: datetime) -> KnowledgeBundle:
    _not_implemented()
