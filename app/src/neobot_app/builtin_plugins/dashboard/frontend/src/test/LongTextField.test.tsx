// 单元测试：LongTextField —— 长文本控件的行为契约
//
// 替换动机：旧实现按 text.length > 120 在 <input> 与 <textarea> 之间切换，
// 打字到第 121 个字符就换掉 DOM 节点，焦点与光标全丢。所以第一组用例锁
// 「短值/长值永远是同一个 textarea」，其余锁单行 Enter 拦截、IME 组字、
// 外部回灌、行数/字符数指示、放大编辑、disabled。
//
// 注意：jsdom 的 scrollHeight 恒为 0，自动增高不在单测范围内（已用真实浏览器验证）。
import { describe, expect, it, vi } from 'vitest';
import { createEvent, fireEvent, render, screen, within } from '@testing-library/react';
import LongTextField, { type LongTextFieldProps } from '../components/schema/LongTextField';

function renderField(overrides: Partial<LongTextFieldProps> = {}) {
  const onChange = vi.fn();
  const props: LongTextFieldProps = { value: '', onChange, ...overrides };
  const view = render(<LongTextField {...props} />);
  const box = screen.getByRole('textbox') as HTMLTextAreaElement;
  return Object.assign(view, { onChange, props, box });
}

describe('类型稳定：短值/长值都是同一个 textarea', () => {
  it('短值渲染 textarea，且不出现 input', () => {
    const { container, box } = renderField({ value: '0.0.0.0' });

    expect(box.tagName).toBe('TEXTAREA');
    expect(container.querySelector('input')).toBeNull();
  });

  it('300 字符的长值同样渲染 textarea', () => {
    const { container, box } = renderField({ value: 'x'.repeat(300) });

    expect(box.tagName).toBe('TEXTAREA');
    expect(container.querySelector('input')).toBeNull();
    expect(box.value).toBe('x'.repeat(300));
  });

  it('从短值改到 121+ 字符时 DOM 节点不换（不会丢焦点）', () => {
    const { rerender, props, box } = renderField({ value: '0.0.0.0' });

    rerender(<LongTextField {...props} value={'y'.repeat(121)} />);

    expect(screen.getByRole('textbox')).toBe(box);
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('y'.repeat(121));
  });
});

describe('单行/多行意图：Enter 是否拦截', () => {
  it('minRows=1 且内容无换行：Enter 被 preventDefault，也不产生提交', () => {
    const { onChange, box } = renderField({ value: '0.0.0.0' });

    expect(fireEvent.keyDown(box, { key: 'Enter' })).toBe(false);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('minRows=1 但内容已有换行：放行 Enter', () => {
    const { box } = renderField({ value: '第一行\n第二行' });

    expect(fireEvent.keyDown(box, { key: 'Enter' })).toBe(true);
  });

  it('minRows>1：放行 Enter', () => {
    const { box } = renderField({ value: '0.0.0.0', minRows: 3 });

    expect(fireEvent.keyDown(box, { key: 'Enter' })).toBe(true);
  });
});

describe('IME 组字：期间不提交，结束一次性提交', () => {
  it('组字中途的 change 不触发 onChange（本地文本照常更新）', () => {
    const { onChange, box } = renderField({ value: '你好' });

    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: '你好wei' } });

    expect(box.value).toBe('你好wei');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('compositionEnd 时恰好提交一次最终值', () => {
    const { onChange, box } = renderField({ value: '你好' });

    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: '你好为' } });
    fireEvent.compositionEnd(box, { data: '为' });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('你好为');
  });

  it('没有 compositionStart、但 nativeEvent.isComposing=true 的 change 也不提交', () => {
    const { onChange, box } = renderField({ value: '你好' });

    // fireEvent.change 的 init 里给 isComposing 不会落到事件对象上（jsdom 忽略未知 init 键），
    // 这里先造事件再补 isComposing，模拟未收到 compositionStart 的浏览器。
    const composingEvent = createEvent.change(box, { target: { value: '你好w' } });
    Object.defineProperty(composingEvent, 'isComposing', { value: true });
    fireEvent(box, composingEvent);
    expect(onChange).not.toHaveBeenCalled();

    // 对照组：同一条派发路径，不带 isComposing 时必须照常提交，证明上面的“没提交”不是路径失效
    const plainEvent = createEvent.change(box, { target: { value: '你好wa' } });
    fireEvent(box, plainEvent);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('你好wa');
  });
});

describe('外部值回灌', () => {
  it('syncExternal 默认开启：外部 value 变化后 textarea 跟随', () => {
    const { rerender, props, box } = renderField({ value: '旧值' });

    rerender(<LongTextField {...props} value="外部新值" />);

    expect(box.value).toBe('外部新值');
  });

  it('syncExternal=false：外部 value 变化不回灌', () => {
    const { rerender, props, box } = renderField({ value: '本地值', syncExternal: false });

    rerender(<LongTextField {...props} value="外部改掉" />);

    expect(box.value).toBe('本地值');
  });
});

describe('行数/字符数指示', () => {
  it('showCount 默认显示「N 行 · M 字符」', () => {
    renderField({ value: 'ab\ncd' });

    expect(screen.getByText('2 行 · 5 字符')).toBeInTheDocument();
  });

  it('showCount=false 不渲染计数', () => {
    renderField({ value: 'ab\ncd', showCount: false });

    expect(screen.queryByText(/字符/)).not.toBeInTheDocument();
  });
});

describe('放大编辑', () => {
  it('点「放大」打开对话框，内容与当前编辑值一致', () => {
    const { onChange, box } = renderField({ value: '初始提示词', ariaLabel: '系统提示词' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.change(box, { target: { value: '改过的提示词' } });
    expect(onChange).toHaveBeenCalledWith('改过的提示词');

    fireEvent.click(screen.getByRole('button', { name: /放大/ }));

    const dialog = screen.getByRole('dialog');
    const modalBox = within(dialog).getByLabelText('系统提示词（放大）') as HTMLTextAreaElement;
    expect(modalBox.value).toBe('改过的提示词');
    expect(within(dialog).getByText('编辑 系统提示词')).toBeInTheDocument();
  });

  it('点「完成」关闭对话框', () => {
    renderField({ value: '0.0.0.0', ariaLabel: '系统提示词' });

    fireEvent.click(screen.getByRole('button', { name: /放大/ }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '完成' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('disabled', () => {
  it('textarea 与「放大」按钮都禁用', () => {
    renderField({ value: '0.0.0.0', disabled: true });

    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.getByRole('button', { name: /放大/ })).toBeDisabled();
  });

  it('禁用时点「放大」不会打开对话框', () => {
    renderField({ value: '0.0.0.0', disabled: true });

    fireEvent.click(screen.getByRole('button', { name: /放大/ }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
