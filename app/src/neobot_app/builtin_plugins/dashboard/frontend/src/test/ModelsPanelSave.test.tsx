// 回归（issue #65）：模型库页 "library.filter is not a function"
//
// 后端保存接口返回的 models 是「模型视图对象」{library, assignments, roles, …}。
// 旧实现把整个对象塞进了 data.library（应当是数组），下一次渲染到
// modelNameOptions 的 library.filter(...) 就抛 TypeError，
// 被路由级错误边界接住 => 面板显示「页面渲染出错 / xxx is not a function」。
//
// 这里直接构造「library 被写成视图对象」的坏数据，锁住「面板必须扛得住」这一点：
// 崩溃点在 render 期，所以修复前本用例会抛 library.filter is not a function。
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ModelsPanel } from '../pages/config/ModelsPanel';
import { api } from '../api/endpoints';
import type { ModelsPayload } from '../api/types';
import { infoBar } from '../notifications/infoBar';

vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));

vi.mock('../api/endpoints', () => ({
  api: {
    configModels: vi.fn(),
    modelsLibrarySave: vi.fn(),
    modelsAssignmentsSave: vi.fn(),
    modelsTest: vi.fn(),
    modelsProviderModels: vi.fn(),
    configBilling: vi.fn(),
    configBillingReload: vi.fn(),
    configBillingPreview: vi.fn(),
  },
}));

const ITEM = {
  model_ref: 'ds',
  display_name: '主对话',
  provider: 'DeepSeek',
  model_name: 'deepseek-flash',
  model_type: 'chat',
  type_label: '对话',
  entry: {
    model_ref: 'ds',
    display_name: '主对话',
    provider: 'DeepSeek',
    model_name: 'deepseek-flash',
    model_type: 'chat',
  },
};

const VIEW = {
  library: [ITEM],
  entry_schema: [
    { name: 'display_name', path: ['display_name'], kind: 'scalar', type: 'str', value: '主对话' },
  ],
  provider_options: ['DeepSeek'],
  model_type_labels: { chat: '对话' },
  revision: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.modelsProviderModels).mockResolvedValue({
    ok: true,
    data: { ok: true, models: [] },
    error: null,
    status: 200,
  });
  vi.mocked(api.configBilling).mockResolvedValue({
    ok: true,
    data: { scripts: [], bindings: [] } as never,
    error: null,
    status: 200,
  });
});

describe('模型库视图形状（issue #65）', () => {
  it('测试完成只通知摘要，完整诊断按需查看，不自动弹出结果窗口', async () => {
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      data: VIEW as ModelsPayload,
      error: null,
      status: 200,
    });
    vi.mocked(api.modelsTest).mockResolvedValue({
      ok: true,
      error: null,
      status: 200,
      data: {
        ok: false,
        model_ref: 'ds',
        provider: 'DeepSeek',
        model_name: 'deepseek-flash',
        reachable: true,
        authorized: false,
        status: 401,
        latency_ms: 83,
        message: '鉴权未通过',
        detail: '请更新供应商密钥',
        url: 'https://example.com/models',
      },
    });
    render(<ModelsPanel />);
    fireEvent.click(await screen.findByRole('button', { name: '测试' }));
    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '模型测试未通过',
          tone: 'err',
          message: 'ds',
        }),
      ),
    );
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog', { name: '模型连通性测试' })).not.toBeInTheDocument();
    const details = render(<>{vi.mocked(infoBar).mock.calls[0][0].details}</>);
    expect(details.container).toHaveTextContent('鉴权未通过');
    expect(details.container).toHaveTextContent('请更新供应商密钥');
    expect(details.container).toHaveTextContent('401 / 83 ms');
    expect(details.container).toHaveTextContent('https://example.com/models');
  });
  it('library 是数组时正常渲染', async () => {
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      data: VIEW as ModelsPayload,
      error: null,
      status: 200,
    });

    render(<ModelsPanel />);

    expect(await screen.findByText('1 个模型')).toBeInTheDocument();
  });

  it('library 被写成模型视图对象时也不崩（保存后的坏状态）', async () => {
    // 复刻旧实现保存后的 state：library 指向视图对象本身
    const broken = { ...VIEW, library: VIEW };
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      data: broken as unknown as ModelsPayload,
      error: null,
      status: 200,
    });

    render(<ModelsPanel />);

    // 只要还能渲染出面板主体（标题 + 计数标签），就说明没有在 render 期抛异常
    expect(await screen.findByRole('heading', { name: '模型库' })).toBeInTheDocument();
    expect(screen.getByText('0 个模型')).toBeInTheDocument();
  });
});

describe('模型编辑表单样式（issue #75）', () => {
  it('用与本体配置同款的面板：左树 + 搜索，而不是旧的嵌套折叠表单', async () => {
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      data: VIEW as ModelsPayload,
      error: null,
      status: 200,
    });
    render(<ModelsPanel />);

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }));

    // 编辑器经 Portal 显示，断言用户实际操作的对话框中的树与搜索入口。
    const dialog = await screen.findByRole('dialog', { name: '编辑模型 ds' });
    expect(dialog.querySelector('.cfg-tree')).toBeInTheDocument();
    expect(within(dialog).getByRole('navigation', { name: '配置分区' })).toBeInTheDocument();
    expect(within(dialog).getByPlaceholderText('搜索模型字段（支持路径与说明）…')).toHaveClass('cfg-search');
  });
});
