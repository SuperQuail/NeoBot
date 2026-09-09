import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App.jsx';
import './styles/theme.css';
import './styles/panel.css';

// 启动时初始化主题（沿用 data-theme + localStorage 约定）
const THEME_KEY = 'neobot-dashboard-theme';
const saved = localStorage.getItem(THEME_KEY);
const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
document.documentElement.dataset.theme = saved || (prefersDark ? 'dark' : 'light');

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>
);
