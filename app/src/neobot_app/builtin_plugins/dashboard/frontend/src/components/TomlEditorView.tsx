import { useCallback, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { basicSetup } from 'codemirror';
import { Annotation, Compartment, EditorState, Transaction, type Extension } from '@codemirror/state';
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  keymap,
  type Command,
  type DecorationSet,
  type ViewUpdate,
} from '@codemirror/view';
import {
  indentLess,
  indentMore,
  indentWithTab,
  isolateHistory,
  redo,
  redoDepth,
  toggleLineComment,
  undo,
  undoDepth,
} from '@codemirror/commands';
import { HighlightStyle, indentUnit, StreamLanguage, syntaxHighlighting } from '@codemirror/language';
import { gotoLine, openSearchPanel, search } from '@codemirror/search';
import { toml } from '@codemirror/legacy-modes/mode/toml';
import { tags } from '@lezer/highlight';
import {
  IndentDecrease,
  IndentIncrease,
  Keyboard,
  ListOrdered,
  MessageSquareCode,
  MoreHorizontal,
  Redo2,
  Search,
  Undo2,
} from 'lucide-react';
import Button from './ui/Button';
import type { TomlEditorViewProps } from './TomlEditor';

const externalChange = Annotation.define<boolean>();
const normalize = (value: string) => value.replace(/\r\n?/g, '\n');
const lineEnding = (value: string) => value.match(/\r\n|\r|\n/)?.[0] || '\n';
const tomlLanguage = StreamLanguage.define(toml);
const highlighting = HighlightStyle.define([
  { tag: tags.comment, class: 'toml-token-comment' },
  { tag: tags.propertyName, class: 'toml-token-key' },
  { tag: tags.string, class: 'toml-token-string' },
  { tag: [tags.number, tags.integer, tags.float], class: 'toml-token-number' },
  { tag: [tags.atom, tags.bool, tags.keyword], class: 'toml-token-atom' },
  { tag: [tags.bracket, tags.punctuation], class: 'toml-token-punctuation' },
]);
const phrases = {
  Find: '查找',
  Replace: '替换为',
  next: '下一个',
  previous: '上一个',
  all: '全选匹配',
  'match case': '区分大小写',
  regexp: '正则',
  'by word': '整词',
  replace: '替换',
  'replace all': '全部替换',
  close: '关闭查找',
  'Go to line': '跳转到行',
  go: '跳转',
  'current match': '当前匹配',
  'on line': '所在行',
  'replaced match on line $': '已替换第 $ 行的匹配',
  'replaced $ matches': '已替换 $ 处匹配',
};

function syntaxConfiguration(props: TomlEditorViewProps): Extension {
  if (props.language !== 'text') return [tomlLanguage, syntaxHighlighting(highlighting)];
  const names = new Set(props.placeholders || []);
  if (!names.size) return [];
  const mark = Decoration.mark({ class: 'editor-template-placeholder' });
  const matcher = new MatchDecorator({
    regexp: /\{([^{}\r\n]+)\}/g,
    decoration: (match, view, from) => {
      const to = from + match[0].length;
      const escaped =
        (from > 0 && view.state.sliceDoc(from - 1, from) === '{') || view.state.sliceDoc(to, to + 1) === '}';
      return names.has(match[1]) && !escaped ? mark : null;
    },
  });
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = matcher.createDeco(view);
      }
      update(update: ViewUpdate) {
        this.decorations = matcher.updateDeco(update, this.decorations);
      }
    },
    { decorations: (value) => value.decorations },
  );
}

function editingConfiguration(props: TomlEditorViewProps): Extension {
  const locked = !!props.disabled || !!props.readOnly;
  return [
    EditorState.readOnly.of(locked),
    EditorView.editable.of(!locked),
    EditorView.contentAttributes.of({
      'aria-label': props.ariaLabel,
      'aria-readonly': String(locked),
      'aria-disabled': String(!!props.disabled),
      ...(props.describedBy ? { 'aria-describedby': props.describedBy } : {}),
      ...(locked ? { tabindex: '0' } : {}),
      spellcheck: 'false',
    }),
  ];
}

function themeConfiguration() {
  return EditorView.theme({}, { dark: document.documentElement.dataset.theme === 'dark' });
}

