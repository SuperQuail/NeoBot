// LongTextField.tsx —— 长文本控件（配置项里的提示词、JSON、多行说明都用它）
//
// 为什么替换掉原来的做法：原实现是「按当前文本长度在 <input> 与 <textarea> 之间切换」，
// 有一串实打实的问题：
//   1. 控件类型会在打字途中翻转（第 121 个字符触发）——DOM 节点被换掉，焦点与光标丢失；
//   2. rows 只数 \n，不数**折行**：591 字符写在一行里也只给 3 行高，必然出现滚动条；
//   3. 高度硬上限 8 行，长提示词被挤在小框里；
//   4. 组字期间受控回写会打断中文输入法（issue #67）。
// 这里改为「永远是 textarea + 按内容自动增高」：
//   - 类型稳定，不存在翻转，也就没有焦点丢失；
//   - 高度按 scrollHeight 实测（含折行），到上限才滚动；
//   - 单行意图（minRows=1 且内容无换行）时拦掉 Enter，语义等同单行输入框；
//   - 组字期间不回写、不提交，组字结束一次性提交。
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Icon from '../Icon';
import Modal from '../Modal';

export interface LongTextFieldProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  /** 初始行数；1 表示「单行意图」（拦 Enter），>1 表示允许换行 */
  minRows?: number;
  /** 自动增高的上限行数，超过则内部滚动 */
  maxRows?: number;
  monospace?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  ariaInvalid?: boolean;
  /** 行数/字符数指示 */
  showCount?: boolean;
  /** 是否提供「放大编辑」 */
  expandable?: boolean;
  /** 外部值变更时是否回灌（撤销/恢复默认场景需要） */
  syncExternal?: boolean;
}

const LINE_HEIGHT = 21;

export default function LongTextField({
  value,
  onChange,
  disabled,
  minRows = 1,
  maxRows = 18,
  monospace = false,
  placeholder,
  ariaLabel,
  ariaInvalid,
  showCount = true,
  expandable = true,
  syncExternal = true,
}: LongTextFieldProps) {
  const [text, setText] = useState(value ?? '');
  const [expanded, setExpanded] = useState(false);
  const composing = useRef(false);
  const inlineRef = useRef<HTMLTextAreaElement | null>(null);
  const modalRef = useRef<HTMLTextAreaElement | null>(null);

  // 外部值回灌（撤销 / 恢复默认 / 重新读取）；组字期间跳过，避免冲掉正在拼的字
  useEffect(() => {
    if (!syncExternal || composing.current) return;
    setText(value ?? '');
  }, [value, syncExternal]);

  // 自动增高：必须实测 scrollHeight —— 折行后的高度只有浏览器算得准，
  // 按 \n 计数正是原实现的错处。
  useLayoutEffect(() => {
    for (const el of [inlineRef.current, modalRef.current]) {
      if (!el) continue;
      el.style.height = 'auto';
      // scrollHeight = 内容 + padding，**不含边框**；而全局是 box-sizing: border-box，
      // 直接把它当高度会少 2px（上下各 1px 边框）→ 明明只占一行也冒出滚动条。
      const borderY = el.offsetHeight - el.clientHeight;
      const max = maxRows * LINE_HEIGHT + 22;
      const needed = el.scrollHeight + borderY;
      const next = expanded ? needed : Math.min(needed, max);
      el.style.height = next + 'px';
      el.style.overflowY = needed > next + 1 ? 'auto' : 'hidden';
    }
  }, [text, maxRows, expanded]);

  const allowNewline = minRows > 1 || text.includes('\n');

  const isComposingEvent = (event: { nativeEvent: Event }) =>
    (event.nativeEvent as Event & { isComposing?: boolean }).isComposing === true;

  const handleChange = (raw: string) => {
    setText(raw);
    // 组字中间态只留在本地，不写草稿、不触发受控回写
    if (composing.current) return;
    onChange(raw);
  };

  const compositionProps = {
    onCompositionStart: () => {
      composing.current = true;
    },
    onCompositionEnd: (event: { currentTarget: { value: string } }) => {
      composing.current = false;
      const next = event.currentTarget.value;
      setText(next);
      onChange(next);
    },
  };

  const lines = text ? text.split('\n').length : 0;

  const count = showCount ? (
    <span className="cfg-longtext-count">
      {lines} 行 · {text.length} 字符
    </span>
  ) : null;

  return (
    <div className="cfg-longtext">
      <textarea
        ref={inlineRef}
        className={'input cfg-longtext-area' + (monospace ? ' mono' : '')}
        spellCheck={false}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-invalid={ariaInvalid}
        rows={minRows}
        value={text}
        {...compositionProps}
        onChange={(event) => {
          if (isComposingEvent(event)) return;
          handleChange(event.target.value);
        }}
        onKeyDown={(event) => {
          // 单行意图：拦掉 Enter，保持与单行输入框一致（不会莫名多出换行）
          if (event.key === 'Enter' && !allowNewline) event.preventDefault();
        }}
      />
      <div className="cfg-longtext-bar">
        {count}
        {expandable && (
          <button type="button" className="btn-sm" disabled={disabled}
            title="在更大的窗口里编辑" onClick={() => setExpanded(true)}>
            <Icon name="external" /> 放大
          </button>
        )}
      </div>
      <Modal open={expanded} size="wide" title={'编辑 ' + (ariaLabel || '文本')} onClose={() => setExpanded(false)}>
        <textarea
          ref={modalRef}
          className={'input cfg-longtext-area cfg-longtext-modal' + (monospace ? ' mono' : '')}
          spellCheck={false}
          aria-label={(ariaLabel || '文本') + '（放大）'}
          value={text}
          {...compositionProps}
          onChange={(event) => {
            if (isComposingEvent(event)) return;
            handleChange(event.target.value);
          }}
        />
        <div className="cfg-longtext-bar">
          {count}
          <div style={{ flex: 1 }} />
          <button type="button" className="btn primary" onClick={() => setExpanded(false)}>完成</button>
        </div>
      </Modal>
    </div>
  );
}
