"""Housing engine v1 public API; later-stage functions remain explicit stubs."""

from datetime import datetime

from .dto import (
    AnswerResult, BillData, CompareRequest, ComparisonResult, DocumentInput,
    DraftRequest, DraftResult, ExplainRequest, ExtractionConfig, ExtractionResult,
    KnowledgeBundle, QuestionRequest, ReceiptExplanation, ValidationResult,
)
from .errors import EngineError
from .comparison import compare_receipts
from .extraction import extract_receipt
from .explanation import explain_receipt
from .receipts import validate_bill

__version__ = "0.1.0"


def _not_implemented() -> None:
    raise NotImplementedError("housing_engine function is not implemented in this stage")


def answer_question(request: QuestionRequest, knowledge: KnowledgeBundle) -> AnswerResult:
    _not_implemented()


def compose_draft(request: DraftRequest, knowledge: KnowledgeBundle) -> DraftResult:
    _not_implemented()


def load_knowledge(path: str, now: datetime) -> KnowledgeBundle:
    _not_implemented()
