// pages/Archives.tsx —— 档案管理（features/spec(2)）：查看 / 编辑 / 删除档案记忆
// 三栏：表清单（左）/ 条目列表（中）/ 单条详情（右），数据全部来自既有的 ArchiveMemoryService。
//
// 关键约束（照 spec §4 执行）：
// - 轮询：POLL.archives = 0（**手动刷新**）。档案查的是数据库且列表可能很大；
//   更要紧的是编辑态绝不能被自动刷新覆盖 —— 因此编辑草稿是独立 state，
//   刷新只更新只读快照（detail.data），不会回写草稿；
// - 删除：二次确认（输入 key **或** 勾选确认）+ 被删内容警示 + delete_enabled=false 时禁用；
//   内部表（memory_counter 等）突出警告文案，且禁止编辑；
// - 编辑：必须带 version；409 时提示「已被他人修改」并展示服务端当前内容，
//   由用户选择「重新加载」或「保留我的修改」，**不自动覆盖**。
import { useCallback, useEffect, useMemo, useState } from 'react';
import Icon from '../components/Icon';
import Modal from '../components/Modal';
import InlineAlert from '../components/ui/InlineAlert';
import { toast } from '../components/Toast';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ArchiveItemDetail, ArchiveSnapshot, ArchiveSummarizeTask } from '../api/types';

/** 每页条目数（后端上限 200） */
const PAGE_SIZE = 50;

/** 面板删除开关名（与模型侧的 agent.memory.archive.allow_delete 完全独立） */
const DELETE_SWITCH = 'allow_archive_delete';

/** localStorage 键：记住上次输入的目标字符数（R15 要求**不写回**全局配置） */
const TARGET_KEY = 'neobot-archives-target-chars';

/** 压缩任务轮询间隔（毫秒） */
const TASK_POLL_MS = 2000;

/** 批量条目状态 → 中文（与后端 ArchiveSummarizeBatchItem.status 对齐） */
const BATCH_STATUS_TEXT: Record<string, string> = {
  pending: '等待中',
  running: '压缩中',
  done: '已完成',
  failed: '失败（已保留原文）',
  skipped: '已跳过',
};

/** 读取上次输入的目标字符数（localStorage 不可用时返回空串） */
function readStoredTarget(): string {
  try {
    return localStorage.getItem(TARGET_KEY) || '';
  } catch {
    return '';
  }
}

interface ArchiveFilters {
  keyQuery: string;
  valueQuery: string;
  tags: string;
  overLimitOnly: boolean;
}

const EMPTY_FILTERS: ArchiveFilters = {
  keyQuery: '',
  valueQuery: '',
  tags: '',
  overLimitOnly: false,
};

function formatTime(value?: string | null): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 19);
}

/** tags 输入框（逗号分隔）→ 数组 */
function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

function tagText(tags?: string[]): string {
  return (tags || []).length > 0 ? (tags || []).join(', ') : '—';
}

