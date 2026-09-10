// Vitest 配置 —— jsdom 环境 + Testing Library（TypeScript）
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 与 vite.config.ts 一致：与应用同源部署，产物由 /bridge/ 提供
  base: '/bridge/',
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
