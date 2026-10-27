import type { SystemInfo } from '../../api/types';
import type { PowerState } from '../../api/endpoints';
import { formatDuration, powerStateLabel } from '../../components/StandbyBanner';

const percent = (value?: number) => (value != null ? value.toFixed(1) + '%' : '—');
const amount = (value?: number, unit = 'MB') =>
  value != null ? Math.round(value).toLocaleString() + ' ' + unit : '—';
export type SystemDetail = { title: string; rows: [string, string][] };

export interface SystemMetric {
  label: string;
  value: string;
  detail: string;
  ratio?: number;
}
export function systemMetrics(sys: SystemInfo): SystemMetric[] {
  return [
    {
      label: 'CPU',
      value: percent(sys.cpu_percent),
      detail: (sys.cpu_count ?? '—') + ' 核',
      ratio: sys.cpu_percent,
    },
    {
      label: '系统内存',
      value: percent(sys.mem_percent),
      detail: amount(sys.mem_used_mb) + ' / ' + amount(sys.mem_total_mb),
      ratio: sys.mem_percent,
    },
    {
      label: '磁盘',
      value: percent(sys.disk_percent),
      detail: amount(sys.disk_used_gb, 'GB') + ' / ' + amount(sys.disk_total_gb, 'GB'),
      ratio: sys.disk_percent,
    },
    {
      label: '进程内存',
      value: amount(sys.process_memory_mb),
      detail: (sys.process_threads ?? '—') + ' 线程',
      ratio:
        sys.mem_total_mb && sys.process_memory_mb != null
          ? (sys.process_memory_mb / sys.mem_total_mb) * 100
          : undefined,
    },
  ];
}
export function hostDetails(sys: SystemInfo, metrics: SystemMetric[]): SystemDetail {
  return {
    title: '主机信息',
    rows: [
      ['主机', sys.hostname || '—'],
      ['进程 PID', String(sys.pid ?? '—')],
      ['操作系统', sys.os || '—'],
      ['Python', sys.python_version || '—'],
      ['平均负载', sys.load_average?.join(' / ') || '—'],
      ...metrics.map((metric): [string, string] => [metric.label, metric.value + ' · ' + metric.detail]),
    ],
  };
}
export function runtimeSummary(powerState: PowerState | null, loading: boolean, error: string | null) {
  const standby = !!powerState?.standby;
  const powerKnown = !!powerState && (typeof powerState.standby === 'boolean' || !!powerState.state);
  const powerAvailable = powerKnown && powerState?.available !== false && powerState?.ok !== false && !error;
  const runtimeLabel =
    loading && !powerState
      ? '正在读取运行状态'
      : powerState?.available === false
        ? '待机服务不可用'
        : !powerAvailable
          ? '运行状态待确认'
          : powerStateLabel(powerState);
  const connectOnebot = !!powerState?.connect_onebot;
  const runtimeDescription = !powerAvailable
    ? '运行状态尚未确认，请刷新后重试。'
    : powerState?.transition
      ? '正在完成清理，完成前不能启动新实例。'
      : standby
        ? (powerState?.operator || '未记录操作者') +
          ' · 已待机 ' +
          formatDuration(powerState?.standby_seconds)
        : powerState?.state === 'running'
          ? '运行时已启动。'
          : '等待运行状态更新。';

  const runtimeIdle =
    standby || !powerAvailable || powerState?.state === 'failed' || !!powerState?.transition;
  return { standby, powerAvailable, runtimeLabel, connectOnebot, runtimeDescription, runtimeIdle };
}
