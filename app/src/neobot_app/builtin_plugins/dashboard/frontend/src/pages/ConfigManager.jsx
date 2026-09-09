// ConfigManager.jsx —— 本体配置 / 环境变量 / 模型注册 在线管理
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/endpoints.js';
import { toast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';
import Modal from '../components/Modal.jsx';
import SchemaForm, { defaultsFromFields } from '../components/SchemaForm.jsx';
import { getPath, setPath } from '../utils/paths.js';

const TABS = [
  ['config', '本体配置'],
  ['env', '环境变量'],
  ['models', '模型库'],
  ['assign', '模型分配'],
];

function collectLeaves(value, path = [], out = []) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of Object.keys(value)) collectLeaves(value[key], [...path, key], out);
  } else {
    out.push({ path, value });
  }
  return out;
}

/** 比较一次分组修改，找出真正变化的叶子配置项（用于逐项历史）。 */
function changedLeaves(before, after, basePath) {
  const beforeMap = new Map(collectLeaves(before).map((item) => [item.path.join('.'), item.value]));
  const changes = [];
  for (const item of collectLeaves(after)) {
    const key = item.path.join('.');
    if (JSON.stringify(beforeMap.get(key) ?? null) === JSON.stringify(item.value ?? null)) continue;
    changes.push({ path: [...basePath, ...item.path], before: beforeMap.get(key), after: item.value });
  }
  return changes;
}

export default function ConfigManager() {
  const [tab, setTab] = useState('config');
  return (
    <div className="page config-page">
      <div className="config-tabs cfg-top-tabs">
        <div role="tablist" aria-label="配置管理">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              className={tab === key ? 'active' : ''}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="muted small">config.toml / .env / 模型库与分配</span>
      </div>
      {tab === 'config' && <BotConfigPanel />}
      {tab === 'env' && <EnvPanel />}
      {tab === 'models' && <ModelsPanel />}
      {tab === 'assign' && <AssignPanel />}
    </div>
  );
}

