// ConfigManager 回归测试 —— 加载、表单渲染、模式切换、脏状态
// 目的：在后续拆组件/换数据层时锁住现有行为。
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import userEvent from '@testing-library/user-event';
import ConfigManager from '../pages/ConfigManager';
import { api } from '../api/endpoints';
import type { ConfigDocument } from '../api/types';

vi.mock('../api/endpoints.js', () => ({
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
    restart: vi.fn(),
  },
}));

const CONFIG_DOC: ConfigDocument = {
  section: 'bot',
  revision: 7,
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  vi.mocked(api.config).mockResolvedValue({ ok: true, data: CONFIG_DOC, error: null, status: 200 });
});

describe('ConfigManager 页面', () => {
  it('重读和放弃草稿均确认；读取中锁定编辑及顶层切换，失败后解除锁定', async () => {
    render(<ConfigManager />);
    const host = await screen.findByDisplayValue('0.0.0.0');
    fireEvent.change(host, { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));
    expect(window.confirm).toHaveBeenCalledTimes(2);
    expect(api.config).toHaveBeenCalledTimes(1);
    expect(host).toHaveValue('draft');
    vi.mocked(window.confirm).mockReturnValue(true);
    let rejectRead!: (error: Error) => void;
    vi.mocked(api.config).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
    fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
    expect(host).toBeDisabled();
    expect(screen.getByRole('button', { name: '读取中…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '校验' })).toBeDisabled();
    expect(screen.getByRole('tab', { name: '环境变量' })).toBeDisabled();
    expect(fireEvent.keyDown(window, { key: 'z', ctrlKey: true })).toBe(true);
    await act(async () => rejectRead(new Error('read failed')));
    expect(host).toBeEnabled();
    expect(host).toHaveValue('draft');
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));
    expect(host).toHaveValue('0.0.0.0');
  });

  it('模式切换明确丢弃草稿，TOML保留原生快捷键且禁止表单历史及默认值', async () => {
    render(<ConfigManager />);
    fireEvent.change(await screen.findByDisplayValue('0.0.0.0'), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('不会转换草稿'));
    expect(screen.queryByLabelText('config.toml')).not.toBeInTheDocument();
    vi.mocked(window.confirm).mockReturnValue(true);
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    const textarea = screen.getByLabelText('config.toml');
    expect(textarea).toHaveValue(CONFIG_DOC.source);
    fireEvent.change(textarea, { target: { value: '# draft' } });
    expect(fireEvent.keyDown(textarea, { key: 'z', ctrlKey: true })).toBe(true);
    expect(fireEvent.keyDown(window, { key: 'y', ctrlKey: true })).toBe(true);
    expect(screen.getByRole('button', { name: /撤销/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重做' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '全部恢复默认' })).toBeDisabled();
    fireEvent.click(screen.getByRole('tab', { name: /表单/ }));
    expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /TOML/ }));
    expect(screen.getByLabelText('config.toml')).toHaveValue(CONFIG_DOC.source);
  });

  it('dirty事件保护顶层tab并在卸载时清理状态', async () => {
    const listener = vi.fn();
    window.addEventListener('dashboard-editor-state', listener);
    const view = render(<ConfigManager />);
    fireEvent.change(await screen.findByDisplayValue('0.0.0.0'), { target: { value: 'draft' } });
    expect(listener.mock.lastCall?.[0].detail).toEqual({ dirty: true, busy: false });
    fireEvent.click(screen.getByRole('tab', { name: '环境变量' }));
    expect(screen.getByRole('tab', { name: '本体配置' })).toHaveAttribute('aria-selected', 'true');
    vi.mocked(window.confirm).mockReturnValue(true);
    vi.mocked(api.env).mockResolvedValue({ ok: false, data: null, error: 'test', status: 500 });
    fireEvent.click(screen.getByRole('tab', { name: '环境变量' }));
    await waitFor(() => expect(screen.getByRole('tab', { name: '环境变量' })).toHaveAttribute('aria-selected', 'true'));
    view.unmount();
    expect(listener.mock.lastCall?.[0].detail).toEqual({ dirty: false, busy: false });
    window.removeEventListener('dashboard-editor-state', listener);
  });

  it('dirty运行时操作说明不保存草稿并确认', async () => {
    render(<ConfigManager />);
    fireEvent.change(await screen.findByDisplayValue('0.0.0.0'), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: '重载运行时配置' }));
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('不会保存当前草稿'));
    fireEvent.click(screen.getByRole('button', { name: '重启 NeoBot' }));
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('不会保存当前草稿'));
    expect(api.configReload).not.toHaveBeenCalled();
    expect(api.restart).not.toHaveBeenCalled();
    expect(api.configSave).not.toHaveBeenCalled();
  });

  it('StrictMode撤销重做无重复历史，输入框及contenteditable不拦截快捷键', async () => {
    render(<StrictMode><ConfigManager /></StrictMode>);
    const host = await screen.findByDisplayValue('0.0.0.0');
    fireEvent.change(host, { target: { value: 'draft' } });
    expect(fireEvent.keyDown(host, { key: 'z', ctrlKey: true })).toBe(true);
    const editable = document.createElement('div');
    editable.contentEditable = 'true';
    editable.setAttribute('contenteditable', 'true');
    document.body.appendChild(editable);
    expect(fireEvent.keyDown(editable, { key: 'z', ctrlKey: true })).toBe(true);
    editable.remove();
    fireEvent.click(screen.getByRole('button', { name: /撤销/ }));
    expect(host).toHaveValue('0.0.0.0');
    fireEvent.click(screen.getByRole('button', { name: '重做' }));
    expect(host).toHaveValue('draft');
    expect(screen.getByRole('button', { name: '重做' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /撤销/ })).toHaveTextContent('撤销 1');
  });

  it('渲染顶部四个 tab 并默认加载本体配置', async () => {
    render(<ConfigManager />);

    expect(screen.getByRole('tab', { name: '本体配置' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '环境变量' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '模型库' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '模型分配' })).toBeInTheDocument();

    await waitFor(() => expect(api.config).toHaveBeenCalledTimes(1));
  });

  it('表单模式渲染后端 schema 的字段与当前值', async () => {
    render(<ConfigManager />);

    await waitFor(() => expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument());
    expect(screen.getByDisplayValue('9981')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /表单/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('切换到 TOML 模式展示原始文本', async () => {
    const user = userEvent.setup();
    render(<ConfigManager />);

    await waitFor(() => expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /TOML/ }));

    const textarea = await screen.findByLabelText('config.toml');
    expect((textarea as HTMLTextAreaElement).value).toContain('host = "0.0.0.0"');
  });

  it('修改字段后进入脏状态并给出未保存提示', async () => {
    const user = userEvent.setup();
    render(<ConfigManager />);

    const host = await screen.findByDisplayValue('0.0.0.0');
    await user.clear(host);
    await user.type(host, '127.0.0.1');

    await waitFor(() => expect(screen.getByText('有未保存的修改')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeEnabled();
  });
});
