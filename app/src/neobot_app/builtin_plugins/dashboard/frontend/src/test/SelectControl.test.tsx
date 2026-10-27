import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SelectControl from '../components/ui/SelectControl';

const OPTIONS = [
  { value: '', label: '全部模块' },
  { value: 'agent', label: 'Agent 任务' },
  { value: 'offline', label: '未启用', disabled: true },
];

describe('SelectControl', () => {
  it('支持键盘选择与空值“全部”，关闭后将焦点返回控件', async () => {
    const changed = vi.fn();
    function Example() {
      const [value, setValue] = useState('');
      return (
        <SelectControl
          label="日志模块"
          value={value}
          options={OPTIONS}
          onValueChange={(next) => {
            setValue(next);
            changed(next);
          }}
        />
      );
    }
    render(<Example />);
    const trigger = screen.getByRole('combobox', { name: '日志模块' });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    });
    const option = screen.getByRole('option', { name: 'Agent 任务' });
    await act(async () => {
      option.focus();
      fireEvent.keyDown(option, { key: 'Enter' });
    });
    await waitFor(() => expect(trigger).toHaveTextContent('Agent 任务'));
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(changed).toHaveBeenLastCalledWith('agent');
    await act(async () => {
      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    });
    const all = screen.getByRole('option', { name: '全部模块' });
    await act(async () => {
      all.focus();
      fireEvent.keyDown(all, { key: 'Enter' });
    });
    await waitFor(() => expect(trigger).toHaveTextContent('全部模块'));
    expect(changed).toHaveBeenLastCalledWith('');
  });

  it('保留完整选项名称与禁用状态，Escape 不改变所选项', async () => {
    const changed = vi.fn();
    const full = '很长的 Agent 名称与完整装配失败说明'.repeat(6);
    render(
      <SelectControl
        label="选择 Agent"
        value="long"
        options={[...OPTIONS, { value: 'long', label: full }]}
        onValueChange={changed}
      />,
    );
    const trigger = screen.getByRole('combobox', { name: '选择 Agent' });
    await act(async () => {
      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    });
    const selected = screen.getByRole('option', { name: full });
    expect(selected).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('option', { name: '未启用' })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.keyDown(selected, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
    expect(changed).not.toHaveBeenCalled();
    expect(trigger).toHaveTextContent(full);
  });
});
