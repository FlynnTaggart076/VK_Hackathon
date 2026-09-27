import { http, HttpResponse } from 'msw';
import { API_BASE } from '../api/client';
import type { AnswerView, ApiErrorBody, BillData, MetaResponse, ReceiptView } from '../api/types';

const requestId = 'b1399c8c-d010-4e0c-b75f-bd312a647fea';
const receiptId = '10000000-0000-4000-8000-000000000001';
const answerId = '30000000-0000-4000-8000-000000000001';
const now = '2026-09-27T10:00:00Z';

function error(status: number, code: ApiErrorBody['error']['code'], message: string): HttpResponse<ApiErrorBody> {
  return HttpResponse.json({
    error: { code, message, retryable: false, fields: [], details: code === 'REVISION_CONFLICT' ? { current_revision: 4 } : {} },
    request_id: requestId,
  }, { status, headers: { 'X-Request-ID': requestId } });
}
function authorized(request: Request): boolean { return request.headers.get('Authorization') === 'Bearer mock-session'; }

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
  id: receiptId, status: 'needs_review', revision: 1, created_at: now, updated_at: now,
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

export const handlers = [
  http.get(`*${API_BASE}/meta`, () => HttpResponse.json(meta, { headers: { 'X-Request-ID': requestId } })),
  http.post(`*${API_BASE}/auth/demo`, async ({ request }) => {
    const input = await request.json() as { access_code?: string; identity?: string };
    if (input.access_code !== 'mock-only' || input.identity !== 'reviewer_a') return error(401, 'AUTH_REQUIRED', 'Нужен учебный вход.');
    return HttpResponse.json({
      access_token: 'mock-session', token_type: 'bearer', expires_in: 3600,
      user: { id: '50000000-0000-4000-8000-000000000001' },
      profile: { role: 'other', territory_id: null, onboarding_completed: false,
        privacy_notice_version: null, privacy_acknowledged_at: null },
    }, { headers: { 'X-Request-ID': requestId } });
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
    if (!authorized(request)) return error(401, 'AUTH_REQUIRED', 'Для просмотра нужен вход.');
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    return HttpResponse.json(partialReceipt, { headers: { 'X-Request-ID': requestId } });
  }),
  http.put(`*${API_BASE}/receipts/:id/draft`, ({ request }) => {
    if (!authorized(request)) return error(401, 'AUTH_REQUIRED', 'Для изменения нужен вход.');
    return error(409, 'REVISION_CONFLICT', 'Документ изменён в другой вкладке. Загрузите актуальную версию.');
  }),
];
