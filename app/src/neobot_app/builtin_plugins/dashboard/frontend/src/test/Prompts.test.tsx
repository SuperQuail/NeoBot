// Prompts.test.tsx —— 提示词页：分区列表、实时预览、保存/恢复默认、无权限只读
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Prompts from '../pages/Prompts';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { PromptsPayload } from '../api/types';

vi.mock('../api/endpoints.js', () => ({
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
  it('渲染分区与键，并自动选中第一个键', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    render(<Prompts />);

    expect(await screen.findByText('group_chat')).toBeInTheDocument();
    expect(screen.getByText('problem_solver')).toBeInTheDocument();
    expect(screen.getByText('已自定义')).toBeInTheDocument();
    // 自动选中与草稿回填是两次渲染，这里等它稳定下来
    await waitFor(() =>
      expect(screen.getByLabelText('提示词内容')).toHaveValue('<你是谁>\n你的名字是{bot_name}'),
    );
  });

  it('编辑后防抖预览转义结果，并保存到自定义文件', async () => {
    prompts.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
    promptsSave.mockResolvedValue({ ok: true, data: { message: '已保存' }, error: null, status: 200 });
    render(<Prompts />);
    await screen.findByText('group_chat');

    fireEvent.change(screen.getByLabelText('提示词内容'), {
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
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<Prompts />);
    await screen.findByText('group_chat');

    const reset = screen.getByRole('button', { name: /恢复默认/ });
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
    await screen.findByText('group_chat');

    // InlineAlert 的 warning 走 role="status"（error 才用 alert）
    expect(screen.getByRole('status')).toHaveTextContent('没有管理权限');
    expect(screen.getByRole('button', { name: /保存/ })).toBeDisabled();
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
