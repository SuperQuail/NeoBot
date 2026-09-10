// firecontrol.tsx —— 火控台 / 舰炮管制（对应 2D 面板 pages/config/BotConfigPanel.tsx）
//
// 一、本体 config.toml 的在线编辑：表单（复用 components/SchemaForm）与原始 TOML 双模式，
//     校验 / 保存 / 重载运行时 / 重启 NeoBot 全部走真实接口，并展示 changes（已生效 / 需重启）。
// 二、损管读数：hull / heat 两项舰况来自父级（由 /api/system 派生），
//     告警清单的每一项都由一个真实指标 + 明确阈值推导，旁边标注字段名，绝不臆造数值。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { ConfigSaveBody } from '../../../api/endpoints';
import type { ConfigChanges, ConfigDocument } from '../../../api/types';
import type { SystemInfo } from '../../../api/types';
import type { Vital } from '../../core/types';
import { bindValues } from '../../../pages/config/shared';
import { getPath, setPath } from '../../../utils/paths';
import { useQuery } from '../../../data/useQuery';
import { QK } from '../../../data/queryKeys';
import { fmt1 } from '../../../utils/format';
import Icon from '../../../components/Icon';
import Modal from '../../../components/Modal';
import ProgressBar from '../../../components/ProgressBar';
import SchemaForm from '../../../components/SchemaForm';
import { toast } from '../../../components/Toast';
import { sfx } from '../../core/sound';
import { notify } from '../../core/store';
import type { PanelProps } from './index';

interface ChangeEntry {
  path: string[];
  before: unknown;
  after: unknown;
}

interface DamageItem {
  name: string;
  /** 底层指标名（与 /api/system 字段一一对应） */
  metric: string;
  value: string;
  status: 'ok' | 'warn' | 'crit';
  note: string;
}

const REFRESH_CHOICES: Array<[number, string]> = [
  [5000, '5 秒'],
  [15000, '15 秒'],
  [60000, '60 秒'],
  [0, '手动'],
];

/** 损管阈值：越界即报损管告警，阈值本身写在界面上，便于核对 */
const LIMITS = { warn: 70, crit: 90 };

function level(value: number, warn = LIMITS.warn, crit = LIMITS.crit): DamageItem['status'] {
  if (value >= crit) return 'crit';
  if (value >= warn) return 'warn';
  return 'ok';
}

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