function BotConfigPanel() {
  const [doc, setDoc] = useState(null);
  const [draft, setDraft] = useState({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState('form');
  const [filter, setFilter] = useState('');
  const [errors, setErrors] = useState([]);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [undoStack, setUndoStack] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [history, setHistory] = useState({});
  const [collapse, setCollapse] = useState({});
  const [changes, setChanges] = useState(null);
  const draftRef = useRef({});
  draftRef.current = draft;

  const applyDoc = useCallback((data) => {
    setDoc(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setErrors([]);
    setNotice(null);
    setUndoStack([]);
    setRedoStack([]);
    setHistory({});
  }, []);

  const pushHistory = useCallback((path, value) => {
    const key = path.join('.') || '(root)';
    setHistory((previous) => ({
      ...previous,
      [key]: [{ value, at: new Date().toLocaleTimeString() }, ...(previous[key] || [])].slice(0, 20),
    }));
  }, []);

  const recordChange = useCallback((path, before, after) => {
    setUndoStack((stack) => [...stack, { path, before, after }].slice(-200));
    setRedoStack([]);
  }, []);

  const applyValue = useCallback((path, value) => {
    setDraft((previous) => setPath(previous, path, value));
  }, []);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.config();
    setLoading(false);
    if (!result.ok) {
      setNotice({ text: result.error || '读取配置失败', warning: true });
      return;
    }
    applyDoc(result.data);
  }, [applyDoc]);

  useEffect(() => {
    read();
  }, [read]);

  const dirty = useMemo(() => {
    if (!doc) return false;
    return mode === 'toml'
      ? source !== doc.source
      : JSON.stringify(draft) !== JSON.stringify(doc.config);
  }, [doc, draft, source, mode]);

  const changeField = useCallback((path, value) => {
    const before = getPath(draftRef.current, path);
    if (JSON.stringify(before ?? null) === JSON.stringify(value ?? null)) return;
    recordChange(path, before, value);
    // 分组修改时按叶子路径记录历史，便于逐项查看/恢复
    for (const leaf of changedLeaves(before, value, path)) {
      pushHistory(leaf.path, leaf.before);
    }
    applyValue(path, value);
  }, [applyValue, pushHistory, recordChange]);

  const restoreValue = useCallback((path, value) => {
    const before = getPath(draftRef.current, path);
    recordChange(path, before, value);
    pushHistory(path, before);
    applyValue(path, value);
  }, [applyValue, pushHistory, recordChange]);

  const undo = useCallback(() => {
    setUndoStack((stack) => {
      if (!stack.length) return stack;
      const entry = stack.at(-1);
      applyValue(entry.path, entry.before);
      setRedoStack((redo) => [...redo, entry]);
      return stack.slice(0, -1);
    });
  }, [applyValue]);

  const redo = useCallback(() => {
    setRedoStack((stack) => {
      if (!stack.length) return stack;
      const entry = stack.at(-1);
      applyValue(entry.path, entry.after);
      setUndoStack((undoList) => [...undoList, entry]);
      return stack.slice(0, -1);
    });
  }, [applyValue]);

  const resetAllDefaults = useCallback(() => {
    if (!doc) return;
    if (!confirm('把所有配置项恢复为默认值？可撤销。')) return;
    const next = structuredClone(draftRef.current || {});
    const walk = (fields, node) => {
      for (const field of fields || []) {
        if (field.kind === 'group') {
          if (!node[field.name] || typeof node[field.name] !== 'object') node[field.name] = {};
          walk(field.fields, node[field.name]);
        } else if (field.default !== undefined) {
          node[field.name] = structuredClone(field.default);
        }
      }
    };
    walk(doc.schema || [], next);
    recordChange([], structuredClone(draftRef.current), structuredClone(next));
    setDraft(next);
  }, [doc, recordChange]);

  useEffect(() => {
    function onKey(event) {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === 'z' && !event.shiftKey) { event.preventDefault(); undo(); }
      else if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); redo(); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [undo, redo]);

  const validate = async () => {
    setBusy('validate');
    const body = mode === 'toml' ? { source } : { config: draft };
    const result = await api.configValidate(body);
    setBusy('');
    if (result.ok) {
      setErrors([]);
      toast('配置校验通过', 'ok');
    } else {
      setErrors(result.data?.errors || []);
      toast(result.error || '配置校验未通过', 'err');
    }
  };

  const save = async (reload) => {
    if (!doc) return;
    setBusy('save');
    const body = {
      revision: doc.revision,
      mode,
      reload,
      ...(mode === 'toml' ? { source } : { config: draft }),
    };
    const result = await api.configSave(body);
    setBusy('');
    if (!result.ok) {
      if (result.status === 409) {
        setNotice({ text: result.error, warning: true });
        toast('配置已被其它会话修改，请重新读取', 'err');
      } else {
        setErrors(result.data?.errors || []);
        toast(result.error || '保存失败', 'err');
      }
      return;
    }
    applyDoc(result.data);
    setChanges(result.data.changes || null);
    setNotice({ text: result.data.message || '配置已保存', warning: !result.data.applied && reload });
    toast(result.data.message || '配置已保存', 'ok');
  };

  const reloadRuntime = async () => {
    setBusy('reload');
    const result = await api.configReload();
    setBusy('');
    if (result.ok) {
      setChanges(result.data?.changes || null);
      toast(result.data?.message || '配置已重载', 'ok');
    } else {
      toast(result.error || '重载失败', 'err');
    }
  };

  const restart = async () => {
    if (!confirm('确认重启 NeoBot？面板会短暂不可用。')) return;
    setBusy('restart');
    const result = await api.restart();
    setBusy('');
    toast(result.ok ? result.data?.message || '已请求重启' : result.error || '重启失败', result.ok ? 'ok' : 'err');
  };

  if (loading && !doc) {
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
              onClick={() => setMode('form')}
            >
              <Icon name="settings" /> 表单
            </button>
            <button
              role="tab"
              aria-selected={mode === 'toml'}
              className={mode === 'toml' ? 'active' : ''}
              disabled={!!busy}
              onClick={() => setMode('toml')}
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
            onChange={(event) => setFilter(event.target.value)}
          />
        )}
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={validate}>校验</button>
        <button className="btn" disabled={!!busy || !undoStack.length} title="撤销 (Ctrl+Z)" onClick={undo}>
          <Icon name="undo" /> 撤销{undoStack.length ? ' ' + undoStack.length : ''}
        </button>
        <button className="btn" disabled={!!busy || !redoStack.length} title="重做 (Ctrl+Y)" onClick={redo}>
          <Icon name="refresh" /> 重做
        </button>
        <button className="btn" disabled={!!busy || !doc} title="所有配置项恢复默认值" onClick={resetAllDefaults}>
          全部恢复默认
        </button>
        <button className="btn" disabled={!!busy || !dirty} onClick={() => { applyDoc(doc); setChanges(null); }}>放弃修改</button>
        <button className="btn" disabled={!!busy} onClick={read}>重新读取</button>
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
      {changes && (changes.hot_reload_count > 0 || changes.needs_restart_count > 0) && (
        <div className="cfg-changes" role="status">
          <strong>
            热重载结果：{changes.hot_reload_count} 项已生效，{changes.needs_restart_count} 项需重启
          </strong>
          {changes.hot_reload?.length > 0 && (
            <details open>
              <summary>已生效（{changes.hot_reload.length}）</summary>
              <ul className="cfg-errors">
                {changes.hot_reload.slice(0, 12).map((item) => (
                  <li key={item.path}><code>{item.path}</code> {item.before} → {item.after}</li>
                ))}
              </ul>
            </details>
          )}
          {changes.needs_restart?.length > 0 && (
            <details>
              <summary>需重启 NeoBot 后生效（{changes.needs_restart.length}）</summary>
              <ul className="cfg-errors">
                {changes.needs_restart.slice(0, 12).map((item) => (
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
            fields={doc.schema || []}
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
          <Icon name="refresh" /> 重载运行时配置
        </button>
        <button className="btn danger" disabled={!!busy} onClick={restart}>重启 NeoBot</button>
      </div>
    </section>
  );
}

function EnvPanel() {
  const [doc, setDoc] = useState(null);
  const [edits, setEdits] = useState({});
  const [deletes, setDeletes] = useState([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(null);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.env();
    setLoading(false);
    if (!result.ok) {
      setNotice({ text: result.error || '读取 .env 失败', warning: true });
      return;
    }
    setDoc(result.data);
    setEdits({});
    setDeletes([]);
    setNotice(null);
  }, []);

  useEffect(() => {
    read();
  }, [read]);

  const items = doc?.items || [];
  const visible = items.filter((item) => !filter || item.key.toLowerCase().includes(filter.toLowerCase()));
  const dirty = Object.keys(edits).length > 0 || deletes.length > 0;

  const [adding, setAdding] = useState(false);
  const [platform, setPlatform] = useState({ name: '', url: '', api_key: '' });

  const openPlatform = (item) => {
    setPlatform({ name: item?.name || '', url: item?.url || '', api_key: '' });
    setAdding(true);
  };

  const submitPlatform = async () => {
    setBusy('platform');
    const result = await api.envAddPlatform({ ...platform, revision: doc?.revision });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '添加供应商失败', 'err');
      return;
    }
    setDoc(result.data);
    setAdding(false);
    setPlatform({ name: '', url: '', api_key: '' });
    setNotice({ text: result.data.message || '供应商已添加', warning: false });
    toast('供应商已添加', 'ok');
  };

  const save = async (reload) => {
    setBusy('save');
    const result = await api.envSave({ updates: edits, deletes, revision: doc?.revision, reload });
    setBusy('');
    if (!result.ok) {
      if (result.status === 409) setNotice({ text: result.error, warning: true });
      toast(result.error || '保存失败', 'err');
      return;
    }
    setDoc(result.data);
    setEdits({});
    setDeletes([]);
    setNotice({ text: result.data.message || '已保存', warning: false });
    toast(result.data.message || '已保存', 'ok');
  };

  const addCustom = () => {
    const key = newKey.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      toast('环境变量名只能是字母、数字与下划线，且不能以数字开头', 'err');
      return;
    }
    setEdits((previous) => ({ ...previous, [key]: newValue }));
    setNewKey('');
    setNewValue('');
    toast('已加入待保存列表', 'info');
  };

  if (loading && !doc) {
    return <section className="card"><p className="empty muted" role="status">正在读取 .env…</p></section>;
  }

  return (
    <section className="card config-card">
      <div className="config-toolbar">
        <input
          className="input cfg-search"
          placeholder="搜索环境变量…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={() => openPlatform(null)}>
          <Icon name="plus" /> 一键添加 API 供应商
        </button>
        <button className="btn" disabled={!!busy} onClick={read}>重新读取</button>
        <button className="btn primary" disabled={!!busy || !dirty} onClick={() => save(true)}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
        </button>
      </div>

      {notice && (
        <div className={'config-notice' + (notice.warning ? ' warning' : '')} role="status">
          <Icon name="check" /> {notice.text}
        </div>
      )}

      <p className="muted small">
        平台密钥形如 <code>平台名_URL</code> / <code>平台名_APIKey</code>；自定义平台可直接新增，例如
        <code>MyProvider_URL</code> 与 <code>MyProvider_APIKey</code>。
      </p>

      <div className="env-table">
        <div className="env-row env-head">
          <span>变量</span><span>值</span><span>说明</span><span>操作</span>
        </div>
        {visible.map((item) => {
          const edited = Object.prototype.hasOwnProperty.call(edits, item.key);
          const removed = deletes.includes(item.key);
          const value = edited ? edits[item.key] : item.value;
          return (
            <div className={'env-row' + (removed ? ' removed' : '')} key={item.key}>
              <span className="env-key">
                <code>{item.key}</code>
                {item.builtin && <span className="meta-chip">内置</span>}
                {item.required && <span className="meta-chip update-available">必须</span>}
              </span>
              <span className="env-value">
                <input
                  className="input"
                  type={item.sensitive ? 'password' : 'text'}
                  value={removed ? '' : value || ''}
                  disabled={removed || !!busy}
                  autoComplete="new-password"
                  spellCheck={false}
                  placeholder={item.sensitive
                    ? (item.has_value ? '已设置 · 留空则不修改' : '未设置')
                    : (item.has_value ? '' : '未配置')}
                  onChange={(event) => setEdits((previous) => ({ ...previous, [item.key]: event.target.value }))}
                />
              </span>
              <span className="muted small env-desc">{item.description || '—'}</span>
              <span className="env-actions">
                {item.sensitive && (
                  <span className={'tag ' + (item.has_value ? 'ok' : 'err')}>
                    {item.has_value ? '已设置' : '未设置'}
                  </span>
                )}
                {item.builtin ? (
                  <span className="muted small">内置</span>
                ) : (
                  <button
                    className="btn-sm danger"
                    disabled={!!busy || removed}
                    onClick={() => {
                      if (!confirm('确认删除 ' + item.key + '？保存后生效。')) return;
                      setDeletes((previous) => [...previous, item.key]);
                    }}
                  >
                    删除
                  </button>
                )}
              </span>
            </div>
          );
        })}
        {visible.length === 0 && <div className="empty muted">没有匹配的环境变量</div>}
      </div>

      <div className="env-add">
        <input
          className="input"
          placeholder="新增变量名，如 MyProvider_URL"
          value={newKey}
          onChange={(event) => setNewKey(event.target.value)}
        />
        <input
          className="input"
          placeholder="值"
          value={newValue}
          onChange={(event) => setNewValue(event.target.value)}
        />
        <button className="btn" onClick={addCustom}><Icon name="plus" /> 添加</button>
      </div>

      <div className="card-head">
        <h3>API 供应商</h3>
        <span className="muted small">{(doc?.platforms || []).length} 个</span>
        <div className="spacer" />
        <span className="muted small">API Key 只写不读，保存后无法再次查看</span>
      </div>
      {(doc?.platforms || []).length === 0 && (
        <div className="empty muted">还没有平台，点击「一键添加 API 供应商」创建</div>
      )}
      {(doc?.platforms || []).length > 0 && (
        <table className="model-table">
          <thead><tr><th>平台名</th><th>API 地址</th><th>API Key</th><th>操作</th></tr></thead>
          <tbody>
            {(doc.platforms || []).map((item) => (
              <tr key={item.name}>
                <td>
                  <code>{item.name}</code>
                  {item.builtin && <span className="meta-chip">内置</span>}
                </td>
                <td className="muted small">{item.url || '—'}</td>
                <td>
                  <span className={'tag ' + (item.has_key ? 'ok' : 'err')}>
                    {item.has_key ? '已设置' : '未设置'}
                  </span>
                </td>
                <td>
                  <button className="btn-sm" disabled={!!busy} onClick={() => openPlatform(item)}>
                    更新 Key
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Modal open={adding} title="添加 / 更新 API 供应商" onClose={() => setAdding(false)}>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-name">平台名</label>
            <p>模型库里的「供应商」填这个名字，会写成 <code>平台名_URL</code> 与 <code>平台名_APIKey</code></p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-name"
              className="input"
              autoFocus
              spellCheck={false}
              disabled={!!busy}
              value={platform.name}
              placeholder="例如 MyProvider"
              onChange={(event) => setPlatform({ ...platform, name: event.target.value })}
            />
          </div>
        </div>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-url">API 地址</label>
            <p>以 http:// 或 https:// 开头，例如 https://api.example.com/v1</p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-url"
              className="input"
              spellCheck={false}
              disabled={!!busy}
              value={platform.url}
              placeholder="https://api.example.com/v1"
              onChange={(event) => setPlatform({ ...platform, url: event.target.value })}
            />
          </div>
        </div>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-key">API Key</label>
            <p>只写不读：保存后无法查看，只能覆盖更新；留空则保持原有 Key</p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-key"
              className="input"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              disabled={!!busy}
              value={platform.api_key}
              placeholder="sk-..."
              onChange={(event) => setPlatform({ ...platform, api_key: event.target.value })}
            />
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn" disabled={!!busy} onClick={() => setAdding(false)}>取消</button>
          <button className="btn primary" disabled={!!busy} onClick={submitPlatform}>
            <Icon name="save" /> {busy === 'platform' ? '保存中…' : '保存供应商'}
          </button>
        </div>
      </Modal>
    </section>
  );
}

function ModelsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState(null);

  const applyData = useCallback((payload) => {
    setData(payload);
  }, []);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.configModels();
    setLoading(false);
    if (!result.ok) {
      toast(result.error || '读取模型库失败', 'err');
      return;
    }
    applyData(result.data);
  }, [applyData]);

  useEffect(() => {
    read();
  }, [read]);

  const library = data?.library || [];
  const schema = data?.entry_schema || [];

  const startNew = () => setEditing({ isNew: true, draft: defaultsFromFields(schema) });

  const startEdit = (item) => setEditing({ isNew: false, draft: structuredClone(item.entry || {}) });

  const save = async () => {
    if (!editing) return;
    setBusy('save');
    const result = await api.modelsLibrarySave({
      action: 'upsert',
      entry: editing.draft,
      revision: data?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存模型失败', 'err');
      return;
    }
    if (result.data?.models) applyData(result.data.models);
    setEditing(null);
    toast('模型已保存；重载配置后生效', 'ok');
  };

  const remove = async (item) => {
    if (!confirm('确认从模型库删除 ' + item.key + '？')) return;
    setBusy('delete');
    const result = await api.modelsLibrarySave({
      action: 'delete',
      key: item.key,
      revision: data?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '删除失败', 'err');
      return;
    }
    if (result.data?.models) applyData(result.data.models);
    toast('已删除 ' + item.key, 'ok');
  };

  const fields = useMemo(() => {
    if (!editing) return [];
    const bound = bindValues(schema, editing.draft);
    if (editing.isNew) return bound;
    return bound.map((field) => (field.name === 'key' ? { ...field, readonly: true } : field));
  }, [editing, schema]);

  return (
    <section className="card config-card">
      <div className="card-head">
        <h3>模型库</h3>
        <span className="muted small">{library.length} 个模型</span>
        <div className="spacer" />
        <button className="btn-sm" disabled={!!busy} onClick={read}>刷新</button>
        <button className="btn-sm primary" disabled={!!busy || !schema.length} onClick={startNew}>
          <Icon name="plus" /> 新增模型
        </button>
      </div>
      <p className="muted small">
        模型单独存储在 <code>[models.registry]</code>，主对话 / Agent / 视觉 / TTS / 生图只引用 key；
        同一个模型可被多个调用方复用，改一处全局生效。
      </p>
      {loading && !data && <p className="empty muted" role="status">正在读取模型库…</p>}
      {data && library.length === 0 && <div className="empty muted">模型库为空，点击「新增模型」添加</div>}
      {library.length > 0 && (
        <table className="model-table">
          <thead>
            <tr><th>key</th><th>描述</th><th>供应商 / 模型</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {library.map((item) => (
              <tr key={item.key}>
                <td><code>{item.key}</code></td>
                <td>{item.description || '—'}</td>
                <td>
                  <div>{item.provider}</div>
                  <div className="muted small">{item.model_name}</div>
                </td>
                <td>
                  <span className={'tag ' + (item.key_configured ? 'ok' : 'err')}>
                    {item.key_configured ? 'Key 已配置' : '缺 APIKey'}
                  </span>
                  {!item.url_configured && <span className="tag err">缺 URL</span>}
                  {item.registered && <span className="tag ok">已注册</span>}
                  {item.assigned && <span className="tag info">已引用</span>}
                  {item.native_vision && <span className="tag info">原生视觉</span>}
                </td>
                <td>
                  <button className="btn-sm" disabled={!!busy} onClick={() => startEdit(item)}>编辑</button>
                  <button className="btn-sm danger" disabled={!!busy} onClick={() => remove(item)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Modal
        open={!!editing}
        title={editing?.isNew ? '新增模型' : '编辑模型 ' + (editing?.draft?.key || '')}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <>
            <SchemaForm
              fields={fields}
              disabled={!!busy}
              onChange={(path, value) => setEditing((previous) => ({ ...previous, draft: setPath(previous.draft, path, value) }))}
            />
            <div className="modal-actions">
              <button className="btn" disabled={!!busy} onClick={() => setEditing(null)}>取消</button>
              <button className="btn primary" disabled={!!busy} onClick={save}>
                <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存模型'}
              </button>
            </div>
          </>
        )}
      </Modal>
    </section>
  );
}

function AssignPanel() {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const applyData = useCallback((payload) => {
    setData(payload);
    const roles = payload?.assignments?.roles || {};
    setDraft({
      ...roles,
      creator_image_models: [...(payload?.assignments?.creator_image_models || [])],
    });
  }, []);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.configModels();
    setLoading(false);
    if (!result.ok) {
      toast(result.error || '读取模型分配失败', 'err');
      return;
    }
    applyData(result.data);
  }, [applyData]);

  useEffect(() => {
    read();
  }, [read]);

  const library = data?.library || [];
  const roles = data?.roles_meta || [];

  const labelOf = (key) => {
    const item = library.find((entry) => entry.key === key);
    if (!item) return key + '（模型库中不存在）';
    return item.key + ' · ' + (item.description || item.model_name || item.provider);
  };

  const save = async () => {
    setBusy('save');
    const result = await api.modelsAssignmentsSave({
      assignments: draft,
      revision: data?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    if (result.data?.models) applyData(result.data.models);
    toast('模型分配已保存；重载配置后生效', 'ok');
  };

  if (loading && !data) {
    return <section className="card"><p className="empty muted" role="status">正在读取模型分配…</p></section>;
  }

  return (
    <section className="card config-card">
      <div className="card-head">
        <h3>模型分配</h3>
        <span className="muted small">{library.length} 个可选模型</span>
        <div className="spacer" />
        <button className="btn-sm" disabled={!!busy} onClick={read}>重新读取</button>
        <button className="btn-sm primary" disabled={!!busy} onClick={save}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存分配'}
        </button>
      </div>
      <p className="muted small">每个调用方只保存一个模型 key；生图模型可多选，Agent 会按模型描述自行选择供应商。</p>

      <div className="assign-grid">
        {roles.map((meta) => (
          <div className="assign-row" key={meta.role}>
            <div className="assign-label">
              <strong>{meta.label}</strong>
              <code className="muted small">{meta.role}</code>
              {meta.required && <span className="meta-chip update-available">必须</span>}
            </div>
            <div className="assign-control">
              {meta.multi ? (
                <div className="assign-choices">
                  {library.length === 0 && <span className="muted small">模型库为空</span>}
                  {library.map((item) => {
                    const checked = (draft.creator_image_models || []).includes(item.key);
                    return (
                      <label className="assign-choice" key={item.key}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!!busy}
                          onChange={() => setDraft((previous) => {
                            const current = previous.creator_image_models || [];
                            return {
                              ...previous,
                              creator_image_models: checked
                                ? current.filter((key) => key !== item.key)
                                : [...current, item.key],
                            };
                          })}
                        />
                        <span>{labelOf(item.key)}</span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <select
                  className="input"
                  disabled={!!busy}
                  value={draft[meta.role] || ''}
                  onChange={(event) => setDraft((previous) => ({ ...previous, [meta.role]: event.target.value }))}
                >
                  {!meta.required && <option value="">（不指定）</option>}
                  {meta.required && !draft[meta.role] && <option value="">（请选择）</option>}
                  {library.map((item) => (
                    <option key={item.key} value={item.key}>{labelOf(item.key)}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="card-head">
        <h3>当前生效情况</h3>
        <span className="muted small">重载配置后生效</span>
      </div>
      <table className="model-table">
        <thead><tr><th>调用方</th><th>模型 key</th><th>供应商 / 模型</th><th>状态</th></tr></thead>
        <tbody>
          {(data?.roles || []).map((item, index) => (
            <tr key={item.role + '-' + index}>
              <td>{item.label}</td>
              <td><code>{item.key || '—'}</code></td>
              <td className="muted small">{[item.provider, item.model_name].filter(Boolean).join(' / ') || '—'}</td>
              <td>
                {item.missing && <span className="tag err">模型库中不存在</span>}
                {!item.missing && item.registered && <span className="tag ok">已注册</span>}
                {!item.missing && !item.registered && <span className="tag info">未注册</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function bindValues(fields, values) {
  return (fields || []).map((field) => {
    const value = values ? values[field.name] : undefined;
    if (field.kind === 'group') {
      const nested = value && typeof value === 'object' ? value : {};
      return { ...field, value: nested, fields: bindValues(field.fields || [], nested) };
    }
    return { ...field, value: value === undefined ? field.value : value };
  });
}
