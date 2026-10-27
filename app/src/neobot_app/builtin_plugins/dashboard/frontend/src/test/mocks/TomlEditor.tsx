import { forwardRef, useImperativeHandle, useRef } from 'react';
import type { CodeEditorHandle, TomlEditorProps } from '../../components/TomlEditor';

/** 页面用例只验证编辑器与保存流程的契约；真实命令由 TomlEditor.test 覆盖。 */
const MockTomlEditor = forwardRef<CodeEditorHandle, TomlEditorProps>(function MockTomlEditor(props, ref) {
  const input = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({
    insertText(text) {
      if (props.readOnly || props.disabled || !input.current) return false;
      input.current.setRangeText(text, input.current.selectionStart, input.current.selectionEnd, 'end');
      props.onChange(input.current.value);
      input.current.focus();
      return true;
    },
  }));
  return (
    <>
      {props.toolbarActions}
      <textarea
        ref={input}
        data-language={props.language || 'toml'}
        aria-label={props.ariaLabel}
        aria-describedby={props.describedBy}
        value={props.value}
        disabled={props.disabled}
        readOnly={props.readOnly}
        onChange={(event) => props.onChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
            event.preventDefault();
            if (!props.disabled && !props.readOnly && !props.saveDisabled) props.onSave?.();
          }
        }}
      />
    </>
  );
});

export default MockTomlEditor;
