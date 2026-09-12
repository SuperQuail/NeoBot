// Archives.test.tsx —— 档案页（spec(2)）：表清单 / 条目筛选分页 / 详情全文 / 乐观锁编辑 / 删除二次确认
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Archives from '../pages/Archives';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { ArchiveItemDetail, ArchiveItemsPayload, ArchivesPayload, Result } from '../api/types';

vi.mock('../api/endpoints.js', () => ({
  api: {
    archives: vi.fn(),
    archiveItems: vi.fn(),
    archiveItem: vi.fn(),
    archiveUpdate: vi.fn(),
    archiveDelete: vi.fn(),
  },
}));

const archives = vi.mocked(api.archives);
const archiveItems = vi.mocked(api.archiveItems);
const archiveItem = vi.mocked(api.archiveItem);
const archiveUpdate = vi.mocked(api.archiveUpdate);
const archiveDelete = vi.mocked(api.archiveDelete);

function ok<T>(data: T): Result<T> {
  return { ok: true, data, error: null, status: 200 };
}

function fail<T>(error: string, status: number, data: T | null = null): Result<T> {
  return { ok: false, data, error, status };
}

const TABLES: ArchivesPayload = {
  ok: true,
  max_total_chars: 5000,
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
  archives.mockResolvedValue(TABLES);
  archiveItems.mockResolvedValue(ITEMS);
  archiveItem.mockResolvedValue(ok(DETAIL));
  archiveUpdate.mockResolvedValue(ok({ ...DETAIL, version: 4, message: '档案已保存' }));
  archiveDelete.mockResolvedValue(ok({ message: '档案已删除（可在 neobot.log 中追溯被删内容）' }));
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
      expect(archiveItems).toHaveBeenCalledWith(expect.objectContaining({ table: 'user_profile', limit: 50 })),
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

    // 重新加载 = 放弃我的修改
    await user.click(screen.getByRole('button', { name: /重新加载（放弃我的修改）/ }));
    await waitFor(() =>
      expect((screen.getByLabelText('档案正文（原样保存，不截断）') as HTMLTextAreaElement).value).toBe(
        '服务端最新内容',
      ),
    );
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
      ok({ ...DETAIL, table_name: 'memory_counter', key: 'counter-1', internal: true, editable: false, value: '{}' }),
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

    await user.type(screen.getByLabelText('key 包含'), 'u-1');
    await user.type(screen.getByLabelText('内容包含'), '正文');
    await user.click(screen.getByRole('button', { name: /查询/ }));

    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(
        expect.objectContaining({ table: 'user_profile', keyQuery: 'u-1', valueQuery: '正文', offset: 0 }),
      ),
    );

    await user.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() =>
      expect(archiveItems).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 })),
    );
  });

  it('档案服务不可用时给出空态', async () => {
    archives.mockResolvedValue(null);
    render(<Archives />);

    expect(await screen.findByText('档案服务不可用')).toBeInTheDocument();
    const region = screen.getByText('档案服务不可用').closest('div');
    expect(within(region as HTMLElement).getByText(/archive_memory_service/)).toBeInTheDocument();
  });
});
