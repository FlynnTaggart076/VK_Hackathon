import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { setupServer } from 'msw/node';
import { api, ApiRequestError, hasSessionToken, request, setSessionToken } from './client';
import { demoAuth } from './devAuth';
import { handlers, resetMockState } from '../mock/handlers';
import type { AnswerContext, BillData } from './types';
import { canUpload } from '../ui/Onboarding';
import { billErrors, normalizeBill } from '../ui/billForm';

const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { server.resetHandlers(); resetMockState(); setSessionToken(null); });
afterAll(() => server.close());

const context: AnswerContext = {
  territory_id: 'demo-territory', role: 'tenant', topic_id: null, organization_id: null,
  service_code: null, document_kind: null, receipt_id: null, receipt_revision: null,
};

describe('E0 API examples', () => {
  it('requires an in-memory session and returns the specified error envelope', async () => {
    await expect(api.answer('Вода', context)).rejects.toMatchObject({
      status: 401, code: 'AUTH_REQUIRED', requestId: 'b1399c8c-d010-4e0c-b75f-bd312a647fea',
    });
    const auth = await demoAuth('mock-only');
    setSessionToken(auth.access_token);
    expect((await api.answer('неизвестный вопрос', context)).status).toBe('unsupported');
  });

  it('returns partial receipt without filling unknown tariff and a revision conflict', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const receipt = await api.receipt('10000000-0000-4000-8000-000000000002');
    expect(receipt.extraction_outcome).toBe('partial');
    expect(receipt.bill_data.services[0].tariff).toBeNull();
    await expect(request('/receipts/10000000-0000-4000-8000-000000000001/draft', {
      method: 'PUT', body: JSON.stringify({ expected_revision: 1, bill_data: receipt.bill_data }),
    })).rejects.toSatisfy((error: unknown) => error instanceof ApiRequestError && error.status === 409 && error.code === 'REVISION_CONFLICT');
  });

  it('accepts the canonical C BillData fixture without schema-only $defs', () => {
    const fixture = JSON.parse(readFileSync(new URL('../../../../contracts/http/examples/receipt-confirmed.json', import.meta.url), 'utf8')) as unknown;
    const schema = JSON.parse(readFileSync(new URL('../../../../contracts/engine/v1/BillData.schema.json', import.meta.url), 'utf8')) as object;
    const ajv = new Ajv2020({ strict: false });
    addFormats(ajv);
    const validate = ajv.compile<BillData>(schema);
    expect(fixture).toBeTruthy();
    const bill = (fixture as { bill_data: unknown }).bill_data;
    expect(validate(bill), JSON.stringify(validate.errors)).toBe(true);
    if (!validate(bill)) throw new Error('Canonical BillData failed schema validation');
    type HasSchemaDefinitions = '$defs' extends keyof BillData ? true : false;
    const hasSchemaDefinitions: HasSchemaDefinitions = false;
    expect(hasSchemaDefinitions).toBe(false);
    expect('$defs' in bill).toBe(false);
    const code: BillData['services'][number]['service_code'] = bill.services[0].service_code;
    expect(code).toBe('cold_water');
  });
});

describe('E1 first run', () => {
  it('requires server profile consent before upload and reads the queued job', async () => {
    const meta = await api.meta();
    setSessionToken((await demoAuth('mock-only')).access_token);
    const initial = await api.me();
    const catalog = await api.catalog();
    expect(catalog.territories.map((item) => item.id)).toContain('demo-territory');
    expect(canUpload(initial.profile, meta)).toBe(false);
    await expect(api.updateProfile({ role: 'tenant', territory_id: 'demo-territory',
      privacy_notice_version: 'old', privacy_acknowledged: true })).rejects.toMatchObject({ status: 422, code: 'PRIVACY_NOTICE_REQUIRED' });
    const profile = await api.updateProfile({ role: 'tenant', territory_id: 'demo-territory',
      privacy_notice_version: meta.privacy_notice.version, privacy_acknowledged: true });
    expect(canUpload(profile, meta)).toBe(true);
    const upload = await api.upload(new File(['synthetic'], 'bill.png', { type: 'image/png' }),
      'b1399c8c-d010-4e0c-b75f-bd312a647fea');
    expect(upload.receipt.status).toBe('queued');
    expect((await api.job(upload.job_id)).state).toBe('queued');
  });

  it('drops an expired session token and requires a new sign-in', async () => {
    setSessionToken('expired-session');
    await expect(api.me()).rejects.toMatchObject({ status: 401, code: 'SESSION_EXPIRED' });
    expect(hasSessionToken()).toBe(false);
  });
});

