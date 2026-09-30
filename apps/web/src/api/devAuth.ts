// Loaded only when the server reports features.demo_auth (dev/demo stands; production forbids it).
// The access code is typed by the tester and never stored in the bundle.
import { request } from './client';
import type { AuthResponse } from './types';

export function demoAuth(accessCode: string, identity: 'reviewer_a' | 'reviewer_b' = 'reviewer_a') {
  return request<AuthResponse>('/auth/demo', {
    method: 'POST', body: JSON.stringify({ access_code: accessCode, identity }),
  });
}