export default function TomlEditorView(props: TomlEditorViewProps) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<EditorView | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const separator = useRef(lineEnding(props.value));
  const configuration = useMemo(() => new Compartment(), []);
  const theme = useMemo(() => new Compartment(), []);
  const syntax = useMemo(() => new Compartment(), []);
  const [helpOpen, setHelpOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const lineCount = useMemo(() => props.value.split(/\r\n|\r|\n/).length, [props.value]);
  const [status, setStatus] = useState({ line: 1, column: 1, undo: 0, redo: 0 });
  const locked = !!props.disabled || !!props.readOnly;
  const isText = props.language === 'text';
  const editorLabel = isText ? '文本' : 'TOML';
  const placeholderKey = JSON.stringify(props.placeholders || []);
  const updateStatus = useCallback((view: EditorView) => {
    const cursor = view.state.selection.main.head;
    const line = view.state.doc.lineAt(cursor);
    setStatus({
      line: line.number,
      column: cursor - line.from + 1,
      undo: undoDepth(view.state),
      redo: redoDepth(view.state),
    });
  }, []);

  useImperativeHandle(
    props.editorRef,
    () => ({
      insertText(text) {
        const view = editor.current;
        const current = latest.current;
        if (!view || current.disabled || current.readOnly || view.state.readOnly) return false;
        view.dispatch({
          ...view.state.replaceSelection(normalize(text)),
          annotations: [Transaction.userEvent.of('input'), isolateHistory.of('full')],
          scrollIntoView: true,
        });
        view.focus();
        return true;
      },
    }),
    [],
  );

  useLayoutEffect(() => {
    if (!host.current) return;
    const initial = latest.current;
    const selection = initial.initialSelection;
    const documentLength = normalize(initial.value).length;
    // textarea 的选区偏移已经按 LF 计数，即便原始文件使用 CRLF。
    const start = selection ? Math.min(selection.start, documentLength) : 0;
    const end = selection ? Math.min(selection.end, documentLength) : 0;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: normalize(initial.value),
        selection:
          selection?.direction === 'backward' ? { anchor: end, head: start } : { anchor: start, head: end },
        extensions: [
          keymap.of([
            {
              key: 'Mod-s',
              scope: 'editor search-panel',
              preventDefault: true,
              run: () => {
                const current = latest.current;
                if (!current.disabled && !current.readOnly && !current.saveDisabled) current.onSave?.();
                return true;
              },
            },
            indentWithTab,
          ]),
          basicSetup,
          syntax.of(syntaxConfiguration(initial)),
          indentUnit.of('  '),
          EditorView.lineWrapping,
          search({ top: true }),
          EditorState.phrases.of(phrases),
          configuration.of(editingConfiguration(initial)),
          theme.of(themeConfiguration()),
          EditorState.transactionFilter.of((transaction) =>
            transaction.docChanged &&
            transaction.startState.readOnly &&
            !transaction.annotation(externalChange)
              ? []
              : transaction,
          ),
          EditorView.updateListener.of((update) => {
            if (
              update.docChanged &&
              !update.transactions.some((transaction) => transaction.annotation(externalChange))
            ) {
              latest.current.onChange(update.state.doc.toString().replace(/\n/g, separator.current));
            }
            if (update.docChanged || update.selectionSet) updateStatus(update.view);
          }),
        ],
      }),
    });
    editor.current = view;
    if (selection?.focused) view.focus();
    if (selection) view.scrollDOM.scrollTop = selection.scrollTop;
    updateStatus(view);
    const observer = new MutationObserver(() => {
      view.dispatch({ effects: theme.reconfigure(themeConfiguration()) });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      observer.disconnect();
      editor.current = null;
      view.destroy();
    };
  }, [configuration, syntax, theme, updateStatus]);

  useLayoutEffect(() => {
    editor.current?.dispatch({ effects: syntax.reconfigure(syntaxConfiguration(latest.current)) });
  }, [syntax, props.language, placeholderKey]);

  useLayoutEffect(() => {
    const view = editor.current;
    if (view) view.dispatch({ effects: configuration.reconfigure(editingConfiguration(latest.current)) });
  }, [configuration, props.disabled, props.readOnly, props.ariaLabel, props.describedBy]);

  useLayoutEffect(() => {
    const view = editor.current;
    if (!view) return;
    separator.current = lineEnding(props.value);
    const before = view.state.doc.toString();
    const after = normalize(props.value);
    if (before === after) return;
    // 最小变更会映射已有选择区与撤销记录；外部回读不加入用户编辑历史。
    let from = 0;
    while (from < before.length && from < after.length && before[from] === after[from]) from++;
    let to = before.length;
    let insertTo = after.length;
    while (to > from && insertTo > from && before[to - 1] === after[insertTo - 1]) {
      to--;
      insertTo--;
    }
    view.dispatch({
      changes: { from, to, insert: after.slice(from, insertTo) },
      annotations: [externalChange.of(true), Transaction.addToHistory.of(false)],
    });
  }, [props.value]);

  const run = (command: Command, mutates = false) => {
    const view = editor.current;
    if (!view || (mutates && locked)) return;
    command(view);
    setMoreOpen(false);
    // 查找与行定位会聚焦自己的输入框，编辑命令才把焦点还给正文。
    if (mutates) view.focus();
  };

  return (
    <div
      className="toml-code-editor"
      data-language={isText ? 'text' : 'toml'}
      data-readonly={locked}
      aria-busy={props.disabled || undefined}
    >
      <div className="toml-editor-toolbar" role="toolbar" aria-label={`${editorLabel} 编辑工具`}>
        <div className="toml-file-info" title={props.filePath || props.fileName || props.ariaLabel}>
          <code>{props.fileName || props.ariaLabel}</code>
          <span>{lineCount} 行</span>
        </div>
        {props.toolbarActions && <div className="toml-toolbar-custom">{props.toolbarActions}</div>}
        <Button
          size="sm"
          onClick={() => run(openSearchPanel)}
          aria-label="查找"
          title="查找与替换（Ctrl / ⌘ F）"
        >
          <Search size={14} /> <span className="toml-tool-label">查找</span>
        </Button>
        <Button
          size="sm"
          className="toml-more-toggle"
          aria-label="更多编辑操作"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
          title={isText ? '定位、缩进与历史' : '定位、注释、缩进与历史'}
        >
          <MoreHorizontal size={16} />
        </Button>
        <div className="toml-toolbar-secondary" data-open={moreOpen} role="group" aria-label="快捷编辑操作">
          <Button size="sm" onClick={() => run(gotoLine)} title="跳转到行（Ctrl / ⌘ Alt G）">
            <ListOrdered size={14} /> 定位
          </Button>
          {!isText && (
            <Button
              size="sm"
              disabled={locked}
              onClick={() => run(toggleLineComment, true)}
              title="切换行注释（Ctrl / ⌘ /）"
            >
              <MessageSquareCode size={14} /> 注释
            </Button>
          )}
          <span className="toml-toolbar-separator" aria-hidden="true" />
          <Button
            size="sm"
            disabled={locked}
            onClick={() => run(indentMore, true)}
            aria-label="增加缩进"
            title="增加缩进（Tab）"
          >
            <IndentIncrease size={15} />
          </Button>
          <Button
            size="sm"
            disabled={locked}
            onClick={() => run(indentLess, true)}
            aria-label="减少缩进"
            title="减少缩进（Shift Tab）"
          >
            <IndentDecrease size={15} />
          </Button>
          <Button
            size="sm"
            disabled={locked || !status.undo}
            onClick={() => run(undo, true)}
            aria-label={`撤销 ${editorLabel} 编辑`}
            title="撤销（Ctrl / ⌘ Z）"
          >
            <Undo2 size={15} />
          </Button>
          <Button
            size="sm"
            disabled={locked || !status.redo}
            onClick={() => run(redo, true)}
            aria-label={`重做 ${editorLabel} 编辑`}
            title="重做（Ctrl Y / ⌘ Shift Z）"
          >
            <Redo2 size={15} />
          </Button>
        </div>
        <Button
          size="sm"
          className="toml-help-toggle"
          aria-label={`${editorLabel} 快捷键帮助`}
          aria-expanded={helpOpen}
          onClick={() => setHelpOpen((open) => !open)}
          title="快捷键帮助"
        >
          <Keyboard size={16} />
        </Button>
      </div>
      {helpOpen && (
        <div className="toml-shortcuts" role="region" aria-label={`${editorLabel} 快捷键`}>
          <dl>
            <div>
              <dt>查找 / 替换</dt>
              <dd>Ctrl / ⌘ F</dd>
            </div>
            <div>
              <dt>定位行</dt>
              <dd>Ctrl / ⌘ Alt G</dd>
            </div>
            <div>
              <dt>缩进 / 取消缩进</dt>
              <dd>Tab / Shift Tab</dd>
            </div>
            {!isText && (
              <div>
                <dt>切换行注释</dt>
                <dd>Ctrl / ⌘ /</dd>
              </div>
            )}
            <div>
              <dt>撤销 / 重做</dt>
              <dd>Ctrl / ⌘ Z / Shift Z</dd>
            </div>
            <div>
              <dt>{isText ? '保存' : '保存并重载'}</dt>
              <dd>Ctrl / ⌘ S</dd>
            </div>
          </dl>
          <p>{!isText && '自动补全括号与引号。'}先按 Esc 再按 Tab 可离开编辑器；编辑不会自动整理全文。</p>
        </div>
      )}
      <div className="toml-editor-surface" ref={host} />
      <div className="toml-editor-status">
        <span>
          第 {status.line} 行，第 {status.column} 列
        </span>
        <span className="toml-editor-tab-hint">Tab 缩进 · Esc 后 Tab 离开</span>
        <span>
          {props.disabled
            ? '处理中'
            : props.readOnly
              ? '只读'
              : isText
                ? props.placeholders?.length
                  ? '模板'
                  : '纯文本'
                : 'TOML'}
        </span>
      </div>
    </div>
  );
}
