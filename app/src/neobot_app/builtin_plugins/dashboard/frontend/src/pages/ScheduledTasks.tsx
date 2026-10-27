// pages/ScheduledTasks.tsx —— 定时任务管理：查看 / 新建 / 编辑 / 启停 / 删除
// 读走 ScheduledTaskManager 的投影；写全部转发给 reminder skill（与主 Agent 同一套校验）。
import { useEffect, useMemo, useState } from 'react';
import Icon from '../components/Icon';
import Modal, { ModalActions } from '../components/Modal';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import InlineAlert from '../components/ui/InlineAlert';
import { notify } from '../notifications/infoBar';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ScheduledTaskActionBody, ScheduledTaskItem } from '../api/types';
import PageHeader from '../components/ui/PageHeader';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import { confirmAction } from '../components/ui/ConfirmDialog';

const RECURRENCE_OPTIONS = [
  { value: 'once', label: '一次' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'yearly', label: '每年' },
];
const COMPACT_TASKS_QUERY = '(max-width: 740px)';

interface BindingDraft {
  kind: 'group' | 'private';
  id: string;
}

interface TaskDraft {
  task_uuid: string;
  title: string;
  detail: string;
  recurrence: string;
  start_at: string;
  end_at: string;
  one_shot_notification: boolean;
  bindings: BindingDraft[];
}

function emptyDraft(): TaskDraft {
  const start = new Date(Date.now() + 60 * 60 * 1000);
  start.setSeconds(0, 0);
  const end = new Date(start.getTime() + 10 * 60 * 1000);
  const toLocal = (value: Date) => {
    const pad = (n: number) => String(n).padStart(2, '0');
    return (
      value.getFullYear() +
      '-' +
      pad(value.getMonth() + 1) +
      '-' +
      pad(value.getDate()) +
      'T' +
      pad(value.getHours()) +
      ':' +
      pad(value.getMinutes())
    );
  };
  return {
    task_uuid: '',
    title: '',
    detail: '',
    recurrence: 'once',
    start_at: toLocal(start),
    end_at: toLocal(end),
    one_shot_notification: true,
    bindings: [{ kind: 'group', id: '' }],
  };
}

function draftFromTask(task: ScheduledTaskItem): TaskDraft {
  return {
    task_uuid: task.task_id,
    title: task.title,
    detail: task.detail || '',
    recurrence: task.recurrence,
    start_at: task.start_at_local || '',
    end_at: task.end_at_local || '',
    one_shot_notification: task.one_shot_notification !== false,
    bindings: (task.bindings || []).map((item) => ({
      kind: item.kind === 'private' ? 'private' : 'group',
      id: item.id,
    })),
  };
}

function bindingsText(task: ScheduledTaskItem): string {
  const bindings = task.bindings || [];
  if (bindings.length === 0) return '—';
  return bindings.map((item) => (item.kind === 'group' ? '群 ' : '私聊 ') + item.id).join('、');
}

