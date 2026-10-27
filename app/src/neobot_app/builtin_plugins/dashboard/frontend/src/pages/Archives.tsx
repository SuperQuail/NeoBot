// pages/Archives.tsx —— 档案管理（features/spec(2)）：查看 / 编辑 / 删除档案记忆
// 三栏：表清单（左）/ 条目列表（中）/ 单条详情（右），数据全部来自既有的 ArchiveMemoryService。
//
// 关键约束（照 spec §4 执行）：
// - 自动更新：只读列表定期读取；详情在编辑、写入或压缩时暂停，回包再次校验编辑世代；
//   编辑草稿与乐观锁基线独立固定，后台读取不能替用户接受新版本；
// - 删除：二次确认（输入 key **或** 勾选确认）+ 被删内容警示 + delete_enabled=false 时禁用；
//   内部表（memory_counter 等）突出警告文案，且禁止编辑；
// - 编辑：必须带 version；409 时提示「已被他人修改」并展示服务端当前内容，
//   由用户选择「重新加载」或「保留我的修改」，**不自动覆盖**。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import Icon from '../components/Icon';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import InlineAlert from '../components/ui/InlineAlert';
import { notify } from '../notifications/infoBar';
import { useQuery } from '../data/useQuery';
import { getQuerySnapshot, setQueryData } from '../data/queryCore';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ArchiveItemDetail, ArchiveSnapshot, ArchiveSummarizeTask } from '../api/types';
import PageHeader from '../components/ui/PageHeader';
import { confirmAction } from '../components/ui/ConfirmDialog';
import { useEditorGuard } from '../hooks/useEditorGuard';
import { isEditingSurfaceActive, useAutoRefresh } from '../hooks/useAutoRefresh';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import { PAGE_SIZE, parseTags } from './archives/archiveUtils';
import { ArchiveTableList, ArchiveEntryList } from './archives/ArchiveLists';
import { ArchiveTools } from './archives/ArchiveTools';
import { ArchiveContent } from './archives/ArchiveContent';
import { ArchiveDeleteDialog, ArchiveSnapshotDialog } from './archives/ArchiveDialogs';
import { useArchiveDetail } from './archives/useArchiveDetail';

/** localStorage 键：记住上次输入的目标字符数（R15 要求**不写回**全局配置） */
const TARGET_KEY = 'neobot-archives-target-chars';

/** 压缩任务轮询间隔（毫秒） */
const TASK_POLL_MS = 2000;

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

/** 后台列表读取失败时保留已有结果，由查询错误区提供重试。 */
async function readArchiveList<T extends { ok?: boolean; error?: string }>(
  queryKey: string,
  read: () => Promise<T | null>,
  failureMessage: string,
): Promise<T | null> {
  const result = await read();
  const previous = getQuerySnapshot<T>(queryKey).data;
  if ((!result || result.ok === false) && previous && previous.ok !== false) {
    throw new Error(result?.error || failureMessage);
  }
  return result;
}

