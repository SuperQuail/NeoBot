import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/**
 * 产物 index.html 的行尾统一成 LF。
 *
 * Vite 生成 HTML 时会保留模板（frontend/index.html）的行尾：Windows 检出的是 CRLF，
 * Linux 是 LF，因此同一份源码在两个平台会产出**不同字节**的 web/index.html，而
 * web/ 又是入库产物——CI 在 Linux 上跑「产物与源码一致」检查时必然报不一致。
 * 这里在 HTML 生成（含资源标签注入）之后统一行尾，顺带清掉 Windows 模板里
 * 残留的孤立 CR。`enforce: 'post'` 保证它排在核心 HTML 插件之后。
 */
function normalizeHtmlEol(): Plugin {
  return {
    name: 'neobot-normalize-html-eol',
    enforce: 'post',
    transformIndexHtml(html) {
      return html.replace(/\r\n?/g, '\n');
    },
  };
}

// 面板由官方 dashboard 插件提供，产物输出到 ../web 并随 Python 包入库。
//
// base 取 '/bridge/' 而不是 './'：React.lazy 动态导入的 chunk 是用 import.meta.url
// 解析的，相对 base 下会退化成「相对当前页面路径」——从 /bridge/ 进入没问题，
// 但一旦地址栏变成 /bridge/xxx（SPA 深链），chunk 就会请求到错误目录而 404。
// 用绝对 base 后 chunk 与静态资源的 URL 恒定指向 /bridge/assets/*，服务端只需把
// /bridge/* 映射到 web/ 目录（见 dashboard/server.py 的 _bridge_asset）。
export default defineConfig({
  plugins: [react(), tailwindcss(), normalizeHtmlEol()],
  base: '/bridge/',
  build: {
    outDir: '../web',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    // three.js 单块 500KB+ 是预期内的（它本来就只在进入 #/bridge 时懒加载），
    // 把阈值提高，避免每次构建都刷一条无意义的告警。
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // three.js 单独成块：升级依赖不会让面板主 chunk 的缓存整块失效
        manualChunks: (id: string) => (id.includes('node_modules/three') ? 'three' : undefined),
      },
    },
  },
  server: {
    port: 5173,
    // 开发服务器下 /bridge/ 之外的静态资源（图标、图片）仍按根路径访问
    proxy: {
      '/api': { target: 'http://localhost:9981', changeOrigin: false },
      '/image': { target: 'http://localhost:9981', changeOrigin: false },
    },
  },
});
