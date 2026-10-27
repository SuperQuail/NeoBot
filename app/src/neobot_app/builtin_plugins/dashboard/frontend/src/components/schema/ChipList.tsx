// ChipList.tsx —— 短值数组的 chip 墙（group_list / reply_blacklist / admin_accounts …）
import { useState } from 'react';
import Icon from '../Icon';
import { Highlight } from './Highlight';

export interface ChipListProps {
  items: string[];
  filter?: string;
  placeholder?: string;
  disabled?: boolean;
  onChange: (next: string[]) => void;
}

export default function ChipList({ items, filter, placeholder = '新值', disabled, onChange }: ChipListProps) {
  const [pending, setPending] = useState('');

  const add = () => {
    if (disabled) return;
    const value = pending.trim();
    if (!value) return;
    onChange([...items, value]);
    setPending('');
  };

  return (
    <div className="cfg-chips">
      {items.length === 0 && <span className="cfg-chips-empty">空</span>}
      {items.map((item, index) => (
        <span className="cfg-chip" key={index} title={item}>
          <span className="cfg-chip-text">
            <Highlight text={item} keyword={filter} />
          </span>
          <button
            type="button"
            className="cfg-chip-remove"
            disabled={disabled}
            aria-label={'删除 ' + item}
            onClick={() => onChange(items.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </span>
      ))}
      <span className="cfg-chip cfg-chip-add">
        <input
          className="cfg-chip-input"
          disabled={disabled}
          value={pending}
          placeholder={placeholder}
          aria-label="添加一项"
          onChange={(event) => setPending(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
              event.preventDefault();
              add();
            }
          }}
        />
        <button
          type="button"
          className="cfg-chip-remove"
          aria-label="添加"
          disabled={disabled || !pending.trim()}
          onClick={add}
        >
          <Icon name="plus" />
        </button>
      </span>
    </div>
  );
}
