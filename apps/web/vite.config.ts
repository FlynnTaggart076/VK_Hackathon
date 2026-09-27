import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  base: '/team/zhkh/',
  plugins: [react()],
  server: { host: '127.0.0.1' },
  publicDir: mode === 'mock' ? 'public' : false,
  test: { environment: 'node' },
}));
