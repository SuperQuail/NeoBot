import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const crawlerHeaders = { 'X-Robots-Tag': 'noindex, nofollow, nosnippet, noimageindex' };

// 面板由官方 dashboard 插件提供，支持 base_path 前缀访问，
// 因此资源使用相对路径（base: './'），产物输出到 ../web。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'NEOBOT_');
  const apiTarget = env.NEOBOT_API_TARGET || 'http://localhost:9981';
  return {
    plugins: [react(), tailwindcss()],
    base: './',
    build: {
      outDir: '../web',
      emptyOutDir: true,
      assetsDir: 'assets',
      sourcemap: false,
    },
    server: {
      port: 5173,
      headers: crawlerHeaders,
      // 测试和文档不参与页面运行，避免修改它们时整页刷新并丢失演示草稿。
      watch: { ignored: ['**/src/test/**', '**/*.md', '**/scripts/**'] },
      // changeOrigin 必须为 false：后端对 /api/auth/login 与 /api/auth/setup 会校验
      // Origin 与 Host 同源（防 CSRF），而字符串简写会被 Vite 展开成
      // { target, changeOrigin: true }，把 Host 改写成 localhost:9981，
      // 于是浏览器发来的 Origin: http://localhost:5173 对不上，登录直接 403。
      // 保留浏览器原始 Host 后两者天然同源，生产环境的校验语义不受影响。
      proxy: {
        '/api': { target: apiTarget, changeOrigin: false },
        '/image': { target: apiTarget, changeOrigin: false },
        '/bilibili': { target: apiTarget, changeOrigin: false },
      },
    },
    preview: { headers: crawlerHeaders },
  };
});
