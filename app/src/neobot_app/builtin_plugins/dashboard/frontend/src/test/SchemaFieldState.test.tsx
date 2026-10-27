import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { FieldDescriptor } from '../api/types';
import SchemaForm from '../components/SchemaForm';
import DictField from '../components/schema/DictField';
import ListField from '../components/schema/ListField';
import ModelParamsField from '../components/schema/ModelParamsField';
import ScalarField from '../components/schema/ScalarField';

function descriptor(
  kind: FieldDescriptor['kind'],
  value: unknown,
  extra: Partial<FieldDescriptor> = {},
): FieldDescriptor {
  return { name: 'setting', path: ['setting'], kind, type: 'str', value, ...extra };
}

describe('字段写入权限', () => {
  it('readonly 布尔字段禁用开关', () => {
    const onChange = vi.fn();
    render(
      <ScalarField
        descriptor={descriptor('scalar', true, { type: 'bool', readonly: true })}
        value={true}
        onChange={onChange}
      />,
    );
    const control = screen.getByRole('checkbox');
    expect(control).toBeDisabled();
    fireEvent.click(control);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('readonly 候选字段禁用自定义输入', () => {
    render(
      <ScalarField
        descriptor={descriptor('scalar', 'custom', { readonly: true, options: [] })}
        value="custom"
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('textbox')).toBeDisabled();
  });

  it('readonly 字符串数组锁定增删控件，仍能切换查看视图', () => {
    const onChange = vi.fn();
    render(
      <ListField
        descriptor={descriptor('list', ['alpha'], { readonly: true })}
        value={['alpha']}
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('button', { name: '删除 alpha' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: '添加一项' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '切换为列表' }));
    expect(screen.getByRole('textbox', { name: '第 1 项' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '删除第 1 项' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    expect(screen.getByRole('textbox', { name: 'setting' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '格式化' })).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('disabled 字典禁用已有条目和新增条目的键值输入', () => {
    render(
      <DictField
        descriptor={descriptor('dict', { alpha: 'one' })}
        value={{ alpha: 'one' }}
        disabled
        onChange={vi.fn()}
      />,
    );
    for (const input of screen.getAllByRole('textbox')) expect(input).toBeDisabled();
    expect(screen.getByRole('button', { name: '删除 alpha' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '添加键值条目' })).toBeDisabled();
  });

  it('readonly 模型参数禁用参数与自定义 JSON 输入', () => {
    render(
      <ModelParamsField
        descriptor={descriptor(
          'model_params',
          {},
          {
            readonly: true,
            catalog: [{ name: 'temperature', type: 'float', default: 1 }],
          },
        )}
        value={{ enabled_params: ['temperature'], values: { temperature: 1 }, extra_body: { key: true } }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('spinbutton', { name: 'temperature的值' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'key自定义参数值' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: '自定义参数键名' })).toBeDisabled();
  });

  it('readonly 分组向下传递到子字段', () => {
    render(
      <SchemaForm
        fields={[
          descriptor(
            'group',
            {},
            {
              readonly: true,
              fields: [
                descriptor('scalar', true, { name: 'enabled', path: ['setting', 'enabled'], type: 'bool' }),
              ],
            },
          ),
        ]}
        values={{}}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });
});

describe('编辑草稿与排序', () => {
  it.each(['list', 'dict'] as const)('切换 %s 的 JSON 视图保留非法草稿', (kind) => {
    const onChange = vi.fn();
    const value = kind === 'list' ? ['alpha'] : { alpha: 'one' };
    const Component = kind === 'list' ? ListField : DictField;
    render(<Component descriptor={descriptor(kind, value)} value={value} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'setting' }), { target: { value: '{invalid' } });
    fireEvent.click(screen.getByRole('button', { name: '返回可视化编辑' }));
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    expect(screen.getByRole('textbox', { name: 'setting' })).toHaveValue('{invalid');
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('折叠再展开分组保留 JSON 非法草稿', () => {
    const fields = [
      descriptor(
        'group',
        {},
        {
          fields: [descriptor('list', ['alpha'], { name: 'items', path: ['setting', 'items'] })],
        },
      ),
    ];
    const props = { fields, values: {}, onChange: vi.fn(), onToggleCollapse: vi.fn() };
    const { rerender } = render(<SchemaForm {...props} collapse={{}} />);
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'items' }), { target: { value: '[unfinished' } });
    rerender(<SchemaForm {...props} collapse={{ setting: true }} />);
    expect(screen.queryByRole('textbox', { name: 'items' })).not.toBeInTheDocument();
    rerender(<SchemaForm {...props} collapse={{ setting: false }} />);
    expect(screen.getByRole('textbox', { name: 'items' })).toHaveValue('[unfinished');
    expect(props.onChange).not.toHaveBeenCalled();
  });

  it('使用上下移按钮调整列表次序', () => {
    const onChange = vi.fn();
    render(
      <ListField
        descriptor={descriptor('list', ['/first', '/second'])}
        value={['/first', '/second']}
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('button', { name: '上移第 1 项' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '上移第 2 项' }));
    expect(onChange).toHaveBeenCalledWith(['/second', '/first']);
  });

  it('自定义模型参数的非法 JSON 在失焦后保留', () => {
    const onChange = vi.fn();
    render(
      <ModelParamsField
        descriptor={descriptor('model_params', {})}
        value={{ enabled_params: [], values: {}, extra_body: { key: true } }}
        onChange={onChange}
      />,
    );
    const input = screen.getByRole('textbox', { name: 'key自定义参数值' });
    fireEvent.change(input, { target: { value: '{unfinished' } });
    fireEvent.blur(input);
    expect(input).toHaveValue('{unfinished');
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('中文输入法确认候选不会误添加数组条目', () => {
    const onChange = vi.fn();
    render(<ListField descriptor={descriptor('list', [])} value={[]} onChange={onChange} />);
    const input = screen.getByRole('textbox', { name: '添加一项' });
    fireEvent.change(input, { target: { value: '候选文字' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue('候选文字');
  });
});
