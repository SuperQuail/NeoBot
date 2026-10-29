import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import { initializeTheme } from './utils/theme';

// 全局样式只在入口引入。字体与 Tailwind preflight 先加载，再加载令牌和基础组件。
import './styles/fonts.css';
import './styles/tailwind.css';
import './styles/tokens.css';
import './styles/theme.css';
import './styles/controls.css';
import './styles/feedback.css';
import './styles/tables.css';
// 工作区布局与页面样式使用基础组件，不再通过历史补丁文件覆盖彼此。
import './styles/workspace.css';
import './styles/config-workspace.css';
import './styles/config-tree.css';
import './styles/environment.css';
import './styles/plugins.css';
import './styles/speaking-schedule.css';
import './styles/forms.css';
import './styles/field-editors.css';
import './styles/schema-collections.css';
import './styles/form-interaction.css';
import './styles/models.css';
import './styles/shell.css';
import './styles/viewers.css';
import './styles/chat-flows.css';
import './styles/prompt-history.css';
import './styles/archives.css';
import './styles/logs.css';
import './styles/prompts.css';
import './styles/scheduled.css';
import './styles/monitor.css';
import './styles/model-assignment.css';
import './styles/deploy.css';
import './styles/system.css';
import './styles/analytics.css';
import './styles/usage.css';
import './styles/analysis.css';
// 独立组件的布局、状态与无障碍表现。
import './styles/starship-toggle.css';
import './styles/motion.css';
import './styles/resource-card.css';
import './styles/editor.css';
import './styles/skeleton.css';
import './styles/record-list.css';
import './styles/task-status.css';
import './styles/password-settings.css';

// 启动时初始化主题（沿用 data-theme + localStorage 约定）
initializeTheme();

const container = document.getElementById('root');
if (!container) throw new Error('#root 容器缺失，index.html 可能被改动');

createRoot(container).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