export default function Archives() {
  const tablesQuery = useQuery(QK.archives, () => api.archives(), { interval: POLL.archives });
  const payload = tablesQuery.data;
  const tables = useMemo(() => payload?.items || [], [payload]);
  // 删除开关关着时提前禁用按钮，避免用户点了才吃 403
  const deleteEnabled = payload?.delete_enabled === true;
  const canManage = payload?.can_manage === true;
  const maxTotalChars = Number(payload?.max_total_chars || 0);

  const [table, setTable] = useState('');
  const [keyInput, setKeyInput] = useState('');
  const [valueInput, setValueInput] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [overLimitInput, setOverLimitInput] = useState(false);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<ArchiveFilters>(EMPTY_FILTERS);
  const [key, setKey] = useState('');

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [tagsDraft, setTagsDraft] = useState('');
  const [saving, setSaving] = useState(false);
  /** 409 冲突时服务端带回的当前内容（用于提示「已被他人修改」） */
  const [conflict, setConflict] = useState<ArchiveItemDetail | null>(null);

  // ── AI 压缩（spec(4) Part C）──
  const summarizeAvailable = payload?.summarize_available !== false;
  const minTarget = Number(payload?.min_target_chars || 200);
  const maxTarget = Number(payload?.max_target_chars || maxTotalChars || 100000);

  /** 本次压缩的目标字符数（默认 = 全局上限；localStorage 记住上次输入） */
  const [targetChars, setTargetChars] = useState(readStoredTarget);
  /** 当前压缩任务（单条或批量；后台任务，轮询到终态） */
  const [task, setTask] = useState<ArchiveSummarizeTask | null>(null);
  const [starting, setStarting] = useState(false);
  const [snapshots, setSnapshots] = useState<ArchiveSnapshot[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [snapshotDetail, setSnapshotDetail] = useState<(ArchiveSnapshot & { value?: string }) | null>(null);
  const [snapshotError, setSnapshotError] = useState('');

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState('');
  const [deleteChecked, setDeleteChecked] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  // 表清单到达后默认选中第一张（用户已选且仍存在时不动）
  useEffect(() => {
    if (tables.length === 0) return;
    if (table && tables.some((item) => item.table_name === table)) return;
    setTable(tables[0].table_name);
  }, [tables, table]);

  const itemsQueryKey = [
    table,
    filters.keyQuery,
    filters.valueQuery,
    filters.tags,
    filters.overLimitOnly ? 'over' : 'all',
    offset,
  ].join('|');

  const itemsQuery = useQuery(
    QK.archiveItems(itemsQueryKey),
    () =>
      table
        ? api.archiveItems({
            table,
            keyQuery: filters.keyQuery,
            valueQuery: filters.valueQuery,
            tags: filters.tags,
            limit: PAGE_SIZE,
            offset,
            overLimitOnly: filters.overLimitOnly,
          })
        : Promise.resolve(null),
    { deps: [itemsQueryKey] },
  );
  const items = useMemo(() => itemsQuery.data?.items || [], [itemsQuery.data]);
  const hasMore = itemsQuery.data?.has_more === true;

  const detailQuery = useQuery(
    QK.archiveItem(table, key),
    () => (table && key ? api.archiveItem(table, key) : Promise.resolve(null)),
    { deps: [table, key] },
  );
  const detailResult = detailQuery.data;
  const item = detailResult?.ok ? detailResult.data : null;
  const detailError = detailResult && !detailResult.ok ? detailResult.error || '读取档案失败' : '';

  const { refetch: refetchTables } = tablesQuery;
  const { refetch: refetchItems } = itemsQuery;
  const { refetch: refetchDetail } = detailQuery;
  const refreshAll = useCallback(async () => {
    await Promise.all([refetchTables(), refetchItems()]);
    if (key) await refetchDetail();
  }, [refetchTables, refetchItems, refetchDetail, key]);

  // ── AI 压缩：压缩历史 / 目标默认值 / 任务轮询 ──────────────────

  /** 当前条目的压缩历史（只读快照；不提供恢复入口） */
  const loadSnapshots = useCallback(async () => {
    if (!table || !key) {
      setSnapshots([]);
      return;
    }
    setSnapshotsLoading(true);
    const data = await api.archiveSnapshots(table, key);
    setSnapshotsLoading(false);
    setSnapshots(data?.items || []);
  }, [table, key]);

  useEffect(() => {
    void loadSnapshots();
  }, [loadSnapshots]);

  // A46：目标输入框默认值 = GET /api/archives 的 max_total_chars
  useEffect(() => {
    if (targetChars) return;
    if (maxTotalChars > 0) setTargetChars(String(maxTotalChars));
  }, [maxTotalChars, targetChars]);

  useEffect(() => {
    try {
      if (targetChars) localStorage.setItem(TARGET_KEY, targetChars);
    } catch {
      /* localStorage 不可用时忽略：默认值仍会回落到全局上限 */
    }
  }, [targetChars]);

  // 压缩是后台任务（D13）：轮询到终态后刷新详情 / 列表并提示前后字数。
  useEffect(() => {
    if (!task || task.status !== 'running' || !task.task_id) return undefined;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        const next = await api.archiveSummarizeStatus(String(task.task_id));
        if (cancelled || !next) return;
        setTask(next);
        if (next.status !== 'done' && next.status !== 'failed') return;
        if (next.kind === 'batch') {
          toast(
            next.message ||
              '批量压缩完成：成功 ' + (next.succeeded ?? 0) + ' 条 / 失败 ' + (next.failed ?? 0) + ' 条',
            (next.failed ?? 0) > 0 ? 'warn' : 'ok',
          );
        } else if (next.status === 'done') {
          toast(
            '压缩完成：' +
              (next.chars_before ?? 0) +
              ' → ' +
              (next.chars_after ?? 0) +
              ' 字（目标 ' +
              (next.target_chars ?? 0) +
              '）',
            'ok',
          );
        } else {
          toast(next.error || '压缩失败，已保留原文', 'err');
        }
        await Promise.all([refetchDetail(), refetchItems(), refetchTables()]);
        await loadSnapshots();
      })();
    }, TASK_POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [task, refetchDetail, refetchItems, refetchTables, loadSnapshots]);

  /** 读取并校验目标输入框；非法时提示并返回 null */
  function targetValue(): number | null {
    const value = Number(targetChars);
    if (!Number.isFinite(value) || value <= 0) {
      toast('请先填写目标字符数', 'err');
      return null;
    }
    return Math.trunc(value);
  }

  async function startSummarize() {
    if (!item) return;
    const target = targetValue();
    if (target === null) return;
    setStarting(true);
    const result = await api.archiveSummarize({
      table: item.table_name,
      key: item.key,
      target_chars: target,
    });
    setStarting(false);
    if (!result.ok || !result.data) {
      toast(result.error || '触发压缩失败', 'err');
      return;
    }
    setTask(result.data);
    if (result.data.status === 'noop') {
      toast(result.data.message || '当前字数已不大于目标，无需压缩', 'info');
      return;
    }
    toast(result.data.message || '已开始压缩', 'ok');
  }

  async function startBatchSummarize() {
    const target = targetValue();
    if (target === null) return;
    setStarting(true);
    const result = await api.archiveSummarizeOverLimit({ target_chars: target });
    setStarting(false);
    if (!result.ok || !result.data) {
      toast(result.error || '批量触发失败', 'err');
      return;
    }
    setTask(result.data);
    toast(result.data.message || '已开始批量压缩', 'ok');
  }

  async function viewSnapshot(snapshot: ArchiveSnapshot) {
    setSnapshotOpen(true);
    setSnapshotDetail(null);
    setSnapshotError('');
    const data = await api.archiveSnapshot(snapshot.id);
    if (!data || data.ok === false || !data.snapshot) {
      setSnapshotError(data?.error || '读取快照失败');
      return;
    }
    setSnapshotDetail(data.snapshot);
  }

  function pickTable(name: string) {
    if (name === table) return;
    setTable(name);
    setKey('');
    setEditing(false);
    setConflict(null);
    setOffset(0);
    setFilters(EMPTY_FILTERS);
    setKeyInput('');
    setValueInput('');
    setTagsInput('');
    setOverLimitInput(false);
  }

  function pickItem(next: string) {
    if (next === key) return;
    // 编辑态切换条目会丢草稿：先确认（避免误点导致白改）
    if (editing && !window.confirm('正在编辑且尚未保存，切换条目会丢弃当前修改，是否继续？')) return;
    setKey(next);
    setEditing(false);
    setConflict(null);
  }

  function applyFilters() {
    setOffset(0);
    setFilters({
      keyQuery: keyInput.trim(),
      valueQuery: valueInput.trim(),
      tags: tagsInput.trim(),
      overLimitOnly: overLimitInput,
    });
  }

  function clearFilters() {
    setKeyInput('');
    setValueInput('');
    setTagsInput('');
    setOverLimitInput(false);
    setOffset(0);
    setFilters(EMPTY_FILTERS);
  }

  function startEdit() {
    if (!item || item.editable === false) return;
    setDraft(item.value || '');
    setTagsDraft((item.tags || []).join(', '));
    setConflict(null);
    setEditing(true);
  }

  async function saveEdit() {
    if (!item) return;
    if (!draft.trim()) {
      toast('档案内容不能为空（后端同样拒绝空内容）', 'err');
      return;
    }
    setSaving(true);
    const result = await api.archiveUpdate({
      table: item.table_name,
      key: item.key,
      value: draft,
      tags: parseTags(tagsDraft),
      version: Number(item.version ?? 0),
    });
    setSaving(false);
    if (result.ok) {
      toast(result.data?.message || '档案已保存', 'ok');
      setEditing(false);
      setConflict(null);
      await refetchDetail();
      void refetchItems();
      void refetchTables();
      return;
    }
    if (result.status === 409) {
      // 乐观锁冲突：不自动覆盖，把服务端当前内容摆出来让用户选择
      setConflict(result.data?.current || null);
      void refetchDetail();
      return;
    }
    toast(result.error || '保存失败', 'err');
  }

  function openDelete() {
    setDeleteText('');
    setDeleteChecked(false);
    setDeleteError('');
    setDeleteOpen(true);
  }

  async function confirmDelete() {
    if (!item) return;
    const armed = deleteChecked || deleteText.trim() === item.key;
    if (!armed) return;
    setDeleting(true);
    setDeleteError('');
    const result = await api.archiveDelete({
      table: item.table_name,
      key: item.key,
      version: Number(item.version ?? 0),
    });
    setDeleting(false);
    if (result.ok) {
      toast(result.data?.message || '档案已删除', 'ok');
      setDeleteOpen(false);
      setKey('');
      setEditing(false);
      await Promise.all([refetchItems(), refetchTables()]);
      return;
    }
    setDeleteError(result.error || '删除失败');
  }

  const taskRunning = task?.status === 'running';
  /** 当前条目是否正在被压缩：running 期间禁用同一条目的编辑 / 删除（§4.10.1） */
  const itemRunning =
    taskRunning === true &&
    (task?.kind === 'batch'
      ? (task?.items || []).some(
          (entry) =>
            entry.status === 'running' &&
            entry.table === item?.table_name &&
            entry.key === item?.key,
        )
      : task?.table === item?.table_name && task?.key === item?.key);

  const unavailable = payload === null && !tablesQuery.loading;
  const loadError = !unavailable && payload?.ok === false ? payload.error || '档案表清单读取失败' : '';

  return (
    <div className="page archives-page">
      <section className="card">
        <div className="card-head">
          <h3>档案管理</h3>
          <div className="spacer" />
          <span className="tag info">共 {tables.length} 张表</span>
          {maxTotalChars > 0 && <span className="tag debug">单条上限 {maxTotalChars} 字符</span>}
          <span className={'tag ' + (deleteEnabled ? 'warn' : 'debug')}>
            删除开关 {deleteEnabled ? '已开启' : '已关闭'}
          </span>
          <button className="btn" disabled={tablesQuery.loading} onClick={() => void refreshAll()}>
            <Icon name="refresh" />
            {tablesQuery.loading ? '读取中…' : '刷新'}
          </button>
        </div>
        <InlineAlert tone="warning" title="档案包含隐私数据">
          这里的用户 / 群档案与记忆摘要都是高敏感内容，面板默认监听 0.0.0.0；请勿随意截图外发，生产环境建议只监听
          127.0.0.1 或置于带鉴权的反向代理之后。本页<b>不轮询</b>（只在打开时与点击「刷新」时读库）。
        </InlineAlert>
        {!canManage && (
          <InlineAlert tone="info" title="当前会话没有管理权限">
            面板管理功能已关闭或远程管理被禁用，只能查看档案（编辑 / 删除按钮已禁用）。
          </InlineAlert>
        )}
        {!deleteEnabled && (
          <InlineAlert tone="warning" title={'面板档案删除未开启（' + DELETE_SWITCH + '）'}>
            请在 dashboard 插件配置里把 <code>{DELETE_SWITCH}</code> 设为 true 才能删除档案；该开关与模型侧的
            <code>agent.memory.archive.allow_delete</code> 完全独立。
          </InlineAlert>
        )}
      </section>

      {canManage && summarizeAvailable && (
        <section className="card">
          <div className="card-head">
            <h3>AI 压缩（超限档案）</h3>
            <div className="spacer" />
            <label className="cfg-label" htmlFor="archive-batch-target">
              批量目标字符数
            </label>
            <input
              id="archive-batch-target"
              className="input archives-target-input"
              type="number"
              min={minTarget}
              max={maxTarget}
              value={targetChars}
              onChange={(event) => setTargetChars(event.target.value)}
            />
            <button
              className="btn"
              type="button"
              disabled={starting || taskRunning}
              onClick={() => void startBatchSummarize()}
            >
              <Icon name="archive" />
              批量压缩超限档案
            </button>
          </div>
          <p className="muted small">
            逐条串行压缩当前超限档案，一次最多 20 条，统一使用上面的目标字符数（{minTarget}–{maxTarget}）。
            目标只对本次压缩生效，<b>不会改写</b>全局配置 agent.memory.archive.max_total_chars。
          </p>
          {task && task.kind === 'batch' && (
            <div className="archives-batch">
              <InlineAlert
                tone={task.status === 'failed' ? 'error' : task.status === 'running' ? 'info' : 'success'}
                title={task.message || '批量压缩进行中…'}
              >
                成功 {task.succeeded ?? 0} 条 / 失败 {task.failed ?? 0} 条 / 跳过 {(task.skipped || []).length} 条
                {task.truncated ? '；本次还有 ' + task.truncated + ' 条超出上限未处理' : ''}
              </InlineAlert>
              {(task.items || []).length > 0 && (
                <table className="model-table archives-table">
                  <thead>
                    <tr>
                      <th>档案</th>
                      <th>状态</th>
                      <th>字数</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(task.items || []).map((entry) => (
                      <tr key={entry.table + ':' + entry.key}>
                        <td>
                          <code>
                            {entry.table}:{entry.key}
                          </code>
                        </td>
                        <td>{BATCH_STATUS_TEXT[entry.status || 'pending']}</td>
                        <td>
                          {entry.chars_before ?? 0} → {entry.chars_after ?? '…'}
                        </td>
                        <td className="muted small">{entry.error || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {(task.skipped || []).length > 0 && (
                <p className="muted small">
                  跳过明细：
                  {(task.skipped || []).map((row) => row.table + ':' + row.key).join('、')}
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {loadError && <InlineAlert tone="error" title={loadError} />}

      {unavailable ? (
        <div className="workspace-empty">
          <Icon name="archive" />
          <h3>档案服务不可用</h3>
          <p>后端未注入 archive_memory_service，或数据库未就绪。</p>
        </div>
      ) : (
        <div className="archives-layout">
          <section className="card archives-tables" aria-label="档案表清单">
            <div className="card-head">
              <h3>档案表</h3>
              <span className="muted small">{tables.length} 张</span>
            </div>
            {tables.length === 0 && !tablesQuery.loading && (
              <div className="empty muted">库里还没有任何档案表</div>
            )}
            <ul className="archives-table-list">
              {tables.map((entry) => {
                const active = entry.table_name === table;
                return (
                  <li key={entry.table_name}>
                    <button
                      type="button"
                      className={'prompt-key archives-table-key' + (active ? ' active' : '')}
                      aria-current={active}
                      onClick={() => pickTable(entry.table_name)}
                    >
                      <span className="archives-table-name">
                        <code>{entry.table_name}</code>
                        {entry.internal && <span className="tag warn">内部表</span>}
                        {Number(entry.over_limit_count || 0) > 0 && (
                          <span className="tag err">{entry.over_limit_count} 条超限</span>
                        )}
                      </span>
                      <span className="muted small">
                        {entry.count ?? 0} 条 · 最长 {entry.max_value_chars ?? 0} 字符
                      </span>
                    </button>
                    {entry.note && <p className="muted small archives-note">{entry.note}</p>}
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="card archives-items" aria-label="档案条目列表">
            <div className="card-head">
              <h3>条目</h3>
              <span className="muted small">{table || '未选择表'}</span>
            </div>

            <form
              className="archives-filters"
              onSubmit={(event) => {
                event.preventDefault();
                applyFilters();
              }}
            >
              <label className="cfg-label" htmlFor="archive-key-query">
                key 包含
              </label>
              <input
                id="archive-key-query"
                className="input"
                value={keyInput}
                placeholder="按 key 模糊匹配"
                onChange={(event) => setKeyInput(event.target.value)}
              />
              <label className="cfg-label" htmlFor="archive-value-query">
                内容包含
              </label>
              <input
                id="archive-value-query"
                className="input"
                value={valueInput}
                placeholder="在档案正文里模糊匹配"
                onChange={(event) => setValueInput(event.target.value)}
              />
              <label className="cfg-label" htmlFor="archive-tags-query">
                标签
              </label>
              <input
                id="archive-tags-query"
                className="input"
                value={tagsInput}
                placeholder="逗号分隔，如 重要,待办"
                onChange={(event) => setTagsInput(event.target.value)}
              />
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={overLimitInput}
                  onChange={(event) => setOverLimitInput(event.target.checked)}
                />
                只看超限
                {maxTotalChars > 0 ? '（>' + maxTotalChars + ' 字符）' : ''}
              </label>
              <div className="archives-filter-actions">
                <button className="btn-sm primary" type="submit">
                  <Icon name="search" />查询
                </button>
                <button className="btn-sm" type="button" onClick={clearFilters}>
                  重置
                </button>
                <button
                  className="btn-sm"
                  type="button"
                  disabled={itemsQuery.loading}
                  onClick={() => void refetchItems()}
                >
                  <Icon name="refresh" />刷新
                </button>
              </div>
            </form>

            <table className="model-table archives-table">
              <thead>
                <tr>
                  <th>key</th>
                  <th>更新时间</th>
                  <th>字符数</th>
                  <th>预览</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const active = row.key === key;
                  return (
                    <tr
                      key={row.key}
                      className={active ? 'archives-row active' : 'archives-row'}
                      onClick={() => pickItem(row.key)}
                    >
                      <td>
                        <button
                          type="button"
                          className="archives-item-key"
                          aria-current={active}
                          onClick={(event) => {
                            event.stopPropagation();
                            pickItem(row.key);
                          }}
                        >
                          <code>{row.key}</code>
                        </button>
                        {row.internal && <span className="tag warn">内部表</span>}
                      </td>
                      <td className="muted small">{formatTime(row.updated_at)}</td>
                      <td>{row.total_chars ?? 0}</td>
                      <td className="archives-preview">
                        {row.preview || '（空）'}
                        {row.preview_truncated && <span className="muted small"> …（已截断预览，详情里看全文）</span>}
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="muted">
                      {itemsQuery.loading ? '读取中…' : '没有匹配的档案条目'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            <div className="archives-pager">
              <span className="muted small">
                第 {items.length === 0 ? 0 : offset + 1}–{offset + items.length} 条 · 每页 {PAGE_SIZE}
              </span>
              <div className="spacer" />
              <button
                className="btn-sm"
                type="button"
                disabled={offset <= 0 || itemsQuery.loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </button>
              <button
                className="btn-sm"
                type="button"
                disabled={!hasMore || itemsQuery.loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </button>
            </div>
          </section>

          <section className="card archives-detail" aria-label="档案详情">
            {!key ? (
              <div className="empty muted">从中间列表选择一条档案查看全文</div>
            ) : detailError ? (
              <InlineAlert
                tone="error"
                title={detailError}
                actions={
                  <button className="btn-sm" type="button" onClick={() => void refetchDetail()}>
                    重新读取
                  </button>
                }
              />
            ) : !item ? (
              <div className="empty muted">{detailQuery.loading ? '读取中…' : '没有该档案'}</div>
            ) : (
              <>
                <div className="card-head">
                  <h3>
                    <code>{item.key}</code>
                  </h3>
                  <div className="spacer" />
                  <span className="tag info">version {item.version ?? 0}</span>
                  {item.internal && <span className="tag warn">内部表</span>}
                </div>

                {item.note && (
                  <InlineAlert tone={item.internal ? 'error' : 'warning'} title="删除保护提示">
                    {item.note}
                  </InlineAlert>
                )}

                <div className="archives-meta muted small">
                  <span>
                    表：<code>{item.table_name}</code>
                  </span>
                  <span>创建：{formatTime(item.created_at)}</span>
                  <span>更新：{formatTime(item.updated_at)}</span>
                  <span>{item.total_chars ?? 0} 字符</span>
                  <span>tags：{tagText(item.tags)}</span>
                </div>

                <div className="archives-actions">
                  <button
                    className="btn-sm primary"
                    type="button"
                    disabled={editing || item.editable === false || !canManage || itemRunning}
                    onClick={startEdit}
                  >
                    <Icon name="edit" />编辑
                  </button>
                  <button
                    className="btn-sm danger"
                    type="button"
                    disabled={editing || !deleteEnabled || !canManage || itemRunning}
                    onClick={openDelete}
                  >
                    <Icon name="trash" />删除
                  </button>
                  <label className="cfg-label" htmlFor="archive-target">
                    目标字符数
                  </label>
                  <input
                    id="archive-target"
                    className="input archives-target-input"
                    type="number"
                    min={minTarget}
                    max={maxTarget}
                    value={targetChars}
                    disabled={itemRunning}
                    onChange={(event) => setTargetChars(event.target.value)}
                  />
                  <button
                    className="btn-sm primary"
                    type="button"
                    disabled={
                      editing || itemRunning || !canManage || !summarizeAvailable || starting
                    }
                    onClick={() => void startSummarize()}
                  >
                    <Icon name="bot" />
                    {itemRunning ? '压缩中…' : 'AI 压缩'}
                  </button>
                  {itemRunning && (
                    <span className="muted small">
                      该条目正在压缩：期间禁止编辑 / 删除（避免人工写入与模型写入互相覆盖）
                    </span>
                  )}
                  {item.editable === false && (
                    <span className="muted small">
                      内部表禁止手工编辑（改坏会导致重复总结或漏总结），后端也会拒绝
                    </span>
                  )}
                  {!deleteEnabled && (
                    <span className="muted small">
                      删除已禁用：dashboard 插件配置 {DELETE_SWITCH} = false
                    </span>
                  )}
                </div>

                {conflict && (
                  <InlineAlert
                    tone="error"
                    title="档案已被他人修改，保存未生效"
                    actions={
                      <button
                        className="btn-sm primary"
                        type="button"
                        onClick={() => {
                          // 用服务端最新内容替换草稿（放弃我的修改），版本号随详情刷新一起更新
                          setDraft(conflict.value || '');
                          setTagsDraft((conflict.tags || []).join(', '));
                          setConflict(null);
                          void refetchDetail();
                        }}
                      >
                        重新加载（放弃我的修改）
                      </button>
                    }
                  >
                    服务端当前 version={conflict.version ?? 0}
                    {(item.version ?? 0) !== (conflict.version ?? 0) ? '（比你读取时更新）' : ''}
                    ，已拒绝写入以避免覆盖。你的修改仍保留在下面的编辑框里，不会自动提交。
                    <pre className="prompt-preview-body archives-conflict-body">{conflict.value || '（空）'}</pre>
                  </InlineAlert>
                )}

                {task &&
                  task.kind !== 'batch' &&
                  task.table === item.table_name &&
                  task.key === item.key && (
                    <InlineAlert
                      tone={task.status === 'failed' ? 'error' : task.status === 'running' ? 'info' : 'success'}
                      title={
                        task.status === 'running'
                          ? 'AI 压缩进行中…'
                          : task.status === 'failed'
                            ? '压缩失败，已保留原文'
                            : '压缩完成'
                      }
                    >
                      {task.status === 'running'
                        ? (task.chars_before ?? 0) +
                          ' 字 → 目标 ' +
                          (task.target_chars ?? 0) +
                          ' 字（后台任务，完成后自动刷新）'
                        : task.status === 'failed'
                          ? task.error || '模型未压到目标字数，原文未被修改'
                          : (task.chars_before ?? 0) +
                            ' → ' +
                            (task.chars_after ?? 0) +
                            ' 字（目标 ' +
                            (task.target_chars ?? 0) +
                            '，快照 id ' +
                            (task.snapshot_id ?? '无') +
                            '）'}
                    </InlineAlert>
                  )}

                {editing ? (
                  <>
                    <label className="cfg-label" htmlFor="archive-value">
                      档案正文（原样保存，不截断）
                    </label>
                    <textarea
                      id="archive-value"
                      className="input prompt-textarea archives-textarea"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                    />
                    <label className="cfg-label" htmlFor="archive-tags">
                      tags（逗号分隔）
                    </label>
                    <input
                      id="archive-tags"
                      className="input"
                      value={tagsDraft}
                      onChange={(event) => setTagsDraft(event.target.value)}
                    />
                    <div className="archives-actions">
                      <button
                        className="btn-sm primary"
                        type="button"
                        disabled={saving}
                        onClick={() => void saveEdit()}
                      >
                        <Icon name="save" />
                        {saving ? '保存中…' : '保存（带 version ' + (item.version ?? 0) + '）'}
                      </button>
                      <button
                        className="btn-sm"
                        type="button"
                        disabled={saving}
                        onClick={() => {
                          setEditing(false);
                          setConflict(null);
                        }}
                      >
                        取消
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="archives-value-head">
                      <strong>全文</strong>
                      <span className="muted small">详情接口返回完整内容，不做截断</span>
                    </div>
                    <pre className="prompt-preview-body archives-full">{item.value || '（空）'}</pre>
                  </>
                )}

                <div className="archives-history">
                  <div className="archives-value-head">
                    <strong>压缩历史</strong>
                    <span className="muted small">
                      只读快照（每条档案最多保留最近 10 份）。本期<b>不提供</b>「恢复到此快照」：
                      需要恢复时请查看全文后人工走编辑接口写回。
                    </span>
                  </div>
                  {snapshotsLoading && snapshots.length === 0 ? (
                    <p className="muted small">读取中…</p>
                  ) : snapshots.length === 0 ? (
                    <p className="muted small">还没有压缩快照</p>
                  ) : (
                    <table className="model-table archives-table">
                      <thead>
                        <tr>
                          <th>时间</th>
                          <th>压缩前</th>
                          <th>压缩后</th>
                          <th>来源</th>
                          <th>操作者</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {snapshots.map((row) => (
                          <tr key={row.id}>
                            <td className="muted small">{formatTime(row.created_at)}</td>
                            <td>{row.chars_before ?? row.total_chars ?? 0}</td>
                            <td>{row.chars_after ?? '—'}</td>
                            <td>{row.reason === 'auto' ? '自动压缩' : '手动压缩'}</td>
                            <td className="muted small">{row.operator_ip || '—'}</td>
                            <td>
                              <button
                                className="btn-sm"
                                type="button"
                                onClick={() => void viewSnapshot(row)}
                              >
                                <Icon name="eye" />
                                查看全文
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}

      <Modal open={deleteOpen} title="删除档案（不可恢复）" onClose={() => setDeleteOpen(false)}>
        {item && (
          <div className="archives-delete">
            <InlineAlert tone="error" title="硬删除，没有回收站">
              被删内容不可恢复；后端只会把前 500 字符写进 neobot.log 的审计日志。
            </InlineAlert>
            <p className="muted small">
              表 <code>{item.table_name}</code> · key <code>{item.key}</code> · version{' '}
              {item.version ?? 0} · {item.total_chars ?? 0} 字符
            </p>
            {item.note && <InlineAlert tone="warning" title="这张表的删除后果">{item.note}</InlineAlert>}
            <div className="archives-value-head">
              <strong>以下内容将被永久删除</strong>
            </div>
            <pre className="prompt-preview-body archives-delete-body">{item.value || '（空）'}</pre>
            {deleteError && <InlineAlert tone="error" title={deleteError} />}
            <label className="cfg-label" htmlFor="archive-delete-key">
              二次确认（二者任一）：输入完整 key，或勾选确认
            </label>
            <input
              id="archive-delete-key"
              className="input"
              value={deleteText}
              placeholder={'输入 key：' + item.key}
              data-autofocus
              onChange={(event) => setDeleteText(event.target.value)}
            />
            <label className="inline-check">
              <input
                type="checkbox"
                checked={deleteChecked}
                onChange={(event) => setDeleteChecked(event.target.checked)}
              />
              我已确认：删除后无法恢复
            </label>
            <div className="modal-actions">
              <button className="btn" type="button" disabled={deleting} onClick={() => setDeleteOpen(false)}>
                取消
              </button>
              <button
                className="btn danger"
                type="button"
                disabled={deleting || !(deleteChecked || deleteText.trim() === item.key)}
                onClick={() => void confirmDelete()}
              >
                <Icon name="trash" />
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={snapshotOpen}
        title={'压缩快照 #' + (snapshotDetail?.id ?? '')}
        onClose={() => setSnapshotOpen(false)}
      >
        <div className="archives-snapshot">
          <InlineAlert tone="info" title="只读快照（压缩前原文）">
            面板不提供「恢复到此快照」；确需恢复时请复制下面的内容，走编辑接口人工写回。
          </InlineAlert>
          {snapshotDetail && (
            <p className="muted small">
              {snapshotDetail.table_name}:{snapshotDetail.key} · {formatTime(snapshotDetail.created_at)} · 
              {snapshotDetail.total_chars ?? 0} 字符 · 
              {snapshotDetail.reason === 'auto' ? '自动压缩' : '手动压缩'} · 
              {snapshotDetail.operator_ip || '系统'}
            </p>
          )}
          {snapshotError && <InlineAlert tone="error" title={snapshotError} />}
          <pre className="prompt-preview-body archives-full">
            {snapshotDetail?.value || (snapshotError ? '（无法读取）' : '读取中…')}
          </pre>
        </div>
      </Modal>
    </div>
  );
}
