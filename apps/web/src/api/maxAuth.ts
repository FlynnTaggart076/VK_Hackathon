import { request } from './client';
import type { AuthResponse } from './types';

// MAX Bridge supplies the signed, URL-encoded string. Its parsed initDataUnsafe
// object is display data and must never be used as proof of identity.
declare global {
  interface Window {
    WebApp?: { initData?: string; platform?: string; openLink?: (url: string) => void; ready?: () => void };
  }
}

export function maxInitData(): string | null {
  const value = window.WebApp?.initData;
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function maxAuth(initData: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/max', {
    method: 'POST', body: JSON.stringify({ init_data: initData }),
  });
}

export async function loadMaxBridge(): Promise<void> {
  if (window.WebApp) return;
  await new Promise<void>((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://st.max.ru/js/max-web-app.js';
    script.async = true;
    const timeout = window.setTimeout(resolve, 5000);
    const done = () => { window.clearTimeout(timeout); window.dispatchEvent(new Event('zhkh:max-bridge-ready')); resolve(); };
    script.onload = done;
    script.onerror = done;
    document.head.append(script);
  });
}
