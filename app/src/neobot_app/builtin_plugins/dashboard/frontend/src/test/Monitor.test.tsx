import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import MessageTrendCard from '../components/MessageTrendCard';
import MonitorList from '../components/MonitorList';

afterEach(() => vi.restoreAllMocks());

describe('一屏总览', () => {
  it('切换消息时间范围时同步更新统计和日期，不把缺失记录算成零', () => {
    const series = Array.from({ length: 10 }, (_, index) => ({
      date: `2026-10-${String(index + 1).padStart(2, '0')}`,
      count: index + 1,
    }));
    const { rerender } = render(<MessageTrendCard series={series} />);
    expect(screen.getByText('55')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7 天' }));
    expect(screen.getByRole('button', { name: '7 天' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('49')).toBeInTheDocument();
    expect(screen.getByText('10/04')).toBeInTheDocument();
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      '消息数量折线图：共 7 个数据点，最新 10 条，峰值 10 条',
    );
    rerender(<MessageTrendCard series={[{ at: '2026-10-01', count: 10 }, { at: '2026-10-02' }]} />);
    expect(screen.getByText('1 天有记录')).toBeInTheDocument();
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      '消息数量折线图：共 2 个数据点，最新 10 条，峰值 10 条',
    );
  });

  it('总览列表按可用高度分页，最后一页和数据缩短后仍能访问全部记录', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 600,
      height: 108,
    } as DOMRect);
    const items = Array.from({ length: 8 }, (_, index) => `记录 ${index + 1}`);
    const { rerender } = render(
      <MonitorList items={items} label="活动" empty="没有活动" rowHeight={36} renderItem={(item) => item} />,
    );
    const list = screen.getByRole('list', { name: '活动' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    expect(within(list).getByText('记录 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '活动下一页' }));
    expect(within(list).getByText('记录 4')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '活动下一页' }));
    expect(within(list).getByText('记录 8')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '活动下一页' })).toBeDisabled();
    rerender(
      <MonitorList
        items={items.slice(0, 2)}
        label="活动"
        empty="没有活动"
        rowHeight={36}
        renderItem={(item) => item}
      />,
    );
    expect(within(list).getByText('记录 1')).toBeInTheDocument();
    expect(within(list).getByText('记录 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '活动上一页' })).toBeDisabled();
  });
});
