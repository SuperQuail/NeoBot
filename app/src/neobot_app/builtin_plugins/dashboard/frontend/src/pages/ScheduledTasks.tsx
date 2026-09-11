// pages/ScheduledTasks.tsx —— 定时任务管理：查看 / 新建 / 编辑 / 启停 / 删除
// 读走 ScheduledTaskManager 的投影；写全部转发给 reminder skill（与主 Agent 同一套校验）。
import { useMemo, useState } from 'react';
import Icon from '../components/Icon';
import Modal from '../components/Modal';
import InlineAlert from '../components/ui/InlineAlert';
import { toast } from '../components/Toast';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ScheduledTaskActionBody, ScheduledTaskItem } from '../api/types';

const RECURRENCE_OPTIONS = [
  { value: 'once', label: '一次(once)' },
  { value: 'daily', label: '每天(daily)' },
  { value: 'weekly', label: '每周(weekly)' },
  { value: 'monthly', label: '每月(monthly)' },
  { value: 'yearly', label: '每年(yearly)' },
];

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

  const run = async (body: ScheduledTaskActionBody, success: string) => {
    setBusy(true);
    const result = await api.scheduledTaskAction(body);
    setBusy(false);
    if (!result.ok) {
      toast(result.error || '操作失败', 'err');
      return false;
    }
    toast(result.data?.message || success, 'ok');
    await query.refetch();
    return true;
  };

  const submit = async () => {
    if (!draft) return;
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
    if (!window.confirm('删除定时任务「' + task.title + '」？删除后不会再提醒。')) return;
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

  return (
    <div className="page scheduled-page">
      <section className="card">
        <div className="card-head">
          <h3>定时任务</h3>
          <div className="spacer" />
          <button className="btn" disabled={query.loading} onClick={() => void query.refetch()}>
            <Icon name="refresh" />
            {query.loading ? '读取中…' : '刷新'}
          </button>
          <button
            className="btn primary"
            disabled={!editable || busy}
            onClick={() => {
              setFormError('');
              setDraft(emptyDraft());
            }}
          >
            <Icon name="plus" />
            新建任务
          </button>
        </div>
        {/* 管理器不可用时下面的空态已经说明了原因，这里不再重复告警 */}
        {payload?.error && payload.available !== false && (
          <InlineAlert tone="warning" title={payload.error} />
        )}
        {!editable && (
          <InlineAlert tone="warning" title="当前会话没有管理权限，只能查看">
            面板管理功能已关闭或远程管理被禁用。
          </InlineAlert>
        )}
      </section>

      {unavailable ? (
        <div className="workspace-empty">
          <Icon name="clock" />
          <h3>定时任务不可用</h3>
          <p>{payload?.error || '定时任务管理器未启用。'}</p>
        </div>
      ) : tasks.length === 0 ? (
        !query.loading && <div className="empty muted">还没有定时任务</div>
      ) : (
        <section className="card">
          <table className="model-table">
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
                  <td>
                    <div>{task.title}</div>
                    {task.detail && <div className="muted small">{task.detail}</div>}
                  </td>
                  <td>{task.recurrence}</td>
                  <td className="muted small">
                    {task.start_at || '—'}
                    <br />
                    {task.end_at || '—'}
                  </td>
                  <td>{task.next_run || '—'}</td>
                  <td>{task.one_shot_notification === false ? '持续' : '一次性'}</td>
                  <td className="muted small">{bindingsText(task)}</td>
                  <td>
                    <span className={'tag ' + (task.enabled ? 'ok' : 'warn')}>
                      {task.enabled ? '启用' : '停用'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn-sm"
                      disabled={!editable || busy}
                      onClick={() => {
                        setFormError('');
                        setDraft(draftFromTask(task));
                      }}
                    >
                      编辑
                    </button>
                    <button
                      className={'btn-sm' + (task.enabled ? '' : ' primary')}
                      disabled={!editable || busy}
                      onClick={() => void toggle(task)}
                    >
                      {task.enabled ? '停用' : '启用'}
                    </button>
                    <button
                      className="btn-sm danger"
                      disabled={!editable || busy}
                      onClick={() => void remove(task)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <Modal
        open={!!draft}
        title={draft?.task_uuid ? '编辑定时任务' : '新建定时任务'}
        size="wide"
        onClose={() => setDraft(null)}
      >
        {draft && (
          <form
            className="install-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {formError && <InlineAlert tone="error" title={formError} />}

            <div className="cfg-row">
              <label className="cfg-label" htmlFor="task-title">
                标题
              </label>
              <div className="cfg-control">
                <input
                  id="task-title"
                  className="input"
                  value={draft.title}
                  data-autofocus
                  onChange={(event) => updateDraft({ title: event.target.value })}
                />
              </div>
            </div>

            <div className="cfg-row">
              <label className="cfg-label" htmlFor="task-detail">
                提醒内容
              </label>
              <div className="cfg-control">
                <textarea
                  id="task-detail"
                  className="input"
                  rows={3}
                  value={draft.detail}
                  onChange={(event) => updateDraft({ detail: event.target.value })}
                />
              </div>
            </div>

            <div className="cfg-row">
              <label className="cfg-label" htmlFor="task-recurrence">
                重复方式
              </label>
              <div className="cfg-control">
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

            <div className="cfg-row">
              <label className="cfg-label" htmlFor="task-start">
                开始时间
              </label>
              <div className="cfg-control">
                <input
                  id="task-start"
                  className="input"
                  type="datetime-local"
                  value={draft.start_at}
                  onChange={(event) => updateDraft({ start_at: event.target.value })}
                />
              </div>
            </div>

            <div className="cfg-row">
              <label className="cfg-label" htmlFor="task-end">
                结束时间
              </label>
              <div className="cfg-control">
                <input
                  id="task-end"
                  className="input"
                  type="datetime-local"
                  value={draft.end_at}
                  onChange={(event) => updateDraft({ end_at: event.target.value })}
                />
                <span className="muted small">
                  结束时间定义每个周期的时间窗口长度；重复任务按相同窗口周期出现。
                </span>
              </div>
            </div>

            <div className="cfg-row">
              <span className="cfg-label">通知策略</span>
              <div className="cfg-control">
                <label className="muted small">
                  <input
                    type="checkbox"
                    checked={draft.one_shot_notification}
                    onChange={(event) =>
                      updateDraft({ one_shot_notification: event.target.checked })
                    }
                  />
                  每个触发窗口只通知一次(关闭则窗口内持续提醒)
                </label>
              </div>
            </div>

            <div className="cfg-row">
              <span className="cfg-label">绑定聊天流</span>
              <div className="cfg-control">
                {draft.bindings.map((binding, index) => (
                  <div className="binding-row" key={index}>
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
                      aria-label={'绑定 ID ' + (index + 1)}
                      placeholder={binding.kind === 'group' ? '群号' : 'QQ 号'}
                      value={binding.id}
                      onChange={(event) => updateBinding(index, { id: event.target.value })}
                    />
                    <button
                      type="button"
                      className="btn-sm danger"
                      disabled={draft.bindings.length <= 1}
                      onClick={() =>
                        updateDraft({
                          bindings: draft.bindings.filter((_, itemIndex) => itemIndex !== index),
                        })
                      }
                    >
                      移除
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="btn-sm"
                  onClick={() =>
                    updateDraft({ bindings: [...draft.bindings, { kind: 'group', id: '' }] })
                  }
                >
                  添加绑定
                </button>
              </div>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setDraft(null)}>
                取消
              </button>
              <button type="submit" className="btn primary" disabled={busy}>
                <Icon name="save" />
                {busy ? '提交中…' : '保存'}
              </button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
