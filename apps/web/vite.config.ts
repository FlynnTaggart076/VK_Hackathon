import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  base: '/team/zhkh/',
  plugins: [react()],
  server: { host: '127.0.0.1' },
  ...(mode === 'real' ? { server: { host: '127.0.0.1', proxy: {
    '/team/zhkh/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: (path: string) => path.replace(/^\/team\/zhkh/, '') },
  } } } : {}),
  publicDir: mode === 'mock' ? 'public' : false,
  test: { environment: 'node' },
}));
