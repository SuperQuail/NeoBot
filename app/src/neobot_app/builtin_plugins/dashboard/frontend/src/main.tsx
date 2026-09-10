import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
// 顺序很重要：tailwind.css 含 preflight（基础重置），必须排在业务样式之前，
// 否则 theme/panel 的既有规则会被重置覆盖。组件内不要再 import 全局样式表，
// 统一在这里按层级顺序引入，避免 Vite 因模块顺序把某个样式表提到最前面。
import './styles/tailwind.css';
import './styles/theme.css';
import './styles/panel.css';
import './styles/workspace.css';
import './styles/plugins.css';

// 启动时初始化主题（沿用 data-theme + localStorage 约定）
const THEME_KEY = 'neobot-dashboard-theme';
const saved = localStorage.getItem(THEME_KEY);
const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
document.documentElement.dataset.theme = saved || (prefersDark ? 'dark' : 'light');

const container = document.getElementById('root');
if (!container) throw new Error('#root 容器缺失，index.html 可能被改动');

createRoot(container).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
