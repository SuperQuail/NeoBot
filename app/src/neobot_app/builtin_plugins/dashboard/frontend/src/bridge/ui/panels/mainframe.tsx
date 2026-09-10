// mainframe.tsx —— 主机机柜 / 模块管理（对应 2D 面板 pages/Plugins.tsx）
//
// 覆盖 2D 页面的全部写操作：启用/停用、热重载、更新、卸载、从 GitHub 安装、下载代理，
// 以及「表单 / TOML」两种模式的插件配置编辑（表单直接复用 components/SchemaForm）。
// 保存/重载返回的 changes 会按「已生效 / 需重启」分别列出。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { PluginConfigSaveBody } from '../../../api/endpoints';
import type { ConfigChanges, ConfigDocument, Plugin, ProxyInfo, Result } from '../../../api/types';
import { bindValues } from '../../../pages/config/shared';
import { setPath } from '../../../utils/paths';
import Icon from '../../../components/Icon';
import Modal from '../../../components/Modal';
import SchemaForm from '../../../components/SchemaForm';
import { toast } from '../../../components/Toast';
import { sfx } from '../../core/sound';
import { notify } from '../../core/store';
import type { PanelProps } from './index';

const STATUS_LABELS: Record<string, string> = {
  loaded: '运行中',
  error: '异常',
  disabled: '已停用',
  unloaded: '未加载',
  stopped: '已停止',
};

const SOURCE_FILTERS: Array<[string, string]> = [
  ['all', '全部'],
  ['official', '官方'],
  ['third_party', '第三方'],
];

const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [20000, '20 秒'],
  [60000, '60 秒'],
];

const pluginId = (plugin: Plugin): string => plugin.id || plugin.path || plugin.name;

function clockOf(ms: number): string {
  if (!ms) return '—';
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
}

function play(effect: keyof typeof sfx): void {
  try {
    sfx[effect]();
  } catch {
    // 音频不可用不影响面板功能
  }
}

function usePanelKeys(onClose: () => void, onRefresh: () => void) {
  const handlers = useRef({ onClose, onRefresh });
  handlers.current = { onClose, onRefresh };
  return useCallback((event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      handlers.current.onClose();
      return;
    }
    if (event.key !== 'r' && event.key !== 'R') return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]'))
      return;
    handlers.current.onRefresh();
  }, []);
}

/** 写操作提示语统一取自后端 message，其次 error，最后才是本地兜底文案 */
function messageOf(result: Result<unknown>, fallback: string): string {
  const data = result.data as { message?: string } | null;
  return data?.message || result.error || fallback;
}

interface ConfirmState {
  title: string;
  body: string;
  label: string;
  run: () => void;
}

