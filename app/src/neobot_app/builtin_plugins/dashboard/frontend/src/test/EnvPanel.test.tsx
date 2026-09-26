import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { api } from '../api/endpoints';
import type { EnvPayload } from '../api/types';
import { EnvPanel } from '../pages/config/EnvPanel';

vi.mock('../api/endpoints', () => ({
  api: { env: vi.fn(), envSave: vi.fn(), envAddPlatform: vi.fn() },
}));
vi.mock('../components/Toast', () => ({ toast: vi.fn() }));

const document: EnvPayload = {
  revision: 7,
  items: [
    { key: 'DeepSeek_APIKey', builtin: true, in_file: true, sensitive: true, has_value: true, value: '' },
    { key: 'CUSTOM_VALUE', builtin: false, in_file: true, value: 'hello', has_value: true },
    { key: 'DeepSeek_URL', builtin: true, in_file: false, value: '', has_value: false },
  ],
  platforms: [],
};
const ok = (data: EnvPayload) => ({ ok: true, data, error: null, status: 200 });

async function row(key: string) {
  return within((await screen.findByText(key)).closest('.env-row') as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.mocked(api.env).mockResolvedValue(ok(document));
});

describe('EnvPanel 删除真实条目', () => {
  it('内置和自定义文件条目均可删除，schema占位项没有删除入口', async () => {
    render(<EnvPanel />);
    expect((await row('DeepSeek_APIKey')).getByRole('button', { name: '删除' })).toBeEnabled();
    expect((await row('CUSTOM_VALUE')).getByRole('button', { name: '删除' })).toBeEnabled();
    const placeholder = await row('DeepSeek_URL');
    expect(placeholder.queryByRole('button', { name: '删除' })).not.toBeInTheDocument();
    expect(placeholder.getByText('未写入 .env')).toBeInTheDocument();
  });

  it('删除覆盖未保存的密钥编辑，保存重载后变成未写入占位项', async () => {
    vi.mocked(api.envSave).mockResolvedValue(ok({
      ...document, revision: 8,
      items: document.items?.map(item => item.key === 'DeepSeek_APIKey'
        ? { ...item, in_file: false, has_value: false } : item),
    }));
    render(<EnvPanel />);
    const secret = await row('DeepSeek_APIKey');
    fireEvent.change(secret.getByPlaceholderText('已设置 · 留空则不修改'), { target: { value: 'draft-secret' } });
    fireEvent.click(secret.getByRole('button', { name: '删除' }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('DeepSeek_APIKey'));
    expect(secret.getByRole('button', { name: '删除' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(api.envSave).toHaveBeenCalledWith({
      updates: {}, deletes: ['DeepSeek_APIKey'], revision: 7, reload: true,
    }));
    expect((await row('DeepSeek_APIKey')).getByText('未写入 .env')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
  });

  it('删除自定义条目后该行消失，不影响其它条目', async () => {
    vi.mocked(api.envSave).mockResolvedValue(ok({
      ...document, items: document.items?.filter(item => item.key !== 'CUSTOM_VALUE'),
    }));
    render(<EnvPanel />);
    fireEvent.click((await row('CUSTOM_VALUE')).getByRole('button', { name: '删除' }));
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(screen.queryByText('CUSTOM_VALUE')).not.toBeInTheDocument());
    expect(screen.getByText('DeepSeek_APIKey')).toBeInTheDocument();
  });

  it('取消确认不会标记删除或触发保存', async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<EnvPanel />);
    const custom = await row('CUSTOM_VALUE');
    fireEvent.click(custom.getByRole('button', { name: '删除' }));
    expect(custom.getByDisplayValue('hello')).toBeEnabled();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    expect(api.envSave).not.toHaveBeenCalled();
  });

  it('敏感值留空是更新而非删除，删除只能由明确点击产生', async () => {
    vi.mocked(api.envSave).mockResolvedValue(ok(document));
    render(<EnvPanel />);
    const secret = (await row('DeepSeek_APIKey')).getByPlaceholderText('已设置 · 留空则不修改');
    fireEvent.change(secret, { target: { value: 'draft' } });
    fireEvent.change(secret, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(api.envSave).toHaveBeenCalledWith({
      updates: { DeepSeek_APIKey: '' }, deletes: [], revision: 7, reload: true,
    }));
  });
});
