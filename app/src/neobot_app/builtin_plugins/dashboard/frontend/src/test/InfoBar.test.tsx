import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { closeInfoBarDetails, infoBar, notify } from '../notifications/infoBar';
import { InfoBarHost } from '../components/InfoBar';
import Modal from '../components/Modal';
import { MotionProvider } from '../components/ui/PageMotion';
import { mockReducedEffects } from './mediaPreference';

let preference: ReturnType<typeof mockReducedEffects>;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
  preference = mockReducedEffects(true);
});
afterEach(() => {
  preference.restore();
  vi.useRealTimers();
});

function mountHost() {
  return render(
    <div className="app">
      <MotionProvider>
        <InfoBarHost />
      </MotionProvider>
    </div>,
  );
}
async function publish(options: Parameters<typeof infoBar>[0]) {
  await act(async () => {
    infoBar(options);
  });
}
async function click(element: HTMLElement) {
  act(() => {
    element.focus();
    fireEvent.click(element);
  });
  await act(async () => {
    vi.advanceTimersByTime(0);
  });
}

describe('Global InfoBar', () => {
  it('通知宿主挂载到 body，脱离应用容器的堆叠上下文，并随宿主卸载', async () => {
    const { container, unmount } = mountHost();
    await publish({ title: '弹窗内操作失败', tone: 'err' });
    const host = screen.getByRole('status');
    expect(host.parentElement).toBe(document.body);
    expect(container.querySelector('.app')).not.toContainElement(host);
    expect(document.querySelectorAll('.info-bar-host')).toHaveLength(1);
    expect(within(host).getByRole('group', { name: '弹窗内操作失败' })).toBeInTheDocument();
    unmount();
    expect(document.querySelector('.info-bar-host')).toBeNull();
  });

  it('业务弹窗打开时可关闭通知和阅读详情，且不关闭业务弹窗或丢失草稿', async () => {
    vi.useRealTimers();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <div className="app">
        <MotionProvider>
          <InfoBarHost />
          <Modal open title="插件工作区" onClose={onClose}>
            <input aria-label="业务草稿" defaultValue="未保存链接" />
          </Modal>
        </MotionProvider>
      </div>,
    );
    await publish({ title: '第一次失败', tone: 'err' });
    await user.click(screen.getByRole('button', { name: '关闭通知' }));
    expect(screen.queryByRole('group', { name: '第一次失败' })).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    await publish({ title: '需要查看详情', message: '完整诊断结果', tone: 'err' });
    await user.click(screen.getByRole('button', { name: '查看详情' }));
    const details = screen.getByRole('dialog', { name: '通知详情' });
    expect(within(details).getByText('完整诊断结果')).toBeInTheDocument();
    await user.click(within(details).getByRole('button', { name: '关闭对话框' }));
    expect(screen.queryByRole('dialog', { name: '通知详情' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '插件工作区' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '业务草稿' })).toHaveValue('未保存链接');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('简单通知默认 4 秒时长，保留 polite 通知区和独立关闭按钮', async () => {
    mountHost();
    await act(async () => {
      notify('已保存', 'ok');
    });
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    const notice = screen.getByRole('group', { name: '已保存' });
    expect(notice).toHaveClass('ok');
    expect(notice).not.toHaveAttribute('role', 'button');
    expect(within(notice).getByRole('button', { name: '关闭通知' })).toBeEnabled();
    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(notice).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByRole('group', { name: '已保存' })).not.toBeInTheDocument();
  });

  it('同一时刻只显示最新一条；重复标题与级别不换节点、不重置相同通知的时长', async () => {
    mountHost();
    await publish({ title: '已读取', message: '第一份结果' });
    const first = screen.getByRole('group', { name: '已读取' });
    await publish({ title: '已读取', message: '更新后的结果' });
    expect(screen.getByRole('group', { name: '已读取' })).toBe(first);
    expect(screen.getByText('更新后的结果')).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    await publish({ title: '已读取', message: '更新后的结果' });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    await publish({ title: '上一条', duration: 0 });
    await publish({ title: '最新结果', tone: 'warn' });
    expect(screen.getAllByRole('group')).toHaveLength(1);
    expect(screen.queryByText('上一条')).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: '最新结果' })).toBeInTheDocument();
  });

  it('警告和错误默认保留到手动关闭，显式时长仍然有效', async () => {
    mountHost();
    await publish({ title: '需要重启', tone: 'warn' });
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(screen.getByRole('group', { name: '需要重启' })).toBeInTheDocument();
    await act(async () => {
      notify('保存失败', 'err');
    });
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    const error = screen.getByRole('group', { name: '保存失败' });
    const close = within(error).getByRole('button', { name: '关闭通知' });
    await click(close);
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    await publish({ title: '自定义时长', tone: 'warn', duration: 800 });
    act(() => {
      vi.advanceTimersByTime(799);
    });
    expect(screen.getByRole('group', { name: '自定义时长' })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('长正文可在详情完整阅读，并支持详情内操作关闭弹窗', async () => {
    mountHost();
    const fullText = '这是保留完整内容的配置结果。'.repeat(260) + '末尾错误路径：chat.models.primary';
    await publish({
      title: '配置保存结果',
      tone: 'warn',
      message: fullText,
      details: <button onClick={closeInfoBarDetails}>定位配置项</button>,
    });
    await click(screen.getByRole('button', { name: '查看详情' }));
    const dialog = within(screen.getByRole('dialog', { name: '通知详情' }));
    expect(dialog.getByText(fullText)).toHaveTextContent(fullText);
    await click(dialog.getByRole('button', { name: '定位配置项' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看详情' })).toHaveFocus();
    expect(screen.getByRole('group', { name: '配置保存结果' })).toBeInTheDocument();
  });

  it('旧 notify 的长文本变成简短标题和可展开全文', async () => {
    mountHost();
    const text = '后端返回的详细失败原因：'.repeat(20) + '不能丢失的结尾';
    await act(async () => {
      notify(text, 'err');
    });
    expect(screen.getByRole('group', { name: '操作失败' })).toBeInTheDocument();
    await click(screen.getByRole('button', { name: '查看详情' }));
    expect(within(screen.getByRole('dialog')).getByText(text)).toHaveTextContent(text);
  });

  it('悬停暂停计时，离开后继续剩余时长', async () => {
    mountHost();
    await publish({ title: '稍后关闭', duration: 1000 });
    act(() => {
      vi.advanceTimersByTime(250);
    });
    fireEvent.mouseEnter(screen.getByRole('status'));
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByRole('group', { name: '稍后关闭' })).toBeInTheDocument();
    fireEvent.mouseLeave(screen.getByRole('status'));
    act(() => {
      vi.advanceTimersByTime(749);
    });
    expect(screen.getByRole('group', { name: '稍后关闭' })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('详情阅读和键盘焦点暂停计时，关闭并移开焦点后恢复剩余时长', async () => {
    mountHost();
    await publish({ title: '可阅读结果', message: '完整结果内容', duration: 1000 });
    act(() => {
      vi.advanceTimersByTime(250);
    });
    await click(screen.getByRole('button', { name: '查看详情' }));
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await click(screen.getByRole('button', { name: '关闭对话框' }));
    const details = screen.getByRole('button', { name: '查看详情' });
    expect(details).toHaveFocus();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByRole('group', { name: '可阅读结果' })).toBeInTheDocument();
    act(() => {
      details.blur();
    });
    fireEvent.mouseLeave(screen.getByRole('status'));
    act(() => {
      vi.advanceTimersByTime(749);
    });
    expect(screen.getByRole('group', { name: '可阅读结果' })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('新提示不会替换正在阅读的详情，关掉详情后呈现最新通知', async () => {
    mountHost();
    await publish({ title: '第一项结果', message: '正在阅读的内容' });
    await click(screen.getByRole('button', { name: '查看详情' }));
    await publish({ title: '第二项结果', message: '最新内容', duration: 500 });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(within(screen.getByRole('dialog')).getByText('正在阅读的内容')).toBeInTheDocument();
    await click(screen.getByRole('button', { name: '关闭对话框' }));
    expect(screen.getByRole('group', { name: '第二项结果' })).toBeInTheDocument();
    expect(screen.queryByText('正在阅读的内容')).not.toBeInTheDocument();
  });

  it('替换、提前关闭和卸载都会清理对应定时器', async () => {
    const schedule = vi.spyOn(globalThis, 'setTimeout');
    const cancel = vi.spyOn(globalThis, 'clearTimeout');
    const { unmount } = mountHost();
    await publish({ title: '旧通知', duration: 12345 });
    const timerFor = (duration: number) =>
      schedule.mock.results[schedule.mock.calls.findIndex((call) => call[1] === duration)].value;
    const oldTimer = timerFor(12345);
    await publish({ title: '新通知', duration: 23456 });
    expect(cancel).toHaveBeenCalledWith(oldTimer);
    const dismissedTimer = timerFor(23456);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '关闭通知' }));
    });
    expect(cancel).toHaveBeenCalledWith(dismissedTimer);
    await publish({ title: '卸载通知', duration: 34567 });
    const finalTimer = timerFor(34567);
    unmount();
    expect(cancel).toHaveBeenCalledWith(finalTimer);
    schedule.mockRestore();
    cancel.mockRestore();
  });
});
