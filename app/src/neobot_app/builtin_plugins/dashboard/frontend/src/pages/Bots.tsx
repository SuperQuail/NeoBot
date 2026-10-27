import { useState } from 'react';
import { api } from '../api/endpoints';
import type { ActiveUser } from '../api/types';
import { useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { fmtUptime, fmtNum, fmtRelTime } from '../utils/format';
import LineChart from '../components/LineChart';
import MessageTrendCard from '../components/MessageTrendCard';
import MonitorList from '../components/MonitorList';
import PageHeader from '../components/ui/PageHeader';
import Button from '../components/ui/Button';
import InlineAlert from '../components/ui/InlineAlert';

export default function Bots() {
  const detail = useQuery(QK.botDetail, () => api.botDetail(), { interval: POLL.botDetail });
  const latency = useQuery(QK.latency, () => api.seriesLatency(), { interval: POLL.botDetail });
  const messages = useQuery(QK.messages, () => api.seriesMessages(30), { interval: POLL.messages });
  const apiCalls = useQuery(QK.apiCalls, () => api.statsApiCalls(10), { interval: POLL.apiCalls });
  const users = useQuery(QK.activeUsers, () => api.statsActiveUsers(10), { interval: POLL.activeUsers });
  const [view, setView] = useState('trend');
  const d = detail.data || {};
  const lat = latency.data || {};
  const latSeries = lat.series || [];
  const calls = apiCalls.data || {};
  const callItems = calls.items || [];
  const usr = users.data || {};
  const userItems: ActiveUser[] = usr.items || [];
  const maxCall = Math.max(1, ...callItems.map((item) => item.count || 0));
  const queries = [detail, latency, messages, apiCalls, users];

  return (
    <div className="page page--viewport monitor-page bots-page" data-view={view}>
      <PageHeader title="机器人" />
      {queries.some((query) => query.error) && (
        <InlineAlert
          tone="warning"
          title="部分机器人数据暂时无法读取"
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
      <section className="card monitor-identity" aria-label="机器人信息">
        <div className="monitor-profile">
          <div className="bot-avatar">
            N
            {d.avatar_url && (
              <img
                src={d.avatar_url}
                alt=""
                referrerPolicy="no-referrer"
                onError={(event) => event.currentTarget.remove()}
              />
            )}
          </div>
          <div>
            <h2 title={d.nickname}>{d.nickname || '未连接'}</h2>
            <span>QQ {d.user_id || '—'}</span>
          </div>
          <span className={'monitor-connection ' + (d.online ? 'online' : '')}>
            <i />
            {d.online ? '在线' : '离线'}
          </span>
        </div>
        <dl className="monitor-identity-stats">
          <div>
            <dt>协议端</dt>
            <dd title={d.app_name ? `${d.app_name} ${d.app_version || ''}` : undefined}>
              {d.app_name ? `${d.app_name} ${d.app_version || ''}`.trim() : '—'}
            </dd>
          </div>
          <div>
            <dt>运行时长</dt>
            <dd>{d.uptime_seconds == null ? '—' : fmtUptime(d.uptime_seconds)}</dd>
          </div>
          <div>
            <dt>今日消息</dt>
            <dd>{fmtNum(d.today_messages)}</dd>
          </div>
          <div>
            <dt>累计消息</dt>
            <dd>{fmtNum(d.total_messages)}</dd>
          </div>
        </dl>
      </section>
      <div className="monitor-mobile-tabs" aria-label="机器人视图">
        <button aria-pressed={view === 'trend'} onClick={() => setView('trend')}>
          消息趋势
        </button>
        <button aria-pressed={view === 'latency'} onClick={() => setView('latency')}>
          网络延迟
        </button>
        <button aria-pressed={view === 'api'} onClick={() => setView('api')}>
          接口调用
        </button>
        <button aria-pressed={view === 'users'} onClick={() => setView('users')}>
          活跃用户
        </button>
      </div>
      <div className="monitor-grid bots-grid">
        <div className="monitor-overview monitor-trend">
          <MessageTrendCard series={messages.data?.series} />
        </div>
        <section className="card monitor-card monitor-overview monitor-latency">
          <div className="monitor-card-head">
            <h3>网络延迟</h3>
            <span className="muted small">
              {lat.success_rate != null ? `成功率 ${lat.success_rate}%` : '等待采样'}
            </span>
          </div>
          <div className="trend-metrics">
            <div className="trend-primary">
              <strong>{lat.current_ms != null ? Math.round(lat.current_ms) : '—'}</strong>
              <span>ms 当前</span>
            </div>
            <dl>
              <div>
                <dt>平均延迟</dt>
                <dd>{lat.avg_ms != null ? `${lat.avg_ms} ms` : '—'}</dd>
              </div>
            </dl>
          </div>
          <div className="monitor-chart">
            <LineChart
              fit
              name="网络延迟"
              values={latSeries.map((point) => point.ms ?? null)}
              labels={latSeries.map((point, index) =>
                point.ts != null && Number.isFinite(point.ts)
                  ? new Date(point.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })
                  : point.at || `采样 ${index + 1}`,
              )}
              fmtTick={(value) => `${Math.round(value)}`}
              fmtValue={(value) => `${Math.round(value)} ms`}
            />
          </div>
          <div className="trend-caption">
            <span className="chart-legend">
              <i />
              连接延迟
            </span>
            <span>{latSeries.length ? `${latSeries.length} 个采样点` : '等待首次采样'}</span>
          </div>
        </section>
        <section className="card monitor-card monitor-activity monitor-api">
          <div className="monitor-card-head">
            <h3>API 调用排行</h3>
            <span className="muted small">
              {fmtNum(calls.total_calls || 0)} 次 · {calls.unique_actions || 0} 种
            </span>
          </div>
          <MonitorList
            items={callItems}
            label="API 调用排行"
            empty="尚未捕获到 API 调用"
            rowHeight={36}
            renderItem={(item, index) => (
              <>
                <span className="monitor-rank">{String(index + 1).padStart(2, '0')}</span>
                <div className="monitor-call">
                  <span title={item.action}>{item.action}</span>
                  <div>
                    <i style={{ width: `${((item.count || 0) / maxCall) * 100}%` }} />
                  </div>
                </div>
                <strong className="monitor-rank-count">{fmtNum(item.count)}</strong>
              </>
            )}
          />
        </section>
        <section className="card monitor-card monitor-activity monitor-users">
          <div className="monitor-card-head">
            <h3>活跃用户</h3>
            <span className="muted small">追踪 {fmtNum(usr.tracked_users || 0)} 人</span>
          </div>
          <MonitorList
            items={userItems}
            label="活跃用户"
            empty="尚无消息记录"
            rowHeight={46}
            renderItem={(user, index) => (
              <>
                <span className="monitor-rank">{String(index + 1).padStart(2, '0')}</span>
                <div className="monitor-user-avatar">
                  <img
                    src={`https://q1.qlogo.cn/g?b=qq&nk=${user.user_id}&s=100`}
                    alt=""
                    referrerPolicy="no-referrer"
                    onError={(event) => {
                      event.currentTarget.style.visibility = 'hidden';
                    }}
                  />
                </div>
                <div className="monitor-item-main">
                  <strong title={user.nickname}>{user.nickname || `用户${user.user_id}`}</strong>
                  <span>QQ {user.user_id}</span>
                </div>
                <div className="monitor-item-side">
                  <strong>{fmtNum(user.count)} 条</strong>
                  <span>{fmtRelTime(user.last_seen)}</span>
                </div>
              </>
            )}
          />
        </section>
      </div>
    </div>
  );
}