describe('E2 synthetic receipt flow', () => {
  it('polls, edits with revision, confirms acknowledged warnings and reads explanation', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const meta = await api.meta();
    await api.updateProfile({ role: 'tenant', territory_id: 'demo-territory',
      privacy_notice_version: meta.privacy_notice.version, privacy_acknowledged: true });
    const upload = await api.upload(new File(['synthetic'], 'bill.png', { type: 'image/png' }), crypto.randomUUID());
    expect((await api.job(upload.job_id)).state).toBe('queued');
    expect((await api.job(upload.job_id)).state).toBe('running');
    expect((await api.job(upload.job_id)).state).toBe('succeeded');
    const receipt = await api.receipt(upload.receipt.id);
    expect(receipt.status).toBe('needs_review');
    expect(receipt.extraction_outcome).toBe('partial');
    expect((await api.page(receipt.id, 1)).type).toBe('image/png');
    const bill = normalizeBill({ ...receipt.bill_data, services: [{ ...receipt.bill_data.services[0], tariff: '40,00', charge_amount: '200' }] });
    expect(billErrors(bill)).toEqual([]);
    await expect(api.editReceipt(receipt.id, { expected_revision: 20, bill_data: bill })).rejects.toMatchObject({ status: 409, code: 'REVISION_CONFLICT' });
    const edited = await api.editReceipt(receipt.id, { expected_revision: receipt.revision,
      bill_data: { ...bill, template_id: 'client-forged', template_version: '999',
        services: [{ ...bill.services[0], calculation_kind: 'simple_product' }],
        settlement: { ...bill.settlement, formula_kind: 'unsupported' } } });
    expect(edited.revision).toBe(receipt.revision + 1);
    expect((await api.receipt(edited.id)).bill_data.services[0].tariff).toBe('40.00');
    expect(edited.bill_data.settlement.formula_kind).toBe('signed_balance_v1');
    expect(edited.bill_data.template_id).toBe(receipt.bill_data.template_id);
    expect(edited.bill_data.template_version).toBe(receipt.bill_data.template_version);
    expect(edited.bill_data.services[0].calculation_kind).toBe('document_amount');
    expect(edited.field_evidence[0].source).toBe('manual');
    await expect(api.confirmReceipt(edited.id, { expected_revision: edited.revision, acknowledged_warning_codes: [] }, crypto.randomUUID()))
      .rejects.toMatchObject({ status: 422, code: 'WARNINGS_NOT_ACKNOWLEDGED' });
    const confirmed = await api.confirmReceipt(edited.id, { expected_revision: edited.revision,
      acknowledged_warning_codes: edited.issues.filter((issue) => issue.severity === 'warning').map((issue) => issue.code) }, crypto.randomUUID());
    expect(confirmed.status).toBe('confirmed');
    const explanation = await api.explanation(confirmed.id, confirmed.revision);
    expect(explanation.receipt_ref.revision).toBe(confirmed.revision);
    expect(explanation.lines[0].title).toBe(bill.services[0].raw_name);
  });

  it('allows unknown issuer but requires every adjustment amount before submission', () => {
    const sample = JSON.parse(readFileSync(new URL('../../../../contracts/http/examples/receipt-confirmed.json', import.meta.url), 'utf8')) as { bill_data: BillData };
    expect(billErrors({ ...sample.bill_data, issuer_name: null })).toEqual([]);
    expect(billErrors({ ...sample.bill_data, adjustments: [{ adjustment_id: crypto.randomUUID(), label: 'Перерасчёт', amount: null,
      service_line_id: null, related_period: null }] })).toContain('Перерасчёт 1: укажите сумму с двумя цифрами после точки.');
  });
});

