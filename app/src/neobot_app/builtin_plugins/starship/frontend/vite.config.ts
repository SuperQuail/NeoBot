import { defineConfig } from 'vite';

// 星舰游戏由官方 starship 插件提供，页面挂在面板端口下（默认 /game/），
// 支持面板 base_path 前缀访问，因此资源使用相对路径（base: './'），
// 产物输出到 ../web（随包分发；部署方不需要 Node 工具链）。
export default defineConfig({
  base: './',
  build: {
    outDir: '../web',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 1600,
  },
  server: {
    port: 5174,
    proxy: {
      // 开发时把游戏接口与控制台接口都代理到面板端口
      '/game': { target: 'http://localhost:9981', changeOrigin: false },
      '/api': { target: 'http://localhost:9981', changeOrigin: false },
    },
  },
});
