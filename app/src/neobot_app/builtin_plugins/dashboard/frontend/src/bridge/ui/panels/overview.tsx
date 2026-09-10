// overview.tsx —— 指挥台 / 舰况总览（对应 2D 面板 pages/Dashboard.tsx）
//
// 数据来源全部是真实接口：/api/overview、/api/system、/api/series/messages、
// /api/stats/api-calls、/api/stats/active-users、/api/tasks、/api/services、/api/plugins、/api/logs。
// 舰况四项（vitals）由父级用 /api/system 的实测值派生后传入，这里只负责呈现并标注来源。
// 本面板是唯一同时提供「火控演习」与「断路器检修」入口的终端。

import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { api } from '../../../api/endpoints';
import type { ActiveUser, SeriesPayload } from '../../../api/types';
import { useQuery } from '../../../data/useQuery';
import { POLL, QK } from '../../../data/queryKeys';
import { fmt1, fmtNum, fmtUptime, mapTag } from '../../../utils/format';
import Icon from '../../../components/Icon';
import ProgressBar from '../../../components/ProgressBar';
import Sparkline from '../../../components/Sparkline';
import StatCard from '../../../components/StatCard';
import { sfx } from '../../core/sound';
import { notify, useShipLog } from '../../core/store';
import { ACHIEVEMENTS } from '../../core/types';
import type { PanelProps } from './index';

/** 自动刷新档位：0 = 手动 */
const REFRESH_CHOICES: Array<[number, string]> = [
  [0, '手动'],
  [5000, '5 秒'],
  [15000, '15 秒'],
  [30000, '30 秒'],
];

function clockOf(ms: number): string {
  if (!ms) return '—';
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
}

/** 音效统一兜底：未初始化或浏览器不支持 WebAudio 时静默 */
function play(effect: keyof typeof sfx): void {
  try {
    sfx[effect]();
  } catch {
    // 音频不可用不影响面板功能
  }
}

/**
 * 面板内键盘：Esc 断开终端、R 刷新。
 * 终端外框（engine）已在 window 捕获阶段接管这两个键，因此这里【不】注册全局监听，
 * 只在面板子树内部处理按键：外框处理过的事件不会冒泡到这里，不会重复触发；
 * 而输入框/文本域里的 Esc 仍能关闭面板（浏览器不会吞掉 Esc）。
 */
