import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SchemaForm from '../components/SchemaForm';
import type { FieldDescriptor } from '../api/types';

describe('插件声明的字段显示名称', () => {
  it.each(['列表名称', 'board_title'])('按 %s 搜索仍能找到同一字段', (filter) => {
    render(
      <SchemaForm
        fields={[
          {
            name: 'board_title',
            path: ['board_title'],
            label: '列表名称',
            kind: 'scalar',
            type: 'str',
            value: '待办',
          },
        ]}
        filter={filter}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('textbox', { name: '列表名称' })).toHaveValue('待办');
  });
  it('使用中文名称访问控件，编辑仍写回原始字段路径', () => {
    const change = vi.fn();
    const fields: FieldDescriptor[] = [
      {
        name: 'board_title',
        path: ['board_title'],
        label: '列表名称',
        kind: 'scalar',
        type: 'str',
        value: '我的待办',
      },
      { name: 'enabled', path: ['enabled'], label: '接收通知', kind: 'scalar', type: 'bool', value: true },
      {
        name: 'interval',
        path: ['interval'],
        label: '检查间隔（秒）',
        kind: 'scalar',
        type: 'int',
        value: 60,
      },
    ];
    render(<SchemaForm fields={fields} onChange={change} />);
    fireEvent.input(screen.getByRole('textbox', { name: '列表名称' }), { target: { value: '工作待办' } });
    expect(change).toHaveBeenLastCalledWith(['board_title'], '工作待办');
    fireEvent.click(screen.getByRole('checkbox', { name: /接收通知/ }));
    expect(change).toHaveBeenLastCalledWith(['enabled'], false);
    expect(screen.getByRole('spinbutton', { name: '检查间隔（秒）' })).toHaveValue(60);
    expect(screen.queryByText('board_title')).not.toBeInTheDocument();
  });

  it('中文显示名称不改变密钥识别，没有名称时保留旧字段名', () => {
    const fields: FieldDescriptor[] = [
      { name: 'api_key', path: ['api_key'], label: '访问凭据', kind: 'scalar', type: 'str', value: '' },
      { name: 'legacy', path: ['legacy'], kind: 'scalar', type: 'int', value: 1 },
    ];
    render(<SchemaForm fields={fields} onChange={vi.fn()} />);
    expect(screen.getByLabelText('访问凭据', { exact: true })).toHaveAttribute('type', 'password');
    expect(screen.getByRole('spinbutton', { name: 'legacy' })).toHaveValue(1);
  });

  it('集合和分组展示同一份声明名称', () => {
    const fields: FieldDescriptor[] = [
      { name: 'options', path: ['options'], label: '通知选项', kind: 'group', fields: [] },
      { name: 'targets', path: ['targets'], label: '接收目标', kind: 'list', value: [], element_type: 'str' },
      { name: 'mapping', path: ['mapping'], label: '自定义映射', kind: 'dict', value: {} },
    ];
    render(<SchemaForm fields={fields} onChange={vi.fn()} />);
    expect(screen.getByRole('heading', { name: '通知选项' })).toBeVisible();
    expect(screen.getByText('接收目标')).toBeVisible();
    expect(screen.getByText('自定义映射')).toBeVisible();
  });
});
