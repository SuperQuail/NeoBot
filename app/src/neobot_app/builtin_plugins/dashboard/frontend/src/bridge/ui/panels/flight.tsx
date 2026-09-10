// flight.tsx —— 飞行甲板 / 舰载单位（对应 2D 面板 pages/Bots.tsx）
//
// 「舰载单位」= 机器人本身，「僚机编队」= 活跃用户，「舰载系统调用」= API 调用排行。
// 每个主题化数字旁边都标注了真实字段名（latency_ms / today_messages / …），不做换算包装。

import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { ActiveUser, BotSummary, RankPayload, SeriesPayload } from '../../../api/types';
import { useQuery } from '../../../data/useQuery';
import { QK } from '../../../data/queryKeys';
import { fmtNum, fmtRelTime, fmtUptime } from '../../../utils/format';
import Icon from '../../../components/Icon';
import LineChart from '../../../components/LineChart';
import { sfx } from '../../core/sound';
import type { PanelProps } from './index';

const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [10000, '10 秒'],
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

export default function FlightPanel({ station, onClose, refreshToken }: PanelProps) {
  const [refreshMs, setRefreshMs] = useState(10000);

  const detail = useQuery(QK.botDetail, () => api.botDetail(), { interval: refreshMs });
  const latency = useQuery(QK.latency, () => api.seriesLatency(), { interval: refreshMs });
  const messages = useQuery(QK.messages, () => api.seriesMessages(30), { interval: refreshMs });
  const apiCalls = useQuery(QK.apiCalls, () => api.statsApiCalls(10), { interval: refreshMs });
  const users = useQuery(QK.activeUsers, () => api.statsActiveUsers(10), { interval: refreshMs });

  const refresh = useCallback(() => {
    play('beep');
    void Promise.all([
      detail.refetch(),
      latency.refetch(),
      messages.refetch(),
      apiCalls.refetch(),
      users.refetch(),
    ]);
  }, [detail, latency, messages, apiCalls, users]);

  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    refresh();
  }, [refreshToken, refresh]);

  const onPanelKeyDown = usePanelKeys(onClose, refresh);

  const bot: BotSummary = detail.data || {};
  const latencyPayload: SeriesPayload | null = latency.data;
  const latencyPoints = latencyPayload?.series || [];
  const messagePoints = messages.data?.series || [];
  const calls: RankPayload = apiCalls.data || {};
  const callItems = calls.items || [];
  const userItems: ActiveUser[] = users.data?.items || [];

  const messageTotal = messagePoints.reduce((sum, point) => sum + (point.count || 0), 0);
  const messagePeak = messagePoints.reduce((max, point) => Math.max(max, point.count || 0), 0);
  const maxCall = callItems.reduce((max, item) => Math.max(max, Number(item.count) || 0), 0);

  const updatedAt = Math.max(
    detail.updatedAt,
    latency.updatedAt,
    messages.updatedAt,
    apiCalls.updatedAt,
    users.updatedAt,
  );
  const failed = [detail, latency, messages, apiCalls, users].filter(
    (query) => query.error === 'no-data',
  ).length;
  const busy = [detail, latency, messages, apiCalls, users].some((query) => query.loading);
  const link = failed === 0 ? 'ok' : failed === 5 ? 'err' : 'warn';

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
        <span className={`bp-pill ${bot.online ? 'ok' : 'err'}`}>{bot.online ? '单位在线' : '单位离线'}</span>
        <button className="btn-sm" onClick={onClose} aria-label="断开终端">
          断开终端
        </button>
      </div>

      <div className="bp-status" role="status" aria-live="polite">
        <span className={`bp-link ${link === 'ok' ? 'ok' : link === 'warn' ? 'busy' : 'err'}`}>
          <i className="bp-dot" />
          {failed === 0 ? '编队链路正常' : failed === 5 ? '编队链路中断' : `部分链路中断（${failed}）`}
        </span>
        <span className="bp-status-item">末次刷新 {clockOf(updatedAt)}</span>
        {busy && <span className="bp-status-item">读取中…</span>}
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
        <div className="bp-card">
          <div className="bp-card-head">
            <h3>旗舰单位</h3>
            <span className="bp-card-meta">/api/bot/detail</span>
          </div>
          {detail.error === 'no-data' && !detail.data ? (
            <div className="bp-empty">无法读取单位详情（可能未登录或协议端未连接）</div>
          ) : (
            <div className="bp-toolbar" style={{ marginBottom: 0 }}>
              {bot.avatar_url && (
                <img
                  className="user-avatar"
                  style={{ width: 48, height: 48, borderRadius: 12 }}
                  src={bot.avatar_url}
                  alt=""
                  referrerPolicy="no-referrer"
                  onError={(event) => {
                    event.currentTarget.style.display = 'none';
                  }}
                />
              )}
              <div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>
                  {bot.nickname || bot.name || '未连接'}
                  <span className={`bp-pill ${bot.online ? 'ok' : 'err'}`} style={{ marginLeft: 8 }}>
                    {bot.online ? '在线' : '离线'}
                  </span>
                </div>
                <div className="bp-metric-src">
                  {bot.app_name ? `${bot.app_name} ${bot.app_version || ''}`.trim() : '协议端未知'} · QQ{' '}
                  {bot.user_id || '—'}
                </div>
              </div>
              <span className="bp-spacer" />
              <dl className="bp-kv" style={{ minWidth: 380 }}>
                <div className="bp-kv-row">
                  <dt>通讯延迟（latency_ms）</dt>
                  <dd>{bot.latency_ms != null ? `${Math.round(bot.latency_ms)} ms` : '—'}</dd>
                </div>
                <div className="bp-kv-row">
                  <dt>运行时长（uptime_seconds）</dt>
                  <dd>{fmtUptime(bot.uptime_seconds)}</dd>
                </div>
                <div className="bp-kv-row">
                  <dt>今日消息（today_messages）</dt>
                  <dd>{fmtNum(bot.today_messages)}</dd>
                </div>
                <div className="bp-kv-row">
                  <dt>累计消息（total_messages）</dt>
                  <dd>{fmtNum(bot.total_messages)}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>

        <div className="bp-grid two">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>通讯延迟航迹</h3>
              <span className="bp-card-meta">/api/series/latency · {latencyPoints.length} 个采样点</span>
            </div>
            <LineChart
              values={latencyPoints.map((point) => point.ms ?? null)}
              fmtTick={(value) => `${Math.round(value)}ms`}
            />
            <div className="bp-metric-src">
              {latencyPoints.length
                ? `当前 ${latencyPayload?.current_ms != null ? `${Math.round(latencyPayload.current_ms)} ms` : '—'} · 平均 ${
                    latencyPayload?.avg_ms != null ? `${latencyPayload.avg_ms} ms` : '—'
                  } · 成功率 ${latencyPayload?.success_rate != null ? `${latencyPayload.success_rate}%` : '—'}`
                : '等待首次采样…'}
            </div>
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>消息航迹</h3>
              <span className="bp-card-meta">/api/series/messages?days=30</span>
            </div>
            <LineChart
              values={messagePoints.map((point) => point.count ?? null)}
              fmtTick={(value) => fmtNum(Math.round(value))}
            />
            <div className="bp-metric-src">
              {messagePoints.length
                ? `区间合计 ${fmtNum(messageTotal)} 条 · 峰值 ${fmtNum(messagePeak)}/采样点`
                : '尚无历史数据'}
            </div>
          </div>
        </div>

        <div className="bp-grid two">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>舰载系统调用</h3>
              <span className="bp-card-meta">
                共 {fmtNum(calls.total_calls)} 次 · {calls.unique_actions ?? 0} 种动作
              </span>
            </div>
            {callItems.length === 0 ? (
              <div className="bp-empty">尚未捕获到 API 调用</div>
            ) : (
              <ul className="bp-rank">
                {callItems.map((item, index) => (
                  <li className="bp-rank-row" key={item.action || index}>
                    <span className="bp-rank-no">{index + 1}</span>
                    <div className="bp-rank-track">
                      <div
                        className="bp-rank-fill"
                        style={{ width: `${maxCall > 0 ? ((Number(item.count) || 0) / maxCall) * 100 : 0}%` }}
                      />
                      <span className="bp-rank-label">{item.action || '—'}</span>
                    </div>
                    <span className="bp-rank-count">{fmtNum(item.count)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>僚机编队（活跃用户）</h3>
              <span className="bp-card-meta">追踪 {users.data?.tracked_users ?? 0} 人</span>
            </div>
            {userItems.length === 0 ? (
              <div className="bp-empty">尚无消息记录</div>
            ) : (
              <ul className="bp-list">
                {userItems.map((user, index) => (
                  <li className="bp-list-row" key={String(user.user_id)}>
                    <span className="bp-rank-no">{index + 1}</span>
                    <img
                      className="user-avatar"
                      src={`https://q1.qlogo.cn/g?b=qq&nk=${user.user_id}&s=100`}
                      alt=""
                      referrerPolicy="no-referrer"
                      onError={(event) => {
                        event.currentTarget.style.visibility = 'hidden';
                      }}
                    />
                    <span className="bp-list-key">{user.nickname || `用户 ${user.user_id}`}</span>
                    <span className="bp-list-val">{fmtNum(user.count)} 条</span>
                    <span className="bp-metric-src">{fmtRelTime(user.last_seen)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
