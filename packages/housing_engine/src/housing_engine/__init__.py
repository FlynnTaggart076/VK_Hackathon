"""Housing engine v1 public API."""

from .dto import (
    AnswerResult, BillData, CompareRequest, ComparisonResult, DocumentInput,
    DraftRequest, DraftResult, ExplainRequest, ExtractionConfig, ExtractionResult,
    KnowledgeBundle, QuestionRequest, ReceiptExplanation, ValidationResult,
)
from .errors import EngineError
from .comparison import compare_receipts
from .knowledge import answer_question, compose_draft, load_knowledge
from .extraction import extract_receipt
from .epd import EPD_TEMPLATE_ID, project_epd_table_candidates, project_receipt_facts
from .cohort import CohortKey, CohortObservation, CohortSummary, summarize_cohort
from .explanation import explain_receipt
from .receipts import validate_bill

__version__ = "0.1.0"
