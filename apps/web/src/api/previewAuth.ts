import { request } from './client';
import type { AuthResponse } from './types';

let pending: Promise<AuthResponse> | null = null;

// React StrictMode may mount twice. One server-issued guest per simultaneous attempt.
export function previewAuth(): Promise<AuthResponse> {
  if (!pending) {
    pending = request<AuthResponse>('/auth/preview', { method: 'POST' })
      .finally(() => { pending = null; });
  }
  return pending;
}
