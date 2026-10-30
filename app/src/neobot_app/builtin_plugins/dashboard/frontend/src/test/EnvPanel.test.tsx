import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { api } from '../api/endpoints';
import type { EnvPayload } from '../api/types';
import { EnvPanel } from '../pages/config/EnvPanel';
import { ConfirmHost } from '../components/ui/ConfirmDialog';
import userEvent from '@testing-library/user-event';
import { infoBar, notify } from '../notifications/infoBar';

vi.mock('../api/endpoints', () => ({
  api: { env: vi.fn(), envSave: vi.fn(), envAddPlatform: vi.fn(), restart: vi.fn() },
}));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));

const document: EnvPayload = {
  revision: '00000000000000000000000000000007',
  items: [
    { key: 'DeepSeek_APIKey', builtin: true, in_file: true, sensitive: true, has_value: true, value: '' },
    { key: 'CUSTOM_VALUE', builtin: false, in_file: true, value: 'hello', has_value: true },
    { key: 'DeepSeek_URL', builtin: true, in_file: false, value: '', has_value: false },
  ],
  platforms: [],
};
const ok = (data: EnvPayload) => ({ ok: true, data, error: null, status: 200 });

function renderEnv() {
  return render(
    <>
      <EnvPanel />
      <ConfirmHost />
    </>,
  );
}

async function answerConfirmation(title: string, answer: string) {
  const dialog = await screen.findByRole('dialog', { name: title });
  await userEvent.click(within(dialog).getByRole('button', { name: answer }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: title })).not.toBeInTheDocument());
}

async function row(key: string) {
  return within((await screen.findByText(key)).closest('.env-row') as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.env).mockResolvedValue(ok(document));
});

