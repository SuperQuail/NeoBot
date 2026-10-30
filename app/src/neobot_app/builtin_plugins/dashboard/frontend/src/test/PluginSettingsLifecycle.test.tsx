import type { ComponentProps } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { ConfigDocument, Result } from '../api/types';
import { clearQueries, setQueryData } from '../data/queryCore';
import { POLL, QK } from '../data/queryKeys';
import Plugins from '../pages/Plugins';
import PluginManualEntry from '../pages/plugins/PluginManualEntry';
import PluginPonderPlayer from '../pages/plugins/PluginPonderPlayer';
import PluginSettingsViews from '../pages/plugins/PluginSettingsViews';
import type { PluginViewSurface } from '../pages/plugins/pluginViewBridge';

const auth = vi.hoisted(() => ({ canManage: true as boolean | null }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));
vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../api/endpoints', () => ({
  api: {
    plugins: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    pluginSurface: vi.fn(),
    pluginViews: vi.fn(),
    pluginAction: vi.fn(),
  },
}));
vi.mock('../pages/plugins/PluginSettingsViews', () => ({
  default: vi.fn((props: ComponentProps<typeof PluginSettingsViews>) => (
    <button onClick={() => void props.configAccess.save({ note: '来自设置' }, revision)}>业务设置保存</button>
  )),
}));
vi.mock('../pages/plugins/PluginPonderPlayer', () => ({
  default: vi.fn((props: ComponentProps<typeof PluginPonderPlayer>) => (
    <div role="dialog" aria-label="说明书">
      <button onClick={props.onClose}>关闭说明</button>
    </div>
  )),
}));

const revision = '00000000000000000000000000000021';
const configDocument: ConfigDocument = {
  config: { note: '原值' },
  schema: [{ name: 'note', path: ['note'], kind: 'scalar', type: 'str', value: '原值' }],
  revision,
  form_supported: true,
};
const surface: PluginViewSurface = {
  available: true,
  state: 'loaded',
  source: 'runtime',
  permissions: ['read', 'manage'],
  contract: {
    schema_version: 1,
    plugin: { name: 'demo' },
    config: { type: 'object', properties: { note: { type: 'string' } } },
    actions: [],
    resources: [],
    guides: [{ id: 'start', title: '入门', steps: [{ target: 'config.note', text: '填写备注。' }] }],
    views: [{ id: 'editor', title: '业务设置', entry: 'web/index.html', anchors: [] }],
  },
};

function ok<T>(data: T): Result<T> {
  return { ok: true, status: 200, error: null, data };
}

