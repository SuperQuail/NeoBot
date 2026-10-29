// Plugins.tsx —— 插件工作区：官方/第三方分组、启停、热重载、安装与在线配置
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { api } from '../api/endpoints';
import type { PluginConfigSaveBody } from '../api/endpoints';
import type { ConfigDocument, Plugin, PluginConflict, ProxyInfo, Result } from '../api/types';
import { infoBar, notify } from '../notifications/infoBar';
import Modal, { ModalActions } from '../components/Modal';
import Button from '../components/ui/Button';
import Icon from '../components/Icon';
import WorkspaceLayout from '../components/WorkspaceLayout';
import PluginListPanel from './plugins/PluginListPanel';
import PluginEditorPanel from './plugins/PluginEditorPanel';
import { scheduleErrors } from './plugins/speakingScheduleModel';
import { confirmAction } from '../components/ui/ConfirmDialog';
import PageHeader from '../components/ui/PageHeader';
import { isEditingSurfaceActive, useAutoRefresh } from '../hooks/useAutoRefresh';
import { POLL } from '../data/queryKeys';

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
  const [editorVersion, setEditorVersion] = useState(0);
  const [editingSession, setEditingSession] = useState(false);
  const editingSessionRef = useRef(false);
  const [installOpen, setInstallOpen] = useState(false);
  const [installRepo, setInstallRepo] = useState('');
  const [installBranch, setInstallBranch] = useState('main');
  /** 安装冲突（spec(4) R27）：非空时弹窗进入三选一冲突态 */
  const [installConflict, setInstallConflict] = useState<PluginConflict | null>(null);
  const [proxy, setProxy] = useState<ProxyInfo>({});
  const [proxyOpen, setProxyOpen] = useState(false);
  const proxyEditing = useRef(proxyOpen);
  proxyEditing.current = proxyOpen;
  const [proxyDraft, setProxyDraft] = useState<{ mode: string; host: string; port: number }>({
    mode: 'system',
    host: '127.0.0.1',
    port: 7890,
  });
  const searchRef = useRef<HTMLInputElement | null>(null);
  const actionsRef = useRef<HTMLDetailsElement | null>(null);
  const requestId = useRef(0);
  const documentId = useRef('');
  const listRequest = useRef(0);
  const listPending = useRef<Promise<void> | null>(null);
  const dirtyRef = useRef(false);
  const busyRef = useRef(false);
  const editGeneration = useRef(0);
  const editorState = useRef({ selectedId, configDocument, mode });
  editorState.current = { selectedId, configDocument, mode };
  const mounted = useRef(true);
  const listedSelection = items.find((plugin) => pluginId(plugin) === selectedId);
  const selectedExists = !!listedSelection;
  const dirty =
    !!configDocument &&
    (mode === 'toml'
      ? source !== configDocument.source
      : JSON.stringify(draft) !== JSON.stringify(configDocument.config));
  dirtyRef.current = dirty;
  busyRef.current = !!operation;
  const previousSelection = useRef<Plugin>();
  if (listedSelection) previousSelection.current = listedSelection;
  const selected =
    listedSelection ||
    ((dirty || editingSession || operation) &&
    previousSelection.current &&
    pluginId(previousSelection.current) === selectedId
      ? previousSelection.current
      : undefined);

  const load = useCallback(async (afterWrite = false) => {
    if (listPending.current) {
      await listPending.current;
      if (!afterWrite) return;
    }
    if (!mounted.current) return;
    if (listPending.current) return listPending.current;
    const ticket = ++listRequest.current;
    const pending = (async () => {
      try {
        const data = await api.plugins();
        if (!mounted.current || ticket !== listRequest.current) return;
        setListLoading(false);
        if (!data) {
          setListError('无法读取插件列表，请检查连接后重试');
          return;
        }
        setListError('');
        setItems(data.items || []);
        setConsolePlugin(data.console_plugin || '');
        setPermissions({
          manage_enabled: data.manage_enabled ?? false,
          hot_reload: data.hot_reload ?? false,
        });
        setProxy(data.proxy || {});
        if (!proxyEditing.current) {
          setProxyDraft((current) => ({
            mode: data.proxy?.mode || current.mode,
            host: data.proxy?.host || current.host,
            port: data.proxy?.port || current.port,
          }));
        }
        setSelectedId((current) => {
          if ((data.items || []).some((plugin) => pluginId(plugin) === current)) return current;
          if (dirtyRef.current || busyRef.current || editingSessionRef.current) return current;
          const first =
            (data.items || []).find((plugin) => plugin.status === 'loaded') || (data.items || [])[0];
          return first ? pluginId(first) : '';
        });
      } catch {
        if (mounted.current && ticket === listRequest.current) {
          setListLoading(false);
          setListError('无法读取插件列表，请检查连接后重试');
        }
      }
    })();
    listPending.current = pending;
    try {
      await pending;
    } finally {
      if (listPending.current === pending) listPending.current = null;
    }
  }, []);

  useEffect(() => {
    const pending = listRequest;
    mounted.current = true;
    void load(true);
    return () => {
      mounted.current = false;
      pending.current++;
    };
  }, [load]);
  useAutoRefresh(() => load(), { enabled: !listLoading, interval: POLL.plugins, pauseWhileEditing: false });

  const applyDocument = useCallback((data: ConfigDocument, preferredMode?: string) => {
    editingSessionRef.current = false;
    setEditingSession(false);
    setConfigDocument(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setMode(data.form_supported && (preferredMode !== 'toml' || !data.source_available) ? 'form' : 'toml');
    setErrors([]);
    setConfigError('');
    setEditorVersion((version) => version + 1);
  }, []);

  const read = useCallback(
    async (id: string) => {
      const ticket = ++requestId.current;
      setLoading(true);
      setConfigError('');
      setConfigDocument(null);
      const result = await api.pluginConfig(id);
      if (ticket !== requestId.current) return;
      setLoading(false);
      if (!result.ok || !result.data) {
        setConfigError(result.error || '无法读取配置');
        return;
      }
      documentId.current = id;
      applyDocument(result.data);
    },
    [applyDocument],
  );

  const syncConfig = async () => {
    const state = editorState.current;
    const generation = editGeneration.current;
    if (
      !state.selectedId ||
      dirtyRef.current ||
      busyRef.current ||
      editingSessionRef.current ||
      isEditingSurfaceActive()
    )
      return;
    const canApply = () =>
      mounted.current &&
      editorState.current.selectedId === state.selectedId &&
      editorState.current.configDocument === state.configDocument &&
      editGeneration.current === generation &&
      !dirtyRef.current &&
      !busyRef.current &&
      !editingSessionRef.current &&
      !isEditingSurfaceActive();
    try {
      const result = await api.pluginConfig(state.selectedId);
      if (!canApply()) return;
      if (!result.ok || !result.data) {
        setConfigError(result.error || '暂时无法同步插件配置');
        return;
      }
      setConfigError('');
      if (JSON.stringify(result.data) !== JSON.stringify(state.configDocument)) {
        documentId.current = state.selectedId;
        applyDocument(result.data, editorState.current.mode);
      }
    } catch {
      if (canApply()) setConfigError('暂时无法同步插件配置');
    }
  };
  useAutoRefresh(syncConfig, {
    enabled: !!selectedId && !dirty && !editingSession && !operation && !loading,
  });

  useEffect(() => {
    const pending = requestId;
    if (selectedId && documentId.current === selectedId && (dirtyRef.current || editingSessionRef.current))
      return;
    setConfigDocument(null);
    setConfigError('');
    setErrors([]);
    // 列表轮询只更新运行状态；相同插件的配置文档必须保留，不能覆盖本地草稿。
    if (selectedId && permissions.manage_enabled && selectedExists) void read(selectedId);
    return () => {
      pending.current++;
    };
  }, [selectedId, permissions.manage_enabled, read, selectedExists]);

  useEffect(() => {
    function beforeUnload(event: BeforeUnloadEvent) {
      if (dirtyRef.current || busyRef.current || editingSessionRef.current) {
        event.preventDefault();
        event.returnValue = '';
      }
    }
    function keyboard(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    function closeActions(event: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(event.target as Node))
        actionsRef.current.open = false;
    }
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('pointerdown', closeActions);
    window.addEventListener('keydown', keyboard);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      document.removeEventListener('pointerdown', closeActions);
      window.removeEventListener('keydown', keyboard);
    };
  }, []);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty, busy: !!operation } }));
    return () => {
      window.dispatchEvent(
        new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }),
      );
    };
  }, [dirty, operation]);

  const visible = useMemo(
    () =>
      items
        .filter((plugin) => (sourceFilter === 'all' ? true : plugin.source === sourceFilter))
        .filter((plugin) =>
          `${plugin.name} ${plugin.description || ''} ${plugin.author || ''}`
            .toLowerCase()
            .includes(filter.toLowerCase()),
        )
        .sort((a, b) => a.name.localeCompare(b.name)),
    [items, filter, sourceFilter],
  );

  async function select(plugin: Plugin) {
    const id = pluginId(plugin);
    if (
      operation ||
      (id !== selectedId &&
        (dirty || editingSession) &&
        !(await confirmAction({
          title: '切换插件并放弃修改？',
          description: '当前插件的配置尚未保存。',
          confirmLabel: '放弃并切换',
          danger: true,
        })))
    )
      return;
    if (actionsRef.current) actionsRef.current.open = false;
    setSelectedId(id);
    setMobileDetail(true);
  }

  async function act(key: string, fn: () => Promise<Result<any>>, success: string, showFeedback = true) {
    if (busyRef.current) return;
    editGeneration.current++;
    listRequest.current++;
    if (actionsRef.current) actionsRef.current.open = false;
    busyRef.current = true;
    setOperation(key);
    try {
      const result = await fn();
      const message = result.data?.message || result.error || (result.ok ? success : '操作失败');
      if (showFeedback) notify(message, result.ok ? 'ok' : 'err');
      if (result.ok) {
        if (key === 'uninstall') setSelectedId('');
        await load(true);
      }
      return result;
    } finally {
      setOperation('');
      busyRef.current = false;
    }
  }

  function closeInstall() {
    if (operation) return;
    setInstallOpen(false);
    setInstallConflict(null);
  }

  /**
   * 安装流程（spec(4) R27/D24）：
   *   ① 先 dry_run 探测（不写盘）→ 有冲突就停在弹窗里三选一；
   *   ② 用户在冲突态点「替换现有插件」时才会带 replace=true 再次提交。
   * 未确认替换时后端直接拒绝，磁盘零变化。
   */
  async function submitInstall(replace: boolean) {
    if (busyRef.current) return;
    const repo = installRepo.trim();
    if (!repo) return;
    editGeneration.current++;
    listRequest.current++;
    busyRef.current = true;
    setOperation(replace ? 'install' : 'probe');
    try {
      if (!replace) {
        const probe = await api.pluginInstall(repo, installBranch.trim() || 'main', false, true);
        if (!probe.ok) {
          notify(probe.error || '探测失败', 'err');
          if (probe.data?.conflict) setInstallConflict(probe.data.conflict);
          return;
        }
        const conflict = probe.data?.conflict || null;
        if (conflict) {
          setInstallConflict(conflict);
          return;
        }
      }
      const result = await api.pluginInstall(repo, installBranch.trim() || 'main', replace, false);
      const message = result.data?.message || result.error || (result.ok ? '安装完成' : '安装失败');
      notify(message, result.ok ? 'ok' : 'err');
      if (result.ok) {
        setInstallOpen(false);
        setInstallConflict(null);
        setInstallRepo('');
        await load(true);
        return;
      }
      if (result.data?.conflict) setInstallConflict(result.data.conflict);
    } finally {
      setOperation('');
      busyRef.current = false;
    }
  }

  async function save(reload: boolean) {
    if (!configDocument) return;
    if (
      mode === 'form' &&
      selected?.official &&
      selected.name === 'speaking_schedule' &&
      scheduleErrors(draft).length
    )
      return;
    const body: PluginConfigSaveBody = {
      revision: configDocument.revision,
      mode,
      reload,
      ...(mode === 'toml' ? { source } : { config: draft }),
    };
    const result = await act('save', () => api.pluginConfigSave(selectedId, body), '配置已保存', false);
    if (!result) return;
    if (result.ok && result.data) {
      applyDocument(result.data, mode);
      const pending = reload && !result.data.applied;
      infoBar({
        title: pending ? '配置已保存，尚未生效' : '插件配置已保存',
        tone: pending ? 'warn' : 'ok',
        message: pending ? '请查看详情，确认后续生效方式。' : undefined,
        details: result.data.message ? <p>{result.data.message}</p> : undefined,
      });
    } else {
      setConfigError(result.error || '保存失败，请重试');
      setErrors(result.data?.errors || []);
    }
  }

  async function changeMode(next: 'form' | 'toml') {
    if (mode === next || operation || !configDocument) return;
    editGeneration.current++;
    if (
      (dirty || editingSession) &&
      !(await confirmAction({
        title: '切换编辑方式？',
        description: '当前插件尚未保存的配置修改会丢失。',
        confirmLabel: '切换方式',
        danger: true,
      }))
    )
      return;
    setDraft(configDocument.config || {});
    setSource(configDocument.source || '');
    setErrors([]);
    setMode(next);
    editingSessionRef.current = false;
    setEditingSession(false);
    setEditorVersion((version) => version + 1);
  }

  function changeField(path: string[], value: unknown) {
    editGeneration.current++;
    setErrors([]);
    setDraft((previous) => {
      const next: Record<string, any> = structuredClone(previous);
      let target: Record<string, any> = next;
      for (const key of path.slice(0, -1)) target = target[key as string];
      Object.defineProperty(target, path[path.length - 1], {
        value,
        writable: true,
        enumerable: true,
        configurable: true,
      });
      return next;
    });
  }

  const isConsole = selected?.name === consolePlugin;
  const canEdit = selectedExists && permissions.manage_enabled && !!configDocument && !loading;
  const invalidSchedule =
    mode === 'form' &&
    selected?.official &&
    selected.name === 'speaking_schedule' &&
    scheduleErrors(draft).length > 0;
  const canSave = canEdit && dirty && !operation && !errors.length && !invalidSchedule;
  const canReload =
    selectedExists &&
    !!selected &&
    !isConsole &&
    permissions.manage_enabled &&
    !operation &&
    !dirty &&
    selected.hot_reload !== false;
  const canManage =
    selectedExists && !!selected && permissions.manage_enabled && !operation && !dirty && selected.manageable;

  return (
    <div
      className="page plugins-page page--viewport"
      onInputCapture={(event) => {
        if (!(event.target instanceof HTMLElement) || !event.target.closest('.config-body')) return;
        editGeneration.current++;
        editingSessionRef.current = true;
        setEditingSession(true);
      }}
    >
      <PageHeader
        title="插件管理"
        actions={
          <Button
            variant="primary"
            disabled={!permissions.manage_enabled || !!operation}
            onClick={() => {
              setInstallConflict(null);
              setInstallOpen(true);
            }}
          >
            <Icon name="plus" /> 安装插件
          </Button>
        }
      />
      <WorkspaceLayout
        className="plugin-workspace"
        showDetail={mobileDetail}
        panel={
          <PluginListPanel
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
            proxy={proxy}
            onSelect={select}
            onOpenProxy={() => setProxyOpen(true)}
            onReload={() => void load()}
          />
        }
        editor={
          <PluginEditorPanel
            selected={selected}
            selectedPresent={selectedExists}
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
            onSourceChange={(value) => {
              editGeneration.current++;
              setSource(value);
              setErrors([]);
            }}
            onChangeField={changeField}
            onRetryRead={() => {
              void read(selectedId);
            }}
          />
        }
      />
      {/* 弹窗仍由页面持有：安装第三方插件 / 插件下载代理 */}
      <Modal
        open={installOpen}
        title="安装第三方插件"
        onClose={() => {
          if (!operation) closeInstall();
        }}
      >
        <form
          className="install-form"
          onSubmit={async (event) => {
            event.preventDefault();
            await submitInstall(false);
          }}
        >
          <label className="field">
            <span>GitHub 仓库</span>
            <input
              className="input"
              placeholder="https://github.com/user/plugin"
              required
              value={installRepo}
              disabled={!!operation}
              onChange={(event) => setInstallRepo(event.target.value)}
              data-autofocus
            />
          </label>
          <label className="field">
            <span>分支</span>
            <input
              className="input"
              value={installBranch}
              disabled={!!operation}
              onChange={(event) => setInstallBranch(event.target.value)}
            />
          </label>
          {installConflict && (
            <div className="workspace-error" role="alert">
              <strong>插件 ID 冲突：只能二选一</strong>
              <div className="muted small">
                {installConflict.message || '已存在同名插件，请选择保留现有或替换。'}
              </div>
              <div className="muted small">
                待安装：{installConflict.requested?.name || '—'}
                {installConflict.requested?.version ? ` v${installConflict.requested.version}` : ''}
                {installConflict.requested?.repo ? ` · 来源 ${installConflict.requested.repo}` : ''}
              </div>
              <div className="muted small">
                已存在：{installConflict.existing?.name || '—'}
                {installConflict.existing?.version
                  ? ` v${installConflict.existing.version}`
                  : '（未声明版本）'}
                {installConflict.existing?.repo ? ` · 来源 ${installConflict.existing.repo}` : ' · 来源未知'}
                {installConflict.existing?.official ? ' · 官方插件（保留字）' : ''}
              </div>
              <ModalActions>
                <Button type="button" disabled={!!operation} onClick={closeInstall}>
                  保留现有
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  disabled={!!operation || installConflict.reserved}
                  onClick={async () => {
                    await submitInstall(true);
                  }}
                >
                  {operation === 'install' ? '替换中…' : '替换现有插件'}
                </Button>
                <Button type="button" disabled={!!operation} onClick={closeInstall}>
                  取消
                </Button>
              </ModalActions>
            </div>
          )}
          <p className="muted small">
            只允许从 GitHub 下载；安装后自动启用并加载。官方插件 ID
            为保留字，随本体更新，不能在面板内安装或更新。
          </p>
          <p className="muted small">
            当前下载代理：{proxy.description || '跟随系统'}。网络受限时可在此切换代理模式或端口。
          </p>
          <ModalActions>
            <Button type="button" disabled={!!operation} onClick={() => setProxyOpen(true)}>
              <Icon name="settings" />
              代理设置
            </Button>
            <Button type="button" disabled={!!operation} onClick={closeInstall}>
              取消
            </Button>
            <button
              className="btn primary"
              disabled={!!operation || !installRepo.trim() || !!installConflict}
            >
              {operation === 'probe' ? '探测中…' : operation === 'install' ? '安装中…' : '下载并安装'}
            </button>
          </ModalActions>
        </form>
      </Modal>
      <Modal
        open={proxyOpen}
        title="插件下载代理"
        onClose={() => {
          if (!operation) setProxyOpen(false);
        }}
      >
        <form
          className="install-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const result = await act(
              'proxy',
              () =>
                api.pluginsProxySave({
                  mode: proxyDraft.mode,
                  host: proxyDraft.host,
                  port: Number(proxyDraft.port) || 7890,
                }),
              '代理设置已保存',
            );
            if (result?.ok) {
              setProxy(result.data.proxy || {});
              setProxyOpen(false);
            }
          }}
        >
          <label className="field">
            <span>代理模式</span>
            <select
              className="input"
              value={proxyDraft.mode}
              disabled={!!operation}
              onChange={(event) => setProxyDraft({ ...proxyDraft, mode: event.target.value })}
            >
              <option value="system">跟随系统 / 环境变量代理</option>
              <option value="none">直连（不使用代理）</option>
              <option value="custom">自定义 HTTP 代理</option>
            </select>
          </label>
          {proxyDraft.mode === 'custom' && (
            <>
              <label className="field">
                <span>代理地址</span>
                <input
                  className="input"
                  required
                  value={proxyDraft.host}
                  disabled={!!operation}
                  placeholder="127.0.0.1"
                  onChange={(event) => setProxyDraft({ ...proxyDraft, host: event.target.value })}
                />
              </label>
              <label className="field">
                <span>代理端口</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  max="65535"
                  required
                  value={proxyDraft.port}
                  disabled={!!operation}
                  onChange={(event) => setProxyDraft({ ...proxyDraft, port: Number(event.target.value) })}
                />
              </label>
            </>
          )}
          <p className="muted small">
            保存后写入 <code>config.toml</code> 的 <code>[plugins]</code>，下一次下载立即生效（无需重启）。
          </p>
          <ModalActions>
            <Button type="button" disabled={!!operation} onClick={() => setProxyOpen(false)}>
              取消
            </Button>
            <button className="btn primary" disabled={!!operation}>
              {operation === 'proxy' ? '保存中…' : '保存代理设置'}
            </button>
          </ModalActions>
        </form>
      </Modal>
    </div>
  );
}
