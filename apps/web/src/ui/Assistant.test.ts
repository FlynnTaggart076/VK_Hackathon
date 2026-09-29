import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { setupServer } from 'msw/node';
import { api, ApiRequestError, setSessionToken } from '../api/client';
import { demoAuth } from '../api/devAuth';
import { handlers, resetMockState } from '../mock/handlers';
import { openExternal, safeLinks } from './Assistant';
import { retryMessage } from './Upload';

const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { server.resetHandlers(); resetMockState(); setSessionToken(null); vi.unstubAllGlobals(); });
afterAll(() => server.close());

describe('assistant chat helpers', () => {
  it('keeps only https links and opens them through MAX Bridge when present', () => {
    expect(safeLinks([
      { label: 'ok', url: 'https://example.org/a' },
      { label: 'plain', url: 'http://example.org/b' },
      { label: 'script', url: 'javascript:alert(1)' },
    ]).map((item) => item.label)).toEqual(['ok']);
    const openLink = vi.fn();
    vi.stubGlobal('window', { WebApp: { openLink } });
    expect(openExternal('https://example.org/a')).toBe(true);
    expect(openLink).toHaveBeenCalledWith('https://example.org/a');
    expect(openExternal('javascript:alert(1)')).toBe(false);
    vi.stubGlobal('window', {});
    expect(openExternal('https://example.org/a')).toBe(false);
  });

  it('explains retry failures by status', () => {
    const body = (code: string) => ({ error: { code, message: 'x', retryable: false, fields: [], details: {} }, request_id: 'r' });
    expect(retryMessage(new ApiRequestError(410, body('SOURCE_EXPIRED') as never))).toContain('удалён');
    expect(retryMessage(new ApiRequestError(429, body('QUEUE_LIMIT_REACHED') as never))).toContain('очереди');
    expect(retryMessage(new Error('network'))).toContain('ещё раз');
  });

  it('walks the mock dialogue from the menu to a house card', async () => {
    setSessionToken((await demoAuth('mock-only')).access_token);
    const menu = await api.dialog({ message: null });
    expect(menu.menu).toBe(true);
    const service = await api.dialog({ choice: 'topic:supplier_contacts' });
    expect(service.awaiting).toBe('service');
    const address = await api.dialog({ choice: 'service:electricity' });
    expect(address.awaiting).toBe('address');
    const card = await api.dialog({ message: 'Учебный город, Примерная улица, 1' });
    expect(card.status).toBe('answered');
    expect(card.card?.management.name).toBe('Учебная УК');
    expect(card.options.map((item) => item.label)).toContain('Другая услуга');
    expect((await api.dialog({ reset: true })).menu).toBe(true);
  });
});
