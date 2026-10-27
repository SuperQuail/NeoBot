// Archives.test.tsx —— 档案页（spec(2)）：表清单 / 条目筛选分页 / 详情全文 / 乐观锁编辑 / 删除二次确认
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Archives from '../pages/Archives';
import { confirmAction } from '../components/ui/ConfirmDialog';
import { api } from '../api/endpoints';
import { clearQueries, getQuerySnapshot } from '../data/queryCore';
import { POLL, QK } from '../data/queryKeys';
import type {
  ArchiveItemDetail,
  ArchiveItemsPayload,
  ArchiveSnapshot,
  ArchiveSummarizeTask,
  ArchivesPayload,
  Result,
} from '../api/types';

vi.mock('../components/ui/ConfirmDialog', () => ({ confirmAction: vi.fn() }));

vi.mock('../api/endpoints', () => ({
  api: {
    archives: vi.fn(),
    archiveItems: vi.fn(),
    archiveItem: vi.fn(),
    archiveUpdate: vi.fn(),
    archiveDelete: vi.fn(),
    archiveSummarize: vi.fn(),
    archiveSummarizeStatus: vi.fn(),
    archiveSummarizeOverLimit: vi.fn(),
    archiveSnapshots: vi.fn(),
    archiveSnapshot: vi.fn(),
  },
}));

const archives = vi.mocked(api.archives);
const archiveItems = vi.mocked(api.archiveItems);
const archiveItem = vi.mocked(api.archiveItem);
const archiveUpdate = vi.mocked(api.archiveUpdate);
const archiveDelete = vi.mocked(api.archiveDelete);
const archiveSummarize = vi.mocked(api.archiveSummarize);
const archiveSummarizeStatus = vi.mocked(api.archiveSummarizeStatus);
const archiveSnapshots = vi.mocked(api.archiveSnapshots);
const archiveSnapshot = vi.mocked(api.archiveSnapshot);

function ok<T>(data: T): Result<T> {
  return { ok: true, data, error: null, status: 200 };
}

function fail<T>(error: string, status: number, data: T | null = null): Result<T> {
  return { ok: false, data, error, status };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function openArchiveWithClock() {
  vi.useFakeTimers();
  // 假时钟只推进页面轮询；事件后的 React 更新由 act 等待，避免 user-event 的内部等待计时器。
  const user = {
    click: async (element: HTMLElement) => {
      await act(async () => {
        fireEvent.click(element);
      });
    },
    clear: async (element: HTMLElement) => {
      await act(async () => {
        fireEvent.change(element, { target: { value: '' } });
      });
    },
    type: async (element: HTMLElement, value: string) => {
      await act(async () => {
        fireEvent.change(element, { target: { value: (element as HTMLInputElement).value + value } });
      });
    },
  };
  await act(async () => {
    render(<Archives />);
  });
  await user.click(screen.getByRole('button', { name: 'u-1' }));
  expect(screen.getByText('完整档案正文')).toBeInTheDocument();
  return user;
}

async function advanceRefresh() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL.editor);
  });
}

const TABLES: ArchivesPayload = {
  ok: true,
  max_total_chars: 5000,
  min_target_chars: 200,
  max_target_chars: 5000,
  summarize_available: true,
  delete_enabled: false,
  can_manage: true,
  items: [
    {
      table_name: 'user_profile',
      count: 3,
      max_value_chars: 120,
      over_limit_count: 1,
      internal: false,
      note: '用户长期档案。删除后模型将忘记该用户的历史设定。',
    },
    {
      table_name: 'memory_counter',
      count: 2,
      max_value_chars: 9000,
      over_limit_count: 2,
      internal: true,
      note: '自动总结的内部计数表（待总结消息）。删除会把该会话的自动总结计数清零。',
    },
  ],
};

const ITEMS: ArchiveItemsPayload = {
  ok: true,
  table: 'user_profile',
  limit: 50,
  offset: 0,
  has_more: true,
  items: [
    {
      table_name: 'user_profile',
      key: 'u-1',
      preview: '预览内容',
      preview_truncated: false,
      total_chars: 6,
      tags: ['重要'],
      version: 3,
      created_at: '2026-09-01T10:00:00',
      updated_at: '2026-09-02T11:00:00',
      internal: false,
    },
  ],
};

