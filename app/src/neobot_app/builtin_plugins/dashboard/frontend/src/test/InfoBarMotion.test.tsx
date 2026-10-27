import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { notify } from '../notifications/infoBar';
import { InfoBarHost } from '../components/InfoBar';
import { MotionProvider } from '../components/ui/PageMotion';
import { mockReducedEffects } from './mediaPreference';

let preference: ReturnType<typeof mockReducedEffects>;
beforeEach(() => {
  preference = mockReducedEffects();
});
afterEach(() => {
  preference.restore();
});

// 独立使用真实 rAF，避免定时器合约测试的假时钟影响动画调度器。
describe('InfoBarHost live motion preferences', () => {
  it('减少动态效果时不从位移位置入场，仍可正常关闭', async () => {
    preference.set(true);
    render(
      <MotionProvider>
        <InfoBarHost />
      </MotionProvider>,
    );
    act(() => {
      notify('静态提示', 'info', 0);
    });
    const message = screen.getByRole('group', { name: '静态提示' });
    expect(message).toHaveStyle({ transform: 'none', opacity: '1' });
    await act(async () => {
      fireEvent.click(within(message).getByRole('button', { name: '关闭通知' }));
    });
    expect(screen.queryByRole('group', { name: '静态提示' })).not.toBeInTheDocument();
  });

  it('运行中减少动态效果会在下一帧取消当前位移，新提示直接呈现', async () => {
    render(
      <MotionProvider>
        <InfoBarHost />
      </MotionProvider>,
    );
    act(() => {
      notify('正在入场', 'info', 0);
    });
    const message = screen.getByRole('group', { name: '正在入场' });
    expect(message.style.transform).not.toBe('none');
    act(() => {
      preference.set(true);
    });
    await act(async () => {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    });
    expect(message).toHaveStyle({ transform: 'none', opacity: '1' });
    await act(async () => {
      notify('随后提示', 'info', 0);
    });
    const latest = screen.getByRole('group', { name: '随后提示' });
    expect(latest).toHaveStyle({ transform: 'none', opacity: '1' });
    expect(screen.queryByRole('group', { name: '正在入场' })).not.toBeInTheDocument();
    act(() => {
      preference.set(false);
    });
    fireEvent.click(within(latest).getByRole('button', { name: '关闭通知' }));
    expect(screen.queryByRole('group', { name: '随后提示' })).not.toBeInTheDocument();
    expect(within(latest).getByRole('button', { name: '关闭通知', hidden: true })).toBeDisabled();
    await waitFor(() => expect(screen.queryByText('随后提示')).not.toBeInTheDocument(), { timeout: 600 });
  });
});
