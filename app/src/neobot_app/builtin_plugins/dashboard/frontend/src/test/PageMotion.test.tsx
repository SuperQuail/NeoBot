import { useEffect, useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PageMotion, { MotionProvider } from '../components/ui/PageMotion';
import { mockReducedEffects } from './mediaPreference';

afterEach(() => vi.restoreAllMocks());

function mediaPreference(reduced: boolean) {
  return mockReducedEffects(reduced).set;
}

describe('页面动效与编辑状态', () => {
  it('减少动态效果时，页面和后续挂载的内容直接呈现', async () => {
    mediaPreference(true);
    const view = (extra: boolean) => (
      <MotionProvider>
        <PageMotion>
          <div className="page">
            <section className="card">原有内容</section>
            {extra && <section className="card">新增内容</section>}
          </div>
        </PageMotion>
      </MotionProvider>
    );
    const { rerender } = render(view(false));
    rerender(view(true));
    await act(async () => {
      await Promise.resolve();
    });
    for (const text of ['原有内容', '新增内容']) {
      const card = screen.getByText(text);
      expect(card).toBeVisible();
      expect(card.style.opacity).toBe('');
      expect(card.style.transform).toBe('');
    }
  });

  it('异步组件入场不重建现有编辑器、不清空输入或移动焦点', async () => {
    mediaPreference(false);
    const mounted = vi.fn();
    function Editor() {
      const [draft, setDraft] = useState('');
      useEffect(() => {
        mounted();
      }, []);
      return (
        <section className="card">
          <input aria-label="配置草稿" value={draft} onChange={(event) => setDraft(event.target.value)} />
        </section>
      );
    }
    const view = (extra: boolean) => (
      <MotionProvider>
        <PageMotion>
          <div className="page">
            <Editor />
            {extra && <section className="card">异步读取结果</section>}
          </div>
        </PageMotion>
      </MotionProvider>
    );
    const { rerender } = render(view(false));
    const input = screen.getByRole('textbox', { name: '配置草稿' });
    input.focus();
    fireEvent.change(input, { target: { value: '未保存的配置' } });
    rerender(view(true));
    await act(async () => {
      await Promise.resolve();
    });
    expect(input).toHaveValue('未保存的配置');
    expect(input).toHaveFocus();
    expect(mounted).toHaveBeenCalledTimes(1);
    expect(screen.getByText('异步读取结果')).toBeVisible();
  });

  it('页面打开后开启减少动态效果会停止过渡，后续卡片直接出现', async () => {
    const setReduced = mediaPreference(false);
    const view = (extra: boolean) => (
      <MotionProvider>
        <PageMotion>
          <div className="page">
            <section className="card">当前卡片</section>
            {extra && <section className="card">之后读取的卡片</section>}
          </div>
        </PageMotion>
      </MotionProvider>
    );
    const { container, rerender } = render(view(false));
    act(() => setReduced(true));
    rerender(view(true));
    await act(async () => {
      await Promise.resolve();
    });
    const elements = [
      container.querySelector<HTMLElement>('.route-stage')!,
      screen.getByText('当前卡片'),
      screen.getByText('之后读取的卡片'),
    ];
    for (const element of elements) {
      expect(element).toBeVisible();
      expect(element.style.opacity).toBe('');
      expect(element.style.transform || 'none').toBe('none');
    }
  });
});
