// Loaded only by the local development entry screen. Never import from a production route.
import { request } from './client';
import type { AuthResponse } from './types';

export function demoAuth(accessCode: string, identity: 'reviewer_a' | 'reviewer_b' = 'reviewer_a') {
  return request<AuthResponse>('/auth/demo', {
    method: 'POST', body: JSON.stringify({ access_code: accessCode, identity }),
  });
}