function leavingIsBlocked() {
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

async function leaveConfig() {
  await act(async () => screen.getByRole('tab', { name: '插件页面' }).focus());
}

async function openManual() {
  const button = await screen.findByRole('button', { name: '使用说明' });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  expect(screen.getByRole('dialog', { name: '说明书' })).toBeVisible();
}

beforeEach(() => {
  vi.clearAllMocks();
  clearQueries();
  auth.canManage = true;
  vi.mocked(api.plugins).mockResolvedValue({
    manage_enabled: true,
    items: [{ name: 'demo', version: '1.0', status: 'loaded', enabled: true }],
  });
  vi.mocked(api.pluginConfig).mockResolvedValue(ok(configDocument));
  vi.mocked(api.pluginConfigSave).mockResolvedValue(ok({ ...configDocument, config: { note: '来自设置' } }));
  vi.mocked(api.pluginSurface).mockResolvedValue(ok(surface));
});

describe('插件设置与原编辑会话的恢复', () => {
  it('配置和插件页面独立导航，键盘切换保留配置输入并暂停隐藏页面', async () => {
    render(<Plugins />);
    const input = await screen.findByRole('textbox', { name: 'note' });
    const configTab = screen.getByRole('tab', { name: '配置表单' });
    const pageTab = await screen.findByRole('tab', { name: '插件页面' });
    expect(configTab).toHaveAttribute('aria-selected', 'true');
    expect(vi.mocked(PluginSettingsViews).mock.lastCall![0].suspended).toBe(true);
    configTab.focus();
    fireEvent.keyDown(configTab, { key: 'End' });
    expect(pageTab).toHaveFocus();
    expect(pageTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('textbox', { name: 'note' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存并重载' })).not.toBeInTheDocument();
    expect(vi.mocked(PluginSettingsViews).mock.lastCall![0].suspended).toBe(false);
    const pageControl = screen.getByRole('button', { name: '业务设置保存' });
    fireEvent.keyDown(pageTab, { key: 'Home' });
    expect(configTab).toHaveFocus();
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
    expect(pageControl).toBeInTheDocument();
    expect(vi.mocked(PluginSettingsViews).mock.lastCall![0].suspended).toBe(true);
  });

  it('输入回到保存基线后，离开原编辑区释放会话并允许独立设置保存', async () => {
    render(<Plugins />);
    const input = await screen.findByRole('textbox', { name: 'note' });
    input.focus();
    fireEvent.input(input, { target: { value: '临时备注' } });
    fireEvent.input(input, { target: { value: '原值' } });
    expect(screen.getByText('配置与文件同步')).toBeInTheDocument();
    expect(leavingIsBlocked()).toBe(true);
    await leaveConfig();
    expect(leavingIsBlocked()).toBe(false);
    await userEvent.click(screen.getByRole('tab', { name: '插件页面' }));
    await userEvent.click(screen.getByRole('button', { name: '业务设置保存' }));
    expect(api.pluginConfigSave).toHaveBeenCalledWith('demo', {
      mode: 'form',
      config: { note: '来自设置' },
      revision,
      reload: true,
    });
    await userEvent.click(screen.getByRole('tab', { name: '配置表单' }));
    expect(await screen.findByRole('textbox', { name: 'note' })).toHaveValue('来自设置');
  });

  it.each(['非法 JSON', '待添加键值'] as const)('%s 失焦后仍保护本地草稿并阻止独立设置覆盖', async (kind) => {
    const payload = kind === '非法 JSON' ? { nested: [1] } : {};
    vi.mocked(api.pluginConfig).mockResolvedValue(
      ok({
        ...configDocument,
        config: { payload },
        schema: [{ name: 'payload', path: ['payload'], kind: 'dict', value: payload }],
      }),
    );
    render(<Plugins />);
    const input = await screen.findByRole('textbox', {
      name: kind === '非法 JSON' ? 'payload' : '新增条目的键',
    });
    input.focus();
    const text = kind === '非法 JSON' ? '{"unfinished":' : '未点击添加的键';
    fireEvent.input(input, { target: { value: text } });
    await leaveConfig();
    expect(input).toHaveValue(text);
    expect(leavingIsBlocked()).toBe(true);
    await userEvent.click(screen.getByRole('tab', { name: '插件页面' }));
    await userEvent.click(screen.getByRole('button', { name: '业务设置保存' }));
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('tab', { name: '配置表单' }));
    expect(screen.getByRole('textbox', { name: kind === '非法 JSON' ? 'payload' : '新增条目的键' })).toBe(
      input,
    );
  });

  it('组字期间失焦不释放会话，组字完成后的正常失焦才释放', async () => {
    render(<Plugins />);
    const input = await screen.findByRole('textbox', { name: 'note' });
    input.focus();
    fireEvent.compositionStart(input);
    fireEvent.input(input, { target: { value: '原值' } });
    await leaveConfig();
    expect(leavingIsBlocked()).toBe(true);
    await userEvent.click(screen.getByRole('tab', { name: '插件页面' }));
    await userEvent.click(screen.getByRole('button', { name: '业务设置保存' }));
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('tab', { name: '配置表单' }));
    fireEvent.compositionEnd(input, { data: '原值' });
    input.focus();
    await leaveConfig();
    expect(leavingIsBlocked()).toBe(false);
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
  });

  it('释放已回到基线的会话后，旧读取仍不能更新当前输入或保存版本', async () => {
    vi.useFakeTimers();
    try {
      let finish!: (value: Result<ConfigDocument>) => void;
      vi.mocked(api.pluginConfig)
        .mockResolvedValueOnce(ok(configDocument))
        .mockReturnValueOnce(
          new Promise((resolve) => {
            finish = resolve;
          }),
        );
      render(<Plugins />);
      await act(async () => {});
      const input = screen.getByRole('textbox', { name: 'note' });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(api.pluginConfig).toHaveBeenCalledTimes(2);
      input.focus();
      fireEvent.input(input, { target: { value: '临时备注' } });
      fireEvent.input(input, { target: { value: '原值' } });
      await leaveConfig();
      await act(async () =>
        finish(
          ok({
            ...configDocument,
            revision: '00000000000000000000000000000022',
            config: { note: '迟到的服务端值' },
          }),
        ),
      );
      expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
      expect(input).toHaveValue('原值');
      fireEvent.input(input, { target: { value: '新修改' } });
      fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
      await act(async () => {});
      expect(api.pluginConfigSave).toHaveBeenCalledWith(
        'demo',
        expect.objectContaining({ revision, config: { note: '新修改' } }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('鉴权尚未探测完成时移除设置管理权限并拒绝配置保存', async () => {
    auth.canManage = null;
    render(<Plugins />);
    await userEvent.click(await screen.findByRole('tab', { name: '插件页面' }));
    const button = await screen.findByRole('button', { name: '业务设置保存' });
    const settings = vi.mocked(PluginSettingsViews).mock.lastCall![0];
    expect(settings.surface.permissions).toEqual(['read']);
    await userEvent.click(button);
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });
});

describe('说明书暂停状态的归还', () => {
  it('回调身份变化不关闭说明书，卸载时通过最新回调归还一次暂停状态', async () => {
    const first = vi.fn();
    const current = vi.fn();
    const test = render(<PluginManualEntry pluginId="demo" onOpenChange={first} />);
    await openManual();
    expect(first).toHaveBeenCalledWith(true);
    test.rerender(<PluginManualEntry pluginId="demo" onOpenChange={current} />);
    expect(screen.getByRole('dialog', { name: '说明书' })).toBeVisible();
    expect(first).not.toHaveBeenCalledWith(false);
    expect(current).not.toHaveBeenCalled();
    test.unmount();
    expect(current).toHaveBeenCalledTimes(1);
    expect(current).toHaveBeenCalledWith(false);
  });

  it('打开的说明被后台移除时自动关闭并归还暂停状态', async () => {
    const onOpenChange = vi.fn();
    render(<PluginManualEntry pluginId="demo" onOpenChange={onOpenChange} />);
    await openManual();
    act(() =>
      setQueryData(QK.pluginSurface('demo'), { ...surface, contract: { ...surface.contract, guides: [] } }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenLastCalledWith(false));
    expect(onOpenChange).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '使用说明' })).not.toBeInTheDocument();
  });
});