export default function Archives() {
  const tablesQuery = useQuery(
    QK.archives,
    () => readArchiveList(QK.archives, () => api.archives(), '档案表清单读取失败'),
    { interval: POLL.archives },
  );
  const payload = tablesQuery.data;
  const tables = useMemo(() => payload?.items || [], [payload]);
  // 删除开关关着时提前禁用按钮，避免用户点了才吃 403
  const deleteEnabled = payload?.delete_enabled === true;
  const canManage = payload?.can_manage === true;
  const maxTotalChars = Number(payload?.max_total_chars || 0);

  const [table, setTable] = useState('');
  const selectedTable = tables.find((entry) => entry.table_name === table);
  const [keyInput, setKeyInput] = useState('');
  const [valueInput, setValueInput] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [overLimitInput, setOverLimitInput] = useState(false);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<ArchiveFilters>(EMPTY_FILTERS);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [key, setKey] = useState('');
  const [showDetail, setShowDetail] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const detailBodyRef = useRef<HTMLDivElement>(null);
  const previousDetailMode = useRef(showDetail);

  useEffect(() => {
    if (previousDetailMode.current === showDetail) return;
    previousDetailMode.current = showDetail;
    if (!window.matchMedia?.('(max-width: 760px)').matches) return;
    (showDetail ? detailBodyRef.current : searchInputRef.current)?.focus({ preventScroll: true });
  }, [showDetail]);

  const [editing, setEditing] = useState(false);
  const [editBase, setEditBase] = useState<ArchiveItemDetail | null>(null);
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
  const taskRunning = task?.status === 'running';
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
  const busy = saving || deleting || starting || taskRunning;
  const detailProtected = editing || busy || deleteOpen || snapshotOpen;

  // 表清单到达后默认选中第一张（用户已选且仍存在时不动）
  useEffect(() => {
    if (tables.length === 0 || detailProtected) return;
    if (table && tables.some((item) => item.table_name === table)) return;
    setTable(tables[0].table_name);
  }, [tables, table, detailProtected]);

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
        ? readArchiveList(
            QK.archiveItems(itemsQueryKey),
            () =>
              api.archiveItems({
                table,
                keyQuery: filters.keyQuery,
                valueQuery: filters.valueQuery,
                tags: filters.tags,
                limit: PAGE_SIZE,
                offset,
                overLimitOnly: filters.overLimitOnly,
              }),
            '档案条目读取失败',
          )
        : Promise.resolve(null),
    { deps: [itemsQueryKey] },
  );
  const items = useMemo(() => itemsQuery.data?.items || [], [itemsQuery.data]);
  const hasMore = itemsQuery.data?.has_more === true;

  const detailQuery = useArchiveDetail(table, key, detailProtected);
  const detailResult = detailQuery.data;
  const item = editing ? editBase : detailResult?.ok ? detailResult.data : null;
  const detailError = editing
    ? ''
    : (detailQuery.error ? '读取档案失败' : '') ||
      (detailResult && !detailResult.ok ? detailResult.error || '读取档案失败' : '');
  const dirty =
    editing &&
    (draft !== (editBase?.value ?? '') ||
      JSON.stringify(parseTags(tagsDraft)) !== JSON.stringify(editBase?.tags ?? []));
  useEditorGuard(dirty, saving || deleting || starting);

  const { refetch: refetchTables } = tablesQuery;
  const { refetch: refetchItems } = itemsQuery;
  const {
    refetch: refetchDetail,
    refetchAutomatically: refetchDetailAutomatically,
    refetchAfterWrite: refetchDetailAfterWrite,
  } = detailQuery;

  // ── AI 压缩：压缩历史 / 目标默认值 / 任务轮询 ──────────────────

  /** 当前条目的压缩历史（只读快照；不提供恢复入口） */
  const snapshotsRequest = useRef(0);
  const loadSnapshots = useCallback(async () => {
    const request = ++snapshotsRequest.current;
    if (!table || !key) {
      setSnapshots([]);
      setSnapshotsLoading(false);
      return;
    }
    setSnapshotsLoading(true);
    const data = await api.archiveSnapshots(table, key);
    if (request !== snapshotsRequest.current) return;
    setSnapshotsLoading(false);
    setSnapshots(data?.items || []);
  }, [table, key]);
  const cancelSnapshotRead = useCallback(() => {
    snapshotsRequest.current++;
  }, []);

  useEffect(() => {
    setSnapshots([]);
    void loadSnapshots();
    return cancelSnapshotRead;
  }, [loadSnapshots, cancelSnapshotRead]);

  useAutoRefresh(
    async () => {
      const reads: Promise<unknown>[] = [refetchTables()];
      if (table) reads.push(refetchItems());
      if (key && !detailProtected && !isEditingSurfaceActive()) {
        reads.push(refetchDetailAutomatically(), loadSnapshots());
      }
      await Promise.all(reads);
    },
    { enabled: !busy, interval: POLL.editor, pauseWhileEditing: false },
  );

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
          notify(
            next.message ||
              '批量压缩完成：成功 ' + (next.succeeded ?? 0) + ' 条 / 失败 ' + (next.failed ?? 0) + ' 条',
            (next.failed ?? 0) > 0 ? 'warn' : 'ok',
          );
        } else if (next.status === 'done') {
          notify(
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
          notify(next.error || '压缩失败，已保留原文', 'err');
        }
      })();
    }, TASK_POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [task]);

  // 终态提交后再读详情，避免仍处于 running 的旧渲染拦截写后读取。
  const refreshedTask = useRef<ArchiveSummarizeTask | null>(null);
  useEffect(() => {
    if (!task || (task.status !== 'done' && task.status !== 'failed') || refreshedTask.current === task)
      return;
    refreshedTask.current = task;
    void Promise.all([refetchDetailAfterWrite(), refetchItems(), refetchTables(), loadSnapshots()]);
  }, [task, refetchDetailAfterWrite, refetchItems, refetchTables, loadSnapshots]);

  /** 读取并校验目标输入框；非法时提示并返回 null */
  function targetValue(): number | null {
    const value = Number(targetChars);
    if (!Number.isFinite(value) || value <= 0) {
      notify('请先填写目标字符数', 'err');
      return null;
    }
    return Math.trunc(value);
  }

  async function startSummarize() {
    if (!item || !canManage || !summarizeAvailable || starting || itemRunning || editing) return;
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
      notify(result.error || '触发压缩失败', 'err');
      return;
    }
    setTask(result.data);
    if (result.data.status === 'noop') {
      notify(result.data.message || '当前字数已不大于目标，无需压缩', 'info');
      return;
    }
    notify(result.data.message || '已开始压缩', 'ok');
  }

  async function startBatchSummarize() {
    if (!canManage || !summarizeAvailable || starting || taskRunning) return;
    const target = targetValue();
    if (target === null) return;
    setStarting(true);
    const result = await api.archiveSummarizeOverLimit({ target_chars: target });
    setStarting(false);
    if (!result.ok || !result.data) {
      notify(result.error || '批量触发失败', 'err');
      return;
    }
    setTask(result.data);
    notify(result.data.message || '已开始批量压缩', 'ok');
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

  async function pickTable(name: string) {
    if (name === table) return;
    if (saving) return;
    if (
      editing &&
      !(await confirmAction({
        title: '放弃未保存的档案',
        description: '切换档案表会丢弃当前修改。',
        confirmLabel: '放弃修改',
        danger: true,
      }))
    )
      return;
    setTable(name);
    setKey('');
    setShowDetail(false);
    setEditing(false);
    setConflict(null);
    setOffset(0);
    setFilters(EMPTY_FILTERS);
    setKeyInput('');
    setValueInput('');
    setTagsInput('');
    setOverLimitInput(false);
  }

  async function pickItem(next: string) {
    if (next === key) {
      setShowDetail(true);
      return;
    }
    if (saving) return;
    // 编辑态切换条目会丢草稿：先确认（避免误点导致白改）
    if (
      editing &&
      !(await confirmAction({
        title: '放弃未保存的档案',
        description: '切换条目会丢弃当前修改。',
        confirmLabel: '放弃修改',
        danger: true,
      }))
    )
      return;
    setKey(next);
    setShowDetail(true);
    setEditing(false);
    setConflict(null);
  }

  function applyFilters() {
    setOffset(0);
    setFiltersExpanded(false);
    searchInputRef.current?.focus({ preventScroll: true });
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
    if (!item || item.editable === false || !canManage || itemRunning) return;
    setEditBase(item);
    setDraft(item.value || '');
    setTagsDraft((item.tags || []).join(', '));
    setConflict(null);
    setEditing(true);
  }

  async function saveEdit() {
    if (!item || !canManage || item.editable === false || itemRunning || saving) return;
    if (!draft.trim()) {
      notify('档案内容不能为空（后端同样拒绝空内容）', 'err');
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
      notify(result.data?.message || '档案已保存', 'ok');
      if (result.data) setQueryData(QK.archiveItem(item.table_name, item.key), result);
      setEditing(false);
      setConflict(null);
      await refetchDetailAfterWrite();
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
    notify(result.error || '保存失败', 'err');
  }

  function openDelete() {
    setDeleteText('');
    setDeleteChecked(false);
    setDeleteError('');
    setDeleteOpen(true);
  }

  async function confirmDelete() {
    if (!item || !canManage || !deleteEnabled || itemRunning || deleting) return;
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
      notify(result.data?.message || '档案已删除', 'ok');
      setDeleteOpen(false);
      setKey('');
      setShowDetail(false);
      setEditing(false);
      await Promise.all([refetchItems(), refetchTables()]);
      return;
    }
    setDeleteError(result.error || '删除失败');
  }

  /** 当前条目是否正在被压缩：running 期间禁用同一条目的编辑 / 删除（§4.10.1） */
  const itemRunning =
    taskRunning === true &&
    (task?.kind === 'batch'
      ? (task?.items || []).some(
          (entry) =>
            entry.status === 'running' && entry.table === item?.table_name && entry.key === item?.key,
        )
      : task?.table === item?.table_name && task?.key === item?.key);

  const unavailable = payload === null && !tablesQuery.loading;
  const loadError = !unavailable
    ? tablesQuery.error || (payload?.ok === false ? payload.error || '档案表清单读取失败' : '')
    : '';
  const itemsError = table
    ? (itemsQuery.error === 'no-data' ? '档案条目读取失败' : itemsQuery.error) ||
      (itemsQuery.data?.ok === false ? itemsQuery.data.error || '档案条目读取失败' : '')
    : '';
  const filterCount = [filters.keyQuery, filters.valueQuery, filters.tags, filters.overLimitOnly].filter(
    Boolean,
  ).length;

  return (
    <div className="page page--viewport archives-page">
      <PageHeader title="档案管理" />
      <ArchiveTools
        task={task}
        taskRunning={taskRunning}
        maxTotalChars={maxTotalChars}
        deleteEnabled={deleteEnabled}
        canManage={canManage}
        summarizeAvailable={summarizeAvailable}
        minTarget={minTarget}
        maxTarget={maxTarget}
        targetChars={targetChars}
        starting={starting}
        onTargetChange={setTargetChars}
        onStartBatch={() => void startBatchSummarize()}
      />

      {loadError && (
        <InlineAlert
          tone="error"
          title={loadError}
          actions={
            <Button size="sm" onClick={() => void refetchTables()}>
              重试表清单
            </Button>
          }
        />
      )}

      {unavailable ? (
        <EmptyState icon="archive" title="档案服务不可用">
          <p>后端未注入 archive_memory_service，或数据库未就绪。</p>
          <Button size="sm" onClick={() => void refetchTables()}>
            重新读取
          </Button>
        </EmptyState>
      ) : (
        <div className={'viewer-layout archive-workspace' + (showDetail ? ' show-detail' : '')}>
          <ArchiveTableList
            tables={tables}
            table={table}
            loading={tablesQuery.loading}
            hasData={Boolean(tablesQuery.data)}
            onSelect={(name) => void pickTable(name)}
          />

          <section className="card archives-items" aria-label="档案条目列表">
            <div className="card-head archive-items-heading">
              <h3 className="archive-items-title">条目</h3>
              <label className="archive-table-picker">
                <span className="sr-only">档案表</span>
                <select
                  className="input"
                  value={table}
                  onChange={(event) => void pickTable(event.target.value)}
                >
                  {tables.map((entry) => (
                    <option key={entry.table_name} value={entry.table_name}>
                      {entry.table_name} · {entry.count ?? 0} 条
                    </option>
                  ))}
                </select>
              </label>
              <span className="muted small">{items.length} 条</span>
            </div>

            {selectedTable?.note && (
              <p className="archive-table-description" title={selectedTable.note}>
                {selectedTable.note}
              </p>
            )}

            <form
              className="archives-filters"
              onSubmit={(event) => {
                event.preventDefault();
                applyFilters();
              }}
            >
              <div className="archive-search-row">
                <input
                  ref={searchInputRef}
                  className="input"
                  aria-label="搜索档案 key"
                  value={keyInput}
                  placeholder="搜索档案 key…"
                  onChange={(event) => setKeyInput(event.target.value)}
                />
                <Button size="sm" type="submit" aria-label="查询" title="查询">
                  <Icon name="search" size={16} />
                </Button>
                <Button
                  size="sm"
                  type="button"
                  aria-expanded={filtersExpanded}
                  aria-controls="archive-advanced-filters"
                  onClick={() => setFiltersExpanded((value) => !value)}
                >
                  <SlidersHorizontal size={15} aria-hidden="true" />
                  筛选{filterCount > 0 ? ` ${filterCount}` : ''}
                </Button>
              </div>
              {filtersExpanded && (
                <div className="archive-filter-fields" id="archive-advanced-filters">
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
                    <Button size="sm" type="button" onClick={clearFilters}>
                      重置
                    </Button>
                    <Button
                      size="sm"
                      type="button"
                      disabled={itemsQuery.loading}
                      onClick={() => void refetchItems()}
                    >
                      <Icon name="refresh" />
                      刷新
                    </Button>
                  </div>
                </div>
              )}
            </form>

            {itemsError && (
              <InlineAlert
                tone="error"
                title={itemsError}
                actions={
                  <Button size="sm" onClick={() => void refetchItems()}>
                    重试条目列表
                  </Button>
                }
              />
            )}
            <ArchiveEntryList
              items={items}
              selectedKey={key}
              loading={itemsQuery.loading}
              offset={offset}
              hasMore={hasMore}
              onSelect={(next) => void pickItem(next)}
              onPageChange={setOffset}
            />
          </section>

          <section className="card archives-detail" aria-label="档案详情">
            <div className="viewer-mobile-back">
              <Button variant="ghost" size="sm" onClick={() => setShowDetail(false)}>
                <Icon name="back" size={15} />
                返回档案列表
              </Button>
            </div>
            <div
              ref={detailBodyRef}
              className="archive-detail-body viewer-body"
              tabIndex={-1}
              aria-label="档案正文与详情"
            >
              {!key ? (
                <EmptyState icon="archive" title="选择一条档案">
                  从条目列表查看完整内容、标签与压缩历史。
                </EmptyState>
              ) : detailError ? (
                <InlineAlert
                  tone="error"
                  title={detailError}
                  actions={
                    <Button size="sm" type="button" onClick={() => void refetchDetail()}>
                      重新读取
                    </Button>
                  }
                />
              ) : !item ? (
                detailQuery.loading ? (
                  <PanelSkeleton label="正在读取档案详情…" kind="text" rows={8} />
                ) : (
                  <EmptyState compact>没有该档案</EmptyState>
                )
              ) : (
                <ArchiveContent
                  item={item}
                  canManage={canManage}
                  deleteEnabled={deleteEnabled}
                  editing={editing}
                  saving={saving}
                  draft={draft}
                  tagsDraft={tagsDraft}
                  conflict={conflict}
                  task={task}
                  itemRunning={itemRunning}
                  summarizeAvailable={summarizeAvailable}
                  starting={starting}
                  targetChars={targetChars}
                  minTarget={minTarget}
                  maxTarget={maxTarget}
                  snapshots={snapshots}
                  snapshotsLoading={snapshotsLoading}
                  onStartEdit={startEdit}
                  onCancelEdit={() => {
                    setEditing(false);
                    setConflict(null);
                  }}
                  onReloadConflict={() => {
                    if (!conflict) return;
                    setEditBase(conflict);
                    setDraft(conflict.value || '');
                    setTagsDraft((conflict.tags || []).join(', '));
                    setQueryData(QK.archiveItem(table, key), {
                      ok: true,
                      data: conflict,
                      error: null,
                      status: 200,
                    });
                    setConflict(null);
                    void refetchDetail();
                  }}
                  onDraftChange={setDraft}
                  onTagsChange={setTagsDraft}
                  onSave={() => void saveEdit()}
                  onDelete={openDelete}
                  onTargetChange={setTargetChars}
                  onSummarize={() => void startSummarize()}
                  onViewSnapshot={(snapshot) => void viewSnapshot(snapshot)}
                />
              )}
            </div>
          </section>
        </div>
      )}

      <ArchiveDeleteDialog
        deleteOpen={deleteOpen}
        item={item}
        deleteError={deleteError}
        deleteText={deleteText}
        deleteChecked={deleteChecked}
        deleting={deleting}
        canManage={canManage}
        deleteEnabled={deleteEnabled}
        itemRunning={itemRunning}
        onClose={() => setDeleteOpen(false)}
        onTextChange={setDeleteText}
        onCheckedChange={setDeleteChecked}
        onConfirm={() => void confirmDelete()}
      />
      <ArchiveSnapshotDialog
        snapshotOpen={snapshotOpen}
        snapshotDetail={snapshotDetail}
        snapshotError={snapshotError}
        onClose={() => setSnapshotOpen(false)}
      />
    </div>
  );
}
