import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
  type Ref,
} from 'react';

export interface CodeEditorHandle {
  /** 在当前光标/选区插入，保持编辑器原生撤销历史；不可编辑时返回 false。 */
  insertText: (text: string) => boolean;
}

export interface TomlEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  saveDisabled?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  ariaLabel: string;
  describedBy?: string;
  fileName?: string;
  filePath?: string;
  language?: 'toml' | 'text';
  /** 纯文本模式仅为这些明确的模板占位符着色，不把人设当成代码解析。 */
  placeholders?: readonly string[];
  toolbarActions?: ReactNode;
}

export interface TomlEditorSelection {
  start: number;
  end: number;
  direction: 'forward' | 'backward' | 'none';
  focused: boolean;
  scrollTop: number;
}

export interface TomlEditorViewProps extends TomlEditorProps {
  initialSelection?: TomlEditorSelection;
  editorRef?: Ref<CodeEditorHandle>;
}

let editorModule: Promise<typeof import('./TomlEditorView')> | undefined;
const loadEditor = () => (editorModule ??= import('./TomlEditorView'));

/** 进入源码或文本编辑时再加载编辑器；加载期间继续使用同一份受控草稿。 */
const TomlEditor = forwardRef<CodeEditorHandle, TomlEditorProps>(function TomlEditor(props, ref) {
  const [Editor, setEditor] = useState<ComponentType<TomlEditorViewProps> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const fallback = useRef<HTMLTextAreaElement>(null);
  const handoff = useRef<TomlEditorSelection>();
  const enhanced = useRef<CodeEditorHandle>(null);
  const latest = useRef(props);
  latest.current = props;

  useImperativeHandle(
    ref,
    () => ({
      insertText(text) {
        const current = latest.current;
        if (current.disabled || current.readOnly) return false;
        if (enhanced.current) return enhanced.current.insertText(text);
        const input = fallback.current;
        if (!input) return false;
        const token = text.replace(/\r\n?/g, '\n');
        input.setRangeText(token, input.selectionStart, input.selectionEnd, 'end');
        const separator = current.value.match(/\r\n|\r|\n/)?.[0] || '\n';
        current.onChange(input.value.replace(/\n/g, separator));
        input.focus();
        return true;
      },
    }),
    [],
  );

  useEffect(() => {
    let active = true;
    loadEditor()
      .then((module) => {
        if (!active) return;
        const input = fallback.current;
        if (input) {
          handoff.current = {
            start: input.selectionStart,
            end: input.selectionEnd,
            direction: input.selectionDirection,
            focused: document.activeElement === input,
            scrollTop: input.scrollTop,
          };
        }
        setEditor(() => module.default);
      })
      .catch(() => {
        if (active) setLoadFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (Editor) return <Editor {...props} initialSelection={handoff.current} editorRef={enhanced} />;

  return (
    <div
      className="toml-code-editor toml-editor-fallback"
      data-readonly={!!props.readOnly || !!props.disabled}
    >
      {props.toolbarActions && (
        <div className="toml-editor-toolbar">
          <div className="toml-file-info">
            <code>{props.fileName || props.ariaLabel}</code>
          </div>
          {props.toolbarActions}
        </div>
      )}
      <div className="toml-editor-loading" role="status">
        {loadFailed ? '增强编辑器加载失败，仍可直接编辑和保存。' : '正在加载编辑工具，文本可继续编辑…'}
      </div>
      <textarea
        ref={fallback}
        className="toml-fallback-input"
        aria-label={props.ariaLabel}
        aria-describedby={props.describedBy}
        spellCheck={false}
        disabled={props.disabled}
        readOnly={props.readOnly}
        value={props.value}
        onChange={(event) => {
          if (!props.disabled && !props.readOnly) {
            const separator = props.value.match(/\r\n|\r|\n/)?.[0] || '\n';
            props.onChange(event.target.value.replace(/\n/g, separator));
          }
        }}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
            event.preventDefault();
            if (!props.disabled && !props.readOnly && !props.saveDisabled) props.onSave?.();
          }
        }}
      />
    </div>
  );
});

export default TomlEditor;
