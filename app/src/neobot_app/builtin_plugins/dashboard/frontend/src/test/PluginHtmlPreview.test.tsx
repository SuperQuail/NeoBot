import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PluginHtmlPreview from '../pages/plugins/PluginHtmlPreview';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function previewLayout(initialWidth: number) {
  let width = initialWidth;
  const observers: Array<{ callback: ResizeObserverCallback; active: boolean; targets: Set<Element> }> = [];
  // jsdom 不执行布局，仅补上容器实测宽度和尺寸变化通知。
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('plugin-preview-canvas') ? width : 0;
  });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      private observer: (typeof observers)[number];
      constructor(callback: ResizeObserverCallback) {
        this.observer = { callback, active: true, targets: new Set() };
        observers.push(this.observer);
      }
      observe(target: Element) {
        this.observer.targets.add(target);
      }
      disconnect() {
        this.observer.active = false;
      }
    },
  );
  return {
    resize(next: number) {
      width = next;
      act(() =>
        observers
          .filter((observer) => observer.active)
          .forEach((observer) =>
            observer.callback(
              [...observer.targets].map(
                (target) => ({ target, contentRect: new DOMRect(0, 0, width, 0) }) as ResizeObserverEntry,
              ),
              {} as ResizeObserver,
            ),
          ),
      );
    },
    activeObservers: () => observers.filter((observer) => observer.active).length,
  };
}

function paintedSize(frame: HTMLIFrameElement) {
  const scale = Number(/scale\(([^)]+)\)/.exec(frame.style.transform)?.[1] ?? '1');
  return {
    width: parseFloat(frame.style.width) * scale,
    height: parseFloat(frame.style.height) * scale,
    scale,
  };
}

describe('隔离 HTML 预览', () => {
  it('窄容器能看完整预览，查看原图后可以返回适应窗口，尺寸变化不重新创建文档', async () => {
    const layout = previewLayout(360);
    const user = userEvent.setup();
    render(<PluginHtmlPreview title="通知卡片" html="<p>合成卡片内容</p>" width={960} height={600} />);
    const frame = screen.getByTitle<HTMLIFrameElement>('通知卡片');
    expect(paintedSize(frame).width).toBeLessThanOrEqual(360);
    expect(paintedSize(frame).scale).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: '查看原始大小' }));
    expect(paintedSize(frame).width).toBe(960);
    layout.resize(280);
    await user.click(screen.getByRole('button', { name: '适应窗口' }));
    expect(paintedSize(frame).width).toBeLessThanOrEqual(280);
    expect(screen.getByTitle('通知卡片')).toBe(frame);
    expect(frame).toHaveAttribute('srcdoc', expect.stringContaining('合成卡片内容'));
  });

  it('原图切换、缩放和新内容不会扩大 iframe 权限或暴露宿主来源', async () => {
    const layout = previewLayout(420);
    const user = userEvent.setup();
    const rendered = render(<PluginHtmlPreview title="通知卡片" html="<p>第一张卡片</p>" />);
    await user.click(screen.getByRole('button', { name: '查看原始大小' }));
    layout.resize(280);
    rendered.rerender(
      <PluginHtmlPreview title="通知卡片" html="<p>第二张卡片</p>" width={800} height={500} />,
    );
    const frame = screen.getByTitle('通知卡片');
    expect(frame).toHaveAttribute('sandbox', '');
    expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer');
    const source = frame.getAttribute('srcdoc')!;
    expect(source).toContain("default-src 'none'");
    expect(source).not.toContain('allow-scripts');
    expect(source).toContain('第二张卡片');
  });

  it('明确声明短文档时不沿用默认长画布，特殊尺寸也保持有限且可适应的绘制范围', () => {
    previewLayout(600);
    const rendered = render(
      <PluginHtmlPreview title="通知卡片" html="<p>一行通知</p>" width={480} height={140} />,
    );
    const frame = screen.getByTitle<HTMLIFrameElement>('通知卡片');
    expect(paintedSize(frame).height).toBeLessThanOrEqual(140);
    expect(paintedSize(frame).width).toBeLessThanOrEqual(600);
    rendered.rerender(
      <PluginHtmlPreview title="通知卡片" html="<p>一行通知</p>" width={Number.NaN} height={0} />,
    );
    const size = paintedSize(frame);
    expect(Number.isFinite(size.width)).toBe(true);
    expect(Number.isFinite(size.height)).toBe(true);
    expect(size.scale).toBeGreaterThan(0);
    expect(size.width).toBeLessThanOrEqual(600);
  });

  it('文字内容可折叠，缩放保留隔离文档，卸载后释放尺寸观察', async () => {
    const layout = previewLayout(420);
    const user = userEvent.setup();
    const rendered = render(
      <PluginHtmlPreview title="通知卡片" html="<p>合成卡片内容</p>" fallbackText="合成通知文字" />,
    );
    const frame = screen.getByTitle('通知卡片');
    await user.click(screen.getByRole('button', { name: '查看原始大小' }));
    layout.resize(280);
    await user.click(screen.getByRole('button', { name: '适应窗口' }));
    expect(screen.getByTitle('通知卡片')).toBe(frame);
    expect(screen.getByRole('button', { name: '查看文字内容' })).toHaveAttribute('aria-expanded', 'false');
    await user.click(screen.getByRole('button', { name: '查看文字内容' }));
    expect(screen.getByRole('button', { name: '收起文字内容' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('合成通知文字')).toBeVisible();
    await user.click(screen.getByRole('button', { name: '收起文字内容' }));
    expect(screen.queryByText('合成通知文字')).not.toBeInTheDocument();
    expect(layout.activeObservers()).toBeGreaterThan(0);
    rendered.unmount();
    expect(layout.activeObservers()).toBe(0);
  });
});
