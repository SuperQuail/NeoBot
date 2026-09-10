// nav.tsx —— 星图与航迹（对应 2D 面板 pages/Usage.tsx 的图表 + 消息/延迟趋势）
//
// 航迹 = 消息采样点，跃迁延迟 = 延迟采样点，补给消耗 = 模型用量（花费/Token）。
// 三个时间范围（24 小时 / 7 天 / 30 天）同时切换用量接口的 bucket 与消息趋势的采样天数，
// 保证图上两条曲线的横轴口径一致。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { SeriesPayload, UsagePayload, UsageTotals } from '../../../api/types';
import { useQuery } from '../../../data/useQuery';
import { QK } from '../../../data/queryKeys';
import { fmtNum } from '../../../utils/format';
import Icon from '../../../components/Icon';
import LineChart from '../../../components/LineChart';
import StatCard from '../../../components/StatCard';
import { sfx } from '../../core/sound';
import type { PanelProps } from './index';

interface RangeOption {
  key: string;
  label: string;
  hours: number;
  bucket: string;
  /** 消息趋势接口只接受「天数」，与用量范围保持同一口径 */
  days: number;
}

const RANGES: RangeOption[] = [
  { key: '24h', label: '近 24 小时', hours: 24, bucket: 'hour', days: 1 },
  { key: '7d', label: '近 7 天', hours: 24 * 7, bucket: 'hour', days: 7 },
  { key: '30d', label: '近 30 天', hours: 24 * 30, bucket: 'day', days: 30 },
];

const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [15000, '15 秒'],
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

/** 与 pages/Usage.tsx 完全一致的金额/Token 格式，避免两处显示口径不同 */
function fmtCost(value?: number | null): string {
  const num = Number(value || 0);
  if (num === 0) return '¥0';
  if (num < 0.01) return '¥' + num.toFixed(6);
  if (num < 1) return '¥' + num.toFixed(4);
  return '¥' + num.toFixed(2);
}

function fmtTokens(value?: number | null): string {
  const num = Number(value || 0);
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(2) + ' M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + ' K';
  return String(num);
}

function shortLabel(at?: string | null, bucket?: string): string {
  if (!at) return '';
  if (bucket === 'day') return at.slice(5);
  return at.slice(5, 13).replace('T', ' ');
}