export default function MainframePanel({ station, onClose, refreshToken }: PanelProps) {
  const [items, setItems] = useState<Plugin[]>([]);
  const [permissions, setPermissions] = useState({ manage_enabled: false, hot_reload: false });
  const [consolePlugin, setConsolePlugin] = useState('');
  const [proxy, setProxy] = useState<ProxyInfo>({});
  const [proxyDraft, setProxyDraft] = useState<{ mode: string; host: string; port: number }>({
    mode: 'system',
    host: '127.0.0.1',
    port: 7890,
  });
  const [listError, setListError] = useState('');
  const [listLoading, setListLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [refreshMs, setRefreshMs] = useState(20000);
  const [filter, setFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [selectedId, setSelectedId] = useState('');
  const [document, setDocument] = useState<ConfigDocument | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState<'form' | 'toml'>('form');
  const [errors, setErrors] = useState<Array<{ path?: string; message?: string }>>([]);
  const [configError, setConfigError] = useState('');
  const [loading, setLoading] = useState(false);
  const [operation, setOperation] = useState('');
  const [notice, setNotice] = useState('');
  const [changes, setChanges] = useState<ConfigChanges | null>(null);
  const [installOpen, setInstallOpen] = useState(false);
  const [installRepo, setInstallRepo] = useState('');
  const [installBranch, setInstallBranch] = useState('main');
  const [proxyOpen, setProxyOpen] = useState(false);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  const busyRef = useRef(false);
  busyRef.current = !!operation;
  const dirtyRef = useRef(false);

  const selected = items.find((plugin) => pluginId(plugin) === selectedId);
  const isConsole = !!selected && selected.name === consolePlugin;
  const dirty =
    !!document &&
    (mode === 'toml'
      ? source !== (document.source || '')
      : JSON.stringify(draft) !== JSON.stringify(document.config || {}));
  dirtyRef.current = dirty;

  const load = useCallback(async () => {
    const data = await api.plugins();
    setListLoading(false);
    if (!data) {
      setListError('无法读取模块列表（/api/plugins 返回空），请检查连接后重试');
      return;
    }
    setListError('');
    setUpdatedAt(Date.now());
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
      const list = data.items || [];
      if (list.some((plugin) => pluginId(plugin) === current)) return current;
      if (dirtyRef.current || busyRef.current) return current;
      const first = list.find((plugin) => plugin.status === 'loaded') || list[0];
      return first ? pluginId(first) : '';
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (refreshMs === 0) return undefined;
    const timer = setInterval(() => void load(), refreshMs);
    return () => clearInterval(timer);
  }, [load, refreshMs]);

  const readConfig = useCallback(async (id: string) => {
    setLoading(true);
    setConfigError('');
    setDocument(null);
    setChanges(null);
    const result = await api.pluginConfig(id);
    setLoading(false);
    if (!result.ok || !result.data) {
      setConfigError(
        result.status === 401 ? '会话已过期（401），请重新登录' : result.error || '无法读取模块配置',
      );
      return;
    }
    setDocument(result.data);
    setDraft(result.data.config || {});
    setSource(result.data.source || '');
    setErrors([]);
    setMode(result.data.form_supported ? 'form' : 'toml');
  }, []);

  // 选中项变化时读取配置（只读模式下不请求）
  useEffect(() => {
    if (!selectedId || !permissions.manage_enabled) {
      setDocument(null);
      setDraft({});
      setSource('');
      setErrors([]);
      setConfigError('');
      return;
    }
    void readConfig(selectedId);
  }, [selectedId, permissions.manage_enabled, readConfig]);

  const refresh = useCallback(() => {
    play('beep');
    void load();
  }, [load]);

  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    void load();
    if (selectedId && permissions.manage_enabled) void readConfig(selectedId);
  }, [refreshToken, load, readConfig, selectedId, permissions.manage_enabled]);

  const onPanelKeyDown = usePanelKeys(onClose, refresh);

  const visible = useMemo(
    () =>
      items
        .filter((plugin) => (sourceFilter === 'all' ? true : plugin.source === sourceFilter))
        .filter((plugin) =>
          `${plugin.name} ${plugin.description || ''} ${plugin.author || ''}`
            .toLowerCase()
            .includes(filter.toLowerCase()),
        )
        .sort((left, right) => left.name.localeCompare(right.name)),
    [items, filter, sourceFilter],
  );

  const fields = useMemo(() => bindValues(document?.schema || [], draft), [document, draft]);

  async function act<T>(
    key: string,
    run: () => Promise<Result<T>>,
    success: string,
  ): Promise<Result<T> | null> {
    if (operation) return null;
    setOperation(key);
    try {
      const result = await run();
      const message = messageOf(result, result.ok ? success : '操作失败');
      toast(message, result.ok ? 'ok' : 'err');
      notify(message, result.ok ? 'good' : 'warn');
      play(result.ok ? 'beep' : 'deny');
      if (result.ok) await load();
      return result;
    } finally {
      setOperation('');
    }
  }

  const saveConfig = (reload: boolean) =>
    act(
      'save',
      () =>
        api.pluginConfigSave(selectedId, {
          revision: document?.revision,
          mode,
          reload,
          ...(mode === 'toml' ? { source } : { config: draft }),
        } as PluginConfigSaveBody),
      '配置已保存',
    ).then((result) => {
      if (!result) return;
      if (result.ok && result.data) {
        const saved = result.data;
        setDocument(saved);
        setDraft(saved.config || {});
        setSource(saved.source || '');
        setErrors([]);
        setChanges(saved.changes || null);
        setNotice(saved.message || '配置已保存');
      } else {
        setErrors(result.data?.errors || []);
        setConfigError(result.error || '保存失败，请重试');
      }
    });

  const switchMode = (next: 'form' | 'toml') => {
    if (operation || !document || mode === next) return;
    if (dirty && !window.confirm('切换编辑方式会放弃尚未保存的修改，是否继续？')) return;
    play('beep');
    setDraft(document.config || {});
    setSource(document.source || '');
    setErrors([]);
    setMode(next);
  };

  const selectModule = (plugin: Plugin) => {
    const id = pluginId(plugin);
    if (id === selectedId || operation) return;
    if (dirty && !window.confirm('配置尚未保存，确认切换模块并放弃修改？')) return;
    play('beep');
    setSelectedId(id);
    setNotice('');
  };

  const toggleEnabled = () => {
    if (!selected || !permissions.manage_enabled || operation || dirty) return;
    void act('toggle', () => api.pluginToggle(selectedId), '状态已更新');
  };

  const reloadModule = () => {
    if (!selected || operation || dirty || isConsole || selected.hot_reload === false) return;
    void act('reload', () => api.pluginReload(selectedId), '模块已重载');
  };

  const checkUpdates = () => {
    void act('check', () => api.pluginsCheckUpdates(), '更新检查完成');
  };

  const rows = STATUS_LABELS;
  const manage = permissions.manage_enabled;

  return (
    // 面板根节点只在「焦点位于终端内部」时兜底处理 Esc/R：外框（TerminalFrame）已在 window 捕获阶段
    // 接管 Esc 并阻止冒泡，因此这里不会重复触发；面板被直接挂载（测试/单独打开）时它才是唯一入口。
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <section
      className="bp-panel"
      aria-label={`${station.terminal} ${station.title}`}
      onKeyDown={onPanelKeyDown}
    >
      {/* 抬头（编号 / 终端名 / 中文标题）由外框 TerminalFrame 渲染，面板内只保留动作按钮 */}
      <div className="bp-head-actions">
        {!manage && <span className="bp-pill warn">只读模式（manage_plugins 未开启）</span>}
        <button
          className="btn-sm"
          disabled={!!operation}
          onClick={() =>
            setConfirmState({
              title: '检查全部模块更新',
              body: '将向各模块仓库查询最新版本；只检查，不会自动下载。',
              label: '开始检查',
              run: checkUpdates,
            })
          }
        >
          <Icon name="search" size={14} /> 检查更新
        </button>
        <button className="btn-sm" disabled={!!operation || !manage} onClick={() => setInstallOpen(true)}>
          <Icon name="plus" size={14} /> 安装模块
        </button>
        <button className="btn-sm" disabled={!!operation || !manage} onClick={() => setProxyOpen(true)}>
          <Icon name="settings" size={14} /> 下载代理
        </button>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${listError ? 'err' : listLoading ? 'busy' : 'ok'}`}>
          <i className="bp-dot" />
          {listError ? '机柜链路中断' : listLoading ? '正在枚举模块…' : `模块 ${items.length} 个`}
        </span>
        <span className="bp-status-item">末次刷新 {clockOf(updatedAt)}</span>
        <span className="bp-status-item">
          热重载 {permissions.hot_reload ? '可用' : '不可用'} · 下载代理{' '}
          {proxy.description || proxy.mode || '跟随系统'}
        </span>
        <button className="btn-sm" onClick={refresh} disabled={listLoading} aria-label="刷新数据">
          <Icon name="refresh" size={14} /> 刷新
        </button>
        <label className="bp-status-item">
          自动刷新
          <select
            className="input bp-select"
            aria-label="自动刷新间隔"
            value={refreshMs}
            onChange={(event) => setRefreshMs(Number(event.target.value))}
          >
            {REFRESH_CHOICES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="bp-body">
        {listError && (
          <div className="bp-alert err" role="alert">
            {listError}
            <button className="btn-sm" onClick={refresh}>
              重试
            </button>
          </div>
        )}

        <div className="bp-toolbar">
          <div className="bp-tablist" role="tablist" aria-label="模块来源">
            {SOURCE_FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={sourceFilter === key}
                className={`bp-tab${sourceFilter === key ? ' active' : ''}`}
                onClick={() => {
                  play('beep');
                  setSourceFilter(key);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="bp-field" style={{ minWidth: 220 }}>
            <span>搜索</span>
            <input
              className="input"
              aria-label="搜索模块"
              placeholder="模块名 / 描述 / 作者"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
          </label>
        </div>

        <div className="bp-grid side">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>模块清单</h3>
              <span className="bp-card-meta">
                {visible.length} / {items.length} 个
              </span>
            </div>
            {listLoading && items.length === 0 && <div className="bp-empty">正在读取模块列表…</div>}
            {!listLoading && visible.length === 0 && <div className="bp-empty">没有匹配的模块</div>}
            <ul className="bp-list">
              {visible.map((plugin) => {
                const id = pluginId(plugin);
                const active = id === selectedId;
                return (
                  <li className="bp-list-row" key={id}>
                    <button
                      type="button"
                      className={`bp-tab${active ? ' active' : ''}`}
                      aria-current={active ? 'true' : undefined}
                      onClick={() => selectModule(plugin)}
                    >
                      {plugin.name}
                    </button>
                    <span
                      className={`bp-pill ${plugin.status === 'loaded' ? 'ok' : plugin.status === 'error' ? 'err' : 'warn'}`}
                    >
                      {rows[plugin.status] || plugin.status}
                    </span>
                    <span className="bp-chips">
                      <span className="bp-chip">v{plugin.version || '—'}</span>
                      <span className="bp-chip">{plugin.official ? '官方' : '第三方'}</span>
                      {plugin.config_hot_reload === false && <span className="bp-chip">配置需重启</span>}
                    </span>
                    <span className="bp-list-key bp-metric-src">{plugin.description || '—'}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>模块控制</h3>
              <span className="bp-card-meta">{selected ? pluginId(selected) : '未选中'}</span>
            </div>

            {!selected && <div className="bp-empty">在左侧选择一个模块</div>}

            {selected && (
              <>
                <dl className="bp-kv">
                  <div className="bp-kv-row">
                    <dt>状态</dt>
                    <dd>{rows[selected.status] || selected.status}</dd>
                  </div>
                  <div className="bp-kv-row">
                    <dt>版本</dt>
                    <dd>{selected.version || '—'}</dd>
                  </div>
                  <div className="bp-kv-row">
                    <dt>作者</dt>
                    <dd>{selected.author || '—'}</dd>
                  </div>
                  <div className="bp-kv-row">
                    <dt>可管理</dt>
                    <dd>{selected.manageable ? '是' : '否（官方内置）'}</dd>
                  </div>
                </dl>

                {selected.error && (
                  <div className="bp-alert err" role="alert">
                    运行错误：{selected.error}
                  </div>
                )}

                <div className="bp-toolbar" style={{ marginTop: 10 }}>
                  <button
                    className="btn-sm"
                    disabled={!manage || !!operation || dirty}
                    aria-label={`${selected.enabled ? '停用' : '启用'}模块 ${selected.name}`}
                    title={dirty ? '请先保存或放弃修改' : selected.enabled ? '停用模块' : '启用模块'}
                    onClick={toggleEnabled}
                  >
                    <Icon name={selected.enabled ? 'pause' : 'play'} size={14} />
                    {selected.enabled ? '停用' : '启用'}
                  </button>
                  <button
                    className="btn-sm"
                    disabled={!manage || !!operation || dirty || isConsole || selected.hot_reload === false}
                    aria-label={`热重载模块 ${selected.name}`}
                    title={isConsole ? '面板自身不能热重载' : '重载模块'}
                    onClick={reloadModule}
                  >
                    <Icon name="refresh" size={14} /> 热重载
                  </button>
                  <button
                    className="btn-sm"
                    disabled={!manage || !!operation || dirty || !selected.manageable || !selected.repo}
                    onClick={() =>
                      setConfirmState({
                        title: `更新模块 ${selected.name}`,
                        body: '将从仓库重新下载并重载该模块，运行中的任务可能中断。',
                        label: '立即更新',
                        run: () => {
                          void act('update', () => api.pluginUpdate(selectedId), '更新完成').then(
                            (result) => {
                              if (result?.ok) void readConfig(selectedId);
                            },
                          );
                        },
                      })
                    }
                  >
                    <Icon name="download" size={14} /> 更新
                  </button>
                  <button
                    className="btn-sm danger"
                    disabled={!manage || !!operation || dirty || !selected.manageable}
                    onClick={() =>
                      setConfirmState({
                        title: `卸载模块 ${selected.name}`,
                        body: '模块代码会被移入备份目录，独立的数据目录会保留。',
                        label: '确认卸载',
                        run: () => {
                          void act('uninstall', () => api.pluginUninstall(selectedId), '已卸载').then(
                            (result) => {
                              if (result?.ok) setSelectedId('');
                            },
                          );
                        },
                      })
                    }
                  >
                    <Icon name="trash" size={14} /> 卸载
                  </button>
                </div>

                {notice && (
                  <div className="bp-alert ok" role="status">
                    {notice}
                  </div>
                )}
                {configError && (
                  <div className="bp-alert err" role="alert">
                    {configError}
                  </div>
                )}
                {errors.length > 0 && (
                  <div className="bp-alert err" role="alert">
                    校验失败：
                    <ul>
                      {errors.slice(0, 10).map((item, index) => (
                        <li key={index}>
                          <code>{item.path || '?'}</code> {item.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {changes &&
                  ((changes.hot_reload_count ?? 0) > 0 || (changes.needs_restart_count ?? 0) > 0) && (
                    <div className="bp-alert warn" role="status">
                      <strong>
                        热重载结果：{changes.hot_reload_count ?? 0} 项已生效，
                        {changes.needs_restart_count ?? 0} 项需重启
                      </strong>
                      {(changes.hot_reload_count ?? 0) > 0 && (
                        <ul>
                          {(changes.hot_reload || []).slice(0, 8).map((item) => (
                            <li key={item.path}>
                              已生效 <code>{item.path}</code>：{String(item.before)} → {String(item.after)}
                            </li>
                          ))}
                        </ul>
                      )}
                      {(changes.needs_restart_count ?? 0) > 0 && (
                        <ul>
                          {(changes.needs_restart || []).slice(0, 8).map((item) => (
                            <li key={item.path}>
                              需重启 NeoBot 后生效 <code>{item.path}</code>：{item.reason || '构建期配置'}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
              </>
            )}
          </div>
        </div>

        {selected && manage && (
          <div className="bp-card" style={{ marginTop: 14 }}>
            <div className="bp-card-head">
              <h3>模块配置</h3>
              <span className="bp-card-meta">
                {document?.path || selected.config_section || 'plugin.toml'} · revision{' '}
                {document?.revision ?? '—'}
              </span>
            </div>

            <div className="config-tabs">
              <div role="tablist" aria-label="配置编辑方式">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'form'}
                  className={mode === 'form' ? 'active' : ''}
                  disabled={!document?.form_supported || !!operation}
                  onClick={() => switchMode('form')}
                >
                  <Icon name="settings" size={14} /> 配置表单
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'toml'}
                  className={mode === 'toml' ? 'active' : ''}
                  disabled={!document?.source_available || !!operation}
                  onClick={() => switchMode('toml')}
                >
                  <Icon name="code" size={14} /> TOML
                </button>
              </div>
              <span className="bp-metric-src">
                {dirty ? '有未保存的修改' : document ? '与文件同步' : '等待配置'}
              </span>
              <span className="bp-spacer" />
              <button
                className="btn-sm"
                disabled={!!operation || !document}
                onClick={() => void readConfig(selectedId)}
              >
                重新读取
              </button>
              <button
                className="btn-sm"
                disabled={!!operation || !dirty}
                onClick={() => void saveConfig(false)}
              >
                <Icon name="save" size={14} /> {operation === 'save' ? '保存中…' : '仅保存'}
              </button>
              <button
                className="btn-sm primary"
                disabled={!!operation || !dirty}
                onClick={() => void saveConfig(true)}
              >
                <Icon name="save" size={14} /> {operation === 'save' ? '保存中…' : '保存并重载'}
              </button>
            </div>

            {loading && !document && <div className="bp-empty">正在读取模块配置…</div>}

            {document && (
              <div className="config-body">
                {mode === 'form' ? (
                  <SchemaForm
                    fields={fields}
                    values={draft}
                    baseline={document.config || {}}
                    disabled={!!operation}
                    onChange={(path, value) => setDraft((previous) => setPath(previous, path, value))}
                  />
                ) : (
                  <>
                    <p className="bp-metric-src">
                      直接编辑该模块的 TOML；保存前会做语法与类型校验，并自动备份旧文件。
                    </p>
                    <textarea
                      className="toml-editor"
                      aria-label="模块 TOML 配置"
                      spellCheck={false}
                      disabled={!!operation}
                      value={source}
                      onChange={(event) => setSource(event.target.value)}
                    />
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <Modal
        open={installOpen}
        title="从 GitHub 安装模块"
        onClose={() => (operation ? undefined : setInstallOpen(false))}
      >
        <div className="bp-field">
          <span>仓库地址（只允许 GitHub）</span>
          <input
            className="input"
            data-autofocus
            aria-label="模块仓库地址"
            placeholder="https://github.com/user/plugin"
            value={installRepo}
            disabled={!!operation}
            onChange={(event) => setInstallRepo(event.target.value)}
          />
        </div>
        <div className="bp-field" style={{ marginTop: 10 }}>
          <span>分支</span>
          <input
            className="input"
            aria-label="模块分支"
            value={installBranch}
            disabled={!!operation}
            onChange={(event) => setInstallBranch(event.target.value)}
          />
        </div>
        <p className="bp-metric-src">
          安装后自动启用并加载；官方模块不可被覆盖。当前代理：{proxy.description || '跟随系统'}。
        </p>
        <div className="modal-actions">
          <button className="btn" disabled={!!operation} onClick={() => setInstallOpen(false)}>
            取消
          </button>
          <button
            className="btn primary"
            disabled={!!operation || !installRepo.trim()}
            onClick={() => {
              void act(
                'install',
                () => api.pluginInstall(installRepo.trim(), installBranch.trim() || 'main'),
                '安装完成',
              ).then((result) => {
                if (result?.ok) {
                  setInstallOpen(false);
                  setInstallRepo('');
                }
              });
            }}
          >
            {operation === 'install' ? '安装中…' : '下载并安装'}
          </button>
        </div>
      </Modal>

      <Modal
        open={proxyOpen}
        title="模块下载代理"
        onClose={() => (operation ? undefined : setProxyOpen(false))}
      >
        <div className="bp-field">
          <span>代理模式</span>
          <select
            className="input"
            aria-label="代理模式"
            value={proxyDraft.mode}
            disabled={!!operation}
            onChange={(event) => setProxyDraft({ ...proxyDraft, mode: event.target.value })}
          >
            <option value="system">跟随系统 / 环境变量代理</option>
            <option value="none">直连（不使用代理）</option>
            <option value="custom">自定义 HTTP 代理</option>
          </select>
        </div>
        {proxyDraft.mode === 'custom' && (
          <>
            <div className="bp-field" style={{ marginTop: 10 }}>
              <span>代理地址</span>
              <input
                className="input"
                aria-label="代理地址"
                value={proxyDraft.host}
                disabled={!!operation}
                onChange={(event) => setProxyDraft({ ...proxyDraft, host: event.target.value })}
              />
            </div>
            <div className="bp-field" style={{ marginTop: 10 }}>
              <span>代理端口</span>
              <input
                className="input"
                type="number"
                min={1}
                max={65535}
                aria-label="代理端口"
                value={proxyDraft.port}
                disabled={!!operation}
                onChange={(event) => setProxyDraft({ ...proxyDraft, port: Number(event.target.value) })}
              />
            </div>
          </>
        )}
        <p className="bp-metric-src">保存后写入 config.toml 的 [plugins]，下一次下载立即生效（无需重启）。</p>
        <div className="modal-actions">
          <button className="btn" disabled={!!operation} onClick={() => setProxyOpen(false)}>
            取消
          </button>
          <button
            className="btn primary"
            disabled={!!operation}
            onClick={() => {
              void act(
                'proxy',
                () =>
                  api.pluginsProxySave({
                    mode: proxyDraft.mode,
                    host: proxyDraft.host,
                    port: Number(proxyDraft.port) || 7890,
                  }),
                '代理设置已保存',
              ).then((result) => {
                if (result?.ok) {
                  setProxy(result.data?.proxy || {});
                  setProxyOpen(false);
                }
              });
            }}
          >
            {operation === 'proxy' ? '保存中…' : '保存代理设置'}
          </button>
        </div>
      </Modal>

      <Modal open={!!confirmState} title={confirmState?.title} onClose={() => setConfirmState(null)}>
        <p>{confirmState?.body}</p>
        <div className="modal-actions">
          <button className="btn" onClick={() => setConfirmState(null)}>
            取消
          </button>
          <button
            className="btn danger"
            onClick={() => {
              const run = confirmState?.run;
              setConfirmState(null);
              run?.();
            }}
          >
            {confirmState?.label || '确认'}
          </button>
        </div>
      </Modal>
    </section>
  );
}
