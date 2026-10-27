import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AssignPanel } from '../pages/config/AssignPanel';
import { api } from '../api/endpoints';
import { useAuthGate } from '../auth/AuthContext';
import { confirmAction } from '../components/ui/ConfirmDialog';
import type { ModelsPayload, Result } from '../api/types';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: vi.fn() }));
vi.mock('../components/ui/ConfirmDialog', () => ({ confirmAction: vi.fn() }));
vi.mock('../api/endpoints', () => ({
  api: { configModels: vi.fn(), modelsAssignmentsSave: vi.fn() },
}));

const PAYLOAD: ModelsPayload = {
  revision: 10,
  can_manage: true,
  assignments: { roles: { primary_chat_model: 'main', vision_model: '' }, creator_image_models: ['image'] },
  roles_meta: [
    {
      role: 'primary_chat_model',
      label: '主对话模型（Agent 编号 0）',
      required: true,
      model_type: 'chat',
      model_type_label: '对话',
    },
    {
      role: 'vision_model',
      label: '视觉 / 图像识别模型',
      required: false,
      model_type: 'vision',
      model_type_label: '视觉',
    },
    {
      role: 'creator_image_models',
      label: '创作者生图模型',
      multi: true,
      required: false,
      model_type: 'image',
      model_type_label: '生图',
    },
  ],
  role_model_types: { primary_chat_model: 'chat', vision_model: 'vision', creator_image_models: 'image' },
  library: [
    {
      model_ref: 'main',
      display_name: '日常对话',
      provider: 'Demo',
      model_name: 'chat-basic',
      model_type: 'chat',
      type_label: '对话',
      registered: true,
    },
    {
      model_ref: 'reason',
      display_name: '长上下文推理模型',
      provider: 'Reason',
      model_name: 'reason-long',
      model_type: 'chat',
      type_label: '对话',
      native_vision: true,
      registered: false,
    },
    {
      model_ref: 'vision',
      display_name: '图片理解模型',
      provider: 'Vision',
      model_name: 'vision-full',
      model_type: 'vision',
      type_label: '视觉',
      registered: true,
    },
    {
      model_ref: 'image',
      display_name: '绘图模型',
      provider: 'Illustration',
      model_name: 'image-create',
      model_type: 'image',
      type_label: '生图',
      registered: true,
    },
  ],
  roles: [
    { role: 'primary_chat_model', model_ref: 'main', registered: true },
    { role: 'creator_image_models', model_ref: 'image', registered: true },
  ],
};

function ok(data: ModelsPayload): Result<ModelsPayload> {
  return { ok: true, status: 200, error: null, data };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuthGate).mockReturnValue({ canManage: true, setupRequired: false, refresh: async () => {} });
  vi.mocked(api.configModels).mockResolvedValue(ok(structuredClone(PAYLOAD)));
  vi.mocked(api.modelsAssignmentsSave).mockResolvedValue(ok({ revision: 11 }));
  vi.mocked(confirmAction).mockResolvedValue(true);
});

async function readyPrimary() {
  const select = await screen.findByRole('combobox', { name: '主对话使用的模型' });
  await waitFor(() => expect(select).toBeEnabled());
  return select;
}

async function openOptions(trigger: HTMLElement) {
  await act(async () => {
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
  });
}

async function chooseOption(trigger: HTMLElement, label: string) {
  if (trigger.getAttribute('aria-expanded') !== 'true') await openOptions(trigger);
  const option = screen.getByRole('option', { name: label });
  await act(async () => {
    option.focus();
    fireEvent.keyDown(option, { key: 'Enter' });
  });
}

