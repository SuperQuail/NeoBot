// Plugins.jsx —— 插件工作区：官方/第三方分组、启停、热重载、安装与在线配置
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { api } from '../api/endpoints.js';
import { toast } from '../components/Toast.jsx';
import Modal from '../components/Modal.jsx';
import Icon from '../components/Icon.jsx';
import SchemaForm from '../components/SchemaForm.jsx';
import '../styles/plugins.css';

const statusLabels = { loaded: '运行中', error: '异常', disabled: '已停用', unloaded: '未加载', stopped: '已停止' };
const statusGroups = [['loaded', '运行中'], ['disabled', '已停用'], ['error', '异常'], ['other', '其他']];
const pluginId = (plugin) => plugin.id || plugin.path || plugin.name;

const SOURCE_FILTERS = [
  ['all', '全部'],
  ['official', '官方'],
  ['third_party', '第三方'],
];

export default function Plugins() {
  const [items, setItems] = useState([]);
  const [permissions, setPermissions] = useState({ manage_enabled: false, hot_reload: false });
  const [consolePlugin, setConsolePlugin] = useState('');
  const [listError, setListError] = useState('');
  const [listLoading, setListLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [collapsed, setCollapsed] = useState({});
  const [selectedId, setSelectedId] = useState('');
  const [mobileDetail, setMobileDetail] = useState(false);
  const [configDocument, setConfigDocument] = useState(null);
  const [draft, setDraft] = useState({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState('form');
  const [errors, setErrors] = useState([]);
  const [configError, setConfigError] = useState('');
  const [loading, setLoading] = useState(false);
  const [operation, setOperation] = useState('');
  const [notice, setNotice] = useState(null);
  const [editorVersion, setEditorVersion] = useState(0);
  const [installOpen, setInstallOpen] = useState(false);
  const [installRepo, setInstallRepo] = useState('');
  const [installBranch, setInstallBranch] = useState('main');
  const searchRef = useRef(null);
  const actionsRef = useRef(null);
  const requestId = useRef(0);
  const listRequest = useRef(0);
  const dirtyRef = useRef(false);
  const busyRef = useRef(false);
  const selected = items.find((plugin) => pluginId(plugin) === selectedId);
  const dirty = !!configDocument && (mode === 'toml'
    ? source !== configDocument.source
    : JSON.stringify(draft) !== JSON.stringify(configDocument.config));
  dirtyRef.current = dirty;
  busyRef.current = !!operation;

  const load = useCallback(async () => {
    const ticket = ++listRequest.current;
    const data = await api.plugins();
    if (ticket !== listRequest.current) return;
    setListLoading(false);
    if (!data) { setListError('无法读取插件列表，请检查连接后重试'); return; }
    setListError('');
    setItems(data.items || []);
    setConsolePlugin(data.console_plugin || '');
    setPermissions({ manage_enabled: data.manage_enabled ?? false, hot_reload: data.hot_reload ?? false });
    setSelectedId((current) => {
      if ((data.items || []).some((plugin) => pluginId(plugin) === current)) return current;
      if (dirtyRef.current || busyRef.current) return current;
      const first = (data.items || []).find((plugin) => plugin.status === 'loaded') || (data.items || [])[0];
      return first ? pluginId(first) : '';
    });
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 20000);
    return () => { clearInterval(timer); listRequest.current++; };
  }, [load]);

  const applyDocument = useCallback((data, preferredMode) => {
    setConfigDocument(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setMode(data.form_supported && preferredMode !== 'toml' ? 'form' : 'toml');
    setErrors([]);
    setConfigError('');
    setEditorVersion((version) => version + 1);
  }, []);

  const read = useCallback(async (id) => {
    const ticket = ++requestId.current;
    setLoading(true);
    setConfigError('');
    setConfigDocument(null);
    setNotice(null);
    const result = await api.pluginConfig(id);
    if (ticket !== requestId.current) return;
    setLoading(false);
    if (!result.ok) { setConfigError(result.error || '无法读取配置'); return; }
    applyDocument(result.data);
  }, [applyDocument]);

  useEffect(() => {
    setConfigDocument(null);
    setNotice(null);
    setConfigError('');
    setErrors([]);
    const target = items.find((plugin) => pluginId(plugin) === selectedId);
    if (selectedId && permissions.manage_enabled && target && !target.official) read(selectedId);
    return () => { requestId.current++; };
  }, [selectedId, permissions.manage_enabled, read, items]);

  useEffect(() => {
    function beforeUnload(event) {
      if (dirtyRef.current || busyRef.current) { event.preventDefault(); event.returnValue = ''; }
    }
    function guardNavigation(event) {
      const link = event.target.closest('a[href]');
      if (!link || !link.getAttribute('href')?.startsWith('#/')) return;
      if (busyRef.current || (dirtyRef.current && !window.confirm('配置尚未保存，确认离开？'))) {
        event.preventDefault(); event.stopPropagation();
      }
    }
    function keyboard(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); searchRef.current?.focus();
      }
    }
    function closeActions(event) {
      if (actionsRef.current && !actionsRef.current.contains(event.target)) actionsRef.current.open = false;
    }
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', guardNavigation, true);
    document.addEventListener('pointerdown', closeActions);
    window.addEventListener('keydown', keyboard);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      document.removeEventListener('click', guardNavigation, true);
      document.removeEventListener('pointerdown', closeActions);
      window.removeEventListener('keydown', keyboard);
    };
  }, []);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: dirty || !!operation }));
    return () => window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: false }));
  }, [dirty, operation]);

  const visible = useMemo(() => items
    .filter((plugin) => (sourceFilter === 'all' ? true : plugin.source === sourceFilter))
    .filter((plugin) => `${plugin.name} ${plugin.description || ''} ${plugin.author || ''}`.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name)), [items, filter, sourceFilter]);

  function select(plugin) {
    const id = pluginId(plugin);
    if (operation || (id !== selectedId && dirty && !confirm('配置尚未保存，确认切换插件并放弃修改？'))) return;
    if (actionsRef.current) actionsRef.current.open = false;
    setSelectedId(id);
    setMobileDetail(true);
  }

  async function act(key, fn, success) {
    if (busyRef.current) return;
    if (actionsRef.current) actionsRef.current.open = false;
    busyRef.current = true;
    setOperation(key);
    try {
      const result = await fn();
      const message = result.data?.message || result.error || (result.ok ? success : '操作失败');
      toast(message, result.ok ? 'ok' : 'err');
      if (result.ok) {
        if (key === 'uninstall') setSelectedId('');
        await load();
      }
      return result;
    } finally {
      setOperation('');
      busyRef.current = false;
    }
  }

  async function save(reload) {
    const body = { revision: configDocument.revision, mode, reload,
      ...(mode === 'toml' ? { source } : { config: draft }) };
    const result = await act('save', () => api.pluginConfigSave(selectedId, body), '配置已保存');
    if (!result) return;
    if (result.ok) {
      applyDocument(result.data, mode);
      setNotice({ text: result.data.message, warning: reload && !result.data.applied });
    } else {
      setConfigError(result.error || '保存失败，请重试');
      setErrors(result.data?.errors || []);
    }
  }

  function changeMode(next) {
    if (mode === next || operation) return;
    if (dirty && !confirm('切换编辑模式会放弃尚未保存的修改，是否继续？')) return;
    setDraft(configDocument.config);
    setSource(configDocument.source);
    setErrors([]);
    setMode(next);
    setEditorVersion((version) => version + 1);
  }

  function changeField(path, value) {
    setDraft((previous) => {
      const next = structuredClone(previous);
      let target = next;
      for (const key of path.slice(0, -1)) target = target[key];
      Object.defineProperty(target, path.at(-1), { value, writable: true, enumerable: true, configurable: true });
      return next;
    });
  }

  const isConsole = selected?.name === consolePlugin;
  const canEdit = !!selected && !selected.official && permissions.manage_enabled && !!configDocument && !loading;
  const canSave = canEdit && dirty && !operation && !errors.length;
  const canReload = !!selected && !isConsole && permissions.manage_enabled && !operation && !dirty;
  const canManage = !!selected && permissions.manage_enabled && !operation && !dirty && selected.manageable;

  return <div className={`plugin-workspace ${mobileDetail ? 'show-detail' : ''}`}>
    <aside className="plugin-sidebar" aria-label="插件列表">
      <div className="plugin-sidebar-heading"><div><h1>插件管理 <span>{items.length}</span></h1></div>
        <button className="icon-btn" aria-label="安装插件" title="安装插件" disabled={!permissions.manage_enabled || !!operation}
          onClick={() => setInstallOpen(true)}><Icon name="plus" /></button></div>
      <div className="plugin-search"><Icon name="search" /><input ref={searchRef} aria-label="搜索插件" placeholder="搜索插件…"
        value={filter} onChange={(event) => setFilter(event.target.value)} /><kbd>Ctrl K</kbd></div>
      <div className="plugin-source-filter" role="group" aria-label="按来源筛选">
        {SOURCE_FILTERS.map(([key, label]) => (
          <button key={key} className={sourceFilter === key ? 'active' : ''} onClick={() => setSourceFilter(key)}>{label}</button>
        ))}
      </div>
      <div className="plugin-list">
        {listError && <div className="workspace-error" role="alert">{listError}<button className="btn-sm" onClick={load}>重试</button></div>}
        {listLoading && <p className="empty muted">正在读取插件…</p>}
        {!listLoading && !listError && visible.length === 0 && <p className="empty muted">{filter ? '没有匹配的插件' : '还没有安装插件'}</p>}
        {statusGroups.map(([status, label]) => {
          const plugins = visible.filter((plugin) => (status === 'other'
            ? !['loaded', 'disabled', 'error'].includes(plugin.status)
            : plugin.status === status));
          return plugins.length > 0 && <section className="plugin-group" key={status}>
            <h2><button className="plugin-group-toggle" aria-expanded={!!filter || !collapsed[status]}
              aria-controls={`plugin-group-${status}`} onClick={() => setCollapsed((current) => ({ ...current, [status]: !current[status] }))}>
              <Icon name="chevron" />{label}<span>{plugins.length}</span></button></h2>
            <div id={`plugin-group-${status}`} hidden={!filter && collapsed[status]}>
            {plugins.map((plugin) => <button key={pluginId(plugin)} className={`plugin-list-item ${selectedId === pluginId(plugin) ? 'selected' : ''}`}
              disabled={!!operation} onClick={() => select(plugin)} aria-current={selectedId === pluginId(plugin) ? 'true' : undefined}>
              <span className="plugin-item-icon"><Icon name="package" /></span>
              <span className="plugin-item-copy">
                <span>{plugin.name}</span>
                <small>
                  <span className={'source-badge' + (plugin.official ? ' official' : '')}>{plugin.official ? '官方' : '第三方'}</span>
                  {plugin.version || '未声明版本'}
                </small>
              </span>
              <span className={`plugin-status-dot ${plugin.status}`} role="img" aria-label={statusLabels[plugin.status] || plugin.status} />
            </button>)}</div>
          </section>;
        })}
      </div>
      <div className="plugin-sidebar-footer">
        <span><i className="plugin-status-dot loaded" />{items.filter((plugin) => plugin.status === 'loaded').length} 个运行中</span>
        <button className="icon-btn" aria-label="刷新插件列表" title="刷新插件列表" disabled={!!operation} onClick={load}><Icon name="refresh" /></button></div>
    </aside>
    <section className="plugin-editor" aria-label="在线配置">
      <header className="plugin-editor-toolbar">
        <button className="icon-btn plugin-back" aria-label="返回插件列表" onClick={() => setMobileDetail(false)}><Icon name="back" /></button>
        <div className="plugin-breadcrumb"><Icon name="package" /><span>插件</span><Icon name="chevron" /><strong>{selected?.name || '选择插件'}</strong>
          {dirty && <span className="unsaved-dot" title="有未保存的修改" />}</div>
        <div className="plugin-toolbar-actions" role="group" aria-label="插件操作">
          <button className="icon-btn" disabled={!selected || !permissions.manage_enabled || !!operation}
            aria-label={selected?.enabled ? '停用插件' : '启用插件'}
            title={dirty ? '请先保存或放弃修改' : selected?.enabled ? '停用插件' : '启用插件'}
            onClick={async () => { const result = await act('toggle', () => api.pluginToggle(selectedId), '状态已更新'); if (result?.ok) read(selectedId); }}>
            <Icon name={selected?.enabled ? 'pause' : 'play'} /></button>
          <button className="icon-btn" aria-label="重载插件" title={isConsole ? '面板自身不能热重载' : dirty ? '请先保存或放弃修改' : '重载插件'} disabled={!canReload}
            onClick={() => act('reload', () => api.pluginReload(selectedId), '插件已重载')}><Icon name="refresh" /></button>
          <span className="toolbar-divider" />
          <button className="btn primary" disabled={!canSave} onClick={() => save(true)}><Icon name="save" />
            {operation === 'save' ? '保存中…' : '保存并重载'}</button>
          <details className="plugin-more" ref={actionsRef} onKeyDown={(event) => {
            if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary').focus(); }
          }}>
            <summary className="icon-btn" aria-label="更多操作" title="更多操作"><Icon name="more" /></summary>
            <div className="plugin-action-menu" role="group" aria-label="更多插件操作">
              <button disabled={!!operation || !items.length}
                onClick={() => act('check', () => api.pluginsCheckUpdates(), '更新检查完成')}><Icon name="search" />检查全部更新</button>
              {selected?.manageable && selected?.repo && <button disabled={!canManage}
                onClick={() => { if (confirm(`更新 ${selected.name}？这会重载插件，当前运行中的任务可能中断。`)) act('update', () => api.pluginUpdate(selectedId), '更新完成').then((result) => { if (result?.ok) read(selectedId); }); }}><Icon name="download" />更新此插件</button>}
              {canEdit && <button disabled={!canSave} onClick={() => save(false)}><Icon name="save" />仅保存配置</button>}
              <button disabled={!dirty || !!operation} onClick={() => {
                if (confirm('放弃所有未保存的修改？')) { applyDocument(configDocument, mode); actionsRef.current.open = false; }
              }}><Icon name="undo" />放弃修改</button>
              <hr />
              <button className="danger" disabled={!canManage}
                onClick={() => { if (confirm(`确认卸载 ${selected.name}？插件代码会被移入备份目录，独立的数据目录会保留。`)) act('uninstall', () => api.pluginUninstall(selectedId), '已卸载'); }}><Icon name="trash" />卸载插件</button>
            </div>
          </details>
        </div>
      </header>
      {!selected ? <div className="workspace-empty"><Icon name="package" /><h2>{selectedId ? '插件已不在列表中' : '选择一个插件'}</h2>
        <p>{selectedId && dirty ? '尚未保存的内容已保留。请先恢复插件，再保存配置。' : '在左侧管理插件，在这里调整配置。'}</p></div> : <>
        <div className="plugin-editor-scroll">
          <div className="plugin-intro">
            <div className="plugin-title-row"><div className="plugin-large-icon"><Icon name="package" /></div>
              <div><div className="plugin-title"><h2>{selected.name}</h2><span className={`plugin-state ${selected.status}`}>
                <i className={`plugin-status-dot ${selected.status}`} />{statusLabels[selected.status] || selected.status}</span></div>
                <p>{selected.description || '在这里管理插件并编辑运行配置。'}</p></div></div>
            <div className="plugin-meta">
              <span className={'source-badge' + (selected.official ? ' official' : '')}>{selected.official ? '官方插件' : '第三方插件'}</span>
              <span className="meta-chip">v{selected.version || '—'}</span>
              {selected.author && <span className="meta-chip">{selected.author}</span>}
              {selected.repo && /^https?:\/\//i.test(selected.repo) && <a className="meta-chip" href={selected.repo} target="_blank" rel="noopener noreferrer">插件仓库 <Icon name="external" /></a>}
              {selected.homepage && !selected.repo && /^https?:\/\//i.test(selected.homepage) && <a className="meta-chip" href={selected.homepage} target="_blank" rel="noopener noreferrer">主页 <Icon name="external" /></a>}
              {(selected.tags || []).map((tag) => <span className="meta-chip" key={tag}>{tag}</span>)}
            </div>
          </div>
          {!permissions.manage_enabled ? <div className="workspace-empty"><Icon name="settings" /><h3>当前为只读模式</h3>
            <p>请在「配置管理 → 本体配置 → dashboard」中开启 manage_plugins。</p></div> : <>
            {selected.official ? (
              <div className="workspace-empty">
                <Icon name="settings" />
                <h3>官方插件配置来自 config.toml</h3>
                <p>请到「配置管理 → 本体配置」中修改 <code>{selected.name}</code> 分区，保存后重载即可生效。</p>
                <a className="btn primary" href="#/config"><Icon name="settings" />前往配置管理</a>
              </div>
            ) : (
              <>
                <div className="config-tabs"><div role="tablist" aria-label="配置编辑方式">
                  <button role="tab" aria-selected={mode === 'form'} className={mode === 'form' ? 'active' : ''}
                    disabled={!configDocument?.form_supported || !!operation} onClick={() => changeMode('form')}><Icon name="settings" />配置表单</button>
                  <button role="tab" aria-selected={mode === 'toml'} className={mode === 'toml' ? 'active' : ''}
                    disabled={!configDocument || !!operation} onClick={() => changeMode('toml')}><Icon name="code" />TOML</button>
                </div><span className="muted small">plugin.toml / config</span></div>
                {notice && <div className={`config-notice ${notice.warning ? 'warning' : ''}`} role="status"><Icon name="check" />{notice.text}</div>}
                {selected.error && <div className="workspace-error" role="alert">运行错误：{selected.error}</div>}
                {configError && <div className="workspace-error" role="alert">{configError}
                  <button className="btn-sm" disabled={!!operation} onClick={() => { if (!dirty || confirm('重新读取会放弃当前修改，是否继续？')) read(selectedId); }}>重新读取</button></div>}
                {errors.length > 0 && <div className="workspace-error" role="alert">
                  <ul className="cfg-errors">{errors.map((item, index) => <li key={index}><code>{item.path || '?'}</code> {item.message}</li>)}</ul>
                </div>}
                {loading ? <p className="empty muted" role="status">正在读取配置…</p> : configDocument && <div className="config-body" role="tabpanel">
                  {mode === 'form' ? <SchemaForm key={`${selectedId}-${editorVersion}`} fields={configDocument.schema || []} values={draft}
                    disabled={!!operation} onChange={changeField} /> : <>
                    <p className="muted small">编辑 [config] 及其子表。插件名称、版本等信息保持不变。</p>
                    <textarea className="toml-editor" aria-label="TOML 配置" spellCheck={false} disabled={!!operation}
                      value={source} onChange={(event) => setSource(event.target.value)} />
                  </>}
                </div>}
              </>
            )}
          </>}
        </div>
        <footer className="plugin-editor-footer" role="status"><span className={dirty ? 'dirty-label' : 'muted'}>
          <i className={`plugin-status-dot ${dirty ? 'pending' : ''}`} />{dirty ? '有未保存的修改' : configDocument ? '配置与文件同步' : '等待配置'}</span>
          <span className="muted">{operation ? '正在处理…' : selected.official ? '官方插件随本体更新' : '支持保存后热重载'}</span></footer>
      </>}
    </section>
    <Modal open={installOpen} title="安装第三方插件" onClose={() => { if (!operation) setInstallOpen(false); }}>
      <form className="install-form" onSubmit={async (event) => {
        event.preventDefault();
        const result = await act('install', () => api.pluginInstall(installRepo.trim(), installBranch.trim() || 'main'), '安装完成');
        if (result?.ok) { setInstallOpen(false); setInstallRepo(''); }
      }}>
        <label className="field"><span>GitHub 仓库</span><input className="input" placeholder="https://github.com/user/plugin" required
          value={installRepo} disabled={!!operation} onChange={(event) => setInstallRepo(event.target.value)} autoFocus /></label>
        <label className="field"><span>分支</span><input className="input" value={installBranch} disabled={!!operation} onChange={(event) => setInstallBranch(event.target.value)} /></label>
        <p className="muted small">只允许从 GitHub 下载；安装后自动启用并加载，官方插件不可被覆盖。</p>
        <div className="modal-actions"><button type="button" className="btn" disabled={!!operation} onClick={() => setInstallOpen(false)}>取消</button>
          <button className="btn primary" disabled={!!operation || !installRepo.trim()}>{operation === 'install' ? '安装中…' : '下载并安装'}</button></div>
      </form>
    </Modal>
  </div>;
}