export default function ScheduledTasks() {
  const query = useQuery(QK.scheduledTasks, () => api.scheduledTasks(), {
    interval: POLL.scheduledTasks,
  });
  const payload = query.data;
  const tasks = useMemo(() => payload?.tasks || [], [payload]);
  const editable = payload?.editable !== false;

  const [draft, setDraft] = useState<TaskDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [compact, setCompact] = useState(() => window.matchMedia(COMPACT_TASKS_QUERY).matches);

  useEffect(() => {
    const media = window.matchMedia(COMPACT_TASKS_QUERY);
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const run = async (body: ScheduledTaskActionBody, success: string) => {
    setBusy(true);
    try {
      const result = await api.scheduledTaskAction(body);
      if (!result.ok) {
        notify(result.error || '操作失败', 'err');
        return false;
      }
      notify(result.data?.message || success, 'ok');
      await query.refetch();
      return true;
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!draft || busy) return;
    setFormError('');
    if (!draft.title.trim()) {
      setFormError('标题不能为空');
      return;
    }
    const bindings = draft.bindings
      .map((item) => ({ kind: item.kind, id: item.id.trim() }))
      .filter((item) => item.id);
    if (bindings.length === 0) {
      setFormError('至少需要一个绑定聊天流');
      return;
    }
    if (!draft.start_at || !draft.end_at) {
      setFormError('开始与结束时间都要填写');
      return;
    }
    const body: ScheduledTaskActionBody = draft.task_uuid
      ? {
          action: 'update',
          task_uuid: draft.task_uuid,
          title: draft.title.trim(),
          detail: draft.detail,
          recurrence: draft.recurrence,
          start_at: draft.start_at,
          end_at: draft.end_at,
          one_shot_notification: draft.one_shot_notification,
          bindings,
        }
      : {
          action: 'create',
          title: draft.title.trim(),
          detail: draft.detail,
          recurrence: draft.recurrence,
          start_at: draft.start_at,
          end_at: draft.end_at,
          one_shot_notification: draft.one_shot_notification,
          bindings,
        };
    const ok = await run(body, draft.task_uuid ? '定时任务已更新' : '定时任务已创建');
    if (ok) setDraft(null);
  };

  const toggle = async (task: ScheduledTaskItem) => {
    await run(
      {
        action: 'set_state',
        task_uuid: task.task_id,
        state: task.enabled ? 'disabled' : 'active',
      },
      task.enabled ? '已停用' : '已启用',
    );
  };

  const remove = async (task: ScheduledTaskItem) => {
    if (
      !(await confirmAction({
        title: '删除定时任务',
        description: '删除「' + task.title + '」后将不再提醒。',
        confirmLabel: '删除任务',
        danger: true,
      }))
    )
      return;
    await run({ action: 'delete', task_uuid: task.task_id }, '定时任务已删除');
  };

  const updateDraft = (patch: Partial<TaskDraft>) =>
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));

  const updateBinding = (index: number, patch: Partial<BindingDraft>) =>
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            bindings: prev.bindings.map((item, itemIndex) =>
              itemIndex === index ? { ...item, ...patch } : item,
            ),
          }
        : prev,
    );

  const unavailable = payload !== null && payload !== undefined && payload.available === false;
  const taskActions = (task: ScheduledTaskItem) => (
    <div className="scheduled-row-actions">
      <Button
        size="sm"
        disabled={!editable || busy}
        onClick={() => {
          setFormError('');
          setDraft(draftFromTask(task));
        }}
      >
        编辑
      </Button>
      <Button
        size="sm"
        variant={task.enabled ? 'default' : 'primary'}
        disabled={!editable || busy}
        onClick={() => void toggle(task)}
      >
        {task.enabled ? '停用' : '启用'}
      </Button>
      <Button variant="danger" size="sm" disabled={!editable || busy} onClick={() => void remove(task)}>
        删除
      </Button>
    </div>
  );

  return (
    <div className="page scheduled-page">
      <PageHeader
        title="定时任务"
        actions={
          <>
            <Button
              variant="primary"
              disabled={!editable || busy || unavailable}
              onClick={() => {
                setFormError('');
                setDraft(emptyDraft());
              }}
            >
              <Icon name="plus" />
              新建任务
            </Button>
          </>
        }
      />
      {/* 管理器不可用时下面的空态已经说明了原因，这里不再重复告警 */}
      {payload?.error && payload.available !== false && <InlineAlert tone="warning" title={payload.error} />}
      {!editable && (
        <InlineAlert tone="warning" title="当前会话没有管理权限，只能查看">
          面板管理功能已关闭或远程管理被禁用。
        </InlineAlert>
      )}
      {query.loading && !payload && (
        <PanelSkeleton className="card" label="正在读取定时任务…" kind="list" rows={4} />
      )}
      {query.error && (
        <InlineAlert
          tone="error"
          title="读取定时任务失败"
          actions={<Button onClick={() => void query.refetch()}>重新读取</Button>}
        />
      )}

      {unavailable ? (
        <EmptyState icon="clock" title="定时任务不可用">
          <p>{payload?.error || '定时任务管理器未启用。'}</p>
        </EmptyState>
      ) : tasks.length === 0 ? (
        !query.loading && !query.error && <EmptyState compact>还没有定时任务</EmptyState>
      ) : compact ? (
        <ol className="scheduled-task-list" aria-label="定时任务列表">
          {tasks.map((task) => {
            const bindings = task.bindings || [];
            const bindingItems = (items: typeof bindings, offset = 0) =>
              items.map((binding, index) => (
                <li key={`${binding.kind}:${binding.id}:${offset + index}`}>
                  <span>{binding.kind === 'group' ? '群聊' : '私聊'}</span>
                  <code>{binding.id}</code>
                </li>
              ));
            return (
              <li key={task.task_id}>
                <article className="scheduled-task-card" aria-label={task.title}>
                  <div className="scheduled-task-card-head">
                    <h3>{task.title}</h3>
                    <span className={'tag ' + (task.enabled ? 'ok' : 'warn')}>
                      {task.enabled ? '启用' : '停用'}
                    </span>
                  </div>
                  {task.detail && <p className="scheduled-task-card-detail">{task.detail}</p>}
                  <dl className="scheduled-task-card-meta">
                    <div className="scheduled-task-next">
                      <dt>下次触发</dt>
                      <dd>{task.next_run || '—'}</dd>
                    </div>
                    <div className="scheduled-task-window">
                      <dt>时间窗口</dt>
                      <dd>
                        <span>
                          <span>开始</span>
                          <span>{task.start_at || '—'}</span>
                        </span>
                        <span>
                          <span>结束</span>
                          <span>{task.end_at || '—'}</span>
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>重复方式</dt>
                      <dd>
                        {RECURRENCE_OPTIONS.find((item) => item.value === task.recurrence)?.label ||
                          task.recurrence}
                      </dd>
                    </div>
                    <div>
                      <dt>通知策略</dt>
                      <dd>{task.one_shot_notification === false ? '窗口内持续提醒' : '每个窗口一次'}</dd>
                    </div>
                  </dl>
                  <div className="scheduled-task-card-bindings">
                    <h4>绑定聊天流{bindings.length > 0 && <span>{bindings.length}</span>}</h4>
                    {bindings.length === 0 ? (
                      <p className="muted small">暂无绑定</p>
                    ) : (
                      <>
                        <ul>{bindingItems(bindings.slice(0, 2))}</ul>
                        {bindings.length > 2 && (
                          <details>
                            <summary>其余 {bindings.length - 2} 个绑定</summary>
                            <ul>{bindingItems(bindings.slice(2), 2)}</ul>
                          </details>
                        )}
                      </>
                    )}
                  </div>
                  {taskActions(task)}
                </article>
              </li>
            );
          })}
        </ol>
      ) : (
        <section className="card scheduled-table-card">
          <p className="table-scroll-hint">左右滑动查看完整任务</p>
          <div className="table-scroll" role="region" aria-label="定时任务列表">
            <table className="model-table scheduled-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>周期</th>
                  <th>时间窗口</th>
                  <th>下次触发</th>
                  <th>通知</th>
                  <th>绑定</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.task_id}>
                    <td className="scheduled-title-cell">
                      <div className="scheduled-title">{task.title}</div>
                      {task.detail && <div className="scheduled-detail muted small">{task.detail}</div>}
                    </td>
                    <td>
                      {RECURRENCE_OPTIONS.find((item) => item.value === task.recurrence)?.label ||
                        task.recurrence}
                    </td>
                    <td className="scheduled-time muted small">
                      {task.start_at || '—'}
                      <br />
                      {task.end_at || '—'}
                    </td>
                    <td className="scheduled-time">{task.next_run || '—'}</td>
                    <td>{task.one_shot_notification === false ? '持续' : '一次性'}</td>
                    <td className="scheduled-bindings muted small">{bindingsText(task)}</td>
                    <td>
                      <span className={'tag ' + (task.enabled ? 'ok' : 'warn')}>
                        {task.enabled ? '启用' : '停用'}
                      </span>
                    </td>
                    <td>{taskActions(task)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Modal
        open={!!draft}
        title={draft?.task_uuid ? '编辑定时任务' : '新建定时任务'}
        size="wide"
        className="scheduled-task-dialog"
        closeDisabled={busy}
        onClose={() => setDraft(null)}
        footer={
          <ModalActions>
            <Button type="button" disabled={busy} onClick={() => setDraft(null)}>
              取消
            </Button>
            <Button type="submit" form="scheduled-task-form" variant="primary" disabled={busy}>
              <Icon name="save" />
              {busy ? '提交中…' : '保存'}
            </Button>
          </ModalActions>
        }
      >
        {draft && (
          <form
            id="scheduled-task-form"
            className="scheduled-task-form"
            aria-label="定时任务表单"
            aria-busy={busy}
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {formError && <InlineAlert tone="error" title={formError} />}
            <fieldset className="scheduled-task-fields" disabled={busy}>
              <div className="scheduled-task-section">
                <div className="scheduled-task-grid scheduled-task-basics">
                  <div className="scheduled-task-field">
                    <label htmlFor="task-title">标题</label>
                    <input
                      id="task-title"
                      className="input"
                      value={draft.title}
                      data-autofocus
                      placeholder="例如：每天下午喝水"
                      onChange={(event) => updateDraft({ title: event.target.value })}
                    />
                  </div>
                  <div className="scheduled-task-field">
                    <label htmlFor="task-recurrence">重复方式</label>
                    <select
                      id="task-recurrence"
                      className="input"
                      value={draft.recurrence}
                      onChange={(event) => updateDraft({ recurrence: event.target.value })}
                    >
                      {RECURRENCE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="scheduled-task-field">
                  <label htmlFor="task-detail">提醒内容</label>
                  <textarea
                    id="task-detail"
                    className="input"
                    rows={3}
                    value={draft.detail}
                    placeholder="填写需要发送的提醒"
                    onChange={(event) => updateDraft({ detail: event.target.value })}
                  />
                </div>
              </div>

              <div className="scheduled-task-section">
                <div className="scheduled-task-grid">
                  <div className="scheduled-task-field">
                    <label htmlFor="task-start">开始时间</label>
                    <input
                      id="task-start"
                      className="input"
                      type="datetime-local"
                      value={draft.start_at}
                      aria-describedby="task-window-hint"
                      onChange={(event) => updateDraft({ start_at: event.target.value })}
                    />
                  </div>
                  <div className="scheduled-task-field">
                    <label htmlFor="task-end">结束时间</label>
                    <input
                      id="task-end"
                      className="input"
                      type="datetime-local"
                      value={draft.end_at}
                      aria-describedby="task-window-hint"
                      onChange={(event) => updateDraft({ end_at: event.target.value })}
                    />
                  </div>
                </div>
                <p id="task-window-hint" className="scheduled-task-hint">
                  开始与结束时间定义每次触发窗口；重复任务会沿用这个时长。
                </p>
                <label className="scheduled-task-notification">
                  <input
                    type="checkbox"
                    checked={draft.one_shot_notification}
                    onChange={(event) => updateDraft({ one_shot_notification: event.target.checked })}
                    aria-describedby="task-notification-hint"
                  />
                  <span>
                    每个触发窗口只通知一次
                    <span id="task-notification-hint" className="scheduled-task-hint">
                      关闭后会在窗口内持续提醒。
                    </span>
                  </span>
                </label>
              </div>

              <section className="scheduled-task-section" aria-labelledby="task-bindings-title">
                <div className="scheduled-task-section-head">
                  <h4 id="task-bindings-title">绑定聊天流</h4>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => updateDraft({ bindings: [...draft.bindings, { kind: 'group', id: '' }] })}
                  >
                    <Icon name="plus" />
                    添加绑定
                  </Button>
                </div>
                {draft.bindings.map((binding, index) => (
                  <div className="scheduled-task-binding" key={index}>
                    <select
                      className="input"
                      aria-label={'绑定类型 ' + (index + 1)}
                      value={binding.kind}
                      onChange={(event) =>
                        updateBinding(index, { kind: event.target.value as 'group' | 'private' })
                      }
                    >
                      <option value="group">群聊</option>
                      <option value="private">私聊</option>
                    </select>
                    <input
                      className="input"
                      inputMode="numeric"
                      aria-label={'绑定 ID ' + (index + 1)}
                      placeholder={binding.kind === 'group' ? '群号' : 'QQ 号'}
                      value={binding.id}
                      onChange={(event) => updateBinding(index, { id: event.target.value })}
                    />
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      disabled={draft.bindings.length <= 1}
                      onClick={() =>
                        updateDraft({
                          bindings: draft.bindings.filter((_, itemIndex) => itemIndex !== index),
                        })
                      }
                    >
                      移除
                    </Button>
                  </div>
                ))}
              </section>
            </fieldset>
          </form>
        )}
      </Modal>
    </div>
  );
}
