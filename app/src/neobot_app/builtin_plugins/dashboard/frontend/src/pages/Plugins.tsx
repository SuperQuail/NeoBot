// Plugins.tsx —— 插件工作区：官方/第三方分组、启停、热重载、安装与在线配置
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { api } from '../api/endpoints';
import type { PluginConfigSaveBody } from '../api/endpoints';
import type { ConfigDocument, Plugin, ProxyInfo, Result } from '../api/types';
import { toast } from '../components/Toast';
import Modal from '../components/Modal';
import Icon from '../components/Icon';
import WorkspaceLayout from '../components/WorkspaceLayout';
import PluginListPanel from './plugins/PluginListPanel';
import PluginEditorPanel from './plugins/PluginEditorPanel';
import '../styles/plugins.css';

const statusLabels: Record<string, string> = {
  loaded: '运行中',
  error: '异常',
  disabled: '已停用',
  unloaded: '未加载',
  stopped: '已停止',
};
const statusGroups: Array<[string, string]> = [
  ['loaded', '运行中'],
  ['disabled', '已停用'],
  ['error', '异常'],
  ['other', '其他'],
];
const pluginId = (plugin: Plugin): string => plugin.id || plugin.path || plugin.name;

interface Notice {
  text?: string;
  warning?: boolean;
}

const SOURCE_FILTERS: Array<[string, string]> = [
  ['all', '全部'],
  ['official', '官方'],
  ['third_party', '第三方'],
];

