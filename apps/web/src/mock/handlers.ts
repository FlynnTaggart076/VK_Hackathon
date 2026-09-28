import { http, HttpResponse } from 'msw';
import { API_BASE } from '../api/client';
import { APP_BASE } from '../api/appConfig';
import type { AnswerView, ApiErrorBody, BillData, Catalog, ComparisonView, DraftView, Job, MetaResponse, Profile, ReceiptExplanation, ReceiptQueued, ReceiptSummary, ReceiptView, UpdateProfileRequest } from '../api/types';

const requestId = 'b1399c8c-d010-4e0c-b75f-bd312a647fea';
const receiptId = '10000000-0000-4000-8000-000000000001';
const partialReceiptId = '10000000-0000-4000-8000-000000000002';
const answerId = '30000000-0000-4000-8000-000000000001';
const now = '2026-09-27T10:00:00Z';
const augustId = '10000000-0000-4000-8000-000000000003';
const septemberId = '10000000-0000-4000-8000-000000000004';
const identityId = '10000000-0000-4000-8000-000000000005';
const ambiguousId = '10000000-0000-4000-8000-000000000006';
const partialCompareId = '10000000-0000-4000-8000-000000000007';
let removed = new Set<string>();

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
const newProfile: Profile = { role: 'other', territory_id: null, onboarding_completed: false, aggregate_opt_in: false,
  privacy_notice_version: null, privacy_acknowledged_at: null };
let profile: Profile = { ...newProfile };
export function resetMockState(): void { profile = { ...newProfile }; currentReceipt = { ...queuedReceipt }; jobReads = 0; currentDemoId = null; removed = new Set(); mockDraft = null; }
const topicLabels: [string, string][] = [
  ['first_bill', 'Первая квитанция'], ['bill_terms', 'Термины квитанции'], ['bill_change', 'Изменение суммы'],
  ['meter_readings', 'Передача показаний'], ['meter_deadline', 'Срок передачи показаний'], ['account_number', 'Лицевой счёт'],
  ['management_contacts', 'Контакты управляющей организации'], ['supplier_contacts', 'Контакты поставщика'],
  ['payment_history', 'История платежей'], ['arrears_or_credit', 'Долг или переплата'], ['adjustment', 'Перерасчёт'],
  ['request_breakdown', 'Запрос расшифровки'], ['service_issue', 'Проблема с услугой'],
  ['housing_document', 'Жилищный документ или справка'], ['new_resident', 'После переезда'],
];
const catalog: Catalog = {
  territories: [{ id: 'demo-territory', label: 'Учебная территория' }, { id: 'moscow', label: 'Москва' }], organizations: [], topics: topicLabels.map(([id, label]) => ({ id, label })),
  service_codes: [], units: [], document_kinds: [], demo_receipts: [
    { fixture_id: 'water-2026-08', label: 'Вода, август', description: 'Синтетическая квитанция' },
    { fixture_id: 'water-2026-09', label: 'Вода, сентябрь', description: 'Синтетическая квитанция' },
  ],
};