const DETAIL: ArchiveItemDetail = {
  table_name: 'user_profile',
  key: 'u-1',
  value: '完整档案正文',
  preview: '完整档案正文',
  total_chars: 6,
  tags: ['重要'],
  version: 3,
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-02T11:00:00',
  internal: false,
  editable: true,
  note: '用户长期档案。删除后模型将忘记该用户的历史设定。',
};

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  vi.mocked(confirmAction).mockResolvedValue(true);
  archives.mockResolvedValue(TABLES);
  archiveItems.mockResolvedValue(ITEMS);
  archiveItem.mockResolvedValue(ok(DETAIL));
  archiveUpdate.mockResolvedValue(ok({ ...DETAIL, version: 4, message: '档案已保存' }));
  archiveDelete.mockResolvedValue(ok({ message: '档案已删除（可在 neobot.log 中追溯被删内容）' }));
  archiveSummarize.mockResolvedValue(
    ok<ArchiveSummarizeTask>({
      ok: true,
      status: 'running',
      task_id: 'task-1',
      kind: 'single',
      table: 'user_profile',
      key: 'u-1',
      target_chars: 5000,
      chars_before: 12000,
      message: '已开始压缩（12000 → 目标 5000 字）',
    }),
  );
  archiveSummarizeStatus.mockResolvedValue(null);
  archiveSnapshots.mockResolvedValue({ ok: true, items: [] });
  archiveSnapshot.mockResolvedValue({ ok: false, error: '没有该快照' });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Archives 档案页', () => {
  it('渲染表清单（条目数 / 最大长度 / 超限 / 内部表警告）并默认选中第一张表', async () => {
    render(<Archives />);

    expect(await screen.findByText('user_profile')).toBeInTheDocument();
    expect(screen.getByText('memory_counter')).toBeInTheDocument();
    expect(screen.getByText('内部表')).toBeInTheDocument();
    expect(screen.getByText('2 条超限')).toBeInTheDocument();
    expect(screen.getByText(/自动总结的内部计数表/)).toBeInTheDocument();

    // 默认选中的表用于拉条目列表
    await waitFor(() =>
      expect(archiveItems).toHaveBeenCalledWith(
        expect.objectContaining({ table: 'user_profile', limit: 50 }),
      ),
    );
    expect(await screen.findByText('u-1')).toBeInTheDocument();
  });

  it('详情展示全文与 version，delete_enabled=false 时删除按钮禁用并说明开关名', async () => {
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));

    expect(await screen.findByText('完整档案正文')).toBeInTheDocument();
    expect(screen.getByText('version 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /删除/ })).toBeDisabled();
    expect(screen.getAllByText(/allow_archive_delete/).length).toBeGreaterThan(0);
  });

  it('档案信息按需展开，长 key、标签、时间与保护原因完整保留，操作组仍可单独访问', async () => {
    const longKey = `user:${'long-key-'.repeat(30)}`;
    const longTag = '需要保留的完整标签'.repeat(30);
    archiveItems.mockResolvedValue({ ...ITEMS, items: [{ ...ITEMS.items![0], key: longKey }] });
    archiveItem.mockResolvedValue(ok({ ...DETAIL, key: longKey, tags: [longTag, '重要'] }));
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: longKey }));
    await screen.findByText('完整档案正文');

    const summary = screen.getByLabelText('档案信息');
    const information = summary.closest('details') as HTMLDetailsElement;
    expect(information).not.toHaveAttribute('open');
    expect(within(summary).getByText(longKey)).toHaveAttribute('title', longKey);
    expect(within(information).getByText('档案表')).not.toBeVisible();
    expect(
      within(screen.getByRole('group', { name: '档案编辑操作' })).getByRole('button', { name: '编辑' }),
    ).toBeEnabled();
    const compression = screen.getByRole('group', { name: 'AI 压缩操作' });
    expect(within(compression).getByLabelText('目标字符数')).toHaveValue(5000);
    expect(within(compression).getByRole('button', { name: 'AI 压缩' })).toBeEnabled();

    await user.click(summary);
    expect(information).toHaveAttribute('open');
    expect(within(information).getByText('档案表')).toBeVisible();
    expect(within(information).getByText('user_profile')).toBeVisible();
    expect(within(information).getByText(`${longTag}, 重要`)).toBeVisible();
    expect(within(information).getByText('2026-09-01 10:00:00')).toBeVisible();
    expect(within(information).getByText('2026-09-02 11:00:00')).toBeVisible();
    expect(within(information).getByText('allow_archive_delete')).toBeVisible();
    expect(within(information).getByText(DETAIL.note!)).toBeVisible();
  });

  it('删除需要二次确认：未确认时按钮禁用，输入 key 后才提交且带 version', async () => {
    archives.mockResolvedValue({ ...TABLES, delete_enabled: true });
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    await user.click(screen.getByRole('button', { name: /删除/ }));

    // 被删内容的明显警示
    expect(await screen.findByText(/硬删除，没有回收站/)).toBeInTheDocument();
    expect(screen.getAllByText('完整档案正文').length).toBeGreaterThan(0);

    const confirm = screen.getByRole('button', { name: /确认删除/ });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(/二次确认/), 'u-1');
    expect(screen.getByRole('button', { name: /确认删除/ })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: /确认删除/ }));

    await waitFor(() =>
      expect(archiveDelete).toHaveBeenCalledWith({ table: 'user_profile', key: 'u-1', version: 3 }),
    );
  });

  it('编辑提交带 version；409 冲突时展示服务端当前内容且不自动覆盖，可重新加载', async () => {
    archiveUpdate.mockResolvedValue(
      fail('档案已被其它会话修改（当前 version=5），请重新读取后再保存', 409, {
        ...DETAIL,
        current: { ...DETAIL, version: 5, value: '服务端最新内容' },
        actual_version: 5,
      }),
    );
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    await user.click(screen.getByRole('button', { name: /编辑/ }));
    const textarea = screen.getByLabelText('档案正文（原样保存，不截断）');
    await user.clear(textarea);
    await user.type(textarea, '我的修改');
    archiveItem.mockResolvedValue(ok({ ...DETAIL, version: 5, value: '服务端最新内容' }));

    await user.click(screen.getByRole('button', { name: /保存（带 version 3）/ }));

    await waitFor(() =>
      expect(archiveUpdate).toHaveBeenCalledWith({
        table: 'user_profile',
        key: 'u-1',
        value: '我的修改',
        tags: ['重要'],
        version: 3,
      }),
    );

    // 409：提示「已被他人修改」+ 服务端当前内容，且**不**自动覆盖
    expect(await screen.findByText(/档案已被他人修改，保存未生效/)).toBeInTheDocument();
    expect(screen.getByText(/当前 version=5/)).toBeInTheDocument();
    expect(screen.getByText('服务端最新内容')).toBeInTheDocument();
    expect(archiveUpdate).toHaveBeenCalledTimes(1);
    expect(textarea).toHaveValue('我的修改');

    // 冲突后重读不能替用户接受 version 5；再次保存仍使用原版本。
    await user.click(screen.getByRole('button', { name: /保存（带 version 3）/ }));
    expect(archiveUpdate).toHaveBeenLastCalledWith(expect.objectContaining({ version: 3 }));

    // 重新加载 = 放弃我的修改
    await user.click(screen.getByRole('button', { name: /重新加载（放弃我的修改）/ }));
    await waitFor(() =>
      expect((screen.getByLabelText('档案正文（原样保存，不截断）') as HTMLTextAreaElement).value).toBe(
        '服务端最新内容',
      ),
    );
    expect(screen.getByRole('button', { name: /保存（带 version 5）/ })).toBeInTheDocument();
  });

  it('切换档案表先确认，取消时保留当前编辑草稿', async () => {
    vi.mocked(confirmAction).mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');
    await user.click(screen.getByRole('button', { name: /编辑/ }));
    const editor = screen.getByLabelText('档案正文（原样保存，不截断）');
    await user.clear(editor);
    await user.type(editor, '尚未保存的档案');
    await user.click(screen.getByText('memory_counter'));
    expect(confirmAction).toHaveBeenCalledTimes(1);
    expect(editor).toHaveValue('尚未保存的档案');
    expect(archiveItems).toHaveBeenLastCalledWith(expect.objectContaining({ table: 'user_profile' }));
    await user.click(screen.getByText('memory_counter'));
    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(expect.objectContaining({ table: 'memory_counter' })),
    );
    expect(screen.queryByLabelText('档案正文（原样保存，不截断）')).not.toBeInTheDocument();
  });

  it('内部表禁止编辑（后端也会拒绝）', async () => {
    archiveItems.mockImplementation(async (query) =>
      query.table === 'memory_counter'
        ? {
            ...ITEMS,
            table: 'memory_counter',
            items: [{ ...(ITEMS.items || [])[0], table_name: 'memory_counter', key: 'counter-1' }],
          }
        : ITEMS,
    );
    archiveItem.mockResolvedValue(
      ok({
        ...DETAIL,
        table_name: 'memory_counter',
        key: 'counter-1',
        internal: true,
        editable: false,
        value: '{}',
      }),
    );
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByText('memory_counter'));
    await user.click(await screen.findByRole('button', { name: 'counter-1' }));

    expect(await screen.findByRole('button', { name: /编辑/ })).toBeDisabled();
    expect(screen.getByText(/内部表禁止手工编辑/)).toBeInTheDocument();
  });

  it('按 key / 内容筛选与分页都会带上参数重新请求', async () => {
    const user = userEvent.setup();
    render(<Archives />);
    await screen.findByText('u-1');

    expect(screen.queryByLabelText('内容包含')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '筛选' }));
    await user.type(screen.getByLabelText('key 包含'), 'u-1');
    await user.type(screen.getByLabelText('内容包含'), '正文{Enter}');

    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(
        expect.objectContaining({ table: 'user_profile', keyQuery: 'u-1', valueQuery: '正文', offset: 0 }),
      ),
    );
    expect(screen.queryByLabelText('内容包含')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '搜索档案 key' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 })),
    );
  });

  it('快速搜索无需展开筛选，按 Enter 查询 key 并保留高级条件入口', async () => {
    const user = userEvent.setup();
    render(<Archives />);
    await screen.findByText('u-1');

    await user.type(screen.getByRole('textbox', { name: '搜索档案 key' }), 'u-1{Enter}');

    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(
        expect.objectContaining({
          table: 'user_profile',
          keyQuery: 'u-1',
          valueQuery: '',
          tags: '',
          offset: 0,
        }),
      ),
    );
    expect(screen.getByRole('button', { name: '筛选 1' })).toHaveAttribute('aria-expanded', 'false');
    await user.click(screen.getByRole('button', { name: '筛选 1' }));
    expect(screen.getByLabelText('key 包含')).toHaveValue('u-1');
  });

  it('自动更新撤销管理权限、移除表时仍保留当前草稿与基线，并禁止编辑保存', async () => {
    const user = await openArchiveWithClock();
    await user.click(screen.getByRole('button', { name: /编辑/ }));
    const editor = screen.getByLabelText('档案正文（原样保存，不截断）');
    await user.clear(editor);
    await user.type(editor, '保留的修改');

    archives.mockResolvedValue({ ...TABLES, can_manage: false, items: [TABLES.items![1]] });
    await advanceRefresh();

    const save = screen.getByRole('button', { name: /保存（带 version 3）/ });
    expect(save).toBeDisabled();
    expect(editor).toHaveValue('保留的修改');
    expect(editor).toHaveAttribute('readonly');
    expect(screen.getByLabelText('tags（逗号分隔）')).toHaveAttribute('readonly');
    await user.click(save);
    expect(archiveUpdate).not.toHaveBeenCalled();
    expect(archiveItem).toHaveBeenCalledTimes(1);
    expect(archiveItems).toHaveBeenLastCalledWith(expect.objectContaining({ table: 'user_profile' }));
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('每个自动更新周期读取表、条目、详情和历史，页头不再放刷新按钮', async () => {
    await openArchiveWithClock();
    expect(archives).toHaveBeenCalledTimes(1);
    expect(archiveItems).toHaveBeenCalledTimes(1);
    expect(archiveItem).toHaveBeenCalledTimes(1);
    expect(archiveSnapshots).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();

    archives.mockResolvedValue({ ...TABLES, items: [{ ...TABLES.items![0], count: 4 }] });
    archiveItems.mockResolvedValue({ ...ITEMS, items: [{ ...ITEMS.items![0], preview: '自动更新的预览' }] });
    archiveItem.mockResolvedValue(ok({ ...DETAIL, value: '自动更新的全文', version: 4 }));
    await advanceRefresh();

    expect(archives).toHaveBeenCalledTimes(2);
    expect(archiveItems).toHaveBeenCalledTimes(2);
    expect(archiveItem).toHaveBeenCalledTimes(2);
    expect(archiveSnapshots).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: /user_profile，4 条/ })).toBeInTheDocument();
    expect(screen.getByText('自动更新的预览')).toBeInTheDocument();
    expect(screen.getByText('自动更新的全文')).toBeInTheDocument();
    expect(screen.getByText('version 4')).toBeInTheDocument();
  });

  it.each(['success', 'error'] as const)(
    '编辑开始前发出的自动详情 %s 回包不覆盖草稿或版本基线',
    async (outcome) => {
      const user = await openArchiveWithClock();
      const pending = deferred<Result<ArchiveItemDetail>>();
      archiveItem.mockReturnValueOnce(pending.promise);
      await advanceRefresh();
      expect(archiveItem).toHaveBeenCalledTimes(2);

      await user.click(screen.getByRole('button', { name: '编辑' }));
      const editor = screen.getByLabelText('档案正文（原样保存，不截断）');
      await user.clear(editor);
      await user.type(editor, '回包前写下的草稿');
      await act(async () => {
        pending.resolve(
          outcome === 'success'
            ? ok({ ...DETAIL, value: '后台的新版本', version: 8 })
            : fail('后台读取失败', 500),
        );
      });

      expect(editor).toHaveValue('回包前写下的草稿');
      expect(screen.getByRole('button', { name: '保存（带 version 3）' })).toBeInTheDocument();
      expect(
        getQuerySnapshot<Result<ArchiveItemDetail>>(QK.archiveItem('user_profile', 'u-1')).data?.data
          ?.version,
      ).toBe(3);
      expect(screen.queryByText('后台的新版本')).not.toBeInTheDocument();
      expect(screen.queryByText('后台读取失败')).not.toBeInTheDocument();
      expect(confirmAction).not.toHaveBeenCalled();
      await user.click(screen.getByRole('button', { name: '保存（带 version 3）' }));
      expect(archiveUpdate).toHaveBeenLastCalledWith(
        expect.objectContaining({ version: 3, value: '回包前写下的草稿' }),
      );

      archiveItem.mockResolvedValue(ok({ ...DETAIL, value: '后续自动更新', version: 9 }));
      await advanceRefresh();
      expect(screen.getByText('后续自动更新')).toBeInTheDocument();
      expect(screen.getByText('version 9')).toBeInTheDocument();
    },
  );

  it('保存未结束时暂停自动读取，写后继续刷新列表并显示确认后的版本', async () => {
    const user = await openArchiveWithClock();
    await user.click(screen.getByRole('button', { name: '编辑' }));
    const editor = screen.getByLabelText('档案正文（原样保存，不截断）');
    await user.clear(editor);
    await user.type(editor, '保存中的草稿');
    const pending = deferred<Result<ArchiveItemDetail>>();
    archiveUpdate.mockReturnValueOnce(pending.promise);
    await user.click(screen.getByRole('button', { name: '保存（带 version 3）' }));
    await advanceRefresh();
    expect(archives).toHaveBeenCalledTimes(1);
    expect(archiveItems).toHaveBeenCalledTimes(1);
    expect(archiveItem).toHaveBeenCalledTimes(1);
    expect(editor).toHaveValue('保存中的草稿');
    expect(screen.getByRole('button', { name: '保存中…' })).toBeDisabled();

    const saved = { ...DETAIL, value: '保存中的草稿', version: 4 };
    archiveItem.mockResolvedValue(ok(saved));
    await act(async () => {
      pending.resolve(ok(saved));
    });
    expect(archives).toHaveBeenCalledTimes(2);
    expect(archiveItems).toHaveBeenCalledTimes(2);
    expect(screen.getByText('version 4')).toBeInTheDocument();
    expect(screen.getByText('保存中的草稿')).toBeInTheDocument();
  });

  it('压缩状态轮询期间暂停自动详情读取，完成后沿用既有刷新', async () => {
    const user = await openArchiveWithClock();
    const backgroundRead = deferred<Result<ArchiveItemDetail>>();
    archiveItem.mockReturnValueOnce(backgroundRead.promise);
    await advanceRefresh();
    const pending = deferred<ArchiveSummarizeTask | null>();
    archiveSummarizeStatus.mockReturnValueOnce(pending.promise);
    await user.click(screen.getByRole('button', { name: 'AI 压缩' }));
    await advanceRefresh();
    expect(archiveSummarizeStatus).toHaveBeenCalledTimes(1);
    expect(archives).toHaveBeenCalledTimes(2);
    expect(archiveItem).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: '编辑' })).toBeDisabled();

    archiveItem.mockResolvedValue(ok({ ...DETAIL, value: '压缩后的正文', version: 4 }));
    await act(async () => {
      pending.resolve({
        ok: true,
        task_id: 'task-1',
        kind: 'single',
        status: 'done',
        table: 'user_profile',
        key: 'u-1',
      });
    });
    await act(async () => {
      backgroundRead.resolve(ok({ ...DETAIL, value: '压缩前的旧回包' }));
    });
    expect(archives).toHaveBeenCalledTimes(3);
    expect(archiveItems).toHaveBeenCalledTimes(3);
    expect(archiveItem).toHaveBeenCalledTimes(3);
    expect(screen.queryByText('压缩前的旧回包')).not.toBeInTheDocument();
    expect(screen.getByText('压缩后的正文')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '编辑' })).toBeEnabled();
  });

  it('后台读取失败保留列表，错误区重试可恢复', async () => {
    const user = await openArchiveWithClock();
    archives.mockResolvedValueOnce({ ok: false, error: '表清单暂时不可用' });
    archiveItems.mockResolvedValueOnce({ ok: false, error: '条目暂时不可用' });
    archiveItem.mockResolvedValueOnce(fail('详情暂时不可用', 503));
    await advanceRefresh();
    expect(screen.getByRole('button', { name: 'u-1' })).toBeInTheDocument();
    expect(screen.getByText('表清单暂时不可用')).toBeInTheDocument();
    expect(screen.getByText('条目暂时不可用')).toBeInTheDocument();
    expect(screen.getByText('详情暂时不可用')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试表清单' }));
    await user.click(screen.getByRole('button', { name: '重试条目列表' }));
    await user.click(screen.getByRole('button', { name: '重新读取' }));
    expect(screen.queryByText('表清单暂时不可用')).not.toBeInTheDocument();
    expect(screen.queryByText('条目暂时不可用')).not.toBeInTheDocument();
    expect(screen.queryByText('详情暂时不可用')).not.toBeInTheDocument();
    expect(screen.getByText('完整档案正文')).toBeInTheDocument();
  });

  it('A46：目标字符数输入框默认取 max_total_chars，并记住上次输入（不写回配置）', async () => {
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    const detailTarget = screen.getByLabelText('目标字符数') as HTMLInputElement;
    expect(detailTarget.value).toBe('5000');
    expect(detailTarget.min).toBe('200');
    expect(detailTarget.max).toBe('5000');

    // jsdom 下 user.clear() 对 <input type="number"> 不生效（不会派发清空后的 change），
    // 用「全选 + 覆写」表达同样的用户意图。
    await user.tripleClick(detailTarget);
    await user.keyboard('3000');
    await waitFor(() => expect(localStorage.getItem('neobot-archives-target-chars')).toBe('3000'));
  });

  it('A28/A31：点「AI 压缩」提交目标并轮询到 done，running 期间禁用编辑', async () => {
    archiveSummarizeStatus.mockResolvedValue({
      ok: true,
      status: 'done',
      task_id: 'task-1',
      kind: 'single',
      table: 'user_profile',
      key: 'u-1',
      target_chars: 5000,
      chars_before: 12000,
      chars_after: 3000,
      snapshot_id: 7,
    });
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    await user.click(screen.getByRole('button', { name: /AI 压缩/ }));

    await waitFor(() =>
      expect(archiveSummarize).toHaveBeenCalledWith({
        table: 'user_profile',
        key: 'u-1',
        target_chars: 5000,
      }),
    );
    // 压缩进行中：同一条目的编辑被禁用（避免人工写入与模型写入互相覆盖）
    expect(screen.getByRole('button', { name: /编辑/ })).toBeDisabled();
    expect(screen.getByText(/该条目正在压缩/)).toBeInTheDocument();

    // 轮询到终态后展示前后字数与快照 id
    await waitFor(() => expect(screen.getAllByText(/12000 → 3000 字/).length).toBeGreaterThan(0), {
      timeout: 5000,
    });
    expect(screen.getAllByText(/快照 id 7/).length).toBeGreaterThan(0);
  });

  it('A32：目标不小于当前字数时提示 no-op（零 token，不进入轮询）', async () => {
    archiveSummarize.mockResolvedValue(
      ok<ArchiveSummarizeTask>({
        ok: true,
        status: 'noop',
        task_id: null,
        chars_before: 6,
        chars_after: 6,
        target_chars: 5000,
        message: '当前 6 字已不大于目标 5000 字，无需压缩（未调用模型）',
      }),
    );
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    await user.click(screen.getByRole('button', { name: /AI 压缩/ }));

    await waitFor(() => expect(archiveSummarize).toHaveBeenCalledTimes(1));
    expect(archiveSummarizeStatus).not.toHaveBeenCalled();
  });

  it('A47：压缩历史只读列出快照（时间/前后字数/来源/操作者）并可查看全文，没有恢复入口', async () => {
    const snapshots: ArchiveSnapshot[] = [
      {
        id: 7,
        table_name: 'user_profile',
        key: 'u-1',
        total_chars: 12000,
        chars_before: 12000,
        chars_after: 6,
        chars_after_source: 'current',
        reason: 'manual',
        operator_ip: '127.0.0.1',
        created_at: '2026-09-12T10:00:00',
      },
    ];
    archiveSnapshots.mockResolvedValue({ ok: true, items: snapshots, current_chars: 6 });
    archiveSnapshot.mockResolvedValue({
      ok: true,
      snapshot: { ...snapshots[0], value: '压缩前的完整原文' },
    });
    const user = userEvent.setup();
    render(<Archives />);
    await user.click(await screen.findByRole('button', { name: 'u-1' }));
    await screen.findByText('完整档案正文');

    expect(await screen.findByText('压缩历史')).toBeInTheDocument();
    expect(screen.getByText('手动压缩')).toBeInTheDocument();
    expect(screen.getByText('127.0.0.1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /恢复到此快照/ })).toBeNull();

    await user.click(screen.getByRole('button', { name: /查看全文/ }));
    expect(await screen.findByText('压缩前的完整原文')).toBeInTheDocument();
  });

  it('档案服务不可用时给出空态', async () => {
    archives.mockResolvedValue(null);
    render(<Archives />);

    expect(await screen.findByText('档案服务不可用')).toBeInTheDocument();
    const region = screen.getByText('档案服务不可用').closest('div');
    expect(within(region as HTMLElement).getByText(/archive_memory_service/)).toBeInTheDocument();
  });
});