export default function Plugins() {
  const [items, setItems] = useState<Plugin[]>([]);
  const [permissions, setPermissions] = useState({ manage_enabled: false, hot_reload: false });
  const [consolePlugin, setConsolePlugin] = useState('');
  const [listError, setListError] = useState('');
  const [listLoading, setListLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedId, setSelectedId] = useState('');
  const [mobileDetail, setMobileDetail] = useState(false);
  const [configDocument, setConfigDocument] = useState<ConfigDocument | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState<'form' | 'toml'>('form');
  const [errors, setErrors] = useState<Array<{ path?: string; message?: string }>>([]);
  const [configError, setConfigError] = useState('');
  const [loading, setLoading] = useState(false);
  const [operation, setOperation] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [editorVersion, setEditorVersion] = useState(0);
  const [installOpen, setInstallOpen] = useState(false);
  const [installRepo, setInstallRepo] = useState('');
  const [installBranch, setInstallBranch] = useState('main');
  const [proxy, setProxy] = useState<ProxyInfo>({});
  const [proxyOpen, setProxyOpen] = useState(false);
  const [proxyDraft, setProxyDraft] = useState<{ mode: string; host: string; port: number }>({
    mode: 'system',
    host: '127.0.0.1',
    port: 7890,
  });
  const searchRef = useRef<HTMLInputElement | null>(null);
  const actionsRef = useRef<HTMLDetailsElement | null>(null);
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
    setProxy(data.proxy || {});
    setProxyDraft((current) => ({
      mode: data.proxy?.mode || current.mode,
      host: data.proxy?.host || current.host,
      port: data.proxy?.port || current.port,
    }));
    setSelectedId((current) => {
      if ((data.items || []).some((plugin) => pluginId(plugin) === current)) return current;
      if (dirtyRef.current || busyRef.current) return current;
      const first = (data.items || []).find((plugin) => plugin.status === 'loaded') || (data.items || [])[0];
      return first ? pluginId(first) : '';
    });
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 20000);
    return () => { clearInterval(timer); listRequest.current++; };
  }, [load]);

  const applyDocument = useCallback((data: ConfigDocument, preferredMode?: string) => {
    setConfigDocument(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setMode(data.form_supported && preferredMode !== 'toml' ? 'form' : 'toml');
    setErrors([]);
    setConfigError('');
    setEditorVersion((version) => version + 1);
  }, []);

  const read = useCallback(async (id: string) => {
    const ticket = ++requestId.current;
    setLoading(true);
    setConfigError('');
    setConfigDocument(null);
    setNotice(null);
    const result = await api.pluginConfig(id);
    if (ticket !== requestId.current) return;
    setLoading(false);
    if (!result.ok || !result.data) { setConfigError(result.error || '无法读取配置'); return; }
    applyDocument(result.data);
  }, [applyDocument]);

  useEffect(() => {
    setConfigDocument(null);
    setNotice(null);
    setConfigError('');
    setErrors([]);
    const target = items.find((plugin) => pluginId(plugin) === selectedId);
    if (selectedId && permissions.manage_enabled && target) void read(selectedId);
    return () => { requestId.current++; };
  }, [selectedId, permissions.manage_enabled, read, items]);

  useEffect(() => {
    function beforeUnload(event: BeforeUnloadEvent) {
      if (dirtyRef.current || busyRef.current) { event.preventDefault(); event.returnValue = ''; }
    }
    function guardNavigation(event: MouseEvent) {
      const link = (event.target as HTMLElement | null)?.closest('a[href]');
      if (!link || !link.getAttribute('href')?.startsWith('#/')) return;
      if (busyRef.current || (dirtyRef.current && !window.confirm('配置尚未保存，确认离开？'))) {
        event.preventDefault(); event.stopPropagation();
      }
    }
    function keyboard(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); searchRef.current?.focus();
      }
    }
    function closeActions(event: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(event.target as Node)) actionsRef.current.open = false;
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
    return () => {
      window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: false }));
    };
  }, [dirty, operation]);

  const visible = useMemo(() => items
    .filter((plugin) => (sourceFilter === 'all' ? true : plugin.source === sourceFilter))
    .filter((plugin) => `${plugin.name} ${plugin.description || ''} ${plugin.author || ''}`.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name)), [items, filter, sourceFilter]);

  function select(plugin: Plugin) {
    const id = pluginId(plugin);
    if (operation || (id !== selectedId && dirty && !confirm('配置尚未保存，确认切换插件并放弃修改？'))) return;
    if (actionsRef.current) actionsRef.current.open = false;
    setSelectedId(id);
    setMobileDetail(true);
  }

  async function act(key: string, fn: () => Promise<Result<any>>, success: string) {
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

  async function save(reload: boolean) {
    if (!configDocument) return;
    const body: PluginConfigSaveBody = { revision: configDocument.revision, mode, reload,
      ...(mode === 'toml' ? { source } : { config: draft }) };
    const result = await act('save', () => api.pluginConfigSave(selectedId, body), '配置已保存');
    if (!result) return;
    if (result.ok && result.data) {
      applyDocument(result.data, mode);
      setNotice({ text: result.data.message, warning: reload && !result.data.applied });
    } else {
      setConfigError(result.error || '保存失败，请重试');
      setErrors(result.data?.errors || []);
    }
  }

  function changeMode(next: 'form' | 'toml') {
    if (mode === next || operation || !configDocument) return;
    if (dirty && !confirm('切换编辑模式会放弃尚未保存的修改，是否继续？')) return;
    setDraft(configDocument.config || {});
    setSource(configDocument.source || '');
    setErrors([]);
    setMode(next);
    setEditorVersion((version) => version + 1);
  }

  function changeField(path: string[], value: unknown) {
    setDraft((previous) => {
      const next: Record<string, any> = structuredClone(previous);
      let target: Record<string, any> = next;
      for (const key of path.slice(0, -1)) target = target[key as string];
      Object.defineProperty(target, path[path.length - 1], { value, writable: true, enumerable: true, configurable: true });
      return next;
    });
  }

  const isConsole = selected?.name === consolePlugin;
  const canEdit = !!selected && permissions.manage_enabled && !!configDocument && !loading;
  const canSave = canEdit && dirty && !operation && !errors.length;
  const canReload = !!selected && !isConsole && permissions.manage_enabled && !operation && !dirty
    && selected.hot_reload !== false;
  const canManage = !!selected && permissions.manage_enabled && !operation && !dirty && selected.manageable;

  return <>
    <WorkspaceLayout
      showDetail={mobileDetail}
      panel={<PluginListPanel
        items={items}
        visible={visible}
        statusLabels={statusLabels}
        statusGroups={statusGroups}
        pluginId={pluginId}
        selectedId={selectedId}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        filter={filter}
        setFilter={setFilter}
        sourceFilter={sourceFilter}
        setSourceFilter={setSourceFilter}
        sourceFilters={SOURCE_FILTERS}
        searchRef={searchRef}
        listLoading={listLoading}
        listError={listError}
        operation={operation}
        permissions={permissions}
        proxy={proxy}
        onSelect={select}
        onOpenInstall={() => setInstallOpen(true)}
        onOpenProxy={() => setProxyOpen(true)}
        onReload={load}
      />}
      editor={<PluginEditorPanel
        selected={selected}
        selectedId={selectedId}
        itemsCount={items.length}
        statusLabels={statusLabels}
        permissions={permissions}
        configDocument={configDocument}
        proxy={proxy}
        mode={mode}
        source={source}
        draft={draft}
        errors={errors}
        configError={configError}
        notice={notice}
        loading={loading}
        operation={operation}
        dirty={dirty}
        isConsole={isConsole}
        canEdit={canEdit}
        canSave={canSave}
        canReload={canReload}
        canManage={!!canManage}
        editorVersion={editorVersion}
        actionsRef={actionsRef}
        act={act}
        load={load}
        read={read}
        save={save}
        applyDocument={applyDocument}
        onBack={() => setMobileDetail(false)}
        onModeChange={changeMode}
        onSourceChange={setSource}
        onChangeField={changeField}
        onRetryRead={() => { void read(selectedId); }}
      />}
    />
    {/* 弹窗仍由页面持有：安装第三方插件 / 插件下载代理 */}
    <Modal open={installOpen} title="安装第三方插件" onClose={() => { if (!operation) setInstallOpen(false); }}>
      <form className="install-form" onSubmit={async (event) => {
        event.preventDefault();
        const result = await act('install', () => api.pluginInstall(installRepo.trim(), installBranch.trim() || 'main'), '安装完成');
        if (result?.ok) { setInstallOpen(false); setInstallRepo(''); }
      }}>
        <label className="field"><span>GitHub 仓库</span><input className="input" placeholder="https://github.com/user/plugin" required
          value={installRepo} disabled={!!operation} onChange={(event) => setInstallRepo(event.target.value)} data-autofocus /></label>
        <label className="field"><span>分支</span><input className="input" value={installBranch} disabled={!!operation} onChange={(event) => setInstallBranch(event.target.value)} /></label>
        <p className="muted small">只允许从 GitHub 下载；安装后自动启用并加载，官方插件不可被覆盖。</p>
        <p className="muted small">当前下载代理：{proxy.description || '跟随系统'}。网络受限时可在此切换代理模式或端口。</p>
        <div className="modal-actions">
          <button type="button" className="btn" disabled={!!operation} onClick={() => setProxyOpen(true)}><Icon name="settings" />代理设置</button>
          <button type="button" className="btn" disabled={!!operation} onClick={() => setInstallOpen(false)}>取消</button>
          <button className="btn primary" disabled={!!operation || !installRepo.trim()}>{operation === 'install' ? '安装中…' : '下载并安装'}</button></div>
      </form>
    </Modal>
    <Modal open={proxyOpen} title="插件下载代理" onClose={() => { if (!operation) setProxyOpen(false); }}>
      <form className="install-form" onSubmit={async (event) => {
        event.preventDefault();
        const result = await act('proxy', () => api.pluginsProxySave({
          mode: proxyDraft.mode,
          host: proxyDraft.host,
          port: Number(proxyDraft.port) || 7890,
        }), '代理设置已保存');
        if (result?.ok) { setProxy(result.data.proxy || {}); setProxyOpen(false); }
      }}>
        <label className="field"><span>代理模式</span>
          <select className="input" value={proxyDraft.mode} disabled={!!operation}
            onChange={(event) => setProxyDraft({ ...proxyDraft, mode: event.target.value })}>
            <option value="system">跟随系统 / 环境变量代理</option>
            <option value="none">直连（不使用代理）</option>
            <option value="custom">自定义 HTTP 代理</option>
          </select></label>
        {proxyDraft.mode === 'custom' && <>
          <label className="field"><span>代理地址</span>
            <input className="input" required value={proxyDraft.host} disabled={!!operation}
              placeholder="127.0.0.1"
              onChange={(event) => setProxyDraft({ ...proxyDraft, host: event.target.value })} /></label>
          <label className="field"><span>代理端口</span>
            <input className="input" type="number" min="1" max="65535" required value={proxyDraft.port} disabled={!!operation}
              onChange={(event) => setProxyDraft({ ...proxyDraft, port: Number(event.target.value) })} /></label>
        </>}
        <p className="muted small">保存后写入 <code>config.toml</code> 的 <code>[plugins]</code>，下一次下载立即生效（无需重启）。</p>
        <div className="modal-actions"><button type="button" className="btn" disabled={!!operation} onClick={() => setProxyOpen(false)}>取消</button>
          <button className="btn primary" disabled={!!operation}>{operation === 'proxy' ? '保存中…' : '保存代理设置'}</button></div>
      </form>
    </Modal>
  </>;
}