export default function FireControlPanel({
  station,
  vitals,
  onClose,
  onLaunchMiniGame,
  refreshToken,
}: PanelProps) {
  const [doc, setDoc] = useState<ConfigDocument | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState<'form' | 'toml'>('form');
  const [filter, setFilter] = useState('');
  const [errors, setErrors] = useState<Array<{ path?: string; message?: string }>>([]);
  const [notice, setNotice] = useState<{ text: string; warning?: boolean } | null>(null);
  const [changes, setChanges] = useState<ConfigChanges | null>(null);
  const [busy, setBusy] = useState('');
  const [undoStack, setUndoStack] = useState<ChangeEntry[]>([]);
  const [redoStack, setRedoStack] = useState<ChangeEntry[]>([]);
  const [refreshMs, setRefreshMs] = useState(5000);
  const [refreshKey, setRefreshKey] = useState(0);
  const [detailOpen, setDetailOpen] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(0);

  const operationRef = useRef(false);
  const draftRef = useRef<Record<string, any>>({});
  draftRef.current = draft;

  const system = useQuery(QK.system, () => api.system(), { interval: refreshMs });
  const sys = useMemo<SystemInfo>(() => system.data || {}, [system.data]);

  const applyDoc = useCallback((data: ConfigDocument, keepMode = false) => {
    setDoc(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setUndoStack([]);
    setRedoStack([]);
    setErrors([]);
    // 后端不支持表单时直接落到 TOML 模式；保存/放弃修改后保留用户当前选择的模式
    if (!keepMode) setMode(data.form_supported ? 'form' : 'toml');
  }, []);

  const read = useCallback(async () => {
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy('read');
    const result = await api.config();
    operationRef.current = false;
    setBusy('');
    if (!result.ok || !result.data) {
      setDoc(null);
      setNotice({
        text:
          result.status === 401 ? '会话已过期（401），请重新登录' : result.error || '读取 config.toml 失败',
        warning: true,
      });
      return;
    }
    applyDoc(result.data);
    setNotice(null);
    setUpdatedAt(Date.now());
  }, [applyDoc]);

  useEffect(() => {
    void read();
  }, [read, refreshKey]);

  const dirty = useMemo(() => {
    if (!doc) return false;
    return mode === 'toml'
      ? source !== (doc.source || '')
      : JSON.stringify(draft) !== JSON.stringify(doc.config || {});
  }, [doc, draft, source, mode]);

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

  const refresh = useCallback(() => {
    play('beep');
    setRefreshKey((key) => key + 1);
    void system.refetch();
  }, [system]);

  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    refresh();
  }, [refreshToken, refresh]);

  const onPanelKeyDown = usePanelKeys(onClose, refresh);

  const fields = useMemo(() => bindValues(doc?.schema || [], draft), [doc, draft]);

  const changeField = useCallback(
    (path: string[], value: unknown) => {
      if (operationRef.current || mode !== 'form') return;
      const before = getPath(draftRef.current, path);
      if (JSON.stringify(before ?? null) === JSON.stringify(value ?? null)) return;
      setUndoStack((stack) => [...stack, { path, before, after: value }].slice(-100));
      setRedoStack([]);
      setDraft((previous) => setPath(previous, path, value));
    },
    [mode],
  );

  const undo = useCallback(() => {
    if (busy || mode !== 'form') return;
    const entry = undoStack[undoStack.length - 1];
    if (!entry) return;
    setDraft((previous) => setPath(previous, entry.path, entry.before));
    setRedoStack((stack) => [...stack, entry]);
    setUndoStack((stack) => stack.slice(0, -1));
  }, [busy, mode, undoStack]);

  const redo = useCallback(() => {
    if (busy || mode !== 'form') return;
    const entry = redoStack[redoStack.length - 1];
    if (!entry) return;
    setDraft((previous) => setPath(previous, entry.path, entry.after));
    setUndoStack((stack) => [...stack, entry]);
    setRedoStack((stack) => stack.slice(0, -1));
  }, [busy, mode, redoStack]);

  const validate = () =>
    runOperation('validate', async () => {
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

  const save = (reload: boolean) =>
    runOperation('save', async () => {
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
          setNotice({ text: result.error || '配置已被其它会话修改，请重新读取', warning: true });
          toast('配置已被其它会话修改，请重新读取', 'err');
        } else {
          setErrors(result.data?.errors || []);
          setNotice({ text: result.error || '保存失败', warning: true });
          toast(result.error || '保存失败', 'err');
        }
        play('deny');
        return;
      }
      const saved = result.data;
      applyDoc(saved, true);
      setChanges(saved.changes || null);
      setNotice({ text: saved.message || '配置已保存', warning: !saved.applied && reload });
      toast(saved.message || '配置已保存', 'ok');
      notify('火控参数已写入 config.toml', 'good');
      play('beep');
    });

  const reloadRuntime = () => {
    if (busy || operationRef.current) return;
    if (dirty && !window.confirm('重载运行时只使用已保存的配置，不会保存当前草稿。确认继续？')) return;
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

  const restart = () =>
    runOperation('restart', async () => {
      const result = await api.restart();
      toast(
        result.ok ? result.data?.message || '已请求重启' : result.error || '重启失败',
        result.ok ? 'ok' : 'err',
      );
      notify(result.ok ? '舰载主机重启指令已下发' : '重启指令被拒绝', result.ok ? 'warn' : 'good');
    });

  const resetAllDefaults = () => {
    if (!doc || busy || mode !== 'form') return;
    if (!window.confirm('把所有配置项恢复为默认值？可撤销。')) return;
    const next = structuredClone(draftRef.current || {});
    const walk = (list: typeof doc.schema, node: Record<string, any>) => {
      for (const field of list || []) {
        if (field.kind === 'group') {
          if (!node[field.name] || typeof node[field.name] !== 'object') node[field.name] = {};
          walk(field.fields, node[field.name]);
        } else if (field.default !== undefined) {
          node[field.name] = structuredClone(field.default);
        }
      }
    };
    walk(doc.schema, next);
    setUndoStack((stack) => [
      ...stack,
      { path: [], before: structuredClone(draftRef.current), after: structuredClone(next) },
    ]);
    setRedoStack([]);
    setDraft(next);
  };

  // ---- 损管读数 ----
  const hull: Vital | undefined = vitals.find((vital) => vital.key === 'hull');
  const heat: Vital | undefined = vitals.find((vital) => vital.key === 'heat');

  const damage = useMemo<DamageItem[]>(() => {
    const items: DamageItem[] = [];
    if (hull) {
      items.push({
        name: '舰体装甲',
        metric: 'vitals.hull（父级由 /api/system 派生）',
        value: `${hull.value.toFixed(0)}${hull.unit}`,
        status: hull.value <= 30 ? 'crit' : hull.value <= 60 ? 'warn' : 'ok',
        note:
          hull.value <= 30 ? '装甲破损，建议使用装甲合金板' : hull.value <= 60 ? '局部装甲磨损' : '装甲完好',
      });
    }
    if (heat) {
      items.push({
        name: '回路温度',
        metric: 'vitals.heat（父级由 /api/system 派生）',
        value: `${heat.value.toFixed(0)}${heat.unit}`,
        status: level(heat.value, 65, 85),
        note: heat.value >= 85 ? '回路过热，投入冷却剂' : heat.value >= 65 ? '温度偏高' : '温度正常',
      });
    }
    if (sys.cpu_percent != null) {
      items.push({
        name: '主炮控制器',
        metric: 'cpu_percent',
        value: fmt1(sys.cpu_percent, '%'),
        status: level(sys.cpu_percent),
        note: `阈值 ${LIMITS.warn}/${LIMITS.crit}%`,
      });
    }
    if (sys.mem_percent != null) {
      items.push({
        name: '火控解算内存',
        metric: 'mem_percent',
        value: fmt1(sys.mem_percent, '%'),
        status: level(sys.mem_percent),
        note:
          sys.mem_used_mb != null
            ? `已用 ${Math.round(sys.mem_used_mb)} MB`
            : `阈值 ${LIMITS.warn}/${LIMITS.crit}%`,
      });
    }
    if (sys.disk_percent != null) {
      items.push({
        name: '弹药库容量',
        metric: 'disk_percent',
        value: fmt1(sys.disk_percent, '%'),
        status: level(sys.disk_percent, 80, 92),
        note: sys.disk_used_gb != null ? `已用 ${sys.disk_used_gb.toFixed(1)} GB` : '阈值 80/92%',
      });
    }
    const load = Array.isArray(sys.load_average) ? sys.load_average[0] : undefined;
    if (load != null && sys.cpu_count) {
      const percent = (load / sys.cpu_count) * 100;
      items.push({
        name: '炮塔伺服负载',
        metric: 'load_average[0] / cpu_count',
        value: fmt1(percent, '%'),
        status: level(percent, 80, 100),
        note: `负载 ${load.toFixed(2)} / ${sys.cpu_count} 核`,
      });
    }
    return items;
  }, [hull, heat, sys]);

  const critical = damage.filter((item) => item.status === 'crit').length;
  const warning = damage.filter((item) => item.status === 'warn').length;

  const link = notice?.warning ? 'warn' : busy === 'read' && !doc ? 'busy' : doc ? 'ok' : 'err';
  const linkText =
    busy === 'read' && !doc ? '正在读取 config.toml…' : doc ? '火控链路正常' : notice?.text || '火控链路中断';

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
            notify('舰炮演习程序接入中…', 'info');
            onLaunchMiniGame('turret');
          }}
          aria-label="启动舰炮演习"
        >
          <Icon name="play" size={14} /> 舰炮演习
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
        <span className="bp-status-item">末次读取 {clockOf(updatedAt)}</span>
        <span className="bp-status-item">
          损管 {critical > 0 ? `${critical} 项严重` : warning > 0 ? `${warning} 项告警` : '全部正常'}
        </span>
        {dirty && <span className="bp-status-item">有未保存的修改</span>}
        <button className="btn-sm" onClick={refresh} disabled={busy === 'read'} aria-label="刷新数据">
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
        <div className="bp-card">
          <div className="bp-card-head">
            <h3>损管读数</h3>
            <span className="bp-card-meta">
              hull / heat 来自父级舰况，其余为 /api/system 实测（阈值 {LIMITS.warn}/{LIMITS.crit}%）
            </span>
          </div>
          {hull && (
            <ProgressBar
              label={`舰体装甲（${hull.source}）`}
              text={`${hull.value.toFixed(0)}${hull.unit}`}
              pct={hull.value}
            />
          )}
          {heat && (
            <ProgressBar
              label={`回路温度（${heat.source}）`}
              text={`${heat.value.toFixed(0)}${heat.unit}`}
              pct={heat.value}
            />
          )}
          {damage.length === 0 ? (
            <div className="bp-empty">暂无可用指标：/api/system 未返回数据</div>
          ) : (
            <ul className="bp-damage">
              {damage.map((item) => (
                <li className={`bp-damage-row ${item.status}`} key={item.metric}>
                  <span
                    className={`bp-pill ${item.status === 'ok' ? 'ok' : item.status === 'warn' ? 'warn' : 'err'}`}
                  >
                    {item.status === 'ok' ? '正常' : item.status === 'warn' ? '告警' : '严重'}
                  </span>
                  <span className="bp-damage-name">
                    {item.name}
                    <span className="bp-chip">{item.metric}</span>
                  </span>
                  <span className="bp-damage-value">{item.value}</span>
                  <span className="bp-damage-src">{item.note}</span>
                </li>
              ))}
            </ul>
          )}
          {critical > 0 && (
            <div className="bp-alert err" role="alert">
              损管警报：{critical} 项读数超过严重阈值，建议立即降低负载或投入冷却剂。
            </div>
          )}
        </div>

        <div className="bp-card">
          <div className="bp-card-head">
            <h3>本体配置 config.toml</h3>
            <span className="bp-card-meta">
              {doc?.path || '—'} · revision {doc?.revision ?? '—'}
            </span>
          </div>

          <div className="bp-toolbar">
            <div className="bp-tablist" role="tablist" aria-label="编辑方式">
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'form'}
                className={`bp-tab${mode === 'form' ? ' active' : ''}`}
                disabled={!!busy || !doc}
                onClick={() => {
                  if (mode === 'form') return;
                  if (dirty && !window.confirm('切换编辑方式会放弃当前模式未保存的修改，确认切换？')) return;
                  play('beep');
                  setMode('form');
                  setDraft(doc?.config || {});
                  setSource(doc?.source || '');
                  setErrors([]);
                }}
              >
                <Icon name="settings" size={14} /> 表单
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'toml'}
                className={`bp-tab${mode === 'toml' ? ' active' : ''}`}
                disabled={!!busy || !doc}
                onClick={() => {
                  if (mode === 'toml') return;
                  if (dirty && !window.confirm('切换编辑方式会放弃当前模式未保存的修改，确认切换？')) return;
                  play('beep');
                  setMode('toml');
                  setDraft(doc?.config || {});
                  setSource(doc?.source || '');
                  setErrors([]);
                }}
              >
                <Icon name="code" size={14} /> TOML
              </button>
            </div>
            {mode === 'form' && (
              <label className="bp-field" style={{ minWidth: 180 }}>
                <span>搜索配置项</span>
                <input
                  className="input"
                  aria-label="搜索配置项"
                  value={filter}
                  disabled={!!busy}
                  onChange={(event) => setFilter(event.target.value)}
                />
              </label>
            )}
            <span className="bp-spacer" />
            <button className="btn-sm" disabled={!!busy || !doc} onClick={() => void validate()}>
              {busy === 'validate' ? '校验中…' : '校验'}
            </button>
            <button
              className="btn-sm"
              disabled={!!busy || mode === 'toml' || undoStack.length === 0}
              title="撤销 (Ctrl+Z)"
              onClick={undo}
            >
              <Icon name="undo" size={14} /> 撤销{undoStack.length ? ` ${undoStack.length}` : ''}
            </button>
            <button
              className="btn-sm"
              disabled={!!busy || mode === 'toml' || redoStack.length === 0}
              title="重做"
              onClick={redo}
            >
              <Icon name="refresh" size={14} /> 重做
            </button>
            <button
              className="btn-sm"
              disabled={!!busy || mode === 'toml' || !doc}
              onClick={resetAllDefaults}
            >
              恢复默认
            </button>
            <button className="btn-sm" disabled={!!busy || !dirty} onClick={() => doc && applyDoc(doc, true)}>
              放弃修改
            </button>
            <button className="btn-sm primary" disabled={!!busy || !dirty} onClick={() => void save(true)}>
              <Icon name="save" size={14} /> {busy === 'save' ? '保存中…' : '保存并重载'}
            </button>
          </div>

          {notice && (
            <div className={`bp-alert ${notice.warning ? 'warn' : 'ok'}`} role="status">
              <Icon name={notice.warning ? 'more' : 'check'} size={14} /> {notice.text}
            </div>
          )}
          {errors.length > 0 && (
            <div className="bp-alert err" role="alert">
              校验失败：
              <ul>
                {errors.slice(0, 12).map((item, index) => (
                  <li key={index}>
                    <code>{item.path || '?'}</code> {item.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {changes && ((changes.hot_reload_count ?? 0) > 0 || (changes.needs_restart_count ?? 0) > 0) && (
            <div className="bp-alert warn" role="status">
              <strong>
                热重载结果：{changes.hot_reload_count ?? 0} 项已生效，{changes.needs_restart_count ?? 0}{' '}
                项需重启
              </strong>
              {(changes.hot_reload_count ?? 0) > 0 && (
                <ul>
                  {(changes.hot_reload || []).slice(0, 10).map((item) => (
                    <li key={item.path}>
                      已生效 <code>{item.path}</code>：{String(item.before)} → {String(item.after)}
                    </li>
                  ))}
                </ul>
              )}
              {(changes.needs_restart_count ?? 0) > 0 && (
                <ul>
                  {(changes.needs_restart || []).slice(0, 10).map((item) => (
                    <li key={item.path}>
                      需重启 NeoBot 后生效 <code>{item.path}</code>：{item.reason || '构建期配置'}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {!doc && busy === 'read' && <div className="bp-empty">正在读取 config.toml…</div>}
          {!doc && busy !== 'read' && (
            <div className="bp-empty">
              无法读取配置
              <button className="btn-sm" onClick={refresh}>
                重试
              </button>
            </div>
          )}

          {doc && (
            <div className="config-body" role="tabpanel">
              {mode === 'form' ? (
                <SchemaForm
                  fields={fields}
                  values={draft}
                  baseline={doc.config || {}}
                  disabled={!!busy}
                  filter={filter}
                  onChange={changeField}
                />
              ) : (
                <>
                  <p className="bp-metric-src">
                    直接编辑整份 config.toml；保存前会做语法与类型校验，并自动备份旧文件。
                  </p>
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
          )}

          <div className="bp-toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <span className={dirty ? 'bp-pill warn' : 'bp-pill ok'}>
              {dirty ? '有未保存的修改' : '与文件同步'}
            </span>
            <span className="bp-spacer" />
            <button className="btn-sm" disabled={!!busy} onClick={() => void reloadRuntime()}>
              <Icon name="refresh" size={14} /> {busy === 'reload' ? '重载中…' : '重载运行时配置'}
            </button>
            <button className="btn-sm danger" disabled={!!busy} onClick={() => setDetailOpen(true)}>
              {busy === 'restart' ? '重启中…' : '重启 NeoBot'}
            </button>
          </div>
        </div>
      </div>

      <Modal open={detailOpen} title="重启 NeoBot" onClose={() => setDetailOpen(false)}>
        <p>
          {dirty
            ? '重启不会保存当前草稿，未保存的修改可能丢失。面板会短暂不可用，确认重启？'
            : '确认重启 NeoBot？面板会短暂不可用，重启完成后需要重新接入终端。'}
        </p>
        <div className="modal-actions">
          <button className="btn" onClick={() => setDetailOpen(false)}>
            取消
          </button>
          <button
            className="btn danger"
            onClick={() => {
              setDetailOpen(false);
              void restart();
            }}
          >
            确认重启
          </button>
        </div>
      </Modal>
    </section>
  );
}
