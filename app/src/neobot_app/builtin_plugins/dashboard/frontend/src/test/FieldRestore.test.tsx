import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import SchemaForm from '../components/SchemaForm';
import { FieldActions } from '../components/schema/FieldChrome';
import type { FieldDescriptor } from '../api/types';

const field: FieldDescriptor = {
  name: 'note',
  path: ['note'],
  kind: 'scalar',
  type: 'str',
  value: '默认备注',
  default: '默认备注',
};

it('默认值相同时不显示恢复按钮，已保存的非默认值仍可用紧凑图标恢复', async () => {
  const restore = vi.fn();
  const props = {
    fields: [field],
    values: { note: '默认备注' },
    baseline: { note: '默认备注' },
    onChange: vi.fn(),
    onRestore: restore,
  };
  const view = render(<SchemaForm {...props} />);
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
  view.rerender(
    <SchemaForm
      {...props}
      fields={[{ ...field, value: '已保存的自定义备注' }]}
      values={{ note: '已保存的自定义备注' }}
      baseline={{ note: '已保存的自定义备注' }}
    />,
  );
  const button = screen.getByRole('button', { name: '恢复默认' });
  expect(button).toBeEnabled();
  expect(button.textContent).toBe('');
  expect(button.querySelector('svg')).not.toBeNull();
  expect(button.closest('.cfg-control')).toContainElement(screen.getByRole('textbox', { name: 'note' }));
  await userEvent.click(button);
  expect(restore).toHaveBeenCalledWith(['note'], '默认备注');
  view.rerender(<SchemaForm {...props} />);
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
});

it.each(['readonly', 'disabled'] as const)('%s 状态不会恢复已保存的非默认值', async (mode) => {
  const restore = vi.fn();
  render(
    <SchemaForm
      fields={[{ ...field, value: '自定义备注', readonly: mode === 'readonly' }]}
      values={{ note: '自定义备注' }}
      baseline={{ note: '自定义备注' }}
      disabled={mode === 'disabled'}
      onChange={vi.fn()}
      onRestore={restore}
    />,
  );
  const button = screen.getByRole('button', { name: '恢复默认' });
  expect(button).toBeDisabled();
  await userEvent.click(button);
  expect(restore).not.toHaveBeenCalled();
});

it('敏感字段未公开默认值时不提供恢复按钮', () => {
  render(
    <SchemaForm
      fields={[
        {
          ...field,
          name: '凭据',
          path: ['credential'],
          sensitive: true,
          default: undefined,
          value: '••••••••',
          has_value: true,
        },
      ]}
      values={{ credential: '••••••••' }}
      onChange={vi.fn()}
      onRestore={vi.fn()}
    />,
  );
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
});

it('值已等于默认值时仍可查看历史，不因隐藏恢复按钮而丢掉历史入口', async () => {
  const history = vi.fn();
  render(
    <FieldActions
      descriptor={field}
      value={field.value}
      historyCount={2}
      onRestore={vi.fn()}
      onShowHistory={history}
    />,
  );
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '历史 2' }));
  expect(history).toHaveBeenCalledWith(field);
});

it.each([
  { value: true, defaultValue: false },
  { value: 1, defaultValue: 0 },
  { value: '自定义', defaultValue: '' },
  { value: ['一项'], defaultValue: [] },
  { value: { key: '内容' }, defaultValue: {} },
  { value: '自定义', defaultValue: null },
])('默认值 %j 保持原始类型，不被当作没有默认值', async ({ value, defaultValue }) => {
  const restore = vi.fn();
  render(<FieldActions descriptor={{ ...field, default: defaultValue }} value={value} onRestore={restore} />);
  await userEvent.click(screen.getByRole('button', { name: '恢复默认' }));
  expect(restore).toHaveBeenCalledWith(['note'], defaultValue);
});
