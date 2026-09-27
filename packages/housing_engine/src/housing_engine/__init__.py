"""Housing engine v1 contract. Processing functions are scheduled for E1-E3."""

from datetime import datetime

from .dto import (
    AnswerResult, BillData, CompareRequest, ComparisonResult, DocumentInput,
    DraftRequest, DraftResult, ExplainRequest, ExtractionConfig, ExtractionResult,
    KnowledgeBundle, QuestionRequest, ReceiptExplanation, ValidationResult,
)
from .errors import EngineError
from .extraction import extract_receipt
from .explanation import explain_receipt
from .receipts import validate_bill

__version__ = "0.1.0"


def _not_implemented() -> None:
    raise NotImplementedError("housing_engine processing starts in E1; E0 publishes DTO only")


def compare_receipts(request: CompareRequest, knowledge: KnowledgeBundle) -> ComparisonResult:
    _not_implemented()


def answer_question(request: QuestionRequest, knowledge: KnowledgeBundle) -> AnswerResult:
    _not_implemented()


def compose_draft(request: DraftRequest, knowledge: KnowledgeBundle) -> DraftResult:
    _not_implemented()


def load_knowledge(path: str, now: datetime) -> KnowledgeBundle:
    _not_implemented()
