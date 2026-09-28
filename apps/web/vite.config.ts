import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const composeProxy = process.env.E2_API_PROXY_TARGET ?? (process.env.REAL_API_PRESERVE_PREFIX === 'true' ? process.env.REAL_API_TARGET : undefined);
const targetValue = composeProxy ?? process.env.REAL_API_TARGET ?? 'http://127.0.0.1:8000';
const apiTarget = targetValue.startsWith('http://') || targetValue.startsWith('https://') ? targetValue : `http://${targetValue}`;
const appBase = process.env.VITE_APP_BASE ?? '/team/zhkh/';
if (!appBase.startsWith('/') || !appBase.endsWith('/') || appBase.includes('//') || appBase.includes('..') || /[?#]/.test(appBase)) {
  throw new Error(`Invalid VITE_APP_BASE: ${appBase}`);
}
const basePrefix = appBase.slice(0, -1);

export default defineConfig(({ mode }) => ({
  base: appBase,
  plugins: [react()],
  server: { host: '127.0.0.1' },
  ...(mode === 'real' ? { server: { host: '127.0.0.1', proxy: {
    [`${appBase}api`]: { target: apiTarget, changeOrigin: true,
      rewrite: (path: string) => composeProxy ? path : path.slice(basePrefix.length) },
  } } } : {}),
  publicDir: mode === 'mock' ? 'public' : false,
  test: { environment: 'node' },
}));
