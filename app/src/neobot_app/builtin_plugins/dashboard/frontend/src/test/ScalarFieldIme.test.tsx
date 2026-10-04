// 回归（issue #67）：多行输入框在中文输入法（IME）下被「受控回写」打断
//
// 组字期间若把外部 value 回写到受控 textarea，正在拼的候选会被截断
// （表现为 wei'c 这类未上屏拼音残片）。这里锁住三条契约：
//   1. 组字中一律不向上提交；
//   2. compositionend 后恰好提交一次最终值；
//   3. 组字期间外部 value 变化不回灌，不覆盖正在编辑的文本。
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render } from '@testing-library/react';
import ScalarField from '../components/schema/ScalarField';
import type { FieldDescriptor } from '../api/types';

function descriptor(overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return {
    name: 'group_prompt_template',
    path: ['chat', 'group_prompt_template'],
    kind: 'scalar',
    type: 'str',
    value: '',
    default: '',
    ...overrides,
  } as FieldDescriptor;
}

// 必须超过 ScalarField 的长文本阈值（> 120 字符）才会渲染成多行 textarea
const LONG_TEXT =
  '这是一段足够长的配置文本，用来触发多行输入框；阈值是超过 120 个字符，'.repeat(4);

function renderField(value: string, onChange = vi.fn()) {
  const view = render(
    <ScalarField descriptor={descriptor({ value })} value={value} onChange={onChange} />,
  );
  const box = view.container.querySelector('textarea') as HTMLTextAreaElement;
  return { view, box, onChange };
}

describe('多行输入框的 IME 组字（issue #67）', () => {
  it('组字中的中间态不提交；结束后提交一次最终值', () => {
    const value = LONG_TEXT;
    expect(value.length).toBeGreaterThan(120);
    const { box, onChange } = renderField(value);
    expect(box.tagName).toBe('TEXTAREA');

    // 开始组字
    fireEvent.compositionStart(box);
    // 组字中途的拼音残片：只更新输入框，不得提交
    fireEvent.change(box, { target: { value: value + 'wei' } });
    expect(box.value).toBe(value + 'wei');
    expect(onChange).not.toHaveBeenCalled();

    // 候选上屏
    fireEvent.change(box, { target: { value: value + '为' } });
    expect(onChange).not.toHaveBeenCalled();

    // 组字结束：一次性提交
    fireEvent.compositionEnd(box, { data: '为' });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(value + '为');
  });

  it('组字期间外部 value 变化不回灌，不冲掉正在拼的字', () => {
    const value = 'x'.repeat(200);
    const { view, box, onChange } = renderField(value);

    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: value + 'wei' } });
    expect(box.value).toBe(value + 'wei');

    // 模拟外部回写（撤销 / 恢复默认 / 重新读取）——组字中必须忽略
    view.rerender(
      <ScalarField descriptor={descriptor({ value: '被外部改掉' })} value="被外部改掉" onChange={onChange} />,
    );
    expect(box.value).toBe(value + 'wei');

    fireEvent.compositionEnd(box, { data: '为' });
    expect(onChange).toHaveBeenCalledWith(value + 'wei');
  });

  it('非组字路径仍然实时提交（加了守卫不能让普通输入变懒）', () => {
    const { box, onChange } = renderField(LONG_TEXT);

    fireEvent.change(box, { target: { value: LONG_TEXT + 'ab' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(LONG_TEXT + 'ab');
  });

  it('组字结束后，外部值仍能正常回灌（撤销要好使）', () => {
    const { view, box, onChange } = renderField(LONG_TEXT);

    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: LONG_TEXT + 'we' } });
    fireEvent.compositionEnd(box, { data: '为' });
    expect(box.value).toBe(LONG_TEXT + 'we');

    // 外部回灌（撤销 / 恢复默认）。注意短文本会切回单行 input，
    // 所以 element 类型会变，这里按「实际渲染出来的输入控件」断言。
    act(() => {
      view.rerender(
        <ScalarField descriptor={descriptor({ value: '恢复后的值' })} value="恢复后的值" onChange={onChange} />,
      );
    });
    const control = view.container.querySelector('textarea, input') as HTMLTextAreaElement | HTMLInputElement;
    expect(control.value).toBe('恢复后的值');
  });
});
