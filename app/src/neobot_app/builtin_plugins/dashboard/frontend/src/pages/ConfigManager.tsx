// pages/ConfigManager.tsx —— 配置管理入口：只负责顶层 tab 路由，各面板独立成文件
import { useLayoutEffect, useRef, useState } from 'react';
import { BotConfigPanel } from './config/BotConfigPanel';
import { EnvPanel } from './config/EnvPanel';
import { ModelsPanel } from './config/ModelsPanel';
import { AssignPanel } from './config/AssignPanel';
import PageHeader from '../components/ui/PageHeader';
import { confirmAction } from '../components/ui/ConfirmDialog';

const TABS: Array<[string, string]> = [
  ['config', '本体配置'],
  ['env', '环境变量'],
  ['models', '模型库'],
  ['assign', '模型分配'],
];

export default function ConfigManager() {
  const [tab, setTab] = useState('config');
  const editorState = useRef({ dirty: false, busy: false });
  const [busy, setBusy] = useState(false);
  useLayoutEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<boolean | { dirty: boolean; busy: boolean }>).detail;
      editorState.current = typeof detail === 'boolean' ? { dirty: detail, busy: false } : detail;
      setBusy(editorState.current.busy);
    };
    window.addEventListener('dashboard-editor-state', handler);
    return () => {
      window.removeEventListener('dashboard-editor-state', handler);
      editorState.current = { dirty: false, busy: false };
      window.dispatchEvent(
        new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }),
      );
    };
  }, []);
  const switchTab = async (next: string) => {
    if (next === tab || editorState.current.busy) return;
    if (
      editorState.current.dirty &&
      !(await confirmAction({
        title: '切换配置面板？',
        description: '切换会丢弃当前面板尚未保存的修改。',
        confirmLabel: '放弃并切换',
        danger: true,
      }))
    )
      return;
    editorState.current = { dirty: false, busy: false };
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: editorState.current }));
    setTab(next);
  };
  return (
    <div className="page config-page page--viewport">
      <PageHeader
        title="配置管理"
        actions={
          <div className="config-tabs cfg-top-tabs">
            <div role="tablist" aria-label="配置管理">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={tab === key}
                  className={tab === key ? 'active' : ''}
                  disabled={busy}
                  onClick={() => switchTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        }
      />
      {tab === 'config' && <BotConfigPanel />}
      {tab === 'env' && <EnvPanel />}
      {tab === 'models' && <ModelsPanel />}
      {tab === 'assign' && <AssignPanel />}
    </div>
  );
}
