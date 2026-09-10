// drydock.tsx —— 船坞调配台 / 补给与装载
// 对应 2D 面板 pages/config/EnvPanel.tsx + ModelsPanel.tsx + AssignPanel.tsx。
//
// 三个舱室（页签）：
//   补给清单  —— .env 环境变量与 API 供应商（密钥只写不读）
//   装备库    —— 模型库增删改 + 连通性测试 + 供应商模型拉取
//   装载计划  —— 把主对话 / Agent / 视觉 / TTS / 生图改绑到模型库 key
// 货舱调度小游戏入口也在这里（onLaunchMiniGame('cargo')），舰内物资清单来自本地存档。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { EnvPayload, ModelItem, ModelsPayload, ModelProbeResult } from '../../../api/types';
import { bindValues } from '../../../pages/config/shared';
import { setPath } from '../../../utils/paths';
import Icon from '../../../components/Icon';
import Modal from '../../../components/Modal';
import SchemaForm, { defaultsFromFields } from '../../../components/SchemaForm';
import { toast } from '../../../components/Toast';
import { sfx } from '../../core/sound';
import { notify, useShipLog } from '../../core/store';
import { ITEMS, ITEM_IDS } from '../../core/types';
import type { PanelProps } from './index';

type TabKey = 'env' | 'models' | 'assign';

const TABS: Array<[TabKey, string]> = [
  ['env', '补给清单（.env）'],
  ['models', '装备库（模型库）'],
  ['assign', '装载计划（模型分配）'],
];

const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [30000, '30 秒'],
  [60000, '60 秒'],
];

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

