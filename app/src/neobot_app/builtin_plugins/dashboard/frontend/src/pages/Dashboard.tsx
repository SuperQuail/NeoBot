import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot as BotGlyph, Clock, MessageSquare, Package } from 'lucide-react';
import { api } from '../api/endpoints';
import { useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { fmtUptime, fmtNum, mapTag } from '../utils/format';
import StatCard from '../components/StatCard';
import SystemResourceCard from '../components/SystemResourceCard';
import MessageTrendCard from '../components/MessageTrendCard';
import MonitorList from '../components/MonitorList';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import InlineAlert from '../components/ui/InlineAlert';
import Icon from '../components/Icon';

export default function Dashboard() {
  const overview = useQuery(QK.overview, () => api.overview(), { interval: POLL.overview });
  const system = useQuery(QK.system, () => api.system(), { interval: POLL.system });
  const series = useQuery(QK.messages, () => api.seriesMessages(30), { interval: POLL.messages });
  const bots = useQuery(QK.bots, () => api.bots(), { interval: POLL.bots });
  const plugins = useQuery(QK.plugins, () => api.plugins(), { interval: POLL.plugins });
  const logs = useQuery(QK.logs, () => api.logs(8), { interval: POLL.logs });
  const [view, setView] = useState('trend');
  const d = overview.data || {};
  const botList = Array.isArray(bots.data) ? bots.data : [];
  const pluginItems = plugins.data?.items || [];
  const logItems = [...(logs.data?.items || [])].reverse();
  const pluginLoaded = pluginItems.filter((plugin) => plugin.status === 'loaded').length;
  const notices = Array.isArray(d.notices) ? d.notices : [];
  const queries = [overview, system, series, bots, plugins, logs];

  return (
    <div className="page page--viewport monitor-page dashboard-page" data-view={view}>
      <PageHeader title="运行概览" />
      {queries.some((query) => query.error) && (
        <InlineAlert
          tone="warning"
          title="部分运行数据暂时无法读取"
          actions={
            <Button
              size="sm"
              disabled={queries.some((query) => query.loading)}
              onClick={() =>
                void Promise.all(queries.filter((query) => query.error).map((query) => query.refetch()))
              }
            >
              重试读取
            </Button>
          }
        >
          已保留最近一次数据，稍后会自动重试。
        </InlineAlert>
      )}
      {notices.length > 0 && (
        <details className="monitor-notices">
          <summary>{notices.length} 项配置提示</summary>
          <div className="monitor-notices-body">
            {notices.map((notice, index) => (
              <p key={index}>
                <strong>{notice.text || '配置提示'}</strong>
                {notice.hint && <span>{notice.hint}</span>}
              </p>
            ))}
          </div>
        </details>
      )}
      <section className="monitor-stats" aria-label="核心运行指标">
        <StatCard
          label="今日消息"
          value={fmtNum(d.today_messages)}
          sub={`累计 ${fmtNum(d.total_messages)}`}
          icon={<MessageSquare size={16} />}
        />
        <StatCard
          label="机器人"
          value={d.bot_nickname || '等待连接'}
          sub={d.bot_user_id ? `QQ ${d.bot_user_id}` : '尚未连接 OneBot'}
          icon={<BotGlyph size={16} />}
        />
        <StatCard
          label="已加载插件"
          value={d.plugins_loaded ?? pluginLoaded}
          sub={`共 ${d.plugins_total ?? pluginItems.length} 个插件`}
          icon={<Package size={16} />}
        />
        <StatCard
          label="运行时长"
          value={d.uptime_seconds == null ? '—' : fmtUptime(d.uptime_seconds)}
          sub={d.online ? 'NeoBot 在线' : '等待机器人连接'}
          accent={d.online ? 'var(--ok)' : undefined}
          icon={<Clock size={16} />}
        />
      </section>
      <div className="monitor-mobile-tabs" aria-label="仪表盘视图">
        <button aria-pressed={view === 'trend'} onClick={() => setView('trend')}>
          消息趋势
        </button>
        <button aria-pressed={view === 'resources'} onClick={() => setView('resources')}>
          系统资源
        </button>
        <button aria-pressed={view === 'bots'} onClick={() => setView('bots')}>
          机器人
        </button>
        <button aria-pressed={view === 'logs'} onClick={() => setView('logs')}>
          日志
        </button>
      </div>
      <div className="monitor-grid dashboard-grid">
        <div className="monitor-overview monitor-trend">
          <MessageTrendCard series={series.data?.series} />
        </div>
        <SystemResourceCard
          data={system.data}
          loading={system.loading}
          error={system.error}
          updatedAt={system.updatedAt}
        />
        <section className="card monitor-card monitor-activity monitor-bots">
          <div className="monitor-card-head">
            <h3>
              机器人连接 <span className="monitor-count">{botList.length}</span>
            </h3>
            <Link className="section-link" to="/bots">
              查看详情 <Icon name="chevron" />
            </Link>
          </div>
          <MonitorList
            items={botList}
            label="机器人连接"
            empty="暂无机器人连接"
            rowHeight={52}
            renderItem={(bot) => (
              <>
                <div className="bot-avatar">
                  {bot.avatar_initial || 'N'}
                  {bot.avatar_url && (
                    <img
                      src={bot.avatar_url}
                      alt=""
                      referrerPolicy="no-referrer"
                      onError={(event) => event.currentTarget.remove()}
                    />
                  )}
                </div>
                <div className="monitor-item-main">
                  <strong title={bot.name}>{bot.name}</strong>
                  <span>
                    {bot.platform || 'OneBot'}
                    {bot.user_id ? ` · ${bot.user_id}` : ''}
                  </span>
                </div>
                <div className="monitor-item-side">
                  <span className={'monitor-connection ' + (bot.status === 'on' ? 'online' : '')}>
                    <i />
                    {bot.status === 'on' ? '在线' : '离线'}
                  </span>
                  <span>{bot.latency_ms != null ? `${bot.latency_ms} ms` : '—'}</span>
                </div>
              </>
            )}
          />
        </section>
        <section className="card monitor-card monitor-activity monitor-logs">
          <div className="monitor-card-head">
            <h3>最近日志</h3>
            <Link className="section-link" to="/logs">
              查看日志 <Icon name="chevron" />
            </Link>
          </div>
          <MonitorList
            items={logItems}
            label="最近日志"
            empty="暂无日志"
            rowHeight={36}
            renderItem={(log) => (
              <>
                <span className={'tag ' + mapTag(log.level)}>{log.level}</span>
                <span className="monitor-log-message" title={log.message}>
                  {log.message}
                </span>
                <time className="monitor-log-time">{log.time}</time>
              </>
            )}
          />
        </section>
      </div>
    </div>
  );
}
