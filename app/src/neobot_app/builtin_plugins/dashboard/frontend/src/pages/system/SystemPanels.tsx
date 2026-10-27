import { useState } from 'react';
import Icon from '../../components/Icon';
import Modal from '../../components/Modal';
import MonitorList from '../../components/MonitorList';
import SelectControl from '../../components/ui/SelectControl';
import { TaskDetails, TaskStatusRow, describeTask } from '../../components/TaskStatusList';
import { fmtNum } from '../../utils/format';
import type { SystemData } from './useSystemState';
import type { SystemDetail, SystemMetric } from './systemPresentation';

const HOUR_OPTIONS = [
  [1, '最近 1 小时'],
  [24, '最近 24 小时'],
  [168, '最近 7 天'],
  [720, '最近 30 天'],
] as const;

export function SystemResourceStrip({ metrics }: { metrics: SystemMetric[] }) {
  return (
    <section className="system-resource-strip" aria-label="进程与资源">
      {metrics.map((metric) => (
        <article className="system-resource-tile" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <div
            className={
              'system-resource-track' + (metric.ratio != null && metric.ratio >= 85 ? ' is-high' : '')
            }
            role="meter"
            aria-label={metric.label}
            aria-valuenow={metric.ratio == null ? undefined : Math.min(100, Math.max(0, metric.ratio))}
            aria-valuetext={metric.value + '，' + metric.detail}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <i style={{ width: Math.min(100, Math.max(0, metric.ratio ?? 0)) + '%' }} />
          </div>
          <small title={metric.detail}>{metric.detail}</small>
        </article>
      ))}
    </section>
  );
}
export function SystemActivityPanel({
  services,
  tasks,
  setDetail,
  setTaskDetail,
}: {
  services: SystemData['services'];
  tasks: SystemData['tasks'];
  setDetail: (detail: SystemDetail) => void;
  setTaskDetail: (detail: unknown) => void;
}) {
  const [activity, setActivity] = useState<'services' | 'background' | 'scheduled'>('services');
  const serviceItems = services.data?.items || [];
  const scheduled = tasks.data?.scheduled || [];
  const background = tasks.data?.background || [];
  return (
    <section className="card system-panel system-activity-panel" aria-label="服务与任务">
      <div className="system-panel-heading">
        <h3>服务与任务</h3>
        <span>自动更新</span>
      </div>
      <div className="system-activity-tabs" aria-label="状态分类">
        {(
          [
            ['services', '宿主服务', serviceItems.length],
            ['background', '后台任务', background.length],
            ['scheduled', '定时任务', scheduled.length],
          ] as const
        ).map(([key, label, count]) => (
          <button key={key} aria-pressed={activity === key} onClick={() => setActivity(key)}>
            {label}
            <span>{count}</span>
          </button>
        ))}
      </div>
      {activity === 'services' && (
        <MonitorList
          key="services"
          items={serviceItems}
          label="宿主服务"
          loading={services.loading && !services.data}
          empty={
            services.loading
              ? '正在读取服务…'
              : services.error
                ? '服务暂时无法读取，请刷新重试'
                : '没有可用的服务信息'
          }
          rowHeight={60}
          renderItem={(item) => (
            <button
              className="system-detail-row"
              onClick={() =>
                setDetail({
                  title: item.name,
                  rows: [
                    ['说明', item.description || '—'],
                    ['状态', item.available ? '可用' : '未启用'],
                  ],
                })
              }
            >
              <span className="system-row-content">
                <strong>{item.name}</strong>
                <span>{item.description || '未提供说明'}</span>
              </span>
              <span className={'system-row-status' + (item.available ? ' is-available' : '')}>
                <i />
                {item.available ? '可用' : '未启用'}
              </span>
              <Icon name="chevron" size={14} />
            </button>
          )}
        />
      )}
      {activity === 'background' && (
        <MonitorList
          key="background"
          items={background}
          label="后台任务"
          loading={tasks.loading && !tasks.data}
          empty={
            tasks.loading
              ? '正在读取任务…'
              : tasks.data?.background_error || tasks.error
                ? tasks.data?.background_error || '任务暂时无法读取，请刷新重试'
                : '当前没有后台任务'
          }
          rowHeight={60}
          renderItem={(item) => <TaskStatusRow value={item} onSelect={() => setTaskDetail(item)} />}
        />
      )}
      {activity === 'scheduled' && (
        <MonitorList
          key="scheduled"
          items={scheduled}
          label="定时任务"
          loading={tasks.loading && !tasks.data}
          empty={
            tasks.loading
              ? '正在读取任务…'
              : tasks.data?.scheduled_error || tasks.error
                ? tasks.data?.scheduled_error || '任务暂时无法读取，请刷新重试'
                : '当前没有定时任务'
          }
          rowHeight={60}
          renderItem={(item) => (
            <button
              className="system-detail-row"
              onClick={() =>
                setDetail({
                  title: item.description || item.name || item.task_id || '定时任务',
                  rows: [
                    ['任务 ID', item.task_id || item.id || '—'],
                    ['下次运行', item.next_run || item.trigger_time || '—'],
                    ['Cron', item.cron || '—'],
                    ['状态', item.status || '—'],
                  ],
                })
              }
            >
              <span className="system-row-content">
                <strong>{item.description || item.name || item.task_id || '定时任务'}</strong>
                <span>{item.next_run || item.trigger_time || item.cron || '时间未提供'}</span>
              </span>
              <span className="system-row-status">{item.status || '—'}</span>
              <Icon name="chevron" size={14} />
            </button>
          )}
        />
      )}
      <div className="system-panel-note">选择一项查看完整信息</div>
    </section>
  );
}
export function SystemUsagePanel({
  usage,
  hours,
  setHours,
  setDetail,
}: {
  usage: SystemData['usage'];
  hours: number;
  setHours: (hours: number) => void;
  setDetail: (detail: SystemDetail) => void;
}) {
  const totals = usage.data?.totals || {};
  const usageAvailable = !!usage.data && usage.data.available !== false;
  const usageItems = usage.data?.items || [];
  return (
    <section className="card system-panel system-usage-panel" aria-label="系统模型用量">
      <div className="system-panel-heading">
        <h3>模型用量</h3>
        <SelectControl
          label="系统用量时间范围"
          value={String(hours)}
          onValueChange={(value) => setHours(Number(value))}
          options={HOUR_OPTIONS.map(([value, label]) => ({ value: String(value), label }))}
        />
      </div>
      <dl className="system-usage-summary">
        <div>
          <dt>总花费</dt>
          <dd>{usageAvailable && totals.cost_cny != null ? '¥' + totals.cost_cny.toFixed(4) : '—'}</dd>
        </div>
        <div>
          <dt>调用次数</dt>
          <dd>{usageAvailable && totals.calls != null ? fmtNum(totals.calls) : '—'}</dd>
        </div>
        <div>
          <dt>输入 / 输出 Token</dt>
          <dd>
            {usageAvailable && totals.input_tokens != null ? fmtNum(totals.input_tokens) : '—'}
            <span> / </span>
            {usageAvailable && totals.output_tokens != null ? fmtNum(totals.output_tokens) : '—'}
          </dd>
        </div>
      </dl>
      <div className="system-usage-column-labels">
        <span>模块 / Token</span>
        <span>调用 · 花费</span>
      </div>
      <MonitorList
        key={'usage-' + hours}
        items={usageItems}
        label="模块用量"
        loading={usage.loading && !usage.data}
        rowHeight={60}
        empty={
          usage.data?.available === false
            ? '用量数据库不可用' + (usage.data.error ? '：' + usage.data.error : '')
            : usage.loading
              ? '正在读取用量…'
              : usage.error
                ? '用量暂时无法读取，请刷新重试'
                : '该时间段没有用量记录'
        }
        renderItem={(item) => (
          <button
            className="system-detail-row"
            onClick={() =>
              setDetail({
                title: item.module || item.module_name || '模块用量',
                rows: [
                  ['调用次数', fmtNum(item.calls)],
                  ['输入 Token', fmtNum(item.input_tokens)],
                  ['输出 Token', fmtNum(item.output_tokens)],
                  ['花费', '¥' + Number(item.cost_cny || 0).toFixed(6)],
                ],
              })
            }
          >
            <span className="system-row-content">
              <strong>{item.module || item.module_name || '未命名模块'}</strong>
              <span>
                输入 {fmtNum(item.input_tokens)} · 输出 {fmtNum(item.output_tokens)}
              </span>
            </span>
            <span className="system-usage-row-amount">
              <strong>¥{Number(item.cost_cny || 0).toFixed(6)}</strong>
              <span>{fmtNum(item.calls)} 次调用</span>
            </span>
            <Icon name="chevron" size={14} />
          </button>
        )}
      />
      <a className="system-panel-note system-text-button" href="#/usage">
        查看完整用量分析
        <Icon name="chevron" size={14} />
      </a>
    </section>
  );
}
export function SystemDetailDialogs({
  detail,
  setDetail,
  taskDetail,
  setTaskDetail,
}: {
  detail: SystemDetail | null;
  setDetail: (detail: SystemDetail | null) => void;
  taskDetail: unknown;
  setTaskDetail: (detail: unknown) => void;
}) {
  return (
    <>
      <Modal open={!!detail} title={detail?.title} onClose={() => setDetail(null)}>
        <dl className="system-detail-list">
          {detail?.rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </Modal>
      <Modal
        open={taskDetail !== null}
        title={describeTask(taskDetail).title}
        onClose={() => setTaskDetail(null)}
      >
        {taskDetail !== null && <TaskDetails value={taskDetail} />}
      </Modal>
    </>
  );
}
