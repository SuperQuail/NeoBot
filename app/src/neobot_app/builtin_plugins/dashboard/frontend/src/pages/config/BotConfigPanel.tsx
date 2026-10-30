// pages/config/BotConfigPanel.tsx —— 本体 config.toml 在线编辑与操作反馈
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { ConfigSaveBody } from '../../api/endpoints';
import type { ConfigChangeItem, ConfigChanges, ConfigDocument, FieldDescriptor } from '../../api/types';
import { closeInfoBarDetails, infoBar } from '../../notifications/infoBar';
import Icon from '../../components/Icon';
import TomlEditor from '../../components/TomlEditor';
import Button from '../../components/ui/Button';
import { confirmAction } from '../../components/ui/ConfirmDialog';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { ConfigTreePanel } from './ConfigTreePanel';
import { getPath, setPath } from '../../utils/paths';
import { changedLeaves, useConfigAutoRead, type ChangeEntry, type HistoryMap } from './shared';
import { useAuthGate } from '../../auth/AuthContext';

type ValidationIssue = { path?: string; message?: string };
type ReloadFeedback = { message?: string; changes?: ConfigChanges; needs_restart_parts?: unknown };
const OPERATION_FAILURES: Record<string, string> = {
  read: '读取配置失败',
  validate: '配置校验失败',
  save: '保存配置失败',
  reload: '重载配置失败',
  restart: '重启失败',
};

