import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { SystemInfo } from '../api/types';
import SystemResourceCard from '../components/SystemResourceCard';

const snapshot: SystemInfo = {
  hostname: 'neobot-host',
  os: 'Linux 6.8',
  python_version: '3.12.10',
  cpu_percent: 32.4,
  cpu_count: 8,
  mem_used_mb: 2048,
  mem_total_mb: 8192,
  mem_percent: 25,
  disk_used_gb: 120,
  disk_total_gb: 500,
  disk_percent: 24,
};

function show(props: Parameters<typeof SystemResourceCard>[0]) {
  return render(
    <MemoryRouter>
      <SystemResourceCard {...props} />
    </MemoryRouter>,
  );
}

describe('SystemResourceCard', () => {
  it('按实际快照展示三类占用、容量与主机信息，并保留系统状态入口', () => {
    show({ data: snapshot, updatedAt: 1_700_000_000_000 });
    expect(screen.getByRole('meter', { name: 'CPU 使用率' })).toHaveAttribute('aria-valuenow', '32.4');
    expect(screen.getByRole('meter', { name: '内存使用率' })).toHaveAttribute('aria-valuenow', '25');
    expect(screen.getByRole('meter', { name: '磁盘使用率' })).toHaveAttribute('aria-valuenow', '24');
    expect(screen.getByRole('region', { name: '内存' })).toHaveTextContent('2.0 / 8.0 GB');
    expect(screen.getByRole('region', { name: '磁盘' })).toHaveTextContent('120.0 / 500.0 GB');
    expect(screen.getByText('8 个逻辑核心')).toBeInTheDocument();
    expect(screen.getByText('neobot-host')).toBeInTheDocument();
    expect(screen.getByText('Linux 6.8')).toBeInTheDocument();
    expect(screen.getByText('Python 3.12.10')).toBeInTheDocument();
    expect(screen.getByText(/^更新于/)).toHaveAttribute('datetime', '2023-11-14T22:13:20.000Z');
    expect(screen.getByRole('link', { name: '系统状态' })).toHaveAttribute('href', '/system');
  });

  it('首次读取保留未知占用，不把尚未采样画成 0%', () => {
    show({ data: null, loading: true });
    expect(screen.getByText('读取中…')).toBeInTheDocument();
    expect(screen.getByText('等待采样')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
    expect(screen.queryByText('实时快照')).not.toBeInTheDocument();
  });

  it('空快照与首读失败不被呈现成健康或零使用率', () => {
    const { rerender } = show({ data: {} });
    expect(screen.getByText('暂无采样')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    rerender(
      <MemoryRouter>
        <SystemResourceCard data={null} error="连接中断" />
      </MemoryRouter>,
    );
    expect(screen.getByText('读取失败')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('暂时无法读取资源，请刷新重试。');
    expect(screen.getByRole('status')).toHaveAttribute('title', '连接中断');
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });

  it('刷新失败保留旧快照并明确过期状态，不冒充新采样', () => {
    show({ data: snapshot, error: '请求超时', updatedAt: 1_700_000_000_000 });
    expect(screen.getByText('更新失败')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('刷新失败，以下保留最近一次数据。');
    expect(screen.getByRole('meter', { name: 'CPU 使用率' })).toHaveAttribute('aria-valuenow', '32.4');
    expect(screen.getByText(/^更新于/)).toHaveAttribute('datetime', '2023-11-14T22:13:20.000Z');
    expect(screen.queryByText('实时快照')).not.toBeInTheDocument();
  });

  it('识别真实零值，只在已用和总量齐全时计算缺失占比', () => {
    show({ data: { cpu_percent: 0, mem_used_mb: 512, mem_total_mb: 1024, disk_used_gb: 20 } });
    expect(screen.getByRole('meter', { name: 'CPU 使用率' })).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByRole('meter', { name: '内存使用率' })).toHaveAttribute('aria-valuenow', '50');
    expect(screen.queryByRole('meter', { name: '磁盘使用率' })).not.toBeInTheDocument();
    const disk = screen.getByRole('region', { name: '磁盘' });
    expect(disk).toHaveTextContent('20.0 / — GB');
    expect(within(disk).getByText('未上报占用')).toBeInTheDocument();
    expect(screen.getByText('部分数据缺失')).toBeInTheDocument();
  });

  it('拒绝非法百分比与零总容量，不把错误读数截成正常区间', () => {
    show({ data: { cpu_percent: Number.NaN, mem_percent: -1, mem_total_mb: 0, disk_percent: 150 } });
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.getByText('暂无采样')).toBeInTheDocument();
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
    expect(screen.queryByText('100.0%')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '内存' })).toHaveTextContent('— / — MB');
  });
});
