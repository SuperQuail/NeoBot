// Prompts.test.tsx —— 提示词页：分区列表、实时预览、保存/恢复默认、无权限只读
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Prompts from '../pages/Prompts';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { PromptsPayload } from '../api/types';
import { confirmAction } from '../components/ui/ConfirmDialog';
import { POLL } from '../data/queryKeys';

vi.mock('../components/ui/ConfirmDialog', () => ({ confirmAction: vi.fn() }));
vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
const auth = vi.hoisted(() => ({ canManage: true }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));

vi.mock('../api/endpoints', () => ({
  api: { prompts: vi.fn(), promptsPreview: vi.fn(), promptsSave: vi.fn(), promptsReset: vi.fn() },
}));

const prompts = vi.mocked(api.prompts);
const promptsPreview = vi.mocked(api.promptsPreview);
const promptsSave = vi.mocked(api.promptsSave);
const promptsReset = vi.mocked(api.promptsReset);

const PAYLOAD: PromptsPayload = {
  editable: true,
  custom_file: '/tmp/prompts/custom/prompts.toml',
  sections: [
    {
      name: 'group_chat',
      customized: false,
      keys: [
        {
          path: 'template',
          label: 'template',
          kind: 'template',
          value: '<你是谁>\n你的名字是{bot_name}',
          default: '<你是谁>\n你的名字是{bot_name}',
          custom: null,
          overridden: false,
          placeholders: ['bot_name'],
        },
      ],
    },
    {
      name: 'problem_solver',
      customized: true,
      keys: [
        {
          path: 'description',
          label: 'description',
          kind: 'text',
          value: '复杂问题解题',
          default: '复杂问题解题',
          custom: null,
          overridden: false,
          placeholders: [],
        },
      ],
    },
  ],
};

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  auth.canManage = true;
  vi.mocked(confirmAction).mockResolvedValue(true);
  promptsPreview.mockResolvedValue({
    ok: true,
    data: {
      rendered: '<你是谁>\n你的名字是小助手',
      placeholders: ['bot_name'],
      unresolved: [],
      values: { bot_name: '小助手' },
    },
    error: null,
    status: 200,
  });
});