export default function DrydockPanel({ station, onClose, onLaunchMiniGame, refreshToken }: PanelProps) {
  const [tab, setTab] = useState<TabKey>('env');
  const [refreshMs, setRefreshMs] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [updatedAt, setUpdatedAt] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const log = useShipLog();

  // ---- 补给清单（.env） ----
  const [envDoc, setEnvDoc] = useState<EnvPayload | null>(null);
  const [envEdits, setEnvEdits] = useState<Record<string, string>>({});
  const [envDeletes, setEnvDeletes] = useState<string[]>([]);
  const [envFilter, setEnvFilter] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [platformOpen, setPlatformOpen] = useState(false);
  const [platform, setPlatform] = useState({ name: '', url: '', api_key: '' });

  // ---- 装备库（模型库） ----
  const [modelsDoc, setModelsDoc] = useState<ModelsPayload | null>(null);
  const [editing, setEditing] = useState<{ isNew: boolean; draft: Record<string, any> } | null>(null);
  const [probe, setProbe] = useState<ModelProbeResult | null>(null);
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [pulledProvider, setPulledProvider] = useState('');

  // ---- 装载计划（模型分配） ----
  const [assignDraft, setAssignDraft] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState('');

  const envDirty = Object.keys(envEdits).length > 0 || envDeletes.length > 0;

  const read = useCallback(async () => {
    setLoading(true);
    if (tab === 'env') {
      const result = await api.env();
      setLoading(false);
      if (!result.ok || !result.data) {
        setError(result.status === 401 ? '会话已过期（401），请重新登录' : result.error || '读取 .env 失败');
        setEnvDoc(null);
        return;
      }
      setError('');
      setEnvDoc(result.data);
      setEnvEdits({});
      setEnvDeletes([]);
      setUpdatedAt(Date.now());
      return;
    }
    const result = await api.configModels();
    setLoading(false);
    if (!result.ok || !result.data) {
      setError(result.status === 401 ? '会话已过期（401），请重新登录' : result.error || '读取模型库失败');
      setModelsDoc(null);
      return;
    }
    setError('');
    setModelsDoc(result.data);
    setAssignDraft({
      ...(result.data.assignments?.roles || {}),
      creator_image_models: [...(result.data.assignments?.creator_image_models || [])],
    });
    setUpdatedAt(Date.now());
  }, [tab]);

  useEffect(() => {
    void read();
  }, [read, refreshKey]);

  // 自动刷新：环境变量有未保存修改时不覆盖草稿（避免把用户输入冲掉）
  useEffect(() => {
    if (refreshMs === 0) return undefined;
    const timer = setInterval(() => {
      if (tab === 'env' && envDirty) return;
      setRefreshKey((key) => key + 1);
    }, refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, tab, envDirty]);

  const refresh = useCallback(() => {
    play('beep');
    setRefreshKey((key) => key + 1);
  }, []);

  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    setRefreshKey((key) => key + 1);
  }, [refreshToken]);

  const onPanelKeyDown = usePanelKeys(onClose, refresh);

  // ---------- 补给清单 ----------
  const envItems = envDoc?.items || [];
  const envVisible = envItems.filter(
    (item) => !envFilter || item.key.toLowerCase().includes(envFilter.toLowerCase()),
  );

  const addEnvKey = () => {
    const key = newKey.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      toast('环境变量名只能是字母、数字与下划线，且不能以数字开头', 'err');
      return;
    }
    play('beep');
    setEnvEdits((previous) => ({ ...previous, [key]: newValue }));
    setNewKey('');
    setNewValue('');
    toast('已加入待保存列表', 'info');
  };

  const saveEnv = async () => {
    setBusy('env');
    const result = await api.envSave({
      updates: envEdits,
      deletes: envDeletes,
      revision: envDoc?.revision,
      reload: true,
    });
    setBusy('');
    if (!result.ok || !result.data) {
      setError(
        result.status === 409 ? result.error || '已被其它会话修改，请重新读取' : result.error || '保存失败',
      );
      toast(result.error || '保存失败', 'err');
      return;
    }
    setError('');
    setEnvDoc(result.data);
    setEnvEdits({});
    setEnvDeletes([]);
    setUpdatedAt(Date.now());
    toast(result.data.message || '补给清单已保存', 'ok');
    notify(result.data.message || '补给清单已写入 .env', 'good');
  };

  const submitPlatform = async () => {
    setBusy('platform');
    const result = await api.envAddPlatform({ ...platform, revision: envDoc?.revision });
    setBusy('');
    if (!result.ok || !result.data) {
      toast(result.error || '添加供应商失败', 'err');
      return;
    }
    setEnvDoc(result.data);
    setPlatformOpen(false);
    setPlatform({ name: '', url: '', api_key: '' });
    toast(result.data.message || '供应商已添加', 'ok');
  };

  // ---------- 装备库 ----------
  const library = useMemo(() => modelsDoc?.library || [], [modelsDoc]);
  const entrySchema = useMemo(() => modelsDoc?.entry_schema || [], [modelsDoc]);
  const currentProvider = String(editing?.draft?.provider || '').trim();

  const modelNameOptions = useMemo(() => {
    if (pulledProvider && pulledProvider.toLowerCase() === currentProvider.toLowerCase()) {
      return [...new Set(providerModels.filter(Boolean))].sort((left, right) => left.localeCompare(right));
    }
    const names = library
      .filter(
        (item) =>
          String(item.provider || '')
            .trim()
            .toLowerCase() === currentProvider.toLowerCase(),
      )
      .map((item) => String(item.model_name || '').trim())
      .filter(Boolean);
    return [...new Set(names)].sort((left, right) => left.localeCompare(right));
  }, [pulledProvider, providerModels, currentProvider, library]);

  // 引用名（key）不进表单：新建时后端按模型名自动生成，已有条目只读展示
  const modelFields = useMemo(() => {
    if (!editing) return [];
    return bindValues(entrySchema, editing.draft)
      .filter((field) => field.name !== 'key' && !field.hidden)
      .map((field) => {
        if (field.name === 'provider') return { ...field, options: modelsDoc?.provider_options || [] };
        if (field.name === 'model_name') return { ...field, options: modelNameOptions };
        if (field.name === 'model_type')
          return { ...field, options: Object.keys(modelsDoc?.model_type_labels || {}) };
        return field;
      });
  }, [editing, entrySchema, modelsDoc, modelNameOptions]);

  const pullProviderModels = async (provider: string, useSystemProxy?: boolean, silent = false) => {
    const name = String(provider || '').trim();
    if (!name) return;
    setBusy('pull');
    setPulledProvider(name);
    const result = await api.modelsProviderModels({ provider: name, use_system_proxy: !!useSystemProxy });
    setBusy('');
    const payload = result.data || {};
    if (!result.ok || !payload.ok) {
      setProviderModels([]);
      setPulledProvider('');
      if (!silent) toast(payload.message || result.error || '拉取供应商模型列表失败', 'err');
      return;
    }
    setProviderModels(payload.models || []);
    if (!silent) toast(`已拉取 ${(payload.models || []).length} 个模型`, 'ok');
  };

  const saveModel = async (reload: boolean) => {
    if (!editing) return;
    setBusy('model');
    const result = await api.modelsLibrarySave({
      action: 'upsert',
      entry: editing.draft,
      revision: modelsDoc?.revision,
      reload,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存模型失败', 'err');
      return;
    }
    if (result.data?.models)
      setModelsDoc((previous) => ({ ...(previous || {}), library: result.data?.models }));
    else setRefreshKey((key) => key + 1);
    setEditing(null);
    const savedKey = result.data?.saved_key;
    const base = result.data?.message || (reload ? '模型已保存并重载' : '模型已保存；重载配置后生效');
    toast(savedKey ? `${base}（引用名 ${savedKey}）` : base, 'ok');
  };

  const removeModel = async (item: ModelItem) => {
    if (!window.confirm(`确认从模型库删除 ${item.key}？`)) return;
    setBusy('model');
    const result = await api.modelsLibrarySave({
      action: 'delete',
      key: item.key,
      revision: modelsDoc?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '删除失败', 'err');
      return;
    }
    if (result.data?.models)
      setModelsDoc((previous) => ({ ...(previous || {}), library: result.data?.models }));
    toast(`已删除 ${item.key}`, 'ok');
    notify(`模型 ${item.key} 已从装备库移除`, 'warn');
  };

  const runProbe = async (target: unknown) => {
    setBusy('test');
    const result = await api.modelsTest(target);
    setBusy('');
    const payload = result.data || {};
    const record = target as { key?: string; entry?: Record<string, unknown> };
    if (!result.ok && !payload.message) {
      toast(result.error || '测试失败', 'err');
      return;
    }
    setProbe({
      ...payload,
      key: payload.key || record.key || String(record.entry?.key || ''),
      provider: payload.provider || String(record.entry?.provider || ''),
      model_name: payload.model_name || String(record.entry?.model_name || ''),
    });
  };

  // ---------- 装载计划 ----------
  const rolesMeta = modelsDoc?.roles_meta || [];

  const labelOf = (key: string) => {
    const item = library.find((entry) => entry.key === key);
    if (!item) return `${key}（模型库中不存在）`;
    const type = item.type_label ? `[${item.type_label}] ` : '';
    return `${type}${item.key} · ${item.description || item.model_name || item.provider}`;
  };

  /** 与该角色类型匹配的模型排在前面，其余仍可选（与 AssignPanel 行为一致） */
  const sortedLibrary = (role: string) => {
    const expected = modelsDoc?.role_model_types?.[role] || '';
    return [...library].sort((left, right) => {
      const leftMatch = left.model_type === expected ? 0 : 1;
      const rightMatch = right.model_type === expected ? 0 : 1;
      if (leftMatch !== rightMatch) return leftMatch - rightMatch;
      return String(left.key).localeCompare(String(right.key));
    });
  };

  const saveAssignments = async () => {
    setBusy('assign');
    const result = await api.modelsAssignmentsSave({
      assignments: assignDraft,
      revision: modelsDoc?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    if (result.data?.models)
      setModelsDoc((previous) => ({ ...(previous || {}), library: result.data?.models }));
    toast('模型分配已保存；重载配置后生效', 'ok');
    notify('装载计划已写入配置', 'good');
  };

  const inventory = ITEM_IDS.map((id) => ({ def: ITEMS[id], count: log.inventory[id] ?? 0 }));

  const link = error ? 'err' : loading ? 'busy' : 'ok';
  const linkText = error || (loading ? '正在读取货舱清单…' : tab === 'env' ? '.env 已同步' : '模型库已同步');

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
        <button
          className="btn-sm"
          onClick={() => {
            play('beep');
            notify('货舱调度程序接入中…', 'info');
            onLaunchMiniGame('cargo');
          }}
          aria-label="启动货舱调度"
        >
          <Icon name="play" size={14} /> 货舱调度
        </button>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${link}`}>
          <i className="bp-dot" />
          {linkText}
        </span>
        <span className="bp-status-item">末次装载 {clockOf(updatedAt)}</span>
        {envDirty && <span className="bp-status-item">.env 有未保存修改</span>}
        <button className="btn-sm" onClick={refresh} disabled={loading} aria-label="刷新数据">
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
        <div className="bp-toolbar">
          <div className="bp-tablist" role="tablist" aria-label="船坞舱室">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={`bp-tab${tab === key ? ' active' : ''}`}
                onClick={() => {
                  if (tab === key) return;
                  if (envDirty && !window.confirm('切换舱室会放弃未保存的 .env 修改，是否继续？')) return;
                  play('beep');
                  setTab(key);
                  setError('');
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="bp-spacer" />
          <span className="bp-metric-src">
            舰内物资 {Object.values(log.inventory).reduce((sum, n) => sum + (n ?? 0), 0)} 件
          </span>
        </div>

        {error && (
          <div className="bp-alert err" role="alert">
            {error}
            <button className="btn-sm" onClick={refresh}>
              重试
            </button>
          </div>
        )}

        {tab === 'env' && (
          <>
            <div className="bp-toolbar">
              <label className="bp-field" style={{ minWidth: 200 }}>
                <span>搜索变量</span>
                <input
                  className="input"
                  aria-label="搜索环境变量"
                  placeholder="例如 MyProvider_URL"
                  value={envFilter}
                  onChange={(event) => setEnvFilter(event.target.value)}
                />
              </label>
              <span className="bp-spacer" />
              <button className="btn-sm" disabled={!!busy} onClick={() => setPlatformOpen(true)}>
                <Icon name="plus" size={14} /> 一键添加 API 供应商
              </button>
              <button
                className="btn-sm primary"
                disabled={!!busy || !envDirty}
                onClick={() => void saveEnv()}
              >
                <Icon name="save" size={14} /> {busy === 'env' ? '保存中…' : '保存并重载'}
              </button>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>环境变量</h3>
                <span className="bp-card-meta">
                  {envDoc?.path || '.env'} · revision {envDoc?.revision ?? '—'}
                </span>
              </div>
              {loading && !envDoc && <div className="bp-empty">正在读取 .env…</div>}
              {!loading && envVisible.length === 0 && <div className="bp-empty">没有匹配的环境变量</div>}
              {envVisible.length > 0 && (
                <table className="model-table">
                  <thead>
                    <tr>
                      <th>变量</th>
                      <th>值</th>
                      <th>说明</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {envVisible.map((item) => {
                      const edited = Object.prototype.hasOwnProperty.call(envEdits, item.key);
                      const removed = envDeletes.includes(item.key);
                      return (
                        <tr key={item.key} className={removed ? 'bp-removed' : undefined}>
                          <td>
                            <code>{item.key}</code>
                            {item.builtin && <span className="bp-chip">内置</span>}
                            {item.required && <span className="bp-chip">必须</span>}
                          </td>
                          <td>
                            <input
                              className="input"
                              style={{ width: '100%' }}
                              aria-label={`环境变量 ${item.key}`}
                              type={item.sensitive ? 'password' : 'text'}
                              autoComplete="new-password"
                              spellCheck={false}
                              disabled={removed || !!busy}
                              value={removed ? '' : edited ? envEdits[item.key] : item.value || ''}
                              placeholder={
                                item.sensitive
                                  ? item.has_value
                                    ? '已设置 · 留空则不修改'
                                    : '未设置'
                                  : item.has_value
                                    ? ''
                                    : '未配置'
                              }
                              onChange={(event) =>
                                setEnvEdits((previous) => ({ ...previous, [item.key]: event.target.value }))
                              }
                            />
                          </td>
                          <td className="bp-metric-src">{item.description || '—'}</td>
                          <td>
                            {item.sensitive && (
                              <span className={`bp-pill ${item.has_value ? 'ok' : 'err'}`}>
                                {item.has_value ? '已设置' : '未设置'}
                              </span>
                            )}
                            {item.builtin ? (
                              <span className="bp-metric-src">内置</span>
                            ) : (
                              <button
                                className="btn-sm danger"
                                disabled={!!busy || removed}
                                onClick={() => {
                                  if (!window.confirm(`确认删除 ${item.key}？保存后生效。`)) return;
                                  setEnvDeletes((previous) => [...previous, item.key]);
                                }}
                              >
                                删除
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              <div className="bp-toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
                <label className="bp-field" style={{ minWidth: 220 }}>
                  <span>新增变量名</span>
                  <input
                    className="input"
                    aria-label="新增变量名"
                    placeholder="MyProvider_URL"
                    value={newKey}
                    onChange={(event) => setNewKey(event.target.value)}
                  />
                </label>
                <label className="bp-field" style={{ minWidth: 200 }}>
                  <span>值</span>
                  <input
                    className="input"
                    aria-label="新增变量值"
                    value={newValue}
                    onChange={(event) => setNewValue(event.target.value)}
                  />
                </label>
                <button className="btn-sm" onClick={addEnvKey}>
                  <Icon name="plus" size={14} /> 加入待保存
                </button>
              </div>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>API 供应商</h3>
                <span className="bp-card-meta">{(envDoc?.platforms || []).length} 个 · API Key 只写不读</span>
              </div>
              {(envDoc?.platforms || []).length === 0 ? (
                <div className="bp-empty">还没有平台，点击「一键添加 API 供应商」创建</div>
              ) : (
                <table className="model-table">
                  <thead>
                    <tr>
                      <th>平台名</th>
                      <th>API 地址</th>
                      <th>API Key</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(envDoc?.platforms || []).map((item) => (
                      <tr key={item.name}>
                        <td>
                          <code>{item.name}</code>
                          {item.builtin && <span className="bp-chip">内置</span>}
                        </td>
                        <td className="bp-metric-src">{item.url || '—'}</td>
                        <td>
                          <span className={`bp-pill ${item.has_key ? 'ok' : 'err'}`}>
                            {item.has_key ? '已设置' : '未设置'}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-sm"
                            disabled={!!busy}
                            onClick={() => {
                              setPlatform({ name: item.name || '', url: item.url || '', api_key: '' });
                              setPlatformOpen(true);
                            }}
                          >
                            更新 Key
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {tab === 'models' && (
          <>
            <div className="bp-toolbar">
              <span className="bp-metric-src">
                模型单独存放在 [models.registry]，主对话 / Agent / 视觉 / TTS / 生图只引用 key。
              </span>
              <span className="bp-spacer" />
              <button
                className="btn-sm primary"
                disabled={!!busy || entrySchema.length === 0}
                onClick={() => setEditing({ isNew: true, draft: defaultsFromFields(entrySchema) })}
              >
                <Icon name="plus" size={14} /> 新增模型
              </button>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>装备库</h3>
                <span className="bp-card-meta">
                  {library.length} 个模型 · revision {modelsDoc?.revision ?? '—'}
                </span>
              </div>
              {loading && !modelsDoc && <div className="bp-empty">正在读取模型库…</div>}
              {modelsDoc && library.length === 0 && (
                <div className="bp-empty">模型库为空，点击「新增模型」添加</div>
              )}
              {library.length > 0 && (
                <table className="model-table">
                  <thead>
                    <tr>
                      <th>引用名</th>
                      <th>类型</th>
                      <th>供应商 / 模型</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {library.map((item) => (
                      <tr key={item.key}>
                        <td>
                          <code>{item.key}</code>
                          <div className="bp-metric-src">{item.description || '—'}</div>
                        </td>
                        <td>
                          <span className="bp-pill">{item.type_label || item.model_type || '—'}</span>
                        </td>
                        <td>
                          <div>{item.provider}</div>
                          <div className="bp-metric-src">{item.model_name}</div>
                        </td>
                        <td>
                          <span
                            className={`bp-pill ${item.key_configured ? 'ok' : 'err'}`}
                            title={`API Key 来自供应商环境变量 ${item.provider}_APIKey，模型本身不保存密钥`}
                          >
                            {item.key_configured ? 'Key 已配置' : '缺 Key'}
                          </span>
                          {!item.url_configured && (
                            <span className="bp-pill err" title={`请在环境变量中配置 ${item.provider}_URL`}>
                              缺 URL
                            </span>
                          )}
                          {item.registered && <span className="bp-pill ok">已注册</span>}
                          {item.assigned && <span className="bp-pill">已引用</span>}
                          {item.use_system_proxy && <span className="bp-pill dim">系统代理</span>}
                        </td>
                        <td>
                          <button
                            className="btn-sm"
                            disabled={!!busy}
                            onClick={() =>
                              setEditing({
                                isNew: false,
                                draft: structuredClone(
                                  (item as { entry?: Record<string, any> }).entry || item,
                                ),
                              })
                            }
                          >
                            编辑
                          </button>
                          <button
                            className="btn-sm"
                            disabled={!!busy}
                            onClick={() => void runProbe({ key: item.key })}
                          >
                            {busy === 'test' ? '测试中…' : '测试'}
                          </button>
                          <button
                            className="btn-sm danger"
                            disabled={!!busy}
                            onClick={() => void removeModel(item)}
                          >
                            删除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {tab === 'assign' && (
          <>
            <div className="bp-toolbar">
              <span className="bp-metric-src">每个调用方只保存一个模型 key；生图模型可多选。</span>
              <span className="bp-spacer" />
              <button className="btn-sm primary" disabled={!!busy} onClick={() => void saveAssignments()}>
                <Icon name="save" size={14} /> {busy === 'assign' ? '保存中…' : '保存装载计划'}
              </button>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>装载计划</h3>
                <span className="bp-card-meta">{library.length} 个可选模型</span>
              </div>
              {rolesMeta.length === 0 && <div className="bp-empty">模型库未返回角色定义（roles_meta）</div>}
              <div className="bp-grid two">
                {rolesMeta.map((meta) => (
                  <div className="bp-field" key={meta.role}>
                    <span>
                      {meta.label || meta.role}
                      {meta.model_type_label ? ` · ${meta.model_type_label}` : ''}
                      {meta.required ? ' · 必须' : ''}
                    </span>
                    {meta.multi ? (
                      <div className="bp-list">
                        {library.length === 0 && <span className="bp-metric-src">模型库为空</span>}
                        {sortedLibrary(meta.role).map((item) => {
                          const key = String(item.key || '');
                          const checked = (assignDraft.creator_image_models || []).includes(key);
                          return (
                            <label className="bp-list-row" key={key}>
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={!!busy}
                                aria-label={`${meta.label || meta.role} 选用 ${key}`}
                                onChange={() =>
                                  setAssignDraft((previous) => {
                                    const current: string[] = previous.creator_image_models || [];
                                    return {
                                      ...previous,
                                      creator_image_models: checked
                                        ? current.filter((value) => value !== key)
                                        : [...current, key],
                                    };
                                  })
                                }
                              />
                              <span className="bp-list-key">{labelOf(key)}</span>
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <select
                        className="input"
                        aria-label={`${meta.label || meta.role} 模型`}
                        disabled={!!busy}
                        value={assignDraft[meta.role] || ''}
                        onChange={(event) =>
                          setAssignDraft((previous) => ({ ...previous, [meta.role]: event.target.value }))
                        }
                      >
                        {!meta.required && <option value="">（不指定）</option>}
                        {meta.required && !assignDraft[meta.role] && <option value="">（请选择）</option>}
                        {sortedLibrary(meta.role).map((item) => (
                          <option key={item.key} value={item.key}>
                            {labelOf(String(item.key || ''))}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>当前生效情况</h3>
                <span className="bp-card-meta">重载配置后生效</span>
              </div>
              <table className="model-table">
                <thead>
                  <tr>
                    <th>调用方</th>
                    <th>模型 key</th>
                    <th>供应商 / 模型</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {(modelsDoc?.roles || []).map((item, index) => (
                    <tr key={`${item.role}-${index}`}>
                      <td>{item.label || item.role}</td>
                      <td>
                        <code>{item.key || '—'}</code>
                      </td>
                      <td className="bp-metric-src">
                        {[item.provider, item.model_name].filter(Boolean).join(' / ') || '—'}
                      </td>
                      <td>
                        {item.missing && <span className="bp-pill err">模型库中不存在</span>}
                        {!item.missing && item.registered && <span className="bp-pill ok">已注册</span>}
                        {!item.missing && !item.registered && <span className="bp-pill">未注册</span>}
                      </td>
                    </tr>
                  ))}
                  {(modelsDoc?.roles || []).length === 0 && (
                    <tr>
                      <td colSpan={4} className="bp-empty">
                        暂无生效信息
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="bp-card">
          <div className="bp-card-head">
            <h3>舰内物资</h3>
            <span className="bp-card-meta">本地存档 · 用于舰体维修与补给</span>
          </div>
          <ul className="bp-list">
            {inventory.map(({ def, count }) => (
              <li className="bp-list-row" key={def.id}>
                <span className="bp-list-key">
                  {def.name}
                  <span className="bp-chip">{def.hint}</span>
                </span>
                <span className="bp-list-val">{count} 件</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Modal open={platformOpen} title="添加 / 更新 API 供应商" onClose={() => setPlatformOpen(false)}>
        <div className="bp-field">
          <span>平台名（模型库的「供应商」填这个名字）</span>
          <input
            className="input"
            data-autofocus
            aria-label="平台名"
            placeholder="例如 MyProvider"
            spellCheck={false}
            disabled={!!busy}
            value={platform.name}
            onChange={(event) => setPlatform({ ...platform, name: event.target.value })}
          />
        </div>
        <div className="bp-field" style={{ marginTop: 10 }}>
          <span>API 地址（写入 平台名_URL）</span>
          <input
            className="input"
            aria-label="API 地址"
            placeholder="https://api.example.com/v1"
            spellCheck={false}
            disabled={!!busy}
            value={platform.url}
            onChange={(event) => setPlatform({ ...platform, url: event.target.value })}
          />
        </div>
        <div className="bp-field" style={{ marginTop: 10 }}>
          <span>API Key（只写不读，留空保持原有）</span>
          <input
            className="input"
            aria-label="API Key"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            disabled={!!busy}
            value={platform.api_key}
            onChange={(event) => setPlatform({ ...platform, api_key: event.target.value })}
          />
        </div>
        <div className="modal-actions">
          <button className="btn" disabled={!!busy} onClick={() => setPlatformOpen(false)}>
            取消
          </button>
          <button
            className="btn primary"
            disabled={!!busy || !platform.name.trim()}
            onClick={() => void submitPlatform()}
          >
            <Icon name="save" size={14} /> {busy === 'platform' ? '保存中…' : '保存供应商'}
          </button>
        </div>
      </Modal>

      <Modal
        open={!!editing}
        size="wide"
        title={editing?.isNew ? '新增模型' : `编辑模型 ${editing?.draft?.key || ''}`}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <>
            <p className="bp-metric-src">
              引用名（key）：<code>{editing.draft?.key || '保存时按模型名自动生成'}</code> ·
              调用方通过它引用该模型
            </p>
            <SchemaForm
              fields={modelFields}
              disabled={!!busy}
              onChange={(path, value) =>
                setEditing((previous) =>
                  previous ? { ...previous, draft: setPath(previous.draft, path, value) } : previous,
                )
              }
            />
            <div className="modal-actions">
              <button
                className="btn"
                disabled={!!busy || !editing.draft?.provider}
                onClick={() =>
                  void pullProviderModels(
                    String(editing.draft?.provider || ''),
                    !!editing.draft?.use_system_proxy,
                  )
                }
              >
                <Icon name="download" size={14} /> {busy === 'pull' ? '拉取中…' : '拉取供应商模型'}
              </button>
              <button
                className="btn"
                disabled={!!busy}
                onClick={() => void runProbe({ entry: editing.draft, key: editing.draft?.key })}
              >
                测试连通性
              </button>
              <button className="btn" disabled={!!busy} onClick={() => void saveModel(false)}>
                <Icon name="save" size={14} /> 仅保存
              </button>
              <button className="btn primary" disabled={!!busy} onClick={() => void saveModel(true)}>
                <Icon name="save" size={14} /> {busy === 'model' ? '保存中…' : '保存并重载'}
              </button>
            </div>
          </>
        )}
      </Modal>

      <Modal open={!!probe} size="wide" title="模型连通性测试" onClose={() => setProbe(null)}>
        {probe && (
          <>
            <p className={probe.ok ? 'bp-pill ok' : 'bp-pill err'}>
              {probe.message || (probe.ok ? '连接正常' : '测试未通过')}
            </p>
            <table className="model-table">
              <tbody>
                <tr>
                  <th>模型</th>
                  <td>
                    <code>{probe.key || '（未保存草稿）'}</code>
                  </td>
                </tr>
                <tr>
                  <th>供应商 / 模型名</th>
                  <td>
                    {probe.provider || '—'} / <code>{probe.model_name || '—'}</code>
                  </td>
                </tr>
                <tr>
                  <th>请求地址</th>
                  <td className="bp-metric-src">{probe.url || '—'}</td>
                </tr>
                <tr>
                  <th>代理</th>
                  <td>{probe.proxy ? '跟随系统代理' : '直连（不使用代理）'}</td>
                </tr>
                <tr>
                  <th>网络可达</th>
                  <td>{probe.reachable ? '是' : '否'}</td>
                </tr>
                <tr>
                  <th>鉴权</th>
                  <td>{probe.authorized ? '通过' : '未通过'}</td>
                </tr>
                <tr>
                  <th>模型是否存在</th>
                  <td>
                    {probe.model_found === true
                      ? '已找到'
                      : probe.model_found === false
                        ? '未在模型列表中'
                        : '未检查'}
                  </td>
                </tr>
                <tr>
                  <th>HTTP / 耗时</th>
                  <td>
                    {probe.status ?? '—'} / {probe.latency_ms != null ? `${probe.latency_ms} ms` : '—'}
                  </td>
                </tr>
                {probe.detail && (
                  <tr>
                    <th>详情</th>
                    <td className="bp-metric-src">{probe.detail}</td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="modal-actions">
              <button className="btn" onClick={() => setProbe(null)}>
                关闭
              </button>
            </div>
          </>
        )}
      </Modal>
    </section>
  );
}
