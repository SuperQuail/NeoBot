import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 面板由官方 dashboard 插件提供，支持 base_path 前缀访问，
// 因此资源使用相对路径（base: './'），产物输出到 ../web。
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../web',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9981',
      '/image': 'http://localhost:9981',
    },
  },
});