describe('E3 comparison, FAQ, draft and history mock', () => {
  const august = '10000000-0000-4000-8000-000000000003';
  const september = '10000000-0000-4000-8000-000000000004';
  it('paginates history and renders server-owned 70 / 40 / 30 only after valid comparison', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const first = await api.receipts(null, 2);
    expect(first.items).toHaveLength(2);
    expect(first.next_cursor).not.toBeNull();
    const rest = await api.receipts(first.next_cursor, 10);
    expect(rest.items.some((item) => item.id === september)).toBe(true);
    const result = await api.compare({ left: { id: august, revision: 3 }, right: { id: september, revision: 3 }, identity_acknowledged: false });
    expect(result.dataset_kind).toBe('synthetic');
    expect(result.delta_total_due).toBe('70.00');
    expect(result.lines[0]).toMatchObject({ quantity_effect: '40.00', tariff_effect: '30.00' });
    await expect(api.compare({ left: { id: august, revision: 2 }, right: { id: september, revision: 3 }, identity_acknowledged: false }))
      .rejects.toMatchObject({ status: 409, code: 'REVISION_CONFLICT' });
  });
  it('withholds deltas for uncertain identity and keeps ambiguous/partial results partial', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const ref = { id: august, revision: 3 };
    const identity = await api.compare({ left: ref, right: { id: '10000000-0000-4000-8000-000000000005', revision: 3 }, identity_acknowledged: false });
    expect(identity.status).toBe('needs_identity_confirmation');
    expect(identity.delta_total_due).toBeNull();
    expect(identity.lines).toEqual([]);
    const ambiguous = await api.compare({ left: ref, right: { id: '10000000-0000-4000-8000-000000000006', revision: 3 }, identity_acknowledged: false });
    expect(ambiguous.status).toBe('partial');
    expect(ambiguous.lines[0].match_status).toBe('ambiguous');
    expect(ambiguous.lines[0].quantity_effect).toBeNull();
    const partial = await api.compare({ left: ref, right: { id: '10000000-0000-4000-8000-000000000007', revision: 3 }, identity_acknowledged: false });
    expect(partial.delta_total_due).toBeNull();
  });
  it('lists all 15 topics, asks for clarification and admits unknown questions', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const catalog = await api.catalog();
    expect(catalog.topics).toHaveLength(15);
    expect(catalog.topics.map((topic) => topic.id)).toContain('housing_document');
    const vague = await api.answer('Нужна справка', { ...context, topic_id: 'housing_document' });
    expect(vague.status).toBe('needs_clarification');
    expect(vague.sources).toEqual([]);
    expect((await api.answer('неизвестный вопрос', context)).status).toBe('unsupported');
  });
  it('creates and edits a draft with CAS, then marks it stale after source deletion', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const draft = await api.createDraft({ topic_id: 'request_breakdown', organization_id: null,
      receipt_refs: [{ id: september, revision: 3 }], line_id: null, user_question: 'Поясните начисление' }, crypto.randomUUID());
    expect(draft.text).toContain('270.00');
    expect(draft.recipient).toBeNull();
    await expect(api.editDraft(draft.id, { expected_revision: 99, text: 'Мой текст' })).rejects.toMatchObject({ status: 409, code: 'REVISION_CONFLICT' });
    expect((await api.editDraft(draft.id, { expected_revision: draft.revision, text: 'Мой текст' })).text).toBe('Мой текст');
    await api.deleteReceipt(september);
    expect((await api.draft(draft.id)).stale).toBe(true);
    expect((await api.receipts()).items.some((item) => item.id === september)).toBe(false);
  });
});
