import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createRef, useState } from 'react';
import TomlEditor, { type CodeEditorHandle } from '../components/TomlEditor';

const moduleLoad = vi.hoisted(() => {
  let fail!: (error: Error) => void;
  const promise = new Promise<Record<string, unknown>>((_resolve, reject) => {
    fail = reject;
  });
  return { promise, fail };
});
vi.mock('../components/TomlEditorView', () => moduleLoad.promise);

describe('TomlEditor 加载降级', () => {
  it('加载中与加载失败后都保持草稿可编辑、可保存', async () => {
    const saved = vi.fn();
    const handle = createRef<CodeEditorHandle>();
    function Controlled() {
      const [value, setValue] = useState('enabled = true');
      return (
        <TomlEditor
          ref={handle}
          value={value}
          onChange={setValue}
          onSave={() => saved(value)}
          ariaLabel="加载中的 TOML"
        />
      );
    }
    render(<Controlled />);
    const fallback = screen.getByRole('textbox', { name: '加载中的 TOML' });
    fireEvent.change(fallback, { target: { value: '# 加载期间写下的草稿' } });
    fireEvent.keyDown(fallback, { key: 's', ctrlKey: true });
    expect(saved).toHaveBeenLastCalledWith('# 加载期间写下的草稿');
    fireEvent.change(fallback, { target: { value: '前文替换内容后文' } });
    (fallback as HTMLTextAreaElement).setSelectionRange(2, 6, 'backward');
    act(() => expect(handle.current?.insertText('{bot_name}')).toBe(true));
    expect(fallback).toHaveValue('前文{bot_name}后文');
    expect((fallback as HTMLTextAreaElement).selectionStart).toBe('前文{bot_name}'.length);
    await act(async () => moduleLoad.fail(new Error('chunk unavailable')));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('增强编辑器加载失败'));
    expect(fallback).toHaveValue('前文{bot_name}后文');
    fireEvent.change(fallback, { target: { value: '# 失败后仍可编辑' } });
    fireEvent.keyDown(fallback, { key: 's', metaKey: true });
    expect(saved).toHaveBeenLastCalledWith('# 失败后仍可编辑');
  });
});
