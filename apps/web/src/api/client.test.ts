import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { setupServer } from 'msw/node';
import { api, ApiRequestError, request, setSessionToken } from './client';
import { handlers } from '../mock/handlers';
import type { AnswerContext } from './types';

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
});
