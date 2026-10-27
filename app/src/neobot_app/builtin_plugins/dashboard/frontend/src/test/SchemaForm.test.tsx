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
        collapse={{ bot: true }}
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
    // list / dict 曾经共用 JsonField（原始 JSON 文本域）；现在各自有可视化编辑器，不应再相等
    expect(fieldRegistry.list).toBeDefined();
    expect(fieldRegistry.dict).toBeDefined();
    expect(fieldRegistry.list).not.toBe(fieldRegistry.dict);
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

  it('深层对象数组的重载方式只说明一次，不在每个字段重复贴标', () => {
    const settings = makeField({
      name: 'settings',
      path: ['models', '0', 'settings'],
      kind: 'group',
      hot_reload: true,
      fields: ['temperature', 'max_tokens'].map((name) =>
        makeField({
          name,
          path: ['models', '0', 'settings', name],
          hot_reload: true,
        }),
      ),
    });
    render(
      <SchemaForm
        fields={[
          makeField({
            name: 'models',
            path: ['models'],
            kind: 'model_list',
            hot_reload: true,
            value: [{ settings: {} }],
            items: [{ index: 0, fields: [settings] }],
          }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getAllByText('生效方式')).toHaveLength(1);
    expect(screen.getByText('保存后重载配置生效，无需重启')).toBeInTheDocument();
    expect(screen.queryByText('热重载', { exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'temperature' })).toBeInTheDocument();
  });

  it('混合分区保留具体需重启项和原因，折叠时仍能识别分区的例外', () => {
    const fields = [
      makeField({
        name: 'adapter',
        path: ['adapter'],
        kind: 'group',
        hot_reload: false,
        partial_hot_reload: true,
        fields: [
          makeField({ name: 'retry', path: ['adapter', 'retry'], hot_reload: true }),
          makeField({
            name: 'port',
            path: ['adapter', 'port'],
            hot_reload: false,
            restart_reason: '监听端口在启动时绑定',
          }),
        ],
      }),
    ];
    const props = { fields, onChange: vi.fn(), onToggleCollapse: vi.fn() };
    const { rerender } = render(<SchemaForm {...props} />);
    expect(screen.getByText('支持重载配置；需重启项已单独标注')).toBeInTheDocument();
    expect(screen.getByText('需重启', { exact: true })).toHaveAttribute('title', '监听端口在启动时绑定');
    rerender(<SchemaForm {...props} collapse={{ adapter: true }} />);
    expect(screen.getByText('部分需重启')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'port' })).not.toBeInTheDocument();
  });

  it('缺少生效能力的字段不被当成支持重载', () => {
    const { rerender } = render(<SchemaForm fields={[makeField({})]} onChange={vi.fn()} />);
    expect(screen.queryByText('生效方式')).not.toBeInTheDocument();
    rerender(
      <SchemaForm
        fields={[
          makeField({ name: 'known', path: ['known'], hot_reload: true }),
          makeField({ name: 'unknown', path: ['unknown'] }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('已声明支持重载的配置，保存后重载生效')).toBeInTheDocument();
    expect(screen.queryByText('保存后重载配置生效，无需重启')).not.toBeInTheDocument();
  });

  it('插件配置可使用插件的能力声明，避免通用 schema 错误承诺无需重启', () => {
    render(
      <SchemaForm fields={[makeField({ hot_reload: true })]} showReloadSummary={false} onChange={vi.fn()} />,
    );
    expect(screen.queryByText('生效方式')).not.toBeInTheDocument();
    expect(screen.queryByText('保存后重载配置生效，无需重启')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'f' })).toBeInTheDocument();
  });

  it('对象数组的整体修改策略不会被子字段的可重载能力覆盖', () => {
    const fields = [
      makeField({
        name: 'models',
        path: ['models'],
        kind: 'model_list',
        hot_reload: false,
        value: [{ name: 'demo' }],
        item_fields: [makeField({ hot_reload: true })],
        items: [{ index: 0, fields: [makeField({ hot_reload: true })] }],
      }),
    ];
    const { rerender } = render(<SchemaForm fields={fields} onChange={vi.fn()} />);
    expect(screen.getByText('支持重载配置；需重启项已单独标注')).toBeInTheDocument();
    expect(screen.getByText('需重启', { exact: true })).toBeInTheDocument();
    rerender(<SchemaForm fields={[{ ...fields[0], hot_reload: undefined }]} onChange={vi.fn()} />);
    expect(screen.getByText('已声明支持重载的配置，保存后重载生效')).toBeInTheDocument();
    expect(screen.queryByText('保存后重载配置生效，无需重启')).not.toBeInTheDocument();
  });
});
