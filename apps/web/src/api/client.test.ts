import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { setupServer } from 'msw/node';
import { api, ApiRequestError, request, setSessionToken } from './client';
import { handlers } from '../mock/handlers';
import type { AnswerContext, BillData } from './types';

const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { server.resetHandlers(); setSessionToken(null); });
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
    const auth = await api.demoAuth('mock-only');
    setSessionToken(auth.access_token);
    expect((await api.answer('неизвестный вопрос', context)).status).toBe('unsupported');
  });

  it('returns partial receipt without filling unknown tariff and a revision conflict', async () => {
    setSessionToken((await api.demoAuth('mock-only')).access_token);
    const receipt = await api.receipt('10000000-0000-4000-8000-000000000001');
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