const bill: BillData = {
  schema_version: '1.0', period: '2026-08', currency: 'RUB', issuer_name: 'Demo Housing Organization',
  provider_id: null, account_number: '000123', address_text: 'Demo City, Example Street 1, Flat 1',
  template_id: 'demo-bill-v1', template_version: '1.0',
  services: [{ line_id: '20000000-0000-4000-8000-000000000001', raw_name: 'Cold water (m3)', service_code: 'cold_water',
    scope: 'individual', unit: 'm3', unit_label: null, quantity: '5.000000', tariff: '40.000000', charge_amount: '200.00',
    supplier_key: null, segment_key: null, calculation_kind: 'simple_product' }],
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
  features: { voice: false, external_submission: false, receipt_ocr: true, comparison: true, engine_stub: false, demo_auth: true },
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
let currentReceipt: ReceiptView = { ...queuedReceipt };
let jobReads = 0;
let currentDemoId: string | null = null;
const sampleSummary = (id: string, period: string, amount: string): ReceiptSummary => ({
  id, status: 'confirmed', revision: 3, period, issuer_name: 'Demo Housing Organization',
  document_total_due: amount, dataset_kind: 'synthetic', created_at: now, source_available: true,
});
const samples: ReceiptSummary[] = [
  sampleSummary(augustId, '2026-08', '200.00'), sampleSummary(septemberId, '2026-09', '270.00'),
  sampleSummary(identityId, '2026-10', '270.00'), sampleSummary(ambiguousId, '2026-11', '270.00'),
  { ...sampleSummary(partialCompareId, '2026-12', '270.00'), source_available: false },
];
const sampleReceipt = (item: ReceiptSummary): ReceiptView => ({ ...partialReceipt,
  id: item.id, status: 'confirmed', revision: item.revision, confirmed_at: now, extraction_outcome: 'recognized',
  bill_data: { ...bill, period: item.period, document_current_charges: item.document_total_due,
    document_total_due: item.document_total_due, settlement: { ...bill.settlement, document_closing_balance: item.document_total_due },
    services: [{ ...bill.services[0], quantity: item.id === augustId ? '5.000000' : '6.000000',
      tariff: item.id === augustId ? '40.000000' : '45.000000', charge_amount: item.document_total_due }] },
  issues: [], field_evidence: [], document: { available: item.source_available, mime_type: 'application/pdf', page_count: 1, expires_at: '2026-10-04T10:00:00Z' },
});
let mockDraft: DraftView | null = null;
const comparisonBase: ComparisonView = {
  dataset_kind: 'synthetic', status: 'complete',
  older: { id: augustId, revision: 3, period: '2026-08' }, newer: { id: septemberId, revision: 3, period: '2026-09' },
  engine_version: 'mock-engine-1', knowledge_version: 'mock-knowledge-1',
  delta_current_charges: '70.00', delta_adjustments: '0.00', delta_total_due: '70.00',
  lines: [{ older_line_id: bill.services[0].line_id, newer_line_id: bill.services[0].line_id,
    label: 'Холодная вода', match_status: 'matched', older_amount: '200.00', newer_amount: '270.00',
    delta: '70.00', quantity_effect: '40.00', tariff_effect: '30.00', rounding_effect: '0.00',
    explanation: 'Учебный результат: объём 5→6 м³, тариф 40→45 ₽; влияние объёма 40 ₽, тарифа 30 ₽.' }],
  settlement_deltas: [], unexplained_delta: '0.00', issues: [], actions: [],
};
const previewPng = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z7rUAAAAASUVORK5CYII='), (char) => char.charCodeAt(0));
async function syntheticPreview(): Promise<Uint8Array> {
  if (typeof window === 'undefined') return previewPng;
  const response = await fetch(`${APP_BASE}synthetic-receipt.png`);
  return response.ok ? new Uint8Array(await response.arrayBuffer()) : previewPng;
}

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
  http.get(`*${API_BASE}/receipts`, ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const url = new URL(request.url);
    const limit = Math.max(1, Math.min(50, Number(url.searchParams.get('limit') || 20)));
    const start = Number(url.searchParams.get('cursor') || 0);
    if (!Number.isInteger(start) || start < 0) return error(422, 'VALIDATION_FAILED', 'Некорректная страница истории.');
    const current: ReceiptSummary = { id: receiptId, status: currentReceipt.status, revision: currentReceipt.revision,
      period: currentReceipt.bill_data.period, issuer_name: currentReceipt.bill_data.issuer_name,
      document_total_due: currentReceipt.bill_data.document_total_due, dataset_kind: currentReceipt.dataset_kind,
      created_at: currentReceipt.created_at, source_available: currentReceipt.document.available };
    const all = [current, ...samples].filter((item) => !removed.has(item.id));
    return HttpResponse.json({ items: all.slice(start, start + limit), next_cursor: start + limit < all.length ? String(start + limit) : null });
  }),
  http.post(`*${API_BASE}/comparisons`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const body = await request.json() as { left: { id: string; revision: number }; right: { id: string; revision: number }; identity_acknowledged: boolean };
    const left = samples.find((item) => item.id === body.left?.id);
    const right = samples.find((item) => item.id === body.right?.id);
    if (!left || !right || removed.has(left.id) || removed.has(right.id)) return error(404, 'NOT_FOUND', 'Квитанция не найдена.');
    if (body.left.revision !== left.revision || body.right.revision !== right.revision) return error(409, 'REVISION_CONFLICT', 'Ревизия документа изменилась.');
    if (left.id === right.id || left.period === right.period) return error(409, 'INCOMPARABLE_RECEIPTS', 'Нужны разные периоды одного счёта.');
    const refs = { older: { id: left.id, revision: left.revision, period: left.period }, newer: { id: right.id, revision: right.revision, period: right.period } };
    if (right.id === identityId && !body.identity_acknowledged) return HttpResponse.json({ ...comparisonBase, ...refs,
      status: 'needs_identity_confirmation', delta_current_charges: null, delta_adjustments: null,
      delta_total_due: null, lines: [], settlement_deltas: [], unexplained_delta: null,
      issues: [{ code: 'IDENTITY_UNCERTAIN', severity: 'warning', path: null, message: 'Сверьте адрес и лицевой счёт в двух документах.' }] } satisfies ComparisonView);
    if (right.id === partialCompareId || right.id === ambiguousId) return HttpResponse.json({ ...comparisonBase, ...refs,
      status: 'partial', delta_current_charges: null, delta_adjustments: null, delta_total_due: null,
      lines: right.id === ambiguousId ? [{ ...comparisonBase.lines[0], match_status: 'ambiguous', delta: null,
        quantity_effect: null, tariff_effect: null, rounding_effect: null, explanation: 'Строки нельзя однозначно сопоставить.' }] : [],
      unexplained_delta: null, issues: [{ code: right.id === ambiguousId ? 'AMBIGUOUS_LINE' : 'AMOUNT_INCOMPLETE',
        severity: 'warning', path: null, message: right.id === ambiguousId ? 'Сопоставление строк неоднозначно.' : 'Одной из сумм нет в документе.' }] } satisfies ComparisonView);
    return HttpResponse.json({ ...comparisonBase, ...refs });
  }),
  http.post(`*${API_BASE}/receipts/demo`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    if (profile.privacy_notice_version !== meta.privacy_notice.version) return error(422, 'PRIVACY_NOTICE_REQUIRED', 'Подтвердите уведомление.');
    const body = await request.json() as { fixture_id?: string };
    if (body.fixture_id !== 'water-2026-08' && body.fixture_id !== 'water-2026-09') return error(404, 'NOT_FOUND', 'Образец не найден.');
    currentDemoId = body.fixture_id;
    currentReceipt = { ...queuedReceipt, dataset_kind: 'synthetic' };
    jobReads = 0;
    return HttpResponse.json({ ...queued, receipt: currentReceipt }, { status: 202 });
  }),
  http.post(`*${API_BASE}/drafts`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const body = await request.json() as { topic_id: string; receipt_refs: { id: string; revision: number }[]; line_id: string | null; user_question: string };
    if (!topicLabels.some(([id]) => id === body.topic_id) || !body.user_question?.trim()) return error(422, 'VALIDATION_FAILED', 'Укажите тему и вопрос.');
    const ref = body.receipt_refs[0];
    const source = samples.find((item) => item.id === ref?.id) ?? (ref?.id === receiptId && currentReceipt.status === 'confirmed' ? {
      id: currentReceipt.id, status: currentReceipt.status, revision: currentReceipt.revision,
      period: currentReceipt.bill_data.period, issuer_name: currentReceipt.bill_data.issuer_name,
      document_total_due: currentReceipt.bill_data.document_total_due, dataset_kind: currentReceipt.dataset_kind,
      created_at: currentReceipt.created_at, source_available: currentReceipt.document.available,
    } satisfies ReceiptSummary : undefined);
    if (!source || removed.has(source.id)) return error(404, 'NOT_FOUND', 'Документ не найден.');
    if (ref.revision !== source.revision) return error(409, 'REVISION_CONFLICT', 'Ревизия документа изменилась.');
    mockDraft = { id: '60000000-0000-4000-8000-000000000001', revision: 1,
      text: `Учебный черновик. Прошу пояснить начисление за холодную воду за ${source.period}: ${source.document_total_due} ₽ по квитанции. Вопрос: ${body.user_question.trim()}`,
      recipient: null, actions: [], receipt_refs: [ref], stale: false, knowledge_version: 'mock-knowledge-1', created_at: now, updated_at: now };
    return HttpResponse.json(mockDraft, { status: 201 });
  }),
  http.get(`*${API_BASE}/drafts/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (!mockDraft || params.id !== mockDraft.id) return error(404, 'NOT_FOUND', 'Черновик не найден.');
    return HttpResponse.json({ ...mockDraft, stale: mockDraft.receipt_refs.some((ref) => removed.has(ref.id) ||
      (ref.id === receiptId && currentReceipt.revision !== ref.revision)) });
  }),
  http.put(`*${API_BASE}/drafts/:id`, async ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (!mockDraft || params.id !== mockDraft.id) return error(404, 'NOT_FOUND', 'Черновик не найден.');
    const body = await request.json() as { expected_revision: number; text: string };
    if (body.expected_revision !== mockDraft.revision) return error(409, 'REVISION_CONFLICT', 'Ревизия черновика изменилась.');
    if (!body.text?.trim()) return error(422, 'VALIDATION_FAILED', 'Текст не может быть пустым.');
    mockDraft = { ...mockDraft, revision: mockDraft.revision + 1, text: body.text, updated_at: now };
    return HttpResponse.json(mockDraft);
  }),
  http.delete(`*${API_BASE}/drafts/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (!mockDraft || params.id !== mockDraft.id) return error(404, 'NOT_FOUND', 'Черновик не найден.');
    mockDraft = null; return new HttpResponse(null, { status: 204 });
  }),
  http.delete(`*${API_BASE}/receipts/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== receiptId && !samples.some((item) => item.id === params.id)) return error(404, 'NOT_FOUND', 'Документ не найден.');
    removed.add(String(params.id));
    return new HttpResponse(null, { status: 204 });
  }),
  http.put(`*${API_BASE}/me/profile`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const body = await request.json() as UpdateProfileRequest;
    if (!['owner', 'tenant', 'other'].includes(body.role) || !catalog.territories.some((item) => item.id === body.territory_id))
      return error(422, 'VALIDATION_FAILED', 'Выберите доступную роль и территорию.');
    if (body.privacy_notice_version !== meta.privacy_notice.version || body.privacy_acknowledged !== true)
      return error(422, 'PRIVACY_NOTICE_REQUIRED', 'Подтвердите актуальное уведомление.');
    profile = { role: body.role, territory_id: body.territory_id, onboarding_completed: true, aggregate_opt_in: profile.aggregate_opt_in,
      privacy_notice_version: body.privacy_notice_version, privacy_acknowledged_at: now };
    return HttpResponse.json(profile);
  }),
  http.put(`*${API_BASE}/me/aggregate-consent`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    const input = await request.json() as { enabled: boolean };
    profile = { ...profile, aggregate_opt_in: input.enabled === true };
    return HttpResponse.json({ aggregate_opt_in: profile.aggregate_opt_in });
  }),
  http.post(`*${API_BASE}/assistant/answers`, async ({ request }) => {
    if (!authorized(request)) return error(401, 'AUTH_REQUIRED', 'Для ответа нужен вход.');
    const input = await request.json() as { question: string; context: { topic_id: string | null; territory_id: string | null; role: string | null; document_kind: string | null; service_code: string | null; organization_id: string | null } };
    const lower = input.question.toLowerCase();
    if (lower.includes('проверь поля') && (input.context.role !== profile.role || input.context.territory_id !== profile.territory_id))
      return error(409, 'INVALID_REQUEST', 'Роль и территория должны совпадать с сохранённым профилем.');
    const unsupported = lower.includes('неизвест') || lower.includes('космос');
    // Exercise every existing AnswerContext clarification field in the browser-only mock.
    const fieldProbe = lower.includes('проверь поля');
    const probeField = !fieldProbe ? null : !input.context.topic_id ? 'topic_id'
      : input.context.territory_id !== 'moscow' ? 'territory_id'
        : input.context.role !== 'owner' ? 'role'
          : !input.context.organization_id ? 'organization_id'
            : !input.context.service_code ? 'service_code'
              : !input.context.document_kind ? 'document_kind' : null;
    const supplier = input.context.topic_id === 'supplier_contacts';
    const needsService = !unsupported && !probeField && supplier && !input.context.service_code;
    const needsOrganization = !unsupported && supplier && !needsService && lower.includes('цепоч') &&
      !input.context.organization_id && !lower.includes('организация со слов пользователя:');
    const needsDocument = !unsupported && !needsService && !needsOrganization && (input.context.topic_id === 'housing_document' || lower.includes('справк')) && !input.context.document_kind;
    const needsClarification = !!probeField || needsService || needsOrganization || needsDocument;
    const response: AnswerView = {
      id: answerId, created_at: now, stale: false, stale_reasons: [],
      status: unsupported ? 'unsupported' : needsClarification ? 'needs_clarification' : 'answered',
      text: unsupported ? 'Для этого вопроса пока нет проверенной карточки.' : needsService ? 'Уточните услугу, чтобы выбрать поставщика.' : needsOrganization ? 'Уточните организацию для учебного сценария.' : needsDocument ? 'По слову «справка» нельзя определить порядок получения документа.' : 'Это учебный ответ. Проверьте объём и тариф в двух платёжках; вывод о правильности начисления здесь не делается.',
      topic_id: unsupported ? null : input.context.topic_id || 'bill_change', steps: [],
      sources: unsupported || needsClarification ? [] : [{ id: 'mock-source', title: 'Учебная карточка темы', url: null,
        territory_id: 'demo-territory', verified_at: now, review_after: '2026-10-27T10:00:00Z', content_version: 'mock-1', is_synthetic: true }],
      actions: [], clarification: probeField ? { field: probeField, prompt: `Уточните поле ${probeField}`, options: probeField === 'territory_id' ? [{ value: 'moscow', label: 'Москва' }] : probeField === 'role' ? [{ value: 'owner', label: 'Собственник' }] : probeField === 'organization_id' ? [{ value: 'org-demo', label: 'УК Пример' }] : [] }
        : needsService ? { field: 'service_code', prompt: 'По какой услуге возник вопрос?', options: [] }
        : needsOrganization ? { field: 'organization_id', prompt: 'Какая организация указана?', options: [] }
          : needsDocument ? { field: 'document_kind', prompt: 'Какой именно документ нужен?', options: [
            { value: 'registration', label: 'Сведения о регистрации' }, { value: 'ownership', label: 'Сведения о собственности' }] } : null,
      limitations: ['Пример синтетический; реальные тарифы и порядок обращения здесь не указаны.'],
      knowledge_version: 'mock-knowledge-1', receipt_ref: null, dataset_kind: 'synthetic',
    };
    return HttpResponse.json(response, { headers: { 'X-Request-ID': requestId } });
  }),
  http.get(`*${API_BASE}/receipts/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    const sample = samples.find((item) => item.id === params.id && !removed.has(item.id));
    if (sample) return HttpResponse.json(sampleReceipt(sample));
    if (params.id === partialReceiptId) return HttpResponse.json(partialReceipt);
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    return HttpResponse.json(currentReceipt, { headers: { 'X-Request-ID': requestId } });
  }),
  http.get(`*${API_BASE}/receipts/:id/city-comparison`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    const url = new URL(request.url);
    return HttpResponse.json({ status: 'ineligible', city: null, period: null,
      service_code: url.searchParams.get('service_code') ?? 'other', unit: null,
      metric: url.searchParams.get('metric') ?? 'charge_amount', sample_size: null,
      average: null, median: null, provenance: 'confirmed_opted_in_user_receipts', receipt_id: params.id });
  }),
  http.post(`*${API_BASE}/receipts`, async ({ request }) => {
    const denied = authError(request); if (denied) return denied;
    if (profile.privacy_notice_version !== meta.privacy_notice.version) return error(422, 'PRIVACY_NOTICE_REQUIRED', 'Подтвердите актуальное уведомление.');
    const form = await request.formData();
    const file = form.get('file');
    const demoSampleId = form.get('demo_sample_id');
    if (!(file instanceof File)) return error(422, 'VALIDATION_FAILED', 'Выберите файл.');
    if (demoSampleId !== null && (!['demo-bill-2026-08.pdf', 'demo-bill-2026-09.pdf'].includes(String(demoSampleId)) || file.name !== demoSampleId || file.type !== 'application/pdf' || file.size !== 2278))
      return error(422, 'VALIDATION_FAILED', 'Байты не соответствуют демообразцу.');
    if (file.name.includes('offline')) return HttpResponse.error();
    if (file.name.includes('conflict')) return error(409, 'IDEMPOTENCY_CONFLICT', 'Повторный ключ использован с другим файлом.');
    if (file.size > meta.limits.upload_max_bytes) return error(413, 'FILE_TOO_LARGE', 'Файл превышает 10 МБ.');
    if (!['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)) return error(415, 'UNSUPPORTED_MEDIA_TYPE', 'Формат не поддерживается.');
    currentReceipt = { ...queuedReceipt, dataset_kind: demoSampleId ? 'synthetic' : 'user_provided',
      document: { ...queuedReceipt.document, mime_type: file.type as ReceiptView['document']['mime_type'] } };
    currentDemoId = null;
    jobReads = 0;
    return HttpResponse.json({ ...queued, receipt: currentReceipt }, { status: 202 });
  }),
  http.get(`*${API_BASE}/jobs/:id`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== queuedJob.id) return error(404, 'NOT_FOUND', 'Задание не найдено.');
    jobReads += 1;
    if (jobReads >= 3 && currentReceipt.status === 'queued') currentReceipt = currentDemoId ? {
      ...sampleReceipt(samples[currentDemoId === 'water-2026-08' ? 0 : 1]), id: receiptId, status: 'needs_review', revision: 1,
      confirmed_at: null, document: currentReceipt.document, job: { id: queuedJob.id, state: 'succeeded', stage: 'completed' },
    } : { ...partialReceipt, id: receiptId, dataset_kind: currentReceipt.dataset_kind,
      document: currentReceipt.document, job: { id: queuedJob.id, state: 'succeeded', stage: 'completed' } };
    const state: Job['state'] = jobReads === 1 ? 'queued' : jobReads === 2 ? 'running' : 'succeeded';
    return HttpResponse.json({ ...queuedJob, state, stage: state === 'queued' ? null : state === 'running' ? 'ocr' : 'completed' });
  }),
  http.put(`*${API_BASE}/receipts/:id/draft`, async ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    const body = await request.json() as { expected_revision: number; bill_data: BillData };
    if (currentReceipt.status === 'queued' || body.expected_revision !== currentReceipt.revision)
      return error(409, 'REVISION_CONFLICT', 'Ревизия изменилась или обработка ещё идёт.');
    if (!body.bill_data.period || body.bill_data.services.length === 0 || body.bill_data.services.some((line) => !line.raw_name || !line.charge_amount) || body.bill_data.adjustments.some((item) => item.amount === null))
      return error(422, 'VALIDATION_FAILED', 'Заполните период, строки начислений и суммы перерасчётов.');
    currentReceipt = { ...currentReceipt, status: 'needs_review', revision: currentReceipt.revision + 1,
      bill_data: { ...body.bill_data,
        template_id: currentReceipt.bill_data.template_id, template_version: currentReceipt.bill_data.template_version,
        services: body.bill_data.services.map((line) => ({ ...line, calculation_kind: currentReceipt.bill_data.services.find((old) => old.line_id === line.line_id)?.calculation_kind ?? 'document_amount' })),
        settlement: { ...body.bill_data.settlement, formula_kind: currentReceipt.bill_data.settlement.formula_kind } },
      field_evidence: [{ path: '/services/0/charge_amount', source: 'manual', page_number: null, bbox: null,
        source_text: null, needs_review: false, reason: null }] };
    return HttpResponse.json(currentReceipt);
  }),
  http.post(`*${API_BASE}/receipts/:id/confirm`, async ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    const body = await request.json() as { expected_revision: number; acknowledged_warning_codes: string[] };
    if (body.expected_revision !== currentReceipt.revision) return error(409, 'REVISION_CONFLICT', 'Ревизия изменилась.');
    if (currentReceipt.status !== 'needs_review') return error(409, 'INVALID_STATE', 'Документ не готов к подтверждению.');
    if (currentReceipt.issues.some((issue) => issue.severity === 'warning' && !body.acknowledged_warning_codes.includes(issue.code)))
      return error(422, 'WARNINGS_NOT_ACKNOWLEDGED', 'Примите предупреждения.');
    currentReceipt = { ...currentReceipt, status: 'confirmed', revision: currentReceipt.revision + 1, confirmed_at: now };
    return HttpResponse.json(currentReceipt);
  }),
  http.get(`*${API_BASE}/receipts/:id/explanation`, ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Документ не найден.');
    if (currentReceipt.status !== 'confirmed') return error(409, 'RECEIPT_NOT_CONFIRMED', 'Сначала подтвердите документ.');
    const explanation: ReceiptExplanation = {
      receipt_ref: { id: receiptId, revision: currentReceipt.revision }, engine_version: 'mock-engine-1', knowledge_version: 'mock-knowledge-1',
      summary: 'Учебное объяснение синтетической платёжки. Сверьте данные с исходником.',
      current_charges: currentReceipt.bill_data.document_current_charges,
      document_total_due: currentReceipt.bill_data.document_total_due,
      calculated_closing_balance: null, calculated_total_due: null, unexplained_difference: null,
      reconciliation_checks: [], reconciliation_status: 'incomplete',
      lines: currentReceipt.bill_data.services.map((line) => ({ line_id: line.line_id, title: line.raw_name,
        explanation: 'Сумма взята из подтверждённых данных пользователя; тариф не проверен.', formula_text: null,
        calculated_amount: null, difference: null, issues: [] })),
      balance_components: [], issues: currentReceipt.issues, sources: [], actions: [],
    };
    return HttpResponse.json(explanation);
  }),
  http.get(`*${API_BASE}/receipts/:id/pages/:page`, async ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id !== receiptId || params.page !== '1') return error(404, 'NOT_FOUND', 'Страница не найдена.');
    return new HttpResponse(await syntheticPreview(), { headers: { 'Content-Type': 'image/png' } });
  }),
  http.get(`*${API_BASE}/receipts/:id/source`, async ({ request, params }) => {
    const denied = authError(request); if (denied) return denied;
    if (params.id === partialCompareId) return error(410, 'SOURCE_EXPIRED', 'Срок хранения файла истёк.');
    if (samples.some((item) => item.id === params.id && !removed.has(item.id))) return new HttpResponse(await syntheticPreview(), { headers: { 'Content-Type': 'image/png' } });
    if (params.id !== receiptId) return error(404, 'NOT_FOUND', 'Файл не найден.');
    return new HttpResponse(await syntheticPreview(), { headers: { 'Content-Type': 'image/png' } });
  }),
];
