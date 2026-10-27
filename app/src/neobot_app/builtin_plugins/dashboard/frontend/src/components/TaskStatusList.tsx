import { ChevronRight } from 'lucide-react';
import EmptyState from './ui/EmptyState';
import InlineAlert from './ui/InlineAlert';

type TaskTone = 'running' | 'waiting' | 'ok' | 'error' | 'neutral';
type TaskState = { label: string; tone: TaskTone };
const STATES: Record<string, TaskState> = {
  running: { label: '进行中', tone: 'running' },
  drawing: { label: '正在绘图', tone: 'running' },
  solving: { label: '正在解题', tone: 'running' },
  pending: { label: '待处理', tone: 'waiting' },
  queued: { label: '排队中', tone: 'waiting' },
  waiting: { label: '等待中', tone: 'waiting' },
  scheduled: { label: '等待触发', tone: 'waiting' },
  completed: { label: '已完成', tone: 'ok' },
  done: { label: '已完成', tone: 'ok' },
  success: { label: '已完成', tone: 'ok' },
  failed: { label: '失败', tone: 'error' },
  error: { label: '异常', tone: 'error' },
  timeout: { label: '已超时', tone: 'error' },
  cancelled: { label: '已取消', tone: 'neutral' },
  canceled: { label: '已取消', tone: 'neutral' },
  idle: { label: '当前空闲', tone: 'neutral' },
};
const SOURCE_NAMES: Record<string, string> = {
  drawing: '绘图',
  problem_solver: '解题',
  solver: '解题',
  scheduled_task: '定时任务',
  notification: '通知服务',
  memory_summary: '记忆总结',
  archive_summary: '档案总结',
  session_tools: '会话工具',
};
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '');
const number = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : undefined);
const duration = (value: number) =>
  value < 60
    ? `${value.toLocaleString()} 秒`
    : `${Math.floor(value / 60).toLocaleString()} 分 ${Math.round(value % 60)} 秒`;
const pretty = (value: unknown) => JSON.stringify(value, null, 2) ?? String(value);

export function describeTask(value: unknown, fallback = '后台任务') {
  const item = record(value);
  const status = text(item.status) || text(item.state);
  const error = text(item.error);
  const state: TaskState =
    STATES[status] ||
    (error ? { label: '异常', tone: 'error' } : { label: status || '状态未提供', tone: 'neutral' });
  const title =
    text(item.name) ||
    text(item.description) ||
    text(item.task_id) ||
    text(item.id) ||
    SOURCE_NAMES[text(item.kind)] ||
    text(item.kind) ||
    fallback;
  const pending = number(item.pending_count) ?? number(item.pending);
  const subtitle =
    error ||
    text(item.question) ||
    (pending != null && pending >= 0 ? `待处理 ${pending.toLocaleString()}` : '') ||
    text(item.pipeline_key) ||
    (text(item.kind) ? SOURCE_NAMES[text(item.kind)] || text(item.kind) : '');
  const fields: [string, string][] = [];
  for (const [key, label] of [
    ['task_id', '任务 ID'],
    ['id', 'ID'],
    ['kind', '类型'],
    ['pipeline_key', '聊天流'],
    ['model', '模型'],
    ['next_run', '下次运行'],
    ['trigger_time', '触发时间'],
    ['cron', 'Cron'],
  ] as const) {
    if (text(item[key])) fields.push([label, text(item[key])]);
  }
  if (pending != null && pending >= 0) fields.push(['待处理', pending.toLocaleString()]);
  for (const [key, label] of [
    ['queue_position', '队列位置'],
    ['total', '总数'],
    ['completed', '已完成数量'],
  ] as const) {
    const count = number(item[key]);
    if (count != null && count >= 0) fields.push([label, count.toLocaleString()]);
  }
  const elapsed = number(item.elapsed_seconds);
  if (elapsed != null && elapsed >= 0) fields.push(['已运行', duration(elapsed)]);
  const progress = record(item.progress);
  const completed = number(progress.completed) ?? number(progress.current) ?? number(item.completed);
  const total = number(progress.total) ?? number(item.total);
  const explicitPercent = number(item.progress_percent);
  const percent =
    explicitPercent != null && explicitPercent >= 0 && explicitPercent <= 100
      ? explicitPercent
      : completed != null && total != null && total > 0 && completed >= 0 && completed <= total
        ? (completed / total) * 100
        : undefined;
  const progressLabel =
    completed != null && total != null && percent != null
      ? `${completed} / ${total}`
      : percent != null
        ? `${Math.round(percent)}%`
        : '';
  return {
    title,
    subtitle,
    state,
    fields,
    error,
    question: text(item.question),
    description: text(item.description),
    percent,
    progressLabel,
  };
}

function TaskBadge({ state }: { state: TaskState }) {
  return (
    <span className={`task-state task-state--${state.tone}`}>
      <i aria-hidden="true" />
      {state.label}
    </span>
  );
}

function RawTaskData({ value }: { value: unknown }) {
  return (
    <details className="task-raw-data">
      <summary>原始数据</summary>
      <pre>{pretty(value)}</pre>
    </details>
  );
}

export function TaskStatusRow({ value, onSelect }: { value: unknown; onSelect: () => void }) {
  const task = describeTask(value);
  return (
    <button className="system-detail-row task-status-row" onClick={onSelect}>
      <span className="system-row-content">
        <strong>{task.title}</strong>
        {task.subtitle && <span>{task.subtitle}</span>}
      </span>
      <TaskBadge state={task.state} />
      <ChevronRight size={14} />
    </button>
  );
}

