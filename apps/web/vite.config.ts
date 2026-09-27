import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const composeProxy = process.env.E2_API_PROXY_TARGET;
const apiTarget = composeProxy ? (composeProxy.startsWith('http://') || composeProxy.startsWith('https://') ? composeProxy : `http://${composeProxy}`) : 'http://127.0.0.1:8000';

export default defineConfig(({ mode }) => ({
  base: '/team/zhkh/',
  plugins: [react()],
  server: { host: '127.0.0.1' },
  ...(mode === 'real' ? { server: { host: '127.0.0.1', proxy: {
    '/team/zhkh/api': { target: apiTarget, changeOrigin: true,
      rewrite: (path: string) => composeProxy ? path : path.replace(/^\/team\/zhkh/, '') },
  } } } : {}),
  publicDir: mode === 'mock' ? 'public' : false,
  test: { environment: 'node' },
}));
