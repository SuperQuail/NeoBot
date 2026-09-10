// Bots.jsx —— 机器人详情(移植自旧 botsPage.js)
// 头部信息 + 延迟折线 + 消息趋势折线 + API 调用排行 + 活跃用户排行,带轮询
import { api } from '../api/endpoints.js';
import { useApi } from '../hooks/useApi.js';
import { fmtUptime, fmtNum, fmtRelTime } from '../utils/format.js';
import LineChart from '../components/LineChart.jsx';

function Bar({ rank, label, count, pct }) {
  return (
    <li className="rank-row">
      <span className="rank">{rank}</span>
      <div className="rank-track">
        <div className="rank-fill" style={{ width: pct.toFixed(1) + '%' }} />
        <div className="rank-label">{label}</div>
      </div>
      <span className="rank-count">{fmtNum(count)}</span>
    </li>
  );
}

export default function Bots() {
  // 轮询节奏沿用旧 botsPage.js
  const detail = useApi(() => api.botDetail(), { interval: 10000 });
  const latency = useApi(() => api.seriesLatency(), { interval: 10000 });
  const messages = useApi(() => api.seriesMessages(30), { interval: 60000 });
  const apiCalls = useApi(() => api.statsApiCalls(10), { interval: 10000 });
  const users = useApi(() => api.statsActiveUsers(10), { interval: 60000 });

  const d = detail.data || {};
  const lat = latency.data || {};
  const latSeries = lat.series || [];
  const msgSeries = messages.data?.series || [];
  const calls = apiCalls.data || {};
  const callItems = calls.items || [];
  const usr = users.data || {};
  const userItems = usr.items || [];

  const msgTotal = msgSeries.reduce((s, p) => s + (p.count || 0), 0);
  const msgPeak = msgSeries.reduce((m, p) => Math.max(m, p.count || 0), 0);
  const maxCall = callItems[0]?.count || 1;

  return (
    <div className="page">
      {/* 头部 */}
      <section className="card bot-detail-head">
        {d.avatar_url && (
          <img className="bd-avatar" src={d.avatar_url} alt="" referrerPolicy="no-referrer" onError={(e) => e.currentTarget.remove()} />
        )}
        <div className="bd-main">
          <div className="bd-name-row">
            <span className="bd-name">{d.nickname || '未连接'}</span>
            <span className={'status-pill ' + (d.online ? 'on' : 'off')}>
              <span className="dot-mini" />
              {d.online ? '在线' : '离线'}
            </span>
          </div>
          <div className="bd-grid">
            <div>
              <span className="hm-label">QQ</span>
              <span className="hm-value">{d.user_id || '—'}</span>
            </div>
            <div>
              <span className="hm-label">协议端</span>
              <span className="hm-value">{d.app_name ? `${d.app_name} ${d.app_version || ''}`.trim() : '—'}</span>
            </div>
            <div>
              <span className="hm-label">延迟</span>
              <span className="hm-value">{d.latency_ms != null ? `${Math.round(d.latency_ms)} ms` : '—'}</span>
            </div>
            <div>
              <span className="hm-label">运行时长</span>
              <span className="hm-value">{fmtUptime(d.uptime_seconds)}</span>
            </div>
            <div>
              <span className="hm-label">今日消息</span>
              <span className="hm-value">{fmtNum(d.today_messages)}</span>
            </div>
            <div>
              <span className="hm-label">累计消息</span>
              <span className="hm-value">{fmtNum(d.total_messages)}</span>
            </div>
          </div>
        </div>
      </section>

      <div className="grid two-col">
        {/* 延迟 */}
        <section className="card">
          <div className="card-head">
            <h3>网络延迟</h3>
            <span className="muted small">
              {latSeries.length
                ? `当前 ${lat.current_ms != null ? Math.round(lat.current_ms) + ' ms' : '—'} · 平均 ${
                    lat.avg_ms != null ? lat.avg_ms + ' ms' : '—'
                  } · 成功率 ${lat.success_rate != null ? lat.success_rate + '%' : '—'}`
                : '等待首次采样…'}
            </span>
          </div>
          <LineChart values={latSeries.map((p) => p.ms)} fmtTick={(v) => `${Math.round(v)}ms`} />
        </section>

        {/* 消息趋势 */}
        <section className="card">
          <div className="card-head">
            <h3>消息趋势</h3>
            <span className="muted small">
              {msgSeries.length ? `共 ${fmtNum(msgTotal)} 条 · 峰值 ${fmtNum(msgPeak)}/天` : '尚无历史数据'}
            </span>
          </div>
          <LineChart values={msgSeries.map((p) => p.count)} fmtTick={(v) => fmtNum(Math.round(v))} />
        </section>
      </div>

      <div className="grid two-col">
        {/* API 调用排行 */}
        <section className="card">
          <div className="card-head">
            <h3>API 调用排行</h3>
            <span className="muted small">
              共 {fmtNum(calls.total_calls || 0)} 次 · {calls.unique_actions || 0} 种
            </span>
          </div>
          {callItems.length === 0 ? (
            <div className="empty muted">尚未捕获到 API 调用</div>
          ) : (
            <ul className="rank-list">
              {callItems.map((it, i) => (
                <Bar key={it.action} rank={i + 1} label={it.action} count={it.count} pct={(it.count / maxCall) * 100} />
              ))}
            </ul>
          )}
        </section>

        {/* 活跃用户 */}
        <section className="card">
          <div className="card-head">
            <h3>活跃用户</h3>
            <span className="muted small">追踪 {usr.tracked_users || 0} 人</span>
          </div>
          {userItems.length === 0 ? (
            <div className="empty muted">尚无消息记录</div>
          ) : (
            <ul className="user-list">
              {userItems.map((u, i) => (
                <li className="user-row" key={u.user_id}>
                  <span className="rank">{i + 1}</span>
                  <img
                    className="user-avatar"
                    src={`https://q1.qlogo.cn/g?b=qq&nk=${u.user_id}&s=100`}
                    alt=""
                    referrerPolicy="no-referrer"
                    onError={(e) => (e.target.style.visibility = 'hidden')}
                  />
                  <div className="user-body">
                    <div className="user-name">{u.nickname || `用户${u.user_id}`}</div>
                    <div className="muted small">QQ {u.user_id}</div>
                  </div>
                  <span className="user-count">{fmtNum(u.count)} 条</span>
                  <span className="muted small user-last">{fmtRelTime(u.last_seen)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
