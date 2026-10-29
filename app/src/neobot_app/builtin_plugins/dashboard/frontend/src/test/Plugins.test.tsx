// Plugins 页面回归测试 —— 列表分组、选中态、按钮可用性
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Plugins from '../pages/Plugins';
import { api } from '../api/endpoints';
import type { ConfigDocument } from '../api/types';
import { infoBar, notify } from '../notifications/infoBar';
import { POLL } from '../data/queryKeys';
import { ConfirmHost } from '../components/ui/ConfirmDialog';

vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));

vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
const auth = vi.hoisted(() => ({ canManage: true }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));

vi.mock('../api/endpoints', () => ({
  api: {
    plugins: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    pluginToggle: vi.fn(),
    pluginReload: vi.fn(),
    pluginUpdate: vi.fn(),
    pluginUninstall: vi.fn(),
    pluginInstall: vi.fn(),
    pluginsCheckUpdates: vi.fn(),
    pluginsProxySave: vi.fn(),
  },
}));

const PLUGIN_LIST = {
  console_plugin: 'dashboard',
  manage_enabled: true,
  hot_reload: true,
  proxy: { mode: 'system', description: '跟随系统' },
  items: [
    {
      id: 'dashboard',
      name: 'dashboard',
      version: '1.0.0',
      official: true,
      source: 'official',
      status: 'loaded',
      enabled: true,
      manageable: false,
      hot_reload: false,
      config_hot_reload: true,
      description: '网页面板',
    },
    {
      id: 'memo',
      name: 'memo',
      version: '0.2.0',
      official: false,
      source: 'third_party',
      status: 'disabled',
      enabled: false,
      manageable: true,
      hot_reload: true,
      description: '记忆插件',
    },
  ],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.canManage = true;
  vi.mocked(api.plugins).mockResolvedValue(PLUGIN_LIST);
  // 配置详情保持在加载中，聚焦列表与工具栏行为
  vi.mocked(api.pluginConfig).mockImplementation(() => new Promise(() => {}));
});

