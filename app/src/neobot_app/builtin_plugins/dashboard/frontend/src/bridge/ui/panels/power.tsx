// power.tsx —— 能源分配 / 反应堆控制台（对应 2D 面板 pages/System.tsx）
//
// 诚实性约定（重要）：
//   1) 所有「实测值」直接来自 /api/system（CPU / 内存 / 磁盘 / 负载），不做任何换算包装；
//   2) 配能档位是本舰内部的调节量（只影响舰内表现，不写回后端），
//      因此每一行都把「档位」和「实测值」分开显示，并标注底层指标名，
//      不会因为玩家拖动滑块就让实测数字发生变化。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { SystemInfo } from '../../../api/types';
import type { VitalKey } from '../../core/types';
import { useQuery } from '../../../data/useQuery';
import { QK } from '../../../data/queryKeys';
import { fmt1, fmtNum } from '../../../utils/format';
import Icon from '../../../components/Icon';
import ProgressBar from '../../../components/ProgressBar';
import { sfx } from '../../core/sound';
import type { PanelProps } from './index';

const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [3000, '3 秒'],
  [5000, '5 秒'],
  [15000, '15 秒'],
];

/** 反应堆四路输出 -> 真实指标 的固定映射（这是本面板唯一的数据契约） */
interface BusSpec {
  bus: string;
  /** 底层指标名（显示在主题化数字旁边，便于核对） */
  metric: string;
  pick: (sys: SystemInfo) => number | null;
  detail: (sys: SystemInfo) => string;
}

const toPercent = (value: number | undefined | null): number | null =>
  value == null || !Number.isFinite(value) ? null : Math.max(0, Math.min(100, value));

const BUS: Record<VitalKey, BusSpec> = {
  energy: {
    bus: '主反应堆输出',
    metric: 'cpu_percent',
    pick: (sys) => toPercent(sys.cpu_percent),
    detail: (sys) => (sys.cpu_count != null ? `${sys.cpu_count} 核` : '核心数未知'),
  },
  atmosphere: {
    bus: '生命保障回路',
    metric: 'mem_percent',
    pick: (sys) => toPercent(sys.mem_percent),
    detail: (sys) =>
      sys.mem_used_mb != null && sys.mem_total_mb != null
        ? `${Math.round(sys.mem_used_mb)} / ${Math.round(sys.mem_total_mb)} MB`
        : '内存总量未知',
  },
  hull: {
    bus: '结构完整度',
    metric: 'disk_percent',
    pick: (sys) => toPercent(sys.disk_percent),
    detail: (sys) =>
      sys.disk_used_gb != null && sys.disk_total_gb != null
        ? `${sys.disk_used_gb.toFixed(1)} / ${sys.disk_total_gb.toFixed(1)} GB`
        : '磁盘容量未知',
  },
  heat: {
    bus: '散热回路',
    metric: 'load_average[0] / cpu_count',
    pick: (sys) => {
      const load = Array.isArray(sys.load_average) ? sys.load_average[0] : undefined;
      if (load == null || !sys.cpu_count) return null;
      return toPercent((load / sys.cpu_count) * 100);
    },
    detail: (sys) =>
      Array.isArray(sys.load_average) && sys.load_average.length
        ? `负载 ${sys.load_average.map((value) => value.toFixed(2)).join(' / ')}`
        : '负载数据不可用',
  },
};

