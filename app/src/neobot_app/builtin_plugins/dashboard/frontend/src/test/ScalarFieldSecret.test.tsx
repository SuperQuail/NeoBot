// 回归：密钥判定只看字符串字段；后端掩码残留的空串回落到类型默认值
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import ScalarField from '../components/schema/ScalarField';
import { defaultsFromFields } from '../components/schema/fieldTypes';
import type { FieldDescriptor } from '../api/types';

function descriptor(overrides: Partial<FieldDescriptor> = {}): FieldDescriptor {
  return {
    name: 'api_key',
    path: ['llm', 'api_key'],
    kind: 'scalar',
    type: 'str',
    value: '',
    default: '',
    ...overrides,
  } as FieldDescriptor;
}

function field(name: string, type: string, fallback: unknown): FieldDescriptor {
  return { name, path: [name], kind: 'scalar', type, default: fallback } as FieldDescriptor;
}

describe('ScalarField 的密钥判定', () => {
  it('名字含 token 的数值字段仍是数字框，没有显示/隐藏按钮', () => {
    const { container, queryByRole } = render(
      <ScalarField
        descriptor={descriptor({
          name: 'max_output_tokens',
          path: ['llm', 'max_output_tokens'],
          type: 'int',
          value: 2048,
        })}
        value={2048}
        onChange={vi.fn()}
      />,
    );
    expect(container.querySelector('input[type="number"]')).not.toBeNull();
    expect(queryByRole('button', { name: '显示' })).toBeNull();
    expect(queryByRole('button', { name: '隐藏' })).toBeNull();
  });

  it('字符串密钥字段仍是密码框 + 「显示」按钮', () => {
    const { container, getByRole } = render(
      <ScalarField descriptor={descriptor()} value="" onChange={vi.fn()} />,
    );
    expect(container.querySelector('input[type="password"]')).not.toBeNull();
    expect(getByRole('button', { name: '显示' })).toBeTruthy();
  });
});

describe('defaultsFromFields 的掩码残留兜底', () => {
  it('int/float 空串回落 0，bool 回落 false，str 保持空串', () => {
    const fields = [
      field('i', 'int', ''),
      field('f', 'float', ''),
      field('b', 'bool', ''),
      field('s', 'str', ''),
    ];
    expect(defaultsFromFields(fields)).toEqual({ i: 0, f: 0, b: false, s: '' });
  });

  it('已有的默认值不受影响', () => {
    const fields = [field('i', 'int', 7), field('b', 'bool', true), field('s', 'str', 'x')];
    expect(defaultsFromFields(fields)).toEqual({ i: 7, b: true, s: 'x' });
  });
});
