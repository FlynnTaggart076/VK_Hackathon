import { http, HttpResponse } from 'msw';
import { API_BASE } from '../api/client';
import type { AnswerView, ApiErrorBody, BillData, Catalog, Job, MetaResponse, Profile, ReceiptQueued, ReceiptView, UpdateProfileRequest } from '../api/types';

const requestId = 'b1399c8c-d010-4e0c-b75f-bd312a647fea';
const receiptId = '10000000-0000-4000-8000-000000000001';
const partialReceiptId = '10000000-0000-4000-8000-000000000002';
const answerId = '30000000-0000-4000-8000-000000000001';
const now = '2026-09-27T10:00:00Z';

function error(status: number, code: ApiErrorBody['error']['code'], message: string): HttpResponse<ApiErrorBody> {
  return HttpResponse.json({
    error: { code, message, retryable: false, fields: [], details: code === 'REVISION_CONFLICT' ? { current_revision: 4 } : {} },
    request_id: requestId,
  }, { status, headers: { 'X-Request-ID': requestId } });
}
function authorized(request: Request): boolean { return request.headers.get('Authorization') === 'Bearer mock-session'; }
function authError(request: Request): HttpResponse<ApiErrorBody> | null {
  if (authorized(request)) return null;
  return request.headers.get('Authorization') === 'Bearer expired-session'
    ? error(401, 'SESSION_EXPIRED', 'Срок сессии истёк.')
    : error(401, 'AUTH_REQUIRED', 'Войдите в приложение.');
}
const newProfile: Profile = { role: 'other', territory_id: null, onboarding_completed: false,
  privacy_notice_version: null, privacy_acknowledged_at: null };
let profile: Profile = { ...newProfile };
export function resetMockState(): void { profile = { ...newProfile }; }
const catalog: Catalog = {
  territories: [{ id: 'demo-territory', label: 'Учебная территория' }], organizations: [], topics: [],
  service_codes: [], units: [], document_kinds: [], demo_receipts: [],
};

const bill: BillData = {
  schema_version: '1.0', period: '2026-08', currency: 'RUB', issuer_name: 'Учебная управляющая организация',
  provider_id: 'demo-provider', account_number: '000123', address_text: 'Учебный город, Примерная улица, дом 1, квартира 1',
  template_id: 'demo-bill-v1', template_version: '1.0',
  services: [{ line_id: '20000000-0000-4000-8000-000000000001', raw_name: 'Холодная вода', service_code: 'cold_water',
    scope: 'individual', unit: 'm3', unit_label: null, quantity: '5.000000', tariff: '40.000000', charge_amount: '200.00',
    supplier_key: 'demo-provider', segment_key: null, calculation_kind: 'simple_product' }],
  adjustments: [], settlement: { formula_kind: 'signed_balance_v1', opening_balance: '0.00', payments_credited: '0.00',
    penalties: '0.00', other_account_changes: '0.00', document_closing_balance: '200.00' },
  document_current_charges: '200.00', document_total_due: '200.00',
};
const partialBill: BillData = {
  ...bill, template_id: null, template_version: null,
  services: [{ ...bill.services[0], tariff: null, quantity: null, calculation_kind: 'document_amount' }],
};
const partialReceipt: ReceiptView = {
  id: partialReceiptId, status: 'needs_review', revision: 1, created_at: now, updated_at: now,
  dataset_kind: 'synthetic', extraction_outcome: 'partial', bill_data: partialBill,
  field_evidence: [{ path: '/services/0/tariff', source: 'ocr', page_number: 1, bbox: null,
    source_text: null, needs_review: true, reason: 'Не найдено значение тарифа' }],
  issues: [{ code: 'FIELD_MISSING', severity: 'warning', path: '/services/0/tariff', message: 'Проверьте тариф по исходнику.' }],
  document: { available: false, mime_type: null, page_count: null, expires_at: null },
  job: { id: '40000000-0000-4000-8000-000000000001', state: 'succeeded', stage: 'completed' },
  confirmed_at: null, engine_version: 'mock-engine-1',
};
const meta: MetaResponse = {
  api_version: '1.0', engine_version: 'mock-engine-1', knowledge_version: 'mock-knowledge-1', mode: 'dev',
  limits: { upload_max_bytes: 10485760, pdf_max_pages: 3, receipt_retention_days: 30, source_retention_days: 7 },
  features: { voice: false, external_submission: false, receipt_ocr: false, comparison: false, engine_stub: true, demo_auth: true },
  privacy_notice: { version: 'mock-1', text: 'Учебные данные. Не загружайте настоящие документы.' },
};
const queuedReceipt: ReceiptView = {
  ...partialReceipt, id: receiptId, status: 'queued', extraction_outcome: null,
  bill_data: { ...bill, period: null, issuer_name: null, provider_id: null, account_number: null,
    address_text: null, template_id: null, template_version: null, services: [], adjustments: [],
    settlement: { formula_kind: 'unsupported', opening_balance: null, payments_credited: null,
      penalties: null, other_account_changes: null, document_closing_balance: null },
    document_current_charges: null, document_total_due: null },
  field_evidence: [], issues: [], dataset_kind: 'user_provided',
  document: { available: true, mime_type: 'image/png', page_count: 1, expires_at: '2026-10-04T10:00:00Z' },
  job: { id: '40000000-0000-4000-8000-000000000001', state: 'queued', stage: null },
  engine_version: null,
};
const queuedJob: Job = { id: queuedReceipt.job!.id, kind: 'receipt_ocr', state: 'queued', stage: null,
  receipt_id: receiptId, error: null, updated_at: now };
