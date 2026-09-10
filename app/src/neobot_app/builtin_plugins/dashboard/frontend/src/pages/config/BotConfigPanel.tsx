// pages/config/BotConfigPanel.tsx —— 本体 config.toml 在线编辑（表单 / TOML、撤销重做、历史、热重载明细）
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { ConfigSaveBody } from '../../api/endpoints';
import type { ConfigChanges, ConfigDocument, FieldDescriptor } from '../../api/types';
import { toast } from '../../components/Toast';
import Icon from '../../components/Icon';
import SchemaForm from '../../components/SchemaForm';
import { getPath, setPath } from '../../utils/paths';
import { bindValues, changedLeaves, type ChangeEntry, type HistoryMap, type Notice } from './shared';
function BotConfigPanel() {
  const [doc, setDoc] = useState<ConfigDocument | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState<'form' | 'toml'>('form');
  const [filter, setFilter] = useState('');
  const [errors, setErrors] = useState<Array<{ path?: string; message?: string }>>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState('read');
  const operationRef = useRef(false);
  const [undoStack, setUndoStack] = useState<ChangeEntry[]>([]);
  const [redoStack, setRedoStack] = useState<ChangeEntry[]>([]);
  const [history, setHistory] = useState<HistoryMap>({});
  const [collapse, setCollapse] = useState<Record<string, boolean>>({});
  const [changes, setChanges] = useState<ConfigChanges | null>(null);
  const draftRef = useRef<Record<string, any>>({});
  draftRef.current = draft;
  const fields = useMemo(() => bindValues(doc?.schema || [], draft), [doc, draft]);

  const applyDoc = useCallback((data: ConfigDocument) => {
    setDoc(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setErrors([]);
    setNotice(null);
    setUndoStack([]);
    setRedoStack([]);
    setHistory({});
  }, []);

  const pushHistory = useCallback((path: string[], value: unknown) => {
    const key = path.join('.') || '(root)';
    setHistory((previous) => ({
      ...previous,
      [key]: [{ value, at: new Date().toLocaleTimeString() }, ...(previous[key] || [])].slice(0, 20),
    }));
  }, []);

  const recordChange = useCallback((path: string[], before: unknown, after: unknown) => {
    setUndoStack((stack) => [...stack, { path, before, after }].slice(-200));
    setRedoStack([]);
  }, []);

  const applyValue = useCallback((path: string[], value: unknown) => {
    setDraft((previous) => setPath(previous, path, value));
  }, []);

  const runOperation = useCallback(async (name: string, action: () => Promise<void>) => {
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy(name);
    try {
      await action();
    } catch (error) {
      setNotice({ text: error instanceof Error ? error.message : '配置操作失败', warning: true });
    } finally {
      operationRef.current = false;
      setBusy('');
    }
  }, []);

  const read = useCallback(() => runOperation('read', async () => {
    const result = await api.config();
    if (!result.ok || !result.data) {
      setNotice({ text: result.error || '读取配置失败', warning: true });
      return;
    }
    applyDoc(result.data);
  }), [applyDoc, runOperation]);

  useEffect(() => {
    read();
  }, [read]);

  const dirty = useMemo(() => {
    if (!doc) return false;
    return mode === 'toml'
      ? source !== doc.source
      : JSON.stringify(draft) !== JSON.stringify(doc.config);
  }, [doc, draft, source, mode]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty, busy: !!busy } }));
  }, [dirty, busy]);
  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }));
  }, []);

  const switchMode = (next: 'form' | 'toml') => {
    if (busy || operationRef.current || !doc || mode === next) return;
    if (dirty && !confirm('切换编辑方式会丢弃当前模式未保存的修改，并重新载入已读取的配置，不会转换草稿。确认切换？')) return;
    applyDoc(doc);
    setMode(next);
  };

  const reread = () => {
    if (busy || operationRef.current) return;
    if (dirty && !confirm('重新读取会丢弃未保存的修改，确认继续？')) return;
    void read();
  };

  const discard = () => {
    if (busy || operationRef.current || !doc) return;
    if (dirty && !confirm('确认放弃未保存的修改？')) return;
    applyDoc(doc);
    setChanges(null);
  };

  const changeField = useCallback((path: string[], value: unknown) => {
    if (operationRef.current || mode !== 'form') return;
    const before = getPath(draftRef.current, path);
    if (JSON.stringify(before ?? null) === JSON.stringify(value ?? null)) return;
    recordChange(path, before, value);
    // 分组修改时按叶子路径记录历史，便于逐项查看/恢复
    for (const leaf of changedLeaves(before, value, path)) {
      pushHistory(leaf.path, leaf.before);
    }
    applyValue(path, value);
  }, [applyValue, pushHistory, recordChange, mode]);

  const restoreValue = useCallback((path: string[], value: unknown) => {
    if (operationRef.current || mode !== 'form') return;
    const before = getPath(draftRef.current, path);
    recordChange(path, before, value);
    pushHistory(path, before);
    applyValue(path, value);
  }, [applyValue, pushHistory, recordChange, mode]);

  const undo = useCallback(() => {
    if (busy || operationRef.current || mode !== 'form') return;
    const entry = undoStack[undoStack.length - 1];
    if (!entry) return;
    applyValue(entry.path, entry.before);
    setRedoStack((stack) => [...stack, entry]);
    setUndoStack((stack) => stack.slice(0, -1));
  }, [applyValue, busy, mode, undoStack]);

  const redo = useCallback(() => {
    if (busy || operationRef.current || mode !== 'form') return;
    const entry = redoStack[redoStack.length - 1];
    if (!entry) return;
    applyValue(entry.path, entry.after);
    setUndoStack((stack) => [...stack, entry]);
    setRedoStack((stack) => stack.slice(0, -1));
  }, [applyValue, busy, mode, redoStack]);

  const resetAllDefaults = useCallback(() => {
    if (!doc || busy || operationRef.current || mode !== 'form') return;
    if (!confirm('把所有配置项恢复为默认值？可撤销。')) return;
    const next = structuredClone(draftRef.current || {});
    const walk = (fields: FieldDescriptor[] | undefined, node: Record<string, any>) => {
      for (const field of fields || []) {
        if (field.kind === 'group') {
          if (!node[field.name] || typeof node[field.name] !== 'object') node[field.name] = {};
          walk(field.fields, node[field.name]);
        } else if (field.default !== undefined) {
          node[field.name] = structuredClone(field.default);
        }
      }
    };
    walk(doc.schema, next);
    recordChange([], structuredClone(draftRef.current), structuredClone(next));
    setDraft(next);
  }, [doc, recordChange, busy, mode]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty && !busy) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty, busy]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target;
      if (busy || operationRef.current || mode === 'toml') return;
      if (target instanceof HTMLElement && (target.closest('input, textarea, [contenteditable]:not([contenteditable="false"])') || target.isContentEditable)) return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 'z' && !event.shiftKey) { event.preventDefault(); undo(); }
      else if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); redo(); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo, busy, mode]);

  const validate = () => runOperation('validate', async () => {
    const body: ConfigSaveBody = mode === 'toml' ? { mode, source } : { mode, config: draft };
    const result = await api.configValidate(body);
    if (result.ok) {
      setErrors([]);
      toast('配置校验通过', 'ok');
    } else {
      setErrors(result.data?.errors || []);
      toast(result.error || '配置校验未通过', 'err');
    }
  });

  const save = (reload: boolean) => runOperation('save', async () => {
    if (!doc) return;
    const body: ConfigSaveBody = {
      revision: doc.revision,
      mode,
      reload,
      ...(mode === 'toml' ? { source } : { config: draft }),
    };
    const result = await api.configSave(body);
    if (!result.ok || !result.data) {
      if (result.status === 409) {
        setNotice({ text: result.error || '配置已被其它会话修改', warning: true });
        toast('配置已被其它会话修改，请重新读取', 'err');
      } else {
        setErrors(result.data?.errors || []);
        toast(result.error || '保存失败', 'err');
      }
      return;
    }
    const saved = result.data;
    applyDoc(saved);
    setChanges(saved.changes || null);
    setNotice({ text: saved.message || '配置已保存', warning: !saved.applied && reload });
    toast(saved.message || '配置已保存', 'ok');
  });

  const reloadRuntime = () => {
    if (busy || operationRef.current) return;
    if (dirty && !confirm('重载运行时只使用已保存的配置，不会保存当前草稿。确认继续？')) return;
    return runOperation('reload', async () => {
      const result = await api.configReload();
      if (result.ok) {
        setChanges(result.data?.changes || null);
        toast(result.data?.message || '配置已重载', 'ok');
      } else {
        toast(result.error || '重载失败', 'err');
      }
    });
  };

  const restart = () => {
    if (busy || operationRef.current) return;
    if (!confirm(dirty ? '重启不会保存当前草稿，未保存的修改可能丢失。确认重启 NeoBot？面板会短暂不可用。' : '确认重启 NeoBot？面板会短暂不可用。')) return;
    return runOperation('restart', async () => {
      const result = await api.restart();
      toast(result.ok ? result.data?.message || '已请求重启' : result.error || '重启失败', result.ok ? 'ok' : 'err');
    });
  };

  if (busy === 'read' && !doc) {
    return <section className="card"><p className="empty muted" role="status">正在读取 config.toml…</p></section>;
  }
  if (!doc) {
    return (
      <section className="card">
        <div className="workspace-error" role="alert">
          {notice?.text || '无法读取配置'}
          <button className="btn-sm" onClick={read}>重试</button>
        </div>
      </section>
    );
  }

  return (
    <section className="card config-card">
      <div className="config-toolbar">
        <div className="config-tabs">
          <div role="tablist" aria-label="编辑方式">
            <button
              role="tab"
              aria-selected={mode === 'form'}
              className={mode === 'form' ? 'active' : ''}
              disabled={!!busy}
              onClick={() => switchMode('form')}
            >
              <Icon name="settings" /> 表单
            </button>
            <button
              role="tab"
              aria-selected={mode === 'toml'}
              className={mode === 'toml' ? 'active' : ''}
              disabled={!!busy}
              onClick={() => switchMode('toml')}
            >
              <Icon name="code" /> TOML
            </button>
          </div>
        </div>
        {mode === 'form' && (
          <input
            className="input cfg-search"
            placeholder="搜索配置项…"
            value={filter}
            disabled={!!busy}
            onChange={(event) => setFilter(event.target.value)}
          />
        )}
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={validate}>{busy === 'validate' ? '校验中…' : '校验'}</button>
        <button className="btn" disabled={!!busy || mode === 'toml' || !undoStack.length} title="撤销 (Ctrl+Z)" onClick={undo}>
          <Icon name="undo" /> 撤销{undoStack.length ? ' ' + undoStack.length : ''}
        </button>
        <button className="btn" disabled={!!busy || mode === 'toml' || !redoStack.length} title="重做 (Ctrl+Y)" onClick={redo}>
          <Icon name="refresh" /> 重做
        </button>
        <button className="btn" disabled={!!busy || mode === 'toml' || !doc} title="所有配置项恢复默认值" onClick={resetAllDefaults}>
          全部恢复默认
        </button>
        <button className="btn" disabled={!!busy || !dirty} onClick={discard}>放弃修改</button>
        <button className="btn" disabled={!!busy} onClick={reread}>{busy === 'read' ? '读取中…' : '重新读取'}</button>
        <button className="btn primary" disabled={!!busy || !dirty} onClick={() => save(true)}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
        </button>
      </div>

      {notice && (
        <div className={'config-notice' + (notice.warning ? ' warning' : '')} role="status">
          <Icon name={notice.warning ? 'more' : 'check'} />
          {notice.text}
        </div>
      )}
      {errors.length > 0 && (
        <div className="workspace-error" role="alert">
          <strong>校验失败：</strong>
          <ul className="cfg-errors">
            {errors.slice(0, 12).map((item, index) => (
              <li key={index}><code>{item.path || '?'}</code> {item.message}</li>
            ))}
          </ul>
        </div>
      )}
      {changes && ((changes.hot_reload_count ?? 0) > 0 || (changes.needs_restart_count ?? 0) > 0) && (
        <div className="cfg-changes" role="status">
          <strong>
            热重载结果：{changes.hot_reload_count} 项已生效，{changes.needs_restart_count} 项需重启
          </strong>
          {(changes.hot_reload?.length ?? 0) > 0 && (
            <details open>
              <summary>已生效（{changes.hot_reload?.length}）</summary>
              <ul className="cfg-errors">
                {changes.hot_reload?.slice(0, 12).map((item) => (
                  <li key={item.path}><code>{item.path}</code> {String(item.before)} → {String(item.after)}</li>
                ))}
              </ul>
            </details>
          )}
          {(changes.needs_restart?.length ?? 0) > 0 && (
            <details>
              <summary>需重启 NeoBot 后生效（{changes.needs_restart?.length}）</summary>
              <ul className="cfg-errors">
                {changes.needs_restart?.slice(0, 12).map((item) => (
                  <li key={item.path}><code>{item.path}</code> {item.reason || '构建期配置'}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <div className="config-body">
        {mode === 'form' ? (
          <SchemaForm
            fields={fields}
            values={draft}
            baseline={doc.config || {}}
            disabled={!!busy}
            filter={filter}
            history={history}
            collapse={collapse}
            onToggleCollapse={(key) => setCollapse((previous) => ({ ...previous, [key]: !previous[key] }))}
            onRestore={restoreValue}
            onChange={changeField}
          />
        ) : (
          <>
            <p className="muted small">直接编辑整份 config.toml；保存前会做语法与类型校验，并自动备份旧文件。</p>
            <textarea
              className="toml-editor"
              aria-label="config.toml"
              spellCheck={false}
              disabled={!!busy}
              value={source}
              onChange={(event) => setSource(event.target.value)}
            />
          </>
        )}
      </div>

      <div className="config-footer">
        <span className={dirty ? 'dirty-label' : 'muted'}>
          <i className={'plugin-status-dot' + (dirty ? ' pending' : '')} />
          {dirty ? '有未保存的修改' : '与文件同步'}
        </span>
        <span className="muted small">{doc.path}</span>
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={reloadRuntime}>
          <Icon name="refresh" /> {busy === 'reload' ? '重载中…' : '重载运行时配置'}
        </button>
        <button className="btn danger" disabled={!!busy} onClick={restart}>{busy === 'restart' ? '重启中…' : '重启 NeoBot'}</button>
      </div>
    </section>
  );
}


export { BotConfigPanel };