describe('AssignPanel 用途分配', () => {
  it('在用途旁展示供应商、模型能力与真实注册状态，并保留跨类型选择', async () => {
    render(<AssignPanel />);
    const select = await readyPrimary();
    const card = screen.getByRole('article', { name: '主对话' });
    expect(within(card).getByText('Demo')).toBeInTheDocument();
    expect(within(card).getByText('chat-basic')).toBeInTheDocument();
    expect(within(card).getByText('运行时已注册')).toBeInTheDocument();
    await openOptions(select);
    expect(screen.getByRole('option', { name: '请选择模型' })).toHaveAttribute('aria-disabled', 'true');
    expect(
      within(screen.getByRole('group', { name: '推荐类型 · 对话' }))
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['日常对话 · main', '长上下文推理模型 · reason']);
    expect(
      within(screen.getByRole('group', { name: '其他类型（仍可选择）' })).getByRole('option', {
        name: '绘图模型 · image',
      }),
    ).toBeInTheDocument();

    await chooseOption(select, '长上下文推理模型 · reason');
    await waitFor(() => expect(select).toHaveFocus());
    expect(within(card).getByText('支持看图')).toBeInTheDocument();
    expect(within(card).getByText('Reason')).toBeInTheDocument();
    expect(within(card).getByText('未保存')).toBeInTheDocument();
    await chooseOption(select, '绘图模型 · image');
    expect(within(card).getByText(/当前选择仍可保存/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存分配' })).toBeEnabled();
  });

  it('保存单选与图像多选，采用返回的 models 视图并保留待重载提示', async () => {
    const user = userEvent.setup();
    const assignments = {
      roles: { primary_chat_model: 'reason', vision_model: '' },
      creator_image_models: ['image', 'vision'],
    };
    vi.mocked(api.modelsAssignmentsSave).mockResolvedValue(
      ok({ revision: 11, models: { ...PAYLOAD, assignments } }),
    );
    render(<AssignPanel />);
    await chooseOption(await readyPrimary(), '长上下文推理模型 · reason');
    await user.click(screen.getByRole('checkbox', { name: '图片理解模型 (vision)' }));
    await user.click(screen.getByRole('button', { name: '保存分配' }));

    await waitFor(() =>
      expect(api.modelsAssignmentsSave).toHaveBeenCalledWith({
        revision: 10,
        assignments: {
          primary_chat_model: 'reason',
          vision_model: '',
          creator_image_models: ['image', 'vision'],
        },
      }),
    );
    expect(await screen.findByText('已保存，待重载')).toBeInTheDocument();
    expect(screen.queryByText('分配已保存，等待重载')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '主对话使用的模型' })).toHaveTextContent(
      '长上下文推理模型 · reason',
    );
    expect(screen.getByRole('checkbox', { name: '图片理解模型 (vision)' })).toBeChecked();
    expect(screen.getByRole('button', { name: '保存分配' })).toBeDisabled();
  });

  it('保留缺失引用，不把下拉框伪装为第一项；修正单选及缺失多选后才能保存', async () => {
    const user = userEvent.setup();
    vi.mocked(api.configModels).mockResolvedValue(
      ok({
        ...PAYLOAD,
        assignments: {
          roles: { primary_chat_model: 'deleted', vision_model: '' },
          creator_image_models: ['image', 'old-image'],
        },
      }),
    );
    render(<AssignPanel />);
    const select = await readyPrimary();
    expect(select).toHaveTextContent('deleted（模型库中不存在）');
    expect(select).toHaveAttribute('aria-invalid', 'true');
    expect(select).toHaveAttribute('id', 'assignment-select-primary_chat_model');
    expect(select).toHaveAttribute('title', 'deleted');
    expect(select).toHaveAccessibleDescription('模型库中不存在：deleted。请重新选择。');
    await openOptions(select);
    expect(screen.getByRole('option', { name: 'deleted（模型库中不存在）' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await chooseOption(select, '日常对话 · main');
    expect(screen.getByRole('button', { name: '保存分配' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: '移除缺失模型 old-image' }));
    expect(screen.getByRole('button', { name: '保存分配' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    await waitFor(() =>
      expect(api.modelsAssignmentsSave).toHaveBeenCalledWith(
        expect.objectContaining({
          assignments: { primary_chat_model: 'main', vision_model: '', creator_image_models: ['image'] },
        }),
      ),
    );
  });

  it('可选用途允许通过键盘清空，并按空字符串保存', async () => {
    const user = userEvent.setup();
    vi.mocked(api.configModels).mockResolvedValue(
      ok({
        ...PAYLOAD,
        assignments: {
          ...PAYLOAD.assignments,
          roles: { primary_chat_model: 'main', vision_model: 'vision' },
        },
      }),
    );
    render(<AssignPanel />);
    await readyPrimary();
    const optional = screen.getByRole('combobox', { name: '图像识别使用的模型' });
    await openOptions(optional);
    expect(screen.getByRole('option', { name: '不指定模型' })).not.toHaveAttribute('aria-disabled');
    await chooseOption(optional, '不指定模型');
    expect(optional).toHaveTextContent('不指定模型');
    expect(optional).toHaveAttribute('aria-invalid', 'false');
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    await waitFor(() =>
      expect(api.modelsAssignmentsSave).toHaveBeenCalledWith({
        revision: 10,
        assignments: { primary_chat_model: 'main', vision_model: '', creator_image_models: ['image'] },
      }),
    );
  });

  it.each(['session', 'payload'] as const)(
    '遵守 %s 的只读状态，所有单选、多选及保存均禁用',
    async (source) => {
      if (source === 'session')
        vi.mocked(useAuthGate).mockReturnValue({
          canManage: false,
          setupRequired: false,
          refresh: async () => {},
        });
      else vi.mocked(api.configModels).mockResolvedValue(ok({ ...PAYLOAD, can_manage: false }));
      render(<AssignPanel />);
      await screen.findByText('当前会话只读');
      for (const control of [...screen.getAllByRole('combobox'), ...screen.getAllByRole('checkbox')])
        expect(control).toBeDisabled();
      expect(screen.getByRole('button', { name: '保存分配' })).toBeDisabled();
      expect(api.modelsAssignmentsSave).not.toHaveBeenCalled();
    },
  );

  it('空模型库保留用途与缺口说明，不允许提交必需用途的空选择', async () => {
    vi.mocked(api.configModels).mockResolvedValue(
      ok({
        ...PAYLOAD,
        library: [],
        assignments: { roles: { primary_chat_model: '', vision_model: '' }, creator_image_models: [] },
      }),
    );
    render(<AssignPanel />);
    expect(await screen.findByText('模型库为空')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '主对话使用的模型' })).toBeDisabled();
    expect(screen.getByText('此用途必须指定模型。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存分配' })).toBeDisabled();
  });

  it('冲突后保留草稿；取消重新读取仍保留，确认后才替换', async () => {
    const user = userEvent.setup();
    vi.mocked(api.modelsAssignmentsSave).mockResolvedValue({
      ok: false,
      status: 409,
      error: 'revision changed',
      data: null,
    });
    render(<AssignPanel />);
    const select = await readyPrimary();
    await chooseOption(select, '长上下文推理模型 · reason');
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    expect(await screen.findByText(/当前分配草稿已保留/)).toBeInTheDocument();
    expect(select).toHaveTextContent('长上下文推理模型 · reason');
    vi.mocked(confirmAction).mockResolvedValueOnce(false);
    await user.click(screen.getByRole('button', { name: '重新读取' }));
    expect(select).toHaveTextContent('长上下文推理模型 · reason');
    expect(api.configModels).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: '重新读取' }));
    await waitFor(() => expect(select).toHaveTextContent('日常对话 · main'));
  });

  it('保存中锁定选择；缺少模型视图的成功响应仍更新 revision，允许继续编辑保存', async () => {
    const user = userEvent.setup();
    let finish!: (value: Result<ModelsPayload>) => void;
    vi.mocked(api.modelsAssignmentsSave).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<AssignPanel />);
    const select = await readyPrimary();
    await chooseOption(select, '长上下文推理模型 · reason');
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    expect(select).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '绘图模型 (image)' })).toBeDisabled();
    await act(async () => finish(ok({ revision: 11 })));
    await waitFor(() => expect(select).toBeEnabled());
    await chooseOption(select, '日常对话 · main');
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    await waitFor(() =>
      expect(api.modelsAssignmentsSave).toHaveBeenLastCalledWith(expect.objectContaining({ revision: 11 })),
    );
  });
});