const queued: ReceiptQueued = { receipt: queuedReceipt, job_id: queuedJob.id };

export const handlers = [
  http.get(`*${API_BASE}/meta`, () => HttpResponse.json(meta, { headers: { 'X-Request-ID': requestId } })),
  http.post(`*${API_BASE}/auth/demo`, async ({ request }) => {
    const input = await request.json() as { access_code?: string; identity?: string };
    if (input.access_code !== 'mock-only' || input.identity !== 'reviewer_a') return error(401, 'AUTH_REQUIRED', 'Нужен учебный вход.');
    return HttpResponse.json({
      access_token: 'mock-session', token_type: 'bearer', expires_in: 3600,
      user: { id: '50000000-0000-4000-8000-000000000001' },
      profile,
    }, { headers: { 'X-Request-ID': requestId } });
  }),
  http.get(`*${API_BASE}/me`, ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    return HttpResponse.json({ user: { id: '50000000-0000-4000-8000-000000000001' }, profile });
  }),
  http.get(`*${API_BASE}/catalog`, ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    return HttpResponse.json(catalog);
  }),
  http.put(`*${API_BASE}/me/profile`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const body = await request.json() as UpdateProfileRequest;
    if (!['owner', 'tenant', 'other'].includes(body.role) || body.territory_id !== 'demo-territory')
      return error(422, 'VALIDATION_FAILED', 'Выберите доступную роль и территорию.');
    if (body.privacy_notice_version !== meta.privacy_notice.version || body.privacy_acknowledged !== true)
      return error(422, 'PRIVACY_NOTICE_REQUIRED', 'Подтвердите актуальное уведомление.');
    profile = { role: body.role, territory_id: body.territory_id, onboarding_completed: true,
      privacy_notice_version: body.privacy_notice_version, privacy_acknowledged_at: now };
    return HttpResponse.json(profile);
  }),
  http.post(`*${API_BASE}/assistant/answers`, async ({ request }) => {
    if (!authorized(request)) return error(401, 'AUTH_REQUIRED', 'Для ответа нужен вход.');
    const input = await request.json() as { question: string };
    const unsupported = input.question.toLowerCase().includes('неизвест');
    const response: AnswerView = {
      id: answerId, created_at: now, stale: false, stale_reasons: [],
      status: unsupported ? 'unsupported' : 'answered',
      text: unsupported ? 'Для этого вопроса пока нет проверенной карточки.' : 'Это учебный ответ. Проверьте объём и тариф в двух платёжках; вывод о правильности начисления здесь не делается.',
      topic_id: unsupported ? null : 'cold_water', steps: [], sources: [], actions: [], clarification: null,
      limitations: ['Пример синтетический; реальные тарифы и порядок обращения здесь не указаны.'],
      knowledge_version: 'mock-knowledge-1', receipt_ref: null, dataset_kind: 'synthetic',
    };
    return HttpResponse.json(response, { headers: { 'X-Request-ID': requestId } });
  }),
  http.get(`*${API_BASE}/receipts/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id === partialReceiptId) return HttpResponse.json(partialReceipt);
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    return HttpResponse.json(queuedReceipt, { headers: { 'X-Request-ID': requestId } });
  }),
  http.post(`*${API_BASE}/receipts`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    if (profile.privacy_notice_version !== meta.privacy_notice.version) return error(422, 'PRIVACY_NOTICE_REQUIRED', 'Подтвердите актуальное уведомление.');
    const form = await request.formData();
    const file = form.get('file');
    if (!(file instanceof File)) return error(422, 'VALIDATION_FAILED', 'Выберите файл.');
    if (file.name.includes('offline')) return HttpResponse.error();
    if (file.name.includes('conflict')) return error(409, 'IDEMPOTENCY_CONFLICT', 'Повторный ключ использован с другим файлом.');
    if (file.size > meta.limits.upload_max_bytes) return error(413, 'FILE_TOO_LARGE', 'Файл превышает 10 МБ.');
    if (!['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)) return error(415, 'UNSUPPORTED_MEDIA_TYPE', 'Формат не поддерживается.');
    return HttpResponse.json({ ...queued, receipt: { ...queued.receipt, document: { ...queued.receipt.document, mime_type: file.type } } }, { status: 202 });
  }),
  http.get(`*${API_BASE}/jobs/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== queuedJob.id) return error(404, 'NOT_FOUND', 'Задание не найдено.');
    return HttpResponse.json(queuedJob);
  }),
  http.put(`*${API_BASE}/receipts/:id/draft`, ({ request }) => {
    if (!authorized(request)) return error(401, 'AUTH_REQUIRED', 'Для изменения нужен вход.');
    return error(409, 'REVISION_CONFLICT', 'Документ изменён в другой вкладке. Загрузите актуальную версию.');
  }),
];
