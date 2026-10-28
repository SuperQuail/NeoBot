// 模型库「推理强度」顶层字段：strict 下拉按 option_groups 分组、优先中文选项名；
// 没有分组信息的旧字段仍按扁平 options 渲染（不能因新字段改坏已有单选）。
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ScalarField from '../components/schema/ScalarField';
import { ConfigTreePanel } from '../pages/config/ConfigTreePanel';
import type { FieldDescriptor } from '../api/types';

const OPENAI_OPTIONS = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
const CLAUDE_OPTIONS = ['claude:low', 'claude:medium', 'claude:high', 'claude:xhigh', 'claude:max'];
const EFFORT_LABELS: Record<string, string> = {
  '': '不设置（沿用供应商默认）',
  high: 'high（高）',
  'claude:high': 'Claude 系 · high（高）',
  'claude:max': 'Claude 系 · max（最高）',
};

function reasoningEffortField(value = ''): FieldDescriptor {
  return {
    name: 'reasoning_effort',
    path: ['reasoning_effort'],
    kind: 'scalar',
    type: 'str',
    value,
    default: '',
    options: ['', ...OPENAI_OPTIONS, ...CLAUDE_OPTIONS],
    options_strict: true,
    option_labels: EFFORT_LABELS,
    option_groups: [
      { label: 'OpenAI 系（reasoning_effort）', options: OPENAI_OPTIONS },
      { label: 'Claude 系（output_config.effort）', options: CLAUDE_OPTIONS },
    ],
  };
}

function selectOf(container: HTMLElement): HTMLSelectElement {
  return container.querySelector('select') as HTMLSelectElement;
}

describe('推理强度 strict 下拉', () => {
  it('按 option_groups 渲染 optgroup，空值留在分组外，Claude 档位带系列标注', () => {
    const { container } = render(
      <ScalarField descriptor={reasoningEffortField()} value="" onChange={vi.fn()} />,
    );
    const select = selectOf(container);
    expect(
      Array.from(select.querySelectorAll('optgroup')).map((group) => group.getAttribute('label')),
    ).toEqual(['OpenAI 系（reasoning_effort）', 'Claude 系（output_config.effort）']);

    // 「不设置」不属于任何分组：排第一位，且不在 optgroup 里
    const blank = select.options[0];
    expect(blank.value).toBe('');
    expect(blank.textContent).toBe('不设置（沿用供应商默认）');
    expect(blank.closest('optgroup')).toBeNull();

    const claudeMax = Array.from(select.options).find((option) => option.value === 'claude:max');
    expect(claudeMax?.textContent).toBe('Claude 系 · max（最高）');
    expect(claudeMax?.closest('optgroup')?.getAttribute('label')).toBe('Claude 系（output_config.effort）');

    // 没有中文名的值直接显示原始值，选项不能丢
    const claudeLow = Array.from(select.options).find((option) => option.value === 'claude:low');
    expect(claudeLow?.textContent).toBe('claude:low');
  });

  it('选择 Claude 档位后回传带前缀的原始值', () => {
    const onChange = vi.fn();
    const { container } = render(
      <ScalarField descriptor={reasoningEffortField('high')} value="high" onChange={onChange} />,
    );
    fireEvent.change(selectOf(container), { target: { value: 'claude:high' } });
    expect(onChange).toHaveBeenCalledWith('claude:high');
  });

  it('模型表单把顶层字段放进「（顶层）」分区，改动回传顶层路径', () => {
    const onChange = vi.fn();
    render(
      <ConfigTreePanel
        schema={[reasoningEffortField()]}
        draft={{ reasoning_effort: '' }}
        history={{}}
        collapse={{}}
        filter=""
        onFilterChange={vi.fn()}
        onChange={onChange}
        onToggleCollapse={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByRole('combobox', { name: 'reasoning_effort' }), {
      target: { value: 'claude:max' },
    });
    expect(onChange).toHaveBeenCalledWith([], { reasoning_effort: 'claude:max' });
  });
});

describe('没有分组信息的旧 strict 字段', () => {
  it('仍按扁平 options 渲染，option_labels 生效但不产生 optgroup', () => {
    const legacy: FieldDescriptor = {
      name: 'level',
      path: ['logging', 'level'],
      kind: 'scalar',
      type: 'str',
      value: 'INFO',
      default: 'INFO',
      options: ['DEBUG', 'INFO'],
      options_strict: true,
      option_labels: { INFO: '信息' },
    };
    const { container } = render(<ScalarField descriptor={legacy} value="INFO" onChange={vi.fn()} />);
    const select = selectOf(container);
    expect(select.querySelectorAll('optgroup')).toHaveLength(0);
    expect(Array.from(select.options).map((option) => [option.value, option.textContent])).toEqual([
      ['DEBUG', 'DEBUG'],
      ['INFO', '信息'],
    ]);
  });
});

describe('脏配置的容错', () => {
  it('手写大小写/空白的旧值仍匹配到对应选项，不显示成「不设置」', () => {
    const { container } = render(
      <ScalarField descriptor={reasoningEffortField()} value=" CLAUDE:MAX " onChange={vi.fn()} />,
    );
    expect(selectOf(container).value).toBe('claude:max');
  });

  it('option_groups 是脏数据时退回扁平下拉，不抛错', () => {
    const dirty = {
      ...reasoningEffortField(),
      option_groups: 'nope' as unknown as FieldDescriptor['option_groups'],
    };
    const { container } = render(<ScalarField descriptor={dirty} value="high" onChange={vi.fn()} />);
    expect(selectOf(container).querySelectorAll('optgroup')).toHaveLength(0);
    expect(selectOf(container).value).toBe('high');
  });
});
