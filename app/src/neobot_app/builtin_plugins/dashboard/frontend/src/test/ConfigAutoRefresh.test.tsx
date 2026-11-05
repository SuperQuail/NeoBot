import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { api } from '../api/endpoints';
import type { ConfigDocument, EnvPayload, ModelsPayload, Result } from '../api/types';
import { BotConfigPanel } from '../pages/config/BotConfigPanel';
import { EnvPanel } from '../pages/config/EnvPanel';
import { ModelsPanel } from '../pages/config/ModelsPanel';
import { AssignPanel } from '../pages/config/AssignPanel';
import { infoBar, notify } from '../notifications/infoBar';
import { POLL } from '../data/queryKeys';

vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => ({ canManage: true }) }));
vi.mock('../hooks/useReducedEffects', () => ({ useReducedEffects: () => true }));
vi.mock('../components/ui/ConfirmDialog', () => ({ confirmAction: vi.fn().mockResolvedValue(true) }));
vi.mock('../notifications/infoBar', () => ({
  infoBar: vi.fn(),
  notify: vi.fn(),
  closeInfoBarDetails: vi.fn(),
}));
vi.mock('../api/endpoints', () => ({
  api: {
    config: vi.fn(),
    configSave: vi.fn(),
    env: vi.fn(),
    envSave: vi.fn(),
    envAddPlatform: vi.fn(),
    configModels: vi.fn(),
    modelsLibrarySave: vi.fn(),
    modelsAssignmentsSave: vi.fn(),
    modelsProviderModels: vi.fn(),
    configBilling: vi.fn(),
  },
}));

const CONFIG: ConfigDocument = {
  revision: '00000000000000000000000000000007',
  source: 'host = "before"',
  config: { host: 'before', payload: { nested: [1] } },
  schema: [
    { name: 'host', path: ['host'], kind: 'scalar', type: 'str' },
    { name: 'payload', path: ['payload'], kind: 'dict' },
  ],
};
const ENV: EnvPayload = {
  revision: '00000000000000000000000000000007',
  items: [
    { key: 'CUSTOM_VALUE', value: 'before', in_file: true },
    { key: 'Demo_APIKey', sensitive: true, has_value: true, in_file: true, value: '' },
  ],
};
const MODELS: ModelsPayload = {
  revision: '00000000000000000000000000000007',
  library: [
    { model_ref: 'main', display_name: '原始模型', entry: { model_ref: 'main', display_name: '原始模型' } },
    { model_ref: 'reason', display_name: '推理模型' },
  ],
  entry_schema: [{ name: 'display_name', path: ['display_name'], kind: 'scalar', type: 'str' }],
  roles_meta: [{ role: 'primary_chat_model', required: true }],
  assignments: { roles: { primary_chat_model: 'main' } },
};
function ok<T>(data: T): Result<T> {
  return { ok: true, data, status: 200, error: null };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
async function mount(panel: ReactElement) {
  await act(async () => {
    render(panel);
  });
}
async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL.editor);
  });
}

