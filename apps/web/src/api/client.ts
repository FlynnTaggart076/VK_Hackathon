import type { AggregateConsentView, AnswerContext, AnswerView, ApiErrorBody, Catalog, CityComparisonView, CompareRequest, ComparisonView, ConfirmReceiptRequest, CreateDraftRequest, DraftView, EditDraftRequest, EditReceiptRequest, Job, MeResponse, MetaResponse, Profile, ReceiptExplanation, ReceiptList, ReceiptQueued, ReceiptView, SyntheticCityComparisonView, UnexpectedErrorBody, UpdateProfileRequest } from './types';
import { APP_BASE, PREVIEW_MODE } from './appConfig';

export const API_BASE = `${APP_BASE}api/v1`;
const previewStorageKey = 'zhkh-preview-session';
function restoredPreviewToken(): string | null {
  if (!PREVIEW_MODE || typeof window === 'undefined') return null;
  try { return window.sessionStorage.getItem(previewStorageKey); } catch { return null; }
}
let sessionToken: string | null = restoredPreviewToken();

export function setSessionToken(token: string | null): void {
  sessionToken = token;
  if (!PREVIEW_MODE || typeof window === 'undefined') return;
  try {
    if (token) window.sessionStorage.setItem(previewStorageKey, token);
    else window.sessionStorage.removeItem(previewStorageKey);
  } catch { /* A blocked sessionStorage does not prevent the current tab session. */ }
}
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

async function responseError(response: Response): Promise<never> {
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

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const url = new URL(`${API_BASE}${path}`, globalThis.location?.origin ?? 'http://localhost');
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) return responseError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function requestBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const headers = new Headers();
  if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  const response = await fetch(new URL(`${API_BASE}${path}`, globalThis.location?.origin ?? 'http://localhost'), { headers, signal });
  if (!response.ok) return responseError(response);
  return response.blob();
}

export const api = {
  meta: (signal?: AbortSignal) => request<MetaResponse>('/meta', { signal }),
  me: (signal?: AbortSignal) => request<MeResponse>('/me', { signal }),
  catalog: (signal?: AbortSignal) => request<Catalog>('/catalog', { signal }),
  updateProfile: (body: UpdateProfileRequest, signal?: AbortSignal) => request<Profile>('/me/profile', {
    method: 'PUT', body: JSON.stringify(body), signal,
  }),
  aggregateConsent: (enabled: boolean, signal?: AbortSignal) => request<AggregateConsentView>('/me/aggregate-consent', {
    method: 'PUT', body: JSON.stringify({ enabled }), signal,
  }),
  answer: (question: string, context: AnswerContext, signal?: AbortSignal) => request<AnswerView>('/assistant/answers', {
    method: 'POST', body: JSON.stringify({ question, context }), signal,
  }),
  receipt: (id: string, signal?: AbortSignal) => request<ReceiptView>(`/receipts/${encodeURIComponent(id)}`, { signal }),
  receipts: (cursor?: string | null, limit = 20, signal?: AbortSignal) => request<ReceiptList>(`/receipts?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, { signal }),
  deleteReceipt: (id: string, signal?: AbortSignal) => request<void>(`/receipts/${encodeURIComponent(id)}`, { method: 'DELETE', signal }),
  compare: (body: CompareRequest, signal?: AbortSignal) => request<ComparisonView>('/comparisons', { method: 'POST', body: JSON.stringify(body), signal }),
  createDraft: (body: CreateDraftRequest, key: string, signal?: AbortSignal) => request<DraftView>('/drafts', { method: 'POST', body: JSON.stringify(body), headers: { 'Idempotency-Key': key }, signal }),
  draft: (id: string, signal?: AbortSignal) => request<DraftView>(`/drafts/${encodeURIComponent(id)}`, { signal }),
  editDraft: (id: string, body: EditDraftRequest, signal?: AbortSignal) => request<DraftView>(`/drafts/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body), signal }),
  deleteDraft: (id: string, signal?: AbortSignal) => request<void>(`/drafts/${encodeURIComponent(id)}`, { method: 'DELETE', signal }),
  upload: (file: File, idempotencyKey: string, signal?: AbortSignal, demoSampleId?: string) => {
    const body = new FormData();
    body.append('file', file);
    if (demoSampleId) body.append('demo_sample_id', demoSampleId);
    return request<ReceiptQueued>('/receipts', { method: 'POST', body, headers: { 'Idempotency-Key': idempotencyKey }, signal });
  },
  importDemo: (fixtureId: string, idempotencyKey: string, signal?: AbortSignal) => request<ReceiptQueued>('/receipts/demo', {
    method: 'POST', body: JSON.stringify({ fixture_id: fixtureId }), headers: { 'Idempotency-Key': idempotencyKey }, signal,
  }),
  job: (id: string, signal?: AbortSignal) => request<Job>(`/jobs/${encodeURIComponent(id)}`, { signal }),
  page: (id: string, page: number, signal?: AbortSignal) => requestBlob(`/receipts/${encodeURIComponent(id)}/pages/${page}`, signal),
  source: (id: string, signal?: AbortSignal) => requestBlob(`/receipts/${encodeURIComponent(id)}/source`, signal),
  editReceipt: (id: string, body: EditReceiptRequest, signal?: AbortSignal) => request<ReceiptView>(`/receipts/${encodeURIComponent(id)}/draft`, {
    method: 'PUT', body: JSON.stringify(body), signal,
  }),
  confirmReceipt: (id: string, body: ConfirmReceiptRequest, key: string, signal?: AbortSignal) => request<ReceiptView>(`/receipts/${encodeURIComponent(id)}/confirm`, {
    method: 'POST', body: JSON.stringify(body), headers: { 'Idempotency-Key': key }, signal,
  }),
  explanation: (id: string, revision: number, signal?: AbortSignal) => request<ReceiptExplanation>(`/receipts/${encodeURIComponent(id)}/explanation?revision=${revision}`, { signal }),
  cityComparison: (id: string, serviceCode: string, metric: CityComparisonView['metric'], signal?: AbortSignal) =>
    request<CityComparisonView>(`/receipts/${encodeURIComponent(id)}/city-comparison?service_code=${encodeURIComponent(serviceCode)}&metric=${encodeURIComponent(metric)}`, { signal }),
  previewCityComparison: (id: string, serviceCode: string, metric: SyntheticCityComparisonView['metric'], signal?: AbortSignal) =>
    request<SyntheticCityComparisonView>(`/preview/receipts/${encodeURIComponent(id)}/city-comparison?service_code=${encodeURIComponent(serviceCode)}&metric=${encodeURIComponent(metric)}`, { signal }),
};
