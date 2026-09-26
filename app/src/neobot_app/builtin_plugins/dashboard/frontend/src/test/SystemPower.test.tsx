import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import System from '../pages/System';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';

vi.mock('../api/endpoints', () => ({
  api: {
    services: vi.fn().mockResolvedValue({ items: [] }),
    tasks: vi.fn().mockResolvedValue({ scheduled: [], background: [] }),
    statsUsage: vi.fn().mockResolvedValue({ items: [], totals: {} }),
    system: vi.fn().mockResolvedValue({}),
    powerStatus: vi.fn(),
    standbyEnter: vi.fn(), resume: vi.fn(), reboot: vi.fn(),
    setStandbyOnebot: vi.fn(), restart: vi.fn(),
  },
}));

beforeEach(() => clearQueries());

it('停止仍在进行时禁止软启动和连接切换，但保留进程重启入口', async () => {
  vi.mocked(api.powerStatus).mockResolvedValue({
    available: true, state: 'stopping', phase: 'stopping',
    standby: true, transition: true, reason: '清理仍在进行', connect_onebot: true,
  });
  render(<System />);
  expect(await screen.findByText('正在停止')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '启动运行' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '进入待机' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /待机时保持 OneBot 连接/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: '重启进程' })).toBeEnabled();
});
