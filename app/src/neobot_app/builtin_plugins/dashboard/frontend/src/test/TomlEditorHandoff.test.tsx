import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import TomlEditor, { type TomlEditorViewProps } from '../components/TomlEditor';

const moduleLoad = vi.hoisted(() => {
  let finish!: (module: Record<string, unknown>) => void;
  const promise = new Promise<Record<string, unknown>>((resolve) => {
    finish = resolve;
  });
  return { promise, finish };
});
vi.mock('../components/TomlEditorView', () => moduleLoad.promise);

describe('TomlEditor 加载交接', () => {
  it('增强编辑器接收加载期间的最新文本、选区、滚动位置与焦点', async () => {
    const mounted = vi.fn();
    function Controlled() {
      const [value, setValue] = useState('enabled = true');
      return <TomlEditor value={value} onChange={setValue} ariaLabel="交接 TOML" />;
    }
    render(<Controlled />);
    const fallback = screen.getByRole('textbox', { name: '交接 TOML' }) as HTMLTextAreaElement;
    fireEvent.change(fallback, { target: { value: '# 刚输入的草稿\ncount = 2' } });
    fallback.focus();
    fallback.setSelectionRange(2, 5, 'backward');
    fallback.scrollTop = 42;
    await act(async () =>
      moduleLoad.finish({
        default: (props: TomlEditorViewProps) => {
          mounted(props);
          return <p>增强编辑器已加载</p>;
        },
      }),
    );
    expect(await screen.findByText('增强编辑器已加载')).toBeInTheDocument();
    expect(mounted.mock.lastCall?.[0]).toMatchObject({
      value: '# 刚输入的草稿\ncount = 2',
      initialSelection: { start: 2, end: 5, direction: 'backward', focused: true, scrollTop: 42 },
    });
  });
});
