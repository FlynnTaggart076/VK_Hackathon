export function normalizeAppBase(value: string): string {
  if (!value.startsWith('/') || !value.endsWith('/') || value.includes('//') || value.includes('..') || /[?#]/.test(value)) {
    throw new Error(`Invalid application base path: ${value}`);
  }
  return value;
}

// Vite's BASE_URL is `/` under Vitest; use the same explicit build input as vite.config.
export const APP_BASE = normalizeAppBase(import.meta.env.VITE_APP_BASE || '/team/zhkh/');
export const PREVIEW_MODE = import.meta.env.VITE_PREVIEW_MODE === 'true';