async function chooseModel(trigger: HTMLElement, label: string) {
  await act(async () => {
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
  });
  const option = screen.getByRole('option', { name: label });
  await act(async () => {
    option.focus();
    fireEvent.keyDown(option, { key: 'Enter' });
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.mocked(api.config).mockResolvedValue(ok(structuredClone(CONFIG)));
  vi.mocked(api.env).mockResolvedValue(ok(structuredClone(ENV)));
  vi.mocked(api.configModels).mockResolvedValue(ok(structuredClone(MODELS)));
  vi.mocked(api.configBilling).mockResolvedValue(ok({ scripts: [], bindings: [] }));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('配置面板自动读取', () => {
  it.each([
    {
      name: '本体配置',
      panel: <BotConfigPanel />,
      read: api.config,
      assertRecovered: () => expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('before'),
    },
    {
      name: '环境变量',
      panel: <EnvPanel />,
      read: api.env,
      assertRecovered: () => expect(screen.getByDisplayValue('before')).toBeInTheDocument(),
    },
    {
      name: '模型库',
      panel: <ModelsPanel />,
      read: api.configModels,
      assertRecovered: () => expect(screen.getByText('2 个模型')).toBeInTheDocument(),
    },
    {
      name: '模型分配',
      panel: <AssignPanel />,
      read: api.configModels,
      assertRecovered: () =>
        expect(screen.getByRole('combobox', { name: '主对话使用的模型' })).toHaveTextContent(
          '原始模型 · main',
        ),
    },
  ])('$name 首次读取失败后，下一周期无需点击即可恢复', async ({ panel, read, assertRecovered }) => {
    vi.mocked(read).mockResolvedValueOnce({ ok: false, data: null, status: 503, error: '服务暂时不可用' });
    await mount(panel);
    expect(read).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('alert')).toHaveTextContent('服务暂时不可用');
    await tick();
    expect(read).toHaveBeenCalledTimes(2);
    assertRecovered();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(infoBar).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
  });

  it('本体配置空闲时同步文件，普通状态没有重新读取按钮或成功通知', async () => {
    await mount(<BotConfigPanel />);
    expect(api.config).toHaveBeenCalledTimes(1);
    vi.mocked(api.config).mockResolvedValue(
      ok({
        ...CONFIG,
        revision: '00000000000000000000000000000008',
        config: { ...CONFIG.config, host: 'remote' },
      }),
    );
    await tick();
    expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('remote');
    expect(api.config).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: '重新读取', hidden: true })).not.toBeInTheDocument();
    expect(infoBar).not.toHaveBeenCalled();
  });

  it('环境变量同步新值与版本，敏感字段仍为空', async () => {
    await mount(<EnvPanel />);
    vi.mocked(api.env).mockResolvedValue(
      ok({
        ...ENV,
        revision: '00000000000000000000000000000008',
        items: [{ ...ENV.items![0], value: 'remote' }, ENV.items![1]],
      }),
    );
    await tick();
    expect(screen.getByDisplayValue('remote')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('已设置 · 留空则不修改')).toHaveValue('');
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('remote'), { target: { value: 'local' } });
    vi.mocked(api.envSave).mockResolvedValue({ ok: false, data: null, status: 409, error: '冲突' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    });
    expect(api.envSave).toHaveBeenCalledWith(
      expect.objectContaining({
        revision: '00000000000000000000000000000008',
        updates: { CUSTOM_VALUE: 'local' },
      }),
    );
    expect(notify).not.toHaveBeenCalled();
  });

  it('模型库空闲时同步外部新增模型，不发成功通知', async () => {
    await mount(<ModelsPanel />);
    vi.mocked(api.configModels).mockResolvedValue(
      ok({
        ...MODELS,
        revision: '00000000000000000000000000000008',
        library: [...MODELS.library!, { model_ref: 'external' }],
      }),
    );
    await tick();
    expect(screen.getByText('external', { selector: 'code' })).toBeInTheDocument();
    expect(screen.getByText('3 个模型')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
  });

  it('模型分配同步外部修改，已保存的缺失引用也能通过自动更新恢复', async () => {
    vi.mocked(api.configModels).mockResolvedValue(
      ok({ ...MODELS, assignments: { roles: { primary_chat_model: 'missing' } } }),
    );
    await mount(<AssignPanel />);
    const select = screen.getByRole('combobox', { name: '主对话使用的模型' });
    expect(select).toHaveAttribute('aria-invalid', 'true');
    vi.mocked(api.configModels).mockResolvedValue(
      ok({ ...MODELS, revision: '00000000000000000000000000000008' }),
    );
    await tick();
    expect(select).toHaveTextContent('原始模型 · main');
    expect(select).toHaveAttribute('aria-invalid', 'false');
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
  });

  it.each(['form', 'toml'] as const)(
    '本体 %s 请求发出后开始编辑，不应用旧回包或推进保存 revision',
    async (mode) => {
      await mount(<BotConfigPanel />);
      if (mode === 'toml')
        await act(async () => {
          fireEvent.click(screen.getByRole('tab', { name: 'TOML' }));
        });
      const pending = deferred<Result<ConfigDocument>>();
      vi.mocked(api.config).mockReturnValueOnce(pending.promise);
      await tick();
      const input = screen.getByRole('textbox', { name: mode === 'toml' ? 'config.toml' : 'host' });
      fireEvent.change(input, { target: { value: mode === 'toml' ? 'host = "local"' : 'local' } });
      await act(async () => {
        pending.resolve(
          ok({
            ...CONFIG,
            revision: '00000000000000000000000000000088',
            config: { ...CONFIG.config, host: 'stale' },
            source: 'host = "stale"',
          }),
        );
      });
      expect(input).toHaveValue(mode === 'toml' ? 'host = "local"' : 'local');
      await tick();
      expect(api.config).toHaveBeenCalledTimes(2);
      vi.mocked(api.configSave).mockResolvedValue({ ok: false, data: null, status: 409, error: '版本冲突' });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
      });
      expect(api.configSave).toHaveBeenCalledWith(
        expect.objectContaining({ revision: '00000000000000000000000000000007', mode }),
      );
    },
  );

  it('未提交的非法 JSON 失焦后仍保留，既不应用在途回包也不发新读取', async () => {
    await mount(<BotConfigPanel />);
    const pending = deferred<Result<ConfigDocument>>();
    vi.mocked(api.config).mockReturnValueOnce(pending.promise);
    await tick();
    const input = screen.getByRole('textbox', { name: 'payload' });
    fireEvent.change(input, { target: { value: '{"unfinished":' } });
    fireEvent.blur(input);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: '保存并重载' })).toBeDisabled();
    await act(async () => {
      pending.resolve(
        ok({
          ...CONFIG,
          revision: '00000000000000000000000000000088',
          config: { host: 'stale', payload: { nested: [2] } },
        }),
      );
    });
    await tick();
    expect(input).toHaveValue('{"unfinished":');
    expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('before');
    expect(api.config).toHaveBeenCalledTimes(2);
  });

  it('编辑后又撤销回基线也丢弃先前在途回包，保持当前编辑会话的 revision', async () => {
    await mount(<BotConfigPanel />);
    const pending = deferred<Result<ConfigDocument>>();
    vi.mocked(api.config).mockReturnValueOnce(pending.promise);
    await tick();
    const host = screen.getByRole('textbox', { name: 'host' });
    fireEvent.change(host, { target: { value: 'local' } });
    fireEvent.change(host, { target: { value: 'before' } });
    await act(async () => {
      pending.resolve(
        ok({
          ...CONFIG,
          revision: '00000000000000000000000000000088',
          config: { ...CONFIG.config, host: 'stale' },
        }),
      );
    });
    expect(host).toHaveValue('before');
  });

  it('环境变量密钥草稿阻止在途回包覆盖及 revision 更新', async () => {
    await mount(<EnvPanel />);
    const pending = deferred<Result<EnvPayload>>();
    vi.mocked(api.env).mockReturnValueOnce(pending.promise);
    await tick();
    const secret = screen.getByPlaceholderText('已设置 · 留空则不修改');
    fireEvent.change(secret, { target: { value: 'local-secret' } });
    await act(async () => {
      pending.resolve(ok({ ...ENV, revision: '00000000000000000000000000000088' }));
    });
    await tick();
    expect(secret).toHaveValue('local-secret');
    expect(api.env).toHaveBeenCalledTimes(2);
    vi.mocked(api.envSave).mockResolvedValue({ ok: false, data: null, status: 409, error: '冲突' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    });
    expect(api.envSave).toHaveBeenCalledWith(
      expect.objectContaining({
        revision: '00000000000000000000000000000007',
        updates: { Demo_APIKey: 'local-secret' },
      }),
    );
  });

  it('供应商弹窗打开即固定环境变量版本，未开始输入也不会推进 revision', async () => {
    await mount(<EnvPanel />);
    const pending = deferred<Result<EnvPayload>>();
    vi.mocked(api.env).mockReturnValueOnce(pending.promise);
    await tick();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '一键添加 API 供应商' }));
    });
    await act(async () => {
      pending.resolve(ok({ ...ENV, revision: '00000000000000000000000000000088' }));
    });
    await tick();
    expect(api.env).toHaveBeenCalledTimes(2);
    fireEvent.change(screen.getByRole('textbox', { name: '平台名' }), { target: { value: 'NewProvider' } });
    vi.mocked(api.envAddPlatform).mockResolvedValue({ ok: false, data: null, status: 409, error: '冲突' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '保存供应商' }));
    });
    expect(api.envAddPlatform).toHaveBeenCalledWith(
      expect.objectContaining({ revision: '00000000000000000000000000000007', api_key: '' }),
    );
  });

  it('模型编辑器打开即保护基线；在途回包不能改变表单及保存 revision', async () => {
    await mount(<ModelsPanel />);
    const pending = deferred<Result<ModelsPayload>>();
    vi.mocked(api.configModels).mockReturnValueOnce(pending.promise);
    await tick();
    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: '编辑' })[0]);
    });
    const dialog = screen.getByRole('dialog', { name: '编辑模型 main' });
    await act(async () => {
      pending.resolve(ok({ ...MODELS, revision: '00000000000000000000000000000088', library: [] }));
    });
    await tick();
    expect(api.configModels).toHaveBeenCalledTimes(2);
    expect(within(dialog).getByRole('textbox', { name: 'display_name' })).toHaveValue('原始模型');
    vi.mocked(api.modelsLibrarySave).mockResolvedValue({ ok: false, data: null, status: 409, error: '冲突' });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: '仅保存' }));
    });
    expect(api.modelsLibrarySave).toHaveBeenCalledWith(
      expect.objectContaining({ revision: '00000000000000000000000000000007' }),
    );
  });

  it('模型分配在途读取期间更改选项，保留草稿和版本并暂停后续读取', async () => {
    await mount(<AssignPanel />);
    const pending = deferred<Result<ModelsPayload>>();
    vi.mocked(api.configModels).mockReturnValueOnce(pending.promise);
    await tick();
    const select = screen.getByRole('combobox', { name: '主对话使用的模型' });
    await chooseModel(select, '推理模型 · reason');
    await act(async () => {
      pending.resolve(ok({ ...MODELS, revision: '00000000000000000000000000000088' }));
    });
    await tick();
    expect(select).toHaveTextContent('推理模型 · reason');
    expect(api.configModels).toHaveBeenCalledTimes(2);
    vi.mocked(api.modelsAssignmentsSave).mockResolvedValue({
      ok: false,
      data: null,
      status: 409,
      error: '冲突',
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '保存分配' }));
    });
    expect(api.modelsAssignmentsSave).toHaveBeenCalledWith(
      expect.objectContaining({ revision: '00000000000000000000000000000007' }),
    );
  });

  it('在途读取晚于保存完成时不回滚已保存内容，保存后恢复自动更新', async () => {
    await mount(<BotConfigPanel />);
    const pending = deferred<Result<ConfigDocument>>();
    vi.mocked(api.config).mockReturnValueOnce(pending.promise);
    await tick();
    fireEvent.change(screen.getByRole('textbox', { name: 'host' }), { target: { value: 'saved' } });
    vi.mocked(api.configSave).mockResolvedValue(
      ok({
        ...CONFIG,
        revision: '00000000000000000000000000000009',
        config: { ...CONFIG.config, host: 'saved' },
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '保存并重载' }));
    });
    await act(async () => {
      pending.resolve(ok(CONFIG));
    });
    expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('saved');
    vi.mocked(api.config).mockResolvedValue(
      ok({
        ...CONFIG,
        revision: '00000000000000000000000000000010',
        config: { ...CONFIG.config, host: 'newer' },
      }),
    );
    await tick();
    expect(screen.getByRole('textbox', { name: 'host' })).toHaveValue('newer');
  });

  it('自动读取失败保留当前内容、静默显示恢复入口，后续成功清除错误', async () => {
    await mount(<EnvPanel />);
    vi.mocked(api.env).mockResolvedValueOnce({ ok: false, data: null, status: 503, error: '连接中断' });
    await tick();
    expect(screen.getByDisplayValue('before')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('连接中断');
    expect(screen.getByRole('button', { name: '重新读取' })).toBeEnabled();
    expect(infoBar).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
    await tick();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新读取' })).not.toBeInTheDocument();
  });
});