function ChangeList({ title, items }: { title: string; items: ConfigChangeItem[] }) {
  if (!items.length) return null;
  return (
    <section>
      <strong>
        {title}（{items.length}）
      </strong>
      <ul className="cfg-errors">
        {items.map((item, index) => (
          <li key={`${item.path}-${index}`}>
            <code>{item.path || '配置项'}</code>
            {item.before !== undefined && item.after !== undefined && (
              <>
                ：<code>{JSON.stringify(item.before)}</code> → <code>{JSON.stringify(item.after)}</code>
              </>
            )}
            {item.reason && <> · {item.reason}</>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function reportReload(title: string, result: ReloadFeedback, reloadFailed = false) {
  const changes = result.changes;
  const hot = changes?.hot_reload || [];
  const restart = changes?.needs_restart || [];
  const hotCount = Math.max(changes?.hot_reload_count || 0, hot.length);
  const restartCount = Math.max(changes?.needs_restart_count || 0, restart.length);
  const restartParts = Array.isArray(result.needs_restart_parts)
    ? result.needs_restart_parts.filter((part): part is string => typeof part === 'string')
    : [];
  // 有些旧接口只在 message 中透传模块级重启要求；“0 项需重启”不应触发警告。
  const restartMessage = /(?:仍需|需要?|必须)重启|重启.*生效/.test(
    (result.message || '').replace(/0\s*项需重启/g, ''),
  );
  const requiresRestart = restartCount > 0 || restartParts.length > 0 || restartMessage;
  const summary = reloadFailed
    ? '配置已保存，重载未完成'
    : requiresRestart
      ? `${title}，${restartCount > 0 ? `${restartCount} 项` : '部分改动'}需重启`
      : `${title}${hotCount > 0 ? ` · ${hotCount} 项已生效` : ''}`;
  const hasDetails = !!result.message || hot.length > 0 || restart.length > 0 || restartParts.length > 0;
  infoBar({
    title: summary,
    tone: reloadFailed || requiresRestart ? 'warn' : 'ok',
    duration: reloadFailed || requiresRestart ? 0 : 4000,
    details: hasDetails ? (
      <div>
        {result.message && <p>{result.message}</p>}
        <ChangeList title="已生效" items={hot} />
        <ChangeList title="重启后生效" items={restart} />
        {restartParts.length > 0 && <p>仍需重启：{restartParts.join('、')}</p>}
      </div>
    ) : undefined,
  });
}

function BotConfigPanel() {
  const { canManage } = useAuthGate();
  const readOnly = canManage === false;
  const [doc, setDoc] = useState<ConfigDocument | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState<'form' | 'toml'>('form');
  const [filter, setFilter] = useState('');
  const [readError, setReadError] = useState('');
  const [readRecovery, setReadRecovery] = useState(false);
  const [editingSession, setEditingSession] = useState(false);
  const [busy, setBusy] = useState('read');
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 1100px)').matches);
  const [moreOpen, setMoreOpen] = useState(false);
  const operationRef = useRef(false);
  const [undoStack, setUndoStack] = useState<ChangeEntry[]>([]);
  const [redoStack, setRedoStack] = useState<ChangeEntry[]>([]);
  const [history, setHistory] = useState<HistoryMap>({});
  const [collapse, setCollapse] = useState<Record<string, boolean>>({});
  const draftRef = useRef<Record<string, any>>({});
  const docRef = useRef<ConfigDocument | null>(null);
  draftRef.current = draft;
  docRef.current = doc;

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1100px)');
    const update = () => {
      setCompact(media.matches);
      setMoreOpen(false);
    };
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const applyDoc = useCallback((data: ConfigDocument) => {
    setDoc(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setReadError('');
    setReadRecovery(false);
    setEditingSession(false);
    setUndoStack([]);
    setRedoStack([]);
    setHistory({});
  }, []);

  const dirty = useMemo(() => {
    if (!doc) return false;
    return mode === 'toml' ? source !== doc.source : JSON.stringify(draft) !== JSON.stringify(doc.config);
  }, [doc, draft, source, mode]);
  const invalidateAutoRead = useConfigAutoRead({
    enabled: !dirty && !busy && !editingSession,
    identity: doc,
    read: api.config,
    apply: applyDoc,
    onError: setReadError,
    fallback: '自动读取配置失败',
  });
  const protectFieldDraft = () => {
    invalidateAutoRead();
    // JSON 和自定义参数有尚未提交给父层的本地文本；整个编辑会话保持原始 revision。
    setEditingSession(true);
  };

  const pushHistory = useCallback((path: Array<string | number>, value: unknown) => {
    const key = path.join('.') || '(root)';
    setHistory((previous) => ({
      ...previous,
      [key]: [{ value, at: new Date().toLocaleTimeString() }, ...(previous[key] || [])].slice(0, 20),
    }));
  }, []);

  const recordChange = useCallback((path: Array<string | number>, before: unknown, after: unknown) => {
    setUndoStack((stack) => [...stack, { path, before, after }].slice(-200));
    setRedoStack([]);
  }, []);

  const applyValue = useCallback((path: Array<string | number>, value: unknown) => {
    setDraft((previous) => setPath(previous, path, value));
  }, []);

  const runOperation = useCallback(
    async (name: string, action: () => Promise<void>) => {
      if (operationRef.current) return;
      invalidateAutoRead();
      operationRef.current = true;
      setBusy(name);
      try {
        await action();
      } catch (error) {
        const message = error instanceof Error ? error.message : '配置操作失败';
        if (name === 'read') setReadError(message);
        if (name !== 'read' || docRef.current) {
          infoBar({
            title: OPERATION_FAILURES[name] || '配置操作失败',
            tone: 'err',
            duration: 0,
            details: (
              <>
                <p>{message}</p>
                <p>当前修改已保留。</p>
              </>
            ),
          });
        }
      } finally {
        operationRef.current = false;
        setBusy('');
      }
    },
    [invalidateAutoRead],
  );

  const read = useCallback(
    () =>
      runOperation('read', async () => {
        const rereading = !!docRef.current;
        const result = await api.config();
        if (!result.ok || !result.data) {
          const message = result.error || '读取配置失败';
          setReadError(message);
          if (docRef.current)
            infoBar({
              title: '读取配置失败',
              tone: 'err',
              duration: 0,
              details: (
                <>
                  <p>{message}</p>
                  <p>当前修改已保留。</p>
                </>
              ),
            });
          return;
        }
        applyDoc(result.data);
        if (rereading) infoBar({ title: '已重新读取配置', tone: 'ok' });
      }),
    [applyDoc, runOperation],
  );

  useEffect(() => {
    read();
  }, [read]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty, busy: !!busy } }));
  }, [dirty, busy]);
  useEffect(
    () => () => {
      window.dispatchEvent(
        new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }),
      );
    },
    [],
  );

  const switchMode = async (next: 'form' | 'toml') => {
    if (busy || operationRef.current || !doc || mode === next) return;
    if (
      dirty &&
      !(await confirmAction({
        title: '切换编辑方式？',
        description: '切换会丢弃当前模式未保存的修改，并重新载入已读取的配置，不会转换草稿。',
        confirmLabel: '切换方式',
        danger: true,
      }))
    )
      return;
    applyDoc(doc);
    setMode(next);
  };

  const reread = async () => {
    if (busy || operationRef.current) return;
    if (
      dirty &&
      !(await confirmAction({
        title: '重新读取配置？',
        description: '当前未保存的修改会被文件中的配置替换。',
        confirmLabel: '重新读取',
        danger: true,
      }))
    )
      return;
    void read();
  };

  const discard = async () => {
    if (busy || operationRef.current || !doc) return;
    if (
      dirty &&
      !(await confirmAction({
        title: '放弃配置修改？',
        description: '恢复到上次读取的配置，尚未保存的修改会丢失。',
        confirmLabel: '放弃修改',
        danger: true,
      }))
    )
      return;
    applyDoc(doc);
  };

  const changeField = useCallback(
    (path: Array<string | number>, value: unknown) => {
      if (readOnly || operationRef.current || mode !== 'form') return;
      const before = getPath(draftRef.current, path);
      if (JSON.stringify(before ?? null) === JSON.stringify(value ?? null)) return;
      recordChange(path, before, value);
      // 分组修改时按叶子路径记录历史，便于逐项查看/恢复
      for (const leaf of changedLeaves(before, value, path)) {
        pushHistory(leaf.path, leaf.before);
      }
      applyValue(path, value);
    },
    [applyValue, pushHistory, recordChange, mode, readOnly],
  );

  const restoreValue = useCallback(
    (path: Array<string | number>, value: unknown) => {
      if (readOnly || operationRef.current || mode !== 'form') return;
      const before = getPath(draftRef.current, path);
      recordChange(path, before, value);
      pushHistory(path, before);
      applyValue(path, value);
    },
    [applyValue, pushHistory, recordChange, mode, readOnly],
  );

  const undo = useCallback(() => {
    if (readOnly || busy || operationRef.current || mode !== 'form') return;
    const entry = undoStack[undoStack.length - 1];
    if (!entry) return;
    applyValue(entry.path, entry.before);
    setRedoStack((stack) => [...stack, entry]);
    setUndoStack((stack) => stack.slice(0, -1));
  }, [applyValue, busy, mode, readOnly, undoStack]);

  const redo = useCallback(() => {
    if (readOnly || busy || operationRef.current || mode !== 'form') return;
    const entry = redoStack[redoStack.length - 1];
    if (!entry) return;
    applyValue(entry.path, entry.after);
    setUndoStack((stack) => [...stack, entry]);
    setRedoStack((stack) => stack.slice(0, -1));
  }, [applyValue, busy, mode, readOnly, redoStack]);

  const resetAllDefaults = useCallback(async () => {
    if (readOnly || !doc || busy || operationRef.current || mode !== 'form') return;
    if (
      !(await confirmAction({
        title: '全部恢复默认？',
        description: '把所有配置项恢复为默认值。本次操作可撤销，保存后生效。',
        confirmLabel: '恢复默认',
        danger: true,
      }))
    )
      return;
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
  }, [doc, recordChange, busy, mode, readOnly]);

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
      if (
        target instanceof HTMLElement &&
        (target.closest('input, textarea, [contenteditable]:not([contenteditable="false"])') ||
          target.isContentEditable)
      )
        return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
        event.preventDefault();
        redo();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo, busy, mode]);

  const reportValidation = (title: string, message: string | null, issues: ValidationIssue[] = []) => {
    infoBar({
      title: `${title}${issues.length ? ` · ${issues.length} 项问题` : ''}`,
      tone: 'err',
      duration: 0,
      details: (
        <div>
          {message && <p>{message}</p>}
          {issues.length > 0 && (
            <ul className="cfg-errors">
              {issues.map((item, index) => (
                <li key={`${item.path}-${index}`}>
                  {item.path &&
                    (mode === 'form' ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`定位 ${item.path}`}
                        onClick={() => {
                          if (operationRef.current || !item.path) return;
                          const path = item.path;
                          setFilter(path);
                          setCollapse((previous) =>
                            Object.fromEntries(
                              Object.entries(previous).map(([key, collapsed]) => [
                                key,
                                path === key || path.startsWith(`${key}.`) ? false : collapsed,
                              ]),
                            ),
                          );
                          setMoreOpen(false);
                          closeInfoBarDetails();
                        }}
                      >
                        <code>{item.path}</code>
                      </Button>
                    ) : (
                      <code>{item.path}</code>
                    ))}{' '}
                  {item.message || '配置值不符合要求'}
                </li>
              ))}
            </ul>
          )}
          <p>
            当前修改已保留。
            {mode === 'form' && issues.some((item) => item.path) ? '点击配置路径定位对应字段。' : ''}
          </p>
        </div>
      ),
    });
  };

  const validate = () =>
    runOperation('validate', async () => {
      const body: ConfigSaveBody = mode === 'toml' ? { mode, source } : { mode, config: draft };
      const result = await api.configValidate(body);
      if (result.ok) {
        infoBar({ title: '配置校验通过', tone: 'ok' });
      } else {
        reportValidation('配置校验未通过', result.error, result.data?.errors);
      }
    });

  const save = (reload: boolean) => {
    if (readOnly) return;
    return runOperation('save', async () => {
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
          setReadRecovery(true);
          infoBar({
            title: '保存失败：配置已被其它会话修改',
            tone: 'err',
            duration: 0,
            details: (
              <>
                <p>{result.error || '配置文件版本已变化。'}</p>
                <p>当前草稿已保留，请备份修改后重新读取并合并。</p>
              </>
            ),
          });
        } else {
          reportValidation('保存配置失败', result.error, result.data?.errors);
        }
        return;
      }
      const saved = result.data;
      applyDoc(saved);
      reportReload(reload ? '配置已保存并重载' : '配置已保存', saved, reload && saved.applied === false);
    });
  };

  const reloadRuntime = async () => {
    if (readOnly || busy || operationRef.current) return;
    if (
      dirty &&
      !(await confirmAction({
        title: '重载已保存的配置？',
        description: '重载运行时只使用已保存的配置，不会保存当前草稿。',
        confirmLabel: '重载运行时配置',
      }))
    )
      return;
    return runOperation('reload', async () => {
      const result = await api.configReload();
      if (result.ok) {
        reportReload('配置已重载', result.data || {});
      } else {
        infoBar({
          title: '重载配置失败',
          tone: 'err',
          duration: 0,
          details: <p>{result.error || '请稍后重试。'}</p>,
        });
      }
    });
  };

  const restart = async () => {
    if (readOnly || busy || operationRef.current) return;
    if (
      !(await confirmAction({
        title: '重启 NeoBot？',
        description: dirty
          ? '重启不会保存当前草稿，未保存的修改可能丢失。面板会短暂不可用。'
          : '面板与平台连接会短暂中断，完成后重新连接。',
        confirmLabel: '重启 NeoBot',
        danger: true,
      }))
    )
      return;
    return runOperation('restart', async () => {
      const result = await api.restart();
      infoBar({
        title: result.ok ? '已请求重启 NeoBot' : '重启失败',
        tone: result.ok ? 'ok' : 'err',
        duration: result.ok ? 8000 : 0,
        details: (result.ok ? result.data?.message : result.error) ? (
          <p>{result.ok ? result.data?.message : result.error}</p>
        ) : undefined,
      });
    });
  };

  if (busy === 'read' && !doc) {
    return (
      <section className="card">
        <PanelSkeleton label="正在读取 config.toml" />
      </section>
    );
  }
  if (!doc) {
    return (
      <section className="card">
        <div className="workspace-error" role="alert">
          {readError || '无法读取配置'}
          <Button size="sm" onClick={read}>
            重试
          </Button>
        </div>
      </section>
    );
  }

  const runtimeActions = (
    <>
      <Button
        size="sm"
        disabled={readOnly || !!busy}
        onClick={reloadRuntime}
        aria-label={busy === 'reload' ? '重载中…' : '重载运行时配置'}
        title="重载已保存的运行时配置，不保存当前草稿"
      >
        <Icon name="refresh" /> {busy === 'reload' ? '重载中…' : compact ? '重载运行时配置' : '重载配置'}
      </Button>
      <Button
        size="sm"
        variant="danger"
        disabled={readOnly || !!busy}
        onClick={restart}
        aria-label={busy === 'restart' ? '重启中…' : '重启 NeoBot'}
        title="重启 NeoBot"
      >
        {busy === 'restart' ? '重启中…' : compact ? '重启 NeoBot' : '重启'}
      </Button>
    </>
  );

  return (
    <section className="card config-card config-card-editor" onClickCapture={invalidateAutoRead}>
      <div
        className="config-toolbar config-main-toolbar"
        data-compact={compact}
        role="toolbar"
        aria-label="本体配置操作"
      >
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
        <span
          className={'config-sync-status' + (dirty ? ' dirty-label' : ' muted')}
          role="status"
          title={readError || `${dirty ? '有未保存的修改' : '与文件同步'} · ${doc.path || 'config.toml'}`}
        >
          <i className={'plugin-status-dot' + (dirty ? ' pending' : '')} />
          <span>{dirty ? '有未保存的修改' : readError ? '读取失败，保留当前配置' : '与文件同步'}</span>
        </span>
        {mode === 'form' && !compact && (
          <input
            className="input cfg-search"
            aria-label="搜索配置项"
            placeholder="搜索配置项（支持路径与说明）…"
            value={filter}
            disabled={!!busy}
            onChange={(event) => setFilter(event.target.value)}
          />
        )}
        {(mode === 'toml' || compact) && <div className="config-toolbar-spacer" />}
        {!compact && (
          <Button size="sm" disabled={!!busy} onClick={validate}>
            {busy === 'validate' ? '校验中…' : '校验'}
          </Button>
        )}
        <details
          className="config-more-actions config-action-disclosure"
          open={moreOpen}
          onToggle={(event) => {
            setMoreOpen(event.currentTarget.open);
          }}
        >
          <summary
            aria-label="更多操作"
            title={`${dirty ? '有未保存的修改' : '与文件同步'} · ${doc.path || 'config.toml'}`}
          >
            <Icon name="more" />
            更多操作
          </summary>
          <div className="config-disclosure-content" role="group" aria-label="配置编辑操作">
            {compact && mode === 'form' && (
              <input
                className="input"
                aria-label="搜索配置项"
                placeholder="搜索路径或说明…"
                value={filter}
                disabled={!!busy}
                onChange={(event) => setFilter(event.target.value)}
              />
            )}
            {compact && (
              <Button size="sm" disabled={!!busy} onClick={validate}>
                {busy === 'validate' ? '校验中…' : '校验配置'}
              </Button>
            )}
            <Button
              className="config-history-action"
              disabled={readOnly || !!busy || mode === 'toml' || !undoStack.length}
              aria-label={'撤销' + (undoStack.length ? ' ' + undoStack.length : '')}
              title="撤销 (Ctrl+Z)"
              onClick={undo}
            >
              <Icon name="undo" />
              <span className="config-mobile-action-label">撤销</span>
              {undoStack.length > 0 && <span aria-hidden="true">{undoStack.length}</span>}
            </Button>
            <Button
              className="config-history-action"
              disabled={readOnly || !!busy || mode === 'toml' || !redoStack.length}
              aria-label="重做"
              title="重做 (Ctrl+Y)"
              onClick={redo}
            >
              <Icon name="refresh" />
              <span className="config-mobile-action-label">重做</span>
            </Button>
            <Button
              className="config-secondary-action"
              size="sm"
              disabled={readOnly || !!busy || mode === 'toml' || !doc}
              title="所有配置项恢复默认值"
              onClick={resetAllDefaults}
            >
              全部恢复默认
            </Button>
            <Button
              className="config-secondary-action"
              size="sm"
              disabled={!!busy || !dirty}
              onClick={discard}
            >
              放弃修改
            </Button>
            {(readError || readRecovery) && (
              <Button className="config-secondary-action" size="sm" disabled={!!busy} onClick={reread}>
                {busy === 'read' ? '读取中…' : '重新读取'}
              </Button>
            )}
            {compact && (
              <>
                <div className="config-menu-divider" />
                {runtimeActions}
              </>
            )}
          </div>
        </details>
        {!compact && (
          <div className="config-runtime-inline" role="group" aria-label="运行操作">
            {runtimeActions}
          </div>
        )}
        <Button
          className="config-save-button"
          size="sm"
          variant="primary"
          disabled={readOnly || !!busy || !dirty}
          onClick={() => save(true)}
          title="保存前自动校验语法与类型，并备份旧文件。"
        >
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
        </Button>
      </div>

      <div
        className={'config-body' + (mode === 'toml' ? ' config-source-body' : '')}
        onInputCapture={protectFieldDraft}
        onChangeCapture={protectFieldDraft}
      >
        {mode === 'form' ? (
          <ConfigTreePanel
            schema={doc.schema || []}
            draft={draft}
            baseline={doc.config || {}}
            history={history}
            collapse={collapse}
            disabled={readOnly || !!busy}
            filter={filter}
            onFilterChange={setFilter}
            onToggleCollapse={(key) => setCollapse((previous) => ({ ...previous, [key]: !previous[key] }))}
            onRestore={restoreValue}
            onChange={changeField}
          />
        ) : (
          <TomlEditor
            ariaLabel="config.toml"
            fileName="config.toml"
            filePath={doc.path}
            disabled={!!busy}
            readOnly={readOnly}
            value={source}
            onChange={(value) => {
              if (!readOnly && !busy) setSource(value);
            }}
            onSave={() => {
              if (!readOnly && !busy && dirty) void save(true);
            }}
            saveDisabled={readOnly || !!busy || !dirty}
          />
        )}
      </div>
    </section>
  );
}

export { BotConfigPanel };
