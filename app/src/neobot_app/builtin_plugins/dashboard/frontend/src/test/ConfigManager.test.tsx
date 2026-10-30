// ConfigManager 回归测试 —— 加载、表单渲染、模式切换、脏状态
// 目的：在后续拆组件/换数据层时锁住现有行为。
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { StrictMode } from 'react';
import userEvent from '@testing-library/user-event';
import ConfigManager from '../pages/ConfigManager';
import { api } from '../api/endpoints';
import type { ConfigDocument } from '../api/types';
import { ConfirmHost } from '../components/ui/ConfirmDialog';
import { closeInfoBarDetails, infoBar, notify } from '../notifications/infoBar';

vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../notifications/infoBar', () => ({
  infoBar: vi.fn(),
  closeInfoBarDetails: vi.fn(),
  notify: vi.fn(),
}));
const auth = vi.hoisted(() => ({ canManage: true }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));

vi.mock('../api/endpoints', () => ({
  api: {
    config: vi.fn(),
    configSave: vi.fn(),
    configValidate: vi.fn(),
    configReload: vi.fn(),
    configModels: vi.fn(),
    env: vi.fn(),
    envSave: vi.fn(),
    envAddPlatform: vi.fn(),
    modelsLibrarySave: vi.fn(),
    modelsAssignmentsSave: vi.fn(),
    modelsTest: vi.fn(),
    modelsProviderModels: vi.fn(),
    configBilling: vi.fn(),
    restart: vi.fn(),
  },
}));

const CONFIG_DOC: ConfigDocument = {
  section: 'bot',
  revision: '00000000000000000000000000000007',
  form_supported: true,
  source_available: true,
  path: 'data/config.toml',
  source: '[bot]\nhost = "0.0.0.0"\nport = 9981\n',
  config: { host: '0.0.0.0', port: 9981, enabled: true },
  schema: [
    {
      name: 'enabled',
      path: ['enabled'],
      kind: 'scalar',
      type: 'bool',
      value: true,
      default: true,
      hot_reload: true,
    },
    {
      name: 'host',
      path: ['host'],
      kind: 'scalar',
      type: 'str',
      value: '0.0.0.0',
      default: '127.0.0.1',
      description: '监听地址',
      hot_reload: false,
      restart_reason: '监听地址属于构建期配置',
    },
    {
      name: 'port',
      path: ['port'],
      kind: 'scalar',
      type: 'int',
      value: 9981,
      default: 9981,
      hot_reload: false,
    },
  ],
};

function renderConfig() {
  return render(
    <>
      <ConfigManager />
      <ConfirmHost />
    </>,
  );
}

async function readyHostField() {
  const initialValue = '0.0.0.0';
  const field = await screen.findByDisplayValue(initialValue);
  await waitFor(() => expect(field).toBeEnabled());
  return field;
}

async function selectReadyTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  await waitFor(() => expect(tab).toBeEnabled());
  await userEvent.click(tab);
}

async function openMoreActions() {
  const toggle = screen.getByText('更多操作', { selector: 'summary' });
  await userEvent.click(toggle);
  expect(toggle.closest('details')).toHaveAttribute('open');
  await screen.findByRole('group', { name: '配置编辑操作' });
}

async function answerConfirmation(title: string, answer = '取消') {
  const dialog = await screen.findByRole('dialog', { name: title });
  await userEvent.click(within(dialog).getByRole('button', { name: answer }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: title })).not.toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.canManage = true;
  vi.mocked(api.config).mockResolvedValue({ ok: true, data: CONFIG_DOC, error: null, status: 200 });
  vi.mocked(api.configBilling).mockResolvedValue({
    ok: true,
    data: { enabled: false, scripts: [], templates: [] },
    error: null,
    status: 200,
  });
});

