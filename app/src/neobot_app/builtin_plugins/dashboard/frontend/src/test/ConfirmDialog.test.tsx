import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConfirmHost, confirmAction } from '../components/ui/ConfirmDialog';

describe('统一确认', () => {
  it('默认聚焦取消，取消与确认分别返回真实选择', async () => {
    render(<ConfirmHost />);
    let result: Promise<boolean>;
    act(() => {
      result = confirmAction({ title: '删除测试项', confirmLabel: '删除', danger: true });
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '取消' })).toHaveFocus());
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(await result!).toBe(false);
    act(() => {
      result = confirmAction({ title: '重新加载', confirmLabel: '加载' });
    });
    fireEvent.click(screen.getByRole('button', { name: '加载' }));
    expect(await result!).toBe(true);
  });

  it('排队确认逐个显示，每项重新聚焦取消', async () => {
    render(<ConfirmHost />);
    let first: Promise<boolean>;
    let second: Promise<boolean>;
    act(() => {
      first = confirmAction({ title: '第一项', confirmLabel: '继续第一项' });
      second = confirmAction({ title: '第二项', confirmLabel: '继续第二项' });
    });
    expect(screen.queryByRole('dialog', { name: '第二项' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '继续第一项' }));
    expect(await first!).toBe(true);
    expect(screen.getByRole('dialog', { name: '第二项' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '取消' })).toHaveFocus());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(await second!).toBe(false);
  });
});