describe('Prompts', () => {
  it('模板使用文本编辑模式，占位符替换当前选择区并把光标放在插入内容之后', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    render(<Prompts />);
    const editor = (await screen.findByLabelText('提示词内容')) as HTMLTextAreaElement;
    expect(editor).toHaveAttribute('data-language', 'text');
    fireEvent.change(editor, { target: { value: '前文替换内容后文' } });
    editor.focus();
    editor.setSelectionRange(2, 6, 'backward');
    await userEvent.click(screen.getByText(/插入占位符/));
    await userEvent.click(screen.getByRole('button', { name: '{bot_name}' }));
    expect(editor).toHaveValue('前文{bot_name}后文');
    expect(editor.selectionStart).toBe('前文{bot_name}'.length);
    expect(editor.selectionEnd).toBe(editor.selectionStart);
    expect(editor).toHaveFocus();
    expect(screen.getByText(/插入占位符/).closest('details')).not.toHaveAttribute('open');
  });

  it('快捷保存只提交一次当前值，保存期间的新草稿在回读后继续保留', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    let finish!: (result: Awaited<ReturnType<typeof api.promptsSave>>) => void;
    promptsSave.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<Prompts />);
    const editor = await screen.findByLabelText('提示词内容');
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(promptsSave).not.toHaveBeenCalled();
    fireEvent.change(editor, { target: { value: '准备保存的人设' } });
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    fireEvent.keyDown(editor, { key: 's', metaKey: true });
    expect(promptsSave).toHaveBeenCalledTimes(1);
    expect(promptsSave).toHaveBeenCalledWith({
      section: 'group_chat',
      path: 'template',
      value: '准备保存的人设',
    });
    fireEvent.change(editor, { target: { value: '请求期间新增的人设' } });
    await act(async () => finish({ ok: true, data: { message: '已保存' }, status: 200, error: null }));
    await waitFor(() => expect(screen.getByRole('button', { name: '保存' })).toBeEnabled());
    expect(editor).toHaveValue('请求期间新增的人设');
    expect(screen.getByText('未保存的修改')).toBeInTheDocument();
  });

  it('会话撤销管理权限时保留文本草稿，禁止快捷保存与占位符写入', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    const view = render(<Prompts />);
    const editor = await screen.findByLabelText('提示词内容');
    fireEvent.change(editor, { target: { value: '我的草稿' } });
    auth.canManage = false;
    view.rerender(<Prompts />);
    expect(editor).toHaveAttribute('readonly');
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    fireEvent.change(editor, { target: { value: '不应写入' } });
    await userEvent.click(screen.getByText(/插入占位符/));
    expect(screen.getByRole('button', { name: '{bot_name}' })).toBeDisabled();
    expect(editor).toHaveValue('我的草稿');
    expect(promptsSave).not.toHaveBeenCalled();
  });

  it('单键分区直接显示为一项目录，保留自定义状态并自动选中第一项', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    render(<Prompts />);

    expect(await screen.findByRole('button', { name: '群聊人设 · 提示词模板' })).toBeInTheDocument();
    const directory = screen.getByRole('region', { name: '提示词分区' });
    expect(within(directory).getAllByRole('button')).toHaveLength(2);
    expect(within(directory).getByRole('button', { name: '复杂问题解题 · 功能描述' })).toHaveTextContent(
      '复杂问题解题',
    );
    expect(within(directory).getByRole('img', { name: '已自定义' })).toBeInTheDocument();
    expect(within(directory).queryByText('template')).not.toBeInTheDocument();
    // 自动选中与草稿回填是两次渲染，这里等它稳定下来
    await waitFor(() =>
      expect(screen.getByLabelText('提示词内容')).toHaveValue('<你是谁>\n你的名字是{bot_name}'),
    );
  });

  it('目录仍支持英文路径搜索，多键分区中的每个键均可选中', async () => {
    prompts.mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        ...PAYLOAD,
        sections: [
          PAYLOAD.sections![0],
          {
            ...PAYLOAD.sections![1],
            keys: [
              ...PAYLOAD.sections![1].keys,
              { ...PAYLOAD.sections![0].keys[0], value: '解题模板', default: '解题模板' },
            ],
          },
        ],
      },
    });
    render(<Prompts />);
    const search = await screen.findByRole('textbox', { name: '搜索提示词' });
    fireEvent.change(search, { target: { value: 'group_chat' } });
    expect(screen.getByRole('button', { name: '群聊人设 · 提示词模板' })).toHaveAttribute(
      'title',
      'group_chat.template',
    );
    expect(screen.queryByRole('button', { name: '复杂问题解题 · 功能描述' })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '复杂问题解题 · 功能描述' }));
    await waitFor(() => expect(screen.getByLabelText('提示词内容')).toHaveValue('复杂问题解题'));
    fireEvent.click(screen.getByRole('button', { name: '复杂问题解题 · 提示词模板' }));
    await waitFor(() => expect(screen.getByLabelText('提示词内容')).toHaveValue('解题模板'));

    fireEvent.change(search, { target: { value: 'description' } });
    expect(screen.getByRole('button', { name: '复杂问题解题 · 功能描述' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '复杂问题解题 · 提示词模板' })).not.toBeInTheDocument();
  });

  it('编辑后防抖预览转义结果，并保存到自定义文件', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    promptsSave.mockResolvedValue({ ok: true, data: { message: '已保存' }, error: null, status: 200 });
    render(<Prompts />);
    const editor = await screen.findByLabelText('提示词内容');

    fireEvent.change(editor, {
      target: { value: '你好{bot_name}' },
    });

    await waitFor(() => expect(promptsPreview).toHaveBeenCalledWith({ template: '你好{bot_name}' }));
    expect(await screen.findByText(/你的名字是小助手/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /保存/ }));
    await waitFor(() =>
      expect(promptsSave).toHaveBeenCalledWith({
        section: 'group_chat',
        path: 'template',
        value: '你好{bot_name}',
      }),
    );
  });

  it('自动更新拿到同键新值时同步，已有草稿时暂停且不冲掉草稿', async () => {
    vi.useFakeTimers();
    try {
      // 回归：草稿重置原先以 current 对象为依赖，后端刷新（同值、新引用）会
      // 把用户刚输入的内容覆盖回旧值，防抖预览因此永远拿到旧模板。
      prompts.mockResolvedValueOnce({ ok: true, data: PAYLOAD, error: null, status: 200 });
      render(<Prompts />);
      await act(async () => {});
      const editor = screen.getByLabelText('提示词内容');

      // 模拟刷新：内容一致，但对象引用全部是新的（真实场景：重新拉取列表）
      prompts.mockResolvedValue({
        ok: true,
        data: {
          ...PAYLOAD,
          sections: (PAYLOAD.sections || []).map((section) => ({
            ...section,
            keys: section.keys.map((key) => ({ ...key, value: '外部更新的模板' })),
          })),
        },
        error: null,
        status: 200,
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(prompts).toHaveBeenCalledTimes(2);
      expect(editor).toHaveValue('外部更新的模板');
      fireEvent.change(editor, { target: { value: '你好{bot_name}' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(prompts).toHaveBeenCalledTimes(2);
      // 关键断言：刷新不得覆盖用户输入
      expect(editor).toHaveValue('你好{bot_name}');
      expect(promptsPreview).toHaveBeenCalledWith({ template: '你好{bot_name}' });
    } finally {
      vi.useRealTimers();
    }
  });

  it('自动请求发出后开始输入，不应用迟到的模板回包', async () => {
    vi.useFakeTimers();
    try {
      prompts.mockResolvedValueOnce({ ok: true, data: PAYLOAD, error: null, status: 200 });
      let finish!: (value: Awaited<ReturnType<typeof api.prompts>>) => void;
      prompts.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
      render(<Prompts />);
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      const editor = screen.getByLabelText('提示词内容');
      fireEvent.change(editor, { target: { value: '正在输入的草稿' } });
      await act(async () => {
        finish({ ok: true, data: { ...PAYLOAD, sections: [] }, status: 200, error: null });
      });
      expect(editor).toHaveValue('正在输入的草稿');
      expect(screen.getByRole('button', { name: '保存' })).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(['success', 'error'] as const)('恢复默认后，不应用较早自动请求的 %s 回包', async (outcome) => {
    vi.useFakeTimers();
    try {
      const custom = {
        ...PAYLOAD,
        sections: PAYLOAD.sections!.map((section) => ({
          ...section,
          keys: section.keys.map((key) => ({ ...key, overridden: true, value: '当前自定义模板' })),
        })),
      };
      const restored = {
        ...PAYLOAD,
        sections: PAYLOAD.sections!.map((section) => ({
          ...section,
          keys: section.keys.map((key) => ({ ...key, overridden: false, value: '已恢复默认模板' })),
        })),
      };
      let finish!: (value: Awaited<ReturnType<typeof api.prompts>>) => void;
      let fail!: (reason: Error) => void;
      prompts
        .mockResolvedValueOnce({ ok: true, data: custom, status: 200, error: null })
        .mockImplementationOnce(
          () =>
            new Promise((resolve, reject) => {
              finish = resolve;
              fail = reject;
            }),
        )
        .mockResolvedValue({ ok: true, data: restored, status: 200, error: null });
      promptsReset.mockResolvedValue({ ok: true, status: 200, error: null, data: { message: '已恢复默认' } });
      render(<Prompts />);
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '恢复默认' }));
      });
      expect(screen.getByLabelText('提示词内容')).toHaveValue('已恢复默认模板');
      await act(async () => {
        if (outcome === 'success') finish({ ok: true, data: custom, status: 200, error: null });
        else fail(new Error('过期的自动读取错误'));
      });
      expect(screen.getByLabelText('提示词内容')).toHaveValue('已恢复默认模板');
      expect(screen.queryByText('暂时无法同步提示词模板')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('自动错误重试进行中禁用人工重试，同一模板没有重复请求', async () => {
    vi.useFakeTimers();
    try {
      let finish!: (value: Awaited<ReturnType<typeof api.prompts>>) => void;
      prompts
        .mockResolvedValueOnce({ ok: true, data: PAYLOAD, status: 200, error: null })
        .mockResolvedValueOnce({ ok: false, data: null, status: 503, error: '暂时无法同步' })
        .mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              finish = resolve;
            }),
        );
      render(<Prompts />);
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor * 2);
      });
      const retry = screen.getByRole('button', { name: '重试读取' });
      expect(retry).toBeDisabled();
      fireEvent.click(retry);
      expect(prompts).toHaveBeenCalledTimes(3);
      await act(async () => {
        finish({ ok: true, data: PAYLOAD, status: 200, error: null });
      });
      expect(screen.queryByText('暂时无法同步')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('未覆盖的键不能点恢复默认，覆盖过的键可以', async () => {
    prompts.mockResolvedValue({
      ok: true,
      data: {
        ...PAYLOAD,
        sections: [
          {
            name: 'group_chat',
            keys: [
              {
                ...PAYLOAD.sections![0].keys[0],
                overridden: true,
                custom: '自定义',
              },
            ],
          },
        ],
      },
      error: null,
      status: 200,
    });
    promptsReset.mockResolvedValue({ ok: true, data: { message: '已恢复默认' }, error: null, status: 200 });
    render(<Prompts />);

    // 目录先渲染，自动选中后才挂载编辑区与恢复按钮。
    const reset = await screen.findByRole('button', { name: '恢复默认' });
    expect(reset).toBeEnabled();
    fireEvent.click(reset);

    await waitFor(() =>
      expect(promptsReset).toHaveBeenCalledWith({ section: 'group_chat', path: 'template' }),
    );
  });

  it('无管理权限时禁用保存并给出提示', async () => {
    prompts.mockResolvedValue({
      ok: true,
      data: { ...PAYLOAD, editable: false },
      error: null,
      status: 200,
    });
    render(<Prompts />);
    const editor = await screen.findByLabelText('提示词内容');

    // InlineAlert 的 warning 走 role="status"（error 才用 alert）
    expect(screen.getByRole('status')).toHaveTextContent('没有管理权限');
    expect(screen.getByRole('button', { name: /保存/ })).toBeDisabled();
    expect(editor).toHaveAttribute('readonly');
  });

  it('切换模板前保护未保存草稿，取消后保留输入', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    vi.mocked(confirmAction).mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    render(<Prompts />);
    const editor = await screen.findByLabelText('提示词内容');
    fireEvent.change(editor, { target: { value: '尚未保存的人设' } });
    fireEvent.click(screen.getByRole('button', { name: '复杂问题解题 · 功能描述' }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    expect(editor).toHaveValue('尚未保存的人设');
    fireEvent.click(screen.getByRole('button', { name: '复杂问题解题 · 功能描述' }));
    await waitFor(() => expect(screen.getByLabelText('提示词内容')).toHaveValue('复杂问题解题'));
    expect(confirmAction).toHaveBeenCalledTimes(2);
  });

  it('存储不可用时显示不可用态', async () => {
    prompts.mockResolvedValue({
      ok: false,
      data: null,
      error: '提示词存储不可用（未注入 prompt_store）',
      status: 503,
    });
    render(<Prompts />);

    expect(await screen.findByText('提示词存储不可用')).toBeInTheDocument();
    expect(screen.getByText(/未注入 prompt_store/)).toBeInTheDocument();
  });
});