function usePanelKeys(onClose: () => void, onRefresh: () => void) {
  const handlers = useRef({ onClose, onRefresh });
  handlers.current = { onClose, onRefresh };
  return useCallback((event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      // 弹窗（components/Modal）自己也处理 Esc：先让弹窗关闭，避免一次按键连关两层
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

export default function OverviewPanel({
  station,
  vitals,
  onClose,
  onLaunchMiniGame,
  refreshToken,
}: PanelProps) {
  const [refreshMs, setRefreshMs] = useState<number>(POLL.overview);
  const log = useShipLog();

  // 轮询节奏沿用 2D 面板：概览/系统较快，趋势与排行稍慢；
  // 这里统一由面板的自动刷新档位控制，避免用户选择被写死。
  const overview = useQuery(QK.overview, () => api.overview(), { interval: refreshMs });
  const system = useQuery(QK.system, () => api.system(), { interval: refreshMs });
  const series = useQuery(QK.messages, () => api.seriesMessages(30), { interval: refreshMs });
  const apiCalls = useQuery(QK.apiCalls, () => api.statsApiCalls(10), { interval: refreshMs });
  const users = useQuery(QK.activeUsers, () => api.statsActiveUsers(10), { interval: refreshMs });
  const tasks = useQuery(QK.tasks, () => api.tasks(), { interval: refreshMs });
  const services = useQuery(QK.services, () => api.services(), { interval: refreshMs });
  const plugins = useQuery(QK.plugins, () => api.plugins(), { interval: refreshMs });
  const logs = useQuery(QK.logs, () => api.logs(8), { interval: refreshMs });

  const queries = useMemo(
    () => [overview, system, series, apiCalls, users, tasks, services, plugins, logs],
    [overview, system, series, apiCalls, users, tasks, services, plugins, logs],
  );

  const refreshAll = useCallback(() => {
    play('beep');
    void Promise.all(queries.map((query) => query.refetch()));
  }, [queries]);

  // 外框的「刷新」按钮只递增 refreshToken：这里按变化重取，挂载时不重复抓一次
  const tokenRef = useRef(refreshToken);
  useEffect(() => {
    if (tokenRef.current === refreshToken) return;
    tokenRef.current = refreshToken;
    void Promise.all(queries.map((query) => query.refetch()));
  }, [refreshToken, queries]);

  const onPanelKeyDown = usePanelKeys(onClose, refreshAll);

  // 状态条：末次刷新取所有查询里最新的一次；链路状态区分「全部失败 / 部分失败 / 正常」
  const updatedAt = queries.reduce((latest, query) => Math.max(latest, query.updatedAt), 0);
  const broken = queries.filter((query) => query.error === 'no-data').length;
  const busy = queries.some((query) => query.loading);
  const link = broken === 0 ? 'ok' : broken === queries.length ? 'err' : 'warn';
  const linkText =
    broken === 0 ? '链路正常' : broken === queries.length ? '链路中断' : `部分链路中断（${broken}）`;

  const data = overview.data;
  const sys = system.data;
  const seriesData: SeriesPayload | null = series.data;
  const callItems = apiCalls.data?.items || [];
  const userItems: ActiveUser[] = users.data?.items || [];
  const scheduled = tasks.data?.scheduled || [];
  const background = tasks.data?.background || [];
  const serviceItems = services.data?.items || [];
  const pluginItems = plugins.data?.items || [];
  const logItems = logs.data?.items || [];

  const pluginLoaded = pluginItems.filter((item) => item.status === 'loaded').length;
  const maxCall = callItems.reduce((max, item) => Math.max(max, Number(item.count) || 0), 0);
  const serviceUp = serviceItems.filter((item) => item.available).length;
  // 舰内探索进度来自本地存档（探索类数据），业务数据一律不落本地缓存
  const inventory = Object.values(log.inventory).reduce((sum, count) => sum + (count ?? 0), 0);
  const turretBest = log.miniGames.turret?.best;
  const circuitBest = log.miniGames.circuit?.best;

  const launch = (key: 'turret' | 'circuit') => {
    play('beep');
    notify(key === 'turret' ? '火控演习程序接入中…' : '断路器检修程序接入中…', 'info');
    onLaunchMiniGame(key);
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
        <button className="btn-sm" onClick={() => launch('turret')} aria-label="启动火控演习">
          <Icon name="play" size={14} /> 火控演习
        </button>
        <button className="btn-sm" onClick={() => launch('circuit')} aria-label="启动断路器检修">
          <Icon name="settings" size={14} /> 断路器检修
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
        {overview.error === 'no-data' && !data && (
          <div className="bp-alert err" role="alert">
            /api/overview 无数据：可能未登录或后端未就绪，停止显示旧数据。
            <button className="btn-sm" onClick={refreshAll}>
              重试
            </button>
          </div>
        )}

        {/* 统计卡：全部来自 /api/overview 与 /api/plugins */}
        <div className="bp-grid auto">
          <StatCard
            label="已加载插件"
            value={data?.plugins_loaded ?? (pluginItems.length ? pluginLoaded : '—')}
            sub={`共 ${data?.plugins_total ?? pluginItems.length} 个`}
            icon={<Icon name="package" size={18} />}
          />
          <StatCard
            label="机器人"
            value={data?.bot_nickname || '—'}
            sub={data?.bot_user_id ? `QQ ${data.bot_user_id}` : '未连接'}
            icon={<Icon name="bot" size={18} />}
          />
          <StatCard
            label="今日消息"
            value={fmtNum(data?.today_messages)}
            sub={`累计 ${fmtNum(data?.total_messages)}`}
            iconAccent
            icon={<Icon name="log" size={18} />}
          >
            <div className="stat-spark">
              <Sparkline series={seriesData?.series || []} />
            </div>
          </StatCard>
          <StatCard
            label="运行时长"
            value={fmtUptime(data?.uptime_seconds)}
            sub={data?.online ? '在线' : '离线'}
            accent={data?.online ? '#6ee7a8' : '#ff9a9a'}
            icon={<Icon name="cpu" size={18} />}
          />
        </div>

        <div className="bp-grid side">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>舰况读数</h3>
              <span className="bp-card-meta">父级由 /api/system 实测值派生</span>
            </div>
            <div className="bp-vitals">
              {vitals.length === 0 && <div className="bp-empty">暂无舰况数据</div>}
              {vitals.map((vital) => (
                <div className="bp-vital" key={vital.key}>
                  <div className="bp-vital-name">{vital.label}</div>
                  <div className="bp-vital-value">
                    {Number.isFinite(vital.value) ? vital.value.toFixed(0) : '—'}
                    <span className="bp-metric-src">{vital.unit}</span>
                  </div>
                  <div className="bp-vital-src">来源：{vital.source}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>舰员记录</h3>
              <span className="bp-card-meta">本地存档（探索类数据）</span>
            </div>
            <dl className="bp-kv">
              <div className="bp-kv-row">
                <dt>已接入终端</dt>
                <dd>{log.visited.length} / 8</dd>
              </div>
              <div className="bp-kv-row">
                <dt>已解锁成就</dt>
                <dd>
                  {log.achievements.length} / {ACHIEVEMENTS.length}
                </dd>
              </div>
              <div className="bp-kv-row">
                <dt>舰载物资</dt>
                <dd>{inventory} 件</dd>
              </div>
              <div className="bp-kv-row">
                <dt>舰内航程</dt>
                <dd>{Math.round(log.distance)} m</dd>
              </div>
              <div className="bp-kv-row">
                <dt>舰炮演习最好成绩</dt>
                <dd>{turretBest != null ? fmtNum(turretBest) : '—'}</dd>
              </div>
              <div className="bp-kv-row">
                <dt>断路器检修最好成绩</dt>
                <dd>{circuitBest != null ? fmtNum(circuitBest) : '—'}</dd>
              </div>
            </dl>
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
              label="CPU（/api/system cpu_percent）"
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
                ? sys.load_average.join(' / ')
                : '—'}
            </div>
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>消息航迹</h3>
              <span className="bp-card-meta">/api/series/messages 近 30 个采样点</span>
            </div>
            <Sparkline series={seriesData?.series || []} />
            <div className="bp-metric-src">
              {seriesData?.total != null ? `区间合计 ${fmtNum(seriesData.total)} 条` : '接口未返回区间合计'}
            </div>
          </div>
        </div>

        <div className="bp-grid two">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>API 调用排行</h3>
              <span className="bp-card-meta">
                共 {fmtNum(apiCalls.data?.total_calls)} 次 · {apiCalls.data?.unique_actions ?? 0} 种动作
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
              <h3>活跃用户</h3>
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
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="bp-grid two">
          <div className="bp-card">
            <div className="bp-card-head">
              <h3>后台任务</h3>
              <span className="bp-card-meta">
                {scheduled.length} 定时 · {background.length} 进行中
              </span>
            </div>
            {scheduled.length === 0 && background.length === 0 && (
              <div className="bp-empty">当前没有后台任务</div>
            )}
            {scheduled.length > 0 && (
              <table className="model-table">
                <thead>
                  <tr>
                    <th>定时任务</th>
                    <th>下次触发</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduled.map((task, index) => (
                    <tr key={task.task_id || task.id || index}>
                      <td>{task.description || task.name || task.task_id || '—'}</td>
                      <td className="bp-metric-src">
                        {task.next_run || task.trigger_time || task.cron || '—'}
                      </td>
                      <td>
                        <span className="bp-pill">{task.status || '—'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {background.length > 0 && (
              <ul className="bp-list" style={{ marginTop: 10 }}>
                {background.map((task, index) => (
                  <li className="bp-list-row" key={task.task_id || index}>
                    <code className="bp-list-key">{task.task_id || task.kind || '任务'}</code>
                    <span className="bp-list-val">{task.pipeline_key || task.status || '运行中'}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bp-card">
            <div className="bp-card-head">
              <h3>宿主服务</h3>
              <span className="bp-card-meta">
                {serviceUp} / {serviceItems.length} 可用
              </span>
            </div>
            {serviceItems.length === 0 ? (
              <div className="bp-empty">没有可用的服务信息</div>
            ) : (
              <ul className="bp-list">
                {serviceItems.map((item) => (
                  <li className="bp-list-row" key={item.name}>
                    <code className="bp-list-key">{item.name}</code>
                    <span className="bp-metric-src">{item.description || '—'}</span>
                    <span className={`bp-pill ${item.available ? 'ok' : 'err'}`}>
                      {item.available ? '可用' : '未启用'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="bp-card">
          <div className="bp-card-head">
            <h3>通讯记录</h3>
            <span className="bp-card-meta">/api/logs?limit=8 · 共 {fmtNum(logs.data?.total)} 条</span>
          </div>
          {logItems.length === 0 ? (
            <div className="bp-empty">暂无日志</div>
          ) : (
            <ul className="bp-list">
              {logItems
                .slice()
                .reverse()
                .map((item, index) => (
                  <li className="bp-list-row" key={item.id ?? index}>
                    <span className={`bp-pill ${mapTag(item.level)}`}>{item.level || 'INFO'}</span>
                    <span className="bp-list-key">{item.message}</span>
                    <span className="bp-metric-src">{item.time}</span>
                  </li>
                ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