describe('Plugins 页面', () => {
  it('官方发言时段保存数组、保留精确分钟及冲突草稿，并沿用撤销与 TOML 路径', async () => {
    const schedule = {
      ...PLUGIN_LIST.items[0],
      id: 'speaking_schedule',
      name: 'speaking_schedule',
      manageable: true,
    };
    vi.mocked(api.plugins).mockResolvedValue({ ...PLUGIN_LIST, items: [schedule] });
    const config = {
      timezone: 'Asia/Shanghai',
      windows: [{ weekdays: [1], start: '08:13', end: '18:00', next_day: false }],
      overrides: [],
      extra: 'keep',
    };
    const doc = {
      revision: 12,
      config,
      form_supported: true,
      source_available: true,
      source: 'timezone = "Asia/Shanghai"',
      schema: [],
    };
    vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, status: 200, error: null, data: doc });
    vi.mocked(api.pluginConfigSave).mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: '文件已变化',
      data: null,
    });
    render(
      <>
        <Plugins />
        <ConfirmHost />
      </>,
    );
    const start = await screen.findByLabelText('默认窗口 1 开始时间');
    fireEvent.change(start, { target: { value: '08:17' } });
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() =>
      expect(api.pluginConfigSave).toHaveBeenCalledWith('speaking_schedule', {
        revision: 12,
        mode: 'form',
        reload: true,
        config: { ...config, windows: [{ ...config.windows[0], start: '08:17' }] },
      }),
    );
    expect(await screen.findByText('文件已变化')).toBeInTheDocument();
    expect(start).toHaveValue('08:17');
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));
    fireEvent.click(
      within(await screen.findByRole('dialog', { name: '放弃配置修改？' })).getByRole('button', {
        name: '放弃修改',
      }),
    );
    await waitFor(() => expect(screen.getByLabelText('默认窗口 1 开始时间')).toHaveValue('08:13'));
    fireEvent.click(screen.getByRole('tab', { name: 'TOML' }));
    expect(screen.getByLabelText('TOML 配置')).toHaveValue(doc.source);
  });

  it('发言时段的无效持续时间禁止保存，第三方同名插件仍走通用字段', async () => {
    const config = {
      timezone: 'Asia/Shanghai',
      windows: [{ weekdays: [1], start: '08:13', end: '18:00', next_day: false }],
      overrides: [],
    };
    const schedule = { ...PLUGIN_LIST.items[0], id: 'speaking_schedule', name: 'speaking_schedule' };
    vi.mocked(api.plugins).mockResolvedValue({ ...PLUGIN_LIST, items: [schedule] });
    vi.mocked(api.pluginConfig).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: { revision: 1, config, form_supported: true, schema: [] },
    });
    const rendered = render(<Plugins />);
    fireEvent.change(await screen.findByLabelText('默认窗口 1 开始时间'), { target: { value: '20:00' } });
    expect(screen.getByRole('alert')).toHaveTextContent('时长必须大于 0 且小于 24 小时');
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    rendered.unmount();
    vi.mocked(api.plugins).mockResolvedValue({ ...PLUGIN_LIST, items: [{ ...schedule, official: false }] });
    vi.mocked(api.pluginConfig).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        config: { greeting: '通用字段' },
        form_supported: true,
        schema: [{ name: 'greeting', path: ['greeting'], kind: 'scalar', type: 'str', value: '通用字段' }],
      },
    });
    render(<Plugins />);
    expect(await screen.findByDisplayValue('通用字段')).toBeInTheDocument();
    expect(screen.queryByLabelText('时区')).not.toBeInTheDocument();
  });

  it('列表首读慢于多个轮询周期时不重叠，返回后恢复自动读取', async () => {
    vi.useFakeTimers();
    try {
      const first = deferred<Awaited<ReturnType<typeof api.plugins>>>();
      vi.mocked(api.plugins).mockReturnValueOnce(first.promise);
      render(<Plugins />);
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.plugins * 3);
      });
      expect(api.plugins).toHaveBeenCalledTimes(1);
      expect(api.pluginConfig).not.toHaveBeenCalled();

      await act(async () => {
        first.resolve(PLUGIN_LIST);
      });
      expect(screen.getByRole('heading', { name: 'dashboard' })).toBeInTheDocument();
      expect(api.plugins).toHaveBeenCalledTimes(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.plugins);
      });
      expect(api.plugins).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(['非法 JSON', '待添加键值'] as const)(
    '列表自动移除选中插件时保留 %s 的原输入节点，恢复插件后继续编辑',
    async (kind) => {
      vi.useFakeTimers();
      try {
        const doc: ConfigDocument = {
          revision: 3,
          config: { payload: kind === '非法 JSON' ? { nested: [1] } : {} },
          form_supported: true,
          schema: [
            {
              name: 'payload',
              path: ['payload'],
              kind: 'dict',
              value: kind === '非法 JSON' ? { nested: [1] } : {},
            },
          ],
        };
        vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, status: 200, error: null, data: doc });
        render(<Plugins />);
        await act(async () => {});
        const input = screen.getByRole('textbox', {
          name: kind === '非法 JSON' ? 'payload' : '新增条目的键',
        });
        const text = kind === '非法 JSON' ? '{"unfinished":' : '未点击添加的键';
        // 原生 input 事件同时覆盖组件本地草稿与页面的编辑会话捕获。
        fireEvent.input(input, { target: { value: text } });
        fireEvent.blur(input);
        expect(input).toHaveValue(text);
        if (kind === '非法 JSON') expect(input).toHaveAttribute('aria-invalid', 'true');
        expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();

        vi.mocked(api.plugins).mockResolvedValue({ ...PLUGIN_LIST, items: [PLUGIN_LIST.items[1]] });
        await act(async () => {
          await vi.advanceTimersByTimeAsync(POLL.editor);
        });
        expect(api.plugins).toHaveBeenCalledTimes(2);
        expect(api.pluginConfig).toHaveBeenCalledTimes(1);
        expect(screen.getByRole('heading', { name: 'dashboard' })).toBeInTheDocument();
        expect(screen.getByText('插件已不在列表中')).toBeInTheDocument();
        expect(screen.getByText('当前编辑内容已保留，恢复插件后再保存。')).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: kind === '非法 JSON' ? 'payload' : '新增条目的键' })).toBe(
          input,
        );
        expect(input).toHaveValue(text);
        expect(input).toBeDisabled();
        expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
        const leaving = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(leaving);
        expect(leaving.defaultPrevented).toBe(true);

        vi.mocked(api.plugins).mockResolvedValue(PLUGIN_LIST);
        await act(async () => {
          await vi.advanceTimersByTimeAsync(POLL.plugins);
        });
        expect(screen.queryByText('插件已不在列表中')).not.toBeInTheDocument();
        expect(input).toHaveValue(text);
        expect(input).toBeEnabled();
        expect(api.pluginConfig).toHaveBeenCalledTimes(1);
      } finally {
        vi.useRealTimers();
      }
    },
  );

  it('写操作遇在途列表请求时等待后补一次新读取，旧状态不回灌', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.pluginConfig).mockResolvedValue({
        ok: true,
        status: 200,
        error: null,
        data: { revision: 1, config: {}, form_supported: true, schema: [] },
      });
      render(<Plugins />);
      await act(async () => {});
      await act(async () => {
        fireEvent.click(
          within(screen.getByRole('complementary', { name: '插件列表' })).getByRole('button', {
            name: /memo/,
          }),
        );
      });
      const stale = deferred<Awaited<ReturnType<typeof api.plugins>>>();
      const fresh = deferred<Awaited<ReturnType<typeof api.plugins>>>();
      vi.mocked(api.plugins).mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.plugins);
      });
      expect(api.plugins).toHaveBeenCalledTimes(2);

      vi.mocked(api.pluginToggle).mockResolvedValue({ ok: true, status: 200, error: null, data: {} });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '启用插件' }));
      });
      expect(api.pluginToggle).toHaveBeenCalledWith('memo');
      // 写入成功后仍等待旧请求，不能同时发送第二个列表请求。
      expect(api.plugins).toHaveBeenCalledTimes(2);
      await act(async () => {
        stale.resolve({
          ...PLUGIN_LIST,
          items: PLUGIN_LIST.items.map((item) => (item.id === 'memo' ? { ...item, version: 'stale' } : item)),
        });
      });
      expect(api.plugins).toHaveBeenCalledTimes(3);
      expect(screen.queryByText('vstale')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: '启用插件' })).toBeDisabled();

      await act(async () => {
        fresh.resolve({
          ...PLUGIN_LIST,
          items: PLUGIN_LIST.items.map((item) =>
            item.id === 'memo' ? { ...item, version: '0.3.0', enabled: true, status: 'loaded' } : item,
          ),
        });
      });
      expect(screen.getByRole('button', { name: '停用插件' })).toBeEnabled();
      expect(screen.getByText('v0.3.0')).toBeInTheDocument();
      expect(api.plugins).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('配置保存只产生一条通知，未生效结果保留警告及完整原因', async () => {
    const document = {
      revision: 1,
      config: { greeting: '原始内容' },
      form_supported: true,
      schema: [
        { name: 'greeting', path: ['greeting'], kind: 'scalar' as const, type: 'str', value: '原始内容' },
      ],
    };
    vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, status: 200, error: null, data: document });
    vi.mocked(api.pluginConfigSave).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: { ...document, applied: false, message: '配置已保存，但监听端口需重启 NeoBot 后生效' },
    });
    const { container } = render(<Plugins />);
    fireEvent.change(await screen.findByDisplayValue('原始内容'), { target: { value: '新的内容' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '配置已保存，尚未生效',
          tone: 'warn',
        }),
      ),
    );
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(notify).not.toHaveBeenCalled();
    expect(container.querySelector('.inline-alert--success')).toBeNull();
    const details = render(<>{vi.mocked(infoBar).mock.calls[0][0].details}</>);
    expect(details.container).toHaveTextContent('监听端口需重启 NeoBot 后生效');
  });
  it('按状态分组渲染插件，并默认选中第一个运行中的插件', async () => {
    render(<Plugins />);

    // 「dashboard」同时出现在列表项与右侧编辑器标题里，用 heading 定位编辑器
    expect(await screen.findByRole('heading', { name: 'dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /运行中/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /已停用/ })).toBeInTheDocument();

    const selected = await screen.findByRole('button', { current: true });
    expect(within(selected).getByText('dashboard')).toBeInTheDocument();
  });

  it('展示来源筛选与搜索框', async () => {
    render(<Plugins />);

    await screen.findByRole('heading', { name: 'dashboard' });
    expect(screen.getByRole('button', { name: '全部' })).toHaveClass('active');
    expect(screen.getByRole('button', { name: '官方' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '第三方' })).toBeInTheDocument();
    expect(screen.getByLabelText('搜索插件')).toBeInTheDocument();
  });

  it('搜索无结果时给出空状态', async () => {
    const user = userEvent.setup();
    render(<Plugins />);

    const search = await screen.findByLabelText('搜索插件');
    await user.type(search, '不存在的插件');

    expect(await screen.findByText('没有匹配的插件')).toBeInTheDocument();
  });

  it('配置未就绪时保存/重载按钮禁用，面板自身不允许热重载', async () => {
    render(<Plugins />);

    await screen.findByRole('heading', { name: 'dashboard' });

    // dashboard 是面板自身（console_plugin），不允许热重载
    expect(screen.getByRole('button', { name: '重载插件' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    // 配置详情尚未返回，底部状态应提示等待配置
    expect(screen.getByText('等待配置')).toBeInTheDocument();
  });

  it('刷新插件状态不会重新读取配置或覆盖未保存的草稿', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.plugins).mockImplementation(async () => structuredClone(PLUGIN_LIST));
      vi.mocked(api.pluginConfig).mockResolvedValue({
        ok: true,
        status: 200,
        error: null,
        data: {
          config: { greeting: '原始内容' },
          source: 'greeting = "原始内容"',
          form_supported: true,
          source_available: true,
          schema: [{ name: 'greeting', path: ['greeting'], kind: 'scalar', type: 'str', value: '原始内容' }],
        },
      });
      render(<Plugins />);
      await act(async () => {});
      const field = screen.getByDisplayValue('原始内容');
      fireEvent.change(field, { target: { value: '尚未保存的内容' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(api.plugins).toHaveBeenCalledTimes(2);
      expect(api.pluginConfig).toHaveBeenCalledTimes(1);
      expect(screen.getByDisplayValue('尚未保存的内容')).toBeInTheDocument();
      expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('TOML 草稿在刷新列表后保留，快捷键保存遵守忙碌与版本检查', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(api.plugins).mockImplementation(async () => structuredClone(PLUGIN_LIST));
      vi.mocked(api.pluginConfig).mockResolvedValue({
        ok: true,
        status: 200,
        error: null,
        data: {
          revision: 3,
          config: {},
          source: '[config]\nenabled = true\n',
          form_supported: true,
          source_available: true,
          schema: [],
        },
      });
      render(<Plugins />);
      await act(async () => {});
      const tab = screen.getByRole('tab', { name: 'TOML' });
      expect(tab).toBeEnabled();
      fireEvent.click(tab);
      const editor = screen.getByLabelText('TOML 配置');
      fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
      expect(api.pluginConfigSave).not.toHaveBeenCalled();
      const source = '# 插件草稿\n[config]\nenabled = false\n';
      fireEvent.change(editor, { target: { value: source } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(api.plugins).toHaveBeenCalledTimes(2);
      expect(editor).toHaveValue(source);
      expect(api.pluginConfig).toHaveBeenCalledTimes(1);
      let finish!: (value: Awaited<ReturnType<typeof api.pluginConfigSave>>) => void;
      vi.mocked(api.pluginConfigSave).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
      fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
      expect(api.pluginConfigSave).toHaveBeenCalledWith('dashboard', {
        revision: 3,
        mode: 'toml',
        source,
        reload: true,
      });
      expect(editor).toBeDisabled();
      fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
      expect(api.pluginConfigSave).toHaveBeenCalledTimes(1);
      await act(async () => finish({ ok: false, data: null, error: '文件已变化', status: 409 }));
      expect(editor).toHaveValue(source);
      expect(editor).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('干净配置自动跟随文件，读取途中输入时不应用旧文档或变更保存版本', async () => {
    vi.useFakeTimers();
    try {
      const doc = {
        revision: 1,
        config: { greeting: '初始配置' },
        source: 'greeting = "初始配置"',
        form_supported: true,
        source_available: true,
        schema: [
          { name: 'greeting', path: ['greeting'], kind: 'scalar' as const, type: 'str', value: '初始配置' },
        ],
      };
      vi.mocked(api.pluginConfig)
        .mockResolvedValueOnce({ ok: true, status: 200, error: null, data: doc })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          error: null,
          data: {
            ...doc,
            revision: 2,
            config: { greeting: '文件新配置' },
            source: 'greeting = "文件新配置"',
            schema: doc.schema.map((field) => ({ ...field, value: '文件新配置' })),
          },
        });
      render(<Plugins />);
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      expect(api.pluginConfig).toHaveBeenCalledTimes(2);
      expect(screen.getByDisplayValue('文件新配置')).toBeInTheDocument();
      let finish!: (value: Awaited<ReturnType<typeof api.pluginConfig>>) => void;
      vi.mocked(api.pluginConfig).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.editor);
      });
      fireEvent.change(screen.getByDisplayValue('文件新配置'), { target: { value: '请求途中键入' } });
      await act(async () => {
        finish({ ok: true, status: 200, error: null, data: { ...doc, revision: 3 } });
      });
      expect(screen.getByDisplayValue('请求途中键入')).toBeInTheDocument();
      vi.mocked(api.pluginConfigSave).mockResolvedValueOnce({
        ok: false,
        data: null,
        status: 409,
        error: '文件已变化',
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
      });
      expect(api.pluginConfigSave).toHaveBeenCalledWith(
        'dashboard',
        expect.objectContaining({ revision: 2, config: { greeting: '请求途中键入' } }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('插件配置在会话只读时保留源码但禁止输入与保存', async () => {
    vi.mocked(api.pluginConfig).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        config: {},
        source: '[config]\nenabled = true',
        form_supported: true,
        source_available: true,
        schema: [],
      },
    });
    const rendered = render(<Plugins />);
    const tab = await screen.findByRole('tab', { name: 'TOML' });
    await waitFor(() => expect(tab).toBeEnabled());
    fireEvent.click(tab);
    const editor = screen.getByLabelText('TOML 配置');
    fireEvent.change(editor, { target: { value: '# 尚未保存的插件草稿' } });
    auth.canManage = false;
    rendered.rerender(<Plugins />);
    expect(editor).toHaveAttribute('readonly');
    fireEvent.change(editor, { target: { value: '# 不应修改' } });
    fireEvent.keyDown(editor, { key: 's', ctrlKey: true });
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    expect(editor).toHaveValue('# 尚未保存的插件草稿');
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
  });
});
