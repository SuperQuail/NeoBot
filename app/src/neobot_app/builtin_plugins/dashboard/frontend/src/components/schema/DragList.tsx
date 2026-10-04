// DragList.tsx —— 可拖拽排序的字符串列表（HTML5 DnD，无第三方依赖）
//
// 为什么需要它：allowed_read_dirs（只读目录）、web_search.engines（搜索引擎回退顺序）
// 这类数组**顺序有语义**，而且元素往往较长（路径/URL），塞进 chip 墙会很难看也难拖。
import { useRef, useState } from 'react';
import Icon from '../Icon';
import { Highlight } from './Highlight';

export interface DragListProps {
  items: string[];
  filter?: string;
  placeholder?: string;
  addLabel?: string;
  onChange: (next: string[]) => void;
}

export default function DragList({ items, filter, placeholder = '新值', addLabel = '添加', onChange }: DragListProps) {
  const [pending, setPending] = useState('');
  const dragging = useRef<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const commit = (index: number, value: string) => {
    const next = [...items];
    next[index] = value;
    onChange(next);
  };

  const remove = (index: number) => onChange(items.filter((_, i) => i !== index));

  const add = () => {
    const value = pending.trim();
    if (!value) return;
    onChange([...items, value]);
    setPending('');
  };

  const move = (from: number | null, to: number) => {
    if (from === null || from === to) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  };

  return (
    <div className="cfg-draglist">
      {items.map((item, index) => (
        <div
          key={index}
          className={'cfg-draglist-row' + (overIndex === index ? ' over' : '')}
          draggable
          onDragStart={(event) => {
            dragging.current = index;
            event.dataTransfer.effectAllowed = 'move';
            // Firefox 需要设置 data 才会真正开始拖拽
            event.dataTransfer.setData('text/plain', String(index));
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setOverIndex(index);
          }}
          onDragLeave={() => setOverIndex((current) => (current === index ? null : current))}
          onDrop={(event) => {
            event.preventDefault();
            move(dragging.current, index);
            dragging.current = null;
            setOverIndex(null);
          }}
          onDragEnd={() => {
            dragging.current = null;
            setOverIndex(null);
          }}
        >
          <span className="cfg-draglist-grip" title="拖拽排序" aria-hidden="true">⠿</span>
          <input
            className="input cfg-draglist-input"
            value={item}
            aria-label={'第 ' + (index + 1) + ' 项'}
            onChange={(event) => commit(index, event.target.value)}
          />
          {filter && <span className="cfg-match-hint"><Highlight text={item} keyword={filter} /></span>}
          <button type="button" className="cfg-row-remove" title="删除这一项" aria-label={'删除第 ' + (index + 1) + ' 项'}
            onClick={() => remove(index)}>×</button>
        </div>
      ))}
      <div className="cfg-draglist-row add">
        <span className="cfg-draglist-grip" aria-hidden="true" />
        <input
          className="input cfg-draglist-input"
          value={pending}
          placeholder={placeholder}
          onChange={(event) => setPending(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="btn-sm" disabled={!pending.trim()} onClick={add}>
          <Icon name="plus" /> {addLabel}
        </button>
      </div>
    </div>
  );
}