export function TaskDetails({
  value,
  name = '后台任务',
  showTitle = false,
  raw = true,
}: {
  value: unknown;
  name?: string;
  showTitle?: boolean;
  raw?: boolean;
}) {
  const task = describeTask(value, name);
  return (
    <div className="task-details">
      <div className="task-details-heading">
        {showTitle && <h4>{task.title}</h4>}
        <TaskBadge state={task.state} />
      </div>
      {task.description && task.description !== task.title && (
        <p className="task-description">{task.description}</p>
      )}
      {task.question && <p className="task-description">{task.question}</p>}
      {task.error && (
        <InlineAlert tone="error" title="任务异常">
          {task.error}
        </InlineAlert>
      )}
      {task.fields.length > 0 && (
        <dl className="task-facts">
          {task.fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {task.percent != null && (
        <div className="task-progress">
          <div>
            <span>任务进度</span>
            <strong>{task.progressLabel}</strong>
          </div>
          <progress aria-label="任务进度" value={task.percent} max={100} />
        </div>
      )}
      {raw && <RawTaskData value={value} />}
    </div>
  );
}

/** 直接投影各任务管理器的实际字段；无法识别的数据仍可完整展开。 */
export default function TaskStatusList({ snapshot }: { snapshot: Record<string, unknown> }) {
  const groups = [
    {
      name: '绘图任务',
      active: snapshot.active_task,
      recent: snapshot.recent_tasks,
      activeFlag: snapshot.has_active_task,
    },
    {
      name: '解题任务',
      active: snapshot.solver_active_task,
      recent: snapshot.solver_recent_tasks,
      activeFlag: snapshot.solver_has_active_task,
    },
  ];
  const metrics: [string, string][] = [];
  for (const [key, label] of [
    ['background_notifications_pending', '待处理通知'],
    ['scheduled_task_notifications_pending', '待发送提醒'],
  ] as const) {
    const count = number(snapshot[key]);
    if (count != null && count >= 0) metrics.push([label, `${count.toLocaleString()} 条`]);
  }
  const cooldown = number(snapshot.cooldown_remaining_seconds);
  if (cooldown != null && cooldown > 0) metrics.push(['绘图冷却', duration(cooldown)]);
  const sources = Object.entries(record(snapshot.background_notifications_by_source)).filter(
    ([, value]) => number(value) != null,
  );
  const errors = Object.entries(snapshot).filter(([key, value]) => key.endsWith('_error') && text(value));
  const knownKeys = new Set([
    'active_task',
    'recent_tasks',
    'has_active_task',
    'solver_active_task',
    'solver_recent_tasks',
    'solver_has_active_task',
    'background_notifications_pending',
    'scheduled_task_notifications_pending',
    'background_notifications_by_source',
    'cooldown_remaining_seconds',
  ]);
  const namedTasks = Object.entries(snapshot).filter(([key, value]) => {
    if (knownKeys.has(key) || key.endsWith('_error')) return false;
    const item = record(value);
    return [
      'status',
      'state',
      'error',
      'pending',
      'pending_count',
      'total',
      'completed',
      'progress_percent',
      'progress',
    ].some((field) => item[field] != null);
  });
  const hasGroups = groups.some(
    (group) => group.active != null || Array.isArray(group.recent) || typeof group.activeFlag === 'boolean',
  );
  return (
    <div className="task-status-list">
      {metrics.length > 0 && (
        <dl className="task-queue-summary">
          {metrics.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {sources.length > 0 && (
        <div className="task-notification-sources">
          <span>通知来源</span>
          {sources.map(([source, count]) => (
            <span key={source}>
              {SOURCE_NAMES[source] || source}
              <strong>{String(count)}</strong>
            </span>
          ))}
        </div>
      )}
      {errors.map(([key, value]) => (
        <InlineAlert
          key={key}
          tone="error"
          title={`${SOURCE_NAMES[key.slice(0, -6)] || key.slice(0, -6)}状态读取失败`}
        >
          {text(value)}
        </InlineAlert>
      ))}
      {groups.map((group) => {
        const recent = Array.isArray(group.recent) ? group.recent : [];
        if (group.active == null && !Array.isArray(group.recent) && typeof group.activeFlag !== 'boolean')
          return null;
        return (
          <section className="task-group" key={group.name} aria-label={group.name}>
            <div className="task-group-heading">
              <h3>{group.name}</h3>
              {group.active == null && typeof group.activeFlag === 'boolean' && (
                <span>{group.activeFlag ? '有进行中的任务，详情未提供' : '当前没有进行中的任务'}</span>
              )}
            </div>
            {group.active != null && (
              <TaskDetails value={group.active} name={group.name} showTitle raw={false} />
            )}
            {recent.length > 0 && (
              <div className="task-recent">
                <h4>
                  最近任务 <span>{recent.length}</span>
                </h4>
                {recent.map((task, index) => (
                  <TaskDetails key={index} value={task} name={group.name} showTitle raw={false} />
                ))}
              </div>
            )}
          </section>
        );
      })}
      {namedTasks.map(([name, value]) => (
        <section className="task-group" key={name} aria-label={SOURCE_NAMES[name] || name}>
          <TaskDetails value={value} name={SOURCE_NAMES[name] || name} showTitle raw={false} />
        </section>
      ))}
      {!hasGroups && metrics.length === 0 && errors.length === 0 && namedTasks.length === 0 && (
        <EmptyState compact>暂未提供可识别的任务摘要</EmptyState>
      )}
      <RawTaskData value={snapshot} />
    </div>
  );
}
