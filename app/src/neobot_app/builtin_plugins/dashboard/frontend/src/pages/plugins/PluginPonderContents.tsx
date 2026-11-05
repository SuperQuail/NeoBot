import { useState } from 'react';
import { Search } from 'lucide-react';
import type { PluginGuide } from '../../api/types';

interface Props {
  guide: PluginGuide;
  index: number;
  onSelect: (index: number) => void;
}

/** 全文只读取教程声明；选择步骤回到同一演示，不发起业务请求。 */
export default function PluginPonderContents({ guide, index, onSelect }: Props) {
  const [search, setSearch] = useState('');
  const query = search.trim().toLocaleLowerCase();
  const steps = guide.steps
    .map((step, position) => ({ step, position }))
    .filter(({ step }) =>
      [step.chapter, step.text, step.command?.text, step.command?.context, step.command?.reply].some(
        (value) => value?.toLocaleLowerCase().includes(query),
      ),
    );
  return (
    <section className="ponder-stage-viewport ponder-contents" aria-label="说明目录与全文">
      <div className="ponder-contents-search">
        <label>
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">搜索说明</span>
          <input
            className="input"
            type="search"
            value={search}
            placeholder="搜索章节、说明或命令"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <span role="status">
          {steps.length} / {guide.steps.length} 步
        </span>
      </div>
      <ol className="ponder-contents-list">
        {steps.map(({ step, position }) => (
          <li key={position} aria-current={position === index ? 'step' : undefined}>
            <button
              type="button"
              className="ponder-contents-step"
              aria-label={`查看第 ${position + 1} 步：${step.chapter || guide.title}`}
              onClick={() => onSelect(position)}
            >
              <span>{String(position + 1).padStart(2, '0')}</span>
              <strong>{step.chapter || guide.title}</strong>
              <span>查看演示</span>
            </button>
            <p>{step.text}</p>
            {step.command && (
              <div className="ponder-contents-command">
                <p>{step.command.context}</p>
                <code>{step.command.text}</code>
                {step.command.reply && <p>机器人回复示例：{step.command.reply}</p>}
              </div>
            )}
          </li>
        ))}
        {!steps.length && <li className="ponder-contents-empty">没有匹配的说明，请换个关键词。</li>}
      </ol>
    </section>
  );
}
