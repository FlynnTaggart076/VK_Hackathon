import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

describe('build path and auth isolation', () => {
  it('uses production base and does not store production session', async () => {
    vi.stubEnv('VITE_APP_BASE', '/team/zhkh/');
    vi.stubEnv('VITE_PREVIEW_MODE', 'false');
    const tabStorage = storage();
    vi.stubGlobal('window', { sessionStorage: tabStorage });
    const { APP_BASE, PREVIEW_MODE, normalizeAppBase } = await import('./appConfig');
    const { API_BASE, setSessionToken } = await import('./client');
    expect({ APP_BASE, PREVIEW_MODE, API_BASE }).toEqual({
      APP_BASE: '/team/zhkh/', PREVIEW_MODE: false, API_BASE: '/team/zhkh/api/v1',
    });
    setSessionToken('production-token');
    expect(tabStorage.getItem('zhkh-preview-session')).toBeNull();
    expect(normalizeAppBase('/team/zhkh-preview/')).toBe('/team/zhkh-preview/');
    expect(() => normalizeAppBase('//evil.example/')).toThrow();
    expect(() => normalizeAppBase('/team/../private/')).toThrow();
  });

  it('uses preview prefix and one anonymous exchange, then restores only this tab', async () => {
    vi.stubEnv('VITE_APP_BASE', '/team/zhkh-preview/');
    vi.stubEnv('VITE_PREVIEW_MODE', 'true');
    const tabStorage = storage();
    vi.stubGlobal('window', { sessionStorage: tabStorage, dispatchEvent: vi.fn() });
    vi.stubGlobal('location', { origin: 'https://example.test' });
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json({
      access_token: 'unique-guest-token', token_type: 'bearer', expires_in: 3600,
      user: { id: 'guest-1' }, profile: { role: 'other', territory_id: null, onboarding_completed: false },
    }));
    vi.stubGlobal('fetch', fetcher);
    const { API_BASE, setSessionToken } = await import('./client');
    const { previewAuth } = await import('./previewAuth');
    expect(API_BASE).toBe('/team/zhkh-preview/api/v1');
    const [first, second] = await Promise.all([previewAuth(), previewAuth()]);
    expect(first).toBe(second);
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, options] = fetcher.mock.calls[0]!;
    expect(String(url)).toBe('https://example.test/team/zhkh-preview/api/v1/auth/preview');
    expect(options?.method).toBe('POST');
    expect(new Headers(options?.headers).get('Authorization')).toBeNull();
    expect(options?.body).toBeUndefined();
    setSessionToken(first.access_token);
    expect(tabStorage.getItem('zhkh-preview-session')).toBe('unique-guest-token');
    vi.resetModules();
    const restored = await import('./client');
    expect(restored.hasSessionToken()).toBe(true);
    restored.setSessionToken(null);
    expect(tabStorage.getItem('zhkh-preview-session')).toBeNull();
  });
});
