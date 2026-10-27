import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Modal from '../components/Modal';
import { MotionProvider } from '../components/ui/PageMotion';
import { mockReducedEffects } from './mediaPreference';

let preference: ReturnType<typeof mockReducedEffects>;

function Example({ locked = false }: { locked?: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(locked);
  return (
    <>
      <button onClick={() => setOpen(true)}>打开配置</button>
      <Modal
        open={open}
        title="编辑配置"
        onClose={() => setOpen(false)}
        closeDisabled={busy}
        size="wide"
        className="custom-dialog"
        footer={<button onClick={() => setBusy(false)}>完成保存</button>}
      >
        <label htmlFor="dialog-value">配置值</label>
        <input id="dialog-value" data-autofocus defaultValue="原内容" />
      </Modal>
    </>
  );
}

beforeEach(() => {
  preference = mockReducedEffects();
});
afterEach(() => {
  preference.restore();
});

describe('Modal motion integration', () => {
  it('保留自动焦点、页脚与立即关闭，且不覆盖弹窗的 CSS 居中 transform', async () => {
    const user = userEvent.setup();
    render(
      <MotionProvider>
        <Example />
      </MotionProvider>,
    );
    const trigger = screen.getByRole('button', { name: '打开配置' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '编辑配置' });
    expect(dialog).toBeVisible();
    expect(dialog).toHaveClass('modal-wide', 'custom-dialog');
    expect(dialog.style.transform).toBe('');
    expect(screen.getByRole('textbox', { name: '配置值' })).toHaveFocus();
    await waitFor(
      () =>
        expect(screen.getByRole('textbox', { name: '配置值' }).parentElement).toHaveStyle({
          transform: 'none',
        }),
      { timeout: 600 },
    );
    expect(screen.getByRole('button', { name: '完成保存' })).toBeEnabled();
    await user.tab();
    expect(screen.getByRole('button', { name: '完成保存' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: '关闭对话框' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: '关闭对话框' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('保存过程中保留关闭保护，解锁后 Escape 能立即关闭', async () => {
    const user = userEvent.setup();
    render(
      <MotionProvider>
        <Example locked />
      </MotionProvider>,
    );
    await user.click(screen.getByRole('button', { name: '打开配置' }));
    expect(screen.getByRole('button', { name: '关闭对话框' })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '完成保存' }));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('外部关闭不会让旧的可写表单等待退出动画', () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <MotionProvider>
        <Modal open title="编辑旧记录" onClose={onClose}>
          <textarea aria-label="旧记录" />
        </Modal>
      </MotionProvider>,
    );
    expect(screen.getByRole('textbox', { name: '旧记录' })).toBeInTheDocument();
    rerender(
      <MotionProvider>
        <Modal open={false} title="编辑旧记录" onClose={onClose}>
          <textarea aria-label="旧记录" />
        </Modal>
      </MotionProvider>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('减少动态效果时内容一开始就在最终位置，并保持自动焦点', async () => {
    preference.set(true);
    const user = userEvent.setup();
    render(
      <MotionProvider>
        <Example />
      </MotionProvider>,
    );
    await user.click(screen.getByRole('button', { name: '打开配置' }));
    const field = screen.getByRole('textbox', { name: '配置值' });
    expect(field).toHaveFocus();
    expect(field.parentElement).toHaveStyle({ transform: 'none' });
    expect(screen.getByRole('dialog')).toHaveStyle({ opacity: '1' });
  });

  it('运行中减少动态效果会在下一帧结束位移，保留输入和焦点', async () => {
    render(
      <MotionProvider>
        <Modal open title="动态偏好" onClose={() => {}}>
          <input aria-label="偏好切换草稿" data-autofocus />
        </Modal>
      </MotionProvider>,
    );
    const field = screen.getByRole('textbox', { name: '偏好切换草稿' });
    fireEvent.change(field, { target: { value: '未保存草稿' } });
    expect(field.parentElement?.style.transform).not.toBe('none');
    act(() => {
      preference.set(true);
    });
    await act(async () => {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    });
    expect(field.parentElement).toHaveStyle({ transform: 'none' });
    expect(screen.getByRole('dialog')).toHaveStyle({ opacity: '1' });
    expect(field).toHaveValue('未保存草稿');
    expect(field).toHaveFocus();
  });
});