export default function NavPanel({ station, onClose, refreshToken }: PanelProps) {
  const [rangeKey, setRangeKey] = useState('24h');
  const [refreshMs, setRefreshMs] = useState(0);
  const [usage, setUsage] = useState<UsagePayload | null>(null);
  const [usageError, setUsageError] = useState('');
  const [usageUpdatedAt, setUsageUpdatedAt] = useState(0);
  const [busy, setBusy] = useState(false);

  const active = RANGES.find((item) => item.key === rangeKey) || RANGES[0];

  const messages = useQuery(`${QK.messages}:${active.days}`, () => api.seriesMessages(active.days), {
    interval: refreshMs,
  });
  const latency = useQuery(QK.latency, () => api.seriesLatency(), { interval: refreshMs });

  // 用量接口返回 Result（带 HTTP 状态），因此单独管理：401 时清空数据而不是继续显示旧数字
  const readUsage = useCallback(async () => {
    setBusy(true);
    const result = await api.seriesUsage(active.hours, active.bucket);
    setBusy(false);
    if (!result.ok) {
      setUsage(null);
      setUsageError(
        result.status === 401
          ? '会话已过期（401），请重新登录后再读取用量'
          : result.error || '读取用量数据失败',
      );
      return;
    }
    setUsageError('');
    setUsage(result.data);
    setUsageUpdatedAt(Date.now());
  }, [active]);

  useEffect(() => {
    void readUsage();
  }, [readUsage]);

  const refreshAll = useCallback(() => {
    play('beep');
    void readUsage();
    void messages.refetch();
    void latency.refetch();
  }, [readUsage, messages, latency]);

  // 外框的刷新按钮只递增 refreshToken；挂载时不重复抓取
  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    refreshAll();
  }, [refreshToken, refreshAll]);

  const onPanelKeyDown = usePanelKeys(onClose, refreshAll);

  const points = useMemo(() => usage?.points || [], [usage]);
  const totals: UsageTotals = usage?.totals || {};
  const bucket = usage?.bucket || active.bucket;
  const costSeries = useMemo(() => points.map((item) => Number(item.cost_cny || 0)), [points]);
  const inputSeries = useMemo(() => points.map((item) => Number(item.input_tokens || 0)), [points]);
  const outputSeries = useMemo(() => points.map((item) => Number(item.output_tokens || 0)), [points]);
  const labels = useMemo(() => points.map((item) => shortLabel(item.at, bucket)), [points, bucket]);

  const messageSeries: SeriesPayload | null = messages.data;
  const latencySeries: SeriesPayload | null = latency.data;
  const latencyPoints = latencySeries?.series || [];
  // 后端以 available=false 表示用量库不可用；若字段缺省但确实有采样点，仍然照实展示
  const showUsage = Boolean(usage && (usage.available ?? (usage.points || []).length > 0));

  const updatedAt = Math.max(usageUpdatedAt, messages.updatedAt, latency.updatedAt);
  const broken =
    (messages.error === 'no-data' ? 1 : 0) + (latency.error === 'no-data' ? 1 : 0) + (usageError ? 1 : 0);
  const link = broken === 0 ? 'ok' : broken === 3 ? 'err' : 'warn';
  const linkText = usageError ? usageError : broken === 0 ? '航迹链路正常' : `部分航迹数据缺失（${broken}）`;

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
        <span className="bp-pill">{active.label}</span>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${link === 'ok' ? 'ok' : link === 'warn' ? 'busy' : 'err'}`}>
          <i className="bp-dot" />
          {linkText}
        </span>
        <span className="bp-status-item">末次刷新 {clockOf(updatedAt)}</span>
        {busy && <span className="bp-status-item">读取中…</span>}
        <button className="btn-sm" onClick={refreshAll} disabled={busy} aria-label="刷新数据">
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
          <div className="bp-tablist" role="tablist" aria-label="时间范围">
            {RANGES.map((item) => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={rangeKey === item.key}
                className={`bp-tab${rangeKey === item.key ? ' active' : ''}`}
                onClick={() => {
                  play('beep');
                  setRangeKey(item.key);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <span className="bp-spacer" />
          <span className="bp-metric-src">金额单位 CNY · 按模型价格表计算 · bucket={bucket}</span>
        </div>

        {usageError && (
          <div className="bp-alert err" role="alert">
            {usageError}
            <button className="btn-sm" onClick={refreshAll}>
              重试
            </button>
          </div>
        )}
        {usage && usage.available === false && (
          <div className="bp-alert warn" role="status">
            用量数据库不可用{usage.error ? `：${usage.error}` : ''}（/api/series/usage 返回 available=false）
          </div>
        )}

        {usage && showUsage && (
          <>
            <div className="bp-grid auto">
              <StatCard label="总花费" value={fmtCost(totals.cost_cny)} sub={`${active.label} · cost_cny`} />
              <StatCard label="API 调用" value={fmtTokens(totals.calls)} sub={`${active.label} · calls`} />
              <StatCard label="输入 Token" value={fmtTokens(totals.input_tokens)} sub="input_tokens" />
              <StatCard label="输出 Token" value={fmtTokens(totals.output_tokens)} sub="output_tokens" />
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>补给消耗航迹</h3>
                <span className="bp-card-meta">{points.length} 个数据点 · cost_cny</span>
              </div>
              <LineChart values={costSeries} fmtTick={(value) => fmtCost(value)} />
              <div className="bp-metric-src">
                {labels.length > 0 ? `${labels[0]} → ${labels[labels.length - 1]}` : '该范围没有采样点'}
              </div>
            </div>

            <div className="bp-grid two">
              <div className="bp-card">
                <div className="bp-card-head">
                  <h3>消息航迹</h3>
                  <span className="bp-card-meta">/api/series/messages?days={active.days}</span>
                </div>
                <LineChart
                  values={(messageSeries?.series || []).map((point) => point.count ?? null)}
                  fmtTick={(value) => fmtNum(Math.round(value))}
                />
                <div className="bp-metric-src">
                  {messageSeries?.total != null
                    ? `区间合计 ${fmtNum(messageSeries.total)} 条 · ${(messageSeries.series || []).length} 个采样点`
                    : '接口未返回区间合计'}
                </div>
              </div>

              <div className="bp-card">
                <div className="bp-card-head">
                  <h3>通讯延迟</h3>
                  <span className="bp-card-meta">/api/series/latency</span>
                </div>
                <LineChart
                  values={latencyPoints.map((point) => point.ms ?? null)}
                  fmtTick={(value) => `${Math.round(value)}ms`}
                />
                <div className="bp-metric-src">
                  {latencyPoints.length
                    ? `当前 ${latencySeries?.current_ms != null ? `${Math.round(latencySeries.current_ms)} ms` : '—'} · 平均 ${
                        latencySeries?.avg_ms != null ? `${latencySeries.avg_ms} ms` : '—'
                      } · 成功率 ${latencySeries?.success_rate != null ? `${latencySeries.success_rate}%` : '—'}`
                    : '等待首次采样…'}
                </div>
              </div>
            </div>

            <div className="bp-grid two">
              <div className="bp-card">
                <div className="bp-card-head">
                  <h3>Token 输入 / 输出</h3>
                  <span className="bp-card-meta">input_tokens / output_tokens</span>
                </div>
                <LineChart values={inputSeries} fmtTick={(value) => fmtTokens(value)} />
                <p className="bp-metric-src">输入 Token</p>
                <LineChart values={outputSeries} fmtTick={(value) => fmtTokens(value)} />
                <p className="bp-metric-src">输出 Token</p>
              </div>

              <div className="bp-card">
                <div className="bp-card-head">
                  <h3>按模型</h3>
                  <span className="bp-card-meta">{(usage.models || []).length} 个模型</span>
                </div>
                <table className="model-table">
                  <thead>
                    <tr>
                      <th>模型</th>
                      <th>供应商</th>
                      <th>调用</th>
                      <th>花费</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(usage.models || []).map((item) => (
                      <tr key={`${item.provider_name}/${item.model_name}`}>
                        <td>
                          <code>{item.model_name}</code>
                        </td>
                        <td>{item.provider_name}</td>
                        <td>{fmtTokens(item.calls)}</td>
                        <td>{fmtCost(item.cost_cny)}</td>
                      </tr>
                    ))}
                    {(usage.models || []).length === 0 && (
                      <tr>
                        <td colSpan={4} className="bp-empty">
                          暂无数据
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bp-card">
              <div className="bp-card-head">
                <h3>按调用模块</h3>
                <span className="bp-card-meta">{(usage.modules || []).length} 个模块</span>
              </div>
              <table className="model-table">
                <thead>
                  <tr>
                    <th>模块</th>
                    <th>调用</th>
                    <th>输入</th>
                    <th>输出</th>
                    <th>花费</th>
                  </tr>
                </thead>
                <tbody>
                  {(usage.modules || []).map((item) => (
                    <tr key={item.module_name}>
                      <td>
                        <code>{item.module_name}</code>
                      </td>
                      <td>{fmtTokens(item.calls)}</td>
                      <td>{fmtTokens(item.input_tokens)}</td>
                      <td>{fmtTokens(item.output_tokens)}</td>
                      <td>{fmtCost(item.cost_cny)}</td>
                    </tr>
                  ))}
                  {(usage.modules || []).length === 0 && (
                    <tr>
                      <td colSpan={5} className="bp-empty">
                        暂无数据
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {!usage && !usageError && (
          <div className="bp-empty" role="status">
            正在读取用量航迹…
          </div>
        )}
      </div>
    </section>
  );
}
