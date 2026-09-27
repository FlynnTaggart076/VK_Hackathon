// Provisional transcription of TECHNICAL_SPEC.md §§6–7. Reconcile with B's accepted OpenAPI.
export type Id = string;
export type Timestamp = string;
export type Money = string;
export type DatasetKind = 'synthetic' | 'user_provided' | 'public_reference';

export interface ApiFieldError { path: string; message: string }
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    fields: ApiFieldError[];
    details: Record<string, unknown>;
  };
  request_id: Id;
}

export interface Profile {
  role: 'owner' | 'tenant' | 'other';
  territory_id: string | null;
  onboarding_completed: boolean;
  privacy_notice_version: string | null;
  privacy_acknowledged_at: Timestamp | null;
}
export interface AuthResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: { id: Id };
  profile: Profile;
}
export interface MetaResponse {
  api_version: string;
  engine_version: string;
  knowledge_version: string;
  mode: string;
  limits: Record<string, unknown>;
  features: Record<string, unknown>;
  privacy_notice: { version: string; text: string };
}
export interface ReceiptRef { id: Id; revision: number }
export interface SourceRef {
  id: string; title: string; url: string | null; territory_id: string | null;
  verified_at: Timestamp; review_after: Timestamp; content_version: string; is_synthetic: boolean;
}
export interface NextAction {
  id: string; type: 'open_link' | 'prepare_draft' | 'select_topic' | 'navigate';
  label: string; url: string | null; topic_id: string | null; organization_id: string | null;
  source_id: string | null; target: 'receipt_upload' | 'receipt_history' | 'receipt_detail' | 'comparison' | null;
  receipt_ref: ReceiptRef | null; requires: string[];
}
export interface AnswerContext {
  territory_id: string | null; role: Profile['role']; topic_id: string | null;
  organization_id: string | null; service_code: string | null; document_kind: string | null;
  receipt_id: Id | null; receipt_revision: number | null;
}
export interface AnswerView {
  id: Id; created_at: Timestamp; stale: boolean;
  stale_reasons: ('receipt_changed' | 'source_expired' | 'knowledge_updated')[];
  status: 'answered' | 'needs_clarification' | 'unsupported'; text: string;
  topic_id: string | null; steps: string[]; sources: SourceRef[]; actions: NextAction[];
  clarification: { field: keyof AnswerContext; prompt: string; options: { value: string; label: string }[] } | null;
  limitations: string[]; knowledge_version: string; receipt_ref: ReceiptRef | null;
  dataset_kind: DatasetKind;
}
export interface Issue { code: string; severity: 'info' | 'warning' | 'error'; path: string | null; message: string }
export interface BillData {
  schema_version: '1.0'; period: string | null; currency: 'RUB'; issuer_name: string | null;
  provider_id: string | null; account_number: string | null; address_text: string | null;
  template_id: string | null; template_version: string | null;
  services: Array<{ line_id: Id; raw_name: string; service_code: string; scope: string; unit: string | null;
    unit_label: string | null; quantity: string | null; tariff: string | null; charge_amount: Money | null;
    supplier_key: string | null; segment_key: string | null; calculation_kind: string }>;
  adjustments: Array<{ adjustment_id: Id; label: string; amount: Money | null; service_line_id: Id | null; related_period: string | null }>;
  settlement: { formula_kind: 'signed_balance_v1' | 'unsupported'; opening_balance: Money | null;
    payments_credited: Money | null; penalties: Money | null; other_account_changes: Money | null;
    document_closing_balance: Money | null };
  document_current_charges: Money | null; document_total_due: Money | null;
}
export interface ReceiptView {
  id: Id; status: 'queued' | 'processing' | 'needs_review' | 'confirmed' | 'failed';
  revision: number; created_at: Timestamp; updated_at: Timestamp;
  dataset_kind: 'synthetic' | 'user_provided';
  extraction_outcome: 'recognized' | 'partial' | 'manual_required' | null;
  bill_data: BillData;
  field_evidence: Array<{ path: string; source: 'pdf_text' | 'ocr' | 'manual' | 'template_default';
    page_number: number | null; bbox: [number, number, number, number] | null;
    source_text: string | null; needs_review: boolean; reason: string | null }>;
  issues: Issue[]; document: { available: boolean; mime_type: string | null;
    page_count: number | null; expires_at: Timestamp | null };
  job: { id: Id; state: 'queued' | 'running' | 'succeeded' | 'failed'; stage: string | null } | null;
  confirmed_at: Timestamp | null; engine_version: string | null;
}
