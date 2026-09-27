import type { AnswerContext, AnswerView, ApiErrorBody, AuthResponse, Catalog, Job, MeResponse, MetaResponse, Profile, ReceiptQueued, ReceiptView, UnexpectedErrorBody, UpdateProfileRequest } from './types';

export const API_BASE = '/team/zhkh/api/v1';
let sessionToken: string | null = null;

export function setSessionToken(token: string | null): void { sessionToken = token; }
export function hasSessionToken(): boolean { return sessionToken !== null; }

export class ApiRequestError extends Error {
  constructor(public readonly status: number, public readonly body: ApiErrorBody | UnexpectedErrorBody) {
    super(body.error.message);
    this.name = 'ApiRequestError';
  }
  get code(): string { return this.body.error.code; }
  get requestId(): string { return this.body.request_id; }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (!value || typeof value !== 'object' || !('error' in value) || !('request_id' in value)) return false;
  const error = value.error;
  return !!error && typeof error === 'object' && 'message' in error && 'code' in error;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const url = new URL(`${API_BASE}${path}`, globalThis.location?.origin ?? 'http://localhost');
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let parsed: unknown;
    try { parsed = await response.json(); } catch { /* Gateway may return non-JSON. */ }
    if (response.status === 401 && sessionToken) {
      setSessionToken(null);
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('zhkh:session-expired'));
    }
    if (isErrorBody(parsed)) throw new ApiRequestError(response.status, parsed);
    throw new ApiRequestError(response.status, {
      error: { code: 'UNEXPECTED_RESPONSE', message: 'Сервер вернул неожиданный ответ.', retryable: response.status >= 500, fields: [], details: {} },
      request_id: response.headers.get('X-Request-ID') ?? 'unknown',
    });
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export const api = {
  meta: (signal?: AbortSignal) => request<MetaResponse>('/meta', { signal }),
  demoAuth: (accessCode: string, signal?: AbortSignal) => request<AuthResponse>('/auth/demo', {
    method: 'POST', body: JSON.stringify({ access_code: accessCode, identity: 'reviewer_a' }), signal,
  }),
  me: (signal?: AbortSignal) => request<MeResponse>('/me', { signal }),
  catalog: (signal?: AbortSignal) => request<Catalog>('/catalog', { signal }),
  updateProfile: (body: UpdateProfileRequest, signal?: AbortSignal) => request<Profile>('/me/profile', {
    method: 'PUT', body: JSON.stringify(body), signal,
  }),
  answer: (question: string, context: AnswerContext, signal?: AbortSignal) => request<AnswerView>('/assistant/answers', {
    method: 'POST', body: JSON.stringify({ question, context }), signal,
  }),
  receipt: (id: string, signal?: AbortSignal) => request<ReceiptView>(`/receipts/${encodeURIComponent(id)}`, { signal }),
  upload: (file: File, idempotencyKey: string, signal?: AbortSignal) => {
    const body = new FormData();
    body.append('file', file);
    return request<ReceiptQueued>('/receipts', { method: 'POST', body, headers: { 'Idempotency-Key': idempotencyKey }, signal });
  },
  job: (id: string, signal?: AbortSignal) => request<Job>(`/jobs/${encodeURIComponent(id)}`, { signal }),
};
