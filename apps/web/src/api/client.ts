import type { AnswerContext, AnswerView, ApiErrorBody, AuthResponse, MetaResponse, ReceiptView } from './types';

export const API_BASE = '/team/zhkh/api/v1';
let sessionToken: string | null = null;

export function setSessionToken(token: string | null): void { sessionToken = token; }
export function hasSessionToken(): boolean { return sessionToken !== null; }

export class ApiRequestError extends Error {
  constructor(public readonly status: number, public readonly body: ApiErrorBody) {
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
  answer: (question: string, context: AnswerContext, signal?: AbortSignal) => request<AnswerView>('/assistant/answers', {
    method: 'POST', body: JSON.stringify({ question, context }), signal,
  }),
  receipt: (id: string, signal?: AbortSignal) => request<ReceiptView>(`/receipts/${encodeURIComponent(id)}`, { signal }),
};
