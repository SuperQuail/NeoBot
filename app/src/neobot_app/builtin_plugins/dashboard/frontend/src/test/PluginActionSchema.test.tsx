import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { JsonSchema } from '../api/types';
import ScalarField from '../components/schema/ScalarField';
import {
  actionFields,
  actionFieldValue,
  initialActionInput,
  initialActionValues,
} from '../pages/plugins/pluginActionSchema';

it('区分大小写的字符串枚举保留精确值，说明书仍能正确展示枚举', () => {
  const schema = { type: 'object', properties: { mode: { type: 'string', enum: ['A', 'a'] } } };
  expect(actionFields(schema, { mode: 'a' })?.[0].options).toEqual(['', 'A', 'a']);
  expect(actionFieldValue(schema, 'mode', 'a')).toBe('a');
});

it('原配置字段没有精确选项时继续兼容旧 TOML 大小写与空白', () => {
  render(
    <ScalarField
      descriptor={{
        name: 'mode',
        path: ['mode'],
        kind: 'scalar',
        type: 'str',
        options: ['low', 'high'],
        options_strict: true,
      }}
      value=" HIGH "
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByRole('combobox', { name: 'mode' })).toHaveValue('high');
});

it('$ref 旁的默认值和标题保留在说明书样例描述中', () => {
  const schema = {
    type: 'object',
    $defs: { Mode: { type: 'string', enum: ['A', 'B'] } },
    properties: { mode: { $ref: '#/$defs/Mode', default: 'B', title: '选择模式' } },
  };
  expect(initialActionValues(schema)).toEqual({ mode: 'B' });
  expect(actionFields(schema, { mode: 'B' })?.[0]).toMatchObject({
    name: '选择模式',
    default: 'B',
    value: 'B',
  });
});

it.each([true, { type: 'string' }])('显式额外字段 %j 不映射成丢失结构的标量展示', (additionalProperties) => {
  const schema = {
    type: 'object',
    properties: { note: { type: 'string', default: '备注' } },
    additionalProperties,
  };
  expect(actionFields(schema, { note: '备注', extra: '附加值' })).toBeNull();
});

it.each<[JsonSchema, unknown]>([
  [{ type: 'array', items: { type: 'integer' }, default: [1] }, [1]],
  [{ type: 'integer' }, 0],
  [{ type: 'boolean' }, false],
  [{ type: 'string' }, ''],
  [{ type: 'null' }, null],
])('根 Schema %j 的样例初值保持 JSON 类型', (schema, value) => {
  expect(initialActionInput(schema)).toEqual(value);
});
