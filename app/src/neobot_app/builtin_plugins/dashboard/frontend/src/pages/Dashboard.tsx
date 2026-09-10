import { api } from '../api/endpoints';
import { Bot as BotGlyph, Clock, MessageSquare, Package } from 'lucide-react';
import { useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { fmtUptime, fmtNum, fmt1, mapTag } from '../utils/format';
import StatCard from '../components/StatCard';
import ProgressBar from '../components/ProgressBar';
import Sparkline from '../components/Sparkline';

export default function Dashboard() {
  // 轮询节奏沿用旧 app.js:概览/系统 较快,趋势/列表稍慢
  const overview = useQuery(QK.overview, () => api.overview(), { interval: POLL.overview });
  const system = useQuery(QK.system, () => api.system(), { interval: POLL.system });
  const series = useQuery(QK.messages, () => api.seriesMessages(30), { interval: POLL.messages });
  const bots = useQuery(QK.bots, () => api.bots(), { interval: POLL.bots });
  const plugins = useQuery(QK.plugins, () => api.plugins(), { interval: POLL.plugins });
  const logs = useQuery(QK.logs, () => api.logs(8), { interval: POLL.logs });

  const d = overview.data || {};
  const sys = system.data || {};
  const botList = Array.isArray(bots.data) ? bots.data : [];
  const pluginItems = plugins.data?.items || [];
  const logItems = logs.data?.items || [];

  const pluginLoaded = pluginItems.filter((p) => p.status === 'loaded').length;

  return (
    <div className="page">
      {/* Hero */}
      <section className="hero card">
        <div className="hero-grid" />
        <img
          className="hero-bg-character"
          src={import.meta.env.BASE_URL + 'image/background.webp'}
          alt=""
          aria-hidden="true"
          onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
        />
        <div className="hero-inner">
          <h1>欢迎使用 NeoBot</h1>
          <p>
            NeoBot 正在运行。今日已处理 <b>{fmtNum(d.today_messages)}</b> 条消息,共加载{' '}
            <b>{d.plugins_loaded ?? pluginLoaded}</b> 个插件。
          </p>
          <div className="hero-meta">
            <span><i className="pulse" /> 运行状态 <b>{d.online ? '正常' : '离线'}</b></span>
            <span>● 已运行 <b>{fmtUptime(d.uptime_seconds)}</b></span>
            <span>● OneBot <b>{d.app_name && d.app_name !== '—' ? `${d.app_name} ${d.app_version || ''}`.trim() : '—'}</b></span>
            <span>● Python <b>{sys.python_version || '—'}</b></span>
          </div>
        </div>
      </section>

      {/* 统计卡 */}
      <section className="grid stats">
        <StatCard
          label="已加载插件"
          value={d.plugins_loaded ?? pluginLoaded ?? '—'}
          sub={`共 ${d.plugins_total ?? pluginItems.length} 个`}
          icon={
            <Package size={18} strokeWidth={2} aria-hidden="true" />
          }
        />
        <StatCard
          label="机器人状态"
          value={d.bot_nickname || '—'}
          sub={d.bot_user_id ? `QQ ${d.bot_user_id}` : '未连接'}
          icon={
            <BotGlyph size={18} strokeWidth={2} aria-hidden="true" />
          }
        />
        <StatCard
          label="今日消息"
          value={fmtNum(d.today_messages)}
          sub={`累计 ${fmtNum(d.total_messages)}`}
          iconAccent
          icon={
            <MessageSquare size={18} strokeWidth={2} aria-hidden="true" />
          }
        >
          <div className="stat-spark">
            <Sparkline series={series.data?.series || []} />
          </div>
        </StatCard>
        <StatCard
          label="运行时长"
          value={fmtUptime(d.uptime_seconds)}
          sub={d.online ? '在线' : '离线'}
          accent={d.online ? 'var(--ok)' : 'var(--err)'}
          icon={
            <Clock size={18} strokeWidth={2} aria-hidden="true" />
          }
        />
      </section>

      <div className="grid two-col">
        {/* 消息趋势 */}
        <section className="card">
          <div className="card-head">
            <h3>消息趋势</h3>
            <span className="muted">近 30 个采样点</span>
          </div>
          <Sparkline series={series.data?.series || []} />
        </section>

        {/* 系统资源 */}
        <section className="card">
          <div className="card-head">
            <h3>系统资源</h3>
            <span className="muted">{sys.hostname || ''}</span>
          </div>
          <ProgressBar label="CPU" text={sys.cpu_percent != null ? fmt1(sys.cpu_percent, '%') : '—'} pct={sys.cpu_percent} />
          <ProgressBar
            label="内存"
            text={sys.mem_used_mb != null ? `${Math.round(sys.mem_used_mb)} / ${Math.round(sys.mem_total_mb as number)} MB` : '—'}
            pct={sys.mem_percent}
          />
          <ProgressBar
            label="磁盘"
            text={sys.disk_used_gb != null ? `${sys.disk_used_gb.toFixed(1)} / ${(sys.disk_total_gb as number).toFixed(1)} GB` : '—'}
            pct={sys.disk_percent}
          />
          <div className="sys-meta muted">
            {sys.os || '—'} · Python {sys.python_version || '—'}
          </div>
        </section>
      </div>

      <div className="grid two-col">
        {/* 机器人 */}
        <section className="card">
          <div className="card-head">
            <h3>机器人</h3>
          </div>
          {botList.length === 0 && <div className="empty muted">暂无机器人</div>}
          {botList.map((b, i) => (
            <div className="bot-row" key={b.user_id || i}>
              <div className="bot-avatar">
                {b.avatar_initial || 'N'}
                {b.avatar_url && (
                  <img src={b.avatar_url} alt="" referrerPolicy="no-referrer" onError={(e) => e.currentTarget.remove()} />
                )}
              </div>
              <div className="bot-body">
                <div className="bot-name">{b.name}</div>
                <div className="muted small">{b.platform}</div>
              </div>
              <div className="bot-side">
                <span className={'tag ' + (b.status === 'on' ? 'ok' : 'err')}>
                  {b.status === 'on' ? '在线' : '离线'}
                </span>
                {b.latency_ms != null && <span className="muted small">{b.latency_ms} ms</span>}
              </div>
            </div>
          ))}
        </section>

        {/* 最近日志 */}
        <section className="card">
          <div className="card-head">
            <h3>最近日志</h3>
            <span className="muted">{logs.data?.total ?? ''}</span>
          </div>
          {logItems.length === 0 && <div className="empty muted">暂无日志</div>}
          <div className="log-list">
            {logItems
              .slice()
              .reverse()
              .map((it, i) => (
                <div className="log-row" key={it.id ?? i}>
                  <span className={'tag ' + mapTag(it.level)}>{it.level}</span>
                  <span className="log-msg">{it.message}</span>
                  <span className="muted small log-time">{it.time}</span>
                </div>
              ))}
          </div>
        </section>
      </div>
    </div>
  );
}
