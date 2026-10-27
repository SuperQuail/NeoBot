import { Cpu, HardDrive, MemoryStick, Server } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { SystemInfo } from '../api/types';
import Icon from './Icon';

interface SystemResourceCardProps {
  data: SystemInfo | null;
  loading?: boolean;
  error?: string | null;
  updatedAt?: number;
}

function amount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function percentage(value: unknown, used?: number | null, total?: number | null): number | null {
  if (value != null) {
    const current = amount(value);
    return current != null && current <= 100 ? current : null;
  }
  return used != null && total != null && total > 0 && used <= total ? (used / total) * 100 : null;
}

function percentLabel(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}%`;
}

function capacity(value: number | null, divisor: number): string {
  return value == null ? '—' : (value / divisor).toFixed(1);
}

function totalCapacity(value: unknown): number | null {
  const current = amount(value);
  return current != null && current > 0 ? current : null;
}

function CapacityUsage({
  kind,
  value,
  used,
  total,
  pending,
}: {
  kind: 'memory' | 'disk';
  value: number | null;
  used: number | null;
  total: number | null;
  pending: boolean;
}) {
  const memory = kind === 'memory';
  const label = memory ? '内存' : '磁盘';
  const divisor = memory && Math.max(used ?? 0, total ?? 0) >= 1024 ? 1024 : 1;
  const unit = memory && divisor === 1 ? 'MB' : 'GB';
  const Glyph = memory ? MemoryStick : HardDrive;
  const high = value != null && value >= 90;

  return (
    <section className={`resource-capacity resource-capacity--${kind}`} aria-label={label}>
      <div className="resource-capacity-heading">
        <h4>
          <Glyph size={15} aria-hidden="true" />
          {label}
        </h4>
        <strong className={high ? 'resource-usage-high' : undefined}>{percentLabel(value)}</strong>
      </div>
      <div
        className={`resource-capacity-track${value == null ? ' is-unavailable' : ''}${high ? ' is-high' : ''}`}
        role={value == null ? undefined : 'meter'}
        aria-label={value == null ? undefined : `${label}使用率`}
        aria-valuemin={value == null ? undefined : 0}
        aria-valuemax={value == null ? undefined : 100}
        aria-valuenow={value ?? undefined}
        aria-valuetext={value == null ? undefined : percentLabel(value)}
      >
        {value != null && <span style={{ width: `${value}%` }} />}
      </div>
      <div className="resource-capacity-values">
        <span>
          已用 <b>{capacity(used, divisor)}</b> / {capacity(total, divisor)} {unit}
        </span>
        {value == null && <span>{pending ? '读取中' : '未上报占用'}</span>}
      </div>
    </section>
  );
}

export default function SystemResourceCard({
  data,
  loading = false,
  error = null,
  updatedAt = 0,
}: SystemResourceCardProps) {
  const cpu = percentage(data?.cpu_percent);
  const memoryUsed = amount(data?.mem_used_mb);
  const memoryTotal = totalCapacity(data?.mem_total_mb);
  const diskUsed = amount(data?.disk_used_gb);
  const diskTotal = totalCapacity(data?.disk_total_gb);
  const memory = percentage(data?.mem_percent, memoryUsed, memoryTotal);
  const disk = percentage(data?.disk_percent, diskUsed, diskTotal);
  const cores = amount(data?.cpu_count);
  const hasReadings = [cpu, memory, disk, memoryUsed, diskUsed].some((value) => value != null);
  const incomplete = [cpu, memory, disk].some((value) => value == null);
  const pending = loading && !hasReadings;
  const timestamp = new Date(updatedAt);
  const hasTimestamp = updatedAt > 0 && Number.isFinite(timestamp.getTime());
  const status = error
    ? hasReadings
      ? '更新失败'
      : '读取失败'
    : pending
      ? '读取中…'
      : !hasReadings
        ? '暂无采样'
        : incomplete
          ? '部分数据缺失'
          : '实时快照';

  return (
    <section
      className="card monitor-card monitor-overview monitor-resources system-resource-card"
      aria-label="系统资源"
    >
      <div className="monitor-card-head">
        <div className="resource-card-title">
          <h3>系统资源</h3>
          <span className={`resource-read-state${error ? ' is-error' : ''}`}>{status}</span>
        </div>
        <Link className="section-link" to="/system">
          系统状态 <Icon name="chevron" />
        </Link>
      </div>
      {error && (
        <p className="resource-read-error" role="status" title={error}>
          {hasReadings ? '刷新失败，以下保留最近一次数据。' : '暂时无法读取资源，请刷新重试。'}
        </p>
      )}
      <div className="resource-layout">
        <section className="resource-cpu" aria-label="CPU">
          <div
            className={`resource-cpu-gauge${cpu == null ? ' is-unavailable' : ''}${cpu != null && cpu >= 90 ? ' is-high' : ''}`}
            role={cpu == null ? undefined : 'meter'}
            aria-label={cpu == null ? undefined : 'CPU 使用率'}
            aria-valuemin={cpu == null ? undefined : 0}
            aria-valuemax={cpu == null ? undefined : 100}
            aria-valuenow={cpu ?? undefined}
            aria-valuetext={cpu == null ? undefined : percentLabel(cpu)}
          >
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle className="resource-gauge-track" cx="60" cy="60" r="52" />
              {cpu != null && (
                <circle
                  className="resource-gauge-fill"
                  cx="60"
                  cy="60"
                  r="52"
                  pathLength="100"
                  strokeDasharray={`${cpu} ${100 - cpu}`}
                  transform="rotate(-90 60 60)"
                />
              )}
            </svg>
            <div className="resource-cpu-value">
              <Cpu size={16} aria-hidden="true" />
              <strong>
                {cpu == null ? '—' : cpu.toFixed(1)}
                {cpu != null && <small>%</small>}
              </strong>
              <span>CPU 使用率</span>
            </div>
          </div>
          <div className="resource-cpu-context">
            <span>{cores != null && cores > 0 ? `${cores} 个逻辑核心` : '核心数未上报'}</span>
            {cpu == null && <span>{pending ? '等待采样' : '未上报使用率'}</span>}
            {cpu != null && cpu >= 90 && <span className="resource-usage-high">当前负载较高</span>}
          </div>
        </section>
        <div className="resource-capacities">
          <CapacityUsage
            kind="memory"
            value={memory}
            used={memoryUsed}
            total={memoryTotal}
            pending={pending}
          />
          <CapacityUsage kind="disk" value={disk} used={diskUsed} total={diskTotal} pending={pending} />
        </div>
      </div>
      <div className="resource-host">
        <Server size={15} aria-hidden="true" />
        <div className="resource-host-details">
          <strong title={data?.hostname}>{data?.hostname || '主机名未上报'}</strong>
          <span title={data?.os}>{data?.os || '系统信息未上报'}</span>
        </div>
        <div className="resource-host-runtime">
          <span>Python {data?.python_version || '—'}</span>
          {hasTimestamp && (
            <time dateTime={timestamp.toISOString()} title={`最近更新：${timestamp.toLocaleString('zh-CN')}`}>
              更新于 {timestamp.toLocaleTimeString('zh-CN', { hour12: false })}
            </time>
          )}
        </div>
      </div>
    </section>
  );
}