describe('EnvPanel 删除真实条目', () => {
  it('内置和自定义文件条目均可删除，schema占位项没有删除入口', async () => {
    renderEnv();
    expect((await row('DeepSeek_APIKey')).getByRole('button', { name: '删除' })).toBeEnabled();
    expect((await row('CUSTOM_VALUE')).getByRole('button', { name: '删除' })).toBeEnabled();
    const placeholder = await row('DeepSeek_URL');
    expect(placeholder.queryByRole('button', { name: '删除' })).not.toBeInTheDocument();
    expect(placeholder.getByText('未写入 .env')).toBeInTheDocument();
  });

  it('删除覆盖未保存的密钥编辑，保存重载后变成未写入占位项', async () => {
    vi.mocked(api.envSave).mockResolvedValue(
      ok({
        ...document,
        revision: '00000000000000000000000000000008',
        items: document.items?.map((item) =>
          item.key === 'DeepSeek_APIKey' ? { ...item, in_file: false, has_value: false } : item,
        ),
      }),
    );
    renderEnv();
    const secret = await row('DeepSeek_APIKey');
    fireEvent.change(secret.getByPlaceholderText('已设置 · 留空则不修改'), {
      target: { value: 'draft-secret' },
    });
    fireEvent.click(secret.getByRole('button', { name: '删除' }));
    await answerConfirmation('删除环境变量 DeepSeek_APIKey？', '删除变量');
    expect(secret.getByRole('button', { name: '删除' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() =>
      expect(api.envSave).toHaveBeenCalledWith({
        updates: {},
        deletes: ['DeepSeek_APIKey'],
        revision: '00000000000000000000000000000007',
        reload: true,
      }),
    );
    expect((await row('DeepSeek_APIKey')).getByText('未写入 .env')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
  });

  it('删除自定义条目后该行消失，不影响其它条目', async () => {
    vi.mocked(api.envSave).mockResolvedValue(
      ok({
        ...document,
        items: document.items?.filter((item) => item.key !== 'CUSTOM_VALUE'),
      }),
    );
    renderEnv();
    fireEvent.click((await row('CUSTOM_VALUE')).getByRole('button', { name: '删除' }));
    await answerConfirmation('删除环境变量 CUSTOM_VALUE？', '删除变量');
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(screen.queryByText('CUSTOM_VALUE')).not.toBeInTheDocument());
    expect(screen.getByText('DeepSeek_APIKey')).toBeInTheDocument();
  });

  it('取消确认不会标记删除或触发保存', async () => {
    renderEnv();
    const custom = await row('CUSTOM_VALUE');
    fireEvent.click(custom.getByRole('button', { name: '删除' }));
    await answerConfirmation('删除环境变量 CUSTOM_VALUE？', '取消');
    expect(custom.getByDisplayValue('hello')).toBeEnabled();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    expect(api.envSave).not.toHaveBeenCalled();
  });

  it('敏感值留空是更新而非删除，删除只能由明确点击产生', async () => {
    vi.mocked(api.envSave).mockResolvedValue(ok(document));
    renderEnv();
    const secret = (await row('DeepSeek_APIKey')).getByPlaceholderText('已设置 · 留空则不修改');
    fireEvent.change(secret, { target: { value: 'draft' } });
    fireEvent.change(secret, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() =>
      expect(api.envSave).toHaveBeenCalledWith({
        updates: { DeepSeek_APIKey: '' },
        deletes: [],
        revision: '00000000000000000000000000000007',
        reload: true,
      }),
    );
  });
});

describe('EnvPanel 保存后的生效范围提示', () => {
  it('仍需重启时只发一条警告通知，底栏保留状态与确认入口', async () => {
    // 环境变量里 TTS / 生图等在启动期读取，热重载覆盖不到 —— 后端用 needs_restart 标出
    vi.mocked(api.envSave).mockResolvedValue(
      ok({
        ...document,
        revision: '00000000000000000000000000000008',
        needs_restart: true,
        message:
          '环境变量已保存并重载：平台凭据变更已重建 provider（覆盖 主对话 / 视觉 / 档案总结）。' +
          '在启动时读取环境变量的其它模块（TTS、生图、联网搜索等）需重启进程后生效。',
      }),
    );
    vi.mocked(api.restart).mockResolvedValue({
      ok: true,
      data: { message: '已请求重启' },
      error: null,
      status: 200,
    } as never);

    const { container } = renderEnv();
    const custom = await row('CUSTOM_VALUE');
    fireEvent.change(custom.getByDisplayValue('hello'), { target: { value: 'changed' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));

    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '环境变量已保存，部分配置待重启',
          tone: 'warn',
        }),
      ),
    );
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(notify).not.toHaveBeenCalled();
    expect(container.querySelector('.config-notice')).toBeNull();
    expect(screen.getByText('部分配置待重启')).toBeInTheDocument();
    const details = render(<>{vi.mocked(infoBar).mock.calls[0][0].details}</>);
    expect(details.container).toHaveTextContent('需重启进程后生效');

    fireEvent.click(screen.getByRole('button', { name: /重启 NeoBot/ }));
    await answerConfirmation('重启 NeoBot？', '重启 NeoBot');
    await waitFor(() => expect(api.restart).toHaveBeenCalledTimes(1));
  });

  it('完全热生效时不插入结果横幅，也不显示重启入口', async () => {
    vi.mocked(api.envSave).mockResolvedValue(
      ok({
        ...document,
        revision: '00000000000000000000000000000008',
        needs_restart: false,
        message: '未检测到环境变量改动；已重载配置。',
      }),
    );

    const { container } = renderEnv();
    const custom = await row('CUSTOM_VALUE');
    fireEvent.change(custom.getByDisplayValue('hello'), { target: { value: 'changed' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));

    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '环境变量已保存',
          tone: 'ok',
        }),
      ),
    );
    expect(infoBar).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.config-notice')).toBeNull();
    expect(screen.queryByRole('button', { name: /重启 NeoBot/ })).not.toBeInTheDocument();
  });

  it('阻塞读取错误仍显示在内容中，不转为瞬时通知', async () => {
    vi.mocked(api.env).mockResolvedValue({ ok: false, status: 500, error: '环境变量读取失败', data: null });
    renderEnv();
    expect(await screen.findByRole('alert')).toHaveTextContent('环境变量读取失败');
    expect(infoBar).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '重试' })).toBeEnabled();
  });
});
