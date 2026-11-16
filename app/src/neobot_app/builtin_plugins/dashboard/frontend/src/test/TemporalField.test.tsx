// 单元测试：TemporalField —— 日期 / 时间 / 日期时间设置项的 ISO 8601 契约
//
// 锁三件事：
//   1. 后端值（可能是空格分隔、带毫秒或时区偏移的 ISO）能被喂进原生控件；
//   2. 控件回传的值一定是规范 ISO 8601（date / time / datetime 各自的形态）；
//   3. 清空时可选字段给 null（= 不设置），必填字段给空串（交给后端字段级校验）。
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import TemporalField, {
  temporalMode,
  toInputValue,
  toSubmitValue,
} from '../components/schema/TemporalField';
import type { FieldDescriptor } from '../api/types';

function temporalDescriptor(
  kind: 'date' | 'time' | 'datetime',
  value: unknown,
  overrides: Partial<FieldDescriptor> = {},
): FieldDescriptor {
  return {
    name: 'run_at',
    label: '执行时间',
    path: ['task', 'run_at'],
    kind,
    type: kind,
    value,
    ...overrides,
  };
}

function renderField(
  kind: 'date' | 'time' | 'datetime',
  value: unknown,
  overrides: Partial<FieldDescriptor> = {},
) {
  const onChange = vi.fn();
  const descriptor = temporalDescriptor(kind, value, overrides);
  const view = render(<TemporalField descriptor={descriptor} value={value} onChange={onChange} />);
  return { ...view, onChange, descriptor };
}

describe('temporalMode：kind → 控件形态', () => {
  it('三个 kind 各自映射', () => {
    expect(temporalMode('date')).toBe('date');
    expect(temporalMode('time')).toBe('time');
    expect(temporalMode('datetime')).toBe('datetime');
  });

  it('未知 kind 退回日期时间', () => {
    expect(temporalMode(undefined)).toBe('datetime');
    expect(temporalMode('scalar')).toBe('datetime');
  });
});

describe('toInputValue：后端值 → 控件值', () => {
  it('ISO 原样进入控件', () => {
    expect(toInputValue('2026-11-16T23:39:55', 'datetime')).toBe('2026-11-16T23:39:55');
    expect(toInputValue('2026-11-16', 'date')).toBe('2026-11-16');
    expect(toInputValue('23:39:55', 'time')).toBe('23:39:55');
  });

  it('接受空格分隔、毫秒与时区偏移（只取墙钟部分）', () => {
    expect(toInputValue('2026-11-16 23:39:55', 'datetime')).toBe('2026-11-16T23:39:55');
    expect(toInputValue('2026-11-16T23:39:55.123456+08:00', 'datetime')).toBe('2026-11-16T23:39:55');
    expect(toInputValue('2026-11-16T23:39', 'datetime')).toBe('2026-11-16T23:39:00');
  });

  it('空值与脏值都回空串（不把无法解析的内容塞给控件）', () => {
    expect(toInputValue(null, 'datetime')).toBe('');
    expect(toInputValue(undefined, 'date')).toBe('');
    expect(toInputValue('   ', 'time')).toBe('');
    expect(toInputValue('不是时间', 'datetime')).toBe('');
  });

  it('日期模式下忽略时间部分', () => {
    expect(toInputValue('2026-11-16T23:39:55', 'date')).toBe('2026-11-16');
  });
});

describe('toSubmitValue：控件值 → ISO 8601', () => {
  it('缺秒补 :00', () => {
    expect(toSubmitValue('2026-11-16T23:39', 'datetime', true)).toBe('2026-11-16T23:39:00');
    expect(toSubmitValue('23:39', 'time', true)).toBe('23:39:00');
  });

  it('已带秒的值原样提交', () => {
    expect(toSubmitValue('2026-11-16T23:39:55', 'datetime', true)).toBe('2026-11-16T23:39:55');
    expect(toSubmitValue('2026-11-16', 'date', true)).toBe('2026-11-16');
  });

  it('清空：可选给 null，必填给空串', () => {
    expect(toSubmitValue('', 'datetime', false)).toBeNull();
    expect(toSubmitValue('', 'datetime', true)).toBe('');
  });
});

describe('TemporalField：渲染与提交', () => {
  it.each([
    ['date', 'date'],
    ['time', 'time'],
    ['datetime', 'datetime-local'],
  ] as const)('kind=%s 渲染原生 %s 控件', (kind, inputType) => {
    renderField(kind, kind === 'date' ? '2026-11-16' : '2026-11-16T23:39:55');
    expect(screen.getByLabelText('执行时间')).toHaveAttribute('type', inputType);
  });

  it('读入值回显在控件上', () => {
    renderField('datetime', '2026-11-16T23:39:55');
    // jsdom 会把 datetime-local 的值补成带毫秒的形态，真实浏览器不带；
    // 这里比对「去掉毫秒」的墙钟部分，避免把 jsdom 的实现细节写进断言。
    const input = screen.getByLabelText('执行时间') as HTMLInputElement;
    expect(input.value.replace(/\.000$/, '')).toBe('2026-11-16T23:39:55');
  });

  it('改动后提交的是 ISO 8601 字符串', () => {
    const { onChange } = renderField('datetime', '');
    fireEvent.change(screen.getByLabelText('执行时间'), {
      target: { value: '2026-11-16T23:39' },
    });
    expect(onChange).toHaveBeenCalledWith('2026-11-16T23:39:00');
  });

  it('可选字段清空后提交 null', () => {
    const { onChange } = renderField('date', '2026-11-16', { required: false });
    fireEvent.change(screen.getByLabelText('执行时间'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('必填字段清空后提交空串（由后端给出字段级错误）', () => {
    const { onChange } = renderField('date', '2026-11-16', { required: true });
    fireEvent.change(screen.getByLabelText('执行时间'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('禁用或只读时不提交改动', () => {
    const disabled = renderField('date', '2026-11-16', {});
    fireEvent.change(screen.getByLabelText('执行时间'), { target: { value: '2027-01-01' } });
    expect(disabled.onChange).toHaveBeenCalled();
    disabled.unmount();

    const readonly = renderField('date', '2026-11-16', { readonly: true });
    expect(screen.getByLabelText('执行时间')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('执行时间'), { target: { value: '2027-01-01' } });
    expect(readonly.onChange).not.toHaveBeenCalled();
  });
});
