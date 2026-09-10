// System.jsx —— 运维熔断 / 服务状态 / 后台任务 / 模型用量
import { useCallback, useState } from 'react';
import { api } from '../api/endpoints.js';
import { useApi } from '../hooks/useApi.js';
import { fmtNum } from '../utils/format.js';
import { toast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';

const HOUR_OPTIONS = [
  [1, '最近 1 小时'],
  [24, '最近 24 小时'],
  [24 * 7, '最近 7 天'],
  [24 * 30, '最近 30 天'],
];

const FREEZE_DURATIONS = [
  ['', '一直冻结（手动解冻）'],
  ['600', '10 分钟后自动解冻'],
  ['1800', '30 分钟后自动解冻'],
  ['3600', '1 小时后自动解冻'],
];

export default function System() {
  const [hours, setHours] = useState(24);
  const [freezeSeconds, setFreezeSeconds] = useState('');
  const [freezeReason, setFreezeReason] = useState('');
  const [freezeBusy, setFreezeBusy] = useState(false);
  const services = useApi(() => api.services(), { interval: 30000 });
  const tasks = useApi(() => api.tasks(), { interval: 15000 });
  const usage = useApi(() => api.statsUsage(hours), { interval: 60000, deps: [hours] });
  const system = useApi(() => api.system(), { interval: 5000 });
  const freeze = useApi(
    async () => {
      const result = await api.freezeStatus();
      return result.ok ? result.data : null;
    },
    { interval: 5000 },
  );

  const frozen = !!freeze.data?.frozen;

  const doFreeze = useCallback(async () => {
    if (freezeBusy) return;
    setFreezeBusy(true);
    try {
      const body = {};
      if (freezeSeconds) body.seconds = Number(freezeSeconds);
      if (freezeReason.trim()) body.reason = freezeReason.trim();
      const result = await api.freeze(body);
      toast(result.ok ? (result.data?.message || '已冻结') : '冻结失败：' + (result.error || ''), result.ok ? 'ok' : 'err');
      freeze.reload();
    } finally {
      setFreezeBusy(false);
    }
  }, [freezeBusy, freezeSeconds, freezeReason, freeze]);

  const doUnfreeze = useCallback(async () => {
    if (freezeBusy) return;
    setFreezeBusy(true);
    try {
      const result = await api.unfreeze();
      toast(result.ok ? (result.data?.message || '已解冻') : '解冻失败：' + (result.error || ''), result.ok ? 'ok' : 'err');
      freeze.reload();
    } finally {
      setFreezeBusy(false);
    }
  }, [freezeBusy, freeze]);

  const serviceItems = services.data?.items || [];
  const scheduled = tasks.data?.scheduled || [];
  const background = tasks.data?.background || [];
  const totals = usage.data?.totals || {};
  const usageItems = usage.data?.items || [];
  const sys = system.data || {};

  return (
    <div className="page">
      <section className={'card' + (frozen ? ' freeze-card' : '')}>
        <div className="card-head">
          <h3>运维熔断</h3>
          <span className={'tag ' + (frozen ? 'err' : 'ok')}>{frozen ? '冻结中' : '运行中'}</span>
          <div className="spacer" />
          <span className="muted small">
            {frozen
              ? '自 ' + (freeze.data?.frozen_at_text || '—') +
                (freeze.data?.remaining_seconds == null
                  ? ' · 需要手动解冻'
                  : ' · 剩余约 ' + freeze.data.remaining_seconds + ' 秒自动解冻')
              : '冻结后立即停止回复与档案自动总结，进程继续运行'}
          </span>
        </div>
        <div className="freeze-body">
          <select
            className="input"
            value={freezeSeconds}
            onChange={(event) => setFreezeSeconds(event.target.value)}
            disabled={frozen}
          >
            {FREEZE_DURATIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <input
            className="input"
            placeholder="冻结原因（可选，会写进日志）"
            value={freezeReason}
            onChange={(event) => setFreezeReason(event.target.value)}
            disabled={frozen}
          />
          <button className="btn danger" disabled={freezeBusy || frozen} onClick={doFreeze}>
            {frozen ? '已冻结' : '冻结 Bot'}
          </button>
          <button className="btn" disabled={freezeBusy || !frozen} onClick={doUnfreeze}>解冻 Bot</button>
        </div>
        {frozen && freeze.data?.reason && (
          <div className="muted small">冻结原因：{freeze.data.reason} · 操作者：{freeze.data.operator || '—'}</div>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h3>进程与资源</h3>
          <span className="muted small">{sys.hostname || ''} · PID {sys.pid || '—'}</span>
        </div>
        <div className="grid stats">
          <div className="stat-card card"><div className="stat-label">CPU</div>
            <div className="stat-value">{sys.cpu_percent != null ? sys.cpu_percent.toFixed(1) + '%' : '—'}</div>
            <div className="stat-sub">{sys.cpu_count || '—'} 核</div></div>
          <div className="stat-card card"><div className="stat-label">内存</div>
            <div className="stat-value">{sys.mem_percent != null ? sys.mem_percent.toFixed(1) + '%' : '—'}</div>
            <div className="stat-sub">{sys.mem_used_mb != null ? Math.round(sys.mem_used_mb) + ' / ' + Math.round(sys.mem_total_mb) + ' MB' : '—'}</div></div>
          <div className="stat-card card"><div className="stat-label">进程内存</div>
            <div className="stat-value">{sys.process_memory_mb != null ? Math.round(sys.process_memory_mb) + ' MB' : '—'}</div>
            <div className="stat-sub">{sys.process_threads || 0} 线程</div></div>
          <div className="stat-card card"><div className="stat-label">磁盘</div>
            <div className="stat-value">{sys.disk_percent != null ? sys.disk_percent.toFixed(1) + '%' : '—'}</div>
            <div className="stat-sub">{sys.disk_used_gb != null ? sys.disk_used_gb.toFixed(1) + ' / ' + sys.disk_total_gb.toFixed(1) + ' GB' : '—'}</div></div>
        </div>
        <div className="sys-meta muted">{sys.os || '—'} · Python {sys.python_version || '—'} · 负载 {Array.isArray(sys.load_average) ? sys.load_average.join(' / ') : '—'}</div>
      </section>

      <div className="grid two-col">
        <section className="card">
          <div className="card-head"><h3>宿主服务</h3><span className="muted small">{serviceItems.length} 项</span></div>
          {serviceItems.length === 0 && <div className="empty muted">没有可用的服务信息</div>}
          <ul className="service-list">
            {serviceItems.map((item) => (
              <li key={item.name} className="service-row">
                <code>{item.name}</code>
                <span className="muted small">{item.description || '—'}</span>
                <span className={'tag ' + (item.available ? 'ok' : 'err')}>{item.available ? '可用' : '未启用'}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="card-head"><h3>后台任务</h3>
            <span className="muted small">{scheduled.length} 定时 · {background.length} 进行中</span></div>
          {scheduled.length === 0 && background.length === 0 && <div className="empty muted">当前没有后台任务</div>}
          {scheduled.length > 0 && (
            <table className="model-table">
              <thead><tr><th>定时任务</th><th>时间</th><th>状态</th></tr></thead>
              <tbody>
                {scheduled.map((item, index) => (
                  <tr key={item.task_id || item.id || index}>
                    <td>{item.description || item.name || item.task_id || '—'}</td>
                    <td className="muted small">{item.next_run || item.trigger_time || item.cron || '—'}</td>
                    <td><span className="tag info">{item.status || '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {background.length > 0 && (
            <ul className="service-list">
              {background.map((item, index) => (
                <li key={index} className="service-row">
                  <code>{item.task_id || item.kind || '任务'}</code>
                  <span className="muted small">{item.pipeline_key || ''} {item.status || ''}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h3>模型用量</h3>
          <select className="input" value={hours} onChange={(event) => setHours(Number(event.target.value))}>
            {HOUR_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <div className="spacer" />
          <span className="muted small">
            调用 {fmtNum(totals.calls || 0)} 次 · 输入 {fmtNum(totals.input_tokens || 0)} · 输出 {fmtNum(totals.output_tokens || 0)} · ¥{(totals.cost_cny || 0).toFixed(4)}
          </span>
        </div>
        {usage.data && usage.data.available === false && (
          <div className="empty muted">用量数据库不可用{usage.data.error ? '：' + usage.data.error : ''}</div>
        )}
        {usageItems.length === 0 && usage.data?.available && <div className="empty muted">该时间段没有用量记录</div>}
        {usageItems.length > 0 && (
          <table className="model-table">
            <thead><tr><th>模块</th><th>调用</th><th>输入 Token</th><th>输出 Token</th><th>费用</th></tr></thead>
            <tbody>
              {usageItems.map((item) => (
                <tr key={item.module}>
                  <td><code>{item.module}</code></td>
                  <td>{fmtNum(item.calls)}</td>
                  <td>{fmtNum(item.input_tokens)}</td>
                  <td>{fmtNum(item.output_tokens)}</td>
                  <td>¥{Number(item.cost_cny || 0).toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