const PRESETS: Array<{ key: string; label: string; weights: Record<VitalKey, number> }> = [
  { key: 'balanced', label: '均衡', weights: { energy: 25, atmosphere: 25, hull: 25, heat: 25 } },
  { key: 'cruise', label: '巡航', weights: { energy: 20, atmosphere: 25, hull: 25, heat: 30 } },
  { key: 'battle', label: '战斗', weights: { energy: 45, atmosphere: 10, hull: 30, heat: 15 } },
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

export default function PowerPanel({ station, vitals, onClose, refreshToken }: PanelProps) {
  const [refreshMs, setRefreshMs] = useState(5000);
  const [allocation, setAllocation] = useState<Record<VitalKey, number>>(PRESETS[0].weights);
  const system = useQuery(QK.system, () => api.system(), { interval: refreshMs });
  const sys = system.data;

  const refresh = useCallback(() => {
    play('beep');
    void system.refetch();
  }, [system]);

  // 外框刷新：refreshToken 变化时重取一次
  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    void system.refetch();
  }, [refreshToken, system]);

  const onPanelKeyDown = usePanelKeys(onClose, refresh);

  /** 四路实测值（百分比）与分配合计——两个数字来源不同，界面上必须分开标注 */
  const measured = useMemo(
    () =>
      vitals.map((vital) => {
        const spec = BUS[vital.key];
        const percent = sys && spec ? spec.pick(sys) : null;
        return { vital, spec, percent };
      }),
    [vitals, sys],
  );
  const measuredList = measured.map((row) => row.percent).filter((value): value is number => value != null);
  const measuredAvg = measuredList.length
    ? measuredList.reduce((sum, value) => sum + value, 0) / measuredList.length
    : null;
  const allocationSum = vitals.reduce((sum, vital) => sum + (allocation[vital.key] ?? 0), 0);

  const busy = system.loading;
  const link = system.error === 'no-data' && !sys ? 'err' : busy ? 'busy' : 'ok';
  const linkText =
    system.error === 'no-data' && !sys ? '/api/system 无数据' : busy ? '正在采样…' : '反应堆链路正常';

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    play('pulse');
    setAllocation({ ...preset.weights });
  };

  const setWeight = (key: VitalKey, value: number) => {
    setAllocation((previous) => ({ ...previous, [key]: value }));
  };

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
        <span className="bp-pill dim">配能档位仅影响舰内表现</span>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${link}`}>
          <i className="bp-dot" />
          {linkText}
        </span>
        <span className="bp-status-item">末次采样 {clockOf(system.updatedAt)}</span>
        <span className="bp-status-item">
          四路实测均值 {measuredAvg != null ? fmt1(measuredAvg, '%') : '—'}
        </span>
        <span className="bp-status-item">配能合计 {allocationSum}%（本地调节）</span>
        <button className="btn-sm" onClick={refresh} disabled={busy} aria-label="刷新数据">
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
        {system.error === 'no-data' && !sys && (
          <div className="bp-alert err" role="alert">
            /api/system 无数据：无法读取实测指标，已停止显示旧读数。
            <button className="btn-sm" onClick={refresh}>
              重试
            </button>
          </div>
        )}

        <div className="bp-card">
          <div className="bp-card-head">
            <h3>反应堆配能</h3>
            <span className="bp-card-meta">每路主题化档位 ↔ 一个真实指标（右侧为实测值）</span>
          </div>
          <div className="bp-toolbar">
            <div className="bp-toolbar-group" role="group" aria-label="配能预设">
              {PRESETS.map((preset) => (
                <button key={preset.key} type="button" className="btn-sm" onClick={() => applyPreset(preset)}>
                  {preset.label}
                </button>
              ))}
            </div>
            <span className="bp-spacer" />
            <span className="bp-metric-src">档位为本舰内部调节，不会改变 /api/system 的实测数字</span>
          </div>

          {vitals.length === 0 && <div className="bp-empty">暂无舰况数据（父级未传入 vitals）</div>}

          <div className="bp-routing">
            {measured.map(({ vital, spec, percent }) => (
              <div className="bp-routing-row" key={vital.key}>
                <div className="bp-routing-head">
                  <span className="bp-routing-name">{vital.label}</span>
                  <span className="bp-pill dim">{vital.key}</span>
                  <span className="bp-spacer" />
                  <span className="bp-routing-metric">
                    ↔ {spec ? `${spec.bus} · ${spec.metric}` : '无映射指标'}
                  </span>
                </div>

                <label className="bp-field">
                  <span>配能档位 {allocation[vital.key] ?? 0}%（本地）</span>
                  <input
                    className="bp-routing-slider"
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={allocation[vital.key] ?? 0}
                    aria-label={`${vital.label} 配能档位`}
                    onChange={(event) => setWeight(vital.key, Number(event.target.value))}
                  />
                </label>

                <ProgressBar
                  label={`实测（${spec?.metric || '—'}）`}
                  text={percent != null ? fmt1(percent, '%') : '不可用'}
                  pct={percent ?? 0}
                />
                <div className="bp-routing-readout">
                  <span>
                    舰况读数 {vital.value.toFixed(0)}
                    {vital.unit}
                  </span>
                  <span className="bp-spacer" />
                  <span>{spec && sys ? spec.detail(sys) : '指标不可用'}</span>
                </div>
                <div className="bp-metric-src">来源：{vital.source}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="bp-grid two">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>主机资源</h3>
              <span className="bp-card-meta">
                {sys?.hostname || '—'} · PID {sys?.pid ?? '—'}
              </span>
            </div>
            <ProgressBar
              label="CPU（cpu_percent）"
              text={sys?.cpu_percent != null ? fmt1(sys.cpu_percent, '%') : '—'}
              pct={sys?.cpu_percent}
            />
            <ProgressBar
              label="内存（mem_percent）"
              text={
                sys?.mem_used_mb != null
                  ? `${Math.round(sys.mem_used_mb)} / ${Math.round(sys.mem_total_mb ?? 0)} MB`
                  : '—'
              }
              pct={sys?.mem_percent}
            />
            <ProgressBar
              label="磁盘（disk_percent）"
              text={
                sys?.disk_used_gb != null
                  ? `${sys.disk_used_gb.toFixed(1)} / ${(sys.disk_total_gb ?? 0).toFixed(1)} GB`
                  : '—'
              }
              pct={sys?.disk_percent}
            />
            <div className="bp-metric-src" style={{ marginTop: 6 }}>
              {sys?.os || '—'} · Python {sys?.python_version || '—'} · 负载{' '}
              {Array.isArray(sys?.load_average) && sys.load_average.length
                ? sys.load_average.map((v) => v.toFixed(2)).join(' / ')
                : '—'}
            </div>
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>本舰进程</h3>
              <span className="bp-card-meta">/api/system 进程与线程</span>
            </div>
            <dl className="bp-kv">
              <div className="bp-kv-row">
                <dt>进程内存（process_memory_mb）</dt>
                <dd>{sys?.process_memory_mb != null ? `${Math.round(sys.process_memory_mb)} MB` : '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>线程数（process_threads）</dt>
                <dd>{sys?.process_threads ?? '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>CPU 核心（cpu_count）</dt>
                <dd>{sys?.cpu_count ?? '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>主机名（hostname）</dt>
                <dd>{sys?.hostname || '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>磁盘总量（disk_total_gb）</dt>
                <dd>{sys?.disk_total_gb != null ? `${sys.disk_total_gb.toFixed(1)} GB` : '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>内存总量（mem_total_mb）</dt>
                <dd>{sys?.mem_total_mb != null ? `${fmtNum(Math.round(sys.mem_total_mb))} MB` : '—'}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
