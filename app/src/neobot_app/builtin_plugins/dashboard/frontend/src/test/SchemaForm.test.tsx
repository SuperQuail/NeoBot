// SchemaForm 回归测试 —— 渲染、kind 注册表兜底、分组递归、历史弹窗
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SchemaForm from '../components/SchemaForm';
import { resolveFieldComponent, fieldRegistry } from '../components/schema/fieldRegistry';
import type { FieldDescriptor } from '../api/types';

function makeField(overrides: Partial<FieldDescriptor>): FieldDescriptor {
  return { name: 'f', path: ['f'], kind: 'scalar', type: 'str', value: '', ...overrides };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('SchemaForm', () => {
  it('无字段时给出空状态提示', () => {
    render(<SchemaForm fields={[]} values={{}} onChange={() => {}} />);
    expect(screen.getByText('没有可编辑的字段')).toBeInTheDocument();
  });

  it('渲染标量字段的当前值', () => {
    const fields = [
      makeField({ name: 'host', path: ['host'], value: '0.0.0.0' }),
      makeField({ name: 'port', path: ['port'], type: 'int', value: 9981 }),
    ];
    render(<SchemaForm fields={fields} values={{ host: '0.0.0.0', port: 9981 }} onChange={() => {}} />);
    expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument();
    expect(screen.getByDisplayValue('9981')).toBeInTheDocument();
  });

  it('布尔字段渲染成开关并显示开启状态', () => {
    const fields = [makeField({ name: 'enabled', path: ['enabled'], type: 'bool', value: true })];
    render(<SchemaForm fields={fields} values={{ enabled: true }} onChange={() => {}} />);
    expect(screen.getByRole('checkbox')).toBeChecked();
    expect(screen.getByText('已开启')).toBeInTheDocument();
  });

  it('分组递归渲染子字段，折叠时隐藏', () => {
    const fields: FieldDescriptor[] = [
      {
        name: 'bot',
        path: ['bot'],
        kind: 'group',
        value: { account: '0' },
        fields: [makeField({ name: 'account', path: ['bot', 'account'], value: '0' })],
      },
    ];
    render(
      <SchemaForm
        fields={fields}
        values={{ bot: { account: '0' } }}
        collapse={{ 'bot': true }}
        onToggleCollapse={() => {}}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText('bot')).toBeInTheDocument();
    // 折叠后子字段不渲染
    expect(screen.queryByDisplayValue('0')).not.toBeInTheDocument();
  });

  it('注册表：已知 kind 命中，未知 kind 兜底为标量且不抛异常', () => {
    expect(fieldRegistry.scalar).toBeDefined();
    expect(fieldRegistry.list).toBe(fieldRegistry.dict);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const Fallback = resolveFieldComponent('brand_new_kind');
    expect(Fallback).toBe(fieldRegistry.scalar);
    expect(warn).toHaveBeenCalled();
  });

  it('未知 kind 的字段仍会渲染出来（不丢数据）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // 后端可能先于前端引入新 kind，这里刻意绕过 FieldKind 联合类型模拟这种情况
    const unknownKind = 'brand_new_kind' as unknown as FieldDescriptor['kind'];
    const fields = [makeField({ name: 'mystery', path: ['mystery'], kind: unknownKind, value: 'keep-me' })];
    render(<SchemaForm fields={fields} values={{ mystery: 'keep-me' }} onChange={() => {}} />);
    expect(screen.getByDisplayValue('keep-me')).toBeInTheDocument();
    expect(warn).toHaveBeenCalled();
  });
});
