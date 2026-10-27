import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createRef, useState } from 'react';
import { EditorView } from '@codemirror/view';
import { undoDepth } from '@codemirror/commands';
import TomlEditorView from '../components/TomlEditorView';
import type { CodeEditorHandle } from '../components/TomlEditor';

beforeAll(() => {
  // jsdom 无文本排版信息；CodeMirror 的布局测量仍需这些标准 DOM 方法。
  if (!Range.prototype.getClientRects) Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
  if (!Range.prototype.getBoundingClientRect) Range.prototype.getBoundingClientRect = () => new DOMRect();
});
afterEach(() => {
  delete document.documentElement.dataset.theme;
});

function viewFor(label = '测试 TOML') {
  const content = screen.getByRole('textbox', { name: label });
  const view = EditorView.findFromDOM(content)!;
  expect(view).toBeDefined();
  return view;
}

function Controlled({ source, onChange = () => {} }: { source: string; onChange?: (value: string) => void }) {
  const [value, setValue] = useState(source);
  return (
    <TomlEditorView
      value={value}
      ariaLabel="测试 TOML"
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe('TomlEditor 真实 CodeMirror 命令', () => {
  it('文本模式只标记已知未转义占位符，中文与TOML样式文本不被误解析', () => {
    const source = '人设 # 不是注释\n名字 = "保持原文"\n{bot_name} {{bot_name}} {普通中文}';
    const { container, rerender } = render(
      <TomlEditorView
        language="text"
        placeholders={['bot_name']}
        value={source}
        onChange={vi.fn()}
        ariaLabel="模板文本"
      />,
    );
    const view = viewFor('模板文本');
    expect(container.querySelectorAll('.editor-template-placeholder')).toHaveLength(1);
    expect(container.querySelector('.editor-template-placeholder')).toHaveTextContent('{bot_name}');
    expect(
      container.querySelector('.toml-token-comment, .toml-token-key, .toml-token-string'),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '注释' })).not.toBeInTheDocument();
    fireEvent.keyDown(view.contentDOM, { key: '/', code: 'Slash', ctrlKey: true });
    expect(view.state.doc.toString()).toBe(source);
    rerender(<TomlEditorView language="text" value={source} onChange={vi.fn()} ariaLabel="模板文本" />);
    expect(container.querySelector('.editor-template-placeholder')).not.toBeInTheDocument();
    expect(viewFor('模板文本')).toBe(view);
  });

  it('文本编辑器在当前选区插入占位符，可撤销重做并保护只读状态', () => {
    const handle = createRef<CodeEditorHandle>();
    const changed = vi.fn();
    const source = '前文替换内容后文\n第二行';
    const props = {
      language: 'text' as const,
      value: source,
      onChange: changed,
      ariaLabel: '模板文本',
      editorRef: handle,
    };
    const { rerender } = render(<TomlEditorView {...props} />);
    const view = viewFor('模板文本');
    act(() => view.dispatch({ selection: { anchor: 6, head: 2 } }));
    act(() => expect(handle.current?.insertText('{bot_name}')).toBe(true));
    expect(view.state.doc.toString()).toBe('前文{bot_name}后文\n第二行');
    expect(view.state.selection.main.from).toBe('前文{bot_name}'.length);
    expect(view.state.selection.main.empty).toBe(true);
    expect(view.contentDOM).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: '撤销 文本 编辑' }));
    expect(view.state.doc.toString()).toBe(source);
    fireEvent.click(screen.getByRole('button', { name: '重做 文本 编辑' }));
    expect(view.state.doc.toString()).toContain('{bot_name}');
    const edited = view.state.doc.toString();
    rerender(<TomlEditorView {...props} value={edited} readOnly />);
    act(() => expect(handle.current?.insertText('不得写入')).toBe(false));
    expect(view.state.doc.toString()).toBe(edited);
  });

  it('文本模式的查找替换和多行缩进沿用原生命令', () => {
    const source = '第一行 Neo\n第二行 Neo';
    render(<TomlEditorView language="text" value={source} onChange={vi.fn()} ariaLabel="模板文本" />);
    const view = viewFor('模板文本');
    act(() => view.dispatch({ selection: { anchor: 0, head: source.length } }));
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab' });
    expect(view.state.doc.toString()).toBe('  第一行 Neo\n  第二行 Neo');
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab', shiftKey: true });
    expect(view.state.doc.toString()).toBe(source);
    fireEvent.click(screen.getByRole('button', { name: '查找' }));
    fireEvent.change(screen.getByRole('textbox', { name: '查找' }), { target: { value: 'Neo' } });
    fireEvent.change(screen.getByRole('textbox', { name: '替换为' }), { target: { value: '小乔' } });
    fireEvent.click(screen.getByRole('button', { name: '全部替换' }));
    expect(view.state.doc.toString()).toBe(source.replaceAll('Neo', '小乔'));
  });

  it('高亮 TOML 并支持 Tab、Shift Tab 与行注释，保留注释和 CRLF', () => {
    const source = '# 原有注释\r\n[bot]\r\nname = "Neo"\r\ncount = 2\r\nenabled = true\r\n';
    const changed = vi.fn();
    const { container } = render(<Controlled source={source} onChange={changed} />);
    const view = viewFor();
    expect(container.querySelector('.cm-lineNumbers')).toBeInTheDocument();
    expect(container.querySelector('.toml-token-comment')).toHaveTextContent('# 原有注释');
    expect(container.querySelector('.toml-token-string')).toHaveTextContent('"Neo"');
    expect(container.querySelector('.toml-token-number')).toHaveTextContent('2');
    const line = view.state.doc.line(3);
    act(() => view.dispatch({ selection: { anchor: line.from, head: line.to } }));
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab' });
    expect(view.state.doc.line(3).text).toBe('  name = "Neo"');
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab', shiftKey: true });
    expect(view.state.doc.line(3).text).toBe('name = "Neo"');
    fireEvent.click(screen.getByRole('button', { name: '注释' }));
    expect(view.state.doc.line(3).text).toBe('# name = "Neo"');
    fireEvent.click(screen.getByRole('button', { name: '注释' }));
    expect(changed.mock.lastCall?.[0]).toBe(source);
  });

  it('查找替换、撤销重做与跳转行使用真实编辑命令', async () => {
    const source = '# 保留说明\nname = "Neo"\nalias = "Neo"\n';
    render(<Controlled source={source} />);
    const view = viewFor();
    fireEvent.click(screen.getByRole('button', { name: '查找' }));
    fireEvent.change(screen.getByRole('textbox', { name: '查找' }), { target: { value: 'Neo' } });
    fireEvent.change(screen.getByRole('textbox', { name: '替换为' }), { target: { value: '小乔' } });
    fireEvent.click(screen.getByRole('button', { name: '全部替换' }));
    expect(view.state.doc.toString()).toBe(source.replaceAll('Neo', '小乔'));
    fireEvent.click(screen.getByRole('button', { name: '撤销 TOML 编辑' }));
    expect(view.state.doc.toString()).toBe(source);
    fireEvent.click(screen.getByRole('button', { name: '重做 TOML 编辑' }));
    expect(view.state.doc.toString()).toContain('alias = "小乔"');
    fireEvent.click(screen.getByRole('button', { name: '定位' }));
    fireEvent.change(screen.getByRole('textbox', { name: /跳转到行/ }), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '跳转' }));
    await waitFor(() => expect(view.state.doc.lineAt(view.state.selection.main.head).number).toBe(3));
  });

  it('外部回读、权限与主题切换不重建实例或丢掉选择区和撤销记录', async () => {
    const changed = vi.fn();
    const props = { value: 'count = 1\n# 原有说明\n', ariaLabel: '测试 TOML', onChange: changed };
    const { rerender } = render(<TomlEditorView {...props} />);
    const view = viewFor();
    act(() => view.dispatch({ changes: { from: 8, to: 9, insert: '2' }, selection: { anchor: 9 } }));
    const edited = view.state.doc.toString();
    rerender(<TomlEditorView {...props} value={edited} disabled />);
    expect(viewFor()).toBe(view);
    expect(view.state.selection.main.head).toBe(9);
    expect(undoDepth(view.state)).toBe(1);
    act(() => view.dispatch({ changes: { from: 0, insert: '不应写入' } }));
    expect(view.state.doc.toString()).toBe(edited);
    expect(screen.getByRole('button', { name: '注释' })).toBeDisabled();
    rerender(<TomlEditorView {...props} value={'# 外部说明\n' + edited} />);
    expect(view.state.selection.main.head).toBe(16);
    expect(undoDepth(view.state)).toBe(1);
    expect(changed).toHaveBeenCalledTimes(1);
    await act(async () => {
      document.documentElement.dataset.theme = 'dark';
    });
    await waitFor(() => expect(view.state.facet(EditorView.darkTheme)).toBe(true));
    expect(viewFor()).toBe(view);
    fireEvent.click(screen.getByRole('button', { name: '撤销 TOML 编辑' }));
    expect(view.state.doc.toString()).toBe('# 外部说明\n' + props.value);
  });

  it('保存快捷键使用最新回调，禁止忙碌、只读或无修改时保存', () => {
    const oldSave = vi.fn();
    const newSave = vi.fn();
    const props = { value: 'enabled = true', ariaLabel: '测试 TOML', onChange: vi.fn() };
    const { rerender } = render(<TomlEditorView {...props} onSave={oldSave} saveDisabled />);
    const view = viewFor();
    fireEvent.keyDown(view.contentDOM, { key: 's', code: 'KeyS', ctrlKey: true });
    expect(oldSave).not.toHaveBeenCalled();
    rerender(<TomlEditorView {...props} onSave={newSave} />);
    fireEvent.keyDown(view.contentDOM, { key: 's', code: 'KeyS', ctrlKey: true });
    expect(newSave).toHaveBeenCalledTimes(1);
    rerender(<TomlEditorView {...props} onSave={newSave} disabled />);
    fireEvent.keyDown(view.contentDOM, { key: 's', code: 'KeyS', ctrlKey: true });
    rerender(<TomlEditorView {...props} onSave={newSave} readOnly />);
    fireEvent.keyDown(view.contentDOM, { key: 's', code: 'KeyS', ctrlKey: true });
    expect(newSave).toHaveBeenCalledTimes(1);
    expect(view.contentDOM).toHaveAttribute('aria-readonly', 'true');
    fireEvent.click(screen.getByRole('button', { name: '查找' }));
    expect(screen.getByRole('textbox', { name: '查找' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: '替换为' })).not.toBeInTheDocument();
  });
});