describe('ConfigManager 页面', () => {
  it('初次读取失败保留阻塞错误和重试，不重复发送操作通知', async () => {
    vi.mocked(api.config).mockRejectedValueOnce(new Error('配置服务暂时不可用'));
    renderConfig();
    expect(await screen.findByRole('alert')).toHaveTextContent('配置服务暂时不可用');
    expect(infoBar).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '重试' }));
    await readyHostField();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(infoBar).not.toHaveBeenCalled();
  });

  it('保存成功只发一条InfoBar，明细缺少前后值时仅展示路径', async () => {
    vi.mocked(api.configSave).mockResolvedValueOnce({
      ok: true,
      status: 200,
      error: null,
      data: {
        ...CONFIG_DOC,
        revision: '00000000000000000000000000000008',
        config: { ...CONFIG_DOC.config, host: '127.0.0.1' },
        applied: true,
        message: '配置已热重载：2 项已生效，0 项需重启',
        changes: {
          hot_reload_count: 2,
          needs_restart_count: 0,
          hot_reload: [{ path: 'host' }, { path: 'enabled', before: false, after: true }],
        },
      },
    });
    const { container } = renderConfig();
    fireEvent.change(await readyHostField(), { target: { value: '127.0.0.1' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    expect(infoBar).toHaveBeenCalledWith(
      expect.objectContaining({ title: '配置已保存并重载 · 2 项已生效', tone: 'ok' }),
    );
    expect(notify).not.toHaveBeenCalled();
    expect(container.querySelector('.cfg-changes, .config-notice, .workspace-error')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存并重载' })).toBeDisabled();
    const details = render(<>{vi.mocked(infoBar).mock.lastCall?.[0].details}</>);
    expect(details.container.textContent).not.toContain('undefined');
    expect(within(details.container).getByText('host').closest('li')).toHaveTextContent(/^host$/);
    expect(within(details.container).getByText('enabled').closest('li')).toHaveTextContent('false → true');
  });

  it('需重启结果持久提示，路径与原因收进详情而不占编辑区', async () => {
    vi.mocked(api.configReload).mockResolvedValueOnce({
      ok: true,
      status: 200,
      error: null,
      data: {
        message: '监听配置需要重启后生效',
        changes: {
          needs_restart_count: 1,
          needs_restart: [{ path: 'port', reason: '监听端口只在启动时读取' }],
        },
      },
    });
    const { container } = renderConfig();
    await readyHostField();
    fireEvent.click(screen.getByRole('button', { name: '重载运行时配置' }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    expect(infoBar).toHaveBeenCalledWith(
      expect.objectContaining({ tone: 'warn', duration: 0, title: '配置已重载，1 项需重启' }),
    );
    expect(container.querySelector('.cfg-changes, .config-notice')).not.toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
    const details = render(<>{vi.mocked(infoBar).mock.lastCall?.[0].details}</>);
    expect(details.container).toHaveTextContent('监听端口只在启动时读取');
    expect(details.container).not.toHaveTextContent('undefined');
  });

  it('校验错误完整保留精确路径，并能从详情定位表单字段', async () => {
    const errors = Array.from({ length: 15 }, (_, index) => ({
      path: index === 0 ? 'host' : `models.registry.${index}.model_name`,
      message: `第 ${index + 1} 项值无效`,
    }));
    vi.mocked(api.configValidate).mockResolvedValueOnce({
      ok: false,
      status: 400,
      error: '配置类型校验失败',
      data: { errors },
    });
    const { container } = renderConfig();
    const host = await readyHostField();
    fireEvent.change(host, { target: { value: '尚未保存' } });
    fireEvent.click(screen.getByRole('button', { name: '校验' }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    expect(infoBar).toHaveBeenCalledWith(
      expect.objectContaining({ title: '配置校验未通过 · 15 项问题', tone: 'err', duration: 0 }),
    );
    expect(container.querySelector('.workspace-error')).not.toBeInTheDocument();
    expect(host).toHaveValue('尚未保存');
    const details = render(<>{vi.mocked(infoBar).mock.lastCall?.[0].details}</>);
    expect(within(details.container).getAllByRole('listitem')).toHaveLength(15);
    await userEvent.click(within(details.container).getByRole('button', { name: '定位 host' }));
    expect(screen.getByRole('textbox', { name: '搜索配置项' })).toHaveValue('host');
    expect(closeInfoBarDetails).toHaveBeenCalledTimes(1);
    expect(host).toHaveValue('尚未保存');
    expect(notify).not.toHaveBeenCalled();
  });

  it('TOML 校验失败保留草稿和源码模式，仅展示配置路径', async () => {
    vi.mocked(api.configValidate).mockResolvedValueOnce({
      ok: false,
      status: 400,
      error: 'port 类型无效',
      data: { errors: [{ path: 'port', message: '需要整数' }] },
    });
    renderConfig();
    await readyHostField();
    await selectReadyTab('TOML');
    const editor = screen.getByLabelText('config.toml');
    fireEvent.change(editor, { target: { value: '# 我的注释\nport="invalid"' } });
    fireEvent.click(screen.getByRole('button', { name: '校验' }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    const details = render(<>{vi.mocked(infoBar).mock.lastCall?.[0].details}</>);
    expect(details.container).toHaveTextContent('port 需要整数');
    expect(within(details.container).queryByRole('button', { name: /定位/ })).not.toBeInTheDocument();
    expect(editor).toHaveValue('# 我的注释\nport="invalid"');
    expect(screen.getByRole('tab', { name: 'TOML' })).toHaveAttribute('aria-selected', 'true');
  });

  it('本体配置把同步状态和全部保存运行操作放在顶部，正文没有底部操作栏', async () => {
    const { container } = renderConfig();
    await readyHostField();
    const toolbar = screen.getByRole('toolbar', { name: '本体配置操作' });
    expect(within(toolbar).getByRole('button', { name: '保存并重载' })).toBeDisabled();
    expect(within(toolbar).getByRole('button', { name: '重载运行时配置' })).toBeEnabled();
    expect(within(toolbar).getByRole('button', { name: '重启 NeoBot' })).toBeEnabled();
    expect(within(toolbar).getByRole('status')).toHaveAttribute('title', '与文件同步 · data/config.toml');
    expect(container.querySelector('.config-editor-footer')).not.toBeInTheDocument();
    await selectReadyTab('TOML');
    expect(screen.getByRole('textbox', { name: 'config.toml' })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: '保存并重载' })).toHaveAttribute(
      'title',
      '保存前自动校验语法与类型，并备份旧文件。',
    );
    expect(container.querySelector('.source-editor-heading')).not.toBeInTheDocument();
    expect(container.querySelector('.source-editor-hint')).not.toBeInTheDocument();
  });

  it('窄屏顶部保留保存，搜索校验和运行操作通过更多菜单访问', async () => {
    const original = window.matchMedia;
    const media = vi
      .spyOn(window, 'matchMedia')
      .mockImplementation((query) => ({ ...original(query), matches: query === '(max-width: 1100px)' }));
    try {
      renderConfig();
      await readyHostField();
      const toolbar = screen.getByRole('toolbar', { name: '本体配置操作' });
      expect(toolbar).toHaveAttribute('data-compact', 'true');
      expect(within(toolbar).getByRole('button', { name: '保存并重载' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '重载运行时配置' })).not.toBeVisible();
      expect(screen.getByRole('textbox', { name: '搜索配置项' })).not.toBeVisible();
      await openMoreActions();
      expect(screen.getByRole('textbox', { name: '搜索配置项' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '校验配置' })).toBeEnabled();
      expect(screen.getByRole('button', { name: '重载运行时配置' })).toBeEnabled();
      fireEvent.click(screen.getByRole('button', { name: '重启 NeoBot' }));
      await answerConfirmation('重启 NeoBot？');
      expect(api.restart).not.toHaveBeenCalled();
    } finally {
      media.mockRestore();
    }
  });

  it('恢复默认需确认且可撤销，取消时不修改配置', async () => {
    renderConfig();
    const host = await readyHostField();
    expect(screen.getByText('更多操作', { selector: 'summary' }).closest('details')).not.toHaveAttribute(
      'open',
    );
    await openMoreActions();
    fireEvent.click(screen.getByRole('button', { name: '全部恢复默认' }));
    await answerConfirmation('全部恢复默认？');
    expect(host).toHaveValue('0.0.0.0');
    fireEvent.click(screen.getByRole('button', { name: '全部恢复默认' }));
    await answerConfirmation('全部恢复默认？', '恢复默认');
    expect(host).toHaveValue('127.0.0.1');
    fireEvent.click(screen.getByRole('button', { name: '撤销 1' }));
    expect(host).toHaveValue('0.0.0.0');
    expect(api.configSave).not.toHaveBeenCalled();
  });

  it('环境变量草稿保护顶层切换，并在保存时锁定导航', async () => {
    vi.mocked(api.env).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        revision: '00000000000000000000000000000002',
        items: [{ key: 'Demo_APIKey', sensitive: true, has_value: true, in_file: true }],
      },
    });
    renderConfig();
    await readyHostField();
    await selectReadyTab('环境变量');
    const key = await screen.findByPlaceholderText('已设置 · 留空则不修改');
    await waitFor(() => expect(key).toBeEnabled());
    fireEvent.change(key, { target: { value: 'new-draft' } });
    await selectReadyTab('模型分配');
    await answerConfirmation('切换配置面板？');
    expect(screen.getByRole('tab', { name: '环境变量' })).toHaveAttribute('aria-selected', 'true');
    let finish!: (value: Awaited<ReturnType<typeof api.envSave>>) => void;
    vi.mocked(api.envSave).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    expect(screen.getByRole('tab', { name: '模型分配' })).toBeDisabled();
    await act(async () => finish({ ok: false, status: 409, error: '配置已变化', data: null }));
    expect(key).toHaveValue('new-draft');
    expect(screen.getByRole('tab', { name: '模型分配' })).toBeEnabled();
  });

  it('模型分配的未保存草稿阻止离开当前面板', async () => {
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        assignments: { roles: { chat: 'first' } },
        roles_meta: [{ role: 'chat', label: '主对话' }],
        library: [{ model_ref: 'first' }, { model_ref: 'second' }],
      },
    });
    renderConfig();
    await readyHostField();
    await selectReadyTab('模型分配');
    const assignment = await screen.findByRole('combobox');
    await waitFor(() => expect(assignment).toBeEnabled());
    await act(async () => {
      fireEvent.keyDown(assignment, { key: 'ArrowDown' });
    });
    const option = screen.getByRole('option', { name: 'second · second' });
    await act(async () => {
      option.focus();
      fireEvent.keyDown(option, { key: 'Enter' });
    });
    await selectReadyTab('环境变量');
    await answerConfirmation('切换配置面板？');
    expect(screen.getByRole('tab', { name: '模型分配' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('combobox')).toHaveTextContent('second · second');
  });

  it('模型草稿关闭需确认，保存中锁定编辑与导航', async () => {
    vi.mocked(api.configModels).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        library: [],
        entry_schema: [{ name: 'provider', path: ['provider'], kind: 'scalar', type: 'str', default: '' }],
      },
    });
    vi.mocked(api.modelsProviderModels).mockResolvedValue({
      ok: false,
      status: 503,
      error: 'offline',
      data: null,
    });
    const editorState = vi.fn();
    window.addEventListener('dashboard-editor-state', editorState);
    render(
      <>
        <ConfigManager />
        <ConfirmHost />
      </>,
    );
    await readyHostField();
    await selectReadyTab('模型库');
    await waitFor(() => expect(screen.getByRole('button', { name: '新增模型' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '新增模型' }));
    const dialog = await screen.findByRole('dialog', { name: '新增模型' });
    const provider = within(dialog).getByRole('textbox', { name: 'provider' });
    fireEvent.change(provider, { target: { value: 'Demo' } });
    expect(editorState.mock.lastCall?.[0].detail).toEqual({ dirty: true, busy: false });
    expect(screen.queryByRole('tab', { name: '环境变量' })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    const confirm = await screen.findByRole('dialog', { name: '放弃模型修改？' });
    fireEvent.click(within(confirm).getByRole('button', { name: '取消' }));
    expect(await screen.findByRole('textbox', { name: 'provider' })).toHaveValue('Demo');

    let finish!: (value: Awaited<ReturnType<typeof api.modelsLibrarySave>>) => void;
    vi.mocked(api.modelsLibrarySave).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(within(dialog).getByRole('button', { name: '保存并重载' }));
    expect(provider).toBeDisabled();
    expect(editorState.mock.lastCall?.[0].detail).toEqual({ dirty: true, busy: true });
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭对话框' }));
    expect(screen.getByRole('dialog', { name: '新增模型' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '放弃模型修改？' })).not.toBeInTheDocument();
    await act(async () => finish({ ok: false, status: 409, error: '配置已变化', data: null }));
    expect(provider).toBeEnabled();
    expect(provider).toHaveValue('Demo');
    expect(editorState.mock.lastCall?.[0].detail).toEqual({ dirty: true, busy: false });

    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    const discard = await screen.findByRole('dialog', { name: '放弃模型修改？' });
    fireEvent.click(within(discard).getByRole('button', { name: '放弃修改' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新增模型' })).not.toBeInTheDocument());
    expect(screen.getByRole('tab', { name: '模型库' })).toHaveAttribute('aria-selected', 'true');
    vi.mocked(api.env).mockResolvedValue({ ok: false, status: 503, error: 'offline', data: null });
    fireEvent.click(screen.getByRole('tab', { name: '环境变量' }));
    await screen.findByText('offline');
    expect(screen.getByRole('tab', { name: '环境变量' })).toHaveAttribute('aria-selected', 'true');
    window.removeEventListener('dashboard-editor-state', editorState);
  });

  it('冲突后的重读和放弃草稿均确认；读取中锁定编辑及顶层切换，失败后解除锁定', async () => {
    vi.mocked(api.configSave).mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: '文件已变化',
      data: null,
    });
    renderConfig();
    const host = await readyHostField();
    fireEvent.change(host, { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    await waitFor(() => expect(infoBar).toHaveBeenCalledTimes(1));
    await openMoreActions();
    fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
    await answerConfirmation('重新读取配置？');
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));
    await answerConfirmation('放弃配置修改？');
    expect(api.config).toHaveBeenCalledTimes(1);
    expect(host).toHaveValue('draft');
    let rejectRead!: (error: Error) => void;
    vi.mocked(api.config).mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectRead = reject;
        }),
    );
    fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
    await answerConfirmation('重新读取配置？', '重新读取');
    expect(host).toBeDisabled();
    expect(screen.getByRole('button', { name: '读取中…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '校验' })).toBeDisabled();
    expect(screen.getByRole('tab', { name: '环境变量' })).toBeDisabled();
    expect(fireEvent.keyDown(window, { key: 'z', ctrlKey: true })).toBe(true);
    await act(async () => rejectRead(new Error('read failed')));
    expect(host).toBeEnabled();
    expect(host).toHaveValue('draft');
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));
    await answerConfirmation('放弃配置修改？', '放弃修改');
    expect(host).toHaveValue('0.0.0.0');
  });

  it('模式切换明确丢弃草稿，TOML保留原生快捷键且禁止表单历史及默认值', async () => {
    renderConfig();
    fireEvent.change(await readyHostField(), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    const confirmation = await screen.findByRole('dialog', { name: '切换编辑方式？' });
    expect(within(confirmation).getByText(/不会转换草稿/)).toBeInTheDocument();
    await answerConfirmation('切换编辑方式？');
    expect(screen.queryByLabelText('config.toml')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    await answerConfirmation('切换编辑方式？', '切换方式');
    const textarea = screen.getByLabelText('config.toml');
    expect(textarea).toHaveValue(CONFIG_DOC.source);
    fireEvent.change(textarea, { target: { value: '# draft' } });
    expect(fireEvent.keyDown(textarea, { key: 'z', ctrlKey: true })).toBe(true);
    expect(fireEvent.keyDown(window, { key: 'y', ctrlKey: true })).toBe(true);
    await openMoreActions();
    expect(screen.getByRole('button', { name: /撤销/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重做' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '全部恢复默认' })).toBeDisabled();
    fireEvent.click(screen.getByRole('tab', { name: /表单/ }));
    await answerConfirmation('切换编辑方式？', '切换方式');
    expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    expect(screen.getByLabelText('config.toml')).toHaveValue(CONFIG_DOC.source);
  });

  it('dirty事件保护顶层tab并在卸载时清理状态', async () => {
    const listener = vi.fn();
    window.addEventListener('dashboard-editor-state', listener);
    const view = renderConfig();
    fireEvent.change(await readyHostField(), { target: { value: 'draft' } });
    expect(listener.mock.lastCall?.[0].detail).toEqual({ dirty: true, busy: false });
    fireEvent.click(screen.getByRole('tab', { name: '环境变量' }));
    await answerConfirmation('切换配置面板？');
    expect(screen.getByRole('tab', { name: '本体配置' })).toHaveAttribute('aria-selected', 'true');
    vi.mocked(api.env).mockResolvedValue({ ok: false, data: null, error: 'test', status: 500 });
    fireEvent.click(screen.getByRole('tab', { name: '环境变量' }));
    await answerConfirmation('切换配置面板？', '放弃并切换');
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: '环境变量' })).toHaveAttribute('aria-selected', 'true'),
    );
    view.unmount();
    expect(listener.mock.lastCall?.[0].detail).toEqual({ dirty: false, busy: false });
    window.removeEventListener('dashboard-editor-state', listener);
  });

  it('dirty运行时操作说明不保存草稿并确认', async () => {
    renderConfig();
    fireEvent.change(await readyHostField(), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: '重载运行时配置' }));
    expect(
      within(await screen.findByRole('dialog', { name: '重载已保存的配置？' })).getByText(/不会保存当前草稿/),
    ).toBeInTheDocument();
    await answerConfirmation('重载已保存的配置？');
    fireEvent.click(screen.getByRole('button', { name: '重启 NeoBot' }));
    expect(
      within(await screen.findByRole('dialog', { name: '重启 NeoBot？' })).getByText(/不会保存当前草稿/),
    ).toBeInTheDocument();
    await answerConfirmation('重启 NeoBot？');
    expect(api.configReload).not.toHaveBeenCalled();
    expect(api.restart).not.toHaveBeenCalled();
    expect(api.configSave).not.toHaveBeenCalled();
  });

  it('StrictMode撤销重做无重复历史，输入框及contenteditable不拦截快捷键', async () => {
    render(
      <StrictMode>
        <ConfigManager />
      </StrictMode>,
    );
    const host = await readyHostField();
    fireEvent.change(host, { target: { value: 'draft' } });
    expect(fireEvent.keyDown(host, { key: 'z', ctrlKey: true })).toBe(true);
    const editable = document.createElement('div');
    editable.contentEditable = 'true';
    editable.setAttribute('contenteditable', 'true');
    document.body.appendChild(editable);
    expect(fireEvent.keyDown(editable, { key: 'z', ctrlKey: true })).toBe(true);
    editable.remove();
    await openMoreActions();
    fireEvent.click(screen.getByRole('button', { name: /撤销/ }));
    expect(host).toHaveValue('0.0.0.0');
    fireEvent.click(screen.getByRole('button', { name: '重做' }));
    expect(host).toHaveValue('draft');
    expect(screen.getByRole('button', { name: '重做' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /撤销/ })).toHaveAccessibleName('撤销 1');
  });

  it('渲染顶部四个 tab 并默认加载本体配置', async () => {
    renderConfig();

    expect(screen.getByRole('tab', { name: '本体配置' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '环境变量' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '模型库' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '模型分配' })).toBeInTheDocument();

    await waitFor(() => expect(api.config).toHaveBeenCalledTimes(1));
  });

  it('表单模式渲染后端 schema 的字段与当前值', async () => {
    renderConfig();

    await waitFor(() => expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument());
    expect(screen.getByDisplayValue('9981')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /表单/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('切换到 TOML 模式展示原始文本', async () => {
    const user = userEvent.setup();
    renderConfig();

    await waitFor(() => expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /TOML/ }));

    const textarea = await screen.findByLabelText('config.toml');
    expect((textarea as HTMLTextAreaElement).value).toContain('host = "0.0.0.0"');
  });

  it('TOML 保存快捷键沿用版本检查和保存并重载流程，失败后保留草稿', async () => {
    renderConfig();
    await readyHostField();
    await selectReadyTab('TOML');
    const editor = screen.getByLabelText('config.toml');
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(api.configSave).not.toHaveBeenCalled();
    const source = '# 保留注释\n[bot]\nhost = "127.0.0.1"\n';
    fireEvent.change(editor, { target: { value: source } });
    let finish!: (value: Awaited<ReturnType<typeof api.configSave>>) => void;
    vi.mocked(api.configSave).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(api.configSave).toHaveBeenCalledWith({
      revision: '00000000000000000000000000000007',
      mode: 'toml',
      source,
      reload: true,
    });
    expect(editor).toBeDisabled();
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(api.configSave).toHaveBeenCalledTimes(1);
    await act(async () => finish({ ok: false, data: null, error: '文件已变化', status: 409 }));
    expect(editor).toBeEnabled();
    expect(editor).toHaveValue(source);
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(infoBar).toHaveBeenCalledWith(
      expect.objectContaining({ title: '保存失败：配置已被其它会话修改', tone: 'err', duration: 0 }),
    );
    expect(notify).not.toHaveBeenCalled();
  });

  it('会话变为只读时保留 TOML 草稿并锁住输入和保存快捷键', async () => {
    const rendered = renderConfig();
    await readyHostField();
    await selectReadyTab('TOML');
    const editor = screen.getByLabelText('config.toml');
    fireEvent.change(editor, { target: { value: '# 尚未保存的草稿' } });
    auth.canManage = false;
    rendered.rerender(
      <>
        <ConfigManager />
        <ConfirmHost />
      </>,
    );
    expect(editor).toHaveAttribute('readonly');
    fireEvent.change(editor, { target: { value: '# 不应修改' } });
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(api.configSave).not.toHaveBeenCalled();
    expect(editor).toHaveValue('# 尚未保存的草稿');
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重载运行时配置' })).toBeDisabled();
  });

  it('修改字段后进入脏状态并给出未保存提示', async () => {
    const user = userEvent.setup();
    renderConfig();

    const host = await readyHostField();
    await user.clear(host);
    await user.type(host, '127.0.0.1');

    await waitFor(() => expect(screen.getByText('有未保存的修改')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeEnabled();
  });
});
